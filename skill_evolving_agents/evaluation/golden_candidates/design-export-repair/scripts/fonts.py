"""
Font availability repair (defect class 3 — see references/defect-classes.md).

Claude Design decks routinely reference webfonts (Inter, Plus Jakarta Sans,
JetBrains Mono are the ones observed in practice) purely by name, with no
font data embedded in the .pptx. That's normal for a file meant to be
opened in an app that already has those fonts. It becomes a problem the
moment something *else* renders the file to a PDF/image — LibreOffice,
a cloud converter, a CI box — because that renderer almost certainly does
not have "Plus Jakarta Sans" installed and will silently substitute
something else. The substitute has different metrics, so it doesn't just
look wrong: it also changes text wrapping, which can turn a borderline
shape (see geometry.py) from "fine" into "overflowing."

This module makes sure the fonts a deck actually uses are installed where
the PDF renderer will look for them, so the conversion step in
convert.py produces something that matches the design instead of a
best-effort substitute.
"""

import re
import shutil
import subprocess
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_FONTS_DIR = SKILL_ROOT / "assets" / "fonts"

# Fonts that are safe to assume are present on basically any renderer
# (they ship with LibreOffice / are standard Office/Core fonts). Anything
# not in this set gets treated as "needs to be made available."
SAFE_FONTS = {
    "calibri", "calibri light", "arial", "times new roman", "cambria",
    "cambria math", "segoe ui", "verdana", "georgia", "courier new",
    "helvetica", "liberation sans", "liberation serif", "liberation mono",
    "dejavu sans", "dejavu serif", "symbol", "wingdings",
}

# Maps a lowercased family name to the bundled TTF(s) that cover it. Keep
# this in sync with assets/fonts/ — add a family here whenever you drop in
# a new bundled font so ensure_fonts_available() picks it up automatically.
BUNDLED_FAMILIES = {
    "inter": ["Inter.ttf"],
    "plus jakarta sans": ["PlusJakartaSans.ttf", "PlusJakartaSans-Italic.ttf"],
    "jetbrains mono": ["JetBrainsMono-Regular.ttf"],
}

# Placeholder/theme-reference strings that show up in typeface="" attributes
# but aren't real font names (OOXML theme font slots) or are empty.
NOT_A_FONT_NAME = {"", "+mj-lt", "+mn-lt", "+mj-ea", "+mn-ea", "+mj-cs", "+mn-cs"}


def scan_typefaces(unpacked_pptx_dir: Path) -> set[str]:
    """Return the set of distinct Latin-script font family names actually
    used for rendering anywhere in an unpacked .pptx (theme major/minor
    font, and every a:latin typeface on rPr/defRPr/endParaRPr across
    masters, layouts, and slides).

    Deliberately scoped to <a:latin> only, not every typeface="..." in the
    file: every OOXML theme also carries a boilerplate list of ~10
    per-script fallback fonts (<a:font script="Jpan" typeface="..."/>,
    script="Hang", "Thai", "Arab", etc., inside majorFont/minorFont) that
    are only used if the deck actually contains text in that script. For
    an English-language deck those are pure noise — matching them would
    make this skill "fix" font availability for a couple dozen CJK/Indic/
    Southeast-Asian fonts nothing on the slide ever renders with. a:ea and
    a:cs (east-asian / complex-script) typeface overrides on individual
    runs are skipped for the same reason: they only matter for text in
    those scripts, and generators commonly set them to the same value as
    a:latin out of habit even on plain English runs.
    """
    families: set[str] = set()
    latin_re = re.compile(r'<a:latin\b[^>]*?\btypeface="([^"]*)"')
    for xml_file in unpacked_pptx_dir.rglob("*.xml"):
        try:
            text = xml_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in latin_re.finditer(text):
            name = m.group(1).strip()
            if name and name not in NOT_A_FONT_NAME:
                families.add(name)
    return families


def classify_fonts(families: set[str]) -> dict:
    """Split the fonts a deck uses into: already safe, covered by a bundled
    TTF, or unknown (will fall back silently unless fetched from the web)."""
    safe, bundled, unknown = [], [], []
    for name in sorted(families):
        key = name.lower()
        if key in SAFE_FONTS:
            safe.append(name)
        elif key in BUNDLED_FAMILIES:
            bundled.append(name)
        else:
            unknown.append(name)
    return {"safe": safe, "bundled": bundled, "unknown": unknown}


def _try_fetch_from_google_fonts(family: str, dest_dir: Path) -> list[str]:
    """Best-effort: fetch a family Claude didn't ship a copy of, using the
    open google/fonts OFL mirror. Network may not be available wherever
    this skill runs, so failure here is expected and non-fatal — the
    caller just ends up in the same place as if this function didn't
    exist: a logged warning instead of a silent substitution."""
    import urllib.request
    import urllib.parse

    # Only worth attempting for plain ASCII family names — a font family
    # name containing non-Latin characters is never going to be a Google
    # Fonts slug, and building a URL from raw non-ASCII text throws deep
    # inside http.client rather than failing cleanly.
    if not family.isascii():
        return []

    slug = family.lower().replace(" ", "")
    compact = family.replace(" ", "")
    candidates = [
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{slug}/{urllib.parse.quote(compact)}%5Bwght%5D.ttf",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{slug}/{urllib.parse.quote(compact)}-Regular.ttf",
    ]
    saved = []
    for url in candidates:
        try:
            dest = dest_dir / f"{compact}.ttf"
            urllib.request.urlretrieve(url, dest)
            if dest.stat().st_size > 1024:  # got something real, not an error page
                saved.append(str(dest))
                break
            dest.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 - best-effort network fetch, any failure just falls through
            continue
    return saved


def _default_font_install_dir() -> Path:
    """Pick a directory fontconfig already scans by default, so a plain
    `fc-cache -f` is enough to make installed fonts visible — no
    FONTCONFIG_PATH/FONTCONFIG_FILE trickery, which affects *config*
    lookup, not *font* lookup, and silently does nothing useful here.
    `/usr/local/share/fonts` is in the default <dir> list on effectively
    every Linux fontconfig config (confirmed via `fc-match`/fonts.conf at
    build time) and doesn't depend on which user/HOME the renderer runs
    as. Falls back to a per-user XDG font dir if that path isn't
    writable (e.g. running as a non-root user)."""
    import os

    candidate = Path("/usr/local/share/fonts/design-export-repair")
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write_test"
        probe.touch()
        probe.unlink()
        return candidate
    except OSError:
        xdg = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        fallback = xdg / "fonts" / "design-export-repair"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def ensure_fonts_available(families: set[str], work_fonts_dir: Path | None = None, allow_network_fetch: bool = True) -> dict:
    """Install whatever fonts we can for the given family names into a
    directory fontconfig actually scans by default, then refresh the font
    cache so LibreOffice sees them. Returns a per-family status report to
    include in the repair report — this is meant to be visible to the
    user, not just logged, because "your PDF used a substitute font for
    X" is exactly the kind of silent breakage this skill exists to
    surface instead of hide.

    `work_fonts_dir` is accepted for backwards compatibility / explicit
    override but is no longer where the fonts need to end up for
    LibreOffice to find them — see _default_font_install_dir().
    """
    work_fonts_dir = _default_font_install_dir()
    classification = classify_fonts(families)
    status = {}

    for name in classification["safe"]:
        status[name] = {"status": "safe", "detail": "assumed present on any renderer"}

    for name in classification["bundled"]:
        key = name.lower()
        installed = []
        for fname in BUNDLED_FAMILIES[key]:
            src = BUNDLED_FONTS_DIR / fname
            if src.is_file():
                shutil.copy2(src, work_fonts_dir / fname)
                installed.append(fname)
        status[name] = {
            "status": "installed" if installed else "missing_bundled_file",
            "detail": f"copied {', '.join(installed)}" if installed else "expected bundled TTF not found on disk",
        }

    for name in classification["unknown"]:
        fetched = _try_fetch_from_google_fonts(name, work_fonts_dir) if allow_network_fetch else []
        if fetched:
            status[name] = {"status": "fetched", "detail": f"downloaded {fetched[0]} from Google Fonts (OFL)"}
        else:
            status[name] = {
                "status": "fallback",
                "detail": (
                    "not bundled and could not be fetched — the PDF renderer will substitute "
                    "a fallback font for this family, which may shift text position/wrapping"
                ),
            }

    _refresh_font_cache(work_fonts_dir)
    return status


def _refresh_font_cache(fonts_dir: Path) -> None:
    try:
        # Refresh globally (-f forces it even if fontconfig thinks its cache
        # is current) rather than scoped to fonts_dir: fonts_dir is only
        # picked up at all once it's inside a directory fontconfig already
        # scans (see _default_font_install_dir), and a global refresh is
        # cheap and avoids any doubt about scoping.
        subprocess.run(["fc-cache", "-f"], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass
