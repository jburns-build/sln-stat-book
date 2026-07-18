#!/usr/bin/env python3
"""Generate the Team Records page (per-franchise player leaders).

Computed entirely from the roster data already in out/players_dataset.json — no
scraping — so it costs nothing on a refresh. Franchises are identified by their
stable roster number (rn), which follows a team through renames/relocations
(e.g. rn 3 = the Nets whether "New Jersey Nets" or "Brooklyn Ballers"); the
canonical name is the team's current (2038) name.

Two boards per team:
  - Franchise leaders : top 5 by TOTAL amassed while on the team (career-with-team)
  - Best single season: top 5 single-season totals for the team (with the year)

Counting totals are derived from per-game averages (Points = PPG*Games, etc.),
so they carry ~0.1% rounding; Games is exact. Output: out/teams.html -> /teams/.
"""
import json, os, sys, datetime
from collections import defaultdict
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import branding
from branding import FAVICON, LOGO_INLINE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
players = json.load(open(f"{ROOT}/out/players_dataset.json"))["players"]
BUILT = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%b %d, %Y · %-I:%M %p %Z")
_wu = f"{ROOT}/worker_url.txt"
WORKER_URL = open(_wu).read().strip() if os.path.exists(_wu) else ""

PRE = {"96": 1996, "97": 1997, "99": 1999}
def yr(sc): return 2038 if sc == "current" else PRE.get(sc, 2000 + int(sc))

# counting categories (all derived from per-game averages except games)
CUM_CATS = [("g", "Games"), ("pts", "Points"), ("reb", "Rebounds"),
            ("ast", "Assists"), ("stl", "Steals"), ("blk", "Blocks")]
SSN_CATS = [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
            ("stl", "Steals"), ("blk", "Blocks")]
SRC = {"pts": "ppg", "reb": "rpg", "ast": "apg", "stl": "spg", "blk": "bpg"}

active_names = {p["name"] for p in players if p["season"] == "current"}
name_by_rn = {p["rn"]: p["team"] for p in players if p["season"] == "current"}
# any franchise not in the current season -> most recent name
for p in sorted(players, key=lambda p: yr(p["season"])):
    name_by_rn.setdefault(p["rn"], p["team"])

# per (rn, name): career-with-team totals + latest stint for linking
cum = defaultdict(lambda: {"g": 0.0, "pts": 0.0, "reb": 0.0, "ast": 0.0,
                           "stl": 0.0, "blk": 0.0, "y": -1, "key": ""})
# per rn: every (player, season) line, for single-season bests
ssn = defaultdict(list)
for p in players:
    g = p["g"] or 0
    if not g:
        continue
    rn = p["rn"]
    row = {"pts": (p["ppg"] or 0) * g, "reb": (p["rpg"] or 0) * g,
           "ast": (p["apg"] or 0) * g, "stl": (p["spg"] or 0) * g,
           "blk": (p["bpg"] or 0) * g}
    c = cum[(rn, p["name"])]
    c["g"] += g
    for k in ("pts", "reb", "ast", "stl", "blk"):
        c[k] += row[k]
    if yr(p["season"]) >= c["y"]:
        c["y"], c["key"] = yr(p["season"]), f"{p['season']}:{p['id']}"
    ssn[rn].append({"name": p["name"], "year": yr(p["season"]),
                    "key": f"{p['season']}:{p['id']}", **row})

def top5(rows, k, valfn):
    rows = [r for r in rows if valfn(r, k) > 0]
    rows.sort(key=lambda r: -valfn(r, k))
    return rows[:5]

teams = []
for rn in sorted(name_by_rn, key=lambda r: name_by_rn[r]):
    people = [(nm, c) for (r, nm), c in cum.items() if r == rn]
    cum_board = {}
    for k, _ in CUM_CATS:
        rows = top5([{"name": nm, **c} for nm, c in people], k, lambda r, k: r[k])
        cum_board[k] = [[r["name"], round(r[k]), r["name"] in active_names, r["key"]] for r in rows]
    ssn_board = {}
    for k, _ in SSN_CATS:
        rows = top5(ssn[rn], k, lambda r, k: r[k])
        ssn_board[k] = [[r["name"], round(r[k]), r["year"], r["key"]] for r in rows]
    teams.append({"rn": rn, "name": name_by_rn[rn], "cum": cum_board, "ssn": ssn_board})

DATA = {"teams": teams,
        "cumCats": [[k, t] for k, t in CUM_CATS],
        "ssnCats": [[k, t] for k, t in SSN_CATS]}
DATA_JS = json.dumps(DATA, separators=(",", ":"))

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,__FAVICON__">
<title>SLN Team Records</title>
<style>
  :root{
    --bg:#f4f5f7; --panel:#ffffff; --ink:#141821; --muted:#5b6472;
    --line:#e2e6ec; --line2:#eef1f5; --link:#1257c9; --accent:#0b5cff;
    --zebra:#fafbfc; --headbg:#151a24; --headink:#f4f6fa; --gold:#ffd869; --live:#12a150; }
  *{box-sizing:border-box}
  [hidden]{display:none!important}
  body{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
  a{color:var(--link);text-decoration:none} a:hover{text-decoration:underline}
  header.top{background:var(--headbg);color:var(--headink);padding:14px 20px;
    display:flex;align-items:center;gap:14px;flex-wrap:wrap;border-bottom:3px solid var(--accent);}
  header.top .logo{font-size:20px;font-weight:800;letter-spacing:.3px;display:flex;align-items:center;gap:8px}
  header.top .logo .b{color:#ffcf3f}
__SWITCH_CSS__
  .wrap{max-width:1560px;margin:0 auto;padding:18px 20px 60px}
  .bar{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    padding:14px 16px;display:flex;gap:18px;flex-wrap:wrap;align-items:flex-end;
    box-shadow:0 1px 2px rgba(20,24,33,.04);margin-bottom:14px}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld label{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--muted)}
  select{font:inherit;padding:8px 11px;border:1px solid var(--line);border-radius:7px;
    background:#fff;color:var(--ink);min-width:230px;font-weight:600}
  select:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:var(--accent)}
  .note{margin-left:auto;align-self:center;color:var(--muted);font-size:12px;max-width:520px;text-align:right}
  .sect{font-size:15px;letter-spacing:.4px;text-transform:uppercase;color:var(--muted);
    margin:22px 2px 10px;display:flex;align-items:baseline;gap:10px}
  .sect:first-of-type{margin-top:4px}
  .sect span{font-size:12px;text-transform:none;letter-spacing:0;color:#93a0b4;font-weight:400}
  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    box-shadow:0 1px 2px rgba(20,24,33,.04);overflow:hidden}
  .card h3{margin:0;padding:10px 14px;background:var(--headbg);color:var(--headink);
    font-size:13px;letter-spacing:.5px;text-transform:uppercase;border-bottom:2px solid var(--accent)}
  .row{display:flex;align-items:center;gap:8px;padding:6px 14px;border-bottom:1px solid var(--line2);
    font-variant-numeric:tabular-nums}
  .row:last-child{border-bottom:none}
  .row:nth-child(even){background:var(--zebra)}
  .row.rk1{background:var(--gold)}
  .row .n{width:20px;color:var(--muted);font-size:12px;text-align:right}
  .row.rk1 .n{color:#6b5300;font-weight:800}
  .row .nm{flex:1;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .row .nm a{color:var(--ink)}
  .row .era{color:var(--muted);font-weight:400;font-size:11px;margin-left:5px}
  .row .v{font-weight:700;white-space:nowrap}
  .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--live);
    margin-left:5px;vertical-align:1px}
  .empty{color:#8b95a3;font-weight:400}
  .foot{margin-top:16px;color:var(--muted);font-size:12px;text-align:center}
  button.refresh{font:inherit;font-size:12px;font-weight:600;padding:3px 9px;border:1px solid var(--accent);
    background:var(--accent);color:#fff;border-radius:6px;cursor:pointer}
  button.refresh:disabled{opacity:.5;cursor:default}
  @media (max-width:640px){ .note{margin-left:0;text-align:left;width:100%} }
</style>
</head>
<body>
<header class="top">
  <div class="logo">__LOGO__ <span>SLN <span class="b">Team Records</span></span></div>
  <nav>__SWITCHER__</nav>
</header>
<div class="wrap">
  <div class="bar">
    <div class="fld"><label for="team">Franchise</label><select id="team"></select></div>
    <div class="note">Top 5 per category · players link to their SLN page · <span class="dot"></span> = still active in 2038.<br>
      Counting totals are derived from per-game averages (Points = PPG×Games…), so they carry ~0.1%; Games is exact.</div>
  </div>
  <h2 class="sect">Franchise leaders <span>most amassed while on the team (all seasons)</span></h2>
  <div class="cards" id="cum"></div>
  <h2 class="sect">Best single season <span>top individual seasons for the team</span></h2>
  <div class="cards" id="ssn"></div>
  <div class="foot">SLN Team Records — computed from 42 seasons of roster data.<br>
    <span style="opacity:.85">Data updated <b>__BUILT__</b> · auto-refreshes every 4 hours ·
    <button id="refreshBtn" class="refresh" hidden>🔄 Refresh now</button>
    <a href="#" onclick="location.reload();return false;">reload</a>
    <span id="refreshMsg" style="margin-left:6px"></span></span></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const DS=JSON.parse(document.getElementById('data').textContent);
const SITE='https://www.simleaguenirvana.com';
const el=(id)=>document.getElementById(id);
const esc=(s)=>(s+'').replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const fmt=(v)=>Math.round(v).toLocaleString();
function playerUrl(key){const [season,id]=(key||'').split(':'); if(!id)return null;
  return season==='current'?`${SITE}/players/player${id}.htm`:`${SITE}/history/${season}/players/player${id}.htm`;}
function nameCell(name,key,extraActive,eraHtml){
  const url=playerUrl(key);
  const nm=url?`<a href="${url}" target="_blank" rel="noopener">${esc(name)}</a>`:esc(name);
  return `<span class="nm">${nm}${extraActive?'<span class="dot" title="Active in 2038"></span>':''}${eraHtml||''}</span>`;
}

// team dropdown
const sel=el('team');
DS.teams.forEach((t,i)=>{const o=document.createElement('option');o.value=i;o.textContent=t.name;sel.appendChild(o);});

function render(){
  const t=DS.teams[+sel.value];
  const cum=el('cum'); cum.innerHTML='';
  DS.cumCats.forEach(([k,title])=>{
    const rows=t.cum[k]||[];
    let h=`<div class="card"><h3>${title}</h3>`;
    rows.forEach((r,i)=>{ // r = [name, val, active, key]
      h+=`<div class="row${i===0?' rk1':''}"><span class="n">${i+1}</span>`
       + nameCell(r[0],r[3],r[2],'') + `<span class="v">${fmt(r[1])}</span></div>`;
    });
    if(!rows.length) h+=`<div class="row"><span class="nm empty">No data</span></div>`;
    cum.insertAdjacentHTML('beforeend',h+`</div>`);
  });
  const ssn=el('ssn'); ssn.innerHTML='';
  DS.ssnCats.forEach(([k,title])=>{
    const rows=t.ssn[k]||[];
    let h=`<div class="card"><h3>${title}</h3>`;
    rows.forEach((r,i)=>{ // r = [name, val, year, key]
      h+=`<div class="row${i===0?' rk1':''}"><span class="n">${i+1}</span>`
       + nameCell(r[0],r[3],false,`<span class="era">${r[2]}</span>`) + `<span class="v">${fmt(r[1])}</span></div>`;
    });
    if(!rows.length) h+=`<div class="row"><span class="nm empty">No data</span></div>`;
    ssn.insertAdjacentHTML('beforeend',h+`</div>`);
  });
}
sel.onchange=render;
render();

// on-demand rebuild (shared Cloudflare Worker relay), polls for the new build
const WORKER_URL="__WORKER_URL__";
(function(){
  const btn=el('refreshBtn'), msg=el('refreshMsg');
  if(!WORKER_URL) return;
  btn.hidden=false;
  const builtNow=(document.querySelector('.foot b')||{}).textContent||'';
  function waitForNewBuild(){
    let tries=0;
    const iv=setInterval(async()=>{
      tries++;
      try{
        const t=await (await fetch(location.pathname+'?_='+Date.now(),{cache:'no-store'})).text();
        const m=t.match(/Data updated <b>(.*?)<\/b>/);
        if(m&&m[1]&&m[1]!==builtNow){ clearInterval(iv); location.reload(); return; }
      }catch(e){}
      if(tries>=25){ clearInterval(iv); msg.innerHTML=' ✅ still building — reload in a moment.'; }
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
</script>
</body>
</html>
"""

out = (HTML.replace("__DATA__", DATA_JS)
           .replace("__BUILT__", BUILT)
           .replace("__WORKER_URL__", WORKER_URL)
           .replace("__FAVICON__", FAVICON)
           .replace("__LOGO__", LOGO_INLINE)
           .replace("__SWITCH_CSS__", branding.SWITCH_CSS)
           .replace("__SWITCHER__", branding.switcher("Teams")))
path = f"{ROOT}/out/teams.html"
with open(path, "w") as fh:
    fh.write(out)
print(f"wrote {path} ({os.path.getsize(path):,} bytes)  {len(teams)} franchises")
