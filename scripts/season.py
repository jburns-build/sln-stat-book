#!/usr/bin/env python3
"""One source of truth for season codes and which season is currently live.

The league rolls over every season: the in-progress season is archived under
/history/NN/ and a new one takes its place at the top level. The live year used
to be a `2039` literal repeated across six scripts, which meant a rollover
silently mislabelled every page and dataset — the new season's rosters filed
under the old season's year — until somebody noticed by eye.

So it is derived instead. The live season is the one after the newest season the
site has archived, which the mirror already tells us. Nothing here needs editing
at a rollover; scrape_rosters_gap.py picks up the newly-archived season and this
follows it.
"""
import os
import re
import glob

# The three earliest seasons use pre-2000 codes, per the site's own printed
# years: 96=1996, 97=1997, 99=1999. There is no 1998 season.
PRE_YEARS = {"96": 1996, "97": 1997, "99": 1999}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.join(ROOT, "mirror")


def year_of(code):
    """Season code -> calendar year. 'current' is not a code; see current_year()."""
    if code in PRE_YEARS:
        return PRE_YEARS[code]
    return 2000 + int(code)


def archived_codes(mirror=None):
    """Every archived season code mirrored on disk, oldest first."""
    m = mirror or MIRROR
    codes = [re.search(r"[/\\]s(\d\d)[/\\]", d).group(1)
             for d in glob.glob(os.path.join(m, "s[0-9][0-9]", "rosters"))]
    return sorted(set(codes), key=year_of)


def current_year(mirror=None):
    """The live, in-progress season's year: one past the newest archived season.

    Fails loudly rather than guessing. A missing mirror means the caller would
    otherwise stamp every row with a wrong year, which is far harder to spot
    later than a build that stops here.
    """
    codes = archived_codes(mirror)
    if not codes:
        raise SystemExit(
            "season.current_year: no archived seasons found under mirror/ — "
            "cannot derive the live season. Run scripts/scrape_rosters_gap.py first.")
    return year_of(codes[-1]) + 1


def code_of(year):
    """Calendar year -> season code. Inverse of year_of()."""
    for c, y in PRE_YEARS.items():
        if y == year:
            return c
    return "%02d" % (year - 2000)


CURRENT_YEAR = current_year()

if __name__ == "__main__":
    codes = archived_codes()
    print("archived seasons: %d (%s .. %s)" % (
        len(codes), year_of(codes[0]), year_of(codes[-1])))
    print("live season:      %d" % CURRENT_YEAR)
