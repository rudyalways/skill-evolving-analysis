"""
Post-conversion validation. The repair steps upstream (content_types.py,
geometry.py, fonts.py) fix known defect classes *before* conversion; this
module checks the actual PDF that came out the other end, so the repair
report reflects reality rather than just "we ran the fixes and assumed it
worked." Three checks, cheapest first:

  1. Page count matches the slide count. A mismatch almost always means
     the converter silently dropped or merged slides.
  2. No unexpectedly blank page. A single blank divider slide is normal;
     several in a row, or one where the source slide clearly had content,
     is a sign the render failed for that slide specifically.
  3. No text bounding box touches/crosses the page edge. This is the
     direct check for defect class 2 (off-canvas shapes) — if geometry.py
     did its job, this should come back clean. If it doesn't, that's a
     real signal the shape-level fix missed something (e.g. a group-nested
     shape that was flagged rather than auto-fixed) and needs a human look.
"""

from dataclasses import dataclass, field

try:
    import pymupdf as fitz  # modern import name
except ImportError:
    import fitz  # older pymupdf releases expose the module as `fitz`


EDGE_TOLERANCE_PT = 1.0  # points; ignore sub-pixel rounding at the page boundary
BLANK_TEXT_LEN_THRESHOLD = 3  # a page with <= this many non-whitespace chars and no images is "blank"


@dataclass
class PdfValidationResult:
    page_count: int
    expected_page_count: int
    page_count_ok: bool
    blank_pages: list = field(default_factory=list)  # 1-indexed page numbers
    edge_overflow: list = field(default_factory=list)  # {"page": n, "bbox": (...), "text": "..."}

    @property
    def ok(self) -> bool:
        return self.page_count_ok and not self.edge_overflow


def validate_pdf(pdf_path: str, expected_page_count: int) -> PdfValidationResult:
    doc = fitz.open(pdf_path)
    try:
        page_count = doc.page_count
        blank_pages = []
        edge_overflow = []

        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            images = page.get_images()
            if len(text) <= BLANK_TEXT_LEN_THRESHOLD and not images:
                blank_pages.append(i)

            pw, ph = page.rect.width, page.rect.height
            for block in page.get_text("dict").get("blocks", []):
                bbox = block.get("bbox")
                if not bbox:
                    continue
                x0, y0, x1, y1 = bbox
                if x0 < -EDGE_TOLERANCE_PT or y0 < -EDGE_TOLERANCE_PT or x1 > pw + EDGE_TOLERANCE_PT or y1 > ph + EDGE_TOLERANCE_PT:
                    snippet = "".join(
                        span.get("text", "")
                        for line in block.get("lines", [])
                        for span in line.get("spans", [])
                    )[:80]
                    edge_overflow.append({"page": i, "bbox": bbox, "text": snippet})

        return PdfValidationResult(
            page_count=page_count,
            expected_page_count=expected_page_count,
            page_count_ok=(page_count == expected_page_count),
            blank_pages=blank_pages,
            edge_overflow=edge_overflow,
        )
    finally:
        doc.close()
