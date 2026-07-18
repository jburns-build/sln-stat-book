#!/usr/bin/env python3
"""Generate the career Records page from out/careers_dataset.json.

The league's own Player Career Records page shows only the single leader in
each category; this shows the top 10, in both all-time and active-only views,
and marks which all-time leaders are still active.

Output: out/records.html  ->  published at /records/
"""
import json, os, sys, datetime
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import branding
from branding import FAVICON, LOGO_INLINE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ds = json.load(open(f"{ROOT}/out/careers_dataset.json"))

# Career award counts come from the per-season award pages already mirrored for
# the stat book — no extra scraping. Awards are attributed to a real player by
# segmenting each NAME into careers on year-continuity: a run of >=3 missing real
# seasons splits it into different players reusing the name (e.g. the two "LeBron
# James"), while ID changes mid-career (e.g. Hakeem, id 9 -> 484) stay one career.
# Verified against players' own award boxes (Luka: 7 MVP, 16 All-League 1st).
AWARD_KEYS = ["MVP", "DPOY", "6th Man", "All-League 1st", "All-Defensive 1st"]
PRE = {"96": 1996, "97": 1997, "99": 1999}
def _yr(sc): return 2038 if sc == "current" else PRE.get(sc, 2000 + int(sc))

_pl = json.load(open(f"{ROOT}/out/players_dataset.json"))["players"]
_YEARS = sorted({_yr(p["season"]) for p in _pl})
_IDX = {y: i for i, y in enumerate(_YEARS)}      # real-season ordinal (no 1998)
_byname = defaultdict(list)
for p in _pl:
    _byname[p["name"]].append(
        {"y": _yr(p["season"]), "key": f"{p['season']}:{p['id']}", "pos": p["pos"],
         "active": p["season"] == "current", "aw": p.get("awards") or []})

# All-Star appearances (from the box scores), attributed by (name, year) to the
# matching career segment — same bundling as everything else.
_allstar = json.load(open(f"{ROOT}/out/allstar.json"))["appearances"]
_asy = defaultdict(list)
for nm, y in _allstar:
    _asy[nm].append(y)

award_players = []
for name, stints in _byname.items():
    stints.sort(key=lambda s: s["y"])
    segs = [[stints[0]]]
    for st in stints[1:]:                        # split on a gap of >=3 real seasons
        if _IDX[st["y"]] - _IDX[segs[-1][-1]["y"]] >= 3:
            segs.append([st])
        else:
            segs[-1].append(st)
    for seg in segs:
        aw = Counter(a for st in seg for a in st["aw"])
        counts = {k: aw[k] for k in AWARD_KEYS if aw[k]}
        lo, hi = min(st["y"] for st in seg), max(st["y"] for st in seg)
        allstar = sum(1 for y in _asy.get(name, []) if lo <= y <= hi)
        if not counts and not allstar:
            continue
        last = max(seg, key=lambda st: st["y"])
        rec = {"name": name, "aw": counts, "as": allstar,
               "first": lo, "last": last["y"],
               "active": any(st["active"] for st in seg),
               "key": last["key"], "pos": last["pos"]}
        award_players.append(rec)
ds["awardPlayers"] = award_players

FETCHED = ds.get("fetched", "unknown")   # when career totals were last actually pulled
DATA_JS = json.dumps(ds, separators=(",", ":"))
BUILT = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%b %d, %Y · %-I:%M %p %Z")
_wu = f"{ROOT}/worker_url.txt"
WORKER_URL = open(_wu).read().strip() if os.path.exists(_wu) else ""

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,__FAVICON__">
<title>SLN Career Records</title>
<style>
  :root{
    --bg:#f4f5f7; --panel:#ffffff; --ink:#141821; --muted:#5b6472;
    --line:#e2e6ec; --line2:#eef1f5; --link:#1257c9; --accent:#0b5cff;
    --hi:#fff6d6; --zebra:#fafbfc; --headbg:#151a24; --headink:#f4f6fa;
    --gold:#ffd869; --live:#12a150; }
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
  input[type=search]{font:inherit;padding:7px 10px;border:1px solid var(--line);
    border-radius:7px;background:#fff;color:var(--ink);min-width:220px}
  input:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:var(--accent)}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .seg button{font:inherit;font-weight:700;font-size:13px;padding:7px 15px;border:none;
    background:#fff;color:var(--muted);cursor:pointer}
  .seg button.on{background:var(--accent);color:#fff}
  .note{margin-left:auto;align-self:center;color:var(--muted);font-size:12px;max-width:520px;text-align:right}
  .sect{font-size:15px;letter-spacing:.4px;text-transform:uppercase;color:var(--muted);
    margin:22px 2px 10px;display:flex;align-items:baseline;gap:10px}
  .sect:first-of-type{margin-top:4px}
  .sect span{font-size:12px;text-transform:none;letter-spacing:0;color:#93a0b4;font-weight:400}
  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(370px,1fr));gap:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
    box-shadow:0 1px 2px rgba(20,24,33,.04);overflow:hidden}
  .card h3{margin:0;padding:10px 14px;background:var(--headbg);color:var(--headink);
    font-size:13px;letter-spacing:.5px;text-transform:uppercase;
    display:flex;align-items:center;gap:8px;border-bottom:2px solid var(--accent)}
  .card h3 .approx{margin-left:auto;font-size:10px;font-weight:600;letter-spacing:0;
    text-transform:none;color:#93a0b4;cursor:help}
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
  .hit{box-shadow:inset 3px 0 0 var(--accent)}
  .foot{margin-top:16px;color:var(--muted);font-size:12px;text-align:center}
  button.refresh{font:inherit;font-size:12px;font-weight:600;padding:3px 9px;border:1px solid var(--accent);
    background:var(--accent);color:#fff;border-radius:6px;cursor:pointer}
  button.refresh:disabled{opacity:.5;cursor:default}
  @media (max-width:640px){ .note{margin-left:0;text-align:left;width:100%} }
</style>
</head>
<body>
<header class="top">
  <div class="logo">__LOGO__ <span>SLN <span class="b">Career Records</span></span></div>
  <nav>__SWITCHER__</nav>
</header>
<div class="wrap">
  <div class="bar">
    <div class="fld"><label>Show</label>
      <span class="seg">
        <button id="m-all" class="on">All-time top 10</button><button id="m-act">Active top 10</button>
      </span></div>
    <div class="fld"><label for="q">Find a player</label>
      <input id="q" type="search" placeholder="highlight a name…" autocomplete="off"></div>
    <div class="note" id="note"></div>
  </div>
  <h2 class="sect">Career totals <span>top 10 per category</span></h2>
  <div class="cards" id="cards"></div>
  <h2 class="sect">Awards &amp; honors <span>top 5 each</span></h2>
  <div class="cards" id="awards"></div>
  <div class="foot">SLN Career Records — top 10 per category across all 42 seasons (1996–2038).
    <span class="dot"></span> = still active in 2038.<br>
    <b>Career totals last pulled __FETCHED__</b> (refreshed once a day); awards &amp; All-Star update on every refresh.<br>
    <span style="opacity:.85">Page rebuilt <b id="buildstamp">__BUILT__</b> · auto-refreshes every 4 hours ·
    <button id="refreshBtn" class="refresh" hidden>🔄 Refresh now</button>
    <a href="#" onclick="location.reload();return false;">reload</a>
    <span id="refreshMsg" style="margin-left:6px"></span></span></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const DS = JSON.parse(document.getElementById('data').textContent);
const SITE='https://www.simleaguenirvana.com';
const el=(id)=>document.getElementById(id);
const C = DS.careers;

// Same categories the league's own Career Records page lists a single leader for.
// exact:false -> derived from published per-game averages (~0.1% rounding).
const CATS=[
  {k:'games', t:'Games',          exact:true},
  {k:'pts',   t:'Points',         exact:true},
  {k:'reb',   t:'Rebounds',       exact:false},
  {k:'ast',   t:'Assists',        exact:false},
  {k:'stl',   t:'Steals',         exact:false},
  {k:'blk',   t:'Blocks',         exact:false},
  {k:'tov',   t:'Turnovers',      exact:false},
  {k:'fg',    t:'Field Goals',    exact:true},
  {k:'ft',    t:'Free Throws',    exact:true},
  {k:'tp',    t:'3 Pointers',     exact:true},
  {k:'dd',    t:'Double Doubles', exact:true},
  {k:'td',    t:'Triple Doubles', exact:true},
];
// Career award counts — the five you care about.
const AWARD_CATS=[
  {k:'MVP',              t:'MVP'},
  {k:'DPOY',             t:'Defensive Player of the Year'},
  {k:'6th Man',          t:'Sixth Man of the Year'},
  {k:'All-League 1st',   t:'All-League First Team'},
  {k:'All-Defensive 1st',t:'All-Defensive First Team'},
];
let mode='all';

function playerUrl(p){
  const [season,id]=(p.key||'').split(':');
  if(!id) return null;
  return season==='current' ? `${SITE}/players/player${id}.htm`
                            : `${SITE}/history/${season}/players/player${id}.htm`;
}
const esc=(s)=>(s+'').replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const fmt=(v)=>Math.round(v).toLocaleString();

function topN(get,n){
  const pool = mode==='active' ? C.filter(p=>p.active) : C;
  return pool.filter(p=>get(p)>0).sort((a,b)=>get(b)-get(a)).slice(0,n);
}
const topTen=(k)=>topN(p=>p[k]||0,10);
const AP = DS.awardPlayers||[];
function topAward(k){
  const pool = mode==='active' ? AP.filter(p=>p.active) : AP;
  return pool.filter(p=>(p.aw&&p.aw[k])||0).sort((a,b)=>(b.aw[k]||0)-(a.aw[k]||0)).slice(0,5);
}

function rowHtml(p,i,val,q){
  const url=playerUrl(p);
  const nm=url?`<a href="${url}" target="_blank" rel="noopener">${esc(p.name)}</a>`:esc(p.name);
  const hit=q && p.name.toLowerCase().includes(q) ? ' hit' : '';
  return `<div class="row${i===0?' rk1':''}${hit}" title="${esc(p.pos||'')} · ${p.first}–${p.last} · ${p.seasons} seasons">`
   + `<span class="n">${i+1}</span>`
   + `<span class="nm">${nm}${p.active?'<span class="dot" title="Active in 2038"></span>':''}`
   + `<span class="era">'${String(p.first).slice(-2)}–'${String(p.last).slice(-2)}</span></span>`
   + `<span class="v">${val}</span></div>`;
}

function renderAwards(q){
  const box=el('awards'); box.innerHTML='';
  // All-Star appearances lead the honors, then the five awards.
  const pool = mode==='active' ? AP.filter(p=>p.active) : AP;
  const asRows = pool.filter(p=>(p.as||0)).sort((a,b)=>(b.as||0)-(a.as||0)).slice(0,5);
  let ah=`<div class="card"><h3>All-Star Selections`
    +`<span class="approx" title="From the per-season All-Star box scores. The site archives boxes for 1999 and 2001–2037; the 1996, 1997, 2000 and 2005 games aren't archived, so a few players from those years are slightly undercounted.">boxes 1999–2037</span></h3>`;
  asRows.forEach((p,i)=> ah+=rowHtml(p,i,(p.as||0)+'×',q));
  box.insertAdjacentHTML('beforeend',ah+`</div>`);
  AWARD_CATS.forEach(c=>{
    const rows=topAward(c.k);
    let h=`<div class="card"><h3>${c.t}</h3>`;
    rows.forEach((p,i)=> h+=rowHtml(p,i,((p.aw&&p.aw[c.k])||0)+'×',q));
    if(!rows.length) h+=`<div class="row"><span class="nm" style="color:#8b95a3;font-weight:400">No winners yet</span></div>`;
    box.insertAdjacentHTML('beforeend',h+`</div>`);
  });
}

function render(){
  const q=el('q').value.trim().toLowerCase();
  const cards=el('cards'); cards.innerHTML='';
  CATS.forEach(c=>{
    const rows=topTen(c.k);
    let h=`<div class="card"><h3>${c.t}`
      + (c.exact?'':`<span class="approx" title="Rebounds, assists, steals, blocks and turnovers are only published as per-game averages, so career totals are derived (±0.1%). Games, points, FG, FT, 3P and double/triple doubles are exact.">≈ derived</span>`)
      + `</h3>`;
    rows.forEach((p,i)=> h+=rowHtml(p,i,fmt(p[c.k]||0),q));
    if(!rows.length) h+=`<div class="row"><span class="nm" style="color:#8b95a3;font-weight:400">No data</span></div>`;
    h+=`</div>`;
    cards.insertAdjacentHTML('beforeend',h);
  });
  renderAwards(q);
  const act=C.filter(p=>p.active).length;
  el('note').innerHTML = mode==='active'
    ? `Showing the best careers among the <b>${act}</b> players active in 2038.`
    : `All-time across <b>${C.length.toLocaleString()}</b> players in league history · <span class="dot"></span> = active in 2038.`;
}
el('m-all').onclick=()=>{ mode='all'; el('m-all').classList.add('on'); el('m-act').classList.remove('on'); render(); };
el('m-act').onclick=()=>{ mode='active'; el('m-act').classList.add('on'); el('m-all').classList.remove('on'); render(); };
el('q').oninput=render;

// on-demand rebuild (same Cloudflare Worker relay as the other pages)
const WORKER_URL="__WORKER_URL__";
(function(){
  const btn=el('refreshBtn'), msg=el('refreshMsg');
  if(!WORKER_URL) return;
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

render();
</script>
</body>
</html>
"""

out = (HTML.replace("__DATA__", DATA_JS)
           .replace("__BUILT__", BUILT)
           .replace("__FETCHED__", FETCHED)
           .replace("__WORKER_URL__", WORKER_URL)
           .replace("__FAVICON__", FAVICON)
           .replace("__LOGO__", LOGO_INLINE)
           .replace("__SWITCH_CSS__", branding.SWITCH_CSS)
           .replace("__SWITCHER__", branding.switcher("Records")))
path = f"{ROOT}/out/records.html"
with open(path, "w") as fh:
    fh.write(out)
print(f"wrote {path} ({os.path.getsize(path):,} bytes)")
