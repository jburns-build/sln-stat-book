#!/usr/bin/env python3
"""Fold archived NDL seasons back into the NDL stat book's Year dropdown.

The NDL publishes no season archive, so past NDL seasons only exist as the
per-player career lines scrape_ndl_careers.py keeps. Pivoting that archive by
year rebuilds a season table — but an incomplete one, because it can only
contain players whose ids are still allocated. Coverage decays the further back
you go, so a year is only offered once it holds enough of the league to be worth
reading, and anything below FULL_COV is labelled partial and has its leader
highlighting suppressed (a "league leader" out of half a league is not one).

Idempotent: every non-current season is rebuilt from the archive each run.

What a reconstructed row cannot have: age, ability grades, salary, and the
roster number (the archive stores a team nickname, not a roster link), so those
columns read "—" for historical seasons. What it gains over a roster row: raw
makes and attempts, so the Advanced view's TS%/eFG% work for archived NDL
seasons even though the live NDL roster pages never publish attempts.
"""
import json, os, re, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = f"{ROOT}/out/ndl_players_dataset.json"
ARCH = f"{ROOT}/out/ndl_careers.json"

MIN_COV = 0.40    # below this a season is too thin to publish at all
FULL_COV = 0.85   # below this it publishes, but flagged partial (no leaders)

# archive row layout: [year, team, *cols]
def col(cols, k):
    return cols.index(k) + 2


def main():
    if not os.path.exists(ARCH):
        sys.exit(f"missing {ARCH} — run scrape_ndl_careers.py first")
    ds = json.load(open(DS))
    arch = json.load(open(ARCH))
    cols, recs = arch["cols"], arch["records"]

    cur = max((s.get("order", 0) for s in ds["seasons"]), default=0)
    # a full NDL season is one roster spot per player currently in the league
    full = sum(1 for p in ds["players"] if p["season"] == "current") or 348

    # rebuild from scratch so re-running never duplicates rows
    ds["players"] = [p for p in ds["players"] if p["season"] == "current"]
    ds["seasons"] = [s for s in ds["seasons"] if s["key"] == "current"]

    # an id can appear under several names over the years; only the newest
    # occupant is the one the live player page still shows, so only their rows
    # may link out
    newest = {}
    for rec in recs.values():
        cur_best = newest.get(rec["id"])
        if cur_best is None or rec.get("last", 0) > cur_best.get("last", 0):
            newest[rec["id"]] = rec

    G, MPG, PPG = col(cols, "Games"), col(cols, "MPG"), col(cols, "PPG")
    RPG, APG = col(cols, "RPG"), col(cols, "APG")
    SPG, BPG, TOPG = col(cols, "SPG"), col(cols, "BPG"), col(cols, "TOPG")
    FG, FGA, FT, FTA, TP, TPA = (col(cols, k) for k in
                                 ("FG", "FGA", "FT", "FTA", "3P", "3PA"))

    rows_by_year = defaultdict(list)
    for key, rec in recs.items():
        # "YYYY - Award" lines -> that season's award chips
        awards = defaultdict(list)
        for a in rec.get("awards") or []:
            m = re.match(r"(\d{4})\s+-\s+(.*)", a)
            if m:
                awards[int(m.group(1))].append(m.group(2).strip())
        live = newest.get(rec["id"]) is rec
        for r in rec["rows"]:
            y, g = r[0], r[G]
            if y >= cur or not g:          # the live season comes from rosters
                continue
            pct = lambda made, att: round(r[made] / r[att], 3) if r[att] else 0.0
            rows_by_year[y].append({
                "season": str(y), "team": r[1], "rn": None, "id": rec["id"],
                "name": rec["name"], "pos": rec.get("pos"), "age": None,
                "awards": awards.get(y, []), "abil": None, "sal1": None, "yrs": None,
                "g": float(g), "mpg": r[MPG], "ppg": r[PPG], "rpg": r[RPG],
                "apg": r[APG], "spg": r[SPG], "bpg": r[BPG], "tpg": r[TOPG],
                "fgp": pct(FG, FGA), "ftp": pct(FT, FTA), "tpp": pct(TP, TPA),
                # raw shooting -> Advanced view (TS%/eFG%/3PAr/FTr)
                "sh": [g, r[FG], r[FGA], r[FT], r[FTA], r[TP], r[TPA]],
                "hist": 1, **({"live": 1} if live else {}),
            })

    kept, dropped = [], []
    for y in sorted(rows_by_year):
        cov = len(rows_by_year[y]) / full
        (kept if cov >= MIN_COV else dropped).append((y, cov))

    for y, cov in kept:
        partial = cov < FULL_COV
        ds["seasons"].append({
            "key": str(y),
            "label": f"{y}" + (f" (partial — {cov*100:.0f}% of the league)" if partial else ""),
            "order": y, "played": True, "cov": round(cov, 3),
            **({"partial": 1} if partial else {}),
        })
        ds["players"].extend(rows_by_year[y])
    ds["seasons"].sort(key=lambda s: -s["order"])

    json.dump(ds, open(DS, "w"), separators=(",", ":"))
    n = sum(len(rows_by_year[y]) for y, _ in kept)
    print(f"ndl history: {len(kept)} archived seasons added, {n} player-rows")
    for y, cov in kept:
        print(f"  {y}  {len(rows_by_year[y]):>3} players  {cov*100:>3.0f}%"
              f"{'  (partial — no leader highlighting)' if cov < FULL_COV else ''}")
    if dropped:
        thin = ", ".join(f"{y} {cov*100:.0f}%" for y, cov in dropped)
        print(f"  too thin to publish ({int(MIN_COV*100)}% floor): {thin}")
    print(f"wrote {DS} ({os.path.getsize(DS):,} bytes)")


if __name__ == "__main__":
    main()
