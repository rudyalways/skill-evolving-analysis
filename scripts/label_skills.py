#!/usr/bin/env python3
"""Assign facet labels to every public_skills/**/SKILL.md.

Reads label ids from config/skill-label-system.yaml and writes
data/processed/skill-labels.jsonl plus data/processed/skill-label-summary.md.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "public_skills"
SCHEMA = ROOT / "config" / "skill-label-system.yaml"
OUT_JSONL = ROOT / "data" / "processed" / "skill-labels.jsonl"
OUT_SUMMARY = ROOT / "data" / "processed" / "skill-label-summary.md"

FORM_RULES = [
    (
        "reference",
        re.compile(
            r"\b(api reference|cli reference|schema|specification|file format|"
            r"command reference|endpoint reference|sdk reference|reference docs?)\b",
            re.I,
        ),
    ),
    (
        "pattern",
        re.compile(
            r"\b(best practices?|guidelines?|principles?|mindset|avoid|do not|"
            r"never |judgment|behavioural|behavioral rules?|taste|conventions?)\b",
            re.I,
        ),
    ),
]

JOB_RULES = [
    (
        "skill-authoring",
        re.compile(
            r"\b(skill-creator|writing-skills|create(?: a| new)? skills?|"
            r"author(?:ing)? skills?|improve(?: a)? skills?|skill description)\b",
            re.I,
        ),
    ),
    (
        "discovery",
        re.compile(
            r"\b(find-skills|discover skills|install skills|which skill|"
            r"skill search|browse skills|discover|router over)\b",
            re.I,
        ),
    ),
    (
        "audience",
        re.compile(
            r"\b(eli5|explain like|plain english|plain language|non-technical|"
            r"beginner|caveman|like i(?:'| a)m 5|for humans)\b",
            re.I,
        ),
    ),
    (
        "output-format",
        re.compile(
            r"\b(html|pptx|powerpoint|slides?|slide deck|deck|pdf|docx|xlsx|"
            r"spreadsheet|word document|keynote|reveal\.js)\b",
            re.I,
        ),
    ),
    (
        "repo-understanding",
        re.compile(
            r"\b(codebase|repository|repositories|walkthrough|onboard\w*|"
            r"architecture|repo-intake|understand(?:ing)? (?:a |the )?(?:code|repo|project)|"
            r"graphify|knowledge graph)\b|\brepo\b",
            re.I,
        ),
    ),
    (
        "verification",
        re.compile(
            r"\b(verif\w*|audit\w*|evals?\b|qa\b|proof|evidence|tdd|test-driven|"
            r"typecheck|lint|playwright|dogfood|before claiming|checks? pass)\b",
            re.I,
        ),
    ),
    (
        "reflection",
        re.compile(
            r"\b(reflect\w*|retrospect\w*|critique|code-review|review\w*|"
            r"discern\w*|postmortem|lessons? learned|look back)\b",
            re.I,
        ),
    ),
    (
        "methodology",
        re.compile(
            r"\b(brainstorm\w*|writing-plans|plans?|planning|workflow|playbook|"
            r"tdd|test-driven|systematic-debugging|debug\w*|methodolog\w*|"
            r"step-by-step|roadmap|procedure|how to proceed|red-green)\b",
            re.I,
        ),
    ),
]

# First match does not stop later matches. Order is specific before broad.
DOMAIN_RULES = [
    ("life-science", re.compile(r"\b(protein|gene|genom\w*|clinical|chembl|pubmed|bioinformatics|molecule|assay|health|医疗|健康)\b", re.I)),
    ("legal", re.compile(r"\b(legal|compliance|gdpr|hipaa|contract|privacy law|regulatory|policy review|advogad\w*|direito|penal|lei\b)\b", re.I)),
    ("finance", re.compile(r"\b(tax|vat|invoice|accounting|ledger|equity|invest\w*|payroll|stripe|billing|dcf|forex|crypto|backtest\w*|commodit\w*)\b", re.I)),
    ("commerce", re.compile(r"\b(shopify|ecommerce|e-commerce|checkout|storefront|catalog|merchant|cart)\b", re.I)),
    ("games", re.compile(r"\b(game|unity|phaser|gameplay|sprite)\b", re.I)),
    ("education", re.compile(r"\b(teach|tutor\w*|course|lesson|curriculum|exercises?|learn)\b", re.I)),
    ("media", re.compile(r"\b(video|remotion|image|audio|gif|animation|hyperframes|caption)\b", re.I)),
    ("documents", re.compile(r"\b(pptx|powerpoint|docx|xlsx|pdf|spreadsheet|slides?|slide deck|word document|office)\b", re.I)),
    ("design", re.compile(r"\b(figma|brand|canvas|typography|visual design|design system|mockup|design)\b", re.I)),
    ("frontend", re.compile(r"\b(frontend|react|css|tailwind|vue|angular|ui\b|ux\b|accessibility|wcag|html|component|chrome extension|viewmodel)\b", re.I)),
    ("mobile", re.compile(r"\b(ios|android|swift|kotlin|react native|expo|mobile app)\b", re.I)),
    ("databases", re.compile(r"\b(postgres|sqlite|redis|mongodb|database|sql\b|schema)\b", re.I)),
    ("data", re.compile(r"\b(analytics|dashboard|dataframe|notebook|metrics?|kpi|dataset|etl|warehouse|data)\b", re.I)),
    ("security", re.compile(r"\b(security|pentest|owasp|vulnerabilit\w*|threat|auth\w*|secrets?|cve)\b", re.I)),
    ("testing", re.compile(r"\b(test\w*|qa\b|playwright|cypress|jest|pytest|tdd|lint)\b", re.I)),
    ("cloud-devops", re.compile(r"\b(aws|azure|gcp|kubernetes|k8s|docker|terraform|deploy|ci/?cd|devops|cloud|cloudflare|wrangler)\b", re.I)),
    ("git", re.compile(r"\b(git\b|github|pull request|worktree|commit|merge conflict)\b", re.I)),
    ("marketing", re.compile(r"\b(seo|marketing|growth|campaign|social media|newsletter|xiaohongshu|rednote)\b", re.I)),
    ("writing", re.compile(r"\b(copywriting|blog|prose|documentation|readme|writing|editor|changelog|note-taking)\b", re.I)),
    ("research", re.compile(r"\b(research|paper|arxiv|literature|survey|citation)\b", re.I)),
    ("ai", re.compile(r"\b(llms?|prompts?|mcp|rag|agents?|models?|embeddings?|openai|anthropic|claude|codex|ai)\b", re.I)),
    ("productivity", re.compile(r"\b(notion|slack|email|calendar|lark|feishu|google docs|meeting)\b", re.I)),
    ("business", re.compile(r"\b(sales|crm|hr\b|hiring|odoo|customer|product management|okrs?|competitor)\b", re.I)),
    ("backend", re.compile(r"\b(graphql|rest api|endpoint|backend|server|microservice)\b", re.I)),
    ("systems", re.compile(r"\b(doca|dpdk|bluefield|linux|bash|kernel|nic\b|networking|windows|macos|terminal|shell)\b", re.I)),
    ("software", re.compile(r"\b(code|refactor|function|class|module|python|javascript|typescript|java|rust|golang|debug|build|app\b|project|scaffold|cli\b|sdk|library|framework|error)\b", re.I)),
]


def yaml_ids(text: str, facet: str) -> list[str]:
    """Pull label ids for one facet from the schema without a YAML library."""
    lines = text.splitlines()
    ids: list[str] = []
    in_facet = False
    in_labels = False
    indent_facet = None
    for line in lines:
        if re.match(rf"^  {facet}:\s*$", line):
            in_facet = True
            in_labels = False
            indent_facet = 2
            continue
        if in_facet and re.match(r"^  [a-z].*:\s*$", line) and not line.startswith("    "):
            break
        if in_facet and re.match(r"^    labels:\s*$", line):
            in_labels = True
            continue
        if in_labels:
            m = re.match(r"^      - id: ([a-z0-9-]+)\s*$", line)
            if m:
                ids.append(m.group(1))
    if not ids and facet != "provenance":
        raise SystemExit(f"no labels parsed for facet {facet}")
    return ids


def frontmatter(text: str) -> tuple[str, str]:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    block = m.group(1) if m else ""
    name = ""
    desc = ""
    nm = re.search(r"^name:\s*[\"']?(.*?)[\"']?\s*$", block, re.M)
    if nm:
        name = nm.group(1).strip()
    dm = re.search(r"^description:\s*[|>]-?\s*\n((?:[ \t].*\n)*)", block, re.M)
    if dm:
        desc = re.sub(r"\s+", " ", dm.group(1)).strip()
    else:
        dm = re.search(r"^description:\s*(.+)$", block, re.M)
        if dm:
            desc = dm.group(1).strip().strip("\"'")
    return name, desc


def headings(text: str) -> str:
    body = re.sub(r"^---\n.*?\n---", "", text, count=1, flags=re.S)
    found = re.findall(r"^#{1,3} .+$", body, re.M)
    return "\n".join(found[:40])


def git_root(path: Path) -> Path:
    cur = path.parent
    while cur != CORPUS and cur != cur.parent:
        if (cur / ".git").exists():
            return cur
        cur = cur.parent
    return path.parent


def blob_for(path: Path, text: str) -> tuple[str, str, str]:
    name, desc = frontmatter(text)
    folder = path.parent.name
    blob = "\n".join([folder, name, desc, headings(text)])
    return name or folder, desc, blob


def assign(blob: str) -> tuple[str, list[str], list[str]]:
    form = "technique"
    for label, rx in FORM_RULES:
        if rx.search(blob):
            form = label
            break
    jobs = [label for label, rx in JOB_RULES if rx.search(blob)]
    domains = [label for label, rx in DOMAIN_RULES if rx.search(blob)]
    if not domains and ({"skill-authoring", "discovery"} & set(jobs)):
        domains = ["ai"]
    if not domains:
        domains = ["unspecified"]
    return form, jobs, domains


def main() -> None:
    schema = SCHEMA.read_text()
    expected = {
        "form": yaml_ids(schema, "form"),
        "job": yaml_ids(schema, "job"),
        "domain": yaml_ids(schema, "domain"),
    }
    used_jobs = [i for i, _ in JOB_RULES]
    used_domains = [i for i, _ in DOMAIN_RULES] + ["unspecified"]
    used_forms = [i for i, _ in FORM_RULES] + ["technique"]
    for got, facet in (
        (used_forms, "form"),
        (used_jobs, "job"),
        (used_domains, "domain"),
    ):
        missing = [i for i in expected[facet] if i not in got]
        extra = [i for i in got if i not in expected[facet]]
        if missing or extra:
            raise SystemExit(f"{facet} mismatch missing={missing} extra={extra}")

    rows = []
    for path in sorted(CORPUS.rglob("SKILL.md")):
        if ".git" in path.parts:
            continue
        text = path.read_text(errors="replace")
        name, desc, blob = blob_for(path, text)
        form, jobs, domains = assign(blob)
        repo = git_root(path)
        rel = path.relative_to(CORPUS).as_posix()
        channel = rel.split("/", 1)[0]
        rows.append(
            {
                "path": rel,
                "name": name,
                "description": desc[:400],
                "provenance": repo.relative_to(CORPUS).as_posix(),
                "channel": channel,
                "form": form,
                "jobs": jobs,
                "domains": domains,
            }
        )

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    n = len(rows)
    form_c = Counter(r["form"] for r in rows)
    job_c = Counter(j for r in rows for j in r["jobs"])
    dom_c = Counter(d for r in rows for d in r["domains"])
    job_n = Counter(len(r["jobs"]) for r in rows)
    dom_n = Counter(len(r["domains"]) for r in rows)
    unspecified = dom_c["unspecified"]
    no_job = job_n[0]

    lines = [
        "# Skill label coverage",
        "",
        f"Labeled {n} skills from `{CORPUS.name}` using `{SCHEMA.relative_to(ROOT)}`.",
        f"Assignments: `{OUT_JSONL.relative_to(ROOT)}`.",
        "",
        "Every skill has one provenance, one form, and at least one domain.",
        "Job labels are optional and a skill may have several.",
        "",
        "## Form",
        "",
        "| Label | Skills |",
        "|---|---:|",
    ]
    for label, count in form_c.most_common():
        lines.append(f"| {label} | {count} |")
    lines += ["", "## Job", "", f"Skills with no job label: {no_job}.", "", "| Labels on one skill | Skills |", "|---:|---:|"]
    for k in sorted(job_n):
        lines.append(f"| {k} | {job_n[k]} |")
    lines += ["", "| Job | Skills |", "|---|---:|"]
    for label, _ in JOB_RULES:
        lines.append(f"| {label} | {job_c[label]} |")
    lines += ["", "## Domain", "", f"Unspecified: {unspecified} ({unspecified / n:.1%}).", "", "| Labels on one skill | Skills |", "|---:|---:|"]
    for k in sorted(dom_n):
        lines.append(f"| {k} | {dom_n[k]} |")
    lines += ["", "| Domain | Skills |", "|---|---:|"]
    for label, _ in DOMAIN_RULES:
        lines.append(f"| {label} | {dom_c[label]} |")
    lines.append(f"| unspecified | {unspecified} |")
    lines += ["", "## Unspecified sample", ""]
    shown = 0
    for row in rows:
        if "unspecified" in row["domains"]:
            lines.append(f"- `{row['name']}` — {row['description'][:140]}")
            shown += 1
            if shown == 30:
                break
    OUT_SUMMARY.write_text("\n".join(lines) + "\n")
    print(f"skills={n} unspecified={unspecified} no_job={no_job}")
    print(f"wrote {OUT_JSONL}")
    print(f"wrote {OUT_SUMMARY}")


if __name__ == "__main__":
    main()
