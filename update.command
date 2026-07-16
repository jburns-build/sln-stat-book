#!/bin/zsh
# One-click refresh of the SLN Stat Book.
# Re-pulls the live season (and any newly-finished seasons), rebuilds the
# dataset, regenerates the webpage, and refreshes the shareable copy.
# On a Mac you can double-click this file in Finder to run it.
cd "${0:A:h}" || exit 1

echo "1/6  Refreshing SLN rosters (live season always re-fetched)…"
python3 scripts/scrape_rosters_gap.py   || exit 1
echo "2/6  Refreshing award pages…"
python3 scripts/scrape_awards.py        || exit 1
echo "3/6  Refreshing playoff/champion pages…"
python3 scripts/scrape_playoffs.py      || exit 1
echo "4/6  Refreshing NDL (developmental league)…"
python3 scripts/scrape_ndl.py           || exit 1
echo "5/6  Rebuilding datasets…"
python3 scripts/build_players_dataset.py           || exit 1
python3 scripts/build_players_dataset.py --league ndl || exit 1
echo "6/6  Rebuilding webpages…"
python3 scripts/build_site.py             || exit 1
python3 scripts/build_site.py --league ndl || exit 1
cp out/sln_stats.html SLN_Stat_Book.html
cp out/ndl_stats.html NDL_Stat_Book.html

echo ""
echo "✅  Updated:  SLN_Stat_Book.html  +  NDL_Stat_Book.html"
