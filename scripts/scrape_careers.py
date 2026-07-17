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
import json, os, re, sys, time, urllib.request, urllib.error

UA = {"User-Agent": "Mozilla/5.0 (research audit; polite)"}
B = "https://www.simleaguenirvana.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = f"{ROOT}/data/careers.json"
OUT = f"{ROOT}/out/careers_dataset.json"
PRE = {"96": 1996, "97": 1997, "99": 1999}


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


def main():
    ds = json.load(open(f"{ROOT}/out/players_dataset.json"))
    last = {}
    for p in ds["players"]:
        cur = last.get(p["name"])
        if cur is None or yr(p["season"]) > yr(cur["season"]):
            last[p["name"]] = p

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

    careers, fetched, cached = [], 0, 0
    for i, (name, p) in enumerate(sorted(last.items()), 1):
        key = f"{p['season']}:{p['id']}"
        active = p["season"] == "current"
        if not active and key in cache:          # retired careers never change
            careers.append(cache[key]); cached += 1; continue
        u_main, u_stats = urls(p["season"], p["id"])
        h_stats = fetch(u_stats); time.sleep(0.4)
        h_main = fetch(u_main);  time.sleep(0.4)
        fetched += 1
        if not h_stats:
            print(f"  !! no stats page for {name} ({key})")
            continue
        rec = parse_stats(h_stats)
        if not rec:
            print(f"  !! unparsable stats for {name} ({key})")
            continue
        rec.update(parse_main(h_main) if h_main else {})
        rec["name"] = name
        rec["pos"] = rec.get("pos") or p["pos"]
        rec["active"] = active
        rec["key"] = key
        if not active:
            cache[key] = rec
        careers.append(rec)
        if fetched % 100 == 0:
            print(f"  ...{i}/{len(last)} ({fetched} fetched, {cached} cached)", flush=True)

    json.dump(cache, open(CACHE, "w"), separators=(",", ":"))
    os.makedirs(f"{ROOT}/out", exist_ok=True)
    json.dump({"careers": careers}, open(OUT, "w"), separators=(",", ":"))
    print(f"careers: {len(careers)} players ({fetched} fetched, {cached} from cache)")
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes); cache {len(cache)} retired")
    if len(careers) < 1500:
        sys.exit(f"ERROR: only {len(careers)} careers — refusing to continue.")


if __name__ == "__main__":
    main()
