"""
LibreOffice-specific render workaround for letter-spacing clipping.

Verified against the real sample export: any text run with an
`<a:rPr spc="N">` (character tracking, in hundredths of a point — a
deliberate, common styling choice for small tracked-out uppercase
"kicker"/label/eyebrow text) gets its trailing 1-4 characters silently
clipped by LibreOffice's headless PDF renderer, even when the containing
shape's box is far wider than the text needs. Confirmed by A/B test:
stripping `spc` from an otherwise-untouched copy of a real broken slide
made every previously-clipped label render in full ("HOW WE WORI" ->
"HOW WE WORK", "ONGOIN" -> "ONGOING", "MOST POPUL" -> "MOST POPULAR",
etc.) This is independent of and *not* fixed by the shape-boundary repair
in geometry.py — those boxes were already many times wider than their
text, so this is a genuine LibreOffice text-layout/clip-rect bug tied to
the spc attribute itself, not a sizing problem this skill can fix by
resizing anything.

There's no way to ask LibreOffice to render `spc` correctly here, so the
fix is to render a spacing-neutralized COPY through LibreOffice, while
leaving the actual returned .pptx untouched — the design's intended
letter-spacing survives for anyone opening the deck in PowerPoint, Keynote,
or Google Slides (none of which have this bug), and the PDF gets to be
legible instead of visually broken. This is a real, visible trade-off
(tracked-out labels render at normal spacing in the PDF only) and the
repair report says so explicitly rather than changing it silently.
"""

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

_SPC_RE = re.compile(r'\s*spc="\d+"')


def make_render_copy(pptx_path: Path) -> tuple[Path, int]:
    """Return (path_to_render_only_copy, number_of_spc_attributes_removed).
    The caller should feed the returned path to the PDF converter and
    discard it afterward — it is not a deliverable, only a rendering aid.
    """
    pptx_path = Path(pptx_path)
    fd, tmp_name = tempfile.mkstemp(suffix=".render.pptx")
    render_path = Path(tmp_name)

    removed = 0
    with zipfile.ZipFile(pptx_path) as src, zipfile.ZipFile(render_path, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.startswith("ppt/slides/slide") and item.filename.endswith(".xml"):
                text = data.decode("utf-8", errors="ignore")
                text, n = _SPC_RE.subn("", text)
                removed += n
                data = text.encode("utf-8")
            out.writestr(item, data)

    import os
    os.close(fd)
    return render_path, removed
