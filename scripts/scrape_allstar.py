#!/usr/bin/env python3
"""Scrape All-Star Game appearances from the per-season box scores.

Each played season has an All-Star box at /history/{code}/boxes/allstar.html
listing both rosters. We count an appearance per player-name per season.

Coverage note: the site archives All-Star boxes for 1999 and 2001-2037 only —
1996, 1997, 2000 and 2005 have no box (those games happened but weren't
archived), so a handful of players active then are slightly undercounted. The
box source is validated exact for the modern era (Luka 17/17, Kobe 6/6).

Output: out/allstar.json  ->  {"appearances": [[name, year], ...]}
"""
import os, re, sys, time, urllib.request, urllib.error

UA = {"User-Agent": "Mozilla/5.0 (research audit; polite)"}
B = "https://www.simleaguenirvana.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODES = ["96", "97", "99"] + [f"{i:02d}" for i in range(0, 38)]
PRE = {"96": 1996, "97": 1997, "99": 1999}


def yr(code):
    return PRE.get(code, 2000 + int(code))


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


def roster(html):
    """Player names in an All-Star box: a left-aligned name cell immediately
    followed by a position cell (PG/SG/SF/PF/C). Team/total rows have no pos."""
    return [m.group(1).strip() for m in re.finditer(
        r"<TD align=left><font size=2>([^<]+)</font></TD>\s*"
        r"<TD align=center><font size=2>(?:PG|SG|SF|PF|C)</font>", html)]


def main():
    appearances, seasons = [], 0
    for c in CODES:
        h = fetch(f"{B}/history/{c}/boxes/allstar.html")
        time.sleep(0.35)
        if not h:
            continue
        names = roster(h)
        if not names:
            continue
        seasons += 1
        y = yr(c)
        for n in names:
            appearances.append([n, y])
    os.makedirs(f"{ROOT}/out", exist_ok=True)
    import json
    json.dump({"appearances": appearances}, open(f"{ROOT}/out/allstar.json", "w"),
              separators=(",", ":"))
    print(f"all-star: {len(appearances)} appearances across {seasons} seasons")
    if seasons < 25:
        sys.exit(f"ERROR: only {seasons} all-star boxes parsed — refusing to continue.")


if __name__ == "__main__":
    main()
