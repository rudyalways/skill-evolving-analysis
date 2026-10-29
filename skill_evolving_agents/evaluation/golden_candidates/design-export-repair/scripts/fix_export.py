#!/usr/bin/env python3
"""
Main entry point for the design-export-repair skill.

Usage:
    python3 fix_export.py <input> [--out-dir DIR] [--no-pdf] [--no-network]

<input> can be:
  - a .pptx exported from Claude Design (this is what's been seen in
    practice — Design's export sometimes comes through as a bare .pptx,
    not always wrapped in a zip)
  - a .zip containing a .pptx, or an HTML/CSS/JS deck bundle, or a PDF
  - a bare .pdf (repair is limited without the source — see below)

What it does for a .pptx (the fully-verified path — see
references/defect-classes.md for how each of these was confirmed against
a real broken export):
  1. Audits [Content_Types].xml against what's actually in the zip.
  2. Fixes any shape whose box extends past the slide edge.
  3. Scans every typeface reference and makes sure the renderer has
     matching font files instead of silently substituting one.
  4. Re-saves the repaired .pptx (this also naturally clears any dangling
     Content_Types entries — python-pptx rebuilds that manifest from its
     own part graph on save).
  5. Converts the repaired deck to PDF with LibreOffice headless.
  6. Validates the resulting PDF: page count, blank pages, anything still
     touching a page edge.
  7. Writes a report (JSON + Markdown) describing exactly what changed and
     why, so nothing is fixed silently.

Exits non-zero only if something genuinely could not be completed (e.g.
LibreOffice conversion failed outright); font/geometry issues that were
fixed, or fonts that fell back to a substitute, are reported but do not
fail the run.
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import content_types
import fonts as fonts_mod
import geometry
import render_workaround
import soffice
import unpack
import validate_pdf as validate_pdf_mod


def _asdict_list(items):
    return [dataclasses.asdict(i) for i in items]


def repair_pptx(pptx_path: Path, out_dir: Path, allow_network_fetch: bool) -> dict:
    from pptx import Presentation

    report: dict = {"input_kind": "pptx", "source_path": str(pptx_path)}

    # --- defect 1: audit package structure (before) ---
    before_audit = content_types.audit_content_types(pptx_path)
    report["content_types_before"] = dataclasses.asdict(before_audit)

    # --- open, fix geometry (defect 2) ---
    prs = Presentation(str(pptx_path))
    slide_count = len(prs.slides)
    changes, flags = geometry.fix_presentation_geometry(prs)
    report["geometry_changes"] = _asdict_list(changes)
    report["geometry_flags_for_manual_review"] = _asdict_list(flags)

    # --- save repaired pptx (this also clears dangling Content_Types entries) ---
    out_dir.mkdir(parents=True, exist_ok=True)
    repaired_pptx_path = out_dir / (pptx_path.stem.replace(".repaired", "") + ".repaired.pptx")
    prs.save(str(repaired_pptx_path))
    report["repaired_pptx_path"] = str(repaired_pptx_path)

    after_audit = content_types.audit_content_types(repaired_pptx_path)
    report["content_types_after"] = dataclasses.asdict(after_audit)
    report["content_types_fixed"] = (
        len(before_audit.missing_parts) > 0 and len(after_audit.missing_parts) == 0
    )

    # --- defect 3: fonts ---
    import tempfile
    import zipfile as zf_mod

    scan_dir = Path(tempfile.mkdtemp(prefix="der_fontscan_"))
    with zf_mod.ZipFile(repaired_pptx_path) as zf:
        zf.extractall(scan_dir)
    families = fonts_mod.scan_typefaces(scan_dir)
    work_fonts_dir = out_dir / "_fonts"
    font_status = fonts_mod.ensure_fonts_available(families, work_fonts_dir, allow_network_fetch=allow_network_fetch)
    report["fonts_used"] = sorted(families)
    report["font_status"] = font_status

    # --- convert to PDF ---
    # Render a letter-spacing-neutralized copy, not the repaired pptx
    # itself — see render_workaround.py for why. The returned .pptx keeps
    # its original spc values; only this throwaway copy is altered.
    render_copy_path, spc_removed = render_workaround.make_render_copy(repaired_pptx_path)
    report["letter_spacing_workaround"] = {
        "attributes_neutralized_for_pdf_only": spc_removed,
        "note": (
            "LibreOffice clips the trailing characters of any text run with a:rPr spc set "
            "(letter-spacing/tracking), regardless of how much room the containing shape has. "
            "Neutralized for the PDF render only; the repaired .pptx below keeps the original "
            "letter-spacing intact for editing in PowerPoint/Keynote/Google Slides."
        ) if spc_removed else "No letter-spacing attributes found; workaround was a no-op.",
    }

    pdf_path = out_dir / (repaired_pptx_path.stem + ".pdf")
    try:
        produced = soffice.convert_to_pdf(str(render_copy_path), str(out_dir), fonts_dir=str(work_fonts_dir))
        produced.rename(pdf_path)
        report["pdf_path"] = str(pdf_path)
        report["pdf_conversion_ok"] = True
    except RuntimeError as exc:
        report["pdf_conversion_ok"] = False
        report["pdf_conversion_error"] = str(exc)
        return report
    finally:
        render_copy_path.unlink(missing_ok=True)

    # --- validate output ---
    validation = validate_pdf_mod.validate_pdf(str(pdf_path), expected_page_count=slide_count)
    report["validation"] = dataclasses.asdict(validation)

    return report


def repair_html(resolved: unpack.ResolvedInput, out_dir: Path) -> dict:
    import convert_html

    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"input_kind": "html", "source_note": resolved.source_note, "structural_repair": "not_applicable_best_effort_path"}
    pdf_path = out_dir / (resolved.primary_path.stem + ".pdf")
    try:
        convert_html.convert_html_to_pdf(resolved.primary_path, pdf_path)
        report["pdf_path"] = str(pdf_path)
        report["pdf_conversion_ok"] = True
        validation = validate_pdf_mod.validate_pdf(str(pdf_path), expected_page_count=validate_pdf_mod.fitz.open(str(pdf_path)).page_count)
        report["validation"] = dataclasses.asdict(validation)
    except Exception as exc:  # noqa: BLE001 - surface any failure in the report rather than crashing
        report["pdf_conversion_ok"] = False
        report["pdf_conversion_error"] = str(exc)
    return report


def pass_through_pdf(resolved: unpack.ResolvedInput, out_dir: Path) -> dict:
    import shutil

    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / resolved.primary_path.name
    shutil.copy2(resolved.primary_path, dest)
    validation = validate_pdf_mod.validate_pdf(str(dest), expected_page_count=validate_pdf_mod.fitz.open(str(dest)).page_count)
    return {
        "input_kind": "pdf",
        "source_note": resolved.source_note,
        "structural_repair": "not_possible_no_source_file",
        "pdf_path": str(dest),
        "validation": dataclasses.asdict(validation),
    }


def render_markdown_report(report: dict) -> str:
    lines = ["# Design export repair report", ""]
    kind = report.get("input_kind", "unknown")
    lines.append(f"**Input type detected:** `{kind}`")
    if report.get("source_note"):
        lines.append(f"**Note:** {report['source_note']}")
    lines.append("")

    if kind == "pptx":
        ct_before = report.get("content_types_before", {})
        ct_after = report.get("content_types_after", {})
        lines.append("## 1. Package structure ([Content_Types].xml)")
        if ct_before.get("missing_parts"):
            lines.append(f"- Found {len(ct_before['missing_parts'])} declared part(s) with no matching file in the archive:")
            for p in ct_before["missing_parts"]:
                lines.append(f"  - `{p}`")
            lines.append(f"- After repair: {'fixed — manifest now matches the actual archive contents' if report.get('content_types_fixed') else 'STILL PRESENT — needs manual investigation'}")
        else:
            lines.append("- No dangling part declarations found. Package structure was already consistent.")
        lines.append("")

        lines.append("## 2. Off-canvas shapes")
        changes = report.get("geometry_changes", [])
        flags = report.get("geometry_flags_for_manual_review", [])
        if changes:
            lines.append(f"- Repositioned/resized {len(changes)} shape(s) that extended past the slide boundary:")
            for c in changes:
                lines.append(f"  - Slide {c['slide_index']}, \"{c['shape_name']}\" ({c['strategy']}): {c['before']} → {c['after']}")
                if c.get("note"):
                    lines.append(f"    {c['note']}")
        else:
            lines.append("- No shapes were found extending past the slide boundary.")
        if flags:
            lines.append(f"- {len(flags)} shape(s) inside groups were flagged for manual review (not auto-fixed, see references/defect-classes.md):")
            for f in flags:
                lines.append(f"  - Slide {f['slide_index']}: {f['shape_name']}")
        lines.append("")

        lines.append("## 3. Fonts")
        font_status = report.get("font_status", {})
        if font_status:
            for name, info in font_status.items():
                lines.append(f"- **{name}**: {info['status']} — {info['detail']}")
        else:
            lines.append("- No custom fonts detected.")
        lines.append("")

        lines.append("## 4. Letter-spacing / LibreOffice text clipping")
        spc = report.get("letter_spacing_workaround", {})
        if spc.get("attributes_neutralized_for_pdf_only"):
            lines.append(f"- {spc['attributes_neutralized_for_pdf_only']} tracked/letter-spaced text run(s) found. {spc['note']}")
        else:
            lines.append(f"- {spc.get('note', 'No letter-spacing attributes found.')}")
        lines.append("")

    lines.append("## Output")
    if report.get("pdf_conversion_ok"):
        lines.append(f"- PDF: `{report.get('pdf_path')}`")
    else:
        lines.append(f"- PDF conversion FAILED: {report.get('pdf_conversion_error', 'unknown error')}")
    if report.get("repaired_pptx_path"):
        lines.append(f"- Repaired PPTX: `{report['repaired_pptx_path']}`")

    validation = report.get("validation")
    if validation:
        lines.append("")
        lines.append("## PDF validation")
        lines.append(f"- Page count: {validation['page_count']} (expected {validation['expected_page_count']}) — {'OK' if validation['page_count_ok'] else 'MISMATCH'}")
        if validation.get("blank_pages"):
            lines.append(f"- Possibly-blank pages (verify these are intentional, e.g. section dividers): {validation['blank_pages']}")
        if validation.get("edge_overflow"):
            lines.append(f"- {len(validation['edge_overflow'])} text block(s) still touch/cross a page edge:")
            for o in validation["edge_overflow"]:
                lines.append(f"  - Page {o['page']}: \"{o['text']}\"")
        else:
            lines.append("- No text blocks touch or cross a page edge.")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Repair a Claude Design export and produce a clean PDF/PPTX.")
    parser.add_argument("input", help="Path to the export: .zip, .pptx, or .pdf")
    parser.add_argument("--out-dir", default="./design-export-repair-output", help="Where to write outputs")
    parser.add_argument("--no-network", action="store_true", help="Don't attempt to fetch missing fonts from the web")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    resolved = unpack.resolve_input(args.input, work_dir)
    print(f"Detected input kind: {resolved.kind}\n{resolved.source_note}")

    if resolved.kind == "pptx":
        report = repair_pptx(resolved.primary_path, out_dir, allow_network_fetch=not args.no_network)
    elif resolved.kind == "html":
        report = repair_html(resolved, out_dir)
    elif resolved.kind == "pdf":
        report = pass_through_pdf(resolved, out_dir)
    else:
        print(f"ERROR: could not identify a repairable payload in {args.input}. {resolved.source_note}", file=sys.stderr)
        sys.exit(2)

    report["source_note"] = report.get("source_note", resolved.source_note)

    (out_dir / "repair_report.json").write_text(json.dumps(report, indent=2, default=str))
    md = render_markdown_report(report)
    (out_dir / "repair_report.md").write_text(md)

    print("\n" + md)

    if report.get("pdf_conversion_ok") is False:
        sys.exit(1)


if __name__ == "__main__":
    main()
