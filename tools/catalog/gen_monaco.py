#!/usr/bin/env python3
"""Turn catalog.json into Monaco editor assets:

  monaco-suprem.json  - data the providers consume (cards, params, docs)
  monaco-suprem.js    - drop-in monarch language + completion + hover providers

Also prints doc-coverage statistics (how many params carry usable hover text).
"""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
cards = json.load((HERE / "catalog.json").open())

FREEFORM = {"echo", "printf", "man", "pause"}
INTERP = ["set", "unset", "foreach", "end", "source", "define", "undef",
          "quit", "exit", "logout", "help", "prompt"]

MATERIALS = ["silicon", "oxide", "oxynitride", "nitride", "poly", "aluminum",
             "photoresist", "gas", "gaas"]


def hover_md(card, p):
    """Markdown hover body for one parameter."""
    sig = f"**{p['name']}**  `{p['type']}`"
    if p["default"] is not None:
        sig += f" = `{p['default']}`"
    out = [f"`{card}` card &nbsp;&middot;&nbsp; {sig}"]
    if p["units"]:
        out.append(f"\n{p['units']}")
    if p["description"] and p["description"] != p["units"]:
        out.append(f"\n_{p['description']}_")
    if p["group"]:
        note = p["group_message"] or f"one of the `{p['group']}` group only"
        out.append(f"\n\u26a0 mutually exclusive (`{p['group']}`): {note}")
    if p["error"]:
        out.append(f"\n\nconstraint: `!({p['error']})`")
    return "".join(out)


def card_hover_md(c):
    out = [f"**{c['card']}**"]
    if c["description"]:
        out.append(f" \u2014 {c['description']}")
    if c["card"] in FREEFORM:
        out.append("\n\n_(free-form card: the rest of the line is passed "
                   "through verbatim)_")
    else:
        req = [p["name"] for p in c["params"]
               if p["default"] is None and p["type"] in ("float", "integer")
               and not p["group"]]
        out.append(f"\n\n{len(c['params'])} parameters.")
        if req:
            out.append(" No default: " + ", ".join(f"`{r}`" for r in req[:8])
                       + ("\u2026" if len(req) > 8 else ""))
    return "".join(out)


data = {
    "cards": [],
    "interpreterKeywords": INTERP,
    "materials": MATERIALS,
}
for c in cards:
    data["cards"].append({
        "name": c["card"],
        "doc": card_hover_md(c),
        "freeform": c["card"] in FREEFORM,
        "params": [{
            "name": p["name"],
            "type": p["type"],
            "default": p["default"],
            "group": p["group"],
            "doc": hover_md(c["card"], p),
            # completion insert text: booleans are bare flags, others take '='
            "insert": p["name"] if p["type"] == "boolean" else p["name"] + "=",
        } for p in c["params"]],
    })

(HERE / "monaco-suprem.json").write_text(
    json.dumps(data, indent=1, ensure_ascii=False))

card_names = [c["card"] for c in cards]
all_params = sorted({p["name"] for c in cards for p in c["params"]})

JS = """// Generated from SUPREM-IV.GS data/suprem.key -- do not edit by hand.
// usage:  registerSuprem(monaco, SUPREM_DATA)
export const CARDS = __CARDS__;
export const INTERP = __INTERP__;

export function registerSuprem(monaco, data) {
  const byCard = new Map(data.cards.map(c => [c.name, c]));

  monaco.languages.register({ id: 'suprem' });

  monaco.languages.setMonarchTokensProvider('suprem', {
    ignoreCase: false,
    cards: CARDS,
    interp: INTERP,
    tokenizer: {
      root: [
        [/#.*$/, 'comment'],
        [/"/, { token: 'string.quote', next: '@string' }],
        // first word on the line: card or interpreter keyword
        [/^\\s*%?[a-zA-Z][\\w.]*/, {
          cases: {
            '@interp': 'keyword.control',
            '@cards': 'keyword',
            '@default': 'type.identifier'      // prefix-abbreviated card
          }
        }],
        [/\\$\\{?\\w+\\}?/, 'variable'],
        [/[a-zA-Z][\\w./]*(?=\\s*=)/, 'attribute.name'],
        [/[+-]?(\\d+\\.?\\d*|\\.\\d+)([eE][+-]?\\d+)?/, 'number'],
        [/[a-zA-Z][\\w./]*/, 'attribute.name'],   // bare boolean flag
        [/[=;{}()]/, 'delimiter'],
      ],
      string: [
        [/[^"]+/, 'string'],
        [/"/, { token: 'string.quote', next: '@pop' }],
      ],
    },
  });

  // ---- unique-prefix resolution, same rule as the simulator (case sensitive)
  function resolve(tok, names) {
    if (names.includes(tok)) return tok;
    const hit = names.filter(n => n.startsWith(tok));
    return hit.length === 1 ? hit[0] : null;
  }
  function cardOfLine(line) {
    const m = line.match(/^\\s*%?([A-Za-z][\\w.]*)/);
    if (!m) return null;
    const n = resolve(m[1], CARDS);
    return n ? byCard.get(n) : null;
  }

  monaco.languages.registerCompletionItemProvider('suprem', {
    triggerCharacters: [' ', '.'],
    provideCompletionItems(model, pos) {
      const line = model.getValueInRange({
        startLineNumber: pos.lineNumber, startColumn: 1,
        endLineNumber: pos.lineNumber, endColumn: pos.column });
      const word = model.getWordUntilPosition(pos);
      const range = { startLineNumber: pos.lineNumber, endLineNumber: pos.lineNumber,
                      startColumn: word.startColumn, endColumn: word.endColumn };
      const K = monaco.languages.CompletionItemKind;

      if (/^\\s*[\\w.]*$/.test(line)) {              // still on the first word
        return { suggestions: [
          ...data.cards.map(c => ({ label: c.name, kind: K.Function,
              insertText: c.name + ' ', documentation: { value: c.doc }, range })),
          ...data.interpreterKeywords.map(k => ({ label: k, kind: K.Keyword,
              insertText: k + ' ', range })),
        ]};
      }
      const card = cardOfLine(line);
      if (!card || card.freeform) return { suggestions: [] };
      return { suggestions: card.params.map(p => ({
        label: p.name,
        kind: p.type === 'boolean' ? K.EnumMember : K.Property,
        detail: p.type + (p.default !== null ? ' = ' + p.default : '')
                       + (p.group ? '  [' + p.group + ']' : ''),
        documentation: { value: p.doc },
        insertText: p.insert,
        range,
      }))};
    },
  });

  monaco.languages.registerHoverProvider('suprem', {
    provideHover(model, pos) {
      const w = model.getWordAtPosition(pos);
      if (!w) return null;
      const line = model.getLineContent(pos.lineNumber);
      // widen the word to include dots (x.min, D.0, plot.1d)
      let s = w.startColumn, e = w.endColumn;
      while (s > 1 && /[\\w./]/.test(line[s - 2])) s--;
      while (e <= line.length && /[\\w./]/.test(line[e - 1])) e++;
      const tok = line.slice(s - 1, e - 1);
      const range = new monaco.Range(pos.lineNumber, s, pos.lineNumber, e);

      const isFirst = line.slice(0, s - 1).trim().replace(/^%/, '') === '';
      if (isFirst) {
        const n = resolve(tok, CARDS);
        return n ? { range, contents: [{ value: byCard.get(n).doc }] } : null;
      }
      const card = cardOfLine(line);
      if (!card) return null;
      const n = resolve(tok, card.params.map(p => p.name));
      if (!n) return null;
      const p = card.params.find(x => x.name === n);
      return { range, contents: [{ value: p.doc }] };
    },
  });
}
""".replace("__CARDS__", json.dumps(card_names)) \
     .replace("__INTERP__", json.dumps(INTERP))

(HERE / "monaco-suprem.js").write_text(JS)

# ---------------------------------------------------------------- statistics
nparam = sum(len(c["params"]) for c in cards)
with_units = sum(1 for c in cards for p in c["params"] if p["units"])
with_desc = sum(1 for c in cards for p in c["params"]
                if p["description"] or p["units"])
with_def = sum(1 for c in cards for p in c["params"] if p["default"] is not None)
with_err = sum(1 for c in cards for p in c["params"] if p["error"])
in_group = sum(1 for c in cards for p in c["params"] if p["group"])
carddoc = sum(1 for c in cards if c["description"])

print(f"cards                       : {len(cards)}  (with description: {carddoc})")
print(f"parameters                  : {nparam}")
print(f"  with units string         : {with_units:5d}  ({100*with_units/nparam:.1f}%)")
print(f"  with any hover text       : {with_desc:5d}  ({100*with_desc/nparam:.1f}%)")
print(f"  with explicit default     : {with_def:5d}  ({100*with_def/nparam:.1f}%)")
print(f"  with validation expression: {with_err:5d}  ({100*with_err/nparam:.1f}%)")
print(f"  inside a switch group     : {in_group:5d}  ({100*in_group/nparam:.1f}%)")
print(f"distinct parameter names    : {len(all_params)}")
for f in ("monaco-suprem.json", "monaco-suprem.js"):
    print(f"{f}: {(HERE/f).stat().st_size/1024:.1f} kB")
