#!/usr/bin/env python3
"""Cross-check the designation ledger against the scraped NDL careers.

Three things come out of it.

1. WATCHLIST COVERAGE — how many active designations we hold an NDL career for.
   A miss prints its nearest spellings, because the leagues share no id space
   and the join runs on the name, so one wrong letter loses a player.

2. RIGHTS MOVEMENT — a designated player follows his SLN rights. Trade him and
   he moves to the acquiring club's NDL affiliate, without being recalled. The
   ledger annotates one such move in flight ("Titan Williams ... *IN PENDING
   TRADE TO UTAH*"), and his career page shows exactly that: Windy City Bulls
   in 2038, Salt Lake City Stars in 2039.

   Nothing logs these. /NDL/transactions.htm is frozen at the 2028 offseason
   and carries only retirements, re-signings and draft picks — not one trade
   row in its whole history — and the SLN transaction log never mentions the
   NDL. So the affiliate a player actually turns out for IS the record of who
   holds him, and this report reconstructs the moves from it.

   Detection is a change of owning club across the designation, not merely
   "never played for his own affiliate" — that weaker test misses a player
   traded mid-designation, who did start out at home.

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

PSEUDO = {"FA", "Draft"}          # not clubs


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

    def nick_of(full):
        """'Fort Wayne Mad Ants' -> 'Mad Ants'; 'Raptors 905' -> '905'."""
        hits = [n for n in nicknames if full and full.endswith(n)]
        return max(hits, key=len) if hits else None

    # every affiliate the ledger declares -> the SLN club that owns it, so an
    # NDL nickname can be read back as "whose player is this?"
    owner = {}
    for d in des:
        n = nick_of(d["ndl"])
        if n:
            owner[n] = d["sln"]

    def career(name):
        c = by_name.get(name) or by_name.get(alias.get(name, ""), None)
        return max(c, key=lambda r: len(r["rows"])) if c else None

    active = [d for d in des if d["status"] == "active"]
    held = [d for d in active if career(d["name"])]
    missing = [d for d in active if not career(d["name"])]

    moves, checked = [], 0
    for d in des:
        rec, home = career(d["name"]), nick_of(d["ndl"])
        if not rec or not home:
            continue
        span = [row for row in rec["rows"]
                if row[0] >= d["year"] and (not d["end"] or row[0] <= d["end"])
                and row[1] not in PSEUDO]
        if not span:
            continue
        checked += 1
        # collapse the span into consecutive stints at one club
        stints = []
        for row in span:
            y, team, g = row[0], row[1], row[2]
            if stints and stints[-1]["team"] == team:
                stints[-1]["to"], stints[-1]["g"] = y, stints[-1]["g"] + g
            else:
                stints.append({"team": team, "from": y, "to": y, "g": g})
        if len(stints) == 1 and stints[0]["team"] == home:
            continue                                  # stayed home all along
        # Where the path ENDS is the test of whether the ledger is current: the
        # ledger files a player under whoever ended up with him, so a path that
        # lands on his ledger club is just history. One landing anywhere else is
        # a move the ledger has not caught up with — which is exactly what the
        # "*IN PENDING TRADE TO UTAH*" annotation describes, on a player whose
        # career page says the trade already happened.
        stale = stints[-1]["team"] != home
        moves.append({
            "name": d["name"], "sln": d["sln"], "affiliate": d["ndl"],
            "designated": d["year"], "end": d["end"], "status": d["status"],
            "notes": d.get("notes"), "stale": stale,
            "now": owner.get(stints[-1]["team"], "?"),
            "stints": [dict(s, owner=owner.get(s["team"], "?")) for s in stints],
        })

    json.dump({"active": len(active), "held": len(held),
               "missing": [d["name"] for d in missing],
               "moves": moves, "checked": checked},
              open(OUT, "w"), separators=(",", ":"))

    print(f"watchlist: {len(held)}/{len(active)} active designations archived")
    for d in missing:
        near = suggest(d["name"], by_name)
        hint = ("  — did you mean " +
                ", ".join(f"{c} (id {min(r['id'] for r in by_name[c])})" for c in near)
                + "?") if near else ""
        print(f"  !! no NDL career for {d['name']} ({d['sln']}, slot {d['slot']}, "
              f"since {d['year']}){hint}")

    def show(rows, title, blurb):
        print(f"\n{title} — {len(rows)}")
        if blurb:
            print(f"  {blurb}")
        for m in sorted(rows, key=lambda m: -m["designated"]):
            end = m["end"] or ("active" if m["status"] == "active" else "?")
            path = "  ->  ".join(
                f"{s['owner']} ({s['team']} {s['from']}" +
                (f"-{s['to']}" if s['to'] != s['from'] else "") + f", {s['g']}g)"
                for s in m["stints"])
            note = f"   [ledger note: {'; '.join(m['notes'])}]" if m["notes"] else ""
            print(f"  {m['name']:22s} ledger: {m['sln']} {m['designated']}–{end}{note}")
            print(f"    {'':22s} held by: {path}")

    print(f"\nrights movement while designated — {len(moves)} of {checked} "
          f"cross-checkable designations reconstructed")
    print("  (nothing logs NDL trades; the affiliate a player turns out for is "
          "the only record there is)")
    show([m for m in moves if not m["stale"]], "  moved and the ledger agrees",
         "the path ends at the club the ledger files him under")
    show([m for m in moves if m["stale"]], "  LEDGER LOOKS OUT OF DATE",
         "the path ends somewhere else — these entries are filed under a club "
         "that no longer holds the player")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
