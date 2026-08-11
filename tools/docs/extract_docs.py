#!/usr/bin/env python3
"""
Extract the SUPREM-IV.GS manual into a searchable JSON structure.

Source of truth: the Acrobat-distilled PDF shipped in the repo
(`Suprem-IV GS Manual.pdf`, 320 pp, correct page order).
Fallback: `doc/Suprem-IV.GS.ps` converted with ghostscript -- that PS is in
REVERSE page order, so the fallback path reverses pages back.

Output: docs.json  -- one record per manual section, plus per-parameter
sub-records for command/model reference pages, so a web editor can jump from
a token under the cursor straight to the right chunk of the manual.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO = REPO_ROOT / "SUPREM4GS"
OFFICIAL_PDF = REPO / "Suprem-IV GS Manual.pdf"
FALLBACK_PS = REPO / "doc" / "Suprem-IV.GS.ps"
KEY_FILE = REPO / "data" / "suprem.key"

FOOTER_RE = re.compile(r"SUPREM-IV\.GS\s*[-–]\s*2D Process Simulation for Si and GaAs")
COMMAND_ANCHOR_RE = re.compile(r"^COMMAND\s{3,}(\S.*?)\s*$")
EXAMPLE_ANCHOR_RE = re.compile(r"^(EXAMPLE\s+\d+)\s{3,}(\S.*?)\s*$")
PAGE_LABEL_RE = re.compile(r'%%Page:\s+"([^"]+)"\s+(\d+)')

# Headings that appear inside a reference section, in the order they occur.
REF_SUBHEADINGS = ("SYNOPSIS", "DESCRIPTION", "EXAMPLES", "REFERENCES", "SEE ALSO")


class ExtractionError(RuntimeError):
    """Raised when the manual cannot be turned into usable text."""


# --------------------------------------------------------------------------
# text extraction
# --------------------------------------------------------------------------

def _run(cmd: list[str]) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        raise ExtractionError(f"could not run {cmd[0]!r}: {exc}") from exc
    if proc.returncode != 0:
        raise ExtractionError(f"{cmd[0]} failed ({proc.returncode}): {proc.stderr[:400]}")


def pages_from_pdf(pdf: Path, workdir: Path) -> list[str]:
    """pdftotext -layout keeps the two-column margin labels the manual relies on."""
    out = workdir / (pdf.stem + ".layout.txt")
    _run(["pdftotext", "-layout", str(pdf), str(out)])
    pages = out.read_text(encoding="utf-8", errors="replace").split("\f")
    while pages and not pages[-1].strip():
        pages.pop()
    if not pages:
        raise ExtractionError(f"no text extracted from {pdf}")
    return pages


def flow_vocabulary(pdf: Path, workdir: Path) -> set[str]:
    """
    Words seen in poppler's default (non -layout) extraction.

    That mode rejoins words broken across lines ("equi-" + "librium") while
    leaving real compounds ("non-equilibrium") alone, but it destroys the
    column layout the section anchors depend on. So we keep -layout for
    structure and mine this mode purely for a vocabulary that tells us which
    end-of-line hyphens were soft.
    """
    out = workdir / (pdf.stem + ".flow.txt")
    _run(["pdftotext", str(pdf), str(out)])
    text = out.read_text(encoding="utf-8", errors="replace")
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9._]*", text)}


def dehyphenate(text: str, vocab: set[str]) -> str:
    """Join `foo-\\nbar` into `foobar` only when `foobar` is a word we have seen."""
    def repl(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        joined = left + right
        if joined.lower() in vocab:
            return joined
        if f"{left}-{right}".lower() in vocab:
            return f"{left}-{right}"
        return joined if joined.lower() in vocab else m.group(0)
    return re.sub(r"([A-Za-z]{2,})-\n\s*([a-z]+)", repl, text)


def pages_from_ps(ps: Path, workdir: Path) -> list[str]:
    """Fallback: ghostscript to PDF, then pdftotext. The PS is in reverse order."""
    pdf = workdir / "from_ps.pdf"
    _run([
        "gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
        "-sDEVICE=pdfwrite", f"-sOutputFile={pdf}", str(ps),
    ])
    return pages_from_pdf(pdf, workdir)[::-1]


def page_labels_from_ps(ps: Path, count: int) -> list[str]:
    """Printed page labels ('i', 'ii', '1', '2', ...) in reading order."""
    labels: list[tuple[str, int]] = []
    try:
        with ps.open(encoding="latin-1") as fh:
            for line in fh:
                m = PAGE_LABEL_RE.match(line)
                if m:
                    labels.append((m.group(1), int(m.group(2))))
    except OSError:
        return [str(i + 1) for i in range(count)]
    labels.sort(key=lambda pair: pair[1])
    if len(labels) != count:
        return [str(i + 1) for i in range(count)]
    return [label for label, _ in labels]


# --------------------------------------------------------------------------
# page cleanup
# --------------------------------------------------------------------------

MARGIN_LABEL_RE = re.compile(
    r"^(COMMAND|FIGURE\s+\d+|TABLE\s+\d+|EXAMPLE\s+\d+)\s{3,}(\S.*?)\s*$"
)


def clean_page(raw: str, running_head: str | None) -> str:
    """
    Drop the running header and the footer/page-number line, pull the marginal
    label column out of the body, then dedent the body column.

    `pdftotext -layout` renders this manual as a narrow left label column
    (COMMAND / FIGURE n / TABLE n) plus a deeply indented body column. The body
    indent has to be removed or every downstream `^HEADING$` match fails.
    """
    lines = raw.split("\n")

    # running header: first non-blank line, if it is just the section title
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if running_head and line.strip().upper() == running_head.upper():
            lines = lines[i + 1:]
        break

    lines = [ln for ln in lines if not FOOTER_RE.search(ln)]

    body: list[str] = []          # (is_margin, text)
    margins: list[tuple[int, str]] = []
    for ln in lines:
        m = MARGIN_LABEL_RE.match(ln)
        if m:
            label = " ".join(m.group(1).split())
            # the COMMAND label is redundant once the section title is known
            margins.append((len(body), "" if label == "COMMAND" else f"{label}: {m.group(2)}"))
            body.append("")
        else:
            body.append(ln)

    indents = [len(ln) - len(ln.lstrip(" ")) for ln in body if ln.strip()]
    shift = min(indents) if indents else 0
    out = [ln[shift:] if ln.strip() else "" for ln in body]
    for pos, text in margins:
        out[pos] = text

    return "\n".join(out).strip("\n")


def collapse_blanks(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --------------------------------------------------------------------------
# structure detection
# --------------------------------------------------------------------------

@dataclass
class Anchor:
    kind: str            # "command" | "example"
    title: str
    page_index: int      # 0-based index into the page list
    line_index: int      # line within that page


def find_anchors(pages: list[str]) -> list[Anchor]:
    anchors: list[Anchor] = []
    for pi, page in enumerate(pages):
        for li, line in enumerate(page.split("\n")):
            m = COMMAND_ANCHOR_RE.match(line)
            if m:
                anchors.append(Anchor("command", m.group(1), pi, li))
                continue
            m = EXAMPLE_ANCHOR_RE.match(line)
            if m and li < 6:
                anchors.append(Anchor("example", f"{m.group(1)}: {m.group(2)}", pi, li))
    anchors.sort(key=lambda a: (a.page_index, a.line_index))
    return anchors


def running_head(page: str) -> str:
    for line in page.split("\n"):
        if line.strip():
            return " ".join(line.split())
    return ""


@dataclass
class Run:
    """A maximal run of consecutive pages sharing one running header."""
    head: str
    start: int
    end: int


def find_runs(pages: list[str]) -> list[Run]:
    """
    Every page of this manual carries its section title as a running header,
    and chapter front pages carry the chapter title ('Commands', 'Models').
    Grouping consecutive pages by that header segments the whole book with no
    gaps -- which anchor-only splitting cannot do, because chapter intro pages
    have no anchor and would otherwise be swallowed by the preceding command.
    """
    runs: list[Run] = []
    for i, page in enumerate(pages):
        head = running_head(page)
        if runs and runs[-1].head == head:
            runs[-1].end = i
        else:
            runs.append(Run(head, i, i))

    # A chapter's opening page wraps its long title, so the header reads
    # "The SUPREM-IV.GS" there and "The SUPREM-IV.GS Shell" after. Merge a run
    # whose header is a strict prefix of the next run's header.
    merged: list[Run] = []
    for run in runs:
        if (merged and run.head.startswith(merged[-1].head)
                and merged[-1].head and run.head != merged[-1].head
                and merged[-1].end - merged[-1].start == 0):
            merged[-1].head = run.head
            merged[-1].end = run.end
        else:
            merged.append(run)
    return merged


def split_parameters(body: str) -> list[dict]:
    """
    Inside DESCRIPTION, parameters are documented as a short comma-separated
    name line followed by prose. Parameter names are lowercase and may contain
    '.', '_' or digits (e.g. `max.damage`, `std.dev`, `Dix.0`).
    """
    name_line = re.compile(
        r"^([A-Za-z][A-Za-z0-9._]*(?:\s*,\s*[A-Za-z][A-Za-z0-9._]*)*)\s*$"
    )
    lines = body.split("\n")
    params: list[dict] = []
    current: dict | None = None
    buf: list[str] = []

    for idx, line in enumerate(lines):
        stripped = line.strip()
        m = name_line.match(stripped) if stripped else None
        # a parameter heading is a bare name line preceded by a blank line and
        # followed by prose (not by another bare name line of a synopsis block)
        prev_blank = idx == 0 or not lines[idx - 1].strip()
        nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        looks_like_heading = bool(m) and prev_blank and bool(nxt) and len(stripped) <= 70
        if looks_like_heading:
            if current:
                current["text"] = collapse_blanks("\n".join(buf))
                params.append(current)
            names = [n.strip() for n in stripped.split(",") if n.strip()]
            current = {"names": names, "text": ""}
            buf = []
        elif current is not None:
            buf.append(line)

    if current:
        current["text"] = collapse_blanks("\n".join(buf))
        params.append(current)

    return [p for p in params if p["text"]]


def split_subsections(text: str) -> dict[str, str]:
    """Split a reference section body on its ALL-CAPS subheadings."""
    positions: list[tuple[int, int, str]] = []
    for head in REF_SUBHEADINGS:
        for m in re.finditer(rf"^[ \t]*{re.escape(head)}[ \t]*$", text, re.MULTILINE):
            positions.append((m.start(), m.end(), head))
    positions.sort()

    out: dict[str, str] = {}
    if not positions:
        out["BODY"] = collapse_blanks(text)
        return out

    preamble = text[: positions[0][0]].strip()
    if preamble:
        out["SUMMARY"] = collapse_blanks(preamble)
    for i, (start, head_end, head) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        out[head] = collapse_blanks(text[head_end:end])
    return out


# --------------------------------------------------------------------------
# suprem.key cross-reference
# --------------------------------------------------------------------------

def parse_key_cards(path: Path) -> dict[str, list[str]]:
    """Map each `card <name>` to the parameter names declared in its block."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"#.*", "", text)  # strip comments

    cards: dict[str, list[str]] = {}
    decl = re.compile(r"\b(?:float|integer|boolean|string|switch)\s+([A-Za-z][A-Za-z0-9._]*)")
    for m in re.finditer(r"\bcard\s+([A-Za-z][A-Za-z0-9._]*)\s*;", text):
        name = m.group(1)
        nxt = re.search(r"\bcard\s+[A-Za-z][A-Za-z0-9._]*\s*;", text[m.end():])
        block = text[m.end(): m.end() + (nxt.start() if nxt else len(text))]
        params = sorted({d.group(1) for d in decl.finditer(block)})
        cards[name.lower()] = params
    return cards


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

@dataclass
class Section:
    id: str
    kind: str
    title: str
    command: str | None
    aliases: list[str]
    page_start: str
    page_end: str
    pdf_page_start: int
    pdf_page_end: int
    subsections: dict = field(default_factory=dict)
    parameters: list = field(default_factory=list)
    has_key_card: bool = False
    key_parameters: list = field(default_factory=list)
    text: str = ""


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def build(pages: list[str], labels: list[str], cards: dict[str, list[str]],
          vocab: set[str]) -> list[Section]:
    anchors = find_anchors(pages)
    if not anchors:
        raise ExtractionError("no section anchors found - layout assumptions broke")
    by_page = {a.page_index: a for a in anchors}

    runs = find_runs(pages)
    sections: list[Section] = []
    used_ids: set[str] = set()

    for i, run in enumerate(runs):
        anc = next((by_page[p] for p in range(run.start, run.end + 1) if p in by_page), None)
        kind = anc.kind if anc else "chapter"
        title = anc.title if anc else run.head

        body = "\n\n".join(clean_page(pages[p], run.head)
                           for p in range(run.start, run.end + 1))
        body = collapse_blanks(dehyphenate(body, vocab))

        aliases = [a.strip().lower() for a in title.split(",")] if kind == "command" else []
        command = aliases[0] if aliases else None

        subs = split_subsections(body) if kind == "command" else {"BODY": body}
        params = split_parameters(subs.get("DESCRIPTION", "")) if kind == "command" else []

        sid = slugify(title) or f"section-{i}"
        if sid in used_ids:
            sid = f"{sid}-{i}"
        used_ids.add(sid)

        sections.append(Section(
            id=sid,
            kind=kind,
            title=title,
            command=command,
            aliases=aliases,
            page_start=labels[run.start],
            page_end=labels[run.end],
            pdf_page_start=run.start + 1,
            pdf_page_end=run.end + 1,
            subsections=subs,
            parameters=params,
            has_key_card=(command or "") in cards,
            key_parameters=cards.get(command or "", []),
            text=body,
        ))
    return sections


def main() -> int:
    workdir = Path(__file__).resolve().parent / "out"
    workdir.mkdir(parents=True, exist_ok=True)

    source = "official-pdf"
    try:
        if OFFICIAL_PDF.exists():
            pages = pages_from_pdf(OFFICIAL_PDF, workdir)
        else:
            raise ExtractionError("official PDF missing")
    except ExtractionError as exc:
        print(f"warning: {exc}; falling back to PostScript", file=sys.stderr)
        source = "ghostscript-from-ps"
        pages = pages_from_ps(FALLBACK_PS, workdir)

    labels = page_labels_from_ps(FALLBACK_PS, len(pages))
    cards = parse_key_cards(KEY_FILE)
    vocab = flow_vocabulary(
        OFFICIAL_PDF if source == "official-pdf" else workdir / "from_ps.pdf", workdir)
    sections = build(pages, labels, cards, vocab)

    doc = {
        "source": source,
        "source_file": str(OFFICIAL_PDF if source == "official-pdf" else FALLBACK_PS),
        "total_pdf_pages": len(pages),
        "section_count": len(sections),
        "sections": [asdict(s) for s in sections],
    }
    out = workdir / "docs.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    # command -> section index, for editor lookups
    index = {}
    for s in sections:
        for alias in s.aliases:
            index[alias] = {"id": s.id, "title": s.title, "page": s.page_start,
                            "pdf_page": s.pdf_page_start}
    (workdir / "command_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"source          : {source}")
    print(f"pages           : {len(pages)}")
    print(f"sections        : {len(sections)}")
    print(f"  command/model : {sum(1 for s in sections if s.kind == 'command')}")
    print(f"  examples      : {sum(1 for s in sections if s.kind == 'example')}")
    print(f"  chapters/prose: {sum(1 for s in sections if s.kind == 'chapter')}")
    covered = sum(s.pdf_page_end - s.pdf_page_start + 1 for s in sections)
    print(f"page coverage   : {covered}/{len(pages)}")
    print(f"indexed aliases : {len(index)}")
    print(f"suprem.key cards: {len(cards)}")
    matched = [s for s in sections if s.kind == "command" and s.has_key_card]
    print(f"sections matched to a suprem.key card: {len(matched)}")
    with_syn = [s for s in sections if "SYNOPSIS" in s.subsections]
    with_desc = [s for s in sections if "DESCRIPTION" in s.subsections]
    print(f"sections with SYNOPSIS   : {len(with_syn)}")
    print(f"sections with DESCRIPTION: {len(with_desc)}")
    print(f"parameter blocks parsed  : {sum(len(s.parameters) for s in sections)}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ExtractionError as exc:
        print(f"extraction failed: {exc}", file=sys.stderr)
        sys.exit(1)
