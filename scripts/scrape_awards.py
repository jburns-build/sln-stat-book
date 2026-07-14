#!/usr/bin/env python3
"""Scrape the per-season Regular Season Awards page for every season.
   history/{code}/regssnawards.htm  -> mirror/s{code}/regssnawards.htm
   current (top level)  /regssnawards.htm -> mirror/current/regssnawards.htm
Polite ~2 req/sec. Skips files already present.
"""
import os, time, urllib.request

UA = "Mozilla/5.0 (research audit; polite)"
BASE = "https://www.simleaguenirvana.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODES = ["96", "97", "99"] + [f"{i:02d}" for i in range(0, 38)]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read() if r.status == 200 else None
    except Exception:
        return None


def grab(url, out):
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return "cached"
    data = fetch(url)
    time.sleep(0.45)
    if data is None:
        return "404"
    with open(out, "wb") as f:
        f.write(data)
    return "ok"


for code in CODES:
    d = f"{ROOT}/mirror/s{code}"
    os.makedirs(d, exist_ok=True)
    print(f"s{code}: {grab(f'{BASE}/history/{code}/regssnawards.htm', f'{d}/regssnawards.htm')}")
d = f"{ROOT}/mirror/current"
os.makedirs(d, exist_ok=True)
# the live season's awards page changes as the season completes -> always refresh
cur_aw = f"{d}/regssnawards.htm"
if os.path.exists(cur_aw):
    os.remove(cur_aw)
print(f"current: {grab(f'{BASE}/regssnawards.htm', cur_aw)}")
print("DONE")
