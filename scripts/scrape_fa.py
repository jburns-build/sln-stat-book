#!/usr/bin/env python3
"""Fetch the current free-agent pool -> out/fa.json.

The FA list lives at /fa/fa-pos.htm (Name linked with player id, Pos, measurables,
ability grades, Last Team). FAs are on no roster page, so without this the stat
book loses them the moment the offseason starts. One page, refetched every run.

The stat book joins these ids onto the two NEWEST seasons' rows (ids are stable
across adjacent seasons; recycling only happens across eras), so a "Free agents
only" filter over last season's stats works all offseason.
"""
import json, os, re, sys, time, urllib.request, urllib.error

UA = {"User-Agent": "Mozilla/5.0 (research audit; polite)"}
URL = "https://www.simleaguenirvana.com/fa/fa-pos.htm"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{ROOT}/out/fa.json"


def fetch(url, attempts=3, timeout=25):
    for i in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("latin-1") if r.status == 200 else None
        except urllib.error.HTTPError:
            return None
        except Exception:
            if i == attempts - 1:
                return None
            time.sleep(2 * (i + 1))


def main():
    h = fetch(URL)
    os.makedirs(f"{ROOT}/out", exist_ok=True)
    if h is None:
        # page unreachable: write an empty pool so the build proceeds; the
        # filter just matches nobody until the next successful refresh
        json.dump({"ids": [], "n": 0}, open(OUT, "w"))
        print("fa: page unreachable — wrote empty pool")
        return
    # full table rows: Name(linked w/ id), Pos, Height, Weight, Age,
    # In/Out/Hn/Df/Reb/Pot ability grades, Last Team
    fas = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.I | re.S):
        m = re.search(r'player(\d+)\.htm[^>]*>([^<]+)<', row)
        if not m:
            continue
        c = [x for x in (re.sub("<[^>]+>", "", y).replace("&nbsp;", " ").strip()
                         for y in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.I | re.S)) if x]
        # c = [Name, Pos, Height, Weight, Age, In, Out, Hn, Df, Reb, Pot, Last Team]
        rec = {"id": int(m.group(1)), "name": m.group(2).replace("&nbsp;", " ").strip()}
        if len(c) >= 12:
            rec["pos"] = c[1]
            rec["age"] = int(c[4]) if c[4].isdigit() else None
            rec["abil"] = dict(zip(["In", "Out", "Hn", "Df", "Reb", "Pot"], c[5:11]))
            rec["last"] = c[11]
        fas.append(rec)
    seen = set()
    fas = [f for f in fas if not (f["id"] in seen or seen.add(f["id"]))]
    json.dump({"ids": [f["id"] for f in fas], "names": {str(f["id"]): f["name"] for f in fas},
               "players": fas, "n": len(fas)}, open(OUT, "w"), separators=(",", ":"))
    print(f"fa: {len(fas)} free agents")


if __name__ == "__main__":
    main()
