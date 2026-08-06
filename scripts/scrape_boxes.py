#!/usr/bin/env python3
"""Aggregate per-player REGULAR-SEASON totals from the per-game box scores.

Why: the league publishes rebounds/assists/steals/blocks/turnovers only as
per-game averages rounded to 0.1, so career sums derived from them carry ±0.05×G
error per season (enough to scramble close leaderboard orderings). The box
scores carry exact per-game lines — including minutes and personal fouls,
published nowhere else. Summing them gives EXACT season and career totals.

Coverage: boxes exist for 1999 + 2001–2037 + current. 1996 has no archive at
all; 1997, 2000 and 2005 have day scoreboards but no per-game box files (same
gap as the All-Star boxes). Careers spanning those years stay hybrid.

Layout: /history/{code}/leagueschedule.htm links ./boxes/day{D}.htm for every
REGULAR-SEASON day (playoff days live in the same boxes/ dir but are not on the
league schedule — that's the boundary). Each day page links {D}-{G}.html per
game; each box has two team tables: rows of [player link, POS, MIN, FG, FGA,
3P, 3PA, FT, FTA, REB, A, PF, ST, TO, BL, PTS].

Output: data/box_agg.json
  {"seasons": {code: {"players": {pid: [g,min,reb,ast,stl,blk,to,pf]},
               "days_done": D, "games": N, "complete": bool}}}
Historical seasons are final once complete (never refetched). The live season
resumes from its day cursor; a day is merged only after every one of its boxes
parsed, so a crash can't double-count.
"""
import json, os, re, sys, time, urllib.request, urllib.error

UA = {"User-Agent": "Mozilla/5.0 (research audit; polite)"}
B = "https://www.simleaguenirvana.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{ROOT}/data/box_agg.json"
SLEEP = 0.35
# box-era seasons, newest first so the modern leaderboards firm up earliest;
# "current" leads because it's small and keeps the live season fresh
SEASONS = ["current"] + [f"{n:02d}" for n in range(38, 0, -1) if n not in (5,)] + ["99"]
ONLY = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")]
if ONLY:
    SEASONS = [s for s in SEASONS if s in ONLY[0].split(",")]
BUDGET = float(os.environ.get("BOXES_BUDGET_SECONDS", "0"))
START = time.monotonic()


def fetch(url, attempts=3, timeout=25):
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


def base(code):
    return B if code == "current" else f"{B}/history/{code}"


def sched_days(code):
    """Regular-season day numbers, from the league schedule's box links."""
    h = fetch(f"{base(code)}/leagueschedule.htm")
    if not h:
        return None
    return sorted({int(m) for m in re.findall(r"boxes/day(\d+)\.htm", h)})


# Player names in the boxes are UNLINKED plain text (same as the All-Star
# boxes), so records key on (name, team-nickname); the join back to player ids
# happens against the roster dataset by (season, name) — only 5 (season, name)
# pairs in 42 seasons are ambiguous, and those fall back to derived totals.
# A stat line after filtering spacer cells:
#   Name POS MIN FG FGA 3P 3PA FT FTA REB A PF ST TO BL PTS
IX = {"min": 1, "reb": 8, "ast": 9, "pf": 10, "stl": 11, "tov": 12, "blk": 13}


def parse_box(html, agg):
    """Add one game's lines into agg[name][team] = [g,min,reb,ast,stl,blk,to,pf]."""
    cells = [re.sub("<[^>]+>", "", c).replace("&nbsp;", " ").strip()
             for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", html, re.I | re.S)]
    cells = [c for c in cells if c]
    n, i, team = 0, 0, ""
    while i < len(cells):
        # team stat-table header: Nickname, POS, MIN, ...
        if i + 2 < len(cells) and cells[i + 1] == "POS" and cells[i + 2] == "MIN":
            team = cells[i]
            i += 3
            continue
        # player record: Name + POS + 14 ints (Totals/DNP rows fail the guards)
        if (i + 15 < len(cells) and re.fullmatch(r"[A-Z]{1,2}", cells[i + 1])
                and all(re.fullmatch(r"-?\d+", v) for v in cells[i + 2:i + 16])):
            vals = cells[i + 1:i + 16]
            if int(vals[IX["min"]]) > 0:              # played
                a = agg.setdefault(cells[i], {}).setdefault(team, [0] * 8)
                a[0] += 1; a[1] += int(vals[IX["min"]])
                a[2] += int(vals[IX["reb"]]); a[3] += int(vals[IX["ast"]])
                a[4] += int(vals[IX["stl"]]); a[5] += int(vals[IX["blk"]])
                a[6] += int(vals[IX["tov"]]); a[7] += int(vals[IX["pf"]])
            n += 1
            i += 16
            continue
        i += 1
    return n


def main():
    data = json.load(open(OUT)) if os.path.exists(OUT) else {"seasons": {}}
    fetches = 0
    for code in SEASONS:
        s = data["seasons"].setdefault(code, {"players": {}, "days_done": 0,
                                              "games": 0, "complete": False})
        if s["complete"] and code != "current":
            continue
        days = sched_days(code); time.sleep(SLEEP)
        if days is None:
            print(f"s{code}: no league schedule — skipped"); continue
        todo = [d for d in days if d > s["days_done"]]
        if not todo:
            print(f"s{code}: up to date (day {s['days_done']}, {s['games']} games)")
            continue
        print(f"s{code}: {len(todo)} days to fetch (through day {days[-1]})", flush=True)
        failed = []
        for d in todo:
            if BUDGET and (time.monotonic() - START) > BUDGET:
                print(f"  budget hit — stopping at s{code} day {s['days_done']}")
                json.dump(data, open(OUT, "w"), separators=(",", ":"))
                return
            h = fetch(f"{base(code)}/boxes/day{d}.htm"); time.sleep(SLEEP); fetches += 1
            if h is None:
                # day page missing: final for history (odd), not-yet-played for live
                if code == "current":
                    break
                continue
            links = re.findall(rf"href=\"({d}-\d+\.html)\"", h)
            if not links:
                if code == "current":
                    break                              # unplayed day — revisit next run
                s["days_done"] = d                     # historical 0-game day is final
                continue
            day_agg = {}
            lost = []
            for g in links:
                bh = fetch(f"{base(code)}/boxes/{g}"); time.sleep(SLEEP); fetches += 1
                if bh is None or parse_box(bh, day_agg) == 0:
                    if code == "current":
                        lost = None                    # not final yet — retry next run
                        break
                    lost.append(g)                     # upstream hole — salvage the rest
            if lost is None:
                break
            if lost:
                print(f"  !! s{code} day {d}: lost {lost} (missing upstream) — salvaged {len(links)-len(lost)} games")
                s.setdefault("lost", []).extend(lost)
            for name, teams in day_agg.items():        # merge only after a clean day
                for tm, a in teams.items():
                    t = s["players"].setdefault(name, {}).setdefault(tm, [0] * 8)
                    for j in range(8):
                        t[j] += a[j]
            s["days_done"] = d
            s["games"] += len(links) - len(lost)
            if d % 20 == 0:
                json.dump(data, open(OUT, "w"), separators=(",", ":"))
                print(f"  s{code} day {d}: {s['games']} games, "
                      f"{len(s['players'])} players ({fetches} fetches)", flush=True)
        # second chance for days that failed mid-run (never merged, so safe)
        for d in list(failed):
            h = fetch(f"{base(code)}/boxes/day{d}.htm"); time.sleep(SLEEP); fetches += 1
            links = re.findall(rf"href=\"({d}-\d+\.html)\"", h) if h else []
            day_agg, ok = {}, bool(links)
            for g in links:
                bh = fetch(f"{base(code)}/boxes/{g}"); time.sleep(SLEEP); fetches += 1
                if bh is None or parse_box(bh, day_agg) == 0:
                    ok = False
                    break
            if ok:
                for name, teams in day_agg.items():
                    for tm, a in teams.items():
                        t = s["players"].setdefault(name, {}).setdefault(tm, [0] * 8)
                        for j in range(8):
                            t[j] += a[j]
                s["games"] += len(links)
                failed.remove(d)
                print(f"  s{code} day {d}: recovered on retry")
        if failed:
            print(f"  !! s{code}: days {failed} STILL missing — season left incomplete")
        if code != "current" and s["days_done"] >= days[-1] and not failed:
            s["complete"] = True
        json.dump(data, open(OUT, "w"), separators=(",", ":"))
        print(f"s{code} done: {s['games']} games, {len(s['players'])} players, "
              f"complete={s['complete']}", flush=True)
    done = sum(1 for v in data["seasons"].values() if v["complete"])
    print(f"TOTAL: {fetches} fetches this run; {done} seasons complete")


if __name__ == "__main__":
    main()
