#!/usr/bin/env python3
"""
Validates the two things the web app actually needs from docs.json:

  1. token-under-cursor  -> manual section  (editor hover / F1)
  2. free-text query     -> ranked sections (docs search box)

Run after extract_docs.py. Exits non-zero if any check fails.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = HERE / "out" / "docs.json"


def load() -> dict:
    if not DOCS.exists():
        raise SystemExit(f"missing {DOCS}; run extract_docs.py first")
    return json.loads(DOCS.read_text(encoding="utf-8"))


def build_lookup(doc: dict) -> dict[str, dict]:
    """command token -> section, plus command.param -> parameter block."""
    table: dict[str, dict] = {}
    for s in doc["sections"]:
        for alias in s["aliases"]:
            table[alias] = {"type": "command", "section": s["id"], "title": s["title"],
                            "page": s["page_start"], "pdf_page": s["pdf_page_start"]}
        for p in s["parameters"]:
            for name in p["names"]:
                key = f"{s['command']}.{name.lower()}"
                table[key] = {"type": "parameter", "section": s["id"],
                              "title": f"{s['title']} / {name}",
                              "page": s["page_start"], "pdf_page": s["pdf_page_start"],
                              "text": p["text"]}
    return table


def search(doc: dict, query: str, limit: int = 5) -> list[tuple[float, dict]]:
    terms = [t for t in re.findall(r"[a-z0-9.]+", query.lower()) if t]
    scored = []
    for s in doc["sections"]:
        hay = s["text"].lower()
        score = 0.0
        for t in terms:
            score += hay.count(t)
            if t in s["title"].lower():
                score += 25          # title hits dominate
            if t in s["aliases"]:
                score += 50
        if score:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return scored[:limit]


def main() -> int:
    doc = load()
    table = build_lookup(doc)
    failures = 0

    print(f"lookup table entries: {len(table)}")

    # --- 1. the commands the task called out by name -------------------------
    print("\n== token-under-cursor lookup ==")
    for token in ["implant", "diffuse", "deposit", "etch", "line", "region",
                  "structure", "select", "method", "boron", "foreach", "plot.1d"]:
        hit = table.get(token)
        if hit:
            print(f"  {token:<10} -> {hit['title']:<16} manual p.{hit['page']:<5} "
                  f"pdf p.{hit['pdf_page']}")
        else:
            print(f"  {token:<10} -> NOT FOUND")
            failures += 1

    # --- 2. parameter-level lookup -----------------------------------------
    print("\n== parameter lookup (command.param) ==")
    for key in ["implant.dose", "implant.energy", "implant.max.damage",
                "diffuse.time", "etch.trapezoi", "structure.outfile"]:
        hit = table.get(key)
        if hit:
            print(f"  {key:<20} -> {hit['text'][:64].replace(chr(10),' ')}...")
        else:
            print(f"  {key:<20} -> not resolved (falls back to section)")

    # --- 3. free-text search ------------------------------------------------
    print("\n== free-text search ==")
    for q in ["pearson distribution implant", "oxidation stress dependent",
              "segregation coefficient interface"]:
        print(f"  query: {q!r}")
        hits = search(doc, q, 3)
        if not hits:
            print("    NO HITS")
            failures += 1
        for score, s in hits:
            print(f"    {score:7.0f}  {s['title'][:44]:<46} p.{s['page_start']}")

    # --- 4. cross-check against the shipped grammar -------------------------
    print("\n== coverage vs data/suprem.key ==")
    cards = {s["command"] for s in doc["sections"] if s["has_key_card"]}
    docd = {s["command"] for s in doc["sections"] if s["kind"] == "command"}
    print(f"  documented sections            : {len(docd)}")
    print(f"  of those, present in suprem.key: {len(cards)}")
    print(f"  shell-only (no grammar card)   : {sorted(docd - cards)}")

    print(f"\n{'FAILURES: %d' % failures if failures else 'all checks passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
