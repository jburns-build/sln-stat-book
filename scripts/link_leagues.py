#!/usr/bin/env python3
"""Join NDL careers to SLN careers so a player's page shows both leagues.

The two leagues do NOT share an id space — both number players 1..650 and the
same number is a different person on each side — so the only join key is the
NAME. That is not safe on its own: the SLN reuses real NBA names and the NDL
generates its own, so "Matt Geiger" is on the Iowa Wolves today and also played
for the 1996 Suns. Two different people.

The guard is career shape. A genuine call-up leaves an unmistakable signature —
the NDL career ends the year the SLN career begins:

    Danny Green    NDL 2009-2012 -> SLN 2012-2014
    Taj Gibson     NDL 2009-2011 -> SLN 2011-2019
    Quinton Wilson NDL 2020-2028 -> SLN 2029-2031

So a name links only when the two spans are adjacent or overlapping, the
overlap is short enough to be movement rather than two parallel careers, and
the combined career is a plausible length. Everything else is reported as
rejected rather than silently dropped, so a bad rule shows up in the build log.

Writes out/cross_league.json:
  ndl[name] -> that SLN player's NDL career (for the SLN stat book)
  sln[name] -> that NDL player's SLN seasons (for the NDL stat book)
"""
import json, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NDL = f"{ROOT}/out/ndl_careers.json"
SLN = f"{ROOT}/out/players_dataset.json"
OUT = f"{ROOT}/out/cross_league.json"

PRE = {"96": 1996, "97": 1997, "99": 1999}
MAX_GAP = 2        # seasons allowed between the two careers
MAX_OVERLAP = 3    # a player can bounce up and down; they can't play both for a decade
MAX_SPAN = 30      # combined first-to-last; the longest SLN careers run ~25


def yr(code, cur):
    return cur if code == "current" else PRE.get(code, 2000 + int(code) if code.isdigit() else 0)


def shape_ok(a, b):
    """Do two year-sets look like one career that crossed leagues?"""
    if not a or not b:
        return False, "empty"
    overlap = len(a & b)
    if overlap > MAX_OVERLAP:
        return False, f"overlap {overlap}y"
    if not (a & b):
        gap = max(min(b) - max(a), min(a) - max(b))   # the spans are disjoint
        if gap > MAX_GAP:
            return False, f"gap {gap}y"
    span = max(a | b) - min(a | b) + 1
    if span > MAX_SPAN:
        return False, f"span {span}y"
    return True, "ok"


def main():
    if not os.path.exists(NDL):
        sys.exit(f"missing {NDL} — run scrape_ndl_careers.py first")
    ndl = json.load(open(NDL))
    sln_ds = json.load(open(SLN))
    cur = max((s.get("order", 0) for s in sln_ds.get("seasons", [])), default=0)

    # SLN side: every rostered season, played or not. A 0-game SLN season is
    # itself evidence — that is what a year spent down in the NDL looks like
    # from the parent club's roster page.
    sln_rows = defaultdict(list)
    for p in sln_ds["players"]:
        y = yr(p["season"], cur)
        sln_rows[p["name"]].append({
            "yr": y, "team": p["team"], "season": p["season"], "rn": p.get("rn"),
            "g": p.get("g"), "mpg": p.get("mpg"), "ppg": p.get("ppg"),
            "rpg": p.get("rpg"), "apg": p.get("apg"), "spg": p.get("spg"),
            "bpg": p.get("bpg"), "tpg": p.get("tpg"), "fgp": p.get("fgp"),
            "ftp": p.get("ftp"), "tpp": p.get("tpp"),
        })
    for v in sln_rows.values():
        v.sort(key=lambda r: r["yr"])

    # NDL side: several records can share a name — an id reassigned to another
    # generated player, or one person who held two ids over their career. They
    # compete as candidates below and the best-fitting career shape wins.
    by_name = defaultdict(list)
    for key, rec in ndl["records"].items():
        by_name[rec["name"]].append(rec)

    links, rejected = [], []
    out_ndl, out_sln = {}, {}
    for name, recs in sorted(by_name.items()):
        if name not in sln_rows:
            continue
        sy = {r["yr"] for r in sln_rows[name]}
        # pick the candidate whose shape fits the SLN career best; ties go to
        # the one with more seasons (more evidence, and the fuller history)
        best = None
        for rec in recs:
            ny = {row[0] for row in rec["rows"]}
            ok, why = shape_ok(ny, sy)
            if not ok:
                rejected.append({"name": name, "ndl": f"{min(ny)}-{max(ny)}",
                                 "sln": f"{min(sy)}-{max(sy)}", "why": why})
                continue
            score = (len(ny), -abs(min(sy) - max(ny)))
            if best is None or score > best[0]:
                best = (score, rec, ny)
        if best is None:
            continue
        _, rec, ny = best
        # The move year is the season both leagues claim — a player splits it,
        # so it shows as games in one league and few or none in the other. When
        # the spans are merely adjacent, the move is the first year of whichever
        # career came second. Direction follows from which league had them first.
        ov = sorted(ny & sy)
        if ov:
            move = ov[0]
            direction = "up" if min(ny) < min(sy) else "down"
        elif min(sy) > max(ny):
            move, direction = min(sy), "up"
        else:
            move, direction = min(ny), "down"
        links.append({"name": name, "id": rec["id"],
                      "ndl": [min(ny), max(ny)], "sln": [min(sy), max(sy)],
                      "move": move, "dir": direction, "seasons": len(rec["rows"])})
        out_ndl[name] = {"id": rec["id"], "pos": rec.get("pos"),
                         "team": rec.get("team"), "rows": rec["rows"],
                         "awards": rec.get("awards") or [],
                         "dd": rec.get("dd", 0), "td": rec.get("td", 0),
                         "rings": rec.get("rings", 0),
                         "move": move, "dir": direction}
        out_sln[name] = {"rows": sln_rows[name], "move": move, "dir": direction}

    json.dump({"ndl": out_ndl, "sln": out_sln, "cols": ndl["cols"],
               "links": links, "rejected": rejected},
              open(OUT, "w"), separators=(",", ":"))

    print(f"cross-league: {len(links)} players linked, {len(rejected)} name "
          f"matches rejected on career shape")
    ups = sum(1 for l in links if l["dir"] == "up")
    print(f"  {ups} called up to the SLN, {len(links) - ups} sent down to the NDL")
    for l in sorted(links, key=lambda l: -l["move"])[:12]:
        mv = "called up" if l["dir"] == "up" else "sent down"
        print(f"  {l['name']:24s} NDL {l['ndl'][0]}-{l['ndl'][1]}"
              f"   SLN {l['sln'][0]}-{l['sln'][1]}   ({mv} {l['move']})")
    for r in rejected[:8]:
        print(f"  x {r['name']:24s} NDL {r['ndl']}  vs  SLN {r['sln']}   [{r['why']}]")
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)")


if __name__ == "__main__":
    main()
