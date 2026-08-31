#!/usr/bin/env python3
"""SLN Stat Book MCP server.

Exposes the already-built SLN/NDL datasets to Claude as callable tools, so a
conversation never has to re-scrape or re-derive what this repo already knows.

Zero dependencies, stdlib only, Python 3.9+. Speaks MCP over stdio (JSON-RPC).
Reads the same files the site is built from:

  out/players_dataset.json    every season x ~17k player-season rows
  out/careers_dataset.json    ~2.5k career segments (bundled un-retirements)
  out/ndl_players_dataset.json  NDL current season
  out/season_shooting.json    per-season raw FG/FGA/FT/FTA/3P/3PA by player id
  out/allstar.json            All-Star appearances (name, year)
  out/fa.json                 current free agents
  data/box_agg.json           BOX-EXACT reb/ast/stl/blk/to/pf/min by season
  data/games.json             every regular-season game result

NOTHING here touches the network. Refresh is an explicit, separate tool.
Season numbers are never hardcoded — scripts/season.py derives the live year from
the mirror, so a league rollover needs no edit here.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTOCOL_FALLBACK = "2024-11-05"
KNOWN_PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18"}

# East = rn1-15, West = rn16-29.
DIVISIONS = [
    ("East", "Atlantic", range(1, 8)),
    ("East", "Central", range(8, 16)),
    ("West", "Midwest", range(16, 23)),
    ("West", "Pacific", range(23, 30)),
]
# box_agg row layout
BOX = {"g": 0, "min": 1, "reb": 2, "ast": 3, "stl": 4, "blk": 5, "tov": 6, "pf": 7}
# season_shooting row layout
SHOOT = {"g": 0, "fg": 1, "fga": 2, "ft": 3, "fta": 4, "tp": 5, "tpa": 6}

_cache = {}


def log(msg):
    """stderr only — stdout is the protocol channel and must stay clean."""
    sys.stderr.write("[sln-mcp] %s\n" % msg)
    sys.stderr.flush()


def load(rel):
    """Read a dataset, re-reading automatically if it changed on disk.

    The server is long-lived, so a rebuild underneath it must not leave stale
    numbers cached in memory. Keyed on mtime + size: cheap to check, and it
    catches a rebuild that lands within the same clock second.
    """
    path = os.path.join(ROOT, rel)
    st = os.stat(path)
    stamp = (st.st_mtime, st.st_size)
    hit = _cache.get(rel)
    if hit is None or hit[0] != stamp:
        with open(path, "r", encoding="utf-8") as fh:
            _cache[rel] = (stamp, json.load(fh))
    return _cache[rel][1]


def mtime(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return None
    return time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path)))


def dataset(league):
    return load("out/ndl_players_dataset.json" if league == "ndl" else "out/players_dataset.json")


# ---------------------------------------------------------------- seasons


def season_code(s, league="sln"):
    """Accept 2037, '2037', '37', 'current', 'latest' -> the dataset's season key."""
    d = dataset(league)
    keys = [x["key"] for x in d["seasons"]]
    if s is None or str(s).lower() in ("latest", "current", "now"):
        return d["seasons"][0]["key"]
    s = str(s).strip()
    if s in keys:
        return s
    if s.isdigit():
        n = int(s)
        if n >= 1996:  # a calendar year
            for x in d["seasons"]:
                if x["order"] == n:
                    return x["key"]
            return None
        code = "%02d" % n
        return code if code in keys else None
    return None


def season_label(code, league="sln"):
    for x in dataset(league)["seasons"]:
        if x["key"] == code:
            return x["label"]
    return code


def season_year(code, league="sln"):
    for x in dataset(league)["seasons"]:
        if x["key"] == code:
            return x["order"]
    return None


# ---------------------------------------------------------------- lookups


def norm(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def find_players(query, league="sln"):
    """All distinct names matching query, best-first (exact > startswith > substring)."""
    q = norm(query)
    rows = dataset(league)["players"]
    hits = {}
    for r in rows:
        n = norm(r["name"])
        if q == n:
            rank = 0
        elif n.startswith(q):
            rank = 1
        elif q in n:
            rank = 2
        else:
            continue
        prev = hits.get(r["name"])
        if prev is None or rank < prev:
            hits[r["name"]] = rank
    return [n for n, _ in sorted(hits.items(), key=lambda kv: (kv[1], kv[0]))]


def player_seasons(name, league="sln"):
    return sorted(
        [r for r in dataset(league)["players"] if r["name"] == name],
        key=lambda r: season_year(r["season"], league) or 0,
    )


def team_nick(full):
    """'Portland Trail Blazers' -> plausible nickname tail used by box/game data."""
    parts = (full or "").split()
    return parts[-1] if parts else ""


def box_for(name, code):
    """Box-exact totals for one player-season, summed across teams. None if not covered."""
    seasons = load("data/box_agg.json")["seasons"]
    s = seasons.get(code)
    if not s:
        return None
    rec = s["players"].get(name)
    if not rec:
        return None
    tot = [0] * 8
    for _, vals in rec.items():
        for i in range(8):
            tot[i] += vals[i]
    return tot


def shooting_for(pid, year):
    yrs = load("out/season_shooting.json")["years"]
    row = yrs.get(str(year), {}).get(str(pid))
    return row


def resolve_team(q, code, league="sln"):
    """Team name / nickname / roster number -> (rn, full name) for that season."""
    rows = [r for r in dataset(league)["players"] if r["season"] == code]
    byrn = {}
    for r in rows:
        byrn[r["rn"]] = r["team"]
    q = str(q).strip()
    if q.isdigit() and int(q) in byrn:
        return int(q), byrn[int(q)]
    nq = norm(q)
    for rn, full in sorted(byrn.items()):
        if norm(full) == nq:
            return rn, full
    for rn, full in sorted(byrn.items()):
        if nq and nq in norm(full):
            return rn, full
    return None, None


# ---------------------------------------------------------------- format


def table(headers, rows):
    if not rows:
        return "(no rows)"
    cols = len(headers)
    w = [len(str(h)) for h in headers]
    srows = []
    for r in rows:
        sr = [("" if c is None else str(c)) for c in r] + [""] * (cols - len(r))
        srows.append(sr[:cols])
        for i in range(cols):
            w[i] = max(w[i], len(sr[i]))
    out = [" | ".join(str(headers[i]).ljust(w[i]) for i in range(cols))]
    out.append("-|-".join("-" * w[i] for i in range(cols)))
    for sr in srows:
        out.append(" | ".join(sr[i].ljust(w[i]) for i in range(cols)))
    return "\n".join(out)


def num(x, nd=1):
    if x is None:
        return ""
    if isinstance(x, float) and x == int(x) and nd == 0:
        return str(int(x))
    return ("%." + str(nd) + "f") % x


def pct(x):
    if x is None:
        return ""
    return ("%.3f" % x).lstrip("0") if x < 1 else "%.3f" % x


# ================================================================= tools


def t_status(a):
    d = dataset("sln")
    seasons = d["seasons"]
    played = [s for s in seasons if s.get("played")]
    box = load("data/box_agg.json")["seasons"]
    games = load("data/games.json")["seasons"]
    careers = load("out/careers_dataset.json")
    live = seasons[0]
    lines = [
        "SLN STAT BOOK — local data status",
        "",
        "Live season: %s   Last completed: %s" % (live["label"], seasons[1]["label"]),
        "Seasons on disk: %d (%s .. %s). No 1998 season exists."
        % (len(seasons), seasons[-1]["label"], seasons[0]["label"]),
        "Player-season rows: %d   Career segments: %d" % (len(d["players"]), len(careers["careers"])),
        "NDL: current season only (%d rows) — league publishes no history."
        % len(dataset("ndl")["players"]),
        "",
        "Box-score coverage (exact reb/ast/stl/blk/to/pf/min): %d seasons" % len(box),
        "  missing upstream: 1996, 1997, 2000, 2005 (no box files published)",
        "Game results: %d seasons" % len(games),
        "",
        "File freshness (local build artifacts):",
    ]
    for rel in [
        "out/players_dataset.json",
        "out/careers_dataset.json",
        "data/box_agg.json",
        "data/games.json",
        "out/season_shooting.json",
    ]:
        lines.append("  %-30s %s" % (rel, mtime(rel) or "MISSING"))
    lines += [
        "  career totals pulled:          %s" % careers.get("fetched", "?"),
        "",
        "Completed seasons never change, so history is always correct here.",
        "The live season is simmed daily, so these files go stale between sessions.",
        "CI rebuilds and republishes every 4h:",
        "  https://slnstatbook.com  (repo: jburns-build/sln-stat-book)",
        "sln_refresh (mode='sync', the default) pulls that build down — it is the",
        "fastest way to be current and it cannot disagree with the live site.",
        "",
        "EXACT: games, points (2*FG+3P+FT), FG, FT, 3P, DD, TD, and — for box-covered",
        "seasons — reb/ast/stl/blk/to/min. DERIVED (~0.1%, marked ~): rate stats summed",
        "as per-game x games for seasons with no box files.",
    ]
    return "\n".join(lines)


def t_search_players(a):
    league = a.get("league", "sln")
    names = find_players(a["query"], league)
    if not names:
        return "No player matches %r in %s." % (a["query"], league.upper())
    limit = int(a.get("limit", 25))
    careers = {c["name"]: c for c in load("out/careers_dataset.json")["careers"]}
    rows = []
    for n in names[:limit]:
        ss = player_seasons(n, league)
        yrs = [season_year(r["season"], league) for r in ss]
        c = careers.get(n) if league == "sln" else None
        rows.append([
            n,
            ss[-1]["pos"] if ss else "",
            "%s-%s" % (min(yrs), max(yrs)) if yrs else "",
            len(ss),
            ss[-1]["team"] if ss else "",
            "active" if (c and c.get("active")) else "",
        ])
    out = table(["Name", "Pos", "Years", "Ssns", "Last team", ""], rows)
    if len(names) > limit:
        out += "\n(%d more matches — narrow the query)" % (len(names) - limit)
    return out


def t_player(a):
    league = a.get("league", "sln")
    names = find_players(a["name"], league)
    if not names:
        return "No player matches %r in %s. Try sln_search_players." % (a["name"], league.upper())
    if len(names) > 1 and norm(names[0]) != norm(a["name"]):
        return "Ambiguous %r — matches: %s\nRe-ask with a full name." % (a["name"], ", ".join(names[:12]))
    name = names[0]
    ss = player_seasons(name, league)
    d = dataset(league)
    champs = d.get("champs", {})
    allstars = set()
    if league == "sln":
        allstars = set(y for n, y in load("out/allstar.json")["appearances"] if n == name)

    head = ["Year", "Team", "Age", "Pos", "G", "MPG", "PPG", "RPG", "APG", "SPG", "BPG", "TPG",
            "FG%", "FT%", "3P%", "Notes"]
    rows = []
    for r in ss:
        code, yr = r["season"], season_year(r["season"], league)
        notes = []
        if champs.get(code) == r["rn"]:
            notes.append("CHAMP")
        if yr in allstars:
            notes.append("All-Star")
        notes += r.get("awards") or []
        if not r.get("g"):
            notes.append("(did not play)")
        rows.append([
            season_label(code, league), r["team"], r.get("age"), r.get("pos"),
            num(r.get("g"), 0), num(r.get("mpg")), num(r.get("ppg")), num(r.get("rpg")),
            num(r.get("apg")), num(r.get("spg")), num(r.get("bpg")), num(r.get("tpg")),
            pct(r.get("fgp")), pct(r.get("ftp")), pct(r.get("tpp")),
            "; ".join(notes),
        ])
    out = ["%s — %s" % (name, league.upper()), "", table(head, rows)]

    # ability grades
    grades = [r for r in ss if r.get("abil")]
    if grades:
        gh = ["Year", "In", "Out", "Hn", "Df", "Reb", "Pot"]
        gr = [[season_label(r["season"], league)] + [r["abil"].get(k, "") for k in
              ("In", "Out", "Hn", "Df", "Reb", "Pot")] for r in grades]
        out += ["", "Ability grades", table(gh, gr)]

    if league != "sln":
        return "\n".join(out)

    # box-exact per season
    bx = []
    for r in ss:
        b = box_for(name, r["season"])
        sh = shooting_for(r["id"], season_year(r["season"], league))
        if not b and not sh:
            continue
        bx.append([
            season_label(r["season"], league),
            b[BOX["g"]] if b else "", b[BOX["min"]] if b else "",
            b[BOX["reb"]] if b else "", b[BOX["ast"]] if b else "",
            b[BOX["stl"]] if b else "", b[BOX["blk"]] if b else "",
            b[BOX["tov"]] if b else "", b[BOX["pf"]] if b else "",
            sh[SHOOT["fg"]] if sh else "", sh[SHOOT["fga"]] if sh else "",
            sh[SHOOT["ft"]] if sh else "", sh[SHOOT["fta"]] if sh else "",
            sh[SHOOT["tp"]] if sh else "", sh[SHOOT["tpa"]] if sh else "",
        ])
    if bx:
        out += ["", "Box-score totals (exact counting stats; blank = season not archived)",
                table(["Year", "G", "MIN", "REB", "AST", "STL", "BLK", "TO", "PF",
                       "FG", "FGA", "FT", "FTA", "3P", "3PA"], bx)]

    # career
    segs = [c for c in load("out/careers_dataset.json")["careers"] if c["name"] == name]
    for c in segs:
        approx = "~" if c.get("dg") else ""
        out += ["", "CAREER (%d-%d, %d seasons%s)" % (
            c["first"], c["last"], c["seasons"], ", active" if c.get("active") else "")]
        out.append("  G %s  PTS %s  FG %s/%s  FT %s/%s  3P %s/%s" % (
            num(c["games"], 0), num(c["pts"], 0), num(c["fg"], 0), num(c["fga"], 0),
            num(c["ft"], 0), num(c["fta"], 0), num(c["tp"], 0), num(c["tpa"], 0)))
        out.append("  REB %s%s  AST %s%s  STL %s%s  BLK %s%s  TO %s%s" % (
            approx, num(c["reb"], 0), approx, num(c["ast"], 0), approx, num(c["stl"], 0),
            approx, num(c["blk"], 0), approx, num(c["tov"], 0)))
        pg = c.get("pg") or {}
        out.append("  Per game (official): %s" % "  ".join(
            "%s %s" % (k.upper(), num(v)) for k, v in pg.items()))
        out.append("  Double-doubles %s  Triple-doubles %s  All-Star %d" % (
            c["dd"], c["td"], len(allstars)))
        if c.get("dg"):
            out.append("  ~ = %d games' rate stats derived from per-game averages "
                       "(season not box-archived)" % c["dg"])
        if c.get("teams"):
            out.append("  Teams: %s" % ", ".join(c["teams"]))
    return "\n".join(out)


SORTABLE = {"ppg": "ppg", "rpg": "rpg", "apg": "apg", "spg": "spg", "bpg": "bpg",
            "tpg": "tpg", "mpg": "mpg", "g": "g", "fgp": "fgp", "ftp": "ftp", "tpp": "tpp",
            "age": "age", "pts": "_pts"}


def t_season(a):
    league = a.get("league", "sln")
    code = season_code(a.get("season"), league)
    if code is None:
        return "Unknown season %r. Try a year like 2037, or 'current'." % a.get("season")
    rows = [r for r in dataset(league)["players"] if r["season"] == code]
    if a.get("team"):
        rn, full = resolve_team(a["team"], code, league)
        if rn is None:
            return "No team matches %r in %s." % (a["team"], season_label(code, league))
        rows = [r for r in rows if r["rn"] == rn]
    if a.get("pos"):
        want = a["pos"].upper()
        rows = [r for r in rows if (r.get("pos") or "").upper() == want]
    min_mpg = float(a.get("min_mpg", 0) or 0)
    rows = [r for r in rows if (r.get("mpg") or 0) >= min_mpg]
    if a.get("min_games"):
        rows = [r for r in rows if (r.get("g") or 0) >= float(a["min_games"])]
    rows = [r for r in rows if (r.get("g") or 0) > 0] or rows

    sort = (a.get("sort") or "ppg").lower()
    if sort not in SORTABLE:
        return "sort must be one of: %s" % ", ".join(sorted(SORTABLE))
    for r in rows:
        r["_pts"] = (r.get("ppg") or 0) * (r.get("g") or 0)
    key = SORTABLE[sort]
    asc = bool(a.get("ascending")) or sort == "tpg"
    rows.sort(key=lambda r: (r.get(key) or 0), reverse=not asc)
    limit = int(a.get("limit", 25))
    shown = rows[:limit]

    head = ["#", "Name", "Team", "Pos", "Age", "G", "MPG", "PPG", "RPG", "APG", "SPG",
            "BPG", "TPG", "FG%", "FT%", "3P%", "PTS"]
    out = []
    for i, r in enumerate(shown, 1):
        out.append([
            i, r["name"], r["team"], r.get("pos"), r.get("age"), num(r.get("g"), 0),
            num(r.get("mpg")), num(r.get("ppg")), num(r.get("rpg")), num(r.get("apg")),
            num(r.get("spg")), num(r.get("bpg")), num(r.get("tpg")),
            pct(r.get("fgp")), pct(r.get("ftp")), pct(r.get("tpp")), num(r["_pts"], 0),
        ])
    hdr = "%s %s — sorted by %s%s, %d of %d players" % (
        league.upper(), season_label(code, league), sort,
        " (ascending)" if asc else "", len(shown), len(rows))
    note = ""
    if sort == "tpg":
        note = "\n(turnovers sorted fewest-first; set ascending=false to invert)"
    return hdr + "\n\n" + table(head, out) + note


def t_standings(a):
    league = a.get("league", "sln")
    code = season_code(a.get("season"), league)
    if code is None:
        return "Unknown season %r." % a.get("season")
    d = dataset(league)
    rec = (d.get("records") or {}).get(code) or {}
    if not rec:
        return "No W-L records stored for %s." % season_label(code, league)
    teams = {}
    for r in d["players"]:
        if r["season"] == code:
            teams[r["rn"]] = r["team"]
    champ_rn = (d.get("champs") or {}).get(code)
    out = ["%s %s standings" % (league.upper(), season_label(code, league))]
    for conf, div, rng in DIVISIONS:
        rows = []
        for rn in rng:
            if str(rn) not in rec and rn not in rec:
                continue
            w, l = rec.get(str(rn)) or rec.get(rn)
            gp = w + l
            rows.append([teams.get(rn, "rn%d" % rn), w, l,
                         pct(w / gp) if gp else "",
                         "CHAMPION" if rn == champ_rn else ""])
        rows.sort(key=lambda x: -(x[1] / (x[1] + x[2]) if (x[1] + x[2]) else 0))
        out += ["", "%s / %s" % (conf, div), table(["Team", "W", "L", "Pct", ""], rows)]
    if champ_rn:
        out += ["", "Champion: %s" % teams.get(champ_rn, "rn%d" % champ_rn)]
    return "\n".join(out)


def t_team(a):
    league = a.get("league", "sln")
    code = season_code(a.get("season"), league)
    if code is None:
        return "Unknown season %r." % a.get("season")
    rn, full = resolve_team(a["team"], code, league)
    if rn is None:
        return "No team matches %r in %s." % (a["team"], season_label(code, league))
    b = dict(a)
    b["team"] = str(rn)
    b["season"] = code
    b["limit"] = a.get("limit", 30)
    b["sort"] = a.get("sort", "ppg")
    head = t_season(b)
    d = dataset(league)
    rec = (d.get("records") or {}).get(code) or {}
    wl = rec.get(str(rn)) or rec.get(rn)
    extra = []
    if wl:
        extra.append("Record: %d-%d" % (wl[0], wl[1]))
    if (d.get("champs") or {}).get(code) == rn:
        extra.append("*** CHAMPION ***")
    banner = "%s (roster #%d) — %s  %s" % (full, rn, season_label(code, league), "  ".join(extra))
    return banner + "\n\n" + head


CAREER_STATS = {
    "games": ("games", 0), "points": ("pts", 0), "pts": ("pts", 0),
    "fg": ("fg", 0), "ft": ("ft", 0), "3p": ("tp", 0), "tp": ("tp", 0),
    "reb": ("reb", 0), "ast": ("ast", 0), "stl": ("stl", 0), "blk": ("blk", 0),
    "tov": ("tov", 0), "minutes": ("mp", 0), "dd": ("dd", 0), "td": ("td", 0),
    "seasons": ("seasons", 0),
    "ppg": ("_ppg", 1), "rpg": ("_rpg", 1), "apg": ("_apg", 1),
    "spg": ("_spg", 1), "bpg": ("_bpg", 1),
}


def t_career_leaders(a):
    stat = (a.get("stat") or "points").lower()
    if stat not in CAREER_STATS:
        return "stat must be one of: %s" % ", ".join(sorted(CAREER_STATS))
    field, nd = CAREER_STATS[stat]
    careers = list(load("out/careers_dataset.json")["careers"])
    per_game = field.startswith("_")
    if per_game:
        k = field[1:]
        for c in careers:
            c[field] = (c.get("pg") or {}).get(k)
        min_g = float(a.get("min_games", 100))
        careers = [c for c in careers if c.get(field) is not None and c["games"] >= min_g]
    elif a.get("min_games"):
        careers = [c for c in careers if c["games"] >= float(a["min_games"])]
    if a.get("active_only"):
        careers = [c for c in careers if c.get("active")]
    careers.sort(key=lambda c: (c.get(field) or 0), reverse=True)
    limit = int(a.get("limit", 10))
    rows = []
    for i, c in enumerate(careers[:limit], 1):
        approx = "~" if (c.get("dg") and field in ("reb", "ast", "stl", "blk", "tov")) else ""
        rows.append([i, c["name"], approx + num(c.get(field), nd), num(c["games"], 0),
                     "%d-%d" % (c["first"], c["last"]),
                     "active" if c.get("active") else "", ", ".join(c.get("teams") or [])[:40]])
    hdr = "Career leaders — %s%s%s" % (
        stat, " (active only)" if a.get("active_only") else "",
        " (min %s games)" % (a.get("min_games", 100) if per_game else a.get("min_games", "")) if
        (per_game or a.get("min_games")) else "")
    foot = ""
    if field in ("reb", "ast", "stl", "blk", "tov"):
        foot = "\n~ = includes seasons with no box archive; those are derived from per-game averages."
    return hdr + "\n\n" + table(["#", "Name", stat.upper(), "G", "Years", "", "Teams"], rows) + foot


def t_games(a):
    league = "sln"
    code = season_code(a.get("season"), league)
    if code is None:
        return "Unknown season %r." % a.get("season")
    seasons = load("data/games.json")["seasons"]
    s = seasons.get(code)
    if not s:
        return ("No game results stored for %s. Coverage: %s"
                % (season_label(code, league), ", ".join(sorted(seasons))))
    names = {}
    for r in dataset(league)["players"]:
        if r["season"] == code:
            names[r["rn"]] = r["team"]
    games = s["games"]
    rn_a = rn_b = None
    if a.get("team"):
        rn_a, full_a = resolve_team(a["team"], code, league)
        if rn_a is None:
            return "No team matches %r." % a["team"]
    if a.get("opponent"):
        rn_b, full_b = resolve_team(a["opponent"], code, league)
        if rn_b is None:
            return "No team matches %r." % a["opponent"]
    sel = []
    for g in games:
        ra, sa, rb, sb = g
        if rn_a is not None and rn_a not in (ra, rb):
            continue
        if rn_b is not None and rn_b not in (ra, rb):
            continue
        sel.append(g)
    if rn_a is None:
        # league-wide summary
        agg = {}
        for ra, sa, rb, sb in games:
            for rn, pf, pa, won in ((ra, sa, sb, sa > sb), (rb, sb, sa, sb > sa)):
                e = agg.setdefault(rn, [0, 0, 0, 0])
                e[0] += 1 if won else 0
                e[1] += 0 if won else 1
                e[2] += pf
                e[3] += pa
        rows = []
        for rn, (w, l, pf, pa) in agg.items():
            gp = w + l
            rows.append([names.get(rn, "rn%d" % rn), w, l, pct(w / gp) if gp else "",
                         num(pf / gp) if gp else "", num(pa / gp) if gp else "",
                         num((pf - pa) / gp) if gp else ""])
        rows.sort(key=lambda r: -(r[1] / (r[1] + r[2]) if (r[1] + r[2]) else 0))
        return ("%s — %d games%s\n\n" % (season_label(code, league), len(games),
                "" if s.get("complete") else " (season in progress)")
                + table(["Team", "W", "L", "Pct", "PPG", "PA", "Diff"], rows))
    w = l = pf = pa = 0
    rows = []
    for ra, sa, rb, sb in sel:
        me, opp = (ra, rb) if ra == rn_a else (rb, ra)
        ms, os_ = (sa, sb) if ra == rn_a else (sb, sa)
        won = ms > os_
        w += 1 if won else 0
        l += 0 if won else 1
        pf += ms
        pa += os_
        rows.append(["W" if won else "L", names.get(opp, "rn%d" % opp), "%d-%d" % (ms, os_)])
    gp = w + l or 1
    hdr = "%s — %s: %d-%d, %s PPG / %s allowed (%s)" % (
        names.get(rn_a, "rn%d" % rn_a), season_label(code, league), w, l,
        num(pf / gp), num(pa / gp), num((pf - pa) / gp))
    if a.get("opponent"):
        hdr += "\nHead-to-head vs %s" % names.get(rn_b, "")
    if not a.get("detail", True):
        return hdr
    return hdr + "\n\n" + table(["", "Opponent", "Score"], rows)


def t_guide(a):
    path = os.path.join(ROOT, "SLN_NIRVANA_KNOWLEDGE_BASE.md")
    if not os.path.exists(path):
        return "Knowledge base not found at %s" % path
    text = open(path, "r", encoding="utf-8").read()
    sec = a.get("section")
    if not sec:
        return text
    blocks = re.split(r"\n(?=## )", text)
    hit = [b for b in blocks if norm(sec) in norm(b.split("\n", 1)[0])]
    return "\n\n".join(hit) if hit else (
        "No section matching %r. Sections:\n%s" % (sec, "\n".join(
            b.split("\n", 1)[0] for b in blocks if b.startswith("## "))))


# The published site rebuilds every 4 hours from CI. Games are simmed daily, so
# a local stat book goes stale between sessions no matter how good the history
# is. Syncing pulls exactly what CI already built and verified, which is both
# faster than a local rebuild and guaranteed to agree with the live site.
API = "https://slnstatbook.com/api"
SYNC_MAP = [
    ("players_dataset.json", "out/players_dataset.json"),
    ("ndl_players_dataset.json", "out/ndl_players_dataset.json"),
    ("careers_dataset.json", "out/careers_dataset.json"),
    ("season_shooting.json", "out/season_shooting.json"),
    ("allstar.json", "out/allstar.json"),
    ("box_agg.json", "data/box_agg.json"),
    ("games.json", "data/games.json"),
]


def _api_get(name, timeout=90):
    req = urllib.request.Request("%s/%s" % (API, name),
                                 headers={"User-Agent": "sln-mcp/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _sync():
    """Replace the local build artifacts with the ones the published site serves."""
    try:
        man = json.loads(_api_get("manifest.json", timeout=30))
    except Exception as e:
        return ("Could not reach %s/manifest.json (%s).\n"
                "The datasets are published by the 'Stage site' step of the CI "
                "workflow; if that change has not been pushed and run yet, this "
                "endpoint does not exist and sync cannot work. Use "
                "sln_refresh with mode='rebuild' meanwhile." % (API, e))
    out = ["published build %s   live season: %s" % (man["built"], man["live_season"])]
    changed = 0
    for name, rel in SYNC_MAP:
        meta = man.get("files", {}).get(name)
        dest = os.path.join(ROOT, rel)
        if not meta:
            out.append("  --  %-28s not published" % rel)
            continue
        if os.path.exists(dest):
            local = hashlib.sha256(open(dest, "rb").read()).hexdigest()
            if local == meta["sha256"]:
                out.append("  ok  %-28s already current" % rel)
                continue
        try:
            blob = _api_get(name)
        except Exception as e:
            out.append("  !!  %-28s download failed (%s)" % (rel, e))
            continue
        if hashlib.sha256(blob).hexdigest() != meta["sha256"]:
            out.append("  !!  %-28s checksum mismatch — left untouched" % rel)
            continue
        # write via a temp file so an interrupted sync can never leave a
        # half-written dataset that every later query would silently read
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, dest)
        changed += 1
        out.append("  UP  %-28s %d KB" % (rel, meta["bytes"] // 1024))
    _cache.clear()
    out.append("")
    out.append("%d file(s) updated; caches cleared." % changed)
    return "\n".join(out)


def t_refresh(a):
    """Sync from the published build, or rebuild locally from the on-disk mirror."""
    mode = a.get("mode") or ("scrape" if a.get("include_scrape") else "sync")
    if mode == "sync":
        return _sync()
    # Full offline rebuild chain. link_leagues and build_ndl_history must follow
    # the dataset builds — build_players_dataset --league ndl writes a
    # current-season-only file, and build_ndl_history is what folds the archived
    # NDL seasons back in. Omitting them silently drops NDL history.
    steps = [
        ["python3", "scripts/build_players_dataset.py"],
        ["python3", "scripts/build_players_dataset.py", "--league", "ndl"],
        ["python3", "scripts/link_leagues.py"],
        ["python3", "scripts/build_ndl_history.py"],
    ]
    if mode == "scrape":
        steps = [["python3", "scripts/scrape_rosters_gap.py"],
                 ["python3", "scripts/scrape_awards.py"]] + steps
    out = []
    for cmd in steps:
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            out.append("TIMEOUT: %s" % " ".join(cmd))
            break
        tail = (p.stdout or p.stderr or "").strip().splitlines()[-3:]
        out.append("%s %s (%.1fs)\n  %s" % (
            "ok " if p.returncode == 0 else "FAIL", " ".join(cmd), time.time() - t0,
            "\n  ".join(tail)))
        if p.returncode != 0:
            break
    _cache.clear()
    return "\n".join(out) + "\n\nCaches cleared; next query reads the rebuilt files."


# ================================================================= schema

LEAGUE = {"type": "string", "enum": ["sln", "ndl"], "description": "Default sln. NDL is current season only."}
SEASON = {"type": "string", "description": "Year (2037), season code (37), or 'current'. Defaults to newest."}

TOOLS = [
    {
        "name": "sln_status",
        "description": "Data coverage and freshness for the SLN/NDL stat book: seasons on disk, "
                       "row counts, box-score coverage, which stats are exact vs derived. "
                       "Call this first when you need to know what is answerable.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": t_status,
    },
    {
        "name": "sln_search_players",
        "description": "Find players by partial or full name. Returns career span, position, "
                       "last team, active flag. Use to disambiguate before sln_player.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Partial or full name."},
            "league": LEAGUE,
            "limit": {"type": "integer", "description": "Default 25."},
        }, "required": ["query"]},
        "fn": t_search_players,
    },
    {
        "name": "sln_player",
        "description": "Everything about one player: season-by-season stats, ability grades, "
                       "awards, All-Star years, championships, box-exact counting totals, raw "
                       "shooting splits, and bundled career totals.",
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Full name preferred."},
            "league": LEAGUE,
        }, "required": ["name"]},
        "fn": t_player,
    },
    {
        "name": "sln_season",
        "description": "A season's players as a sortable, filterable leaderboard — league leaders, "
                       "team rosters, positional splits. Sort by any rate stat or total points.",
        "inputSchema": {"type": "object", "properties": {
            "season": SEASON,
            "league": LEAGUE,
            "sort": {"type": "string", "description":
                     "ppg rpg apg spg bpg tpg mpg g fgp ftp tpp age pts. Default ppg. "
                     "tpg sorts fewest-first."},
            "ascending": {"type": "boolean"},
            "team": {"type": "string", "description": "Team name, nickname, or roster number."},
            "pos": {"type": "string", "description": "PG SG SF PF C"},
            "min_mpg": {"type": "number", "description": "Minutes-per-game floor. Use ~15-20 for rate leaders."},
            "min_games": {"type": "number"},
            "limit": {"type": "integer", "description": "Default 25."},
        }},
        "fn": t_season,
    },
    {
        "name": "sln_standings",
        "description": "Win-loss records for a season by conference and division, plus that "
                       "season's champion.",
        "inputSchema": {"type": "object", "properties": {"season": SEASON, "league": LEAGUE}},
        "fn": t_standings,
    },
    {
        "name": "sln_team",
        "description": "One team's roster for a season with full stats, record, and championship flag.",
        "inputSchema": {"type": "object", "properties": {
            "team": {"type": "string", "description": "Team name, nickname, or roster number."},
            "season": SEASON,
            "league": LEAGUE,
            "sort": {"type": "string"},
            "limit": {"type": "integer"},
        }, "required": ["team"]},
        "fn": t_team,
    },
    {
        "name": "sln_career_leaders",
        "description": "All-time career leaderboards: totals (games points fg ft 3p reb ast stl "
                       "blk tov minutes dd td seasons) or per-game (ppg rpg apg spg bpg, min 100 "
                       "games). Un-retirements are bundled into one career.",
        "inputSchema": {"type": "object", "properties": {
            "stat": {"type": "string", "description": "Default points."},
            "active_only": {"type": "boolean", "description": "Restrict to players active this season."},
            "min_games": {"type": "number", "description": "Default 100 for per-game stats."},
            "limit": {"type": "integer", "description": "Default 10."},
        }},
        "fn": t_career_leaders,
    },
    {
        "name": "sln_games",
        "description": "Regular-season game results. No team: league-wide W-L with points for/against "
                       "and margin. With team: that team's full results. Add opponent for head-to-head.",
        "inputSchema": {"type": "object", "properties": {
            "season": SEASON,
            "team": {"type": "string"},
            "opponent": {"type": "string"},
            "detail": {"type": "boolean", "description": "Include the game log. Default true."},
        }},
        "fn": t_games,
    },
    {
        "name": "sln_guide",
        "description": "The Sim League Nirvana field guide: URL map, page anatomy, season-code "
                       "conventions, and the quirks that cause wrong answers (recycled player ids, "
                       "the missing 1998, career-page resets, offseason carryover, traded-player "
                       "stat crediting). Read before scraping the live site or making a claim the "
                       "local data cannot support.",
        "inputSchema": {"type": "object", "properties": {
            "section": {"type": "string", "description": "Optional section filter, e.g. 'url map'."},
        }},
        "fn": t_guide,
    },
    {
        "name": "sln_refresh",
        "description": "Bring the local stat book up to date. Default mode 'sync' downloads the "
                       "datasets the published site was built from (rebuilt by CI every 4 hours, so "
                       "it tracks the daily sims) — fast, and always agrees with slnstatbook.com. "
                       "'rebuild' recomputes offline from the on-disk mirror without touching the "
                       "network. 'scrape' re-fetches the live season from the league site first, "
                       "then rebuilds; only needed to get ahead of the next CI run.",
        "inputSchema": {"type": "object", "properties": {
            "mode": {"type": "string", "enum": ["sync", "rebuild", "scrape"],
                     "description": "Default 'sync'."},
            "include_scrape": {"type": "boolean",
                               "description": "Deprecated; equivalent to mode='scrape'."},
        }},
        "fn": t_refresh,
    },
]

BY_NAME = dict((t["name"], t) for t in TOOLS)


# ================================================================= protocol


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def handle(req):
    """Return a response dict, or None for notifications."""
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        want = params.get("protocolVersion")
        version = want if want in KNOWN_PROTOCOLS else PROTOCOL_FALLBACK
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sln-stat-book", "version": "1.0.0"},
        }}

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in TOOLS]}}

    if method in ("resources/list", "prompts/list"):
        key = method.split("/")[0]
        return {"jsonrpc": "2.0", "id": rid, "result": {key: []}}

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = BY_NAME.get(name)
        if tool is None:
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32602, "message": "Unknown tool: %s" % name}}
        try:
            text = tool["fn"](args)
        except Exception as exc:  # surface as tool error, never crash the server
            import traceback
            log(traceback.format_exc())
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": "%s failed: %s: %s"
                             % (name, type(exc).__name__, exc)}],
                "isError": True}}
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": text}]}}

    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid, "error": {
        "code": -32601, "message": "Method not found: %s" % method}}


def main():
    if "--selftest" in sys.argv:
        return selftest()
    log("ready — ROOT=%s" % ROOT)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            log("bad JSON: %.120s" % line)
            continue
        try:
            resp = handle(req)
        except Exception as exc:
            import traceback
            log(traceback.format_exc())
            resp = {"jsonrpc": "2.0", "id": req.get("id"), "error": {
                "code": -32603, "message": str(exc)}}
        if resp is not None:
            send(resp)


def selftest():
    """Exercise every tool against the real data and print a pass/fail summary."""
    checks = [
        ("sln_status", {}),
        ("sln_search_players", {"query": "luka"}),
        ("sln_player", {"name": "Luka Doncic"}),
        ("sln_season", {"season": 2037, "sort": "ppg", "limit": 5}),
        ("sln_season", {"season": "current", "sort": "rpg", "min_mpg": 15, "limit": 5}),
        ("sln_standings", {"season": 2038}),
        ("sln_team", {"team": "Lakers", "season": 2038, "limit": 5}),
        ("sln_career_leaders", {"stat": "points", "limit": 5}),
        ("sln_career_leaders", {"stat": "ppg", "limit": 5}),
        ("sln_games", {"season": 2038, "team": "Celtics", "detail": False}),
        ("sln_guide", {"section": "url map"}),
    ]
    bad = 0
    for name, args in checks:
        try:
            out = BY_NAME[name]["fn"](args)
            first = out.strip().splitlines()[0] if out.strip() else "(empty)"
            ok = bool(out.strip()) and "failed" not in first.lower()
            print("%s %-20s %s" % ("ok  " if ok else "FAIL", name, first[:90]))
            if not ok:
                bad += 1
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print("FAIL %-20s %s: %s" % (name, type(exc).__name__, exc))
            bad += 1
    print("\n%d/%d checks passed" % (len(checks) - bad, len(checks)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
