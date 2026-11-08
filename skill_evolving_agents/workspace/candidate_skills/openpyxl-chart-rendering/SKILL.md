---
name: openpyxl-chart-rendering
description: Build and style openpyxl charts with typed drawing objects, repairing plain-dict styling failures by mapping each chart element to GraphicalProperties, LineProperties, and color descriptors, then regenerate and render the workbook to confirm the fix.
---

# Openpyxl chart rendering

## Overview

Style openpyxl charts with the typed drawing objects that the serializer
actually accepts, and prove the result by regenerating the workbook and
rendering it. This skill covers series lines and fills, the chart area, the
plot area, and axis formatting, plus multi-ring doughnut charts whose per-point
labels must be composed from two category dimensions. The deliverable is a
working workbook and observable render evidence: completion requires rendered
evidence of each label layer, not a successful Python exit.

## When to Use

Use this skill when any one of these is true:

- A chart assignment or save raises a type error such as
  `GraphicalProperties.ln should be <class 'openpyxl.drawing.line.LineProperties'> but value is <class 'dict'>`.
- You are about to set a chart style attribute to a dict, a nested mapping, or
  a raw XML-like fragment.
- A chart was styled or patched but the original generation command, the
  render command, or both have not been rerun since the change.
- You need to build a styled chart and show that the workbook opens and
  renders rather than only that the Python process exited.
- The request involves a nested or multi-level doughnut or ring chart with
  more than one ring, or a doughnut whose slices must be grouped by a parent
  category.
- Two-level category headers in the sheet must become per-point labels inside
  the chart.
- The user asks to make chart labels editable in Excel, meaning real chart
  label objects rather than text boxes or a flattened image.

## Do Not Use

Do not use this skill for cell, table, or conditional-format styling that does
not involve a chart. Do not use it for matplotlib, seaborn, or image-editing
work. Do not use it for broad hand-editing of chart parts, styles, or workbook
XML inside the `.xlsx` zip; that remains out of scope. A narrow exception is
allowed: after `openpyxl` has saved the workbook, targeted injection of chart
`dLbl` elements is permitted when openpyxl exposes no supported attribute for
the required label text. Limit that injection to per-point label runs and leave
unrelated chart parts, styles, and workbook XML untouched. For a request that
only inspects chart data with no styling or render check, answer directly.

## Workflow

1. Reproduce the baseline before editing. Run the exact generation command and,
   separately, the render command. Capture the first traceback or the render
   exit code and stderr. Do not start from a file whose provenance is unknown.
2. Locate the failing element: series, chart area, plot area, or axis. Read the
   error's attribute path (for example `GraphicalProperties.ln`) to identify
   which parent owns it.
3. Replace the leaf value with a typed instance; never pass the mapping itself.
   Assign the typed object to the documented attribute:

   | Target | Attribute | Typed value |
   | --- | --- | --- |
   | Series line, marker, or fill | `series.graphicalProperties` | `GraphicalProperties(ln=LineProperties(...), solidFill=...)` |
   | Chart area | `chart.graphical_properties` | `GraphicalProperties(solidFill=..., ln=LineProperties(...))` |
   | Plot area | `chart.plot_area.graphicalProperties` | `GraphicalProperties(...)` |
   | Axis line | `axis.graphicalProperties` or `axis.spPr` | `GraphicalProperties(ln=LineProperties(...))` |
   | Axis text | `axis.txPr` | `RichText`, `Paragraph`, `CharacterProperties` |

   Note the spelling difference: the chart uses `graphical_properties`, while
   series, plot area, and axes use `graphicalProperties`.
4. Construct styles from the typed leaves. Import `GraphicalProperties` from
   `openpyxl.chart.shapes` and `LineProperties` from
   `openpyxl.drawing.line`. Pass colors as six-digit hex strings without `#`.
   Width `w` is in EMU (12700 EMU = 1 point). Use `noFill=True` on
   `LineProperties` for an invisible line; do not use `solidFill=None` to mean
   "no line".
5. Regenerate the workbook from the original source with the corrected code.
   Do not patch the saved `.xlsx` and treat that as the fix.
6. Re-run the original full generate-plus-render command unchanged, for
   example `soffice -env:UserInstallation=file:///tmp/lo-profile --headless --convert-to pdf --outdir <outdir> <workbook>`. Require exit code 0 and a non-empty
   output artifact. If the render exits nonzero, read stderr, fix the typed
   assignment, and repeat from step 5.
7. Report the modified workbook, the typed replacements, and the render
   evidence. Do not claim completion from a patched file or from a successful
   save alone.

### Multi-level doughnut labels

Use this sequence when two category dimensions must appear as per-point label
text on concentric rings. It is the minimal path that produces a label a user
can click and edit in Excel.

1. Read both category dimensions and the per-series values from the worksheet
   by cell reference, not from a copied output workbook. Keep the rows in sheet
   order: the inner dimension is the parent group, the outer dimension is the
   slice within that group.
2. Build one `DoughnutChart` with one `Series` per ring, first series
   innermost. Give slices that share a parent the same color by setting each
   `DataPoint(idx=i)` fill from the parent category, so ring boundaries line up
   with the parent groups. Set `holeSize` explicitly and keep the series in
   ring order rather than relying on defaults.
3. Set each series' label flags explicitly with
   `DataLabelList(showVal=False, showCatName=False, showSerName=False, showLegendKey=False)`.
   The injected text is the only thing that must render.
4. Save the workbook with `wb.save(path)`. Do not stop here and do not open
   the saved file to patch it by hand later; keep the work in the generation
   script.
5. Immediately after the save, reopen the saved chart part from the zip
   (`xl/charts/chart1.xml` or the matching `chartN.xml`) and append one `c:dLbl`
   per point to each `c:ser`'s `c:dLbls` element. `openpyxl.chart.label.DataLabel`
   rejects a `tx` keyword, so arbitrary text cannot be authored through the
   typed object; the rich-text runs must be written here instead. Match
   `c:ser` by its index in the chart and set `c:idx` to the point index. Compose
   each label from the inner category name, the outer category name, and the
   value, for example `Q1 / North / 42`, and XML-escape it:

   ```python
   from xml.sax.saxutils import escape
   label = f"{inner_name} / {outer_name} / {value}"
   xml = (
       f'<c:dLbl xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"'
       f' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
       f'<c:idx val="{point_index}"/>'
       f'<c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r>'
       f'<a:rPr lang="en-US"/><a:t>{escape(label)}</a:t></a:r></a:p></c:rich></c:tx>'
       f'<c:showLegendKey val="0"/><c:showVal val="0"/>'
       f'<c:showCatName val="0"/><c:showSerName val="0"/>'
       f'</c:dLbl>'
   )
   ```

   Parse the fragment and append it to `c:dLbls`. When that element is absent,
   add `<c:dLbls>` with the same four `show*` flags as a child of `c:ser` in
   schema order (after the `c:dPt` entries and before `c:cat`). Rewrite the zip
   preserving every other entry unchanged.
6. Rerun the full generation pipeline, including the injection and the
   LibreOffice PDF or PNG render, after every change. Never patch the output
   workbook in place between runs. Inspect the new render before claiming the
   labels exist.

## Constraints

- Chart style leaves are typed descriptors. A dict raises `TypeError` at
  assignment or during serialization; do not catch and suppress that error.
- `chart.graphical_properties` is `None` by default. Assign a
  `GraphicalProperties()` instance before touching `.line` or `.solidFill`.
- `LineProperties` accepts `solidFill`, `w`, `prstDash`, `cap`, and `cmpd`.
  Colors belong on `solidFill`, not on a nested `fill` dict.
- Keep the chart's data references and series order unchanged while repairing
  style. Regenerate from the same data, not from a copied output file.
- If LibreOffice fails on a shared profile, isolate it with
  `-env:UserInstallation=file:///tmp/lo-profile` rather than deleting user
  configuration.
- Preserve any pre-existing chart styling that is unrelated to the failure.
- For multi-ring doughnuts, one series per visible ring and one `dLbl` per
  point. A series-level label or a single summary label is not a per-point
  label.
- Do not certify a chart from a single closed yes or no question. The verifier
  must name each expected label layer, the source categories behind it, and its
  point count. If an answer conflicts with an earlier detailed inspection,
  reconcile the two before accepting the answer; do not let a one-line "yes"
  overturn enumerated evidence.

## Verification

- The corrected code runs without `TypeError` and saves a workbook.
- `openpyxl.load_workbook(path)` reopens the saved file successfully.
- The full generation command exits 0 from a clean run.
- The full LibreOffice render command exits 0 and writes a non-empty PDF,
  PNG, or other render artifact.
- The rendered output shows the intended line color, width, fill, or axis
  style; inspect the artifact rather than trusting the exit code alone.
- For every multi-ring doughnut, open the render and produce a label ledger:
  the inner ring category count and names, the outer ring point count, the
  exact expected text for each point, and a statement that no label is missing,
  clipped, or overlapping. A per-point screenshot or cropped render is the
  evidence for that statement.
- A "yes" answer with no enumerated labels is unverified. Treat it as a failed
  check and continue the work.
- When a quick check contradicts a prior detailed inspection, reopen the
  rendered image and resolve the contradiction in favor of the observed
  content.
- `evals/evals.json` contains the observed failure-and-recovery case, the
  incomplete-patch near miss, and the missing-label-yes-answer near miss.

## Output Format

Return the workbook path, the exact generation and render commands with their
exit codes, the render artifact path, and a short list of element-to-typed-
object replacements (for example `series line -> LineProperties(solidFill="2F5597", w=28575)`).
Keep the report concise; do not include the full generated source unless asked.

## Limitations

Rendering through LibreOffice approximates Excel and can differ in font
metrics, gradient interpolation, and default theme colors. openpyxl cannot
serialize every Excel chart feature, so some styles have no typed equivalent.
openpyxl's `DataLabel` has no supported `tx` attribute, so arbitrary per-point
label text requires post-save chart XML injection; the typed API cannot author
it. LibreOffice rendering is the practical completion gate because valid chart
XML does not prove the labels are visible, positioned inside their slices, or
readable at the delivered size. Pixel-perfect visual regression is not
guaranteed. The skill verifies that typed drawing objects serialize and render,
not that the chart matches a designer's reference exactly.
