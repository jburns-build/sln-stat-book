#!/usr/bin/env python3
"""Archive NDL career histories — the league publishes no NDL season archive.

Every /NDL/history/... path 404s, so past NDL seasons cannot be re-read as
roster pages. But each NDL player page embeds player{ID}stats.htm holding that
player's FULL season-by-season line (raw FG/FGA/FT/FTA/3P/3PA, plus DQ and a
published PPG the SLN pages don't carry). So the only surviving record of NDL
history is whatever the currently-allocated ids happen to remember.

That record decays: ids are recycled, and when one is reassigned its previous
occupant's career disappears from the site for good. So this cache is an
APPEND-ONLY ARCHIVE, keyed "{id}:{name}" — a recycled id starts a new record
and the old one is kept forever. Coverage today runs back to 2003, thinning as
it goes (2038 ~100%, 2037 ~90%, 2036 ~65%, under 20% before 2031); it only
improves for seasons captured from here on.

Fetch policy (mirrors scrape_careers.py):
  - a player on a current NDL roster is re-fetched only when their game count
    moved since the cached snapshot;
  - everyone else is settled -> cache hit, zero network;
  - the id space is swept for unknown ids on the first run and whenever the
    season rolls over (the draft is when ids get reassigned).
"""
import json, os, re, sys, time, datetime, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

UA = {"User-Agent": "Mozilla/5.0 (research audit; polite)"}
B = "https://www.simleaguenirvana.com/NDL"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = f"{ROOT}/data/ndl_careers.json"
OUT = f"{ROOT}/out/ndl_careers.json"
DS = f"{ROOT}/out/ndl_players_dataset.json"

CACHE_ONLY = "--cache-only" in sys.argv
FORCE_SWEEP = "--sweep" in sys.argv
MAX_ID = 760              # live space tops out at 650; probe past it for headroom
BUDGET = float(os.environ.get("NDL_CAREERS_BUDGET_SECONDS", "0"))
START = time.monotonic()
WORKERS = 6               # small pool; the host is a single old IIS box
PAUSE = 0.15

# stats-page columns we keep, in output order (after year + team)
ROW_COLS = ["Games", "MPG", "FG", "FGA", "FT", "FTA", "3P", "3PA",
            "RPG", "APG", "SPG", "BPG", "TOPG", "DQ", "PPG"]
INT_COLS = {"Games", "FG", "FGA", "FT", "FTA", "3P", "3PA", "DQ"}


def out_of_time():
    return bool(BUDGET) and (time.monotonic() - START) > BUDGET


def fetch(url, attempts=3, timeout=20):
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("latin-1") if r.status == 200 else None
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == attempts - 1:
                return None
            time.sleep(2 * (i + 1))
        except Exception:
            if i == attempts - 1:
                return None
            time.sleep(2 * (i + 1))


def cells(row):
    return [c for c in [re.sub("<[^>]+>", "", x).replace("&nbsp;", " ").strip()
                        for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.I | re.S)] if c]


def num(x):
    try:
        return float(x.replace(",", ""))
    except Exception:
        return 0.0


def parse_stats(html):
    """Season-by-season rows from player{ID}stats.htm -> [year, team, *ROW_COLS].

    Header-indexed rather than positional: the NDL table carries DQ and PPG
    columns the SLN one doesn't, and neither layout is guaranteed stable.
    """
    rows = [cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S)]
    hdr = next((r for r in rows if r and r[0] == "Season"), None)
    if not hdr:
        return None
    ix = {k: i for i, k in enumerate(hdr)}
    seasons = [r for r in rows if r and re.fullmatch(r"\d{4}", r[0]) and len(r) >= len(hdr)]
    if not seasons:
        return []

    def g(r, k):
        return num(r[ix[k]]) if k in ix and ix[k] < len(r) else 0.0

    out = []
    for r in seasons:
        vals = [int(g(r, c)) if c in INT_COLS else g(r, c) for c in ROW_COLS]
        out.append([int(r[0]), r[1] if len(r) > 1 else ""] + vals)
    return out


def parse_main(html):
    """Name/pos/team, career achievements and the dated award list."""
    out = {}
    m = re.search(r"<title>\s*(\w+)\s+(.*?)\s+-\s+(.*?)</title>", html, re.I | re.S)
    if m:
        out["pos"], out["name"], out["team"] = (m.group(1), m.group(2).strip(),
                                                m.group(3).strip())
    aw = re.search(r"<textarea[^>]*name=\"Awards\"[^>]*>(.*?)</textarea>",
                   html, re.I | re.S)
    if aw:
        # "YYYY - Award"; the Rookie Game is a separate event from the All-Star
        # Game, same as on the SLN side
        out["awards"] = [" ".join(ln.split()) for ln in aw.group(1).splitlines()
                         if re.match(r"\s*\d{4}\s+-\s+\S", ln)]
    txt = re.sub(r"<textarea.*?</textarea>", " ", html, flags=re.I | re.S)
    txt = re.sub(r"<[^>]+>", "|", txt).replace("&nbsp;", " ")
    for label, key in [("Double Doubles", "dd"), ("Triple Doubles", "td"),
                       ("Championships", "rings"), ("Player of the Game", "potg")]:
        m = re.search(re.escape(label) + r":[\s|]*([\d,]+)", txt)
        out[key] = int(m.group(1).replace(",", "")) if m else 0
    return out


def pull(pid):
    """Both pages for one id -> a record, or None when the id is unallocated.
    A record with rows == [] is a real player who has yet to play a game."""
    h_stats = fetch(f"{B}/players/player{pid}stats.htm")
    time.sleep(PAUSE)
    h_main = fetch(f"{B}/players/player{pid}.htm")
    time.sleep(PAUSE)
    if not h_main:
        return None
    rec = parse_main(h_main)
    if not rec.get("name"):
        return None
    rec["id"] = pid
    rec["rows"] = parse_stats(h_stats) or []
    if rec["rows"]:
        rec["first"], rec["last"] = rec["rows"][0][0], rec["rows"][-1][0]
    return rec


def key_of(pid, name):
    return f"{pid}:{name}"


def main():
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    os.makedirs(f"{ROOT}/out", exist_ok=True)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    recs = cache.setdefault("records", {})
    before = len(recs)

    ds = json.load(open(DS)) if os.path.exists(DS) else {"players": [], "seasons": []}
    season_year = max((s.get("order", 0) for s in ds.get("seasons", [])), default=0)
    # current NDL rosters: the only players whose careers can still move
    roster = {p["id"]: (p["name"], int(p.get("g") or 0)) for p in ds["players"]}

    fetched_at = (cache.get("_fetched_at", "unknown") if CACHE_ONLY else
                  datetime.datetime.now(ZoneInfo("America/Los_Angeles")).strftime(
                      "%b %d, %Y · %-I:%M %p %Z"))

    stats = {"fetched": 0, "cached": 0, "new": 0, "updated": 0, "swept": 0, "skipped": 0}

    def store(rec, chk=None):
        k = key_of(rec["id"], rec["name"])
        stats["updated" if k in recs else "new"] += 1
        if chk:
            # what roster state this snapshot was taken against, so an
            # unchanged player is never re-fetched — including one whose
            # stats page has no row yet for the live season (a call-up)
            rec["chk"] = chk
        recs[k] = rec

    # ---- 1. players on current rosters: refetch only if their games moved ----
    todo = []
    for pid, (name, g) in sorted(roster.items()):
        old = recs.get(key_of(pid, name))
        if old and old.get("chk") == [season_year, g]:
            stats["cached"] += 1
        else:
            todo.append(pid)

    def run(ids, label, chk_from_roster=False):
        if not ids:
            return
        print(f"{label}: {len(ids)} ids to fetch", flush=True)
        with ThreadPoolExecutor(WORKERS) as ex:
            for i, (pid, rec) in enumerate(zip(ids, ex.map(pull, ids)), 1):
                stats["fetched"] += 1
                if rec:
                    chk = ([season_year, roster[pid][1]]
                           if chk_from_roster and pid in roster else None)
                    store(rec, chk)
                if i % 100 == 0:
                    print(f"  ...{i}/{len(ids)}", flush=True)

    if CACHE_ONLY or out_of_time():
        stats["skipped"] += len(todo)
        todo = []
    run(todo, "roster refresh", chk_from_roster=True)

    # ---- 2. sweep the id space for players no roster mentions ----
    # Called-up, waived, free-agent and long-retired players keep their pages;
    # they are most of the recoverable history. Sweeping is only worth its cost
    # on a first run or after a rollover, when the draft reassigns ids.
    known_ids = {int(k.split(":", 1)[0]) for k in recs}
    need_sweep = (FORCE_SWEEP or not cache.get("_swept_at")
                  or cache.get("_sweep_year") != season_year)
    if need_sweep and not CACHE_ONLY and not out_of_time():
        # On a rollover re-probe everything (a recycled id now holds someone
        # else); on a first run only the ids we have never seen.
        full = FORCE_SWEEP or (cache.get("_sweep_year") not in (None, season_year))
        cand = [i for i in range(1, MAX_ID + 1)
                if (full or i not in known_ids) and i not in roster]
        stats["swept"] = len(cand)
        run(cand, "id sweep")
        cache["_swept_at"] = fetched_at
        cache["_sweep_year"] = season_year
    elif need_sweep:
        print("sweep due but skipped (cache-only / out of time)")

    # ---- 3. write ----
    # the archive only ever grows; losing records means a bad parse, not news
    if len(recs) < before:
        sys.exit(f"ERROR: archive shrank ({before} -> {len(recs)}). Refusing to write.")
    played = {k: r for k, r in recs.items() if r.get("rows")}
    if not CACHE_ONLY and len(played) < 300:
        sys.exit(f"ERROR: only {len(played)} NDL careers with games — refusing to write.")

    if not CACHE_ONLY:
        cache["_fetched_at"] = fetched_at
        json.dump(cache, open(CACHE, "w"), separators=(",", ":"))

    rows = sum(len(r["rows"]) for r in played.values())
    years = sorted({row[0] for r in played.values() for row in r["rows"]})
    json.dump({"records": played, "cols": ROW_COLS, "fetched": fetched_at},
              open(OUT, "w"), separators=(",", ":"))

    print(f"ndl careers: {len(played)} players with games ({len(recs)} records, "
          f"{before} before), {rows} player-seasons, "
          f"{years[0] if years else '-'}–{years[-1] if years else '-'}")
    print(f"  {stats['fetched']} fetched ({stats['new']} new, {stats['updated']} updated), "
          f"{stats['cached']} cached, {stats['swept']} swept, {stats['skipped']} skipped")
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)")


if __name__ == "__main__":
    main()
