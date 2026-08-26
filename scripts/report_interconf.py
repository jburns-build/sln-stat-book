#!/usr/bin/env python3
"""Inter-conference records report -> out/interconf.html (+ console summary).

Reads data/games.json (scrape_games.py). Conference = franchise roster number:
East rn1-15, West rn16-29. Regular season only. Four views:
  1. per-team, per-season record vs the other conference (year picker)
  2. season head-to-head totals (East wins - West wins per season)
  3. per-team all-time vs the other conference
  4. all-time East vs West
Validation: every season's inter-conference game count must equal
|E_teams| x |W_teams| x 2 (each pair meets twice) or the season is flagged.
"""
import json, os, sys, datetime
from collections import defaultdict
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE = {"96": 1996, "97": 1997, "99": 1999}
def yr(c): return 2039 if c == "current" else PRE.get(c, 2000 + int(c))
EAST = set(range(1, 16))

games = json.load(open(f"{ROOT}/data/games.json"))["seasons"]
pl = json.load(open(f"{ROOT}/out/players_dataset.json"))["players"]

# franchise names: per-season and latest
name_season = {}
latest = {}
for p in pl:
    name_season[(p["season"], p["rn"])] = p["team"]
for p in sorted(pl, key=lambda p: yr(p["season"])):
    latest[p["rn"]] = p["team"]

team_season = defaultdict(lambda: [0, 0])   # (code, rn) -> [W, L] vs other conf
season_tot = {}                             # code -> [E wins, W wins]
flags = []
for code, s in sorted(games.items(), key=lambda kv: yr(kv[0])):
    if not s["games"]:
        continue
    rns = {r for g in s["games"] for r in (g[0], g[2])}
    e, w = rns & EAST, rns - EAST
    inter = 0
    ew = [0, 0]
    for a, sa, b, sb in s["games"]:
        if (a in EAST) == (b in EAST):
            continue
        inter += 1
        win, lose = (a, b) if sa > sb else (b, a)
        team_season[(code, win)][0] += 1
        team_season[(code, lose)][1] += 1
        ew[0 if win in EAST else 1] += 1
    season_tot[code] = ew
    expect = len(e) * len(w) * 2
    if s.get("complete") and inter != expect:
        flags.append(f"s{code}: {inter} inter-conf games, expected {expect}")

for f in flags:
    print("!!", f)

# all-time
team_all = defaultdict(lambda: [0, 0])
for (code, rn), (w, l) in team_season.items():
    team_all[rn][0] += w
    team_all[rn][1] += l
E_all = [sum(season_tot[c][0] for c in season_tot), sum(season_tot[c][1] for c in season_tot)]

print(f"\nALL-TIME: East {E_all[0]:,} — West {E_all[1]:,} "
      f"({100*E_all[0]/max(sum(E_all),1):.1f}% East) across {sum(E_all):,} games, {len(season_tot)} seasons")
east_seasons = sum(1 for c in season_tot if season_tot[c][0] > season_tot[c][1])
print(f"seasons won: East {east_seasons}, West {sum(1 for c in season_tot if season_tot[c][1] > season_tot[c][0])}, "
      f"ties {sum(1 for c in season_tot if season_tot[c][0] == season_tot[c][1])}")
best = sorted(team_all.items(), key=lambda kv: -(kv[1][0]/max(sum(kv[1]),1)))
print("\nbest all-time vs other conference:")
for rn, (w, l) in best[:5]:
    print(f"  {latest[rn]:26} {w}-{l}  ({100*w/(w+l):.1f}%)")
print("worst:")
for rn, (w, l) in best[-3:]:
    print(f"  {latest[rn]:26} {w}-{l}  ({100*w/(w+l):.1f}%)")

# ---------- HTML ----------
BUILT = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%b %d, %Y")
codes = sorted(season_tot, key=yr)
DATA = {
    "seasons": [{"code": c, "year": yr(c), "e": season_tot[c][0], "w": season_tot[c][1],
                 "final": bool(games[c].get("complete"))} for c in codes],
    "teams": sorted(
        [{"rn": rn, "name": latest[rn], "conf": "East" if rn in EAST else "West",
          "w": wl[0], "l": wl[1]} for rn, wl in team_all.items()],
        key=lambda t: -(t["w"] / max(t["w"] + t["l"], 1))),
    "detail": {c: sorted(
        [{"rn": rn, "name": name_season.get((c, rn), latest[rn]),
          "conf": "East" if rn in EAST else "West", "w": wl[0], "l": wl[1]}
         for (cc, rn), wl in team_season.items() if cc == c],
        key=lambda t: -(t["w"] / max(t["w"] + t["l"], 1))) for c in codes},
}
HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>East vs West — SLN Inter-Conference Records</title>
<style>
.viz-root{color-scheme:light;
 --surface-1:#fcfcfb;--surface-2:#f2f1ec;--text-primary:#0b0b0b;--text-secondary:#52514e;
 --line:#dcdbd4;--east:#2a78d6;--west:#eb6834;--gold:#fff3cf}
@media (prefers-color-scheme: dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;
 --surface-1:#1a1a19;--surface-2:#232322;--text-primary:#fff;--text-secondary:#c3c2b7;
 --line:#3a3936;--east:#3987e5;--west:#d95926;--gold:#3a3320}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;
 --surface-1:#1a1a19;--surface-2:#232322;--text-primary:#fff;--text-secondary:#c3c2b7;
 --line:#3a3936;--east:#3987e5;--west:#d95926;--gold:#3a3320}
*{box-sizing:border-box}
body{margin:0}
.viz-root{background:var(--surface-1);color:var(--text-primary);min-height:100vh;
 font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding:0 0 60px}
.wrap{max-width:980px;margin:0 auto;padding:0 20px}
header{padding:44px 0 10px}
h1{font-size:clamp(26px,4.5vw,38px);margin:0 0 6px;letter-spacing:-.01em}
.sub{color:var(--text-secondary);max-width:64ch}
.hero{display:flex;gap:14px;flex-wrap:wrap;margin:26px 0 8px}
.tile{background:var(--surface-2);border:1px solid var(--line);border-radius:12px;padding:14px 20px;min-width:150px}
.tile .k{font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--text-secondary)}
.tile .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:2px}
.tile .v .e{color:var(--east)} .tile .v .w{color:var(--west)}
h2{font-size:19px;margin:38px 0 4px}
.note{color:var(--text-secondary);font-size:13px;margin:0 0 12px}
.legend{display:flex;gap:16px;font-size:13px;color:var(--text-secondary);margin:6px 0 2px}
.legend .sw{display:inline-block;width:11px;height:11px;border-radius:3px;vertical-align:-1px;margin-right:5px}
figure{margin:8px 0 0;position:relative}
svg text{font:11.5px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:var(--text-secondary)}
.tt{position:absolute;pointer-events:none;background:var(--surface-2);border:1px solid var(--line);
 border-radius:8px;padding:6px 10px;font-size:12.5px;display:none;white-space:nowrap;
 box-shadow:0 4px 14px rgba(0,0,0,.15);z-index:5}
.tt b{font-variant-numeric:tabular-nums}
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:12px;margin-top:10px;background:var(--surface-1)}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums;min-width:480px}
th{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-secondary);
 text-align:right;padding:9px 13px;border-bottom:2px solid var(--line);background:var(--surface-2)}
th:first-child,td:first-child{text-align:left}
th.txt,td.txt{text-align:left}
td{padding:7px 13px;border-bottom:1px solid var(--line);text-align:right}
tr:last-child td{border-bottom:none}
tr.best td{background:var(--gold)}
.chip{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:7px;vertical-align:-1px}
select{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:8px;
 background:var(--surface-2);color:var(--text-primary)}
.bar2{display:flex;height:10px;border-radius:5px;overflow:hidden;min-width:110px;border:1px solid var(--line)}
.bar2 i{display:block;height:100%}
footer{color:var(--text-secondary);font-size:12.5px;margin-top:40px}
</style></head><body><div class="viz-root"><div class="wrap">
<header>
<h1>East vs West</h1>
<p class="sub">Inter-conference records across every SLN regular season — every East-vs-West game,
counted from the league's own scoreboards. East = the Atlantic &amp; Central franchises (rn 1–15),
West = Midwest &amp; Pacific (rn 16–29). Playoffs excluded.</p>
<div class="hero" id="hero"></div>
</header>

<h2>Season by season</h2>
<p class="note">Share of inter-conference games won by the East each season. The dotted line is a dead heat.</p>
<div class="legend"><span><span class="sw" style="background:var(--east)"></span>East ahead</span>
<span><span class="sw" style="background:var(--west)"></span>West ahead</span></div>
<figure id="fig"><div class="tt" id="tt"></div></figure>
<div class="tbl"><table id="stbl"><thead><tr>
<th class="txt">Season</th><th>East W</th><th>West W</th><th>Margin</th><th>East share</th><th class="txt" style="min-width:130px">Split</th>
</tr></thead><tbody></tbody></table></div>

<h2>All-time franchise records vs the other conference</h2>
<p class="note">Sorted by winning percentage. Names are the franchise's current name.</p>
<div class="tbl"><table id="ttbl"><thead><tr>
<th class="txt">Franchise</th><th class="txt">Conf</th><th>W</th><th>L</th><th>Win %</th>
</tr></thead><tbody></tbody></table></div>

<h2>Per-season team detail</h2>
<p class="note">Every team's record against the other conference in a chosen season.
<select id="yr"></select></p>
<div class="tbl"><table id="dtbl"><thead><tr>
<th class="txt">Team</th><th class="txt">Conf</th><th>W</th><th>L</th><th>Win %</th>
</tr></thead><tbody></tbody></table></div>

<footer>SLN Stat Book analysis · regular-season games only · built __BUILT__ ·
companion to <a href="https://slnstatbook.com" style="color:inherit">slnstatbook.com</a>.
The in-progress season (if shown) reflects games played to date.</footer>
</div></div>
<script id="d" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('d').textContent);
const fin=D.seasons.filter(s=>s.final);
const cur=D.seasons.find(s=>!s.final);
const Ew=fin.reduce((n,s)=>n+s.e,0), Ww=fin.reduce((n,s)=>n+s.w,0);
const eSeas=fin.filter(s=>s.e>s.w).length, wSeas=fin.filter(s=>s.w>s.e).length, tSeas=fin.length-eSeas-wSeas;
const css=v=>getComputedStyle(document.querySelector('.viz-root')).getPropertyValue(v).trim();
document.getElementById('hero').innerHTML=
 `<div class="tile"><div class="k">All-time (completed seasons)</div><div class="v"><span class="e">East ${Ew.toLocaleString()}</span> — <span class="w">${Ww.toLocaleString()} West</span></div></div>`
 +`<div class="tile"><div class="k">East share</div><div class="v">${(100*Ew/(Ew+Ww)).toFixed(1)}%</div></div>`
 +`<div class="tile"><div class="k">Season series won</div><div class="v"><span class="e">${eSeas}</span> — <span class="w">${wSeas}</span>${tSeas?` <span style="font-size:14px;color:var(--text-secondary)">(${tSeas} even)</span>`:''}</div></div>`
 +(cur?`<div class="tile"><div class="k">${cur.year} so far</div><div class="v"><span class="e">${cur.e}</span> — <span class="w">${cur.w}</span></div></div>`:'');

// ---- chart: East share line, 50% reference ----
(function(){
  const S=D.seasons, W=Math.min(940,Math.max(560,S.length*22)), H=240, L=44, R=14, T=14, B=30;
  const x=i=>L+(W-L-R)*(i/(S.length-1));
  const lo=.3, hi=.7;
  const y=v=>T+(H-T-B)*(1-(v-lo)/(hi-lo));
  let p='';
  S.forEach((s,i)=>{const v=s.e/(s.e+s.w); p+=(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1);});
  let g='';
  [.3,.4,.5,.6,.7].forEach(v=>{
    g+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" stroke-width="1" ${v===.5?'stroke-dasharray="4 4" stroke-opacity="1"':'stroke-opacity=".55"'}/>`
     +`<text x="${L-7}" y="${y(v)+4}" text-anchor="end">${Math.round(v*100)}%</text>`;});
  let dots='';
  S.forEach((s,i)=>{const v=s.e/(s.e+s.w);
    dots+=`<circle cx="${x(i)}" cy="${y(v)}" r="${s.final?3:4}" fill="${v>=.5?'var(--east)':'var(--west)'}" stroke="var(--surface-1)" stroke-width="2"/>`;});
  let xt='';
  S.forEach((s,i)=>{ if(s.year%5===0||i===S.length-1) xt+=`<text x="${x(i)}" y="${H-8}" text-anchor="middle">${s.year}</text>`;});
  const fig=document.getElementById('fig');
  fig.insertAdjacentHTML('beforeend',
   `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="East share of inter-conference wins by season">
     ${g}<path d="${p}" fill="none" stroke="var(--text-secondary)" stroke-width="2" stroke-opacity=".8"/>${dots}${xt}
     <rect id="hover" x="${L}" y="0" width="${W-L-R}" height="${H}" fill="transparent"/></svg>`);
  const tt=document.getElementById('tt'), svg=fig.querySelector('svg');
  svg.addEventListener('mousemove',ev=>{
    const r=svg.getBoundingClientRect(), fx=(ev.clientX-r.left)/r.width*W;
    let i=Math.round((fx-L)/((W-L-R)/(S.length-1))); i=Math.max(0,Math.min(S.length-1,i));
    const s=S[i], v=100*s.e/(s.e+s.w);
    tt.style.display='block';
    tt.style.left=Math.min(ev.clientX-r.left+14, r.width-170)+'px';
    tt.style.top=(ev.clientY-r.top-40)+'px';
    tt.innerHTML=`<b>${s.year}${s.final?'':' (in progress)'}</b><br>East <b>${s.e}</b> — <b>${s.w}</b> West (${v.toFixed(1)}%)`;
  });
  svg.addEventListener('mouseleave',()=>tt.style.display='none');
})();

// ---- season table ----
document.querySelector('#stbl tbody').innerHTML=D.seasons.map(s=>{
  const n=s.e+s.w, sh=100*s.e/n, m=s.e-s.w;
  return `<tr><td class="txt">${s.year}${s.final?'':' *'}</td><td>${s.e}</td><td>${s.w}</td>
  <td style="color:${m>0?'var(--east)':m<0?'var(--west)':'inherit'}">${m>0?'E +'+m:m<0?'W +'+(-m):'even'}</td>
  <td>${sh.toFixed(1)}%</td>
  <td class="txt"><span class="bar2"><i style="width:${sh}%;background:var(--east)"></i><i style="width:${100-sh}%;background:var(--west)"></i></span></td></tr>`;
}).join('');

// ---- all-time team table ----
document.querySelector('#ttbl tbody').innerHTML=D.teams.map((t,i)=>{
  const n=t.w+t.l, pc=100*t.w/n;
  return `<tr${i===0?' class="best"':''}><td class="txt"><span class="chip" style="background:var(--${t.conf==='East'?'east':'west'})"></span>${t.name}</td>
  <td class="txt">${t.conf}</td><td>${t.w.toLocaleString()}</td><td>${t.l.toLocaleString()}</td><td>${pc.toFixed(1)}%</td></tr>`;
}).join('');

// ---- per-season detail ----
const yrSel=document.getElementById('yr');
D.seasons.slice().reverse().forEach(s=>{
  const o=document.createElement('option'); o.value=s.code; o.textContent=s.year+(s.final?'':' (in progress)');
  yrSel.appendChild(o);});
function detail(){
  const rows=D.detail[yrSel.value]||[];
  document.querySelector('#dtbl tbody').innerHTML=rows.map(t=>{
    const n=t.w+t.l, pc=n?100*t.w/n:0;
    return `<tr><td class="txt"><span class="chip" style="background:var(--${t.conf==='East'?'east':'west'})"></span>${t.name}</td>
    <td class="txt">${t.conf}</td><td>${t.w}</td><td>${t.l}</td><td>${pc.toFixed(1)}%</td></tr>`;}).join('');
}
yrSel.onchange=detail; detail();
</script></body></html>"""
out = HTML.replace("__DATA__", json.dumps(DATA, separators=(",", ":"))).replace("__BUILT__", BUILT)
os.makedirs(f"{ROOT}/out", exist_ok=True)
open(f"{ROOT}/out/interconf.html", "w").write(out)
print(f"\nwrote out/interconf.html ({len(out):,} bytes)")
