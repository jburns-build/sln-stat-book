#!/usr/bin/env python3
"""Generate a single self-contained stats site from out/players_dataset.json.
Output: out/ndl_stats.html  (open directly or host statically)

Features: sortable/filterable player table; player + team names link to the
season-scoped simleaguenirvana.com pages; per-year leader highlighting
(top 1/3/5/10 per stat); 🏆 awards badges; and a per-player multi-year view
with Average and 2-year Compare modes.
"""
import json, os, sys, datetime, base64
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import branding
from branding import LOGO_SVG, FAVICON, LOGO_INLINE, SITE_ROOT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Two leagues share this generator. The NDL mirrors the SLN page layout exactly,
# just under /NDL/, and has no published history (current season only).
LEAGUES = {
    "sln": {"data": "players_dataset.json",     "out": "sln_stats.html",
            "name": "SLN", "site": "https://www.simleaguenirvana.com"},
    "ndl": {"data": "ndl_players_dataset.json", "out": "ndl_stats.html",
            "name": "NDL", "site": "https://www.simleaguenirvana.com/NDL"},
}
LEAGUE = "ndl" if "--league" in sys.argv and sys.argv[sys.argv.index("--league") + 1] == "ndl" else "sln"
CFG = LEAGUES[LEAGUE]
ds = json.load(open(f"{ROOT}/out/{CFG['data']}"))

# Per-season raw shooting (G,FG,FGA,FT,FTA,3P,3PA) from the player stats pages
# (emitted by scrape_careers.py) -> baked onto each player row as `sh` so the
# Advanced view can compute TS%/eFG%/3PAr/FTr client-side. SLN only: the NDL
# has no careers pipeline, so its Advanced view shows just the rate metrics.
_sf = f"{ROOT}/out/season_shooting.json"
if LEAGUE == "sln" and os.path.exists(_sf):
    _shoot = json.load(open(_sf))["years"]
    _yr = {s["key"]: str(s["order"]) for s in ds["seasons"]}
    _n = 0
    for p in ds["players"]:
        sh = _shoot.get(_yr.get(p["season"], ""), {}).get(str(p["id"]))
        if sh and p.get("g"):
            p["sh"] = sh
            _n += 1
    _pl = sum(1 for p in ds["players"] if p.get("g"))
    print(f"advanced shooting: joined {_n}/{_pl} played player-seasons")

# Current free agents (scrape_fa.py) -> flag their rows in the two NEWEST
# seasons so a "Free agents only" filter can show last season's stats during
# the offseason. Ids are stable across adjacent seasons; the era-recycling
# hazard only exists for older seasons, which never get the flag.
_ff = f"{ROOT}/out/fa.json"
if LEAGUE == "sln" and os.path.exists(_ff):
    _fa = set(json.load(open(_ff)).get("ids", []))
    if _fa:
        _newest = {s["key"] for s in
                   sorted(ds["seasons"], key=lambda s: -s["order"])[:2]}
        _n = 0
        for p in ds["players"]:
            if p["season"] in _newest and p["id"] in _fa:
                p["fa"] = 1
                _n += 1
        print(f"free agents: {len(_fa)} in pool, flagged {_n} rows across {sorted(_newest)}")

# Cross-league careers (link_leagues.py). The leagues don't share an id space,
# so these are joined by NAME and guarded on career shape — see that script.
# The SLN book gets each player's NDL seasons the way Baseball-Reference shows
# a minor-league line; the NDL book gets the SLN seasons they were called up to.
_xf = f"{ROOT}/out/cross_league.json"
ds["xl"] = None
if os.path.exists(_xf):
    _xl = json.load(open(_xf))
    _side = "ndl" if LEAGUE == "sln" else "sln"
    _rows = {n: r for n, r in _xl[_side].items()
             if any(p["name"] == n for p in ds["players"])}
    if _rows:
        ds["xl"] = {"side": _side, "cols": _xl["cols"], "rows": _rows}
        print(f"cross-league: {len(_rows)} players on this side carry "
              f"an {_side.upper()} career")

DATA_JS = json.dumps(ds, separators=(",", ":"))
# Build time shown to readers, in US Pacific (auto PST/PDT via the tz database)
BUILT = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%b %d, %Y · %-I:%M %p %Z")
# Optional "Refresh now" button: URL of the Cloudflare Worker relay (empty = no button)
_wu = f"{ROOT}/worker_url.txt"
WORKER_URL = open(_wu).read().strip() if os.path.exists(_wu) else ""

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,__FAVICON__">
<title>__LEAGUE__ Stat Book</title>
<style>
  :root{
    --bg:#f4f5f7; --panel:#ffffff; --ink:#141821; --muted:#5b6472;
    --line:#e2e6ec; --line2:#eef1f5; --link:#1257c9; --accent:#0b5cff;
    --hi:#fff6d6; --zebra:#fafbfc; --headbg:#151a24; --headink:#f4f6fa;
    --chip:#eef2f8; --pos:#334;
    --hl1:#ffd869; --hl3:#ffe9a8; --hl5:#dfe7f3; --hl10:#eef1f6;
    --up:#137a3e; --down:#c0392b; }
  *{box-sizing:border-box}
  [hidden]{display:none!important}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
  a{color:var(--link);text-decoration:none} a:hover{text-decoration:underline}
  header.top{background:var(--headbg);color:var(--headink);padding:14px 20px;
    display:flex;align-items:center;gap:14px;flex-wrap:wrap;
    border-bottom:3px solid var(--accent);}
  header.top .logo{font-size:20px;font-weight:800;letter-spacing:.3px;display:flex;align-items:center;gap:8px;cursor:pointer}
  header.top .logo .b{color:#ffcf3f}
__SWITCH_CSS__
  header.top nav span{color:#5f6b7e;margin:0 6px}
  .wrap{max-width:1560px;margin:0 auto;padding:18px 20px 60px}
  .bar{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    padding:14px 16px;display:flex;gap:18px;flex-wrap:wrap;align-items:flex-end;
    box-shadow:0 1px 2px rgba(20,24,33,.04);margin-bottom:12px}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld label{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--muted)}
  select,input[type=search]{font:inherit;padding:7px 10px;border:1px solid var(--line);
    border-radius:7px;background:#fff;color:var(--ink);min-width:150px}
  input[type=search]{min-width:210px}
  select:focus,input:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:var(--accent)}
  .count{margin-left:auto;color:var(--muted);font-size:13px;align-self:center;white-space:nowrap}
  .count b{color:var(--ink)}
  .legend{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:0 2px 12px;
    color:var(--muted);font-size:12px}
  .legend .sw{display:inline-block;width:13px;height:13px;border-radius:3px;
    vertical-align:-2px;margin-right:5px;border:1px solid rgba(0,0,0,.08)}
  .banner{background:#eef4ff;border:1px solid #cfe0ff;border-radius:9px;padding:10px 14px;
    margin-bottom:12px;font-size:14px;display:flex;align-items:center;gap:10px}
  .banner button{margin-left:auto}
  button.act{font:inherit;font-weight:600;padding:7px 13px;border:1px solid var(--accent);
    background:var(--accent);color:#fff;border-radius:7px;cursor:pointer}
  button.act.ghost{background:#fff;color:var(--accent)}
  button.act:disabled{opacity:.4;cursor:not-allowed}
  .seg{display:flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
  .seg button{font:inherit;font-weight:600;padding:7px 12px;border:none;background:#fff;
    color:var(--ink);cursor:pointer}
  .seg button+button{border-left:1px solid var(--line)}
  .seg button.on{background:var(--accent);color:#fff}
  .tablewrap{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    overflow:auto;box-shadow:0 1px 2px rgba(20,24,33,.04);max-height:calc(100vh - 250px)}
  table{border-collapse:separate;border-spacing:0;width:100%;font-variant-numeric:tabular-nums}
  thead th{position:sticky;top:0;z-index:2;background:var(--headbg);color:var(--headink);
    padding:9px 10px;text-align:right;font-size:12px;font-weight:700;white-space:nowrap;
    cursor:pointer;user-select:none;border-bottom:2px solid var(--accent)}
  thead th.txt{text-align:left}
  thead th:hover{background:#1e2634}
  thead th .ar{opacity:.35;font-size:10px;margin-left:3px}
  thead th.sort .ar{opacity:1;color:#ffcf3f}
  tbody td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--line2);white-space:nowrap}
  tbody td.txt{text-align:left}
  tbody tr:nth-child(even){background:var(--zebra)}
  tbody tr:hover{background:var(--hi)}
  td.name{font-weight:600}
  td.name a{color:var(--ink)}
  .team a{color:var(--muted)}
  .pos{display:inline-block;min-width:26px;text-align:center;padding:1px 6px;border-radius:5px;
    background:var(--chip);color:var(--pos);font-size:12px;font-weight:700}
  .team{color:var(--muted);font-size:13px}
  .rk{color:var(--muted);font-size:12px;text-align:right}
  .trophy{cursor:default;margin-left:5px;font-size:12px;letter-spacing:-1px}
  .pos.xl{margin-left:5px;min-width:0;background:#e6f0e8;color:#1d6b3c;
    font-size:10px;letter-spacing:.4px;cursor:default}
  tr.xlmove td{background:#f2f7ff}
  tr.xltot td{border-top:2px solid var(--line);font-weight:700;background:var(--zebra)}
  .cmp{margin-left:6px;cursor:pointer;opacity:.5;font-size:12px;border:none;background:none;padding:0}
  .cmp:hover{opacity:1}
  td.hl1{background:var(--hl1);font-weight:800}
  td.hl3{background:var(--hl3);font-weight:700}
  td.hl5{background:var(--hl5)}
  td.hl10{background:var(--hl10)}
  .empty{padding:40px;text-align:center;color:var(--muted)}
  .foot{margin-top:14px;color:var(--muted);font-size:12px;text-align:center}
  button.refresh{font:inherit;font-size:12px;font-weight:600;padding:3px 9px;border:1px solid var(--accent);
    background:var(--accent);color:#fff;border-radius:6px;cursor:pointer}
  button.refresh:disabled{opacity:.5;cursor:default}
  /* player view */
  #playerview{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    padding:18px 20px;box-shadow:0 1px 2px rgba(20,24,33,.04)}
  .pv-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:4px}
  .pv-head h2{margin:0;font-size:22px}
  .pv-sub{color:var(--muted);font-size:13px;margin-bottom:14px}
  .pv-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
  .pv-controls .lbl{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);margin-right:4px}
  .yr{font:inherit;font-size:13px;padding:5px 10px;border:1px solid var(--line);border-radius:16px;
    background:#fff;color:var(--ink);cursor:pointer}
  .yr.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  .modes{margin-left:auto;display:flex;gap:6px}
  .modes .yr.on{background:#151a24;border-color:#151a24}
  .awd{display:inline-block;background:#fff4d6;border:1px solid #ffe1a1;color:#7a5a12;
    border-radius:5px;padding:1px 6px;font-size:11px;font-weight:600;margin:1px 3px 1px 0;white-space:nowrap}
  .delta.up{color:var(--up);font-weight:700}
  .delta.down{color:var(--down);font-weight:700}
  @media (max-width:640px){ .count{width:100%;margin-left:0;order:9} }
</style>
</head>
<body>
<header class="top">
  <div class="logo" id="home">__LOGO__ <span>__LEAGUE__ <span class="b">Stat Book</span></span></div>
  <nav>__SWITCHER__</nav>
</header>
<div class="wrap">
  <div class="bar">
    <div class="fld"><label>View</label>
      <div class="seg"><button id="mBasic" class="on">Basic</button><button id="mAdv">Advanced</button></div></div>
    <div class="fld"><label for="season">Year</label>
      <select id="season"></select></div>
    <div class="fld"><label for="mpg">Minutes (MPG)</label>
      <select id="mpg">
        <option value="0">All players</option>
        <option value="5">5+ MPG</option>
        <option value="10">10+ MPG</option>
        <option value="15">15+ MPG</option>
        <option value="20">20+ MPG (rotation)</option>
        <option value="25">25+ MPG</option>
        <option value="30">30+ MPG (starters)</option>
      </select></div>
    <div class="fld"><label for="team">Team</label>
      <select id="team"><option value="">All teams</option></select></div>
    <div class="fld"><label for="rec">Team record</label>
      <select id="rec">
        <option value="">Any record</option>
        <option value="losing">Losing teams only</option>
        <option value="winning">Winning teams only</option>
      </select></div>
    <div class="fld"><label for="pos">Position</label>
      <select id="pos"><option value="">All</option></select></div>
    <div class="fld"><label for="ctr">Contract</label>
      <select id="ctr">
        <option value="">Any contract</option>
        <option value="1">Expiring (1 yr left)</option>
        <option value="2">2 yrs left</option>
        <option value="3">3+ yrs left</option>
      </select></div>
    <div class="fld" id="faFld" hidden><label for="fa">Status</label>
      <select id="fa">
        <option value="">All players</option>
        <option value="1">Free agents only</option>
      </select></div>
    <div class="fld"><label for="q">Search player</label>
      <input id="q" type="search" placeholder="name…" autocomplete="off"></div>
    <div class="count" id="count"></div>
  </div>

  <div id="tableview">
    <div class="banner" id="banner" hidden></div>
    <div class="legend">
      <span>Season leaders:</span>
      <span><span class="sw" style="background:var(--hl1)"></span>1st</span>
      <span><span class="sw" style="background:var(--hl3)"></span>Top 3</span>
      <span><span class="sw" style="background:var(--hl5)"></span>Top 5</span>
      <span><span class="sw" style="background:var(--hl10)"></span>Top 10</span>
      <span style="color:#9aa4b2" id="legendNote">· TPG = fewest (20+ MPG); FG/FT/3P leaders need 10+ MPG · 🏅 awards · 🏆 champion · 📊 compare years</span>
    </div>
    <div class="tablewrap">
      <table id="tbl">
        <thead><tr id="hrow"></tr></thead>
        <tbody id="body"></tbody>
      </table>
      <div class="empty" id="empty" hidden>No players match these filters.</div>
    </div>
  </div>

  <div id="playerview" hidden></div>

  <div class="foot">__LEAGUE__ Stat Book — data mirrored from simleaguenirvana.com · click a player name for their SLN page, 📊 to compare years · __GUIDE__<br>
    <span style="opacity:.85">Data updated <b id="buildstamp">__BUILT__</b> · auto-refreshes every 4 hours ·
    <button id="refreshBtn" class="refresh" hidden>🔄 Refresh now</button>
    <a href="#" onclick="location.reload();return false;">reload</a>
    <span id="refreshMsg" style="margin-left:6px"></span></span></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const DS = JSON.parse(document.getElementById('data').textContent);
const CHAMPS = DS.champs||{};
const RECORDS = DS.records||{};   // season -> {roster#: [wins, losses]}
const SITE='__SRC_SITE__';
const el = (id)=>document.getElementById(id);

// ---- advanced metrics, derived once at load ----
// Rate metrics come straight from the roster per-game data; shooting-efficiency
// metrics need raw attempts, baked as p.sh = [G,FG,FGA,FT,FTA,3P,3PA] from the
// player stats pages (SLN only). Points = 2·FG + 3P + FT (exact).
DS.players.forEach(p=>{
  if(!p.g) return;                                  // unplayed -> all stay '—'
  p.stk=(p.spg||0)+(p.bpg||0);
  p.sto=p.tpg>0?p.stk/p.tpg:null;                   // undefined at 0 TO
  p.ato=p.tpg>0?(p.apg||0)/p.tpg:null;
  const m=p.mpg, f36=v=>(m>0&&v!==null&&v!==undefined)?v/m*36:null;
  p.p36=f36(p.ppg); p.r36=f36(p.rpg); p.a36=f36(p.apg);
  p.s36=f36(p.spg); p.b36=f36(p.bpg); p.t36=f36(p.tpg);
  if(p.sh){
    const [g,fg,fga,ft,fta,tp,tpa]=p.sh, pts=2*fg+tp+ft, tsa=fga+0.44*fta;
    p.ts =tsa>0 ? pts/(2*tsa)      : null;
    p.efg=fga>0 ? (fg+0.5*tp)/fga  : null;
    p.par=fga>0 ? tpa/fga          : null;
    p.ftr=fga>0 ? fta/fga          : null;
  }
});
const HAS_SH = DS.players.some(p=>p.sh);

// season key -> year number / label
const YEAR={}, PLAYED={};
DS.seasons.forEach(s=>{ YEAR[s.key]=s.order; PLAYED[s.key]=s.played!==false; });
const yearNum=(k)=>YEAR[k];
const isChamp=(p)=> CHAMPS[p.season]===p.rn;
function champBadge(p){ return isChamp(p)
  ? `<span class="trophy" title="${yearNum(p.season)} Champion">🏆</span>` : ''; }
// team win/loss record for a player's team that season
const teamRec=(p)=>{ const s=RECORDS[p.season]; return s ? (s[p.rn]||null) : null; };
function recAttr(p){ const r=teamRec(p); return r ? ` title="${yearNum(p.season)} record: ${r[0]}-${r[1]}"` : ''; }
function recMatch(p,mode){                 // '' = any, 'losing' = W<L, 'winning' = W>L
  if(!mode) return true;
  const r=teamRec(p); if(!r) return false; // unknown record -> excluded from either filter
  return mode==='losing' ? r[0]<r[1] : r[0]>r[1];
}

// url builders (season-scoped; current season lives at the top level)
function playerUrl(p){ return p.season==='current'
  ? `${SITE}/players/player${p.id}.htm` : `${SITE}/history/${p.season}/players/player${p.id}.htm`; }
function teamUrl(p){ return p.season==='current'
  ? `${SITE}/rosters/roster${p.rn}.htm` : `${SITE}/history/${p.season}/rosters/roster${p.rn}.htm`; }

const BASIC_COLS = [
  {k:'rk',  t:'#'},
  {k:'name',t:'Player',txt:true},
  {k:'pos', t:'Pos',  txt:true},
  {k:'age', t:'Age'},
  {k:'team',t:'Team', txt:true},
  {k:'sal1',t:'Cap Hit', money:true},
  {k:'yrs', t:'Yrs'},
  {k:'g',   t:'G'},
  {k:'mpg', t:'MPG',  d:1},
  {k:'ppg', t:'PPG',  d:1},
  {k:'rpg', t:'RPG',  d:1},
  {k:'apg', t:'APG',  d:1},
  {k:'spg', t:'SPG',  d:1},
  {k:'bpg', t:'BPG',  d:1},
  {k:'tpg', t:'TPG',  d:1},
  {k:'fgp', t:'FG%',  pct:true},
  {k:'ftp', t:'FT%',  pct:true},
  {k:'tpp', t:'3P%',  pct:true},
];
const ADV_COLS = [
  {k:'rk',  t:'#'},
  {k:'name',t:'Player',txt:true},
  {k:'pos', t:'Pos',  txt:true},
  {k:'team',t:'Team', txt:true},
  {k:'g',   t:'G'},
  {k:'mpg', t:'MPG',  d:1},
  {k:'stk', t:'STK',  d:1, tip:'Stocks — steals + blocks per game'},
  {k:'sto', t:'S/TO', d:2, tip:'Stocks per turnover'},
  {k:'ato', t:'A/TO', d:2, tip:'Assists per turnover'},
  {k:'p36', t:'P36',  d:1, tip:'Points per 36 minutes'},
  {k:'r36', t:'R36',  d:1, tip:'Rebounds per 36 minutes'},
  {k:'a36', t:'A36',  d:1, tip:'Assists per 36 minutes'},
  {k:'s36', t:'S36',  d:1, tip:'Steals per 36 minutes'},
  {k:'b36', t:'B36',  d:1, tip:'Blocks per 36 minutes'},
  {k:'t36', t:'TO36', d:1, tip:'Turnovers per 36 minutes — fewer is better'},
  ...(HAS_SH ? [
  {k:'ts',  t:'TS%',  pct:true, tip:'True shooting % — PTS / (2 × (FGA + 0.44·FTA))'},
  {k:'efg', t:'eFG%', pct:true, tip:'Effective FG% — (FG + 0.5·3P) / FGA'},
  {k:'par', t:'3PAr', pct:true, tip:'Three-point attempt rate — 3PA / FGA'},
  {k:'ftr', t:'FTr',  pct:true, tip:'Free-throw rate — FTA / FGA'}] : []),
];
let MODE='basic';
const cols=()=> MODE==='adv' ? ADV_COLS : BASIC_COLS;
// stats eligible for leader-highlighting (G and MPG excluded)
const HILITE = [
  {k:'ppg',dir:'high'}, {k:'rpg',dir:'high'}, {k:'apg',dir:'high'},
  {k:'spg',dir:'high'}, {k:'bpg',dir:'high'},
  {k:'tpg',dir:'low', minMpg:20},
  {k:'fgp',dir:'high',minMpg:10}, {k:'ftp',dir:'high',minMpg:10}, {k:'tpp',dir:'high',minMpg:10},
];
// advanced view: per-36 and ratio leaders need real minutes or they're noise;
// TO36 mirrors the TPG "fewest" rule; 3PAr/FTr are shot-diet styles, not leaders
const HILITE_ADV = [
  {k:'stk',dir:'high'}, {k:'sto',dir:'high',minMpg:15}, {k:'ato',dir:'high',minMpg:15},
  {k:'p36',dir:'high',minMpg:15}, {k:'r36',dir:'high',minMpg:15}, {k:'a36',dir:'high',minMpg:15},
  {k:'s36',dir:'high',minMpg:15}, {k:'b36',dir:'high',minMpg:15},
  {k:'t36',dir:'low', minMpg:20},
  {k:'ts',dir:'high',minMpg:10}, {k:'efg',dir:'high',minMpg:10},
];
const hilite=()=> MODE==='adv' ? HILITE_ADV : HILITE;
const GOOD_UP = {ppg:1,rpg:1,apg:1,spg:1,bpg:1,fgp:1,ftp:1,tpp:1,tpg:-1}; // for compare deltas

let sortKey='ppg', sortDir=-1;
let view={player:null, years:new Set(), mode:'each'};

// --- season dropdown ---
const seasonSel=el('season');
DS.seasons.forEach(s=>{const o=document.createElement('option');o.value=s.key;
  o.textContent=s.label + (s.played===false?' — not yet played':'');seasonSel.appendChild(o);});
seasonSel.value=(DS.seasons.find(s=>s.played!==false)||DS.seasons[0]).key;

// --- formatting ---
function fmtNum(v,d){ if(v===null||v===undefined) return '—'; return d?v.toFixed(d):(''+v); }
function fmtPct(v){ if(v===null||v===undefined) return '—'; let n=v; if(n>1.5)n=n/100; return n.toFixed(3).replace(/^0/,''); }
function fmtMoney(v){ if(v===null||v===undefined||v===0) return '—'; return '$'+(v/1e6).toFixed(1)+'M'; }
function cellText(p,c){
  if(c.money) return fmtMoney(p[c.k]);
  if(c.pct)   return fmtPct(p[c.k]);
  return fmtNum(p[c.k], c.d);
}
function esc(s){ return (s+'').replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m])); }
function trophy(p){ return p.awards&&p.awards.length
  ? `<span class="trophy" title="${esc(p.awards.join(' · '))}">🏅</span>` : ''; }

// ---- cross-league careers (NDL <-> SLN), joined by name in link_leagues.py ----
const XL = DS.xl || null;
const XL_OTHER = XL ? (XL.side==='ndl' ? 'NDL' : 'SLN') : '';
// Normalise either side's stored shape into one row object. The NDL side is
// stored as the raw stats-page line [year, team, ...cols] with makes and
// attempts, so its percentages are computed here; the SLN side is already
// per-game roster data.
function xlRows(name){
  if(!XL) return null;
  const rec=XL.rows[name]; if(!rec) return null;
  if(XL.side==='sln') return {rec, rows:rec.rows};
  const at=k=>XL.cols.indexOf(k)+2;                 // +2: rows start [year, team]
  const rows=rec.rows.map(r=>{
    const fga=r[at('FGA')], fta=r[at('FTA')], tpa=r[at('3PA')];
    return {yr:r[0], team:r[1], g:r[at('Games')], mpg:r[at('MPG')], ppg:r[at('PPG')],
            rpg:r[at('RPG')], apg:r[at('APG')], spg:r[at('SPG')], bpg:r[at('BPG')],
            tpg:r[at('TOPG')],
            fgp: fga? r[at('FG')]/fga : null,
            ftp: fta? r[at('FT')]/fta : null,
            tpp: tpa? r[at('3P')]/tpa : null};
  });
  return {rec, rows};
}
function hasXL(name){ return !!(XL && XL.rows[name]); }
function xlBadge(name){
  if(!hasXL(name)) return '';
  const r=xlRows(name), y=r.rows.map(x=>x.yr);
  return `<span class="pos xl" title="${XL_OTHER} career: ${Math.min(...y)}–${Math.max(...y)}`
    +` — open this player to see it">${XL_OTHER}</span>`;
}
const XL_COLS=[
  {k:'yr',t:'Year',txt:true},{k:'team',t:'Team',txt:true},{k:'g',t:'G'},
  {k:'mpg',t:'MPG',d:1},{k:'ppg',t:'PPG',d:1},{k:'rpg',t:'RPG',d:1},
  {k:'apg',t:'APG',d:1},{k:'spg',t:'SPG',d:1},{k:'bpg',t:'BPG',d:1},
  {k:'tpg',t:'TPG',d:1},{k:'fgp',t:'FG%',pct:true},{k:'ftp',t:'FT%',pct:true},
  {k:'tpp',t:'3P%',pct:true},
];
function xlSection(name){
  const x=xlRows(name); if(!x) return '';
  const {rec,rows}=x;
  const cu=rec.move, up=rec.dir==='up';
  const note = XL.side==='ndl'
    ? `Developmental-league seasons, read from this player's NDL page. The league `
      +`publishes no NDL archive, so this is whatever their page still carries.`
    : `Top-flight SLN seasons.`;
  const mv = cu
    ? ` <b>${up?'Called up':'Sent down'} in ${cu}</b> — both leagues claim part of `
      +`that season, so neither line is a full year.`
    : '';
  let h=`<div class="pv-sub" style="margin-top:22px;margin-bottom:8px">`
    +`<b>${XL_OTHER} career</b> — ${note}${mv}</div>`;
  h+=`<div class="tablewrap"><table><thead><tr>`;
  XL_COLS.forEach(c=> h+=`<th class="${c.txt?'txt':''}">${c.t}</th>`);
  h+=`</tr></thead><tbody>`;
  rows.forEach(r=>{
    h+=`<tr${r.yr===cu?' class="xlmove"':''}>`;
    XL_COLS.forEach(c=>{
      let v;
      if(c.k==='yr')        v=r.yr+(r.yr===cu?` <span class="delta up" title="${up?'Called up to the SLN':'Sent down to the NDL'} this season">⇄</span>`:'');
      else if(c.k==='team') v=esc(r.team||'—');
      else if(c.pct)        v=fmtPct(r[c.k]);
      else                  v=fmtNum(r[c.k],c.d);
      h+=`<td class="${c.txt?'txt':''}">${v}</td>`;
    });
    h+=`</tr>`;
  });
  // career line: games summed, rates games-weighted (the source pages publish
  // their own career row, but only for the seasons still on the page)
  const G=rows.reduce((n,r)=>n+(r.g||0),0);
  h+=`<tr class="xltot">`;
  XL_COLS.forEach(c=>{
    let v;
    if(c.k==='yr')        v=`<b>${XL_OTHER} career</b>`;
    else if(c.k==='team'){ const n=rows.filter(r=>r.g>0).length; v=`${n} season${n===1?'':'s'}`; }
    else if(c.k==='g')    v=G;
    else { const a=wavg(rows,c.k); v=c.pct?fmtPct(a):fmtNum(a,c.d); }
    h+=`<td class="${c.txt?'txt':''}">${v}</td>`;
  });
  h+=`</tr></tbody></table></div>`;
  const bits=[];
  if(rec.dd)    bits.push(`${rec.dd} double-double${rec.dd>1?'s':''}`);
  if(rec.td)    bits.push(`${rec.td} triple-double${rec.td>1?'s':''}`);
  if(rec.rings) bits.push(`${rec.rings} 🏆`);
  if(bits.length) h+=`<div class="pv-sub" style="margin-top:6px">${XL_OTHER} career: ${bits.join(' · ')}</div>`;
  if(rec.awards && rec.awards.length)
    h+=`<div class="pv-sub" style="margin-top:6px">`
      +rec.awards.map(a=>`<span class="awd">${esc(a)}</span>`).join('')+`</div>`;
  return h;
}

// letter-grade ordering for ability change arrows
const GRADES=['F','D-','D','D+','C-','C','C+','B-','B','B+','A-','A','A+'];
const gradeVal=(g)=>{ const i=GRADES.indexOf((g||'').trim()); return i<0?null:i; };
const ABIL_KEYS=['In','Out','Hn','Df','Reb','Pot'];
const ABIL_FULL={In:'Inside',Out:'Outside',Hn:'Handling',Df:'Defense',Reb:'Rebounding',Pot:'Potential'};

// --- per-year leader ranks: ranks[stat][id] = 0..9 (best=0), only kept if top 10 ---
function computeRanks(seasonKey){
  const pool=DS.players.filter(p=>p.season===seasonKey);
  const ranks={};
  hilite().forEach(h=>{
    // only players who've actually played qualify (also stops an unplayed
    // season, where everything is 0.0, from highlighting every cell)
    const q=pool.filter(p=> p.g>0 && p[h.k]!==null && p[h.k]!==undefined && (!h.minMpg || (p.mpg!==null&&p.mpg>=h.minMpg)));
    const m={};
    q.forEach(p=>{
      const v=p[h.k];
      const better=q.reduce((n,o)=> n + (h.dir==='low' ? (o[h.k]<v?1:0) : (o[h.k]>v?1:0)), 0);
      if(better<10) m[p.id]=better;
    });
    ranks[h.k]=m;
  });
  return ranks;
}
function tierClass(rank){
  if(rank===0) return 'hl1';
  if(rank<=2)  return 'hl3';
  if(rank<=4)  return 'hl5';
  return 'hl10';
}

// ============================ TABLE VIEW ============================
function tableRows(){
  const season=seasonSel.value, mpg=+el('mpg').value, team=el('team').value,
        pos=el('pos').value, rec=el('rec').value, ctr=el('ctr').value,
        q=el('q').value.trim().toLowerCase();
  return DS.players.filter(p=> p.season===season
    && (mpg===0 || (p.mpg!==null && p.mpg>=mpg))
    && (!team || p.team===team)
    && (!pos || p.pos===pos)
    && recMatch(p,rec)
    && (!ctr || (ctr==='3' ? (p.yrs||0)>=3 : (p.yrs||0)===+ctr))
    && (!el('fa').value || p.fa)
    && (!q || p.name.toLowerCase().includes(q)));
}
function buildHead(){
  const hr=el('hrow'); hr.innerHTML='';
  cols().forEach(c=>{
    const th=document.createElement('th');
    th.textContent=c.t; if(c.txt) th.className='txt';
    if(c.tip) th.title=c.tip;
    if(c.k==='rk'){ th.style.cursor='default'; hr.appendChild(th); return; }
    const ar=document.createElement('span'); ar.className='ar'; ar.textContent='▾'; th.appendChild(ar);
    if(c.k===sortKey){ th.classList.add('sort'); ar.textContent = sortDir<0?'▾':'▴'; }
    th.onclick=()=>{ if(sortKey===c.k){sortDir=-sortDir;} else {sortKey=c.k; sortDir=c.txt?1:-1;} renderTable(); };
    hr.appendChild(th);
  });
}
function renderTable(){
  buildHead();
  let rows=tableRows();
  const dir=sortDir,k=sortKey;
  rows.sort((a,b)=>{
    let x=a[k],y=b[k];
    if(k==='name'||k==='team'||k==='pos'){ x=(x||'').toLowerCase(); y=(y||'').toLowerCase(); return x<y?-dir:x>y?dir:0; }
    if(x===null||x===undefined) return 1;
    if(y===null||y===undefined) return -1;
    return (x-y)*dir;
  });
  const ranks=computeRanks(seasonSel.value);
  const body=el('body'); body.innerHTML='';
  const frag=document.createDocumentFragment();
  rows.forEach((p,i)=>{
    const tr=document.createElement('tr');
    let html='';
    cols().forEach(c=>{
      if(c.k==='rk'){ html+=`<td class="txt rk">${i+1}</td>`; return; }
      if(c.k==='name'){ html+=`<td class="txt name"><a href="${playerUrl(p)}" target="_blank" rel="noopener">${esc(p.name)}</a>`
        +trophy(p)+xlBadge(p.name)+`<button class="cmp" title="Compare ${esc(p.name)} across years" data-nm="${esc(p.name)}">📊</button></td>`; return; }
      if(c.k==='pos'){ html+=`<td class="txt"><span class="pos">${esc(p.pos||'')}</span></td>`; return; }
      if(c.k==='team'){ html+=`<td class="txt team"><a href="${teamUrl(p)}"${recAttr(p)} target="_blank" rel="noopener">${esc(p.team)}</a>${champBadge(p)}${p.fa?'<span class="pos" style="margin-left:5px;background:#fde8cf;color:#8a5a12" title="Currently a free agent">FA</span>':''}</td>`; return; }
      const rk = ranks[c.k] && (p.id in ranks[c.k]) ? ranks[c.k][p.id] : null;
      const cls = rk!==null ? ' class="'+tierClass(rk)+'"' : '';
      html+=`<td${cls}>${cellText(p,c)}</td>`;
    });
    tr.innerHTML=html; frag.appendChild(tr);
  });
  body.appendChild(frag);
  el('empty').hidden = rows.length>0;
  const total=DS.players.filter(p=>p.season===seasonSel.value).length;
  el('count').innerHTML=`<b>${rows.length}</b> of ${total} players`;
  // "search resolved to one player" banner
  const q=el('q').value.trim().toLowerCase();
  const names=[...new Set(rows.map(r=>r.name))];
  const bn=el('banner');
  if(q && names.length===1){
    bn.hidden=false;
    bn.innerHTML=`Found <b>${esc(names[0])}</b>. `
      +`<button class="act" data-nm="${esc(names[0])}">📊 Compare years for ${esc(names[0])}</button>`;
    bn.querySelector('button').onclick=()=>openPlayer(names[0]);
  } else bn.hidden=true;
  body.querySelectorAll('button.cmp').forEach(b=> b.onclick=()=>openPlayer(b.dataset.nm));
}

// ============================ PLAYER VIEW ============================
function openPlayer(name){
  view.player=name;
  const rows=DS.players.filter(p=>p.name===name);
  view.years=new Set(rows.map(r=>r.season));   // all their years selected by default
  view.mode='each';
  render();
}
function closePlayer(){ view.player=null; render(); }

function wavg(rows,k){ // games-weighted per-game average; falls back to simple mean
  let sw=0,sv=0,n=0,sum=0;
  rows.forEach(r=>{ const v=r[k]; if(v===null||v===undefined) return; const g=r.g||0; n++; sum+=v; sw+=g; sv+=v*g; });
  if(sw>0) return sv/sw; return n? sum/n : null;
}
const PV_COLS=[
  {k:'yr',t:'Year',txt:true},{k:'team',t:'Team',txt:true},{k:'age',t:'Age'},
  {k:'g',t:'G'},{k:'mpg',t:'MPG',d:1},{k:'ppg',t:'PPG',d:1},{k:'rpg',t:'RPG',d:1},
  {k:'apg',t:'APG',d:1},{k:'spg',t:'SPG',d:1},{k:'bpg',t:'BPG',d:1},{k:'tpg',t:'TPG',d:1},
  {k:'fgp',t:'FG%',pct:true},{k:'ftp',t:'FT%',pct:true},{k:'tpp',t:'3P%',pct:true},
  {k:'awards',t:'Awards',txt:true},
];
function pvCell(p,c){
  if(c.k==='yr')   return yearNum(p.season)+(PLAYED[p.season]?'':' *');
  if(c.k==='team') return `<a href="${teamUrl(p)}"${recAttr(p)} target="_blank" rel="noopener">${esc(p.team)}</a>${champBadge(p)}`;
  if(c.k==='awards') return (p.awards&&p.awards.length)? p.awards.map(a=>`<span class="awd">${esc(a)}</span>`).join('') : '<span style="color:#c2c8d2">—</span>';
  if(c.money) return fmtMoney(p[c.k]);
  if(c.pct)   return fmtPct(p[c.k]);
  return fmtNum(p[c.k],c.d);
}
function abilSection(sel){
  if(!sel.length) return '';
  let h=`<div class="pv-sub" style="margin-top:20px;margin-bottom:8px">`
    +`<b>Ability grades over time</b> — In=Inside, Out=Outside, Hn=Handling, Df=Defense, Reb=Rebounding, Pot=Potential`
    +` <span style="color:#9aa4b2">(▲ up / ▼ down vs the prior selected year)</span></div>`;
  h+=`<div class="tablewrap"><table><thead><tr><th class="txt">Year</th>`;
  ABIL_KEYS.forEach(k=> h+=`<th title="${ABIL_FULL[k]}">${k}</th>`);
  h+=`</tr></thead><tbody>`;
  let prev=null;
  sel.forEach(p=>{                       // sel is year-sorted ascending
    h+=`<tr><td class="txt">${yearNum(p.season)}</td>`;
    ABIL_KEYS.forEach(k=>{
      const g=p.abil?p.abil[k]:null;
      if(!g){ h+=`<td>—</td>`; return; }
      let arrow='';
      if(prev&&prev.abil&&prev.abil[k]){
        const dv=gradeVal(g)-gradeVal(prev.abil[k]);
        if(dv>0) arrow=' <span class="delta up">▲</span>';
        else if(dv<0) arrow=' <span class="delta down">▼</span>';
      }
      h+=`<td>${g}${arrow}</td>`;
    });
    h+=`</tr>`; prev=p;
  });
  h+=`</tbody></table></div>`;
  return h;
}

function renderPlayer(){
  const name=view.player;
  const all=DS.players.filter(p=>p.name===name).sort((a,b)=>yearNum(a.season)-yearNum(b.season));
  const sel=all.filter(p=>view.years.has(p.season));
  const canCompare=sel.length===2;
  if(view.mode==='compare' && !canCompare) view.mode='each';

  const teams=[...new Set(all.map(p=>p.team))];
  const pv=el('playerview');
  let h=`<div class="pv-head"><h2>${esc(name)}</h2>
    <span class="pv-sub">${all.length} season${all.length>1?'s':''} · ${yearNum(all[0].season)}–${yearNum(all[all.length-1].season)} · ${teams.length} team${teams.length>1?'s':''}</span></div>
    <div class="pv-sub">Toggle years, then choose a view. <b>Average</b> is games-weighted across the selected years; <b>Compare</b> needs exactly two.</div>
    <div class="pv-controls"><span class="lbl">Years</span>`;
  all.forEach(p=>{ h+=`<button class="yr ${view.years.has(p.season)?'on':''}" data-yr="${p.season}">${yearNum(p.season)}</button>`; });
  h+=`<span class="modes">
      <button class="yr ${view.mode==='each'?'on':''}" data-mode="each">Each year</button>
      <button class="yr ${view.mode==='avg'?'on':''}" data-mode="avg">Average</button>
      <button class="yr ${view.mode==='compare'?'on':''}" data-mode="compare" ${canCompare?'':'disabled'}>Compare 2</button>
      <button class="act ghost" id="pvback">← All players</button>
    </span></div>`;

  h+=`<div class="tablewrap"><table><thead><tr>`;
  PV_COLS.forEach(c=> h+=`<th class="${c.txt?'txt':''}">${c.t}</th>`);
  h+=`</tr></thead><tbody>`;

  if(sel.length===0){
    h+=`<tr><td class="txt" colspan="${PV_COLS.length}" style="color:#8b95a3;padding:20px">Select at least one year above.</td></tr>`;
  } else if(view.mode==='avg'){
    h+=`<tr>`; PV_COLS.forEach(c=>{
      let v;
      if(c.k==='yr') v=`Avg (${sel.map(p=>yearNum(p.season)).join(', ')})`;
      else if(c.k==='team') v=teams.length>1?'Multiple':esc(teams[0]);
      else if(c.k==='age') v='—';
      else if(c.k==='awards') { const u=[...new Set(sel.flatMap(p=>p.awards.map(a=>`'${String(yearNum(p.season)).slice(-2)} ${a}`)))];
        v=u.length?u.map(a=>`<span class="awd">${esc(a)}</span>`).join(''):'<span style="color:#c2c8d2">—</span>'; }
      else if(c.k==='g') v=sel.reduce((n,p)=>n+(p.g||0),0);
      else { const a=wavg(sel,c.k); v=c.pct?fmtPct(a):fmtNum(a,c.d); }
      h+=`<td class="${c.txt?'txt':''}">${v}</td>`;
    }); h+=`</tr>`;
  } else if(view.mode==='compare'){
    const A=sel[0],B=sel[1];  // sel is year-sorted ascending
    [A,B].forEach(p=>{ h+=`<tr>`; PV_COLS.forEach(c=> h+=`<td class="${c.txt?'txt':''}">${pvCell(p,c)}</td>`); h+=`</tr>`; });
    h+=`<tr>`; PV_COLS.forEach(c=>{
      if(c.k==='yr'){ h+=`<td class="txt"><b>Δ ${yearNum(A.season)}→${yearNum(B.season)}</b></td>`; return; }
      if(c.txt||c.k==='age'){ h+=`<td class="${c.txt?'txt':''}"></td>`; return; }
      const a=A[c.k],b=B[c.k];
      if(a===null||a===undefined||b===null||b===undefined){ h+=`<td>—</td>`; return; }
      const d=b-a; const gd=GOOD_UP[c.k];            // undefined for neutral stats (G, MPG)
      const cls=(gd===undefined||d===0)?'':((gd*Math.sign(d))>0?'delta up':'delta down');
      const sign=d>0?'+':'';
      const txt=c.pct?(sign+(d*100).toFixed(1)+'%'):(sign+d.toFixed(c.d||0));
      h+=`<td class="${cls}">${txt}</td>`;
    }); h+=`</tr>`;
  } else { // each year
    sel.forEach(p=>{ h+=`<tr>`; PV_COLS.forEach(c=> h+=`<td class="${c.txt?'txt':''}">${pvCell(p,c)}</td>`); h+=`</tr>`; });
  }
  h+=`</tbody></table></div>`;
  h+=abilSection(sel);
  h+=xlSection(name);
  pv.innerHTML=h;

  pv.querySelectorAll('button[data-yr]').forEach(b=> b.onclick=()=>{
    const y=b.dataset.yr; if(view.years.has(y)) view.years.delete(y); else view.years.add(y); renderPlayer(); });
  pv.querySelectorAll('button[data-mode]').forEach(b=> b.onclick=()=>{ if(!b.disabled){ view.mode=b.dataset.mode; renderPlayer(); } });
  el('pvback').onclick=closePlayer;
}

// ============================ ROUTING ============================
function render(){
  const inPlayer=!!view.player;
  el('tableview').hidden=inPlayer;
  el('playerview').hidden=!inPlayer;
  el('count').style.visibility=inPlayer?'hidden':'visible';
  if(inPlayer) renderPlayer(); else renderTable();
}
function buildFacets(){
  const pool=DS.players.filter(p=>p.season===seasonSel.value);
  const teams=[...new Set(pool.map(p=>p.team))].sort();
  const poss=[...new Set(pool.map(p=>p.pos).filter(Boolean))].sort();
  const teamSel=el('team'),kt=teamSel.value;
  teamSel.innerHTML='<option value="">All teams</option>'+teams.map(t=>`<option>${esc(t)}</option>`).join('');
  if([...teamSel.options].some(o=>o.value===kt)) teamSel.value=kt;
  const posSel=el('pos'),kp=posSel.value;
  posSel.innerHTML='<option value="">All</option>'+poss.map(p=>`<option>${esc(p)}</option>`).join('');
  if([...posSel.options].some(o=>o.value===kp)) posSel.value=kp;
}
seasonSel.onchange=()=>{ buildFacets(); render(); };
el('mpg').onchange=render; el('team').onchange=render; el('pos').onchange=render;
el('rec').onchange=render; el('ctr').onchange=render; el('q').oninput=render;
// Status filter only appears when the dataset carries free-agent flags.
// FAs have no current-season roster rows, so engaging the filter jumps to the
// newest season that actually contains them (their last played season).
if(DS.players.some(p=>p.fa)){
  el('faFld').hidden=false;
  el('fa').onchange=()=>{
    if(el('fa').value && !DS.players.some(p=>p.season===seasonSel.value&&p.fa)){
      const best=DS.seasons.find(s=>DS.players.some(p=>p.season===s.key&&p.fa));
      if(best){ seasonSel.value=best.key; buildFacets(); }
    }
    render();
  };
}
el('home').onclick=()=>{ closePlayer(); };

// --- Basic / Advanced view toggle ---
const LEGEND_BASIC = el('legendNote').textContent;
const LEGEND_ADV = '· TO36 = fewest (20+ MPG) · per-36 & ratio leaders need 15+ MPG'
  + (HAS_SH ? '; TS/eFG need 10+ MPG' : '')
  + ' · hover a column header for its definition'
  + (HAS_SH ? '' : ' · TS%/eFG% need shot attempts, which the league only publishes for SLN');
function setMode(m){
  if(MODE===m) return;
  MODE=m;
  el('mBasic').classList.toggle('on', m==='basic');
  el('mAdv').classList.toggle('on', m==='adv');
  el('legendNote').textContent = m==='adv' ? LEGEND_ADV : LEGEND_BASIC;
  if(!cols().some(c=>c.k===sortKey)){ sortKey = m==='adv' ? 'p36' : 'ppg'; sortDir=-1; }
  render();
}
el('mBasic').onclick=()=>setMode('basic');
el('mAdv').onclick=()=>setMode('adv');

// --- optional on-demand "Refresh now" button (via Cloudflare Worker relay) ---
const WORKER_URL="__WORKER_URL__";
(function(){
  const btn=el('refreshBtn'), msg=el('refreshMsg');
  if(!WORKER_URL){ return; }              // no worker configured -> button stays hidden
  btn.hidden=false;
  const builtNow=(document.getElementById('buildstamp')||{}).textContent||'';
  function waitForNewBuild(){          // reload exactly when the new build is live
    let tries=0;
    const iv=setInterval(async()=>{
      tries++;
      try{
        const t=await (await fetch(location.pathname+'?_='+Date.now(),{cache:'no-store'})).text();
        const m=t.match(/id="buildstamp">(.*?)<\/b>/);
        if(m&&m[1]&&m[1]!==builtNow){ clearInterval(iv); location.reload(); return; }
      }catch(e){}
      if(tries>=25){ clearInterval(iv); msg.innerHTML=' ✅ still building — reload in a moment to see the latest.'; }
    },20000);
  }
  btn.onclick=async()=>{
    btn.disabled=true; msg.textContent=' contacting…';
    try{
      const r=await fetch(WORKER_URL,{method:'POST'});
      const j=await r.json().catch(()=>({}));
      if(j.status==='triggered'||j.status==='already_refreshing'){
        msg.innerHTML=' ✅ refreshing… the page updates automatically when the new build is live (usually 1–3 min).';
        waitForNewBuild();
      } else { msg.textContent=' ⚠️ could not start a refresh (try again shortly).'; btn.disabled=false; }
    }catch(e){ msg.textContent=' ⚠️ refresh request failed (try again shortly).'; btn.disabled=false; }
  };
})();

buildFacets(); render();
</script>
</body>
</html>
"""

out = (HTML.replace("__DATA__", DATA_JS)
           .replace("__BUILT__", BUILT)
           .replace("__WORKER_URL__", WORKER_URL)
           .replace("__FAVICON__", FAVICON)
           .replace("__LOGO__", LOGO_INLINE)
           .replace("__LEAGUE__", CFG["name"])
           .replace("__SRC_SITE__", CFG["site"])
           .replace("__SWITCH_CSS__", branding.SWITCH_CSS)
           .replace("__GUIDE__", branding.GUIDE_LINK)
           .replace("__SWITCHER__", branding.switcher(CFG["name"])))
path = f"{ROOT}/out/{CFG['out']}"
with open(path, "w") as fh:
    fh.write(out)
print(f"wrote {path} ({os.path.getsize(path):,} bytes)")
