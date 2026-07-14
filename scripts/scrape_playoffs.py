#!/usr/bin/env python3
"""Scrape each season's playoffs bracket (to find the champion).
   history/{code}/playoffs.htm -> mirror/s{code}/playoffs.htm
The current/top-level season is skipped (its playoffs haven't happened yet).
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


for code in CODES:
    d = f"{ROOT}/mirror/s{code}"
    os.makedirs(d, exist_ok=True)
    out = f"{d}/playoffs.htm"
    if os.path.exists(out) and os.path.getsize(out) > 0:
        print(f"s{code}: cached")
        continue
    data = fetch(f"{BASE}/history/{code}/playoffs.htm")
    time.sleep(0.45)
    if data is None:
        print(f"s{code}: 404")
        continue
    with open(out, "wb") as f:
        f.write(data)
    print(f"s{code}: ok")
print("DONE")
