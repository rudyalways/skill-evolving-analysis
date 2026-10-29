# Defect classes this skill fixes

Everything below was found by actually breaking down a real Claude Design
export (an 11-slide `.pptx`, generated under the hood by PptxGenJS) and
comparing a LibreOffice-headless PDF render of the original against a
render of a repaired copy, slide by slide. Three of these were hypotheses
confirmed by inspection; the fourth (or in this case a lot of the actual
visible damage) only showed up once real before/after PDF renders were
compared side by side — worth remembering if you're extending this skill:
"the shape's box looks wrong" and "the export looks wrong" are related but
not the same claim, and only the second one is what the user actually
sees.

## 1. Corrupt package structure ([Content_Types].xml)

**What's wrong:** A `.pptx` is a zip of XML parts. `[Content_Types].xml`
is the manifest — it declares which parts exist and what content type
each one is. The sample export declared `Override` entries for ten
`ppt/slideMasters/slideMasterN.xml` parts (N = 2..11) that were never
actually written into the zip. Only `slideMaster1.xml` exists; every
slide in the deck correctly points at it via its own `.rels`. The other
ten declarations are pure manifest noise — nothing in the package
references them, they just shouldn't be there.

**Why it matters:** PowerPoint is forgiving about this and may quietly
"repair" the file on open without telling you. Stricter OOXML consumers
are not guaranteed to be — a strict XSD validator, a from-scratch parser
in a cloud pptx→pdf API, or an OOXML library with less defensive coding
than what ships in Office, can choke on a manifest that promises parts
that aren't there. This is exactly the kind of thing that produces a
failure with no obvious connection to its cause ("conversion failed" with
no further detail, or slides silently dropped).

**Detection:** `content_types.py::audit_content_types()` parses every
`PartName="..."` in the manifest and checks each one against the zip's
actual file list.

**Fix:** Nothing bespoke needed. `python-pptx` builds its in-memory
package graph strictly from parts it can load and the relationships that
actually connect them; `Presentation.save()` serializes a fresh
`[Content_Types].xml` from that graph. A plain load-then-save round trip
already drops any dangling `Override` that pointed at nothing. Confirmed:
running the sample through `Presentation(path).save(out)` with zero other
changes reduced the declared-parts count from 42 to 32, and all 10 phantom
`slideMasterN.xml` entries were gone. `fix_export.py` re-audits the saved
file afterward and reports before/after counts so this isn't just assumed.

## 2. Off-canvas shape geometry

**What's wrong:** Several shapes per slide — specifically the small
tracked-out "kicker" labels (page footers, section eyebrows) — have a
left offset + width whose sum exceeds the slide's own width, by a
consistent ~731,565 EMU (~0.8in) in the sample. The box is defined wider
than the canvas it's supposed to sit on.

**Why it matters in general:** PowerPoint's on-screen renderer doesn't
clip a shape at the slide edge; the overflow just draws into space that
never gets shown. Renderers that treat the slide as a fixed, precisely-
bounded viewport (which is closer to how a browser or a strict rasterizer
thinks about a "page") are not guaranteed to be as forgiving. This is a
real, worth-fixing structural defect independent of any specific
renderer's quirks — it's just wrong for a shape to be wider than the
canvas it's drawn on, and a different PDF pipeline than the one this
skill happens to test against could clip it for real.

**A caveat worth being honest about:** in the sample deck specifically,
this defect turned out *not* to be the thing actually causing visible
clipping in LibreOffice's render (see #4 below — a different bug was
responsible for essentially all of the visible damage, since these
kicker boxes were ~19.8in wide, so a 0.8in overflow past a 20in-wide
slide left an enormous, unused margin — the short label text inside never
got anywhere near either edge). This skill fixes it anyway, because (a)
it's a genuine defect that could bite in a different rendering pipeline
even though it didn't bite here, and (b) "shape exceeds its canvas" is
the general form of the bug — the specific box that happened to overflow
in the sample is incidental, not the point.

**Detection & fix:** `geometry.py`. For every top-level shape on every
slide, compute the effective right/bottom edge and compare against
`prs.slide_width` / `prs.slide_height`. Translate the shape back inside
the slide when its own size allows it (the safe, zero-distortion fix —
this is what fired on every affected shape in the sample: same size, just
slid left). Fall back to a proportional scale-down (with table columns/
rows scaled to match, so a table's grid stays consistent with its frame)
only when the shape is genuinely larger than the slide itself. Shapes
nested inside a group are flagged for manual review rather than
auto-fixed — see the module docstring in `geometry.py` for why translating
a group child's local coordinates safely is a harder problem than it
looks, and getting it wrong is worse than leaving a rare case alone.

## 3. Missing font embedding

**What's wrong:** The deck references three non-system webfonts — Inter,
Plus Jakarta Sans, JetBrains Mono — via plain `typeface="..."` attributes,
with zero embedded font data anywhere in the package (no
`<p:embeddedFontLst>`). That's normal for a file authored somewhere those
fonts are already installed (a browser, a design tool, a machine with
the Office add-ins that ship them). It's a problem the moment something
*else* — a server, a CI box, a cloud converter — tries to render the file
without those fonts present: the renderer picks a fallback (Calibri /
Liberation Sans / whatever it has) with different glyph widths, which
changes text measurements throughout the deck.

**Detection:** `fonts.py::scan_typefaces()` scans every part's XML for
`<a:latin typeface="...">` — deliberately *only* `<a:latin>`, not every
`typeface="..."` in the file. Every OOXML theme also carries a boilerplate
list of ~10 per-script fallback fonts (`<a:font script="Jpan"
typeface="..."/>`, `script="Hang"`, `"Thai"`, `"Arab"`, etc., inside
`majorFont`/`minorFont`) that only matter if the deck contains text in
that script. Matching every `typeface="..."` attribute (an earlier version
of this scan did) pulled in ~40 CJK/Indic/Southeast-Asian fonts nothing on
an English-language deck ever renders with — pure noise that would have
sent this skill off trying to fetch fonts nobody needed.

**Fix:** `fonts.py::ensure_fonts_available()`. Classifies every font found
into: safe (assumed present everywhere — Calibri, Arial, etc.), bundled
(this skill ships actual OFL-licensed TTFs for Inter / Plus Jakarta Sans /
JetBrains Mono in `assets/fonts/`, since these are the ones observed in
practice), or unknown (attempt a best-effort fetch from the open
`google/fonts` OFL mirror; if that fails — no network, or the font isn't
on Google Fonts — report it plainly as "will render with a fallback"
rather than pretending it was handled).

Fonts get installed to `/usr/local/share/fonts/design-export-repair/`
(falling back to the user's XDG font dir if that's not writable) — a
directory fontconfig already scans by default on essentially every Linux
box — followed by a global `fc-cache -f`. An earlier version of this
tried to point `FONTCONFIG_PATH` at an arbitrary temp directory, which
does nothing useful: that variable controls where fontconfig looks for
*configuration*, not where it looks for *font files*. Confirmed via
`fc-list` before/after: the bundled fonts were invisible to the system
until they landed in a real scanned font directory, at which point
LibreOffice picked them up with zero other changes.

## 4. LibreOffice clips text runs with letter-spacing (`a:rPr spc`)

**What's wrong, and how it was found:** After fixing #1–#3, the repaired
PDF *still* showed the exact same visible symptom the user reported —
short, tracked-out uppercase labels missing their last 1–4 characters
("HOW WE WORK" → "HOW WE WORI", "ONGOING" → "ONGOIN", "MOST POPULAR" →
"MOST POPUL", "SCOPED PER ENGAGEMENT" → "SCOPED PER ENGAGEME"). Since the
containing boxes were confirmed enormous (~19.8in wide, see #2) and the
fonts were confirmed installed and in use (#3), neither of those could be
the cause. A direct A/B test settled it: take an *otherwise completely
untouched* copy of the original broken slide, strip only the `spc="NN"`
attribute (character tracking/letter-spacing, in hundredths of a point)
from every run, and reconvert. Every previously-clipped label rendered in
full, with no other change made. `spc` is the trigger.

**Why it matters:** this is a LibreOffice text-shaping/clip-region bug,
not a document defect — the deck is authored correctly (the box has 15+
inches of unused room; there is no legitimate reason for the text to be
cut). Something in LibreOffice's handling of `a:rPr spc` computes a clip
region that doesn't match where it actually places the tracked-out
glyphs, and the tail end of the run gets cut. It reproduces regardless of
`normAutofit`, box width, anchor, or font, as long as `spc` is set on the
run — meaning **this is the dominant cause of the "text gets cut off"
complaint** in decks that use tracked-out labels (a very common style
choice for eyebrows/kickers/badges in exactly the kind of generated deck
this skill targets), and defect #2's shape-boundary fix does not touch it
at all.

**Fix:** There's no flag to tell LibreOffice to render `spc` correctly, so
`render_workaround.py::make_render_copy()` builds a throwaway copy of the
repaired deck with every `spc="NN"` attribute stripped from slide XML,
and *that* copy — not the deliverable `.pptx` — is what gets fed to
`soffice --convert-to pdf`. The actual repaired `.pptx` this skill hands
back keeps its original letter-spacing untouched, because PowerPoint,
Keynote, and Google Slides don't have this bug — the design's intended
tracking is exactly right for anyone opening the file in one of those. The
trade-off (tracked-out labels render at normal spacing in the PDF only,
not in the editable deck) is real and is called out explicitly in the
repair report rather than changed silently.

If you're extending this skill and hit a case where this workaround
doesn't fully resolve clipping, don't reach straight for "strip more
attributes" — check whether the specific LibreOffice version in use has
fixed this upstream (it's the kind of thing that gets patched), and
consider re-running the A/B test (strip one attribute at a time from a
known-broken slide, reconvert, compare) rather than assuming the same root
cause.

## What this means for a deck you haven't seen before

Defects #1 and #3 are cheap, general, and safe to always run — auditing a
manifest and making sure referenced fonts exist can't make a correct file
worse. Defect #2's shape-boundary fix is also always safe (translate-first
never distorts anything) but, per the caveat above, don't assume fixing it
is what makes an export look right — verify against an actual rendered
PDF, not just the shape geometry, because #4 or something like it may be
the real cause of what you're looking at. If you're diagnosing a new
"broken export" complaint this skill's checks don't catch, the fastest
path is the same one that found #4: convert an untouched copy to PDF,
form a hypothesis about what's different between how it looks and how it
should look, strip/change exactly that one thing in a scratch copy,
reconvert, and compare. Don't guess from the XML alone — LibreOffice's
actual rendering behavior is the ground truth for what an export-to-PDF
user will see, and it doesn't always match what the OOXML looks like it
should do.
