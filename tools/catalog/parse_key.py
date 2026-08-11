#!/usr/bin/env python3
"""Parse SUPREM-IV.GS `suprem.key` into a JSON command catalog.

NOTE: this is the original exploration script, kept for one-off inspection.
The webapp does NOT use it — see backend/app/catalog/ instead.

It differs from the app parser in one way that matters: it emits names exactly
as written in suprem.key.  At run time the simulator reads suprem.uk, where
names are truncated to 11 characters, and resolution is by prefix — so a token
LONGER than the stored name matches nothing.  `concentration` is rejected;
`concentrati` works.  Do not feed this file's output to an editor's
autocomplete: it would produce code that does not run.

Grammar (inferred from the file header + the file itself):

    file        := stmt*
    stmt        := decl ';' [ '{' stmt* '}' ]
    decl        := TYPE NAME [ '=' DEFAULT ]
                          [ 'units'   '=' STRING ]
                          [ 'message' '=' STRING ]
                          [ 'error'   '=' EXPR   ]      (clauses in any order)
    TYPE        := card | int | integer | float | string | boolean | switch
    comment     := '#' .. end-of-line

A `switch` groups mutually-exclusive alternatives; its children live in the
following `{}` block.  A `boolean` may also own a `{}` block (e.g. structure
mirror -> right/left/top/bottom).  Max observed nesting depth is 3.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KEY = REPO_ROOT / "SUPREM4GS" / "data" / "suprem.key"
OUT = Path(__file__).with_name("catalog.json")

TYPES = {"card", "int", "integer", "float", "string", "boolean", "switch"}
CLAUSES = {"units", "message", "error"}

TOKEN_RE = re.compile(
    r'''
      (?P<comment>\#[^\n]*)
    | (?P<string>"(?:[^"\\]|\\.)*")
    | (?P<punct>[{};=])
    | (?P<ws>\s+)
    | (?P<name>[A-Za-z_/][A-Za-z0-9_./]*)
    | (?P<number>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
    | (?P<other>\S)
    ''',
    re.VERBOSE,
)


def tokenize(text):
    """-> list of (kind, value, line).  Comments are kept (used as doc text)."""
    toks, line = [], 1
    pos = 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            raise SyntaxError(f"cannot tokenize at line {line}: {text[pos:pos+40]!r}")
        kind = m.lastgroup
        val = m.group()
        if kind not in ("ws",):
            toks.append((kind, val, line))
        line += val.count("\n")
        pos = m.end()
    return toks


def clean_comment(c):
    return c.lstrip("#").lstrip("!").strip()


def parse(toks):
    """Recursive-descent over the token stream; returns a list of nodes."""
    i = 0
    n = len(toks)

    def parse_block(depth):
        nonlocal i
        nodes = []
        pending = []          # comment lines seen since the last statement
        while i < n:
            kind, val, ln = toks[i]
            if kind == "comment":
                pending.append((ln, clean_comment(val)))
                i += 1
                continue
            if kind == "name" and val == "end" and depth == 0:
                i += 1                      # EOF marker on the last line
                continue
            if kind == "punct" and val == "}":
                i += 1
                return nodes
            if kind == "punct" and val == "{":
                # a bare block belonging to the previous node
                i += 1
                child = parse_block(depth + 1)
                if nodes:
                    nodes[-1]["children"].extend(child)
                else:                       # should not happen
                    nodes.extend(child)
                pending = []
                continue
            node, trailing = parse_decl()
            node["doc"] = build_doc(pending, node["line"], trailing)
            node["children"] = []
            nodes.append(node)
            pending = []
        return nodes

    def build_doc(pending, decl_line, trailing):
        """Comment lines directly above the declaration + same-line comment."""
        lines = []
        prev = None
        for ln, txt in pending:
            if prev is not None and ln != prev + 1:
                lines = []                 # non-contiguous -> restart the block
            lines.append((ln, txt))
            prev = ln
        # must be glued to the declaration
        if lines and lines[-1][0] != decl_line - 1:
            lines = []
        out = [t for _, t in lines if t and not re.fullmatch(r"card\s+\d+", t)]
        if trailing:
            out.append(trailing)
        return " ".join(out).strip()

    def parse_decl():
        """Consume TYPE NAME [...] ';' ; return (node, trailing_comment)."""
        nonlocal i
        kind, val, ln = toks[i]
        if kind != "name" or val not in TYPES:
            raise SyntaxError(f"line {ln}: expected a type keyword, got {val!r}")
        node = {"type": val, "line": ln, "name": None, "default": None,
                "units": None, "message": None, "error": None}
        i += 1
        if toks[i][0] != "name":
            raise SyntaxError(f"line {ln}: expected a name after {val!r}")
        node["name"] = toks[i][1]
        i += 1
        # default value: '=' immediately after the name
        if toks[i][1] == "=" and toks[i][0] == "punct":
            i += 1
            node["default"] = toks[i][1].strip('"')
            i += 1
        # clause list
        while not (toks[i][0] == "punct" and toks[i][1] == ";"):
            k, v, l2 = toks[i]
            if k == "name" and v in CLAUSES:
                i += 1
                assert toks[i][1] == "=", f"line {l2}: '=' expected after {v}"
                i += 1
                if v == "error":                       # arbitrary expression
                    parts = []
                    while not (toks[i][0] == "punct" and toks[i][1] in ";"):
                        if toks[i][0] == "comment":
                            i += 1
                            continue
                        parts.append(toks[i][1])
                        i += 1
                    node["error"] = " ".join(parts)
                else:
                    node[v] = toks[i][1].strip('"')
                    i += 1
            elif k == "comment":
                i += 1
            else:
                raise SyntaxError(f"line {l2}: unexpected token {v!r} in decl")
        semi_line = toks[i][2]
        i += 1
        trailing = None
        if i < n and toks[i][0] == "comment" and toks[i][2] == semi_line:
            trailing = clean_comment(toks[i][1])
            i += 1
        return node, trailing

    return parse_block(0)


def flatten_params(nodes, group=None, out=None):
    """Flatten the tree under a card into a flat parameter list.

    `switch` nodes are containers of mutually-exclusive alternatives: they are
    recorded as a group, and their children become parameters tagged with that
    group.  A non-switch node that owns children keeps them as sub-options.
    """
    if out is None:
        out = []
    for nd in nodes:
        if nd["type"] == "switch":
            g = {"group": nd["name"], "message": nd["message"],
                 "units": nd["units"], "default": nd["default"]}
            flatten_params(nd["children"], g, out)
        else:
            p = {
                "name": nd["name"],
                "type": {"int": "integer"}.get(nd["type"], nd["type"]),
                "default": nd["default"],
                "units": nd["units"],
                "description": nd["doc"] or None,
                "error": nd["error"],
                "message": nd["message"],
                "group": group["group"] if group else None,
                "group_message": group["message"] if group else None,
                "line": nd["line"],
            }
            out.append(p)
            if nd["children"]:
                flatten_params(nd["children"], group, out)
    return out


def main():
    text = KEY.read_text(errors="replace")
    toks = tokenize(text)
    tree = parse(toks)

    cards = []
    for nd in tree:
        if nd["type"] != "card":
            print(f"WARNING: top-level non-card node {nd['name']!r} "
                  f"(line {nd['line']})", file=sys.stderr)
            continue
        cards.append({
            "card": nd["name"],
            "description": nd["doc"] or None,
            "line": nd["line"],
            "params": flatten_params(nd["children"]),
        })

    OUT.write_text(json.dumps(cards, indent=1, ensure_ascii=False))
    nparam = sum(len(c["params"]) for c in cards)
    print(f"cards   : {len(cards)}")
    print(f"params  : {nparam}  (unique names: "
          f"{len({p['name'] for c in cards for p in c['params']})})")
    print(f"cards without params: "
          f"{[c['card'] for c in cards if not c['params']]}")
    from collections import Counter
    print("param types:",
          dict(Counter(p["type"] for c in cards for p in c["params"])))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
