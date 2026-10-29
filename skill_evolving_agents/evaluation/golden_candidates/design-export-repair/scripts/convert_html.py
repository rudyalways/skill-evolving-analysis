"""
Best-effort fallback for a Claude Design export that comes as an HTML/CSS/JS
bundle (index.html + assets) rather than a .pptx. This path is NOT backed
by a real defect investigation the way the .pptx path is (repair_pptx.py +
geometry.py + content_types.py were built against an actual broken export
and verified to fix it) — it exists so a zip full of HTML doesn't just fail
outright, applying the generic fixes that most commonly break an
HTML-deck-to-PDF print:

  - `overflow: hidden` on a slide/page container silently clips content
    that would otherwise just scroll on screen — fine in a browser, fatal
    the moment you print, because print has no scrollbar. This is the HTML
    equivalent of defect class 2 (off-canvas shapes) in the pptx path.
  - Browsers only print backgrounds/colors when explicitly told to
    (print-color-adjust / -webkit-print-color-adjust: exact); without it a
    dark-themed deck can print with a white background and invisible
    light-colored text.
  - `@page` size defaults to the browser's page setup, not the deck's
    actual aspect ratio, unless the page explicitly sets one.

If you hit a real broken HTML export, treat this script as a starting
point to extend rather than a finished, battle-tested pipeline the way the
.pptx path is.
"""

import re
from pathlib import Path


PRINT_FIX_CSS = """
<style id="design-export-repair-print-fix">
  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; color-adjust: exact !important; }
  html, body { overflow: visible !important; }
  [class*="slide" i], [class*="page" i], [id*="slide" i] {
    overflow: visible !important;
    page-break-inside: avoid;
    break-inside: avoid;
  }
</style>
"""


def _detect_page_size(html_text: str) -> tuple:
    """Look for an explicit slide/page dimension hint in the markup
    (common in generated decks: a data attribute, inline width/height on
    the root slide container, or a CSS custom property). Falls back to a
    standard 16:9 slide size in inches if nothing is found."""
    m = re.search(r'width["\']?\s*[:=]\s*["\']?(\d{3,5})px["\']?[^}]*height["\']?\s*[:=]\s*["\']?(\d{3,5})px', html_text)
    if m:
        w_px, h_px = int(m.group(1)), int(m.group(2))
        return (w_px / 96, h_px / 96)  # 96 CSS px/in
    return (13.333, 7.5)  # standard 16:9 slide, in inches


def convert_html_to_pdf(html_path: Path, out_pdf_path: Path, fonts_dir: Path | None = None) -> Path:
    from playwright.sync_api import sync_playwright

    html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    width_in, height_in = _detect_page_size(html_text)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri())
        page.add_style_tag(content=PRINT_FIX_CSS)
        page.wait_for_timeout(300)  # let webfonts/late layout settle
        page.pdf(
            path=str(out_pdf_path),
            width=f"{width_in}in",
            height=f"{height_in}in",
            print_background=True,
            margin={"top": "0in", "bottom": "0in", "left": "0in", "right": "0in"},
        )
        browser.close()

    return out_pdf_path
