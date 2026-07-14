#!/usr/bin/env python3
"""Scrape roster pages that aren't mirrored yet:
   - history seasons 32..37  -> mirror/sNN/rosters/
   - current (in-progress S38) top-level /rosters/ -> mirror/current/rosters/
Polite ~2 req/sec. Skips files already present. Probes roster1..32, stops past 29 on a 404.
"""
import os, time, urllib.request

UA = "Mozilla/5.0 (research audit; polite)"
BASE = "https://www.simleaguenirvana.com"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                return None
            return r.read()
    except Exception:
        return None


def scrape_dir(url_prefix, out_dir, label, force=False):
    os.makedirs(out_dir, exist_ok=True)
    got = 0
    for n in range(1, 33):
        f = os.path.join(out_dir, f"roster{n}.htm")
        # historical seasons never change (cache them); the live season always re-fetches
        if not force and os.path.exists(f) and os.path.getsize(f) > 0:
            got += 1
            continue
        data = fetch(f"{url_prefix}/roster{n}.htm")
        time.sleep(0.45)
        if data is None:
            if n >= 29:
                break
            continue
        with open(f, "wb") as fh:
            fh.write(data)
        got += 1
    print(f"{label}: {got} roster files present")


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# earliest league seasons use pre-2000 codes (96=1996, 97=1997, 99=1999; there is no 1998)
PRE = ["96", "97", "99"]
for s in PRE:
    scrape_dir(f"{BASE}/history/{s}/rosters", f"{ROOT}/mirror/s{s}/rosters", f"s{s}")
for ss in range(32, 38):
    s = f"{ss:02d}"
    scrape_dir(f"{BASE}/history/{s}/rosters", f"{ROOT}/mirror/s{s}/rosters", f"s{s}")
# current in-progress season (2038) lives at the top level and changes daily -> always refresh
scrape_dir(f"{BASE}/rosters", f"{ROOT}/mirror/current/rosters", "current(2038)", force=True)
print("DONE")
