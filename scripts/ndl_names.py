#!/usr/bin/env python3
"""Reconciling ledger names with site names.

The designation ledgers are hand-typed and the leagues share no id space, so
every NDL<->SLN join runs on the name — which makes a single wrong letter enough
to lose a player. Four active designations went missing that way (Devin/Davin
Wiley, Konnor/Konner Reynolds, Rashad/Rashard Crawford, Davon McLean/Mclean).

Two halves to the fix. `alias()` applies the confirmed corrections in
data/ndl_name_aliases.json, so the ledger text stays as written. `suggest()`
makes the next one self-diagnosing: an unresolved name prints its nearest
candidates instead of a bare "not found", so a typo is a one-line addition to
the alias file rather than an investigation.
"""
import difflib, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALIASES = f"{ROOT}/data/ndl_name_aliases.json"


def load_aliases(path=ALIASES):
    """{ledger name: site name}, empty if the file is absent."""
    if not os.path.exists(path):
        return {}
    return {k: v["site"] for k, v in json.load(open(path))["aliases"].items()}


def norm(n):
    """Casefold and strip punctuation, so McLean/Mclean and O'Neal/ONeal meet."""
    return re.sub(r"[^a-z ]", "", (n or "").lower())


def suggest(name, candidates, limit=3):
    """Nearest plausible spellings of `name` among `candidates`.

    Ranks an exact surname match first — most ledger typos are in the given
    name (Devin/Davin, Konnor/Konner) — then falls back to whole-name
    similarity, which catches the surname slips (Rashad/Rashard).
    """
    if not name:
        return []
    n = norm(name)
    by_norm = {}
    for c in candidates:
        by_norm.setdefault(norm(c), c)
    if n in by_norm:
        return [by_norm[n]]                       # differs only in punctuation
    surname = n.rsplit(" ", 1)[-1]
    same_surname = [c for k, c in by_norm.items() if k.rsplit(" ", 1)[-1] == surname]
    close = difflib.get_close_matches(n, list(by_norm), n=limit, cutoff=0.82)
    out = same_surname + [by_norm[k] for k in close if by_norm[k] not in same_surname]
    return out[:limit]
