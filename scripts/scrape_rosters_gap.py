#!/usr/bin/env python3
"""Scrape roster pages that aren't mirrored yet:
   - history seasons 32..37  -> mirror/sNN/rosters/
   - current (in-progress S38) top-level /rosters/ -> mirror/current/rosters/
Polite ~2 req/sec. Skips files already present. Probes roster1..32, stops past 29 on a 404.
"""
import os, sys, time, urllib.request, urllib.error

UA = "Mozilla/5.0 (research audit; polite)"
BASE = "https://www.simleaguenirvana.com"
MIN_CURRENT_TEAMS = 25   # sanity floor; the live season always has ~29


def fetch(url, attempts=3, timeout=20):
    """GET with retries. A definitive HTTP error (404) answers immediately;
    transient ones (429/500/502/503/504 rate-limit or blip) and timeouts /
    connection problems are retried with backoff."""
    for i in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read() if r.status == 200 else None
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == attempts - 1:
                return None                  # definitive (e.g. 404), or out of tries
            time.sleep(2 * (i + 1))          # transient server/rate-limit — retry
        except Exception:
            if i == attempts - 1:
                return None
            time.sleep(2 * (i + 1))          # timeout / connection blip — retry


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
    return got


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# earliest league seasons use pre-2000 codes (96=1996, 97=1997, 99=1999; there is no 1998)
PRE = ["96", "97", "99"]
for s in PRE:
    scrape_dir(f"{BASE}/history/{s}/rosters", f"{ROOT}/mirror/s{s}/rosters", f"s{s}")
for ss in range(32, 38):
    s = f"{ss:02d}"
    scrape_dir(f"{BASE}/history/{s}/rosters", f"{ROOT}/mirror/s{s}/rosters", f"s{s}")
# current in-progress season (2038) lives at the top level and changes daily -> always refresh
got = scrape_dir(f"{BASE}/rosters", f"{ROOT}/mirror/current/rosters", "current(2038)", force=True)
# On an intermittently-blocked GitHub runner the live pull can come back empty
# even though the site is up. Wait and retry the whole batch a couple times
# before giving up, so a transient blip doesn't fail the build.
tries = 0
while got < MIN_CURRENT_TEAMS and tries < 2:
    tries += 1
    print(f"  live season short ({got}); waiting 45s and retrying ({tries}/2)…", flush=True)
    time.sleep(45)
    got = scrape_dir(f"{BASE}/rosters", f"{ROOT}/mirror/current/rosters", "current(2038)", force=True)
# Fail loudly rather than let a build ship with the live season missing. In CI
# mirror/current/ starts empty, so a failed scrape would silently drop the whole
# season; exiting non-zero keeps the last good deploy live instead.
if got < MIN_CURRENT_TEAMS:
    sys.exit(f"ERROR: only {got} live-season rosters fetched (need >= {MIN_CURRENT_TEAMS}) "
             f"after retries. Refusing to continue so a broken site isn't published.")
print("DONE")
