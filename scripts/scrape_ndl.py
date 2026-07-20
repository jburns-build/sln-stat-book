#!/usr/bin/env python3
"""Scrape the NDL (developmental league) — current season only.

The site publishes no NDL history (every /NDL/history/... path 404s), so there
is nothing to archive; only the live season exists and it's always re-fetched.
Layout mirrors the SLN pages exactly, just under /NDL/.
"""
import os, sys, time, urllib.request, urllib.error

UA = "Mozilla/5.0 (research audit; polite)"
BASE = "https://www.simleaguenirvana.com/NDL"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{ROOT}/mirror/ndl/current"
MIN_TEAMS = 25   # the NDL runs 29 teams; anything less means the scrape failed


def fetch(url, attempts=3, timeout=20):
    """GET with retries. Real HTTP errors (404) answer immediately; only
    timeouts / connection problems are retried with backoff."""
    for i in range(attempts):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read() if r.status == 200 else None
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or i == attempts - 1:
                return None
            time.sleep(2 * (i + 1))
        except Exception:
            if i == attempts - 1:
                return None
            time.sleep(2 * (i + 1))


def main():
    os.makedirs(f"{OUT}/rosters", exist_ok=True)
    got = 0
    for n in range(1, 33):
        data = fetch(f"{BASE}/rosters/roster{n}.htm")
        time.sleep(0.45)
        if data is None:
            if n >= 29:
                break
            continue
        with open(f"{OUT}/rosters/roster{n}.htm", "wb") as fh:
            fh.write(data)
        got += 1
    print(f"ndl current: {got} roster files")

    # awards + playoffs (guarded downstream by year, like SLN's top-level pages)
    for page in ("regssnawards.htm", "playoffs.htm"):
        d = fetch(f"{BASE}/{page}")
        time.sleep(0.45)
        if d:
            with open(f"{OUT}/{page}", "wb") as fh:
                fh.write(d)
            print(f"ndl {page}: ok")
        else:
            print(f"ndl {page}: missing")

    if got < MIN_TEAMS:
        sys.exit(f"ERROR: only {got} NDL rosters fetched (need >= {MIN_TEAMS}). "
                 f"Refusing to continue so a broken site isn't published.")
    print("DONE")


if __name__ == "__main__":
    main()
