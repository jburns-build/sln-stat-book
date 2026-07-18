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


def yr(s):
    return 2038 if s == "current" else PRE.get(s, 2000 + int(s) if s.isdigit() else 0)


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
    tot["teams"] = sorted({r[1] for r in seasons if len(r) > 1})
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
            p["id"], {"years": set(), "season": p["season"], "y": y, "pos": p["pos"]})
        u["years"].add(y)
        if y >= u["y"]:
            u["y"], u["season"], u["pos"] = y, p["season"], p["pos"]

    # a live player's career only changes when they play a game, so cache their
    # slice keyed by current game count — unchanged games => cache hit, no fetch
    cur_games = {p["id"]: int(p["g"] or 0) for p in players if p["season"] == "current"}

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    stats = {"fetched": 0, "cached": 0}
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

    def unit(pid, season):
        """Per-id career slice (its own stats page). Retired stints are cached
        forever; the live stint is cached against its game count."""
        ck = f"current:{pid}:g{cur_games.get(pid, 0)}" if season == "current" else f"{season}:{pid}"
        used.add(ck)
        if ck in cache:
            stats["cached"] += 1
            return cache[ck]
        if CACHE_ONLY:                             # no network: use best available
            stats["cached"] += 1
            if season == "current":
                snap = cached_current(pid)
                if snap:
                    used.add(f"current:{pid}:g{int(snap.get('games', 0))}")
                return snap
            return None
        u_main, u_stats = urls(season, pid)
        h_stats = fetch(u_stats); time.sleep(0.4)
        h_main = fetch(u_main);  time.sleep(0.4)
        stats["fetched"] += 1
        rec = parse_stats(h_stats) if h_stats else None
        if not rec:
            return None
        rec.update(parse_main(h_main) if h_main else {})
        rec["key"] = f"{season}:{pid}"             # clean key for player-page links
        cache[ck] = rec
        return rec

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
                rec = unit(pid, idmap[pid]["season"])
                if rec is None:
                    missing.append(f"{name} {idmap[pid]['season']}:{pid}")
                else:
                    units.append((pid, rec))
            if not units:
                continue
            car = {"name": name}
            for f in SUM_FIELDS:
                car[f] = sum(u[1].get(f, 0) or 0 for u in units)
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
    print(f"careers: {len(careers)} ({stats['fetched']} fetched, {stats['cached']} from cache)")
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes); cache {len(cache)} retired stints")
    if len(careers) < 1500:
        sys.exit(f"ERROR: only {len(careers)} careers — refusing to continue.")


if __name__ == "__main__":
    main()
