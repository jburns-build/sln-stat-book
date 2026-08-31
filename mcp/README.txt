SLN STAT BOOK — Claude connector
================================

What this is
------------
A small program that lets Claude read your league data directly, instead of
re-scraping the league site and re-deriving numbers at the start of every
conversation. Ask "what did Luka do in 2037" and the answer comes back
instantly, from the files already on this Mac.

It is already switched on. Nothing to run, nothing to remember. Restart the
Claude app and it's there.


What Claude can now ask for
---------------------------
  sln_status           what data exists and how fresh it is
  sln_search_players   find a player by partial name
  sln_player           one player: every season, career totals, awards, grades
  sln_season           a season's leaderboard, filterable and sortable
  sln_standings        W-L by division, plus that season's champion
  sln_team             a team's roster and record for any season
  sln_career_leaders   all-time leaderboards
  sln_games            game results, team records, head-to-head
  sln_guide            the field guide to the league site
  sln_refresh          rebuild the local data files


Where the numbers come from
---------------------------
The same files the website is built from:

  out/players_dataset.json      43 seasons, ~16,800 player-seasons
  out/careers_dataset.json      2,465 careers
  out/season_shooting.json      raw shooting splits
  out/allstar.json              All-Star appearances
  data/box_agg.json             box-score-exact rebounds/assists/steals/etc
  data/games.json               every game result

Nothing new is scraped. Nothing is sent anywhere. It only reads.


Keeping it current
------------------
Finished seasons never change, so history here is always right. Only the
season in progress drifts. To freshen it, either double-click update.command
as usual, or just ask Claude to refresh — that's the sln_refresh tool.


If it ever stops working
------------------------
Run this in Terminal to check the data end:

  python3 "/Users/jackburns/Desktop/NDL Master Stats/mcp/sln_mcp.py" --selftest

It prints a line per tool and a pass count. If that passes but Claude still
can't see it, the connection is the problem, not the data — the setting lives
under "mcpServers" in ~/.claude.json.

Moving the "NDL Master Stats" folder will break the link, because the path is
written into that setting. Everything else is safe to move around.
