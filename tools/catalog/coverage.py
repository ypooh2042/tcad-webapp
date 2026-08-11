#!/usr/bin/env python3
"""Check how well catalog.json (extracted from suprem.key) covers the real
SUPREM-IV.GS input decks under examples/.

SUPREM matches card and parameter names by *unique prefix* (the binary carries
the string "the command is ambiguous"), so the checker does the same:
exact match wins, otherwise a token must prefix exactly one candidate.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "SUPREM4GS"
EXDIR = ROOT / "examples"

# interpreter-level commands (handled by the shell/parser layer, NOT cards).
# Confirmed by `strings suprem`: quit exit logout source foreach undef define
# unset ... ; `set`/`end` appear in the decks and behave the same way.
# cards whose "parameter line" is free text, not name=value pairs
FREEFORM = {"echo", "printf", "man", "pause"}

INTERP = {"set", "unset", "foreach", "end", "source", "define", "undef",
          "quit", "exit", "logout", "help", "prompt"}

TOK = re.compile(r'"[^"]*"|=|[^\s=]+')


def deck_files():
    files = []
    for p in sorted(EXDIR.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix in (".str",) or p.name in ("sup45.examples", "be1", "file1"):
            continue
        head = p.open(errors="replace").read(400)
        if p.suffix in (".in", ".s4") or re.match(r"example\d+$", p.name):
            files.append(p)
    return files


def statements(path):
    """Yield (lineno, [tokens]) for every command statement in a deck."""
    for lineno, raw in enumerate(path.open(errors="replace").read().splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        for piece in line.split(";"):            # `select ...; print.1d ...`
            piece = piece.strip()
            if piece:
                yield lineno, TOK.findall(piece)


def group(tokens):
    """[a, =, 1, b] -> [('a','1'), ('b',None)]  (bare token == boolean flag).

    A value may be an unquoted parenthesised formula containing spaces
    (modelrc: `oxide erf.h = (402 * (0.445 - 1.75 * en ) * exp(- Tox /200 ))`),
    so parentheses are balanced before the value is closed.
    """
    out, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        if i + 1 < len(tokens) and tokens[i + 1] == "=":
            j = i + 2
            val = []
            depth = 0
            while j < len(tokens):
                val.append(tokens[j])
                depth += tokens[j].count("(") - tokens[j].count(")")
                j += 1
                if depth <= 0:
                    break
            out.append((t, " ".join(val)))
            i = j
        elif t == "=":
            i += 1
        else:
            out.append((t, None))
            i += 1
    return out


def resolve(tok, names):
    """SUPREM-style unique-prefix lookup. -> (status, matched_name).

    Verified against the real binary: matching is CASE SENSITIVE for both
    card names and parameter names, and an ambiguous prefix is an error
    ("ambiguous parameter - x.m").
    """
    exact = [n for n in names if n == tok]
    if exact:
        return "ok", exact[0]
    pre = [n for n in names if n.startswith(tok)]
    if len(pre) == 1:
        return "ok", pre[0]
    if len(pre) > 1:
        return "ambiguous", pre
    return "missing", None


def main():
    cards = json.load((HERE / "catalog.json").open())
    by_card = {c["card"]: c for c in cards}
    card_names = list(by_card)

    n_cmd = n_cmd_ok = 0
    n_par = n_par_ok = 0
    miss_cmd = Counter()
    miss_par = Counter()
    amb_cmd = Counter()
    amb_par = Counter()
    where = defaultdict(set)
    interp_used = Counter()
    used_cards = Counter()
    used_params = defaultdict(set)

    files = deck_files()
    for f in files:
        rel = f.relative_to(ROOT)
        for lineno, toks in statements(f):
            cmd = toks[0].lstrip("%")     # '%' = macro-suppression prefix
            if cmd in INTERP:
                interp_used[cmd] += 1
                continue
            n_cmd += 1
            st, m = resolve(cmd, card_names)
            if st == "missing":
                miss_cmd[cmd] += 1
                where[("cmd", cmd)].add(f"{rel}:{lineno}")
                continue
            if st == "ambiguous":
                amb_cmd[cmd] += 1
                where[("cmd", cmd)].add(f"{rel}:{lineno}")
                continue
            n_cmd_ok += 1
            used_cards[m] += 1
            if m in FREEFORM:            # whole line is a format/echo string
                continue
            pnames = [p["name"] for p in by_card[m]["params"]]
            for key, _val in group(toks[1:]):
                n_par += 1
                ps, pm = resolve(key, pnames)
                if ps == "ok":
                    n_par_ok += 1
                    used_params[m].add(pm)
                elif ps == "ambiguous":
                    amb_par[f"{m}.{key}"] += 1
                    where[("par", f"{m}.{key}")].add(f"{rel}:{lineno}")
                else:
                    miss_par[f"{m}.{key}"] += 1
                    where[("par", f"{m}.{key}")].add(f"{rel}:{lineno}")

    print(f"decks scanned      : {len(files)}")
    print(f"command statements : {n_cmd}   resolved {n_cmd_ok} "
          f"({100*n_cmd_ok/n_cmd:.2f}%)   miss {sum(miss_cmd.values())}   "
          f"ambiguous {sum(amb_cmd.values())}")
    print(f"parameter tokens   : {n_par}   resolved {n_par_ok} "
          f"({100*n_par_ok/n_par:.2f}%)   miss {sum(miss_par.values())}   "
          f"ambiguous {sum(amb_par.values())}")
    print(f"distinct cards used: {len(used_cards)} / {len(card_names)}")
    print(f"interpreter cmds   : {dict(interp_used)}")
    print()
    print("-- unresolved commands (token: count) --")
    for k, v in miss_cmd.most_common():
        print(f"   {k:<16} {v:>3}   e.g. {sorted(where[('cmd',k)])[0]}")
    print("-- ambiguous commands --")
    for k, v in amb_cmd.most_common():
        print(f"   {k:<16} {v:>3}   e.g. {sorted(where[('cmd',k)])[0]}")
    print()
    print("-- unresolved parameters (card.token: count) --")
    for k, v in miss_par.most_common():
        print(f"   {k:<28} {v:>3}   e.g. {sorted(where[('par',k)])[0]}")
    print("-- ambiguous parameters --")
    for k, v in amb_par.most_common():
        print(f"   {k:<28} {v:>3}   e.g. {sorted(where[('par',k)])[0]}")
    print()
    print("-- cards used, by frequency --")
    print("   " + ", ".join(f"{k}({v})" for k, v in used_cards.most_common()))
    print("-- cards never exercised by the examples --")
    print("   " + ", ".join(sorted(set(card_names) - set(used_cards))))


if __name__ == "__main__":
    main()
