#!/usr/bin/env python3
"""Build career totals for every SLN player, for the Records page.

Each player page embeds an iframe, player{ID}stats.htm, holding their full
career season-by-season with RAW totals (FG/FGA/FT/FTA/3P/3PA). The main
player page carries career Double/Triple Doubles. Together those give the same
categories the site's Player Career Records page shows a single leader for.

Exact:  Games, FG, FT, 3P, Points (= 2*FG + 3P + FT), Double/Triple Doubles.
        (Verified against the site's own records: Luka = 48,683 pts, 18,621 FG.)
Approx: Reb/Ast/Stl/Blk/TO — published only as per-game averages, so summing
        RPG*G carries ~0.1% rounding. Flagged as approximate in the UI.

A player's LAST stint's page holds their complete career, so we fetch one page
pair per player. Retired careers never change -> cached forever in
data/careers.json (committed). Only active players are re-fetched.
"""
import json, os, re, sys, time, datetime, urllib.request, urllib.error
from zoneinfo import ZoneInfo

UA = {"User-Agent": "Mozilla/5.0 (research audit; polite)"}
B = "https://www.simleaguenirvana.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = f"{ROOT}/data/careers.json"
OUT = f"{ROOT}/out/careers_dataset.json"
PRE = {"96": 1996, "97": 1997, "99": 1999}
# --cache-only: rebuild careers from the committed cache with ZERO network. Used
# by the fast stat-book refresh (manual button / frequent cron); a daily run does
# the real fetch. Career totals aren't real-time, so a day-old cache is fine.
CACHE_ONLY = "--cache-only" in sys.argv
# On a network-degraded CI runner a full fetch can crawl; cap wall-clock time
# spent fetching (0 = unlimited, e.g. local). Past the budget we fall back to
# cache so the run finishes and publishes instead of hitting the job timeout.
BUDGET = float(os.environ.get("CAREERS_BUDGET_SECONDS", "0"))
START = time.monotonic()


def yr(s):
    return 2038 if s == "current" else PRE.get(s, 2000 + int(s) if s.isdigit() else 0)


# inverse of yr(): calendar year -> season code used in URLs
def code_for_year(y):
    if y == 2038:
        return "current"
    if y in (1996, 1997, 1999):
        return str(y)[2:]
    return f"{y - 2000:02d}"


def fetch(url, attempts=3, timeout=20):
    for i in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("latin-1") if r.status == 200 else None
        except urllib.error.HTTPError:
            return None
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
    """Career totals from the player{ID}stats.htm iframe table."""
    rows = [cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S)]
    hdr = next((r for r in rows if r and r[0] == "Season"), None)
    if not hdr:
        return None
    seasons = [r for r in rows if r and re.fullmatch(r"\d{4}", r[0]) and len(r) >= len(hdr)]
    if not seasons:
        return None
    ix = {k: hdr.index(k) for k in hdr}
    g = lambda r, k: num(r[ix[k]]) if k in ix and ix[k] < len(r) else 0.0
    tot = {"games": 0, "fg": 0, "fga": 0, "ft": 0, "fta": 0, "tp": 0, "tpa": 0,
           "reb": 0.0, "ast": 0.0, "stl": 0.0, "blk": 0.0, "tov": 0.0, "mp": 0.0}
    for r in seasons:
        gm = g(r, "Games")
        tot["games"] += gm
        for k, col in [("fg", "FG"), ("fga", "FGA"), ("ft", "FT"), ("fta", "FTA"),
                       ("tp", "3P"), ("tpa", "3PA")]:
            tot[k] += g(r, col)
        for k, col in [("reb", "RPG"), ("ast", "APG"), ("stl", "SPG"),
                       ("blk", "BPG"), ("tov", "TOPG"), ("mp", "MPG")]:
            tot[k] += g(r, col) * gm
    tot["pts"] = 2 * tot["fg"] + tot["tp"] + tot["ft"]          # exact
    tot["seasons"] = len(seasons)
    tot["first"] = int(seasons[0][0])
    tot["last"] = int(seasons[-1][0])
    tot["years"] = [int(r[0]) for r in seasons]      # the window this page covers
    tot["teams"] = sorted({r[1] for r in seasons if len(r) > 1})
    # the page's own "Career:" row carries the official per-game averages
    # (computed once, not season-rounded) — read them directly so PPG/RPG/APG/
    # SPG/BPG match each player's page exactly instead of being re-derived
    car = next((r for r in rows if r and r[0].lower().startswith("career")), None)
    if car:
        tot["pg"] = {k: g(car, col) for k, col in
                     [("ppg", "PPG"), ("rpg", "RPG"), ("apg", "APG"),
                      ("spg", "SPG"), ("bpg", "BPG")]}
    return tot


def parse_main(html):
    """Career Double/Triple Doubles + championships from the player page."""
    txt = re.sub(r"<textarea.*?</textarea>", " ", html, flags=re.I | re.S)
    txt = re.sub(r"<[^>]+>", "|", txt).replace("&nbsp;", " ")
    out = {}
    for label, key in [("Double Doubles", "dd"), ("Triple Doubles", "td"),
                       ("Championships", "rings"), ("Player of the Game", "potg")]:
        # an empty spacer <td> sits between label and value, so allow any run
        # of pipes/whitespace between them
        m = re.search(re.escape(label) + r":[\s|]*([\d,]+)", txt)
        out[key] = int(m.group(1).replace(",", "")) if m else 0
    m = re.search(r"<title>\s*(\w+)\s+(.*?)\s+-\s+(.*?)</title>", html, re.I | re.S)
    if m:
        out["pos"], out["name"], out["team"] = m.group(1), m.group(2).strip(), m.group(3).strip()
    return out


def urls(season, pid):
    base = f"{B}/players" if season == "current" else f"{B}/history/{season}/players"
    return f"{base}/player{pid}.htm", f"{base}/player{pid}stats.htm"


# numeric fields summed across a player's stints to form one career
SUM_FIELDS = ["games", "fg", "fga", "ft", "fta", "tp", "tpa", "reb", "ast",
              "stl", "blk", "tov", "mp", "pts", "dd", "td", "seasons"]


def main():
    from collections import defaultdict
    players = json.load(open(f"{ROOT}/out/players_dataset.json"))["players"]
    years = sorted({yr(p["season"]) for p in players})
    idx = {y: i for i, y in enumerate(years)}    # real-season ordinal (no 1998)

    # name -> {id -> {'years':set, 'season':last code for that id, 'y':last yr, 'pos'}}
    byname = defaultdict(dict)
    for p in players:
        y = yr(p["season"])
        u = byname[p["name"]].setdefault(
            p["id"], {"years": set(), "pyears": set(), "season": p["season"],
                      "y": y, "pos": p["pos"]})
        u["years"].add(y)
        if (p.get("g") or 0) > 0:                     # years the id actually played
            u["pyears"].add(y)
        if y >= u["y"]:
            u["y"], u["season"], u["pos"] = y, p["season"], p["pos"]

    # a live player's career only changes when they play a game, so cache their
    # slice keyed by current game count — unchanged games => cache hit, no fetch
    cur_games = {p["id"]: int(p["g"] or 0) for p in players if p["season"] == "current"}

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    stats = {"fetched": 0, "cached": 0, "skipped": 0}
    used = set()                                   # cache keys touched this run

    # when the career totals were last actually fetched (only a full run refetches;
    # cache-only builds carry the previous value forward so the page can show it)
    if CACHE_ONLY:
        fetched_at = cache.get("_fetched_at", "unknown")
    else:
        fetched_at = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).strftime(
            "%b %d, %Y · %-I:%M %p %Z")
        cache["_fetched_at"] = fetched_at

    def cached_current(pid):
        """Most recent cached live-stint snapshot for an id (any game count)."""
        best, bg = None, -1
        for k, v in cache.items():
            m = re.match(rf"current:{pid}:g(\d+)$", k)
            if m and int(m.group(1)) > bg:
                bg, best = int(m.group(1)), v
        return best

    def snapshot(code, pid):
        """One career-stats-page window for an id, as published at season `code`.
        Retired windows never change -> cached forever; the live window is cached
        against its game count."""
        ck = f"current:{pid}:g{cur_games.get(pid, 0)}" if code == "current" else f"{code}:{pid}"
        used.add(ck)
        if ck in cache:
            stats["cached"] += 1
            return cache[ck]
        # No fetch if cache-only, or if we've blown the time budget (degraded
        # runner): fall back to the best cached snapshot so the build still ships
        # a mostly-fresh records page instead of timing out. Missing players just
        # wait for the next daily run.
        out_of_time = BUDGET and (time.monotonic() - START) > BUDGET
        if CACHE_ONLY or out_of_time:
            stats["skipped" if out_of_time else "cached"] += 1
            if code == "current":
                snap = cached_current(pid)
                if snap:
                    used.add(f"current:{pid}:g{int(snap.get('games', 0))}")
                return snap
            return None
        u_main, u_stats = urls(code, pid)
        h_stats = fetch(u_stats); time.sleep(0.4)
        h_main = fetch(u_main);  time.sleep(0.4)
        stats["fetched"] += 1
        rec = parse_stats(h_stats) if h_stats else None
        if not rec:
            return None
        rec.update(parse_main(h_main) if h_main else {})
        rec["key"] = f"{code}:{pid}"               # clean key for player-page links
        cache[ck] = rec
        return rec

    def unit(pid, season, pyears):
        """Full career slice for one id. The stats page normally holds the id's
        whole career, but the sim sometimes RESETS a player's page to a fresh
        window mid-id (an un-retirement that keeps the same id — e.g. LeBron id3
        was reset from his 2020-25 window to a blank 2026-29 one). The last-season
        snapshot then omits the earlier window entirely. So: take the last window,
        then while the id was known to PLAY seasons below the earliest window we've
        collected, walk back and fetch the window ending at that season, summing
        the (non-overlapping) windows into one career slice."""
        windows, guard, covered_first = [], set(), None
        code = season
        while code is not None and code not in guard:
            guard.add(code)
            rec = snapshot(code, pid)
            if rec is None:
                break
            wfirst, wlast = rec.get("first", 0), rec.get("last", 0)
            if covered_first is not None and wlast >= covered_first:
                break                                # overlaps what we have -> stop
            windows.append(rec)
            covered_first = wfirst
            below = [y for y in (pyears or []) if y < wfirst]
            code = code_for_year(max(below)) if below else None
        if not windows:
            return None
        if len(windows) == 1:
            return windows[0]                        # common case: one clean window
        merged = {"name": windows[0].get("name")}
        for f in SUM_FIELDS:
            merged[f] = sum(w.get(f, 0) or 0 for w in windows)
        sw = sum((w.get("games") or 0) for w in windows if w.get("pg"))
        if sw:                                       # games-weight the window averages
            merged["pg"] = {k: sum((w["pg"].get(k) or 0) * (w.get("games") or 0)
                                   for w in windows if w.get("pg")) / sw
                            for k in ("ppg", "rpg", "apg", "spg", "bpg")}
        merged["key"] = windows[0].get("key")        # newest window = player-page link
        merged["pos"] = windows[0].get("pos")
        merged["first"] = min(w.get("first", 9999) for w in windows)
        merged["last"] = max(w.get("last", 0) for w in windows)
        teams = []
        for w in reversed(windows):                  # oldest-first team order
            for t in (w.get("teams") or []):
                if t not in teams:
                    teams.append(t)
        merged["teams"] = teams
        return merged

    careers, missing = [], []
    for n, (name, idmap) in enumerate(sorted(byname.items()), 1):
        # split the player's ids into careers on a >=3 real-season gap; an
        # un-retirement (contiguous new id) stays one career, a different player
        # reusing the name (big gap) becomes a separate one.
        segs = []
        for pid in sorted(idmap, key=lambda i: min(idmap[i]["years"])):
            ymin = min(idmap[pid]["years"])
            if segs and idx[ymin] - idx[segs[-1]["maxy"]] < 3:
                segs[-1]["ids"].append(pid)
                segs[-1]["maxy"] = max(segs[-1]["maxy"], max(idmap[pid]["years"]))
            else:
                segs.append({"ids": [pid], "maxy": max(idmap[pid]["years"])})

        for seg in segs:
            units = []
            for pid in seg["ids"]:
                rec = unit(pid, idmap[pid]["season"], sorted(idmap[pid]["pyears"]))
                if rec is None:
                    missing.append(f"{name} {idmap[pid]['season']}:{pid}")
                else:
                    units.append((pid, rec))
            if not units:
                continue
            car = {"name": name}
            for f in SUM_FIELDS:
                car[f] = sum(u[1].get(f, 0) or 0 for u in units)
            # per-game averages: read the page's official Career-row values.
            # One stint -> exact page value; bundled un-retirements -> games-weighted.
            pg = {}
            for k in ("ppg", "rpg", "apg", "spg", "bpg"):
                sw = sum((u[1].get("games") or 0) for u in units if u[1].get("pg"))
                if sw:
                    pg[k] = sum((u[1]["pg"].get(k) or 0) * (u[1].get("games") or 0)
                                for u in units if u[1].get("pg")) / sw
            if pg:
                car["pg"] = pg
            yrs = sorted({y for pid in seg["ids"] for y in idmap[pid]["years"]})
            car["first"], car["last"] = yrs[0], yrs[-1]
            car["active"] = any(idmap[pid]["season"] == "current" for pid in seg["ids"])
            latest = max(units, key=lambda u: idmap[u[0]]["y"])
            car["key"], car["pos"] = latest[1]["key"], idmap[latest[0]]["pos"]
            teams = []
            for _, rec in units:
                for t in (rec.get("teams") or []):
                    if t not in teams:
                        teams.append(t)
            car["teams"] = teams
            careers.append(car)
        if n % 300 == 0:
            print(f"  ...{n}/{len(byname)} names "
                  f"({stats['fetched']} fetched, {stats['cached']} cached)", flush=True)

    if not CACHE_ONLY:
        # drop superseded live-stint snapshots (old game counts); keep all retired
        cache = {k: v for k, v in cache.items()
                 if not k.startswith("current:") or k in used}
        json.dump(cache, open(CACHE, "w"), separators=(",", ":"))
    os.makedirs(f"{ROOT}/out", exist_ok=True)
    json.dump({"careers": careers, "fetched": fetched_at}, open(OUT, "w"),
              separators=(",", ":"))
    for m in missing:
        print(f"  !! no stats page: {m}")
    budget_note = f", {stats['skipped']} skipped (time budget)" if stats["skipped"] else ""
    print(f"careers: {len(careers)} ({stats['fetched']} fetched, "
          f"{stats['cached']} from cache{budget_note})")
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes); cache {len(cache)} retired stints")
    if len(careers) < 1500:
        sys.exit(f"ERROR: only {len(careers)} careers — refusing to continue.")


if __name__ == "__main__":
    main()
