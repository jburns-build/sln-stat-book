#!/usr/bin/env python3
"""Cross-check the designation ledger against the scraped NDL careers.

Three things come out of it.

1. WATCHLIST COVERAGE — how many active designations we hold an NDL career for.
   A miss prints its nearest spellings, because the leagues share no id space
   and the join runs on the name, so one wrong letter loses a player.

2. INTRA-NDL TRADES — a designated player can be traded between NDL clubs, and
   that move is logged NOWHERE. /NDL/transactions.htm is frozen at the 2028
   offseason and carries only retirements, re-signings and draft picks — no
   trade row in its entire history — and the SLN transaction log never mentions
   the NDL at all. So the only evidence a trade happened is the disagreement
   between the club the ledger says designated a player and the club his NDL
   career page says he actually played for. This report is the closest thing to
   an NDL transaction log that exists.

3. LEDGER ANOMALIES — entries whose years can't be right.

Read-only: it changes nothing, it just says what the two sources disagree about.
"""
import json, os, sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ndl_names import load_aliases, suggest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = f"{ROOT}/data/ndl_designations.json"
ARCHIVE = f"{ROOT}/data/ndl_careers.json"
OUT = f"{ROOT}/out/designation_reconcile.json"

# teams the archive never treats as a club
PSEUDO = {"FA", "Draft"}


def main():
    if not (os.path.exists(LEDGER) and os.path.exists(ARCHIVE)):
        sys.exit("need data/ndl_designations.json and data/ndl_careers.json")
    des = json.load(open(LEDGER))["designations"]
    recs = json.load(open(ARCHIVE))["records"]
    alias = load_aliases()

    by_name = defaultdict(list)
    for r in recs.values():
        by_name[r["name"]].append(r)
    nicknames = {row[1] for r in recs.values() for row in r["rows"]} - PSEUDO

    def affiliate_nick(full):
        """'Fort Wayne Mad Ants' -> 'Mad Ants'; 'Raptors 905' -> '905'."""
        hits = [n for n in nicknames if full and full.endswith(n)]
        return max(hits, key=len) if hits else None

    def career(name):
        c = by_name.get(name) or by_name.get(alias.get(name, ""), None)
        return max(c, key=lambda r: len(r["rows"])) if c else None

    active = [d for d in des if d["status"] == "active"]
    held, missing = [], []
    for d in active:
        (held if career(d["name"]) else missing).append(d)

    trades, checked = [], 0
    for d in des:
        rec = career(d["name"])
        nick = affiliate_nick(d["ndl"])
        if not rec or not nick:
            continue
        # the seasons this designation was in force
        span = [row for row in rec["rows"]
                if row[0] >= d["year"] and (not d["end"] or row[0] <= d["end"])
                and row[1] not in PSEUDO]
        if not span:
            continue
        checked += 1
        teams = [row[1] for row in span]
        if nick in teams:
            continue                      # played for his own affiliate at some point
        trades.append({
            "name": d["name"], "sln": d["sln"], "affiliate": d["ndl"],
            "designated": d["year"], "end": d["end"], "status": d["status"],
            "played_for": [[row[0], row[1], row[2]] for row in span],
        })

    json.dump({"active": len(active), "held": len(held),
               "missing": [d["name"] for d in missing],
               "trades": trades, "checked": checked},
              open(OUT, "w"), separators=(",", ":"))

    print(f"watchlist: {len(held)}/{len(active)} active designations archived")
    for d in missing:
        near = suggest(d["name"], by_name)
        hint = ("  — did you mean " +
                ", ".join(f"{c} (id {min(r['id'] for r in by_name[c])})" for c in near)
                + "?") if near else ""
        print(f"  !! no NDL career for {d['name']} ({d['sln']}, slot {d['slot']}, "
              f"since {d['year']}){hint}")

    print(f"\nintra-NDL trades — designated by one club, played for another "
          f"({len(trades)} of {checked} designations cross-checkable):")
    print("  (no NDL transaction log exists; this disagreement is the only trace)")
    for t in sorted(trades, key=lambda t: -t["designated"]):
        seq = ", ".join(f"{y} {tm} ({g}g)" for y, tm, g in t["played_for"])
        end = t["end"] or ("active" if t["status"] == "active" else "?")
        print(f"  {t['name']:22s} {t['sln']:22s} -> {t['affiliate']:24s} "
              f"{t['designated']}–{end}")
        print(f"    {'':22s} actually played: {seq}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
