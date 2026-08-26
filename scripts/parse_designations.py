#!/usr/bin/env python3
"""Parse the league's NDL designation ledgers into structured data.

The commissioner keeps the only record of NDL<->SLN movement that exists — the
site's own /NDL/transactions.htm is frozen at the 2028 offseason and no SLN
transaction mentions the NDL at all. Two files, grouped by SLN parent club and
its NDL affiliate:

  ndl_designations.txt          the historical ledger, 1997-2025
  ndl_designations_current.txt  the live sheet, 2022-2039, which also shows each
                                club's OPEN designation slots:

    1. Tamonte Dillard - 2037 (Pre-TC) / 0 Years Exp / 1st Designation
    2. Available
    Protected Player: Kennin Wade - 2038 (Pre-TC) / ...
    Corey Shields - 2037 (Pre-TC) / 0 Years Exp / 1st Designation / Recalled 2039 offseason

Six slots per club — four numbered, plus a protected and an unprotected place —
so at most 174 players are down at any moment. A line with no outcome is an
ACTIVE designation: that player is in the NDL right now, and his stats page is
the one worth capturing before his id gets recycled.

The ledgers carry three things no page publishes: designation timing (Pre-TC /
Pre-Season / Post-TC / Day N), years of experience at designation, and 1st vs
2nd designation.

Hand-maintained across 40 seasons, so the formatting wobbles — "Delegation" for
"Designation", missing parens, dashes for slashes, nicknames in quotes. The
parser absorbs those but REPORTS every line it cannot read rather than silently
dropping a player, and flags entries whose years don't make sense.
"""
import json, os, re, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = [("historical", f"{ROOT}/data/ndl_designations.txt"),
       ("current", f"{ROOT}/data/ndl_designations_current.txt")]
OUT = f"{ROOT}/data/ndl_designations.json"

ENTRY = re.compile(r"^(?P<name>.*?)[\s\-–]*(?P<year>(?:19|20)\d{2})\s*\(?(?P<when>[^)/]*)\)?\s*(?P<rest>.*)$")
EXP = re.compile(r"(?P<exp>\d+)\s+Years?\s+Exp", re.I)
EXP_LOOSE = re.compile(r"(?P<exp>\d+)\s+Years?\b", re.I)
DES = re.compile(r"(?P<n>\d+)\s*(?:st|nd|rd|th)\s+(?:Designation|Delegation)", re.I)
SLOT = re.compile(r"^(?:(?P<num>\d)\s*\.|(?P<kind>Un)?[Pp]rotected\s+Player)\s*:?\s*(?P<body>.*)$")

KINDS = [("recall", "recalled"), ("expired", "contract_expired"),
         ("waive", "waived"), ("bought out", "bought_out"),
         ("buyout", "bought_out"), ("cut", "cut")]


def classify(seg):
    """Outcome kind for one segment, or None if it is just an annotation."""
    low = seg.lower()
    for needle, kind in KINDS:
        if needle in low:
            return kind
    return None


def end_of(seg):
    yr = re.search(r"(?:19|20)\d{2}", seg)
    low = seg.lower()
    day = re.search(r"day\s*(\d+)", low)
    when = (f"Day {day.group(1)}" if day else
            "offseason" if ("offseason" in low or "off-season" in low or "offeason" in low)
            else "Pre-TC" if "pre-tc" in low
            else "season" if "season" in low else None)
    return (int(yr.group()) if yr else None), when


def main():
    rows, bad = [], []
    for source, path in SRC:
        if not os.path.exists(path):
            print(f"  (skipping missing {os.path.basename(path)})")
            continue
        division = sln = ndl = None
        pending = []
        for ln in open(path, encoding="utf-8").read().splitlines():
            s = ln.strip()
            if not s:
                pending = []
                continue
            if re.fullmatch(r"\w+ Division", s):
                division, pending = s.replace(" Division", ""), []
                continue

            # a numbered / protected slot line: strip the prefix, keep the slot
            slot = None
            sm = SLOT.match(s)
            if sm:
                slot = (sm.group("num") if sm.group("num") else
                        ("unprotected" if sm.group("kind") else "protected"))
                s = sm.group("body").strip()
                if not s or s.lower() == "available":
                    continue                      # an open slot, nothing to record

            m = ENTRY.match(s)
            des = DES.search(m.group("rest")) if m else None
            if not m or not des:
                if slot:                          # a slot line we could not read
                    bad.append((source, "slot without designation detail", s))
                    continue
                pending.append(s)                 # SLN parent, then NDL affiliate
                if len(pending) == 2:
                    sln, ndl = pending
                elif len(pending) > 2:
                    bad.append((source, "unrecognised line", s))
                continue

            rest = m.group("rest")
            e = EXP.search(rest) or EXP_LOOSE.search(rest)
            tail = [t.strip() for t in re.split(r"[/:]", rest[des.end():]) if t.strip()]
            # the outcome is the first segment that reads as one; anything else
            # is an annotation ("Sorry Kid", QO, a pending trade)
            outcome = next((t for t in tail if classify(t)), None)
            notes = [t for t in tail if t is not outcome]
            end, end_when = end_of(outcome) if outcome else (None, None)
            name = m.group("name").strip().strip("-").strip().rstrip(".")
            plain = " ".join(re.sub(r'"[^"]*"\s*', "", name).split())
            rows.append({
                "name": plain, "listed": name, "division": division,
                "sln": sln, "ndl": ndl, "slot": slot, "source": source,
                "year": int(m.group("year")), "when": m.group("when").strip() or None,
                "exp": int(e.group("exp")) if e else None,
                "designation": int(des.group("n")),
                "status": "ended" if outcome else "active",
                "outcome": classify(outcome) if outcome else None,
                "outcome_text": outcome, "end": end, "end_when": end_when,
                "notes": notes or None,
            })

    if not rows:
        sys.exit("ERROR: parsed nothing — check the source files")

    # the two ledgers overlap in the 2022-2025 window; one designation is one
    # (player, club, year, ordinal) regardless of which sheet it came from
    seen, merged = {}, []
    for r in rows:
        k = (r["name"], r["sln"], r["year"], r["designation"])
        prev = seen.get(k)
        if prev is None:
            seen[k] = r
            merged.append(r)
        elif prev["status"] == "active" and r["status"] == "ended":
            merged[merged.index(prev)] = r        # prefer the row that knows the end
            seen[k] = r

    json.dump({"designations": merged}, open(OUT, "w"),
              separators=(",", ":"), ensure_ascii=False)

    act = [r for r in merged if r["status"] == "active"]
    kinds = Counter(r["outcome"] for r in merged if r["outcome"])
    print(f"designations: {len(merged)} ({len(rows) - len(merged)} duplicate rows "
          f"merged across the two ledgers), "
          f"{len({r['name'] for r in merged})} distinct players, "
          f"{min(r['year'] for r in merged)}–{max(r['year'] for r in merged)}")
    print("  outcomes: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    print(f"  {sum(1 for r in merged if r['designation'] > 1)} second designations")
    print(f"  ACTIVE (in the NDL now): {len(act)} across "
          f"{len({r['sln'] for r in act})} clubs — this is the watchlist")
    for r in merged:
        if r["end"] and r["end"] < r["year"]:
            print(f"  ?? ends before it starts: {r['listed']} ({r['sln']}) "
                  f"{r['year']} → {r['outcome_text']}")
    for r in merged:
        if r["exp"] is None:
            print(f"  ?? no experience field: {r['listed']} {r['year']}")
    for source, why, s in bad:
        print(f"  !! [{source}] {why}: {s}")
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)")


if __name__ == "__main__":
    main()
