"""
OOXML package structure repair (defect class 1 — see
references/defect-classes.md).

A .pptx is a zip of XML parts, and [Content_Types].xml is the manifest
that declares which parts exist and what content type each one is. It is
possible — and, empirically, something Claude Design's export path
sometimes does — for that manifest to declare Override entries for parts
that were never actually written into the zip (observed: ten
slideMasterN.xml declarations with no corresponding files on disk).
PowerPoint tolerates this and may quietly "repair" it on open. Stricter
OOXML consumers (LibreOffice headless, many cloud pptx->pdf converters)
are not guaranteed to be as forgiving, so this can turn into a failed
conversion, dropped slides, or garbled output somewhere downstream — with
no obvious error pointing back at the real cause.

The reliable fix turns out to be simple: python-pptx builds its in-memory
package graph strictly from parts it can actually load and the
relationships that actually connect them, and Presentation.save() then
serializes [Content_Types].xml fresh from that graph — so a normal
load-then-save round trip through python-pptx already drops any dangling
Override that pointed at a part which was never there to begin with.
audit_content_types() exists so the repair report can say precisely what
was wrong and confirm it's gone, rather than silently trusting that the
round trip worked.
"""

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ContentTypesAudit:
    declared_parts: int
    missing_parts: list  # PartNames declared in [Content_Types].xml but absent from the zip
    undeclared_parts: list  # real XML parts present in the zip with no Content_Types coverage at all


_ALWAYS_COVERED_BY_DEFAULT = {".rels"}  # covered by the <Default Extension="rels".../> entry, not an Override


def audit_content_types(pptx_path: Path) -> ContentTypesAudit:
    with zipfile.ZipFile(pptx_path) as zf:
        names = set(zf.namelist())
        try:
            ct_xml = zf.read("[Content_Types].xml").decode("utf-8", errors="ignore")
        except KeyError:
            # No content types part at all is a much more serious problem than
            # this skill tries to auto-fix; surface it plainly instead of guessing.
            return ContentTypesAudit(declared_parts=0, missing_parts=["[Content_Types].xml itself is missing"], undeclared_parts=[])

        declared = set(re.findall(r'PartName="([^"]+)"', ct_xml))
        default_exts = set(re.findall(r'Default Extension="([^"]+)"', ct_xml))

        missing = sorted(p for p in declared if p.lstrip("/") not in names)

        undeclared = []
        for n in names:
            if n in ("[Content_Types].xml",) or n.endswith("/"):
                continue
            part_name = "/" + n
            ext = n.rsplit(".", 1)[-1] if "." in n else ""
            if part_name in declared:
                continue
            if ext in default_exts:
                continue  # covered by a Default Extension entry
            undeclared.append(part_name)

        return ContentTypesAudit(declared_parts=len(declared), missing_parts=missing, undeclared_parts=sorted(undeclared))
