---
name: openpyxl-chart-rendering
description: Build and style openpyxl charts with typed drawing objects, repairing plain-dict styling failures by mapping each chart element to GraphicalProperties, LineProperties, and color descriptors, then regenerate and render the workbook to confirm the fix.
---

# Openpyxl chart rendering

## Overview

Style openpyxl charts with the typed drawing objects that the serializer
actually accepts, and prove the result by regenerating the workbook and
rendering it. This skill covers series lines and fills, the chart area, the
plot area, and axis formatting, plus the diagnosis and repair of style
attributes that were written as plain dictionaries. The deliverable is a
working workbook and observable render evidence, not a patched binary.

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

## Do Not Use

Do not use this skill for cell, table, or conditional-format styling that does
not involve a chart. Do not use it for matplotlib, seaborn, or image-editing
work. Do not use it to hand-edit chart XML inside the `.xlsx` zip, and do not
use it when the chart must be rendered by Excel-specific features that
openpyxl does not serialize. For a request that only inspects chart data with
no styling or render check, answer directly.

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

## Verification

- The corrected code runs without `TypeError` and saves a workbook.
- `openpyxl.load_workbook(path)` reopens the saved file successfully.
- The full generation command exits 0 from a clean run.
- The full LibreOffice render command exits 0 and writes a non-empty PDF,
  PNG, or other render artifact.
- The rendered output shows the intended line color, width, fill, or axis
  style; inspect the artifact rather than trusting the exit code alone.
- `evals/evals.json` contains the observed failure-and-recovery case and the
  incomplete-patch near miss.

## Output Format

Return the workbook path, the exact generation and render commands with their
exit codes, the render artifact path, and a short list of element-to-typed-
object replacements (for example `series line -> LineProperties(solidFill="2F5597", w=28575)`).
Keep the report concise; do not include the full generated source unless asked.

## Limitations

Rendering through LibreOffice approximates Excel and can differ in font
metrics, gradient interpolation, and default theme colors. openpyxl cannot
serialize every Excel chart feature, so some styles have no typed equivalent.
Pixel-perfect visual regression is not guaranteed. The skill verifies that
typed drawing objects serialize and render, not that the chart matches a
designer's reference exactly.
