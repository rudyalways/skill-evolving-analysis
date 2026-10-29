"""
Off-canvas shape geometry repair (defect class 2 — see
references/defect-classes.md).

PowerPoint's own on-screen renderer is forgiving about a shape whose box
extends past the slide edge — it just draws the part that's off-canvas
into empty space and nobody notices. Rasterizing renderers (what actually
runs when you "export to PDF" through most non-PowerPoint pipelines) clip
precisely at the slide boundary. So a shape that has *always* been 0.8in
too wide only becomes visibly broken — text sliced off mid-word — at
export time, which is exactly the "looked fine in the app, broken in the
PDF" complaint this skill exists to fix.

Strategy, cheapest-safest first:
  1. Translate only. If the shape's own size is <= the slide's size in
     that dimension, sliding it back inside the slide fixes the overflow
     with zero visual change to the shape itself — no resizing, no
     distortion, nothing for autofit to recompute.
  2. Scale down (fallback). Only reached when the shape is simply larger
     than the slide in some dimension (rare — usually a copy/paste from a
     different-sized template). Scales width and height by the same
     factor so aspect ratio holds, and if the shape is a table, scales
     every column width / row height by that same factor so the table
     stays internally consistent (a table's rendered width comes from its
     <a:tblGrid> column widths, not from the graphicFrame's own extent, so
     resizing one without the other leaves a table box that doesn't match
     its contents).

Shapes nested inside a group are flagged for manual review rather than
auto-fixed: python-pptx exposes child-shape offsets in the group's own
child coordinate space, and correctly mapping that back to slide-absolute
coordinates (and then writing a corrected value back through the group's
chOff/chExt transform) is easy to get subtly wrong in a way that's worse
than leaving a rare, already-cosmetic issue alone. If you hit one, the
report tells you exactly which slide/shape to open and nudge by hand.
"""

from dataclasses import dataclass, field

TOLERANCE_EMU = 3175  # ~0.0035in / ~1/3 pt — filters out rounding noise, not real overflow


@dataclass
class GeometryChange:
    slide_index: int
    shape_name: str
    shape_type: str
    strategy: str
    before: tuple
    after: tuple
    note: str = ""


@dataclass
class GeometryFlag:
    slide_index: int
    shape_name: str
    reason: str


def _overflow(left, top, width, height, slide_w, slide_h):
    over_right = (left + width) - slide_w
    over_bottom = (top + height) - slide_h
    over_left = -left
    over_top = -top
    return over_right, over_bottom, over_left, over_top


def _scale_table(shape, factor: float) -> None:
    """Scale a table's column widths and row heights by `factor` so the
    table's internal grid stays consistent with its resized frame."""
    tbl = shape.table
    for col in tbl.columns:
        col.width = int(col.width * factor)
    for row in tbl.rows:
        row.height = int(row.height * factor)


def fix_slide_geometry(slide, slide_index: int, slide_w: int, slide_h: int) -> tuple[list[GeometryChange], list[GeometryFlag]]:
    changes: list[GeometryChange] = []
    flags: list[GeometryFlag] = []

    for shape in slide.shapes:
        # Skip anything without a normal top-level position (placeholders that
        # inherit position from the layout report None here in python-pptx).
        if shape.left is None or shape.top is None or shape.width is None or shape.height is None:
            continue

        if shape.shape_type is not None and str(shape.shape_type) == "GROUP (6)":
            # See module docstring: intentionally not auto-fixed.
            for child in shape.shapes:
                flags.append(GeometryFlag(
                    slide_index=slide_index,
                    shape_name=f"{shape.name} > {getattr(child, 'name', '?')}",
                    reason="shape is inside a group; skipped auto-fix, review position by hand",
                ))
            continue

        left, top, width, height = shape.left, shape.top, shape.width, shape.height
        over_right, over_bottom, over_left, over_top = _overflow(left, top, width, height, slide_w, slide_h)

        if max(over_right, over_bottom, over_left, over_top) <= TOLERANCE_EMU:
            continue  # within tolerance, nothing to do

        before = (left, top, width, height)
        new_left, new_top, new_width, new_height = left, top, width, height
        strategy = "translate"
        note = ""

        # --- horizontal ---
        if width <= slide_w:
            if over_right > TOLERANCE_EMU:
                new_left = max(0, left - over_right)
            elif over_left > TOLERANCE_EMU:
                new_left = 0
        else:
            strategy = "scale"

        # --- vertical ---
        if height <= slide_h:
            if over_bottom > TOLERANCE_EMU:
                new_top = max(0, top - over_bottom)
            elif over_top > TOLERANCE_EMU:
                new_top = 0
        else:
            strategy = "scale"

        if strategy == "scale":
            factor = min(slide_w / width if width > slide_w else 1.0,
                         slide_h / height if height > slide_h else 1.0)
            factor *= 0.98  # tiny safety margin so the scaled box clears the edge
            new_width = int(width * factor)
            new_height = int(height * factor)
            new_left = 0
            new_top = 0
            note = f"shape ({width}x{height} EMU) exceeded slide size ({slide_w}x{slide_h} EMU); scaled by {factor:.3f}"
            if shape.has_table:
                try:
                    _scale_table(shape, factor)
                    note += "; table columns/rows scaled to match"
                except Exception as exc:  # pragma: no cover - defensive, table API can vary
                    note += f"; WARNING could not scale table grid ({exc}) — table contents may not match frame"

        shape.left, shape.top, shape.width, shape.height = int(new_left), int(new_top), int(new_width), int(new_height)

        changes.append(GeometryChange(
            slide_index=slide_index,
            shape_name=shape.name or f"shape#{shape.shape_id}",
            shape_type=str(shape.shape_type),
            strategy=strategy,
            before=before,
            after=(shape.left, shape.top, shape.width, shape.height),
            note=note,
        ))

    return changes, flags


def fix_presentation_geometry(prs) -> tuple[list[GeometryChange], list[GeometryFlag]]:
    all_changes: list[GeometryChange] = []
    all_flags: list[GeometryFlag] = []
    for i, slide in enumerate(prs.slides, start=1):
        changes, flags = fix_slide_geometry(slide, i, prs.slide_width, prs.slide_height)
        all_changes.extend(changes)
        all_flags.extend(flags)
    return all_changes, all_flags
