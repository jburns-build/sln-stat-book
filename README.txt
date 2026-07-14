SLN STAT BOOK
=============

A sortable/filterable stat table for every player in the Sim League Nirvana
(NDL) sim basketball league, themed after slnassistantgm.com.

OPEN IT
-------
Double-click  SLN_Stat_Book.html  (a self-contained webpage — no internet or
server needed; all data is baked in). Same file also lives at out/ndl_stats.html.

WHAT'S IN THE TABLE
-------------------
42 years (1996, 1997, 1999, then 2000–2037, plus 2038 "in progress"). NOTE: the
league has no 1998 season — the site labels its early seasons 1996/1997/1999.
Per player:
  # · Player · Pos · Age · Team · Cap Hit · Yrs · G · MPG · PPG · RPG · APG ·
  SPG · BPG · TPG · FG% · FT% · 3P%
- Click any column header to sort.
- Filters: Year, Minutes (MPG), Team, Position, and a name search.
- Defaults to the newest fully-played year (2037).
- Player names link to their simleaguenirvana.com player page; team names link
  to that team's roster page (both scoped to the correct year).
- SEASON LEADERS are shaded per stat (top 1 / 3 / 5 / 10). TPG highlights the
  FEWEST turnovers among 20+ MPG players; FG/FT/3P leaders need 10+ MPG.
- 🏅 next to a name = individual awards that year (hover to see them).
- 🏆 next to a team = won the championship that year.

COMPARE A PLAYER ACROSS YEARS
-----------------------------
Search a player (or click the 📊 next to any name) to open their multi-year view:
  - toggle which years to include,
  - "Average" = games-weighted averages across the selected years,
  - "Compare 2" = side-by-side of two years with colored deltas,
  - plus each year's awards,
  - and an "Ability grades over time" table (In/Out/Hn/Df/Reb/Pot letter grades
    with ▲/▼ arrows showing how each rating changed year to year).
"← All players" (or the SLN logo) returns to the table.

REBUILD IT (e.g. once 2038 games start logging)
-----------------------------------------------
From this folder, run:
  python3 scripts/scrape_rosters_gap.py       # re-pull current + any new rosters
  python3 scripts/scrape_awards.py            # re-pull season award pages
  python3 scripts/scrape_playoffs.py          # re-pull season playoff pages (champions)
  python3 scripts/build_players_dataset.py    # rebuild out/players_dataset.json
  python3 scripts/build_site.py               # rebuild the webpage
Then copy out/ndl_stats.html back over SLN_Stat_Book.html to refresh the
top-level shareable copy.

FOLDER LAYOUT
-------------
  SLN_Stat_Book.html      the shareable webpage
  scripts/                the build/scrape scripts
  mirror/                 raw roster + award pages (source data), by year
  out/                    generated dataset (JSON) + webpage

Data mirrored from simleaguenirvana.com. Season code -> year: 96=1996, 97=1997,
99=1998 (no 98), then NN = 2000+NN; the live top-level pages are 2038.
