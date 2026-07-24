# Sim League Nirvana — Data Field Guide

Where every stat lives on `simleaguenirvana.com`, how each page is shaped, and the quirks that bite.
Compiled from the scrapers in `scripts/` and verified against the live site.

Browsable version: https://claude.ai/code/artifact/fcf8c7ba-934c-438d-8943-8ad658570c8e

| | |
|---|---|
| Base | `https://www.simleaguenirvana.com` |
| Leagues | SLN (root) · NDL (`/NDL/`) |
| Seasons | 42 (1996–2038) |
| Teams/season | ~29 |
| Encoding | latin-1 |

---

## 1. Scope

**Two leagues, same skeleton.** SLN lives at the site root; the developmental league **NDL** mirrors the exact
same page layout under a `/NDL/` prefix. The same parsers work on both.

**The frameset trap.** On-site navigation runs through JavaScript `<frameset>` pages (e.g. `index2.htm`), so the
browser URL bar *never changes* as you click around. Don't scrape by watching the address bar — fetch the
underlying files directly. The site's own one-leader-per-category `playercareerrecords.htm` is reachable *only*
through that frameset nav.

**NDL has no history.** NDL publishes the **current season only** — every `/NDL/history/…`, four-digit-year, or
`/archive/` path 404s. ~29 teams, ~350 players. Before a season tips off, games read 0-0 while age / contract /
ability data is already populated.

---

## 2. Season codes → calendar years

URLs key on a season *code*, not the year.

| Code | Year | Notes |
|---|---|---|
| `96` | 1996 | historical mirror |
| `97` | 1997 | historical mirror |
| `98` | — **none** | `/history/98/` 404s — the league skipped it |
| `99` | 1999 | historical mirror |
| `00`–`37` | 2000–2037 | `NN` = 2000 + `NN`; 2037 = last **completed** season |
| `current` | 2038 | in progress — top-level, no `/history/` prefix |

> **There is no 1998.** Count career continuity by *real-season ordinal* (96, 97, 99, 00, 01…), never by
> subtracting years, or every gap straddling 1998 is off by one.

---

## 3. URL map

`{rn}` = roster number · `{id}` = player id · `{code}` = season code.

| Resource | Current (2038) | Historical | Key |
|---|---|---|---|
| Team roster | `/rosters/roster{rn}.htm` | `/history/{code}/rosters/roster{rn}.htm` | season + rn |
| Roster schedule | `/rosters/roster{rn}sched.htm` | `/history/{code}/rosters/roster{rn}sched.htm` | per-day W/L |
| Player page | `/players/player{id}.htm` | `/history/{code}/players/player{id}.htm` | season + id |
| Player career stats | `/players/player{id}stats.htm` | `/history/{code}/players/player{id}stats.htm` | season + id |
| Season awards | `/regssnawards.htm` | `/history/{code}/regssnawards.htm` | season |
| Playoffs / champion | `/playoffs.htm` | `/history/{code}/playoffs.htm` | season + rn |
| All-Star box score | — | `/history/{code}/boxes/allstar.html` | by name |
| Transactions | `/transactions.htm` | `/history/{code}/transactions.htm` | season + day |

> **Current-page year skew.** Top-level `/regssnawards.htm` and `/playoffs.htm` show the *last completed*
> season (2037) until 2038 finishes. Always guard on the year the page prints.

---

## 4. Page anatomy

### Team roster — `roster{rn}.htm`
- Team name = `<title>` minus `" Roster"`.
- 9 tables on the page; the one you want literally contains the string **"Player Statistics"**.
- Columns: `ID, Name, Pos, Games, MPG, PPG, RPG, APG, SPG, BPG, TPG, FG%, FT%, 3P%`
- Percents are **proportion strings** (`.467`), not percentages.
- Also carries a **Player Abilities** table: `In/Out/Hn/Df/Reb/Pot`, letter grades A+…F.
- Player links point to *that season's* player pages — recycled ids never collide here.

### Player career stats — `player{id}stats.htm`
- Season-by-season with **raw makes/attempts** — the only place FG/FT/3P counts live.
- Columns: `Season, Team, Games, MPG, FG, FGA, FG%, FT, FTA, FT%, 3P, 3PA, 3P%, RPG, APG, SPG, BPG, TOPG`
- Per-season rows begin with a 4-digit year; a final **`Career:`** row holds official per-game averages.
- **Points are not published** → compute `2*FG + 3P + FT` (exact).
- Reb/Ast/Stl/Blk/TO only as per-game → sum `PG * Games` (≈0.1% rounding).

### Player page — `player{id}.htm`
- `<title>` = `"POS Name - Team"` (e.g. `"SF LeBron James - Pistons"`).
- `<textarea name="Awards">`: every honor as `"YYYY - Award"` lines (includes
  `"All-Star Game Participant"`; exclude `"Rookie Game"`).
- Achievements box: **Double Doubles**, **Triple Doubles**, **Championships**, Player of the Game.
- Embeds the `player{id}stats.htm` iframe.

### Season awards — `regssnawards.htm`
- One consolidated page per season, ~39 slots.
- MVP · DPOY · ROY · 6th Man · All-League 1st/2nd/3rd · All-Defensive 1st/2nd · All-Rookie 1st/2nd.
- Names are **linked with ids** → join cleanly by `(season, id)`.
- The page prints its own year (`"1999 Regular Season Awards"`) — trust that over the URL.

### Playoffs — `playoffs.htm`
- The champion's roster link sits **immediately after the word "Champion"**.
- Join by `(season, roster#)`. 41 champions on record (2038 in progress).

### All-Star box score — `boxes/allstar.html`
- Player names are **unlinked** → count by name, not id.
- Archived for **1999 + 2001–2037** only.
- **Gap:** 1996, 1997, 2000, 2005 boxes are missing — those games happened (see player award boxes) but
  aren't archived.

### Transactions — `transactions.htm`
- Flat 4-column table: `Season, Day, Team, Action`; rows alternate bgcolor.
- Each trade appears **twice** (once per team's perspective) → dedup by `(day, teams, assets)`.
- Format: `Trade {out} to the {counterparty} for {in}`; acting team = the Team column.
- Assets split on `", "` and `" and "`; picks parse from `"one/N draft pick(s)"`.
- **In-season = day ≤ 122.** Regular-season trades cluster days 1–100; offseason resumes ~day 170.

---

## 5. Conventions & the quirks that bite

### Player identity is not the id
**Ids are recycled across eras** (id `609` was Malik Sealy early, Brandon Roy later). An id is not a career key.
To reconstruct a career, group a *name's* ids and split into careers on **year-continuity**: a run of
**≥3 consecutive real seasons missing** starts a new person. This keeps a mid-career id change as one player
while separating two different people who share a name.

### ⚠ Career-page resets — the big one
A player's `…stats.htm` page normally holds their whole career, but the sim sometimes **resets it to a fresh
window mid-career — even under the same id** (an un-retirement). The last-season snapshot then shows only the
latest window, silently dropping earlier ones.

**LeBron James** was the sole site-wide case: id 608 (2003–19) → id 3, whose page was *itself* reset from a
2020–25 window to a blank 2026–29 one. Reading only the final page undercounted him by **434 G / 10,056 pts**.

**Fix:** walk back through earlier-season snapshots of the same id and sum the non-overlapping windows.
Implemented in `scripts/scrape_careers.py` (`unit()`).

### Exact vs approximate
- **Exact:** Games · Points (`2*FG+3P+FT`) · FG · FT · 3P · Double/Triple Doubles
- **≈ derived (~0.1%):** Rebounds · Assists · Steals · Blocks · Turnovers (published only as per-game averages,
  so summed as `PG * Games`)

### Other conventions
- **Mid-season trades:** a traded player's full-season stats are credited to their **end-of-season team**. The
  site never splits one season's line across teams.
- **Franchise = roster number.** `rn` is stable through renames — `rn3` is the Nets / "Brooklyn Ballers". Track
  franchise history by rn, not team name.
- **Ability grades:** In/Out/Hn/Df/Reb/Pot on an F…A+ scale, consistent across every era.
- **Flaky reachability:** the host occasionally refuses connections from cloud IPs though the site is up. Retry
  transient HTTP (429/5xx).

---

## 6. Query playbook

| You want… | Go to | How to read it |
|---|---|---|
| A player's line in one season | `roster{rn}.htm` | Player Statistics row, or the stats-page row for that year |
| A player's full career totals | `player{id}stats.htm` | Sum season rows; bundle ids by name-continuity; **check for page resets** (§5) |
| Who won an award in year Y | `/history/{Y}/regssnawards.htm` | Linked names → ids. Verify the printed year matches Y |
| A player's career award count | `player{id}.htm` | Award textarea, or sum per-season award pages across the career segment |
| Champion of year Y | `/history/{Y}/playoffs.htm` | Roster link right after "Champion" → (season, rn) |
| A team's roster in year Y | `/history/{Y}/rosters/roster{rn}.htm` | Player Statistics table |
| All-Star selections | `boxes/allstar.html` | Count unlinked names by year; mind the 1996/97/2000/2005 gap |
| Trades in a season | `/history/{Y}/transactions.htm` | Dedup double-listed rows; filter day ≤ 122 for in-season |
| Player abilities / grades | `roster{rn}.htm` | Player Abilities table, that season's snapshot |

---

*Counts stated as validated reflect ground-truth checks at time of writing (2026-07-23); a running season and
new un-retirements can shift them. Re-verify totals before quoting them.*
