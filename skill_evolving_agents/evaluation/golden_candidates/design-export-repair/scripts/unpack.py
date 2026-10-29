"""
Figure out what a Claude Design export actually is before trying to fix
it. Two genuinely different things reach this skill in practice:

  - A plain Export (PDF/PPTX/HTML) from a Design deck project. In
    practice this has turned out to be a bare .pptx (produced under the
    hood by PptxGenJS) as often as an actual .zip wrapper around one —
    this is the shape verified against a real broken export, and the
    fully-repaired path (content-types, geometry, fonts, spc workaround).

  - Whatever lands in the working directory from Design's "Send to
    Claude Code" handoff, which is a *different* feature from plain
    Export (it's aimed at importing a design into a codebase / continuing
    prototype work, per Claude's own docs — "import a design into your
    codebase... or let Claude build the whole thing"). Two variants,
    confirmed against Claude Code's own issue tracker (anthropics/
    claude-code#51980, #69246):
      * "Send to Claude Code Web" opens a new claude.ai/code session with
        the design bundle already attached at the working directory — no
        file to locate at all; this skill (or whatever's already there)
        just needs pointing at the directory.
      * "Send to local coding agent" generates a copy/paste prompt that
        depends on a Claude Design MCP connector local Claude Code does
        not ship — per the linked issue this fails silently for most
        people. The dialog's "Download zip instead" option is the
        reliable path: it downloads an actual zip of the design files (a
        bundle of `*.dc.html` canvas files + a README), which this module
        also has to recognize.

Either way, this module accepts a file OR a directory, plus a couple of
other shapes the export might take, and always returns a small, explicit
description of what it found rather than guessing silently.
"""

import zipfile
from dataclasses import dataclass
from pathlib import Path

PPTX_EXTS = {".pptx", ".potx"}
PDF_EXTS = {".pdf"}
HTML_EXTS = {".html", ".htm"}
DC_HTML_SUFFIX = ".dc.html"  # Claude Design's own canvas file format, seen in its "Send to local coding agent" handoff prompt


@dataclass
class ResolvedInput:
    kind: str  # "pptx" | "pdf" | "html" | "unknown"
    primary_path: Path
    extra_files: list  # for html: the sibling assets (css/js/images) it needs
    source_note: str  # human-readable explanation of what was found and where


def _is_zip(path: Path) -> bool:
    try:
        return zipfile.is_zipfile(path)
    except OSError:
        return False


def _looks_like_pptx(path: Path) -> bool:
    """A .pptx is itself a zip. zipfile.is_zipfile() is true for both a
    real .pptx and a zip bundle exported from Design, so distinguish them
    by whether the zip has the OOXML presentation part."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            return "ppt/presentation.xml" in names or any(n.startswith("ppt/slides/") for n in names)
    except (zipfile.BadZipFile, OSError):
        return False


def _scan_directory(directory: Path) -> ResolvedInput:
    """Search a directory (not a zip) for a repairable payload — this is
    what "Send to Claude Code Web" leaves you with: the design bundle
    already sitting in the working directory, no zip to unpack. Reuses
    the same priority order as the zip-extraction path: pptx first (the
    fully-repaired path), then Design's own .dc.html canvas format, then
    generic HTML, then a bare PDF."""
    pptx_candidates = sorted(directory.rglob("*.pptx")) + sorted(directory.rglob("*.potx"))
    if pptx_candidates:
        chosen = max(pptx_candidates, key=lambda p: p.stat().st_size)
        note = f"found {len(pptx_candidates)} pptx file(s) in {directory}; using the largest: {chosen.relative_to(directory)}"
        return ResolvedInput("pptx", chosen, pptx_candidates, note)

    dc_html_candidates = sorted(directory.rglob(f"*{DC_HTML_SUFFIX}"))
    if dc_html_candidates:
        chosen = dc_html_candidates[0]
        siblings = [p for p in directory.rglob("*") if p.is_file() and p != chosen]
        note = (
            f"found {len(dc_html_candidates)} Claude Design canvas file(s) (*.dc.html) in {directory}; "
            f"using {chosen.relative_to(directory)}. This is Design's native canvas format from its "
            "\"Send to Claude Code\" handoff, not an Export — the pptx repair path (content-types/geometry/"
            "fonts/letter-spacing) doesn't apply here; falling back to the best-effort HTML print-to-PDF path."
        )
        return ResolvedInput("html", chosen, siblings, note)

    html_candidates = sorted(directory.rglob("index.html")) or sorted(directory.rglob("*.html"))
    if html_candidates:
        chosen = html_candidates[0]
        siblings = [p for p in directory.rglob("*") if p.is_file() and p != chosen]
        return ResolvedInput("html", chosen, siblings, f"found an HTML/CSS/JS bundle in {directory}; entry point: {chosen.relative_to(directory)}")

    pdf_candidates = sorted(directory.rglob("*.pdf"))
    if pdf_candidates:
        chosen = pdf_candidates[0]
        return ResolvedInput(
            "pdf", chosen, pdf_candidates,
            f"found a PDF with no editable source ({chosen.relative_to(directory)}) in {directory} — see note above about limited repair for flattened PDFs",
        )

    found = [str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()][:20]
    return ResolvedInput("unknown", directory, [], f"{directory} did not contain a recognizable pptx/dc.html/html/pdf payload; top files: {found}")


def resolve_input(input_path: str, work_dir: Path) -> ResolvedInput:
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} does not exist")

    if input_path.is_dir():
        # This is the shape "Send to Claude Code Web" leaves behind: no
        # zip, no single file to point at — just a working directory with
        # the design bundle already in it.
        return _scan_directory(input_path)

    suffix = input_path.suffix.lower()

    # Design's own canvas format (seen in its "Send to local coding agent"
    # handoff prompt: "Implement: <FILE>.dc.html") handed over as a loose
    # file rather than inside a directory/zip.
    if input_path.name.endswith(DC_HTML_SUFFIX):
        return ResolvedInput(
            "html", input_path, [],
            f"input is a Claude Design canvas file ({input_path.name}) from the \"Send to Claude Code\" handoff, "
            "not a plain Export — falling back to the best-effort HTML print-to-PDF path rather than the "
            "verified pptx repair path",
        )

    # Case 1: bare .pptx handed directly (this is what Design's own export
    # button has produced in practice, not just a zip wrapper around one).
    if suffix in PPTX_EXTS or (suffix == "" and _looks_like_pptx(input_path)):
        if _looks_like_pptx(input_path):
            return ResolvedInput("pptx", input_path, [], f"input is already a .pptx: {input_path.name}")

    if suffix in PDF_EXTS:
        return ResolvedInput(
            "pdf", input_path, [],
            f"input is a bare PDF ({input_path.name}) with no editable source alongside it — "
            "structural repair (content-types / off-canvas shapes / font substitution) needs the "
            "original .pptx to fix; this skill can still validate the PDF, but cannot repair a "
            "flattened export the way it repairs a .pptx",
        )

    # Case 2: a zip. Could be a zip that directly *is* a pptx (rename
    # confusion), a zip wrapping a pptx/pdf, or an HTML+assets bundle.
    if _is_zip(input_path):
        if _looks_like_pptx(input_path):
            return ResolvedInput("pptx", input_path, [], f"input is a .pptx saved with a non-.pptx extension: {input_path.name}")

        extract_dir = work_dir / "unzipped"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(input_path) as zf:
            zf.extractall(extract_dir)

        # Same search this skill would do for a "Send to Claude Code Web"
        # working directory — a downloaded zip (whether a plain Export or
        # Design's "Download zip instead" fallback) is just that same
        # bundle shape, pre-zipped.
        resolved = _scan_directory(extract_dir)
        if resolved.kind == "unknown":
            resolved.source_note = resolved.source_note.replace("did not contain", "(from the uploaded zip) did not contain")
        else:
            resolved.source_note = f"zip extracted; {resolved.source_note}"
        return resolved

    return ResolvedInput("unknown", input_path, [], f"unrecognized input type: {input_path.name} (suffix {suffix!r})")
