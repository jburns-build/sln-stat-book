#!/usr/bin/env python3
"""Build the regular-season GAME RESULTS dataset -> data/games.json.

Sources:
- 1999, 2001-2037, 38, current: the day scoreboard pages (boxes/day{D}.htm)
  linked from each season's leagueschedule.htm (regular season only — playoff
  days are off-schedule). Each game is a pair of line-score rows:
  [team label, q1..q4(,OT), TOTAL]. Labels are matched against that season's
  full team names first, then unique nicknames (2020 renamed every team
  "<City> Ballers", but day pages print the full names, so it resolves).
- 1996 (no boxes dir at all): every team's roster{rn}sched.htm. Cells read
  "Winner 93, LOSER 90" with ALL-CAPS = the home team; keeping only each
  team's HOME games yields every game exactly once.

Output: {"seasons": {code: {"games": [[rnA, sA, rnB, sB], ...], "complete": bool}}}
(rnA/rnB are roster numbers; conference mapping is East rn1-15, West rn16-29.)
Completed seasons never change; the live season resumes from its day cursor.
"""
import json, os, re, sys, time, urllib.request, urllib.error

UA = {"User-Agent": "Mozilla/5.0 (research audit; polite)"}
B = "https://www.simleaguenirvana.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{ROOT}/data/games.json"
SLEEP = 0.3
SEASONS = ["current", "38"] + [f"{n:02d}" for n in range(37, 0, -1)] + ["99", "97", "00", "05", "96"]
ONLY = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")]
if ONLY:
    SEASONS = [s for s in SEASONS if s in ONLY[0].split(",")]


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


def cells(chunk):
    return [x for x in (re.sub("<[^>]+>", "", y).replace("&nbsp;", " ").strip()
                        for y in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", chunk, re.I | re.S)) if x]


def team_maps(players, code):
    """full-name -> rn, and unique nickname -> rn, for one season."""
    full, nick = {}, {}
    seen = {}
    for p in players:
        if p["season"] != code:
            continue
        full[p["team"]] = p["rn"]
        n = "Trail Blazers" if p["team"].endswith("Trail Blazers") else p["team"].split()[-1]
        seen.setdefault(n, set()).add(p["rn"])
    for n, rns in seen.items():
        if len(rns) == 1:
            nick[n] = next(iter(rns))
    return full, nick


GLOBAL_NICK = {}    # nickname -> rn when globally unique across ALL seasons;
                    # fallback for upstream roster gaps (e.g. the missing
                    # s00 Kings page — rn28 by franchise continuity)


def resolve(label, full, nick):
    if label in full:
        return full[label]
    if label in nick:
        return nick[label]
    for f, rn in full.items():          # label may drop the city
        if f.endswith(" " + label):
            return rn
    return GLOBAL_NICK.get(label)


def day_games(html, full, nick):
    """Parse one day page into [(rnA, sA, rnB, sB), ...]."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S)
    lines = []
    for r in rows:
        c = cells(r)
        # a line-score row: team label + 4-7 ints, last = total
        if (len(c) >= 5 and not c[0].isdigit() and c[0] not in ("Team",)
                and all(re.fullmatch(r"\d+", x) for x in c[1:])):
            rn = resolve(c[0], full, nick)
            lines.append((rn, int(c[-1]), c[0]))
    resolved = [l for l in lines if l[0] is not None]
    if not resolved:
        return []                       # exhibition-only day (All-Star weekend)
    if len(resolved) != len(lines) or len(resolved) % 2:
        return None                     # mixed/odd — parse trouble, fail loudly
    out = []
    for i in range(0, len(resolved), 2):
        (ra, sa, la), (rb, sb, lb) = resolved[i], resolved[i + 1]
        out.append((ra, sa, rb, sb))
    return out


def season_from_days(code, s, full, nick):
    days = None
    h = fetch(f"{base(code)}/leagueschedule.htm"); time.sleep(SLEEP)
    if h:
        days = sorted({int(m) for m in re.findall(r"boxes/day(\d+)\.htm", h)})
    if not days:
        print(f"s{code}: no schedule day list — skipped")
        return 0
    fetched = 0
    for d in [x for x in days if x > s["day"]]:
        h = fetch(f"{base(code)}/boxes/day{d}.htm"); time.sleep(SLEEP); fetched += 1
        if h is None:
            if code == "current":
                break
            print(f"  !! s{code} day {d}: page fetch failed — season left incomplete")
            return fetched
        g = day_games(h, full, nick)
        if g is None:
            print(f"  !! s{code} day {d}: unparseable — season left incomplete")
            return fetched
        if not g:
            if code == "current":
                break                   # unplayed day
            s["day"] = d
            continue
        s["games"].extend(g)
        s["day"] = d
    if code != "current" and s["day"] >= days[-1]:
        s["complete"] = True
    return fetched


def season_from_scheds(code, s, players):
    """1996: home games from every team's schedule page."""
    _, nick = team_maps(players, code)
    own_rns = sorted({p["rn"] for p in players if p["season"] == code})
    inv = {rn: n for n, rn in nick.items()}
    lower = {n.lower(): rn for n, rn in nick.items()}       # case-insensitive
    fetched = 0
    missed = 0
    for rn in own_rns:
        h = fetch(f"{base(code)}/rosters/roster{rn}sched.htm"); time.sleep(SLEEP); fetched += 1
        if h is None:
            print(f"  !! s{code} roster{rn}sched fetch failed — season left incomplete")
            return fetched
        me = inv[rn].lower()
        # parse row-wise so each result keeps its DAY number; the same table
        # continues into the playoffs, and in-season = day <= 122
        pairs = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.I | re.S):
            c = cells(row)
            for j in range(0, len(c) - 1):
                if re.fullmatch(r"\d+", c[j]) and int(c[j]) <= 122 and "," in c[j + 1]:
                    m = re.fullmatch(
                        r"\s*([A-Za-z0-9 .'\-]+?)\s+(\d+),\s*([A-Za-z0-9 .'\-]+?)\s+(\d+)\s*",
                        c[j + 1])
                    if m:
                        pairs.append(m.groups())
        for a_name, a_sc, b_name, b_sc in pairs:
            # home team is rendered ALL-CAPS; keep only this page-owner's HOME
            # games so every game is counted exactly once league-wide
            a_home = a_name.isupper() and not b_name.isupper()
            b_home = b_name.isupper() and not a_name.isupper()
            if not (a_home or b_home):
                missed += 1
                continue
            hn, hs = (a_name, int(a_sc)) if a_home else (b_name, int(b_sc))
            an, aws = (b_name, int(b_sc)) if a_home else (a_name, int(a_sc))
            if hn.lower() != me:
                continue                                    # someone else's home game
            arn = lower.get(an.lower())
            if arn is None:
                missed += 1
                continue
            s["games"].append((arn, aws, rn, hs))
    if missed:
        print(f"  !! s{code}: {missed} sched cells unresolved")
    s["complete"] = True
    return fetched


def main():
    players = json.load(open(f"{ROOT}/out/players_dataset.json"))["players"]
    seen = {}
    for p in players:
        n = "Trail Blazers" if p["team"].endswith("Trail Blazers") else p["team"].split()[-1]
        seen.setdefault(n, set()).add(p["rn"])
    GLOBAL_NICK.update({n: next(iter(r)) for n, r in seen.items() if len(r) == 1})
    data = json.load(open(OUT)) if os.path.exists(OUT) else {"seasons": {}}
    total = 0
    for code in SEASONS:
        s = data["seasons"].setdefault(code, {"games": [], "day": 0, "complete": False})
        if s["complete"] and code != "current":
            continue
        full, nick = team_maps(players, code)
        if not full:
            print(f"s{code}: no roster data — skipped")
            continue
        n0 = len(s["games"])
        if code == "96":
            total += season_from_scheds(code, s, players)
        else:
            total += season_from_days(code, s, full, nick)
        json.dump(data, open(OUT, "w"), separators=(",", ":"))
        print(f"s{code}: +{len(s['games']) - n0} games (total {len(s['games'])}), "
              f"complete={s['complete']}", flush=True)
    done = sum(1 for v in data["seasons"].values() if v["complete"])
    print(f"DONE: {total} fetches; {done} seasons complete; "
          f"{sum(len(v['games']) for v in data['seasons'].values()):,} games")


if __name__ == "__main__":
    main()
