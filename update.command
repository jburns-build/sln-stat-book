#!/bin/zsh
# One-click refresh of the SLN Stat Book.
# Re-pulls the live season (and any newly-finished seasons), rebuilds the
# dataset, regenerates the webpage, and refreshes the shareable copy.
# On a Mac you can double-click this file in Finder to run it.
cd "${0:A:h}" || exit 1

echo "1/5  Refreshing rosters (live season always re-fetched)…"
python3 scripts/scrape_rosters_gap.py   || exit 1
echo "2/5  Refreshing award pages…"
python3 scripts/scrape_awards.py        || exit 1
echo "3/5  Refreshing playoff/champion pages…"
python3 scripts/scrape_playoffs.py      || exit 1
echo "4/5  Rebuilding dataset…"
python3 scripts/build_players_dataset.py || exit 1
echo "5/5  Rebuilding webpage…"
python3 scripts/build_site.py           || exit 1
cp out/ndl_stats.html SLN_Stat_Book.html

echo ""
echo "✅  SLN Stat Book updated:  SLN_Stat_Book.html"
