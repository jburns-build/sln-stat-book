#!/usr/bin/env python3
"""Parse the league's NDL designation ledger into structured data.

data/ndl_designations.txt is the commissioner's own record of every player ever
sent down to the NDL — grouped by SLN parent club and its NDL affiliate, one
line per designation:

    Danny Green - 2009 (Pre-TC) / 0 Years Exp / 1st Designation / Recalled 2012 offseason

This is the ONLY record of NDL<->SLN movement that exists. The site's own
/NDL/transactions.htm is frozen at the 2028 offseason and no SLN transaction
mentions the NDL at all, so send-downs and recalls are otherwise invisible.
It also carries three things no page publishes: the designation timing
(Pre-TC / Pre-Season / Post-TC / Day N), years of experience at designation,
and whether this was a player's 1st or 2nd designation.

The source is hand-maintained across 30 seasons, so the formatting wobbles —
"Delegation" for "Designation", missing parens, dashes for slashes, nicknames
in quotes. The parser tolerates those but REPORTS every line it cannot read
rather than silently dropping a player. Anything it flags is a real ledger typo
worth fixing at the source.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = f"{ROOT}/data/ndl_designations.txt"
OUT = f"{ROOT}/data/ndl_designations.json"

# a designation line is anything carrying "<year> (" — names never contain one
ENTRY = re.compile(r"^(?P<name>.*?)[\s\-–]*(?P<year>(?:19|20)\d{2})\s*\(?(?P<when>[^)/]*)\)?\s*(?P<rest>.*)$")
EXP = re.compile(r"(?P<exp>\d+)\s+Years?\s+Exp", re.I)
EXP_LOOSE = re.compile(r"(?P<exp>\d+)\s+Years?\b", re.I)
DES = re.compile(r"(?P<n>\d+)\s*(?:st|nd|rd|th)\s+(?:Designation|Delegation)", re.I)


def classify(outcome):
    """Outcome text -> (kind, end year, end timing)."""
    o = " ".join(outcome.split())
    low = o.lower()
    yr = re.search(r"(?:19|20)\d{2}", o)
    end = int(yr.group()) if yr else None
    day = re.search(r"day\s*(\d+)", low)
    when = f"Day {day.group(1)}" if day else ("offseason" if "offseason" in low or "off-season" in low
                                              else ("Pre-TC" if "pre-tc" in low else None))
    if "recall" in low:
        kind = "recalled"
    elif "expired" in low:
        kind = "contract_expired"
    elif "waive" in low:
        kind = "waived"
    elif "bought out" in low or "buyout" in low:
        kind = "bought_out"
    elif "cut" in low:
        kind = "cut"
    else:
        kind = "other"
    return kind, end, when


def main():
    lines = open(SRC, encoding="utf-8").read().splitlines()
    rows, bad = [], []
    division = sln = ndl = None
    pending = []          # non-entry lines since the last blank -> team headers

    for ln in lines:
        s = ln.strip()
        if not s:
            pending = []
            continue
        if re.fullmatch(r"\w+ Division", s):
            division, pending = s.replace(" Division", ""), []
            continue

        m = ENTRY.match(s)
        des = DES.search(m.group("rest")) if m else None
        if not m or not des:
            # header lines arrive in pairs: SLN parent, then NDL affiliate
            pending.append(s)
            if len(pending) == 2:
                sln, ndl = pending
            elif len(pending) > 2:
                bad.append(("unrecognised line", s))
            continue

        rest = m.group("rest")
        e = EXP.search(rest) or EXP_LOOSE.search(rest)
        # everything after the designation token, minus empty segments
        tail = [t.strip() for t in rest[des.end():].split("/") if t.strip()]
        outcome = tail[-1] if tail else ""
        notes = tail[:-1]
        kind, end, when_end = classify(outcome)
        name = m.group("name").strip().strip("-").strip()
        # nicknames sit in quotes inside or before the name — keep both forms so
        # the join can match the site's plain spelling
        plain = re.sub(r'"[^"]*"\s*', "", name).strip()
        plain = " ".join(plain.split())
        rows.append({
            "name": plain, "listed": name, "division": division,
            "sln": sln, "ndl": ndl,
            "year": int(m.group("year")), "when": m.group("when").strip() or None,
            "exp": int(e.group("exp")) if e else None,
            "designation": int(des.group("n")),
            "outcome": kind, "outcome_text": outcome,
            "end": end, "end_when": when_end,
            "notes": notes or None,
        })

    if not rows:
        sys.exit("ERROR: parsed nothing — check the source file")

    json.dump({"designations": rows}, open(OUT, "w"),
              separators=(",", ":"), ensure_ascii=False)

    teams = {(r["sln"], r["ndl"]) for r in rows}
    from collections import Counter
    kinds = Counter(r["outcome"] for r in rows)
    second = sum(1 for r in rows if r["designation"] > 1)
    print(f"designations: {len(rows)} across {len(teams)} clubs, "
          f"{len({r['name'] for r in rows})} distinct players "
          f"({min(r['year'] for r in rows)}–{max(r['year'] for r in rows)})")
    print("  outcomes: " + ", ".join(f"{k} {v}" for k, v in kinds.most_common()))
    print(f"  {second} second designations")
    miss = [r for r in rows if r["exp"] is None]
    for r in miss:
        print(f"  ?? no experience field: {r['listed']} {r['year']}")
    for why, s in bad:
        print(f"  !! {why}: {s}")
    print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)")


if __name__ == "__main__":
    main()
