#!/usr/bin/env python3
"""Parse the 'Player Statistics' table from every mirrored roster page and
emit a single JSON dataset for the stats website.

Usage: build_players_dataset.py [--league sln|ndl]   (default: sln)

Output: out/players_dataset.json  (sln)  /  out/ndl_players_dataset.json  (ndl)
  {
    "seasons": [{"key":"current","label":"S38 (current)","order":38}, {"key":"37","label":"S37",...}, ...],
    "teams_by_season": {...},          # optional convenience
    "players": [ {season, team, id, name, pos, g, mpg, ppg, rpg, apg, spg, bpg, tpg, fgp, ftp, tpp}, ... ]
  }
"""
import os, re, json, glob, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The NDL (developmental league) mirrors the SLN page layout exactly, just under
# /NDL/ — same parsers. It has no published history, so it's current-season only.
LEAGUES = {
    "sln": {"mirror": "mirror",     "history": True,  "out": "players_dataset.json"},
    "ndl": {"mirror": "mirror/ndl", "history": False, "out": "ndl_players_dataset.json"},
}
LEAGUE = "ndl" if "--league" in sys.argv and sys.argv[sys.argv.index("--league") + 1] == "ndl" else "sln"
CFG = LEAGUES[LEAGUE]
MIRROR = f"{ROOT}/{CFG['mirror']}"
STAT_COLS =["id", "name", "pos", "g", "mpg", "ppg", "rpg", "apg",
             "spg", "bpg", "tpg", "fgp", "ftp", "tpp"]


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").strip()


def team_name(html):
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    if m:
        return re.sub(r"\s+Roster\s*$", "", strip_tags(m.group(1))).strip()
    return None


def row_cells(r):
    return [strip_tags(c) for c in
            re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.I | re.S)]


def parse_player_stats(html):
    """Return list of dicts from the Player Statistics table."""
    tables = re.findall(r"<table.*?</table>", html, re.I | re.S)
    for t in tables:
        if "Player Statistics" not in t:
            continue
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.I | re.S)
        out = []
        for r in rows:
            cells = row_cells(r)
            # a data row: first cell is a numeric player id, and it has 14 cells
            if len(cells) < 14:
                continue
            if not re.fullmatch(r"\d+", cells[0]):
                continue
            rec = dict(zip(STAT_COLS, cells[:14]))
            out.append(rec)
        return out
    return []


def money(v):
    """'$2,507,369' -> 2507369 ; '$0'/'' -> 0."""
    n = re.sub(r"[^0-9]", "", v or "")
    return int(n) if n else 0


def parse_salaries(html):
    """id -> {'age':int|None, 'sal1':int|None, 'yrs':int}. From Player Salaries table."""
    out = {}
    for t in re.findall(r"<table.*?</table>", html, re.I | re.S):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.I | re.S)
        htxt = " ".join(" ".join(row_cells(rr)) for rr in rows[:2])
        if "Year 1" not in htxt or "Total" not in htxt:
            continue
        for r in rows:
            c = row_cells(r)
            if len(c) < 12 or not re.fullmatch(r"\d+", c[0]):
                continue
            pid = int(c[0])
            age = int(c[3]) if re.fullmatch(r"\d+", c[3]) else None
            years = [money(x) for x in c[4:11]]        # Year 1..Year 7
            sal1 = years[0]
            out[pid] = {"age": age,
                        "sal1": sal1 if sal1 else None,
                        "yrs": sum(1 for y in years if y > 0)}
        break
    return out


# Player Abilities table: ID, Name, Pos, Age, Height, Weight, In, Out, Hn, Df, Reb, Pot
ABIL_KEYS = ["In", "Out", "Hn", "Df", "Reb", "Pot"]


def parse_abilities(html):
    """id -> {'age':int|None, 'abil':{In,Out,Hn,Df,Reb,Pot letter grades}}."""
    out = {}
    for t in re.findall(r"<table.*?</table>", html, re.I | re.S):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.I | re.S)
        htxt = " ".join(" ".join(row_cells(rr)) for rr in rows[:2])
        if "Reb" not in htxt or "Pot" not in htxt or "Age" not in htxt:
            continue
        for r in rows:
            c = row_cells(r)
            if len(c) < 12 or not re.fullmatch(r"\d+", c[0]):
                continue
            age = int(c[3]) if re.fullmatch(r"\d+", c[3]) else None
            abil = {k: c[6 + i] for i, k in enumerate(ABIL_KEYS)}
            out[int(c[0])] = {"age": age, "abil": abil}
        break
    return out


def parse_record(html):
    """(wins, losses) for the team, from the roster page's 'Current Record'
    table (the row right below the W / L headers). None if not found."""
    for t in re.findall(r"<table.*?</table>", html, re.I | re.S):
        if "Current Record" not in t:
            continue
        rows = [[c for c in row_cells(r) if c]
                for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.I | re.S)]
        for i, c in enumerate(rows):
            if len(c) >= 2 and c[0] == "W" and c[1] == "L" and i + 1 < len(rows):
                nxt = rows[i + 1]
                if (len(nxt) >= 2 and re.fullmatch(r"\d+", nxt[0])
                        and re.fullmatch(r"\d+", nxt[1])):
                    return int(nxt[0]), int(nxt[1])
        break
    return None


def parse_champion(path):
    """Return the champion team's roster number for a season, or None.
    The bracket puts the winning team's roster link right after 'Champion'."""
    if not os.path.exists(path):
        return None
    h = open(path, encoding="latin-1").read()
    i = h.find("Champion")
    if i < 0:
        return None
    m = re.search(r"roster(\d+)\.htm", h[i:i + 600], re.I)
    return int(m.group(1)) if m else None


def num(v):
    v = (v or "").strip()
    if v in ("", "-", "--"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


AWARD_LABELS = {
    "Most Valuable Player": "MVP",
    "Defensive Player Of The Year": "DPOY",
    "Rookie Of The Year": "ROY",
    "Sixth Man Of The Year": "6th Man",
    "All League First Team": "All-League 1st",
    "All League Second Team": "All-League 2nd",
    "All League Third Team": "All-League 3rd",
    "All Defensive First Team": "All-Defensive 1st",
    "All Defensive Second Team": "All-Defensive 2nd",
    "All Rookie First Team": "All-Rookie 1st",
    "All Rookie Second Team": "All-Rookie 2nd",
}
_AWARD_RE = re.compile(
    r"(Most Valuable Player|Defensive Player Of The Year|Rookie Of The Year|"
    r"Sixth Man Of The Year|All League (?:First|Second|Third) Team|"
    r"All Defensive (?:First|Second) Team|All Rookie (?:First|Second) Team)"
    r"|player(\d+)\.htm")


def parse_awards(path, expect_year):
    """id -> [award names]. Only returns awards if the page's year matches
    expect_year (guards the current/top-level page which shows last season)."""
    if not os.path.exists(path):
        return {}
    h = open(path, encoding="latin-1").read()
    ym = re.search(r"(\d{4}) Regular Season Awards", h)
    if not ym or int(ym.group(1)) != expect_year:
        return {}
    awards, cur = {}, None
    for m in _AWARD_RE.finditer(h):
        if m.group(1):
            cur = AWARD_LABELS.get(m.group(1))
        elif cur:
            awards.setdefault(int(m.group(2)), []).append(cur)
    return awards


# League season code -> calendar year. Codes 00..37 are 2000+N. The three
# earliest seasons use pre-2000 codes (per the site's own printed years):
# 96=1996, 97=1997, 99=1999. There is no 1998 season (no season 98 or 98-data).
PRE_YEARS = {"96": 1996, "97": 1997, "99": 1999}


def year_of(code):
    if code == "current":
        return 2038
    if code in PRE_YEARS:
        return PRE_YEARS[code]
    return 2000 + int(code)


def season_dirs():
    """Yield (key, label, order, dir) for every season on disk, oldest first."""
    if CFG["history"]:
        dirs = []
        for d in glob.glob(f"{MIRROR}/s[0-9][0-9]/rosters"):
            code = re.search(r"/s(\d\d)/", d).group(1)
            dirs.append((code, d))
        dirs.sort(key=lambda x: year_of(x[0]))
        for code, d in dirs:
            yield (code, str(year_of(code)), year_of(code), d)
    cur = f"{MIRROR}/current/rosters"
    if os.path.isdir(cur):
        yield ("current", "2038 (in progress)", 2038, cur)


def main():
    players = []
    seasons = []
    champs = {}          # season key -> champion roster number
    records = {}         # season key -> {roster number: [wins, losses]}
    for key, label, order, d in season_dirs():
        seasons.append({"key": key, "label": label, "order": order})
        base = os.path.dirname(d)
        # season-wide awards, keyed by player id (guarded to this season's year)
        awards = parse_awards(os.path.join(base, "regssnawards.htm"), order)
        # championship (skip the current/unplayed season)
        if key != "current":
            cr = parse_champion(os.path.join(base, "playoffs.htm"))
            if cr is not None:
                champs[key] = cr
        for f in glob.glob(f"{d}/roster*.htm"):
            if re.search(r"roster\d+sched", f):
                continue
            rn = int(re.search(r"roster(\d+)\.htm", f).group(1))
            html = open(f, encoding="latin-1").read()
            team = team_name(html) or os.path.basename(f)
            rec = parse_record(html)
            if rec:
                records.setdefault(key, {})[str(rn)] = [rec[0], rec[1]]
            sal = parse_salaries(html)
            abils = parse_abilities(html)
            for rec in parse_player_stats(html):
                pid = int(rec["id"])
                s = sal.get(pid, {})
                ab = abils.get(pid, {})
                age = s.get("age")
                if age is None:
                    age = ab.get("age")
                players.append({
                    "season": key, "team": team, "rn": rn,
                    "id": pid,
                    "name": rec["name"], "pos": rec["pos"],
                    "age": age, "awards": awards.get(pid, []),
                    "abil": ab.get("abil"),
                    "sal1": s.get("sal1"), "yrs": s.get("yrs", 0),
                    "g": num(rec["g"]), "mpg": num(rec["mpg"]),
                    "ppg": num(rec["ppg"]), "rpg": num(rec["rpg"]),
                    "apg": num(rec["apg"]), "spg": num(rec["spg"]),
                    "bpg": num(rec["bpg"]), "tpg": num(rec["tpg"]),
                    "fgp": num(rec["fgp"]), "ftp": num(rec["ftp"]),
                    "tpp": num(rec["tpp"]),
                })
    # mark seasons that actually have played games (g>0 for anyone)
    played_keys = {p["season"] for p in players if p["g"]}
    for s in seasons:
        s["played"] = s["key"] in played_keys
    seasons.sort(key=lambda s: -s["order"])
    ds = {"seasons": seasons, "champs": champs, "records": records,
          "players": players}
    os.makedirs(f"{ROOT}/out", exist_ok=True)
    out_path = f"{ROOT}/out/{CFG['out']}"
    with open(out_path, "w") as fh:
        json.dump(ds, fh, separators=(",", ":"))
    # summary
    from collections import Counter
    by_season = Counter(p["season"] for p in players)
    print(f"[{LEAGUE}] seasons: {len(seasons)}  players(rows): {len(players)}")
    for s in seasons:
        print(f"  {s['label']:14} {by_season[s['key']]:>4} players")
    print(f"[{LEAGUE}] wrote {out_path} ({os.path.getsize(out_path):,} bytes)")


if __name__ == "__main__":
    main()
