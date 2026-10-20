#!/usr/bin/env python3
"""Split the eight facets until every leaf holds at most 100 skills.

Reads data/processed/skill-labels.jsonl. Writes one leaf path per placement to
data/processed/skill-label-leaves.jsonl and a check summary to
data/processed/skill-label-leaves.md.

A skill keeps its parent label. A finer label is added only when the parent
still has more than 100 skills. The cut order is: semantic child, another
domain, the clone, then a name range of at most 100.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "processed" / "skill-labels.jsonl"
OUT = ROOT / "data" / "processed" / "skill-label-leaves.jsonl"
SUMMARY = ROOT / "data" / "processed" / "skill-label-leaves.md"
MAX_LEAF = 100

ZH = re.compile(r"[\u4e00-\u9fff]")
JA = re.compile(r"[\u3040-\u30ff]")
KO = re.compile(r"[\uac00-\ud7af]")
ES = re.compile(r"\b(para|cuando|usuario|habilidad|debe|análisis|proyecto)\b", re.I)
PT = re.compile(r"\b(você|quando|habilidade|usuário|para o)\b", re.I)

JOB_CHILD = {
    "methodology": [
        ("plan", re.compile(r"\b(plans?|planning|roadmap)\b", re.I)),
        ("brainstorm", re.compile(r"\bbrainstorm\w*\b", re.I)),
        ("debug", re.compile(r"\bdebug\w*\b", re.I)),
        ("tdd", re.compile(r"\b(tdd|test-driven|red-green)\b", re.I)),
        ("workflow", re.compile(r"\b(workflow|playbook|procedure)\b", re.I)),
    ],
    "verification": [
        ("audit", re.compile(r"\baudit\w*\b", re.I)),
        ("evidence", re.compile(r"\b(evidence|proof)\b", re.I)),
        ("test", re.compile(r"\b(tests?|qa)\b", re.I)),
        ("browser-check", re.compile(r"\b(playwright|cypress|dogfood)\b", re.I)),
        ("eval", re.compile(r"\bevals?\b", re.I)),
        ("lint", re.compile(r"\b(lint|typecheck)\b", re.I)),
    ],
    "reflection": [
        ("review", re.compile(r"\breview\w*\b", re.I)),
        ("critique", re.compile(r"\bcritique\b", re.I)),
        ("postmortem", re.compile(r"\b(postmortem|retrospect\w*|lessons? learned)\b", re.I)),
    ],
    "repo-understanding": [
        ("architecture", re.compile(r"\barchitecture\b", re.I)),
        ("onboard", re.compile(r"\bonboard\w*\b", re.I)),
        ("walkthrough", re.compile(r"\bwalkthrough\b", re.I)),
        ("map", re.compile(r"\b(graphify|knowledge graph)\b", re.I)),
    ],
    "build": [
        ("generate", re.compile(r"\bgenerat\w*\b", re.I)),
        ("implement", re.compile(r"\bimplement\w*\b", re.I)),
        ("scaffold", re.compile(r"\bscaffold\w*\b", re.I)),
    ],
    "operate": [
        ("automate", re.compile(r"\bautomat\w*\b", re.I)),
        ("monitor", re.compile(r"\bmonitor\w*\b", re.I)),
        ("schedule", re.compile(r"\bschedul\w*\b", re.I)),
    ],
    "integrate": [
        ("mcp", re.compile(r"\bmcp\b", re.I)),
        ("api", re.compile(r"\bapi\b", re.I)),
        ("sdk", re.compile(r"\bsdk\b", re.I)),
    ],
    "analyze": [
        ("diagnose", re.compile(r"\bdiagnos\w*\b", re.I)),
        ("compare", re.compile(r"\bcompar\w*\b", re.I)),
        ("calculate", re.compile(r"\bcalculat\w*\b", re.I)),
    ],
    "configure": [
        ("setup", re.compile(r"\b(set ?up|configur\w*)\b", re.I)),
        ("deploy", re.compile(r"\bdeploy\w*\b", re.I)),
        ("install", re.compile(r"\binstall\w*\b", re.I)),
    ],
    "author": [
        ("copy", re.compile(r"\b(copywrit\w*|blog)\b", re.I)),
        ("draft", re.compile(r"\bdraft\w*\b", re.I)),
        ("outreach", re.compile(r"\b(outreach|newsletter)\b", re.I)),
    ],
    "discovery": [
        ("route", re.compile(r"\b(which skill|skill-router|router over)\b", re.I)),
        ("install", re.compile(r"\b(find-skills|install skills)\b", re.I)),
    ],
}

DOMAIN_CHILD = {
    "software": [
        ("python", re.compile(r"\bpython\b", re.I)),
        ("typescript", re.compile(r"\btypescript\b", re.I)),
        ("javascript", re.compile(r"\bjavascript\b", re.I)),
        ("java", re.compile(r"\bjava\b", re.I)),
        ("go", re.compile(r"\b(golang|\bgo\b)\b", re.I)),
        ("rust", re.compile(r"\brust\b", re.I)),
    ],
    "ai": [
        ("agent", re.compile(r"\bagents?\b", re.I)),
        ("model", re.compile(r"\bmodels?\b", re.I)),
        ("prompt", re.compile(r"\bprompts?\b", re.I)),
        ("llm", re.compile(r"\bllms?\b", re.I)),
        ("rag", re.compile(r"\brag\b", re.I)),
    ],
    "security": [
        ("auth", re.compile(r"\bauth\w*\b", re.I)),
        ("secret", re.compile(r"\bsecrets?\b", re.I)),
        ("threat", re.compile(r"\bthreat\w*\b", re.I)),
        ("pentest", re.compile(r"\bpentest\w*\b", re.I)),
        ("cve", re.compile(r"\bcve\b", re.I)),
    ],
    "data": [
        ("metrics", re.compile(r"\bmetrics?\b", re.I)),
        ("analytics", re.compile(r"\banalytics\b", re.I)),
        ("dashboard", re.compile(r"\bdashboard\w*\b", re.I)),
        ("notebook", re.compile(r"\bnotebook\w*\b", re.I)),
        ("etl", re.compile(r"\betl\b", re.I)),
    ],
    "frontend": [
        ("react", re.compile(r"\breact\b", re.I)),
        ("accessibility", re.compile(r"\b(accessibility|wcag)\b", re.I)),
        ("css", re.compile(r"\bcss\b", re.I)),
        ("vue", re.compile(r"\bvue\b", re.I)),
        ("angular", re.compile(r"\bangular\b", re.I)),
    ],
    "design": [
        ("brand", re.compile(r"\bbrand\w*\b", re.I)),
        ("typography", re.compile(r"\btypography\b", re.I)),
        ("figma", re.compile(r"\bfigma\b", re.I)),
    ],
    "cloud-devops": [
        ("azure", re.compile(r"\bazure\b", re.I)),
        ("aws", re.compile(r"\baws\b", re.I)),
        ("ci", re.compile(r"\bci/?cd\b", re.I)),
        ("kubernetes", re.compile(r"\b(kubernetes|k8s)\b", re.I)),
        ("docker", re.compile(r"\bdocker\b", re.I)),
        ("terraform", re.compile(r"\bterraform\b", re.I)),
    ],
    "finance": [
        ("tax", re.compile(r"\btax\w*\b", re.I)),
        ("investing", re.compile(r"\binvest\w*\b", re.I)),
        ("invoice", re.compile(r"\binvoice\w*\b", re.I)),
        ("accounting", re.compile(r"\baccounting\b", re.I)),
    ],
    "legal": [
        ("compliance", re.compile(r"\bcompliance\b", re.I)),
        ("contract", re.compile(r"\bcontracts?\b", re.I)),
        ("privacy", re.compile(r"\bprivacy\b", re.I)),
    ],
    "marketing": [
        ("seo", re.compile(r"\bseo\b", re.I)),
        ("campaign", re.compile(r"\bcampaign\w*\b", re.I)),
        ("growth", re.compile(r"\bgrowth\b", re.I)),
    ],
    "writing": [
        ("docs", re.compile(r"\b(documentation|readme)\b", re.I)),
        ("blog", re.compile(r"\bblogs?\b", re.I)),
    ],
    "databases": [
        ("sql", re.compile(r"\bsql\b", re.I)),
        ("postgres", re.compile(r"\bpostgres\w*\b", re.I)),
        ("redis", re.compile(r"\bredis\b", re.I)),
    ],
    "testing": [
        ("playwright", re.compile(r"\bplaywright\b", re.I)),
        ("qa", re.compile(r"\bqa\b", re.I)),
        ("jest", re.compile(r"\bjest\b", re.I)),
        ("pytest", re.compile(r"\bpytest\b", re.I)),
    ],
    "media": [
        ("video", re.compile(r"\bvideo\b", re.I)),
        ("image", re.compile(r"\bimage\b", re.I)),
        ("audio", re.compile(r"\baudio\b", re.I)),
    ],
    "mobile": [
        ("ios", re.compile(r"\bios\b", re.I)),
        ("android", re.compile(r"\bandroid\b", re.I)),
        ("expo", re.compile(r"\bexpo\b", re.I)),
        ("react-native", re.compile(r"\breact native\b", re.I)),
    ],
    "commerce": [
        ("checkout", re.compile(r"\bcheckout\b", re.I)),
        ("shopify", re.compile(r"\bshopify\b", re.I)),
        ("catalog", re.compile(r"\bcatalog\w*\b", re.I)),
    ],
}

FORM_CHILD = {
    "technique": [
        ("loop", re.compile(r"\b(loop|red-green|iterate)\b", re.I)),
        ("steps", re.compile(r"\b(step-by-step|steps)\b", re.I)),
        ("checklist", re.compile(r"\b(checklist|atomic)\b", re.I)),
    ],
    "pattern": [
        ("constraint", re.compile(r"\b(constraint|avoid|never)\b", re.I)),
        ("convention", re.compile(r"\b(convention|guideline)\b", re.I)),
        ("principle", re.compile(r"\b(principle|mindset)\b", re.I)),
    ],
    "reference": [
        ("schema", re.compile(r"\bschema\b", re.I)),
        ("api", re.compile(r"\bapi\b", re.I)),
        ("cli", re.compile(r"\bcli\b", re.I)),
    ],
}

ARTIFACTS = [
    ("slides", re.compile(r"\b(pptx|powerpoint|slides?|slide deck|deck|keynote)\b", re.I)),
    ("html", re.compile(r"\bhtml\b", re.I)),
    ("document", re.compile(r"\b(docx|pdf|word document)\b", re.I)),
    ("spreadsheet", re.compile(r"\b(xlsx|spreadsheet|csv)\b", re.I)),
    ("video", re.compile(r"\b(video|mp4|remotion)\b", re.I)),
    ("image", re.compile(r"\b(image|png|svg|diagram)\b", re.I)),
    ("code-change", re.compile(r"\b(patch|diff|pull request)\b", re.I)),
]

PRODUCTS = [
    ("mcp", re.compile(r"\bmcp\b", re.I)),
    ("composio", re.compile(r"\bcomposio\b", re.I)),
    ("azure", re.compile(r"\bazure\b", re.I)),
    ("google", re.compile(r"\bgoogle\b", re.I)),
    ("claude", re.compile(r"\bclaude\b", re.I)),
    ("react", re.compile(r"\breact\b", re.I)),
    ("github", re.compile(r"\bgithub\b", re.I)),
    ("aws", re.compile(r"\baws\b", re.I)),
    ("linkedin", re.compile(r"\blinkedin\b", re.I)),
    ("notion", re.compile(r"\bnotion\b", re.I)),
    ("youtube", re.compile(r"\byoutube\b", re.I)),
    ("openai", re.compile(r"\bopenai\b", re.I)),
    ("instagram", re.compile(r"\binstagram\b", re.I)),
    ("tiktok", re.compile(r"\btiktok\b", re.I)),
    ("shopify", re.compile(r"\bshopify\b", re.I)),
    ("figma", re.compile(r"\bfigma\b", re.I)),
    ("slack", re.compile(r"\bslack\b", re.I)),
    ("stripe", re.compile(r"\bstripe\b", re.I)),
]


def slug(text: str) -> str:
    text = text.strip().lower().replace("/", "--")
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9.+_-]", "", text)
    return text or "unnamed"


def first_match(rules: list[tuple[str, re.Pattern[str]]], blob: str) -> str:
    for name, rx in rules:
        if rx.search(blob):
            return name
    return "rest"


def language_of(blob: str) -> str:
    if ZH.search(blob):
        return "zh"
    if JA.search(blob):
        return "ja"
    if KO.search(blob):
        return "ko"
    if PT.search(blob):
        return "pt"
    if ES.search(blob):
        return "es"
    return "en"


def audience_of(blob: str) -> str:
    if re.search(r"\b(eli5|beginner|plain english|plain language|caveman|for humans)\b", blob, re.I):
        return "beginner"
    if re.search(r"\b(executive|c-suite|stakeholder|leadership)\b", blob, re.I):
        return "executive"
    if re.search(r"\b(expert|advanced)\b", blob, re.I):
        return "expert"
    return "unspecified"


def artifact_of(blob: str) -> str:
    for name, rx in ARTIFACTS:
        if rx.search(blob):
            return name
    return "none"


def products_of(blob: str) -> list[str]:
    found = [name for name, rx in PRODUCTS if rx.search(blob)]
    return found or ["unbound"]


def other_domain(row: dict, path: list[str]) -> str:
    used = set(path)
    for domain in row["domains"]:
        if domain not in used and domain != "unspecified":
            return domain
    for domain in row["domains"]:
        if domain not in used:
            return domain
    return "unspecified"


def load() -> list[dict]:
    rows = []
    for i, line in enumerate(SRC.open()):
        row = json.loads(line)
        blob = " ".join(
            [
                row["path"].split("/")[-2],
                row.get("name") or "",
                row.get("description") or "",
            ]
        )
        row["id"] = i
        row["blob"] = blob
        row["jobs"] = row["jobs"] or ["none"]
        row["leaf_language"] = language_of(blob)
        row["leaf_audience"] = audience_of(blob)
        row["leaf_artifact"] = artifact_of(blob)
        row["leaf_products"] = products_of(blob)
        rows.append(row)
    return rows


def build(rows: list[dict]) -> tuple[dict[int, dict[str, list[str]]], Counter]:
    placed: dict[int, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    sizes: Counter = Counter()

    def record(facet: str, path: list[str], items: list[dict]) -> None:
        leaf = "/".join(slug(part) for part in path)
        sizes[leaf] = len(items)
        for row in items:
            placed[row["id"]][facet].append(leaf)

    def split(facet: str, path: list[str], items: list[dict], splitters: list) -> None:
        if len(items) <= MAX_LEAF:
            record(facet, path, items)
            return
        for index, splitter in enumerate(splitters):
            groups: dict[str, list[dict]] = defaultdict(list)
            for row in items:
                groups[splitter(row, path)].append(row)
            if len(groups) > 1 and max(len(v) for v in groups.values()) < len(items):
                rest = splitters[index + 1 :]
                for key in sorted(groups):
                    split(facet, path + [key], groups[key], rest)
                return
        ordered = sorted(items, key=lambda row: (row["name"].lower(), row["path"]))
        width = len(str(len(ordered) // MAX_LEAF))
        for block_index, start in enumerate(range(0, len(ordered), MAX_LEAF)):
            block = ordered[start : start + MAX_LEAF]
            record(facet, path + [f"names-{block_index:0{width}d}"], block)

    def child_splitter(table: dict):
        def splitter(row: dict, path: list[str]) -> str:
            for part in reversed(path):
                rules = table.get(part)
                if rules:
                    return first_match(rules, row["blob"])
            return "rest"

        return splitter

    def domain_splitter(row: dict, path: list[str]) -> str:
        return other_domain(row, path)

    def repo_splitter(row: dict, path: list[str]) -> str:
        return row["provenance"].replace("/", "--")

    job_child = child_splitter(JOB_CHILD)
    domain_child = child_splitter(DOMAIN_CHILD)
    form_child = child_splitter(FORM_CHILD)

    def run(facet: str, roots_fn, splitters: list) -> None:
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            for root in roots_fn(row):
                groups[root].append(row)
        for root in sorted(groups):
            split(facet, [facet, root], groups[root], splitters)

    run("job", lambda row: row["jobs"], [job_child, domain_splitter, repo_splitter])
    run("domain", lambda row: row["domains"], [domain_child, repo_splitter])
    run("form", lambda row: [row["form"]], [form_child, domain_splitter, repo_splitter])
    run("artifact", lambda row: [row["leaf_artifact"]], [domain_splitter, repo_splitter])
    run("binding", lambda row: row["leaf_products"], [domain_splitter, repo_splitter])
    run("audience", lambda row: [row["leaf_audience"]], [domain_splitter, repo_splitter])
    run("language", lambda row: [row["leaf_language"]], [domain_splitter, repo_splitter])
    run(
        "provenance",
        lambda row: [row["provenance"].replace("/", "--")],
        [domain_splitter],
    )
    return placed, sizes


def main() -> None:
    rows = load()
    placed, sizes = build(rows)
    over = [leaf for leaf, count in sizes.items() if count > MAX_LEAF]
    if over:
        raise SystemExit(f"{len(over)} leaves exceed {MAX_LEAF}, e.g. {over[:3]}")
    missing = [
        row["path"]
        for row in rows
        if len(placed[row["id"]]) != 8 or any(not placed[row["id"]][facet] for facet in placed[row["id"]])
    ]
    if missing:
        raise SystemExit(f"{len(missing)} skills missing a facet, e.g. {missing[:3]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as fh:
        for row in rows:
            fh.write(
                json.dumps(
                    {
                        "path": row["path"],
                        "name": row["name"],
                        "leaves": placed[row["id"]],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    by_facet: dict[str, list[int]] = defaultdict(list)
    for leaf, count in sizes.items():
        by_facet[leaf.split("/", 1)[0]].append(count)

    lines = [
        "# Skill label leaves",
        "",
        f"Built from `{SRC.relative_to(ROOT)}`. Every leaf holds at most {MAX_LEAF} skills.",
        f"Assignments: `{OUT.relative_to(ROOT)}`.",
        "",
        "Cut order when a node is over 100: semantic child, another domain, the clone, then a name-range block.",
        "",
        "| Facet | Leaves | Largest leaf | Skills placed |",
        "|---|---:|---:|---:|",
    ]
    for facet in ("job", "domain", "form", "artifact", "binding", "audience", "language", "provenance"):
        counts = by_facet[facet]
        placed_n = sum(counts)
        lines.append(f"| {facet} | {len(counts)} | {max(counts)} | {placed_n} |")
    lines += [
        "",
        f"Leaves in total: {len(sizes)}. Largest leaf anywhere: {max(sizes.values())}.",
        "",
    ]
    SUMMARY.write_text("\n".join(lines))
    print(f"skills={len(rows)} leaves={len(sizes)} max={max(sizes.values())}")
    print(f"wrote {OUT}")
    print(f"wrote {SUMMARY}")


if __name__ == "__main__":
    main()
