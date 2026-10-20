# Skill label system

> Written 2026-10-05 for the corpus in [`public_skills/`](../../public_skills/).
> 19,716 `SKILL.md` files. A facet is one question. Eight questions are the system.

## What "facet" means

A facet is one question you can ask about a skill, with its own set of answers.

The same file can be a verification procedure, about security, written as steps, required to emit HTML, tied to Azure, aimed at a beginner, written in English, and copied from a community pack. Those are eight questions. Putting them in one list drops all but one.

Job, Domain, and Binding allow several labels. Form, Artifact, Audience, Language, and Provenance take exactly one.

## The eight facets

| Facet | Labels on one skill | What it answers | What problem it solves |
|---|---|---|---|
| Job | many | What work the skill tells the agent to do | A frontend skill can be a checklist, a test gate, or an implementation. |
| Domain | many | What subject that work is about | The same job shows up in security, finance, and slides. |
| Form | one | Whether the text is steps, a judgment, or a lookup | A reference page and a procedure can share a job and a domain. |
| Artifact | one | What file the skill requires the agent to emit | `html-it` and a planning skill can share a job. The required file is a separate question. |
| Binding | many | Which named product the skill is tied to | Domain says cloud or commerce. Binding says Azure, AWS, Figma, or Shopify. |
| Audience | one | Who the words are for | An ELI5 explanation and an expert checklist can share a job. |
| Language | one | Which language the instruction is written in | Chinese and Spanish files are invisible to English word rules. |
| Provenance | one | Which git clone the file came from | The same skill name is copied across packs. |

Each facet below has the same table. **Already assigned** is the count from the run that wrote `skill-labels.jsonl`. A dash means that label is specified here and is not in that file yet. **Newly reached** is how many skills that label covers which the labels above it in the same table did not, and the cumulative share of 19,716.

The tables are the trunk. The [label trees](#label-trees) section splits those labels into sublabels. A file keeps the parent. A sublabel is optional and more specific: `job / verification / audit` still is `job / verification`. On Job, Domain, and Binding a file may carry more than one sublabel. On the one-label facets it carries one leaf, or the parent when no leaf matches.

## Job — 16 labels, covering 91%

The running assignment uses the first 8. Together they touch **13,208 skills (67.0%)**. The next 8 are the rest of the closed set. A probe on folder name plus description, applied only to skills the first 8 miss, reaches **18,020 skills (91.4%)**. The "+skills" column is how many still-unlabeled files that label newly reaches, after the labels above it. One skill can carry several, so the assigned counts in the first block overlap.

**1,696 skills (8.6%)** stay outside this probe. They are product manuals and role packs whose name and description do not use these words.

| Label | What it answers | Already assigned | Newly reached |
|---|---|---:|---:|
| methodology | Order of work: plan, brainstorm, debug loop, TDD | 8,306 | in the 67% |
| verification | Tell the agent how to check work and require a test, an audit, or other evidence | 5,243 | in the 67% |
| reflection | Look back at a draft, a diff, or a decision | 3,078 | in the 67% |
| repo-understanding | Explain, map, or onboard someone through a codebase | 2,454 | in the 67% |
| discovery | Find, choose, or install another skill | 21 | raw word match was 1,203; see below |
| output-format | Require HTML, slides, PDF, a deck, docx, or xlsx. The Artifact facet is the full question | 909 | in the 67% |
| skill-authoring | Create, edit, or evaluate a skill | 64 | in the 67% |
| audience | Name a reader or a voice. The Audience facet is the full question | 58 | in the 67% |
| build | Construct or change software, a feature, or a rendered artifact | — | +1,985 → 77.1% |
| operate | Run, automate, monitor, or schedule a workflow or a product | — | +512 → 79.7% |
| integrate | Call or connect an API, SDK, MCP server, package, library, or CLI | — | +838 → 83.9% |
| author | Write prose, copy, outreach, a resume, or a draft | — | +205 → 84.9% |
| analyze | Examine, diagnose, compare, calculate, or optimize | — | +552 → 87.7% |
| configure | Install, set up, provision, or deploy | — | +146 → 88.5% |
| search | Find, retrieve, rank, or hunt | — | +121 → 89.1% |
| practice | Standing know-how: expert, guidelines, patterns, counsel, a guide | — | +453 → 91.4% |

The probe order is methodology through skill-authoring (already assigned), then build, operate, integrate, author, analyze, configure, search, practice. The running script in [`scripts/label_skills.py`](../../scripts/label_skills.py) assigns the first 8 only. The last 8 are specified here and are not in [`data/processed/skill-labels.jsonl`](../../data/processed/skill-labels.jsonl) yet.

### Verification

Yes. The label means the skill tells the agent how to check a piece of work, and to require a test, an audit, or some other evidence before treating that work as done.

`verification-before-completion` is the clear case: do not claim success until a check has passed. A Playwright skill, a lint gate, and a security audit procedure are the same kind of answer.

The assigned count, 5,243, is wider than that sentence. The script marks a file when the folder name, the description, or a heading contains one of these words: verify, audit, eval, qa, proof, evidence, tdd, typecheck, lint, playwright, dogfood. A file can carry the label because a heading says "Audit" or the description says "evidence," even when checking work is only one step inside a larger skill. 543 of the 5,243 matched on the word "evidence" alone.

| Word that fired | Files |
|---|---:|
| verify* | 2,795 |
| audit* | 1,535 |
| evidence | 966 |
| proof | 211 |
| eval | 154 |
| qa | 135 |
| playwright | 134 |
| tdd | 118 |
| lint | 109 |
| before claiming | 16 |
| typecheck | 5 |
| dogfood | 3 |

One file can fire more than one word, so this column sums past 5,243.

### Discovery

The 1,203 count is the word "discover" in a folder name, a description, or a heading. It is not 1,203 skills for finding other skills.

| What the file actually is | Files |
|---|---:|
| A heading or name that says "discover" about something else (files, sessions, tools, hosts, APIs) | 1,182 |
| A skill whose text is about finding, choosing, or installing another skill | 21 |

732 of the 1,182 are the same copied heading, `### Step 1: Discover Available Tools`. Another 145 files have discovery as their only job label, so dropping the bare word "discover" would leave those files with no job.

The 21 files are 12 names, because the same skill is copied into more than one pack: `ask-matt` (5 copies), `skill-router` (3), `antigravity-skill-orchestrator` (3), `find-skills` (2), plus one each of `skill-issue`, `using-agent-skills`, `skill-lookup`, `find-skill`, `help`, `janitor-discover`, `flowstudio-power-automate-mcp`, and `learn-codebase`.

## Domain — 27 labels, covering 100%

All 27 are already assigned. A skill often carries several, so **Already assigned** sums past 19,716. **Newly reached** counts a skill once, under the first label in this table that it has. The first seven labels reach **90.9%**.

| Label | What it answers | Already assigned | Newly reached |
|---|---|---:|---:|
| software | General programming when no narrower subject is the point | 9,977 | +9,977 → 50.6% |
| ai | Models, prompts, agents, MCP, RAG | 7,890 | +3,926 → 70.5% |
| security | Threats, auth, pentest, vulnerability review | 4,789 | +1,223 → 76.7% |
| unspecified | No subject rule matched | 1,083 | +1,083 → 82.2% |
| data | Analysis, metrics, dashboards, tables, notebooks | 4,250 | +850 → 86.5% |
| design | Visual design, brand, canvas, taste | 2,671 | +501 → 89.1% |
| finance | Tax, accounting, invoices, investing, ledgers | 1,660 | +371 → 90.9% |
| testing | Tests, QA, browsers used to check behavior | 3,235 | +283 → 92.4% |
| writing | Prose, copy, blogs, documentation voice | 2,267 | +246 → 93.6% |
| frontend | Web UI, React, CSS, interface accessibility | 2,334 | +198 → 94.6% |
| business | Sales, HR, CRM, operations, product management | 1,043 | +142 → 95.4% |
| media | Video, image, audio, animation | 1,348 | +118 → 96.0% |
| cloud-devops | AWS, Azure, GCP, Kubernetes, CI, deploy, Terraform | 2,555 | +113 → 96.5% |
| legal | Contracts, compliance, privacy, policy | 1,847 | +97 → 97.0% |
| productivity | Notion, Slack, email, calendar, Feishu/Lark | 1,183 | +93 → 97.5% |
| marketing | SEO, growth, campaigns, social distribution | 1,447 | +84 → 97.9% |
| life-science | Biology, clinical, chemistry, genomics, health | 722 | +74 → 98.3% |
| git | Git, GitHub, pull requests, commits | 1,040 | +74 → 98.7% |
| research | Papers, literature, investigations, surveys | 1,430 | +66 → 99.0% |
| systems | Operating systems, shells, networking, machine-level tools | 1,157 | +62 → 99.3% |
| databases | SQL, Postgres, Redis, schemas | 1,754 | +42 → 99.5% |
| backend | Servers, HTTP APIs, GraphQL | 1,699 | +28 → 99.7% |
| education | Teaching, courses, tutoring | 319 | +20 → 99.8% |
| documents | Office files and decks as the subject | 597 | +19 → 99.9% |
| games | Game design, engines, gameplay | 126 | +19 → 100.0% |
| mobile | iOS, Android, Swift, Kotlin, React Native | 529 | +4 → 100.0% |
| commerce | Stores, checkout, catalogs | 421 | +3 → 100.0% |

Figma sits in design. Shopify sits in commerce. The product name itself is the Binding facet.

## Form — 3 labels, covering 100%

Exactly one. The default is technique. All three are already assigned. Two labels reach 93.2%.

| Label | What it answers | Already assigned | Newly reached |
|---|---|---:|---:|
| technique | A procedure with steps the agent follows | 11,473 | +11,473 → 58.2% |
| pattern | A way of thinking, a constraint, or a judgment, without a fixed procedure | 6,910 | +6,910 → 93.2% |
| reference | Lookup material for an API, a CLI, a schema, or a file format | 1,333 | +1,333 → 100% |

## Artifact — 8 labels, covering 100%

Exactly one. The default is `none`: the skill does not require a particular file. `none` alone is 92.2%. The other seven are the shapes that used to be squeezed into the job label `output-format` (909 files). This probe reads the folder name and the description, and it is not in the jsonl yet.

| Label | What it answers | Already assigned | Newly reached |
|---|---|---:|---:|
| none | No required file shape | — | +18,175 → 92.2% |
| slides | A deck: pptx, PowerPoint, slides, keynote | — | +169 → 93.0% |
| html | An HTML page | — | +218 → 94.1% |
| document | A PDF or a Word file | — | +174 → 95.0% |
| spreadsheet | A sheet or CSV | — | +152 → 95.8% |
| video | A video or a Remotion piece | — | +394 → 97.8% |
| image | An image, SVG, or diagram | — | +297 → 99.3% |
| code-change | A patch, a diff, or a pull request | — | +137 → 100% |

## Binding — labels covering 90%

Many labels. The question is which named product the skill is about. `unbound` means the folder name and description name none of the products below. `unbound` plus nine product names reach **90.1%**. The other 9.9% name a longer tail of products (Shopify, Figma, Slack, Stripe, and the rest). This probe is not in the jsonl yet.

| Label | What it answers | Already assigned | Newly reached |
|---|---|---:|---:|
| unbound | No named product in the folder name or description | — | +13,685 → 69.4% |
| mcp | Tied to MCP | — | +1,622 → 77.6% |
| azure | Tied to Azure | — | +583 → 80.6% |
| google | Tied to Google | — | +460 → 82.9% |
| claude | Tied to Claude | — | +385 → 84.9% |
| react | Tied to React | — | +268 → 86.2% |
| github | Tied to GitHub | — | +225 → 87.4% |
| aws | Tied to AWS | — | +193 → 88.4% |
| linkedin | Tied to LinkedIn | — | +177 → 89.3% |
| notion | Tied to Notion | — | +158 → 90.1% |

## Audience — 4 labels, covering 100%

Exactly one. Most skills never name a reader, so `unspecified` is the covering label at 94.5%. The job label `audience` (58 files) was the stricter ELI5 and plain-language rule. This probe reads the name and description, and it is not in the jsonl yet.

| Label | What it answers | Already assigned | Newly reached |
|---|---|---:|---:|
| unspecified | The skill does not name a reader | — | +18,634 → 94.5% |
| expert | Written for an expert or an advanced reader | — | +922 → 99.2% |
| executive | Written for leadership, an executive, or stakeholders | — | +124 → 99.8% |
| beginner | ELI5, plain language, beginner, or caveman | — | +36 → 100% |

## Language — 5 labels, covering 100%

Exactly one. Read from the name and description. `en` means no other language was detected there. English alone is 97.3%. This probe is not in the jsonl yet.

| Label | What it answers | Already assigned | Newly reached |
|---|---|---:|---:|
| en | English, or no other language detected | — | +19,190 → 97.3% |
| zh | Chinese characters in the name or description | — | +448 → 99.6% |
| es | Spanish wording | — | +60 → 99.9% |
| pt | Portuguese wording | — | +9 → 100.0% |
| ko | Korean characters | — | +9 → 100% |

## Provenance — 8 channels, covering 100%

The stored label is the git clone under `public_skills/`: **273** clones, one per skill. The table is the channel, the first directory. Two channels reach 93.1%. All eight are already assigned.

| Label | What it answers | Already assigned | Newly reached |
|---|---|---:|---:|
| others | Awesome-list repos and the later named clones | 9,177 | +9,177 → 46.5% |
| community | Community packs, including antigravity and `eli5` | 9,170 | +9,170 → 93.1% |
| openai_official | `openai/plugins` and the deprecated `openai/skills` | 580 | +580 → 96.0% |
| social | Packs named on Reddit, Zhihu, and related posts | 491 | +491 → 98.5% |
| platforms | skills.sh leader repos that are on GitHub | 165 | +165 → 99.3% |
| high_stars | superpowers, gstack, karpathy, addyosmani | 104 | +104 → 99.9% |
| anthropic_official | `anthropics/skills` | 20 | +20 → 100.0% |
| popular | `vercel-labs/agent-skills` | 9 | +9 → 100% |

**43 clones hold 90.1% of the files** (17,770 skills). The other 230 clones are the long tail.

| Clone | Skills | Cumulative |
|---|---:|---:|
| community/antigravity-awesome-skills | 8,254 | 41.9% |
| community/awesome-claude-skills | 864 | 46.2% |
| others/mukul975--Anthropic-Cybersecurity-Skills | 818 | 50.4% |
| others/mouadja02--skills | 792 | 54.4% |
| others/openaccountants--openaccountants | 781 | 58.4% |
| others/infrasity-labs--dev-gtm-claude-skills | 588 | 61.4% |
| openai_official/plugins | 536 | 64.1% |
| others/NVIDIA--skills | 399 | 66.1% |
| social/davepoon--buildwithclaude | 393 | 68.1% |
| others/gooseworks-ai--goose-skills | 293 | 69.6% |
| others/lawve-ai--awesome-legal-skills | 269 | 70.9% |
| others/foryourhealth111-pixel--Vibe-Skills | 258 | 72.3% |
| others/sandbaseai--sandbase-skills | 246 | 73.5% |
| others/OneWave-AI--claude-skills | 232 | 74.7% |
| others/makenotion--notion-cookbook | 205 | 75.7% |
| others/NeoLabHQ--context-engineering-kit | 204 | 76.7% |
| others/wanshuiyin--Auto-claude-code-research-in-sleep | 189 | 77.7% |
| others/VoDaiLocz--kilo-kit-mcp | 180 | 78.6% |
| others/K-Dense-AI--scientific-agent-skills | 177 | 79.5% |
| others/kensaurus--cursor-kenji | 171 | 80.4% |
| others/GarethManning--education-agent-skills | 165 | 81.2% |
| others/indranilbanerjee--digital-marketing-pro | 164 | 82.1% |
| others/google--skills | 155 | 82.8% |
| others/aaron-he-zhu--aaron-marketing-skills | 120 | 83.4% |
| others/aeonfun--aeon | 110 | 84.0% |
| others/browser-act--skills | 103 | 84.5% |
| others/Orchestra-Research--AI-Research-SKILLs | 98 | 85.0% |
| others/nowork-studio--notfair-plugin | 96 | 85.5% |
| platforms/microsoft--azure-skills | 86 | 86.0% |
| others/JasonColapietro--suede-creator-skills | 79 | 86.4% |
| others/deanpeters--Product-Manager-Skills | 77 | 86.7% |
| others/LambdaTest--agent-skills | 73 | 87.1% |
| others/alinaqi--maggy | 73 | 87.5% |
| others/phuryn--pm-skills | 69 | 87.8% |
| high_stars/gstack | 63 | 88.2% |
| others/KhazP--vibe-coding-prompt-template | 55 | 88.4% |
| others/xberg-io--xberg | 54 | 88.7% |
| others/bitwize-music-studio--claude-ai-music-skills | 53 | 89.0% |
| others/coreyhaines31--marketingskills | 50 | 89.2% |
| others/chrono-meta--forge-harness | 46 | 89.5% |
| others/dembrandt--dembrandt-skills | 45 | 89.7% |
| openai_official/skills | 44 | 89.9% |
| social/EveryInc--compound-engineering-plugin | 43 | 90.1% |

## Label trees

There are **eight** facets. A semantic leaf is a named concept: a child, or the parent when no child matches. `rest` is that parent’s permanent leftover sibling. Skill count is a column on the node. A large count is a reason to look for a missing name. It is not itself a new label.

The file that cuts every node to 100 skills is a browse index for huge clones. [`scripts/build_label_leaves.py`](../../scripts/build_label_leaves.py) reads the assigned labels and, whenever a node has more than 100 skills, cuts it in this order: semantic child, another domain, the clone, then a name-range block of at most 100. The result is [`data/processed/skill-label-leaves.jsonl`](../../data/processed/skill-label-leaves.jsonl). **16,082 leaves. The largest holds 100 skills.** Every one of the 19,716 skills has a leaf on all eight facets. `names-N` blocks in that file are sort buckets. They are not semantic labels. The semantic rules borrowed from the ads trees are in [Borrowed from the ads verticals](#borrowed-from-the-ads-verticals), after the browse trees.

| Facet | Leaves | Largest leaf | Skills placed |
|---|---:|---:|---:|
| job | 2,744 | 100 | 27,823 |
| domain | 3,927 | 100 | 59,373 |
| form | 2,017 | 100 | 19,716 |
| artifact | 1,694 | 100 | 19,716 |
| binding | 1,702 | 100 | 21,486 |

Job, domain, and binding place a skill once per label, so their skill counts exceed 19,716. The other five facets place each skill once.

## Job tree through depth 5

Counted from [`data/processed/skill-label-leaves.jsonl`](../../data/processed/skill-label-leaves.jsonl), the file [`scripts/build_label_leaves.py`](../../scripts/build_label_leaves.py) wrote. Depth is the path segment.

| Depth | Segment |
|---|---|
| 1 | `job` |
| 2 | the job name, such as `methodology` or `none` |
| 3 | the child, such as `plan` or `rest`, or a domain when that job has no child |
| 4 | the next cut, usually a domain |
| 5 | the clone. A `names-N` block is inside that clone when the clone is still over 100 |

`rest` means the skill has that parent and matched none of the named children. Under `methodology` those children are plan, workflow, debug, tdd, and brainstorm, so `methodology / rest` is the 5,945 methodology skills that use none of those words.

A branch is expanded only while it has at least 100 skills. `… smaller` is the rest of that node's children. Those children are in the jsonl.

```
job  19716 skills, 2744 leaves
  methodology  8306 skills, 793 leaves
    rest  5945 skills, 629 leaves
      ai  947 skills, 48 leaves
        community--awesome-claude-skills  705 skills, 8 leaves, 8 name blocks
        community--antigravity-awesome-skills  87 skills, 1 leaves
        … 39 smaller, 155 skills
      security  637 skills, 46 leaves
        community--antigravity-awesome-skills  395 skills, 4 leaves, 4 name blocks
        others--mukul975--anthropic-cybersecurity-skills  133 skills, 2 leaves, 2 name blocks
        … 40 smaller, 109 skills
      legal  526 skills, 49 leaves
        community--antigravity-awesome-skills  155 skills, 2 leaves, 2 name blocks
        others--lawve-ai--awesome-legal-skills  92 skills, 1 leaves
        others--mukul975--anthropic-cybersecurity-skills  60 skills, 1 leaves
        … 45 smaller, 219 skills
      data  485 skills, 48 leaves
        community--antigravity-awesome-skills  130 skills, 2 leaves, 2 name blocks
        others--mukul975--anthropic-cybersecurity-skills  97 skills, 1 leaves
        … 45 smaller, 258 skills
      design  392 skills, 52 leaves
        community--antigravity-awesome-skills  133 skills, 2 leaves, 2 name blocks
        … 50 smaller, 259 skills
      finance  384 skills, 35 leaves
        community--antigravity-awesome-skills  129 skills, 2 leaves, 2 name blocks
        others--openaccountants--openaccountants  95 skills, 1 leaves
        others--mukul975--anthropic-cybersecurity-skills  70 skills, 1 leaves
        … 31 smaller, 90 skills
      media  331 skills, 51 leaves
        community--antigravity-awesome-skills  90 skills, 1 leaves
        … 50 smaller, 241 skills
      databases  279 skills, 38 leaves
        community--antigravity-awesome-skills  133 skills, 2 leaves, 2 name blocks
        … 36 smaller, 146 skills
      frontend  277 skills, 38 leaves
        community--antigravity-awesome-skills  140 skills, 2 leaves, 2 name blocks
        … 36 smaller, 137 skills
      life-science  256 skills, 35 leaves
        community--antigravity-awesome-skills  73 skills, 1 leaves
        … 34 smaller, 183 skills
      testing  233 skills, 46 leaves
        community--antigravity-awesome-skills  110 skills, 2 leaves, 2 name blocks
        … 44 smaller, 123 skills
      unspecified  173 skills, 27 leaves
        community--antigravity-awesome-skills  47 skills, 1 leaves
        … 26 smaller, 126 skills
      documents  161 skills, 36 leaves
        community--antigravity-awesome-skills  43 skills, 1 leaves
        … 35 smaller, 118 skills
      cloud-devops  114 skills, 14 leaves
        community--antigravity-awesome-skills  33 skills, 1 leaves
        others--mukul975--anthropic-cybersecurity-skills  21 skills, 1 leaves
        platforms--microsoft--azure-skills  21 skills, 1 leaves
        … 11 smaller, 39 skills
      software  102 skills, 20 leaves
        community--antigravity-awesome-skills  44 skills, 1 leaves
        … 19 smaller, 58 skills
      writing  101 skills, 35 leaves
        community--antigravity-awesome-skills  30 skills, 1 leaves
        others--wanshuiyin--auto-claude-code-research-in-sleep  8 skills, 1 leaves
        others--foryourhealth111-pixel--vibe-skills  6 skills, 1 leaves
        … 32 smaller, 57 skills
      education  88 skills, 1 leaves
      research  86 skills, 1 leaves
      … 9 smaller, 373 skills
    plan  1144 skills, 113 leaves
      design  155 skills, 38 leaves
        community--antigravity-awesome-skills  27 skills, 1 leaves
        others--infrasity-labs--dev-gtm-claude-skills  27 skills, 1 leaves
        others--indranilbanerjee--digital-marketing-pro  19 skills, 1 leaves
        … 35 smaller, 82 skills
      legal  146 skills, 31 leaves
        others--aaron-he-zhu--aaron-marketing-skills  26 skills, 1 leaves
        others--openaccountants--openaccountants  24 skills, 1 leaves
        others--lawve-ai--awesome-legal-skills  12 skills, 1 leaves
        … 28 smaller, 84 skills
      security  106 skills, 22 leaves
        others--sandbaseai--sandbase-skills  48 skills, 1 leaves
        … 21 smaller, 58 skills
      ai  89 skills, 1 leaves
      unspecified  82 skills, 1 leaves
      … 20 smaller, 566 skills
    workflow  628 skills, 25 leaves
      security  91 skills, 1 leaves
      … 24 smaller, 537 skills
    debug  441 skills, 24 leaves
      software  75 skills, 1 leaves
      frontend  49 skills, 1 leaves
      testing  42 skills, 1 leaves
      … 21 smaller, 275 skills
    … 2 smaller, 148 skills
  none  6508 skills, 623 leaves
    unspecified  667 skills, 62 leaves
      community--antigravity-awesome-skills  270 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-2  70 skills, 1 leaves, 1 name blocks
      … 59 smaller, 397 skills
    data  645 skills, 60 leaves
      community--antigravity-awesome-skills  367 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  67 skills, 1 leaves, 1 name blocks
      … 56 smaller, 278 skills
    ai  592 skills, 58 leaves
      community--antigravity-awesome-skills  351 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  51 skills, 1 leaves, 1 name blocks
      … 54 smaller, 241 skills
    design  562 skills, 49 leaves
      community--antigravity-awesome-skills  319 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 19 skills
      … 45 smaller, 243 skills
    security  522 skills, 45 leaves
      community--antigravity-awesome-skills  360 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  60 skills, 1 leaves, 1 name blocks
      … 41 smaller, 162 skills
    frontend  386 skills, 35 leaves
      community--antigravity-awesome-skills  303 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 3 skills
      … 31 smaller, 83 skills
    legal  377 skills, 39 leaves
      community--antigravity-awesome-skills  143 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  43 skills, 1 leaves, 1 name blocks
      others--openaccountants--openaccountants  82 skills, 1 leaves
      … 36 smaller, 152 skills
    media  372 skills, 50 leaves
      community--antigravity-awesome-skills  164 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  64 skills, 1 leaves, 1 name blocks
      … 48 smaller, 208 skills
    finance  372 skills, 33 leaves
      others--openaccountants--openaccountants  191 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  91 skills, 1 leaves, 1 name blocks
      community--antigravity-awesome-skills  100 skills, 1 leaves
      … 30 smaller, 81 skills
    software  321 skills, 41 leaves
      community--antigravity-awesome-skills  207 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 7 skills
      … 38 smaller, 114 skills
    databases  273 skills, 33 leaves
      community--antigravity-awesome-skills  172 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  72 skills, 1 leaves, 1 name blocks
      … 31 smaller, 101 skills
    life-science  217 skills, 28 leaves
      community--antigravity-awesome-skills  77 skills, 1 leaves
      others--openaccountants--openaccountants  23 skills, 1 leaves
      openai_official--plugins  19 skills, 1 leaves
      … 25 smaller, 98 skills
    testing  188 skills, 34 leaves
      community--antigravity-awesome-skills  77 skills, 1 leaves
      others--lambdatest--agent-skills  22 skills, 1 leaves
      others--mouadja02--skills  17 skills, 1 leaves
      … 31 smaller, 72 skills
    writing  159 skills, 26 leaves
      community--antigravity-awesome-skills  88 skills, 1 leaves
      … 25 smaller, 71 skills
    cloud-devops  157 skills, 18 leaves
      community--antigravity-awesome-skills  102 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 2 skills
      … 16 smaller, 55 skills
    … 12 smaller, 698 skills
  verification  5243 skills, 582 leaves
    rest  3152 skills, 430 leaves
      legal  411 skills, 41 leaves
        community--antigravity-awesome-skills  152 skills, 2 leaves, 2 name blocks
        others--lawve-ai--awesome-legal-skills  51 skills, 1 leaves
        … 38 smaller, 208 skills
      security  407 skills, 47 leaves
        community--antigravity-awesome-skills  202 skills, 3 leaves, 3 name blocks
        others--mukul975--anthropic-cybersecurity-skills  59 skills, 1 leaves
        others--sandbaseai--sandbase-skills  46 skills, 1 leaves
        … 42 smaller, 100 skills
      data  260 skills, 35 leaves
        community--antigravity-awesome-skills  87 skills, 1 leaves
        … 34 smaller, 173 skills
      databases  222 skills, 33 leaves
        community--antigravity-awesome-skills  85 skills, 1 leaves
        others--garethmanning--education-agent-skills  44 skills, 1 leaves
        … 31 smaller, 93 skills
      design  218 skills, 42 leaves
        community--antigravity-awesome-skills  59 skills, 1 leaves
        … 41 smaller, 159 skills
      finance  200 skills, 37 leaves
        community--antigravity-awesome-skills  57 skills, 1 leaves
        others--openaccountants--openaccountants  47 skills, 1 leaves
        … 35 smaller, 96 skills
      ai  191 skills, 39 leaves
        community--antigravity-awesome-skills  81 skills, 1 leaves
        … 38 smaller, 110 skills
      media  175 skills, 31 leaves
        community--antigravity-awesome-skills  70 skills, 1 leaves
        … 30 smaller, 105 skills
      frontend  154 skills, 28 leaves
        community--antigravity-awesome-skills  61 skills, 1 leaves
        … 27 smaller, 93 skills
      life-science  151 skills, 29 leaves
        high_stars--gstack  31 skills, 1 leaves
        community--antigravity-awesome-skills  29 skills, 1 leaves
        others--k-dense-ai--scientific-agent-skills  22 skills, 1 leaves
        … 26 smaller, 69 skills
      testing  131 skills, 31 leaves
        community--antigravity-awesome-skills  68 skills, 1 leaves
        … 30 smaller, 63 skills
      software  106 skills, 22 leaves
        others--makenotion--notion-cookbook  35 skills, 1 leaves
        community--antigravity-awesome-skills  33 skills, 1 leaves
        others--nvidia--skills  8 skills, 1 leaves
        … 19 smaller, 30 skills
      … 15 smaller, 526 skills
    audit  1100 skills, 79 leaves
      legal  251 skills, 34 leaves
        community--antigravity-awesome-skills  98 skills, 1 leaves
        … 33 smaller, 153 skills
      security  124 skills, 23 leaves
        community--antigravity-awesome-skills  70 skills, 1 leaves
        … 22 smaller, 54 skills
      life-science  97 skills, 1 leaves
      frontend  88 skills, 1 leaves
      design  84 skills, 1 leaves
      … 19 smaller, 456 skills
    evidence  482 skills, 22 leaves
      legal  76 skills, 1 leaves
      security  52 skills, 1 leaves
      finance  41 skills, 1 leaves
      … 19 smaller, 313 skills
    test  362 skills, 48 leaves
      testing  153 skills, 34 leaves
        community--antigravity-awesome-skills  73 skills, 1 leaves
        … 33 smaller, 80 skills
      … 14 smaller, 209 skills
    … 3 smaller, 147 skills
  reflection  3078 skills, 281 leaves
    review  1684 skills, 163 leaves
      security  260 skills, 37 leaves
        community--antigravity-awesome-skills  140 skills, 2 leaves, 2 name blocks
        others--sandbaseai--sandbase-skills  49 skills, 1 leaves
        … 34 smaller, 71 skills
      legal  238 skills, 46 leaves
        community--antigravity-awesome-skills  67 skills, 1 leaves
        others--lawve-ai--awesome-legal-skills  51 skills, 1 leaves
        … 44 smaller, 120 skills
      finance  177 skills, 21 leaves
        others--openaccountants--openaccountants  128 skills, 2 leaves, 2 name blocks
        … 19 smaller, 49 skills
      design  151 skills, 36 leaves
        community--antigravity-awesome-skills  53 skills, 1 leaves
        … 35 smaller, 98 skills
      frontend  88 skills, 1 leaves
      data  86 skills, 1 leaves
      … 21 smaller, 684 skills
    rest  1330 skills, 116 leaves
      legal  196 skills, 22 leaves
        community--antigravity-awesome-skills  65 skills, 1 leaves
        … 21 smaller, 131 skills
      security  173 skills, 20 leaves
        community--antigravity-awesome-skills  130 skills, 2 leaves, 2 name blocks
        … 18 smaller, 43 skills
      design  126 skills, 31 leaves
        community--antigravity-awesome-skills  25 skills, 1 leaves
        others--neolabhq--context-engineering-kit  12 skills, 1 leaves
        others--kensaurus--cursor-kenji  12 skills, 1 leaves
        … 28 smaller, 77 skills
      finance  114 skills, 20 leaves
        others--openaccountants--openaccountants  75 skills, 1 leaves
        … 19 smaller, 39 skills
      life-science  92 skills, 1 leaves
      frontend  85 skills, 1 leaves
      data  80 skills, 1 leaves
      … 20 smaller, 464 skills
    … 2 smaller, 64 skills
  repo-understanding  2454 skills, 245 leaves
    rest  1702 skills, 167 leaves
      design  224 skills, 42 leaves
        community--antigravity-awesome-skills  97 skills, 1 leaves
        … 41 smaller, 127 skills
      security  220 skills, 33 leaves
        community--antigravity-awesome-skills  89 skills, 1 leaves
        others--sandbaseai--sandbase-skills  47 skills, 1 leaves
        … 31 smaller, 84 skills
      legal  196 skills, 28 leaves
        community--antigravity-awesome-skills  69 skills, 1 leaves
        … 27 smaller, 127 skills
      finance  134 skills, 20 leaves
        others--openaccountants--openaccountants  84 skills, 1 leaves
        … 19 smaller, 50 skills
      data  108 skills, 22 leaves
        community--antigravity-awesome-skills  49 skills, 1 leaves
        … 21 smaller, 59 skills
      frontend  91 skills, 1 leaves
      media  90 skills, 1 leaves
      testing  89 skills, 1 leaves
      life-science  80 skills, 1 leaves
      … 18 smaller, 470 skills
    architecture  558 skills, 54 leaves
      design  161 skills, 31 leaves
        community--antigravity-awesome-skills  86 skills, 1 leaves
        … 30 smaller, 75 skills
      … 23 smaller, 397 skills
    onboard  166 skills, 22 leaves
      design  28 skills, 1 leaves
      finance  20 skills, 1 leaves
      legal  19 skills, 1 leaves
      … 19 smaller, 99 skills
    … 2 smaller, 28 skills
  discovery  1203 skills, 47 leaves
    rest  1189 skills, 45 leaves
      ai  765 skills, 23 leaves
        community--awesome-claude-skills  727 skills, 8 leaves, 8 name blocks
        … 15 smaller, 38 skills
      … 22 smaller, 424 skills
    … 2 smaller, 14 skills
  output-format  909 skills, 171 leaves
    documents  345 skills, 57 leaves
      community--antigravity-awesome-skills  99 skills, 1 leaves
      … 56 smaller, 246 skills
    frontend  197 skills, 37 leaves
      community--antigravity-awesome-skills  87 skills, 1 leaves
      … 36 smaller, 110 skills
    legal  118 skills, 31 leaves
    media  110 skills, 36 leaves
    … 10 smaller, 139 skills
  skill-authoring  64 skills, 1 leaves
  audience  58 skills, 1 leaves
```

## Trees for the other facets

`rest` is not a kind of work. On Job, Domain, and Form the builder looks for a named child. A skill that has the parent and matches none of those children is labeled `rest`. Under `methodology`, the children are plan, workflow, debug, tdd, and brainstorm. The 5,945 skills in `methodology / rest` are methodology skills whose name and description contain none of those words.

The depth-5 tree above is Job only. The other seven facets are in the same leaf file. A branch below is expanded only while it has at least 100 skills. Counts are placements from [`data/processed/skill-label-leaves.jsonl`](../../data/processed/skill-label-leaves.jsonl).

### Domain

2 the domain name, 3 the child (`python`, `agent`, or `rest`), 4 the clone, 5 a name block when that clone is still over 100.

```
domain  59373 skills, 3927 leaves
  software  9977 skills, 356 leaves
    rest  9012 skills, 287 leaves
      community--antigravity-awesome-skills  4138 skills, 42 leaves
        names-38  100 skills, 1 leaves, 1 name blocks
        names-11  100 skills, 1 leaves, 1 name blocks
        names-18  100 skills, 1 leaves, 1 name blocks
        names-15  100 skills, 1 leaves, 1 name blocks
        names-05  100 skills, 1 leaves, 1 name blocks
        names-36  100 skills, 1 leaves, 1 name blocks
        names-19  100 skills, 1 leaves, 1 name blocks
        names-14  100 skills, 1 leaves, 1 name blocks
        names-27  100 skills, 1 leaves, 1 name blocks
        names-09  100 skills, 1 leaves, 1 name blocks
        names-24  100 skills, 1 leaves, 1 name blocks
        names-32  100 skills, 1 leaves, 1 name blocks
        names-20  100 skills, 1 leaves, 1 name blocks
        names-30  100 skills, 1 leaves, 1 name blocks
        names-21  100 skills, 1 leaves, 1 name blocks
        names-34  100 skills, 1 leaves, 1 name blocks
        names-00  100 skills, 1 leaves, 1 name blocks
        names-25  100 skills, 1 leaves, 1 name blocks
        names-07  100 skills, 1 leaves, 1 name blocks
        names-33  100 skills, 1 leaves, 1 name blocks
        names-29  100 skills, 1 leaves, 1 name blocks
        names-22  100 skills, 1 leaves, 1 name blocks
        names-35  100 skills, 1 leaves, 1 name blocks
        names-03  100 skills, 1 leaves, 1 name blocks
        names-02  100 skills, 1 leaves, 1 name blocks
        names-01  100 skills, 1 leaves, 1 name blocks
        names-40  100 skills, 1 leaves, 1 name blocks
        names-16  100 skills, 1 leaves, 1 name blocks
        names-10  100 skills, 1 leaves, 1 name blocks
        names-26  100 skills, 1 leaves, 1 name blocks
        names-13  100 skills, 1 leaves, 1 name blocks
        names-04  100 skills, 1 leaves, 1 name blocks
        names-31  100 skills, 1 leaves, 1 name blocks
        names-08  100 skills, 1 leaves, 1 name blocks
        names-12  100 skills, 1 leaves, 1 name blocks
        names-28  100 skills, 1 leaves, 1 name blocks
        names-37  100 skills, 1 leaves, 1 name blocks
        names-39  100 skills, 1 leaves, 1 name blocks
        names-06  100 skills, 1 leaves, 1 name blocks
        names-23  100 skills, 1 leaves, 1 name blocks
        names-17  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 38 skills
      others--openaccountants--openaccountants  388 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  88 skills, 1 leaves, 1 name blocks
      others--mouadja02--skills  373 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  73 skills, 1 leaves, 1 name blocks
      others--mukul975--anthropic-cybersecurity-skills  342 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  42 skills, 1 leaves, 1 name blocks
      openai_official--plugins  268 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-2  68 skills, 1 leaves, 1 name blocks
      others--infrasity-labs--dev-gtm-claude-skills  263 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-2  63 skills, 1 leaves, 1 name blocks
      others--nvidia--skills  213 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 13 skills
      others--makenotion--notion-cookbook  163 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  63 skills, 1 leaves, 1 name blocks
      social--davepoon--buildwithclaude  147 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  47 skills, 1 leaves, 1 name blocks
      others--lawve-ai--awesome-legal-skills  131 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 31 skills
      others--foryourhealth111-pixel--vibe-skills  122 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 22 skills
      others--gooseworks-ai--goose-skills  107 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 7 skills
      others--kensaurus--cursor-kenji  100 skills, 1 leaves
      … 213 smaller, 2257 skills
    python  478 skills, 43 leaves
      community--antigravity-awesome-skills  272 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-2  72 skills, 1 leaves, 1 name blocks
      … 40 smaller, 206 skills
    … 5 smaller, 487 skills
  ai  7890 skills, 503 leaves
    rest  5200 skills, 204 leaves
      community--antigravity-awesome-skills  2002 skills, 21 leaves
        names-11  100 skills, 1 leaves, 1 name blocks
        names-18  100 skills, 1 leaves, 1 name blocks
        names-15  100 skills, 1 leaves, 1 name blocks
        names-05  100 skills, 1 leaves, 1 name blocks
        names-19  100 skills, 1 leaves, 1 name blocks
        names-14  100 skills, 1 leaves, 1 name blocks
        names-09  100 skills, 1 leaves, 1 name blocks
        names-00  100 skills, 1 leaves, 1 name blocks
        names-07  100 skills, 1 leaves, 1 name blocks
        names-03  100 skills, 1 leaves, 1 name blocks
        names-02  100 skills, 1 leaves, 1 name blocks
        names-01  100 skills, 1 leaves, 1 name blocks
        names-16  100 skills, 1 leaves, 1 name blocks
        names-10  100 skills, 1 leaves, 1 name blocks
        names-13  100 skills, 1 leaves, 1 name blocks
        names-04  100 skills, 1 leaves, 1 name blocks
        names-08  100 skills, 1 leaves, 1 name blocks
        names-12  100 skills, 1 leaves, 1 name blocks
        names-06  100 skills, 1 leaves, 1 name blocks
        names-17  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 2 skills
      community--awesome-claude-skills  802 skills, 9 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-7  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 2 skills
      social--davepoon--buildwithclaude  168 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  68 skills, 1 leaves, 1 name blocks
      others--mouadja02--skills  155 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  55 skills, 1 leaves, 1 name blocks
      others--garethmanning--education-agent-skills  154 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  54 skills, 1 leaves, 1 name blocks
      others--indranilbanerjee--digital-marketing-pro  121 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 21 skills
      openai_official--plugins  115 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 15 skills
      others--infrasity-labs--dev-gtm-claude-skills  113 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 13 skills
      others--nvidia--skills  111 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 11 skills
      … 160 smaller, 1459 skills
    agent  1390 skills, 128 leaves
      community--antigravity-awesome-skills  603 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 3 skills
      … 121 smaller, 787 skills
    model  801 skills, 81 leaves
      community--antigravity-awesome-skills  299 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-2  99 skills, 1 leaves, 1 name blocks
      … 78 smaller, 502 skills
    llm  226 skills, 41 leaves
      community--antigravity-awesome-skills  95 skills, 1 leaves
      others--infrasity-labs--dev-gtm-claude-skills  20 skills, 1 leaves
      others--xberg-io--xberg  11 skills, 1 leaves
      … 38 smaller, 100 skills
    prompt  212 skills, 48 leaves
      community--antigravity-awesome-skills  72 skills, 1 leaves
      others--mouadja02--skills  29 skills, 1 leaves
      others--infrasity-labs--dev-gtm-claude-skills  14 skills, 1 leaves
      … 45 smaller, 97 skills
    … 1 smaller, 61 skills
  security  4789 skills, 273 leaves
    rest  3680 skills, 143 leaves
      community--antigravity-awesome-skills  2307 skills, 24 leaves
        names-11  100 skills, 1 leaves, 1 name blocks
        names-18  100 skills, 1 leaves, 1 name blocks
        names-15  100 skills, 1 leaves, 1 name blocks
        names-05  100 skills, 1 leaves, 1 name blocks
        names-19  100 skills, 1 leaves, 1 name blocks
        names-14  100 skills, 1 leaves, 1 name blocks
        names-09  100 skills, 1 leaves, 1 name blocks
        names-20  100 skills, 1 leaves, 1 name blocks
        names-21  100 skills, 1 leaves, 1 name blocks
        names-00  100 skills, 1 leaves, 1 name blocks
        names-07  100 skills, 1 leaves, 1 name blocks
        names-22  100 skills, 1 leaves, 1 name blocks
        names-03  100 skills, 1 leaves, 1 name blocks
        names-02  100 skills, 1 leaves, 1 name blocks
        names-01  100 skills, 1 leaves, 1 name blocks
        names-16  100 skills, 1 leaves, 1 name blocks
        names-10  100 skills, 1 leaves, 1 name blocks
        names-13  100 skills, 1 leaves, 1 name blocks
        names-04  100 skills, 1 leaves, 1 name blocks
        names-08  100 skills, 1 leaves, 1 name blocks
        names-12  100 skills, 1 leaves, 1 name blocks
        names-06  100 skills, 1 leaves, 1 name blocks
        names-17  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 7 skills
      others--mukul975--anthropic-cybersecurity-skills  309 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 9 skills
      others--openaccountants--openaccountants  121 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 21 skills
      others--mouadja02--skills  107 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 7 skills
      … 111 smaller, 836 skills
    auth  854 skills, 94 leaves
      community--antigravity-awesome-skills  364 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  64 skills, 1 leaves, 1 name blocks
      … 90 smaller, 490 skills
    … 4 smaller, 255 skills
  data  4250 skills, 277 leaves
    rest  3636 skills, 164 leaves
      community--antigravity-awesome-skills  1407 skills, 15 leaves
        names-13  100 skills, 1 leaves, 1 name blocks
        names-11  100 skills, 1 leaves, 1 name blocks
        names-04  100 skills, 1 leaves, 1 name blocks
        names-03  100 skills, 1 leaves, 1 name blocks
        names-05  100 skills, 1 leaves, 1 name blocks
        names-02  100 skills, 1 leaves, 1 name blocks
        names-08  100 skills, 1 leaves, 1 name blocks
        names-12  100 skills, 1 leaves, 1 name blocks
        names-00  100 skills, 1 leaves, 1 name blocks
        names-01  100 skills, 1 leaves, 1 name blocks
        names-09  100 skills, 1 leaves, 1 name blocks
        names-07  100 skills, 1 leaves, 1 name blocks
        names-06  100 skills, 1 leaves, 1 name blocks
        names-10  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 7 skills
      others--mukul975--anthropic-cybersecurity-skills  218 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 18 skills
      others--infrasity-labs--dev-gtm-claude-skills  165 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  65 skills, 1 leaves, 1 name blocks
      others--mouadja02--skills  149 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  49 skills, 1 leaves, 1 name blocks
      others--nvidia--skills  135 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 35 skills
      others--aaron-he-zhu--aaron-marketing-skills  113 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 13 skills
      others--openaccountants--openaccountants  111 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 11 skills
      others--foryourhealth111-pixel--vibe-skills  101 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 1 skills
      … 134 smaller, 1237 skills
    metrics  303 skills, 48 leaves
      community--antigravity-awesome-skills  106 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 6 skills
      … 46 smaller, 197 skills
    analytics  160 skills, 29 leaves
    … 3 smaller, 151 skills
  testing  3235 skills, 153 leaves
    rest  3017 skills, 149 leaves
      community--antigravity-awesome-skills  1311 skills, 14 leaves
        names-11  100 skills, 1 leaves, 1 name blocks
        names-04  100 skills, 1 leaves, 1 name blocks
        names-03  100 skills, 1 leaves, 1 name blocks
        names-05  100 skills, 1 leaves, 1 name blocks
        names-02  100 skills, 1 leaves, 1 name blocks
        names-08  100 skills, 1 leaves, 1 name blocks
        names-12  100 skills, 1 leaves, 1 name blocks
        names-00  100 skills, 1 leaves, 1 name blocks
        names-01  100 skills, 1 leaves, 1 name blocks
        names-09  100 skills, 1 leaves, 1 name blocks
        names-07  100 skills, 1 leaves, 1 name blocks
        names-06  100 skills, 1 leaves, 1 name blocks
        names-10  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 11 skills
      others--mukul975--anthropic-cybersecurity-skills  199 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  99 skills, 1 leaves, 1 name blocks
      others--openaccountants--openaccountants  158 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  58 skills, 1 leaves, 1 name blocks
      others--mouadja02--skills  138 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 38 skills
      others--makenotion--notion-cookbook  105 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 5 skills
      … 127 smaller, 1106 skills
    … 4 smaller, 218 skills
  design  2671 skills, 172 leaves
    rest  2237 skills, 128 leaves
      community--antigravity-awesome-skills  909 skills, 10 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-8  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-7  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 9 skills
      others--infrasity-labs--dev-gtm-claude-skills  159 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  59 skills, 1 leaves, 1 name blocks
      others--mouadja02--skills  107 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 7 skills
      others--indranilbanerjee--digital-marketing-pro  103 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 3 skills
      … 112 smaller, 959 skills
    brand  316 skills, 42 leaves
      community--antigravity-awesome-skills  66 skills, 1 leaves
      others--indranilbanerjee--digital-marketing-pro  49 skills, 1 leaves
      others--gooseworks-ai--goose-skills  47 skills, 1 leaves
      … 39 smaller, 154 skills
    … 2 smaller, 118 skills
  cloud-devops  2555 skills, 132 leaves
    rest  1398 skills, 74 leaves
      community--antigravity-awesome-skills  682 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-6  82 skills, 1 leaves, 1 name blocks
      others--mukul975--anthropic-cybersecurity-skills  160 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  60 skills, 1 leaves, 1 name blocks
      … 65 smaller, 556 skills
    azure  586 skills, 18 leaves
      community--antigravity-awesome-skills  446 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  46 skills, 1 leaves, 1 name blocks
      … 13 smaller, 140 skills
    aws  210 skills, 14 leaves
      community--antigravity-awesome-skills  108 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 8 skills
      … 12 smaller, 102 skills
    … 4 smaller, 361 skills
  frontend  2334 skills, 203 leaves
    rest  1772 skills, 124 leaves
      community--antigravity-awesome-skills  893 skills, 9 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-7  100 skills, 1 leaves, 1 name blocks
        names-8  93 skills, 1 leaves, 1 name blocks
      others--infrasity-labs--dev-gtm-claude-skills  100 skills, 1 leaves
      … 114 smaller, 779 skills
    react  281 skills, 36 leaves
      community--antigravity-awesome-skills  179 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  79 skills, 1 leaves, 1 name blocks
      … 34 smaller, 102 skills
    accessibility  181 skills, 40 leaves
    … 3 smaller, 100 skills
  writing  2267 skills, 227 leaves
    rest  1705 skills, 147 leaves
      community--antigravity-awesome-skills  605 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 5 skills
      … 140 smaller, 1100 skills
    docs  391 skills, 58 leaves
      community--antigravity-awesome-skills  187 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  87 skills, 1 leaves, 1 name blocks
      … 56 smaller, 204 skills
    blog  171 skills, 22 leaves
  legal  1847 skills, 148 leaves
    rest  1266 skills, 86 leaves
      community--antigravity-awesome-skills  387 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  87 skills, 1 leaves, 1 name blocks
      others--openaccountants--openaccountants  141 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  41 skills, 1 leaves, 1 name blocks
      others--aaron-he-zhu--aaron-marketing-skills  117 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 17 skills
      … 78 smaller, 621 skills
    compliance  388 skills, 34 leaves
      community--antigravity-awesome-skills  146 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  46 skills, 1 leaves, 1 name blocks
      … 32 smaller, 242 skills
    contract  166 skills, 27 leaves
    … 1 smaller, 27 skills
  databases  1754 skills, 114 leaves
    rest  1473 skills, 90 leaves
      community--antigravity-awesome-skills  657 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-6  57 skills, 1 leaves, 1 name blocks
      others--garethmanning--education-agent-skills  145 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  45 skills, 1 leaves, 1 name blocks
      … 81 smaller, 671 skills
    sql  152 skills, 22 leaves
    … 2 smaller, 129 skills
  backend  1699 skills, 107 leaves
    community--antigravity-awesome-skills  869 skills, 9 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-6  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-5  100 skills, 1 leaves
      names-4  100 skills, 1 leaves
      names-7  100 skills, 1 leaves
      … 1 smaller, 69 skills
    others--mukul975--anthropic-cybersecurity-skills  173 skills, 2 leaves
    … 96 smaller, 657 skills
  finance  1660 skills, 121 leaves
    rest  827 skills, 66 leaves
      community--antigravity-awesome-skills  316 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 16 skills
      others--openaccountants--openaccountants  191 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  91 skills, 1 leaves, 1 name blocks
      … 60 smaller, 320 skills
    tax  514 skills, 14 leaves
      others--openaccountants--openaccountants  469 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  69 skills, 1 leaves, 1 name blocks
      … 9 smaller, 45 skills
    investing  211 skills, 39 leaves
      community--antigravity-awesome-skills  57 skills, 1 leaves
      others--mukul975--anthropic-cybersecurity-skills  52 skills, 1 leaves
      openai_official--plugins  15 skills, 1 leaves
      … 36 smaller, 87 skills
    … 2 smaller, 108 skills
  marketing  1447 skills, 150 leaves
    rest  649 skills, 65 leaves
      community--antigravity-awesome-skills  167 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  67 skills, 1 leaves, 1 name blocks
      others--indranilbanerjee--digital-marketing-pro  102 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 2 skills
      … 61 smaller, 380 skills
    seo  494 skills, 30 leaves
      community--antigravity-awesome-skills  220 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 20 skills
      others--infrasity-labs--dev-gtm-claude-skills  109 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 9 skills
      … 25 smaller, 165 skills
    campaign  197 skills, 26 leaves
    … 1 smaller, 107 skills
  research  1430 skills, 95 leaves
    community--antigravity-awesome-skills  311 skills, 4 leaves
      names-2  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 11 skills
    … 88 smaller, 1119 skills
  media  1348 skills, 167 leaves
    rest  631 skills, 69 leaves
      community--antigravity-awesome-skills  275 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-2  75 skills, 1 leaves, 1 name blocks
      … 66 smaller, 356 skills
    video  376 skills, 56 leaves
      community--antigravity-awesome-skills  84 skills, 1 leaves
      others--gooseworks-ai--goose-skills  49 skills, 1 leaves
      others--nvidia--skills  31 skills, 1 leaves
      … 53 smaller, 212 skills
    image  265 skills, 41 leaves
      community--antigravity-awesome-skills  77 skills, 1 leaves
      others--nvidia--skills  32 skills, 1 leaves
      others--infrasity-labs--dev-gtm-claude-skills  26 skills, 1 leaves
      … 38 smaller, 130 skills
    … 1 smaller, 76 skills
  productivity  1183 skills, 78 leaves
    community--antigravity-awesome-skills  367 skills, 4 leaves
      names-2  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 67 skills
    … 74 smaller, 816 skills
  systems  1157 skills, 92 leaves
    community--antigravity-awesome-skills  473 skills, 5 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      … 1 smaller, 73 skills
    others--mukul975--anthropic-cybersecurity-skills  159 skills, 2 leaves
    … 85 smaller, 525 skills
  unspecified  1083 skills, 82 leaves
    community--antigravity-awesome-skills  376 skills, 4 leaves
      names-2  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 76 skills
    … 78 smaller, 707 skills
  business  1043 skills, 61 leaves
    community--antigravity-awesome-skills  318 skills, 4 leaves
      names-2  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 18 skills
    … 56 smaller, 725 skills
  git  1040 skills, 103 leaves
    community--antigravity-awesome-skills  479 skills, 5 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      … 1 smaller, 79 skills
    … 98 smaller, 561 skills
  life-science  722 skills, 64 leaves
    community--antigravity-awesome-skills  207 skills, 3 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 7 skills
    … 61 smaller, 515 skills
  documents  597 skills, 73 leaves
    … 72 smaller, 597 skills
  mobile  529 skills, 47 leaves
    rest  264 skills, 19 leaves
      community--antigravity-awesome-skills  208 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 8 skills
      … 16 smaller, 56 skills
    … 4 smaller, 265 skills
  commerce  421 skills, 51 leaves
    rest  269 skills, 48 leaves
      community--antigravity-awesome-skills  99 skills, 1 leaves
      others--openaccountants--openaccountants  20 skills, 1 leaves
      others--mukul975--anthropic-cybersecurity-skills  17 skills, 1 leaves
      … 45 smaller, 133 skills
    … 3 smaller, 152 skills
  education  319 skills, 59 leaves
  games  126 skills, 19 leaves
```

### Form

2 `technique`, `pattern`, or `reference`, 3 the child or `rest`, 4 another domain, 5 the clone.

```
form  19716 skills, 2017 leaves
  technique  11473 skills, 1216 leaves
    rest  11194 skills, 1192 leaves
      ai  1634 skills, 104 leaves
        community--awesome-claude-skills  743 skills, 8 leaves, 8 name blocks
        community--antigravity-awesome-skills  416 skills, 5 leaves, 5 name blocks
        social--davepoon--buildwithclaude  76 skills, 1 leaves
        … 90 smaller, 399 skills
      data  974 skills, 81 leaves
        community--antigravity-awesome-skills  277 skills, 3 leaves, 3 name blocks
        others--mukul975--anthropic-cybersecurity-skills  108 skills, 2 leaves, 2 name blocks
        others--nvidia--skills  54 skills, 1 leaves
        … 75 smaller, 535 skills
      legal  924 skills, 71 leaves
        community--antigravity-awesome-skills  210 skills, 3 leaves, 3 name blocks
        others--openaccountants--openaccountants  159 skills, 2 leaves, 2 name blocks
        others--lawve-ai--awesome-legal-skills  98 skills, 1 leaves
        others--aaron-he-zhu--aaron-marketing-skills  90 skills, 1 leaves
        others--mukul975--anthropic-cybersecurity-skills  59 skills, 1 leaves
        … 63 smaller, 308 skills
      security  842 skills, 82 leaves
        community--antigravity-awesome-skills  365 skills, 4 leaves, 4 name blocks
        others--mukul975--anthropic-cybersecurity-skills  167 skills, 2 leaves, 2 name blocks
        others--sandbaseai--sandbase-skills  54 skills, 1 leaves
        … 75 smaller, 256 skills
      finance  823 skills, 66 leaves
        others--openaccountants--openaccountants  409 skills, 5 leaves, 5 name blocks
        community--antigravity-awesome-skills  131 skills, 2 leaves, 2 name blocks
        others--mukul975--anthropic-cybersecurity-skills  81 skills, 1 leaves
        … 58 smaller, 202 skills
      unspecified  769 skills, 77 leaves
        community--antigravity-awesome-skills  231 skills, 3 leaves, 3 name blocks
        social--davepoon--buildwithclaude  52 skills, 1 leaves
        openai_official--plugins  50 skills, 1 leaves
        others--mukul975--anthropic-cybersecurity-skills  50 skills, 1 leaves
        … 71 smaller, 386 skills
      design  652 skills, 75 leaves
        community--antigravity-awesome-skills  248 skills, 3 leaves, 3 name blocks
        others--indranilbanerjee--digital-marketing-pro  44 skills, 1 leaves
        … 71 smaller, 360 skills
      media  629 skills, 70 leaves
        community--antigravity-awesome-skills  215 skills, 3 leaves, 3 name blocks
        others--nvidia--skills  46 skills, 1 leaves
        openai_official--plugins  42 skills, 1 leaves
        … 65 smaller, 326 skills
      frontend  595 skills, 67 leaves
        community--antigravity-awesome-skills  306 skills, 4 leaves, 4 name blocks
        … 63 smaller, 289 skills
      testing  492 skills, 68 leaves
        community--antigravity-awesome-skills  187 skills, 2 leaves, 2 name blocks
        … 66 smaller, 305 skills
      life-science  423 skills, 51 leaves
        community--antigravity-awesome-skills  116 skills, 2 leaves, 2 name blocks
        others--k-dense-ai--scientific-agent-skills  47 skills, 1 leaves
        others--openaccountants--openaccountants  41 skills, 1 leaves
        … 47 smaller, 219 skills
      software  395 skills, 52 leaves
        community--antigravity-awesome-skills  134 skills, 2 leaves, 2 name blocks
        … 50 smaller, 261 skills
      databases  256 skills, 30 leaves
        community--antigravity-awesome-skills  133 skills, 2 leaves, 2 name blocks
        … 28 smaller, 123 skills
      cloud-devops  240 skills, 24 leaves
        community--antigravity-awesome-skills  102 skills, 2 leaves, 2 name blocks
        … 22 smaller, 138 skills
      writing  235 skills, 46 leaves
        community--antigravity-awesome-skills  110 skills, 2 leaves, 2 name blocks
        … 44 smaller, 125 skills
      documents  205 skills, 45 leaves
        community--antigravity-awesome-skills  44 skills, 1 leaves
        … 44 smaller, 161 skills
      git  175 skills, 39 leaves
        community--antigravity-awesome-skills  75 skills, 1 leaves
        … 38 smaller, 100 skills
      marketing  158 skills, 28 leaves
        community--antigravity-awesome-skills  52 skills, 1 leaves
        … 27 smaller, 106 skills
      commerce  143 skills, 33 leaves
        community--antigravity-awesome-skills  36 skills, 1 leaves
        others--browser-act--skills  18 skills, 1 leaves
        others--mukul975--anthropic-cybersecurity-skills  11 skills, 1 leaves
        … 30 smaller, 78 skills
      education  128 skills, 38 leaves
        community--antigravity-awesome-skills  46 skills, 1 leaves
        … 37 smaller, 82 skills
      research  115 skills, 27 leaves
        community--antigravity-awesome-skills  36 skills, 1 leaves
        others--wanshuiyin--auto-claude-code-research-in-sleep  21 skills, 1 leaves
        others--gooseworks-ai--goose-skills  14 skills, 1 leaves
        … 24 smaller, 44 skills
      mobile  102 skills, 13 leaves
        community--antigravity-awesome-skills  58 skills, 1 leaves
        … 12 smaller, 44 skills
      … 5 smaller, 285 skills
    … 3 smaller, 279 skills
  pattern  6910 skills, 676 leaves
    rest  6734 skills, 652 leaves
      security  914 skills, 51 leaves
        community--antigravity-awesome-skills  773 skills, 8 leaves, 8 name blocks
        … 43 smaller, 141 skills
      design  806 skills, 68 leaves
        community--antigravity-awesome-skills  408 skills, 5 leaves, 5 name blocks
        others--infrasity-labs--dev-gtm-claude-skills  119 skills, 2 leaves, 2 name blocks
        others--mouadja02--skills  44 skills, 1 leaves
        … 60 smaller, 235 skills
      legal  678 skills, 59 leaves
        community--antigravity-awesome-skills  357 skills, 4 leaves, 4 name blocks
        others--lawve-ai--awesome-legal-skills  79 skills, 1 leaves
        … 54 smaller, 242 skills
      data  608 skills, 51 leaves
        community--antigravity-awesome-skills  394 skills, 4 leaves, 4 name blocks
        … 47 smaller, 214 skills
      frontend  463 skills, 44 leaves
        community--antigravity-awesome-skills  338 skills, 4 leaves, 4 name blocks
        … 40 smaller, 125 skills
      finance  364 skills, 36 leaves
        community--antigravity-awesome-skills  208 skills, 3 leaves, 3 name blocks
        others--openaccountants--openaccountants  58 skills, 1 leaves
        … 32 smaller, 98 skills
      media  338 skills, 52 leaves
        community--antigravity-awesome-skills  170 skills, 2 leaves, 2 name blocks
        … 50 smaller, 168 skills
      unspecified  282 skills, 32 leaves
        community--antigravity-awesome-skills  130 skills, 2 leaves, 2 name blocks
        … 30 smaller, 152 skills
      ai  274 skills, 39 leaves
        community--antigravity-awesome-skills  162 skills, 2 leaves, 2 name blocks
        … 37 smaller, 112 skills
      testing  260 skills, 42 leaves
        community--antigravity-awesome-skills  164 skills, 2 leaves, 2 name blocks
        … 40 smaller, 96 skills
      software  250 skills, 21 leaves
        community--antigravity-awesome-skills  208 skills, 3 leaves, 3 name blocks
        … 18 smaller, 42 skills
      life-science  238 skills, 34 leaves
        community--antigravity-awesome-skills  73 skills, 1 leaves
        high_stars--gstack  40 skills, 1 leaves
        … 32 smaller, 125 skills
      databases  224 skills, 21 leaves
        community--antigravity-awesome-skills  169 skills, 2 leaves, 2 name blocks
        … 19 smaller, 55 skills
      cloud-devops  144 skills, 15 leaves
        community--antigravity-awesome-skills  89 skills, 1 leaves
        … 14 smaller, 55 skills
      documents  132 skills, 29 leaves
        community--antigravity-awesome-skills  58 skills, 1 leaves
        … 28 smaller, 74 skills
      writing  117 skills, 24 leaves
        community--antigravity-awesome-skills  52 skills, 1 leaves
        … 23 smaller, 65 skills
      commerce  109 skills, 24 leaves
        community--antigravity-awesome-skills  58 skills, 1 leaves
        … 23 smaller, 51 skills
      … 10 smaller, 533 skills
    … 3 smaller, 176 skills
  reference  1333 skills, 125 leaves
    rest  905 skills, 78 leaves
      databases  287 skills, 38 leaves
        community--antigravity-awesome-skills  90 skills, 1 leaves
        others--garethmanning--education-agent-skills  50 skills, 1 leaves
        … 36 smaller, 147 skills
      design  179 skills, 20 leaves
        community--antigravity-awesome-skills  49 skills, 1 leaves
        others--garethmanning--education-agent-skills  41 skills, 1 leaves
        … 18 smaller, 89 skills
      … 20 smaller, 439 skills
    schema  296 skills, 32 leaves
      databases  123 skills, 24 leaves
        community--antigravity-awesome-skills  64 skills, 1 leaves
        … 23 smaller, 59 skills
      … 8 smaller, 173 skills
    … 2 smaller, 132 skills
```

### Artifact

2 the file shape (`none`, `html`, `slides`, …), 3 another domain, 4 the clone, 5 a name block.

```
artifact  19716 skills, 1694 leaves
  none  18175 skills, 1462 leaves
    ai  1967 skills, 113 leaves
      community--awesome-claude-skills  743 skills, 8 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-7  43 skills, 1 leaves, 1 name blocks
      community--antigravity-awesome-skills  587 skills, 6 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-5  87 skills, 1 leaves, 1 name blocks
      … 99 smaller, 637 skills
    security  1803 skills, 103 leaves
      community--antigravity-awesome-skills  1147 skills, 12 leaves
        names-04  100 skills, 1 leaves, 1 name blocks
        names-03  100 skills, 1 leaves, 1 name blocks
        names-05  100 skills, 1 leaves, 1 name blocks
        names-02  100 skills, 1 leaves, 1 name blocks
        names-08  100 skills, 1 leaves, 1 name blocks
        names-00  100 skills, 1 leaves, 1 name blocks
        names-01  100 skills, 1 leaves, 1 name blocks
        names-09  100 skills, 1 leaves, 1 name blocks
        names-07  100 skills, 1 leaves, 1 name blocks
        names-06  100 skills, 1 leaves, 1 name blocks
        names-10  100 skills, 1 leaves, 1 name blocks
        names-11  47 skills, 1 leaves, 1 name blocks
      others--mukul975--anthropic-cybersecurity-skills  190 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  90 skills, 1 leaves, 1 name blocks
      … 89 smaller, 466 skills
    design  1696 skills, 100 leaves
      community--antigravity-awesome-skills  746 skills, 8 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-7  46 skills, 1 leaves, 1 name blocks
      others--infrasity-labs--dev-gtm-claude-skills  150 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  50 skills, 1 leaves, 1 name blocks
      … 90 smaller, 800 skills
    legal  1623 skills, 94 leaves
      community--antigravity-awesome-skills  596 skills, 6 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-5  96 skills, 1 leaves, 1 name blocks
      others--openaccountants--openaccountants  196 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  96 skills, 1 leaves, 1 name blocks
      others--lawve-ai--awesome-legal-skills  169 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  69 skills, 1 leaves, 1 name blocks
      others--aaron-he-zhu--aaron-marketing-skills  109 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 9 skills
      … 82 smaller, 553 skills
    data  1610 skills, 101 leaves
      community--antigravity-awesome-skills  678 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-6  78 skills, 1 leaves, 1 name blocks
      others--mukul975--anthropic-cybersecurity-skills  119 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 19 skills
      … 92 smaller, 813 skills
    finance  1188 skills, 69 leaves
      others--openaccountants--openaccountants  471 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  71 skills, 1 leaves, 1 name blocks
      community--antigravity-awesome-skills  352 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  52 skills, 1 leaves, 1 name blocks
      … 60 smaller, 365 skills
    unspecified  1076 skills, 82 leaves
      community--antigravity-awesome-skills  373 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  73 skills, 1 leaves, 1 name blocks
      … 78 smaller, 703 skills
    frontend  1018 skills, 82 leaves
      community--antigravity-awesome-skills  635 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 35 skills
      … 75 smaller, 383 skills
    databases  877 skills, 74 leaves
      community--antigravity-awesome-skills  438 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 38 skills
      … 69 smaller, 439 skills
    testing  788 skills, 81 leaves
      community--antigravity-awesome-skills  366 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  66 skills, 1 leaves, 1 name blocks
      … 77 smaller, 422 skills
    life-science  691 skills, 61 leaves
      community--antigravity-awesome-skills  201 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 1 skills
      … 58 smaller, 490 skills
    software  674 skills, 63 leaves
      community--antigravity-awesome-skills  345 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  45 skills, 1 leaves, 1 name blocks
      … 59 smaller, 329 skills
    media  470 skills, 57 leaves
      community--antigravity-awesome-skills  244 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-2  44 skills, 1 leaves, 1 name blocks
      … 54 smaller, 226 skills
    writing  393 skills, 58 leaves
      community--antigravity-awesome-skills  182 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  82 skills, 1 leaves, 1 name blocks
      … 56 smaller, 211 skills
    cloud-devops  390 skills, 29 leaves
      community--antigravity-awesome-skills  191 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  91 skills, 1 leaves, 1 name blocks
      … 27 smaller, 199 skills
    marketing  263 skills, 34 leaves
      community--antigravity-awesome-skills  104 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 4 skills
      … 32 smaller, 159 skills
    git  254 skills, 44 leaves
      community--antigravity-awesome-skills  115 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 15 skills
      … 42 smaller, 139 skills
    commerce  249 skills, 45 leaves
      community--antigravity-awesome-skills  96 skills, 1 leaves
      openai_official--plugins  18 skills, 1 leaves
      others--mukul975--anthropic-cybersecurity-skills  15 skills, 1 leaves
      … 42 smaller, 120 skills
    education  248 skills, 47 leaves
      community--antigravity-awesome-skills  78 skills, 1 leaves
      others--garethmanning--education-agent-skills  43 skills, 1 leaves
      others--mouadja02--skills  14 skills, 1 leaves
      … 44 smaller, 113 skills
    research  192 skills, 35 leaves
    … 7 smaller, 705 skills
  video  394 skills, 58 leaves
  image  297 skills, 53 leaves
  html  218 skills, 36 leaves
  document  174 skills, 39 leaves
  slides  169 skills, 14 leaves
  spreadsheet  152 skills, 18 leaves
  code-change  137 skills, 14 leaves
```

### Binding

2 the product or `unbound`, 3 another domain, 4 the clone, 5 a name block.

```
binding  21486 skills, 1702 leaves
  unbound  15250 skills, 1366 leaves
    legal  1545 skills, 91 leaves
      community--antigravity-awesome-skills  526 skills, 6 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 26 skills
      others--openaccountants--openaccountants  195 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  95 skills, 1 leaves, 1 name blocks
      others--lawve-ai--awesome-legal-skills  173 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  73 skills, 1 leaves, 1 name blocks
      others--aaron-he-zhu--aaron-marketing-skills  111 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 11 skills
      … 79 smaller, 540 skills
    design  1480 skills, 94 leaves
      community--antigravity-awesome-skills  670 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-6  70 skills, 1 leaves, 1 name blocks
      others--infrasity-labs--dev-gtm-claude-skills  146 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  46 skills, 1 leaves, 1 name blocks
      … 85 smaller, 664 skills
    security  1353 skills, 92 leaves
      community--antigravity-awesome-skills  834 skills, 9 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-7  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 34 skills
      others--mukul975--anthropic-cybersecurity-skills  178 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  78 skills, 1 leaves, 1 name blocks
      … 81 smaller, 341 skills
    data  1320 skills, 94 leaves
      community--antigravity-awesome-skills  527 skills, 6 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 27 skills
      others--mukul975--anthropic-cybersecurity-skills  103 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 3 skills
      … 86 smaller, 690 skills
    finance  1087 skills, 70 leaves
      others--openaccountants--openaccountants  476 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  76 skills, 1 leaves, 1 name blocks
      community--antigravity-awesome-skills  295 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-2  95 skills, 1 leaves, 1 name blocks
      … 62 smaller, 316 skills
    unspecified  1044 skills, 79 leaves
      community--antigravity-awesome-skills  364 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  64 skills, 1 leaves, 1 name blocks
      … 75 smaller, 680 skills
    frontend  873 skills, 80 leaves
      community--antigravity-awesome-skills  533 skills, 6 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 33 skills
      … 74 smaller, 340 skills
    ai  868 skills, 92 leaves
      community--antigravity-awesome-skills  378 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  78 skills, 1 leaves, 1 name blocks
      … 88 smaller, 490 skills
    media  727 skills, 70 leaves
      community--antigravity-awesome-skills  282 skills, 3 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-2  82 skills, 1 leaves, 1 name blocks
      … 67 smaller, 445 skills
    testing  698 skills, 75 leaves
      community--antigravity-awesome-skills  321 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 21 skills
      … 71 smaller, 377 skills
    software  674 skills, 63 leaves
      community--antigravity-awesome-skills  345 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  45 skills, 1 leaves, 1 name blocks
      … 59 smaller, 329 skills
    databases  636 skills, 53 leaves
      community--antigravity-awesome-skills  334 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 34 skills
      … 49 smaller, 302 skills
    life-science  627 skills, 59 leaves
      community--antigravity-awesome-skills  187 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  87 skills, 1 leaves, 1 name blocks
      … 57 smaller, 440 skills
    writing  353 skills, 49 leaves
      community--antigravity-awesome-skills  179 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  79 skills, 1 leaves, 1 name blocks
      … 47 smaller, 174 skills
    documents  291 skills, 56 leaves
      community--antigravity-awesome-skills  90 skills, 1 leaves
      others--foryourhealth111-pixel--vibe-skills  23 skills, 1 leaves
      others--mukul975--anthropic-cybersecurity-skills  16 skills, 1 leaves
      … 53 smaller, 162 skills
    education  235 skills, 48 leaves
      community--antigravity-awesome-skills  78 skills, 1 leaves
      others--garethmanning--education-agent-skills  44 skills, 1 leaves
      others--mukul975--anthropic-cybersecurity-skills  12 skills, 1 leaves
      … 45 smaller, 101 skills
    marketing  195 skills, 29 leaves
    commerce  185 skills, 37 leaves
    git  175 skills, 37 leaves
    cloud-devops  170 skills, 26 leaves
    research  156 skills, 29 leaves
    … 6 smaller, 558 skills
  mcp  1622 skills, 69 leaves
    ai  976 skills, 30 leaves
      community--awesome-claude-skills  738 skills, 8 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 38 skills
      community--antigravity-awesome-skills  153 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  53 skills, 1 leaves, 1 name blocks
      … 20 smaller, 85 skills
    … 20 smaller, 646 skills
  composio  1123 skills, 26 leaves
    ai  915 skills, 11 leaves
      community--awesome-claude-skills  738 skills, 8 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 38 skills
      community--antigravity-awesome-skills  132 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 32 skills
      … 1 smaller, 45 skills
    … 15 smaller, 208 skills
  azure  586 skills, 20 leaves
    security  196 skills, 7 leaves
    … 13 smaller, 390 skills
  google  535 skills, 24 leaves
    … 24 smaller, 535 skills
  claude  436 skills, 51 leaves
    … 20 smaller, 436 skills
  react  281 skills, 28 leaves
  github  271 skills, 16 leaves
  aws  262 skills, 15 leaves
  linkedin  227 skills, 21 leaves
  notion  173 skills, 12 leaves
  youtube  164 skills, 16 leaves
  openai  121 skills, 16 leaves
  instagram  110 skills, 17 leaves
  tiktok  94 skills, 1 leaves
  slack  73 skills, 1 leaves
  stripe  60 skills, 1 leaves
  shopify  54 skills, 1 leaves
  figma  44 skills, 1 leaves
```

### Audience

2 `unspecified`, `expert`, `executive`, or `beginner`, 3 another domain, 4 the clone, 5 a name block.

```
audience  19716 skills, 1603 leaves
  unspecified  18636 skills, 1537 leaves
    ai  1911 skills, 111 leaves
      community--awesome-claude-skills  742 skills, 8 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-7  42 skills, 1 leaves, 1 name blocks
      community--antigravity-awesome-skills  544 skills, 6 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-5  44 skills, 1 leaves, 1 name blocks
      … 97 smaller, 625 skills
    security  1775 skills, 102 leaves
      community--antigravity-awesome-skills  1114 skills, 12 leaves
        names-04  100 skills, 1 leaves, 1 name blocks
        names-03  100 skills, 1 leaves, 1 name blocks
        names-05  100 skills, 1 leaves, 1 name blocks
        names-02  100 skills, 1 leaves, 1 name blocks
        names-08  100 skills, 1 leaves, 1 name blocks
        names-00  100 skills, 1 leaves, 1 name blocks
        names-01  100 skills, 1 leaves, 1 name blocks
        names-09  100 skills, 1 leaves, 1 name blocks
        names-07  100 skills, 1 leaves, 1 name blocks
        names-06  100 skills, 1 leaves, 1 name blocks
        names-10  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 14 skills
      others--mukul975--anthropic-cybersecurity-skills  190 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  90 skills, 1 leaves, 1 name blocks
      … 88 smaller, 471 skills
    legal  1639 skills, 101 leaves
      community--antigravity-awesome-skills  535 skills, 6 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 35 skills
      others--openaccountants--openaccountants  195 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  95 skills, 1 leaves, 1 name blocks
      others--lawve-ai--awesome-legal-skills  160 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  60 skills, 1 leaves, 1 name blocks
      others--aaron-he-zhu--aaron-marketing-skills  115 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 15 skills
      … 89 smaller, 634 skills
    design  1603 skills, 99 leaves
      community--antigravity-awesome-skills  648 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-6  48 skills, 1 leaves, 1 name blocks
      others--infrasity-labs--dev-gtm-claude-skills  147 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  47 skills, 1 leaves, 1 name blocks
      … 90 smaller, 808 skills
    data  1569 skills, 101 leaves
      community--antigravity-awesome-skills  646 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-6  46 skills, 1 leaves, 1 name blocks
      others--mukul975--anthropic-cybersecurity-skills  116 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 16 skills
      … 92 smaller, 807 skills
    finance  1203 skills, 76 leaves
      others--openaccountants--openaccountants  482 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  82 skills, 1 leaves, 1 name blocks
      community--antigravity-awesome-skills  330 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 30 skills
      … 67 smaller, 391 skills
    frontend  1069 skills, 93 leaves
      community--antigravity-awesome-skills  617 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 17 skills
      … 86 smaller, 452 skills
    media  1037 skills, 89 leaves
      community--antigravity-awesome-skills  395 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  95 skills, 1 leaves, 1 name blocks
      … 85 smaller, 642 skills
    unspecified  1005 skills, 81 leaves
      community--antigravity-awesome-skills  329 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 29 skills
      … 77 smaller, 676 skills
    databases  864 skills, 74 leaves
      community--antigravity-awesome-skills  427 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 27 skills
      … 69 smaller, 437 skills
    testing  762 skills, 82 leaves
      community--antigravity-awesome-skills  337 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 37 skills
      … 78 smaller, 425 skills
    life-science  704 skills, 63 leaves
      community--antigravity-awesome-skills  199 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  99 skills, 1 leaves, 1 name blocks
      … 61 smaller, 505 skills
    software  623 skills, 62 leaves
      community--antigravity-awesome-skills  300 skills, 3 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
      … 59 smaller, 323 skills
    cloud-devops  370 skills, 28 leaves
      community--antigravity-awesome-skills  172 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  72 skills, 1 leaves, 1 name blocks
      … 26 smaller, 198 skills
    writing  369 skills, 59 leaves
      community--antigravity-awesome-skills  157 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  57 skills, 1 leaves, 1 name blocks
      … 57 smaller, 212 skills
    documents  351 skills, 58 leaves
      community--antigravity-awesome-skills  97 skills, 1 leaves
      others--foryourhealth111-pixel--vibe-skills  23 skills, 1 leaves
      others--mukul975--anthropic-cybersecurity-skills  16 skills, 1 leaves
      … 55 smaller, 215 skills
    git  265 skills, 46 leaves
      community--antigravity-awesome-skills  112 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 12 skills
      … 44 smaller, 153 skills
    commerce  262 skills, 45 leaves
      community--antigravity-awesome-skills  86 skills, 1 leaves
      openai_official--plugins  19 skills, 1 leaves
      others--browser-act--skills  18 skills, 1 leaves
      … 42 smaller, 139 skills
    education  255 skills, 52 leaves
      community--antigravity-awesome-skills  76 skills, 1 leaves
      others--garethmanning--education-agent-skills  44 skills, 1 leaves
      others--mouadja02--skills  13 skills, 1 leaves
      … 49 smaller, 122 skills
    marketing  248 skills, 33 leaves
      community--antigravity-awesome-skills  92 skills, 1 leaves
      others--infrasity-labs--dev-gtm-claude-skills  30 skills, 1 leaves
      others--nowork-studio--notfair-plugin  18 skills, 1 leaves
      … 30 smaller, 108 skills
    research  187 skills, 35 leaves
    … 6 smaller, 565 skills
  expert  922 skills, 44 leaves
    … 26 smaller, 922 skills
  executive  124 skills, 21 leaves
  beginner  34 skills, 1 leaves
```

### Language

2 `en`, `zh`, `es`, `pt`, or `ko`, 3 another domain, 4 the clone, 5 a name block.

```
language  19716 skills, 1567 leaves
  en  19190 skills, 1540 leaves
    ai  1933 skills, 109 leaves
      community--awesome-claude-skills  743 skills, 8 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-7  43 skills, 1 leaves, 1 name blocks
      community--antigravity-awesome-skills  575 skills, 6 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-5  75 skills, 1 leaves, 1 name blocks
      … 95 smaller, 615 skills
    security  1831 skills, 103 leaves
      community--antigravity-awesome-skills  1158 skills, 12 leaves
        names-04  100 skills, 1 leaves, 1 name blocks
        names-03  100 skills, 1 leaves, 1 name blocks
        names-05  100 skills, 1 leaves, 1 name blocks
        names-02  100 skills, 1 leaves, 1 name blocks
        names-08  100 skills, 1 leaves, 1 name blocks
        names-00  100 skills, 1 leaves, 1 name blocks
        names-01  100 skills, 1 leaves, 1 name blocks
        names-09  100 skills, 1 leaves, 1 name blocks
        names-07  100 skills, 1 leaves, 1 name blocks
        names-06  100 skills, 1 leaves, 1 name blocks
        names-10  100 skills, 1 leaves, 1 name blocks
        names-11  58 skills, 1 leaves, 1 name blocks
      others--mukul975--anthropic-cybersecurity-skills  192 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  92 skills, 1 leaves, 1 name blocks
      … 89 smaller, 481 skills
    design  1727 skills, 102 leaves
      community--antigravity-awesome-skills  746 skills, 8 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-6  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-7  46 skills, 1 leaves, 1 name blocks
      others--infrasity-labs--dev-gtm-claude-skills  151 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  51 skills, 1 leaves, 1 name blocks
      … 92 smaller, 830 skills
    legal  1679 skills, 99 leaves
      community--antigravity-awesome-skills  615 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 15 skills
      others--lawve-ai--awesome-legal-skills  182 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  82 skills, 1 leaves, 1 name blocks
      others--openaccountants--openaccountants  180 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  80 skills, 1 leaves, 1 name blocks
      … 88 smaller, 702 skills
    data  1633 skills, 101 leaves
      community--antigravity-awesome-skills  684 skills, 7 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-6  84 skills, 1 leaves, 1 name blocks
      others--mukul975--anthropic-cybersecurity-skills  120 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 20 skills
      … 92 smaller, 829 skills
    finance  1218 skills, 75 leaves
      others--openaccountants--openaccountants  464 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  64 skills, 1 leaves, 1 name blocks
      community--antigravity-awesome-skills  353 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  53 skills, 1 leaves, 1 name blocks
      … 66 smaller, 401 skills
    frontend  1121 skills, 91 leaves
      community--antigravity-awesome-skills  671 skills, 7 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-3  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-5  100 skills, 1 leaves, 1 name blocks
        names-4  100 skills, 1 leaves, 1 name blocks
        names-6  71 skills, 1 leaves, 1 name blocks
      … 84 smaller, 450 skills
    media  1043 skills, 88 leaves
      community--antigravity-awesome-skills  406 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 6 skills
      … 83 smaller, 637 skills
    unspecified  994 skills, 76 leaves
      community--antigravity-awesome-skills  331 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 31 skills
      … 72 smaller, 663 skills
    databases  905 skills, 73 leaves
      community--antigravity-awesome-skills  462 skills, 5 leaves
        names-3  100 skills, 1 leaves, 1 name blocks
        names-2  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-4  62 skills, 1 leaves, 1 name blocks
      … 68 smaller, 443 skills
    testing  789 skills, 80 leaves
      community--antigravity-awesome-skills  369 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  69 skills, 1 leaves, 1 name blocks
      … 76 smaller, 420 skills
    life-science  683 skills, 61 leaves
      community--antigravity-awesome-skills  189 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  89 skills, 1 leaves, 1 name blocks
      … 59 smaller, 494 skills
    software  678 skills, 62 leaves
      community--antigravity-awesome-skills  345 skills, 4 leaves
        names-2  100 skills, 1 leaves, 1 name blocks
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  100 skills, 1 leaves, 1 name blocks
        names-3  45 skills, 1 leaves, 1 name blocks
      … 58 smaller, 333 skills
    cloud-devops  386 skills, 28 leaves
      community--antigravity-awesome-skills  188 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  88 skills, 1 leaves, 1 name blocks
      … 26 smaller, 198 skills
    writing  374 skills, 58 leaves
      community--antigravity-awesome-skills  167 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        names-1  67 skills, 1 leaves, 1 name blocks
      … 56 smaller, 207 skills
    documents  349 skills, 58 leaves
      community--antigravity-awesome-skills  105 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 5 skills
      … 56 smaller, 244 skills
    git  273 skills, 47 leaves
      community--antigravity-awesome-skills  124 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 24 skills
      … 45 smaller, 149 skills
    commerce  269 skills, 46 leaves
      community--antigravity-awesome-skills  96 skills, 1 leaves
      openai_official--plugins  19 skills, 1 leaves
      others--browser-act--skills  17 skills, 1 leaves
      … 43 smaller, 137 skills
    marketing  263 skills, 34 leaves
      community--antigravity-awesome-skills  104 skills, 2 leaves
        names-0  100 skills, 1 leaves, 1 name blocks
        … 1 smaller, 4 skills
      … 32 smaller, 159 skills
    education  261 skills, 50 leaves
      community--antigravity-awesome-skills  78 skills, 1 leaves
      others--garethmanning--education-agent-skills  44 skills, 1 leaves
      others--mouadja02--skills  15 skills, 1 leaves
      … 47 smaller, 124 skills
    research  178 skills, 34 leaves
    … 6 smaller, 603 skills
  zh  448 skills, 24 leaves
    … 24 smaller, 448 skills
  es  60 skills, 1 leaves
  ko  9 skills, 1 leaves
  pt  9 skills, 1 leaves
```

### Provenance

2 the clone, 3 another domain, 4 a name block when that domain inside the clone is still over 100.

```
provenance  19716 skills, 828 leaves
  community--antigravity-awesome-skills  8254 skills, 95 leaves
    security  1164 skills, 12 leaves
      names-04  100 skills, 1 leaves
      names-03  100 skills, 1 leaves
      names-05  100 skills, 1 leaves
      names-02  100 skills, 1 leaves
      names-08  100 skills, 1 leaves
      names-00  100 skills, 1 leaves
      names-01  100 skills, 1 leaves
      names-09  100 skills, 1 leaves
      names-07  100 skills, 1 leaves
      names-06  100 skills, 1 leaves
      names-10  100 skills, 1 leaves
      … 1 smaller, 64 skills
    design  749 skills, 8 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-6  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-5  100 skills, 1 leaves
      names-4  100 skills, 1 leaves
      … 1 smaller, 49 skills
    data  687 skills, 7 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-5  100 skills, 1 leaves
      names-4  100 skills, 1 leaves
      … 1 smaller, 87 skills
    frontend  683 skills, 7 leaves
      names-2  100 skills, 1 leaves
      names-3  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-5  100 skills, 1 leaves
      names-4  100 skills, 1 leaves
      … 1 smaller, 83 skills
    legal  618 skills, 7 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-5  100 skills, 1 leaves
      names-4  100 skills, 1 leaves
      … 1 smaller, 18 skills
    ai  596 skills, 6 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-4  100 skills, 1 leaves
      … 1 smaller, 96 skills
    databases  462 skills, 5 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      … 1 smaller, 62 skills
    media  412 skills, 5 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      … 1 smaller, 12 skills
    unspecified  376 skills, 4 leaves
      names-2  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 76 skills
    testing  372 skills, 4 leaves
      names-2  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 72 skills
    finance  361 skills, 4 leaves
      names-2  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 61 skills
    software  348 skills, 4 leaves
      names-2  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 48 skills
    life-science  207 skills, 3 leaves
      names-0  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      … 1 smaller, 7 skills
    cloud-devops  191 skills, 2 leaves
    writing  182 skills, 2 leaves
    … 12 smaller, 846 skills
  community--awesome-claude-skills  864 skills, 29 leaves
    ai  743 skills, 8 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-6  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      names-5  100 skills, 1 leaves
      names-4  100 skills, 1 leaves
      … 1 smaller, 43 skills
    … 21 smaller, 121 skills
  others--mukul975--anthropic-cybersecurity-skills  818 skills, 26 leaves
    security  192 skills, 2 leaves
    … 23 smaller, 626 skills
  others--mouadja02--skills  792 skills, 26 leaves
    … 26 smaller, 792 skills
  others--openaccountants--openaccountants  781 skills, 19 leaves
    finance  482 skills, 5 leaves
      names-3  100 skills, 1 leaves
      names-2  100 skills, 1 leaves
      names-1  100 skills, 1 leaves
      names-0  100 skills, 1 leaves
      … 1 smaller, 82 skills
    legal  196 skills, 2 leaves
    … 12 smaller, 103 skills
  others--infrasity-labs--dev-gtm-claude-skills  588 skills, 24 leaves
    design  151 skills, 2 leaves
    … 22 smaller, 437 skills
  openai_official--plugins  536 skills, 27 leaves
    … 27 smaller, 536 skills
  others--nvidia--skills  399 skills, 24 leaves
  social--davepoon--buildwithclaude  393 skills, 25 leaves
  others--gooseworks-ai--goose-skills  293 skills, 23 leaves
  others--lawve-ai--awesome-legal-skills  269 skills, 19 leaves
  others--foryourhealth111-pixel--vibe-skills  258 skills, 19 leaves
  others--sandbaseai--sandbase-skills  246 skills, 21 leaves
  others--onewave-ai--claude-skills  232 skills, 24 leaves
  others--makenotion--notion-cookbook  205 skills, 9 leaves
  others--neolabhq--context-engineering-kit  204 skills, 16 leaves
  others--wanshuiyin--auto-claude-code-research-in-sleep  189 skills, 20 leaves
  others--vodailocz--kilo-kit-mcp  180 skills, 21 leaves
  others--k-dense-ai--scientific-agent-skills  177 skills, 17 leaves
  others--kensaurus--cursor-kenji  171 skills, 22 leaves
  others--garethmanning--education-agent-skills  165 skills, 9 leaves
  others--indranilbanerjee--digital-marketing-pro  164 skills, 11 leaves
  others--google--skills  155 skills, 19 leaves
  others--aaron-he-zhu--aaron-marketing-skills  120 skills, 3 leaves
  others--aeonfun--aeon  110 skills, 21 leaves
  others--browser-act--skills  103 skills, 13 leaves
  others--orchestra-research--ai-research-skills  98 skills, 1 leaves
  others--nowork-studio--notfair-plugin  96 skills, 1 leaves
  platforms--microsoft--azure-skills  86 skills, 1 leaves
  others--jasoncolapietro--suede-creator-skills  79 skills, 1 leaves
  others--deanpeters--product-manager-skills  77 skills, 1 leaves
  others--lambdatest--agent-skills  73 skills, 1 leaves
  others--alinaqi--maggy  73 skills, 1 leaves
  others--phuryn--pm-skills  69 skills, 1 leaves
  high_stars--gstack  63 skills, 1 leaves
  others--khazp--vibe-coding-prompt-template  55 skills, 1 leaves
  others--xberg-io--xberg  54 skills, 1 leaves
  others--bitwize-music-studio--claude-ai-music-skills  53 skills, 1 leaves
  others--coreyhaines31--marketingskills  50 skills, 1 leaves
  others--chrono-meta--forge-harness  46 skills, 1 leaves
  others--dembrandt--dembrandt-skills  45 skills, 1 leaves
  openai_official--skills  44 skills, 1 leaves
  social--everyinc--compound-engineering-plugin  43 skills, 1 leaves
  others--heygen-com--hyperframes  40 skills, 1 leaves
  others--eronred--aso-skills  40 skills, 1 leaves
  others--mattpocock--skills  37 skills, 1 leaves
  others--larksuite--cli  37 skills, 1 leaves
  others--huifer--wellally-health  37 skills, 1 leaves
  others--thedotmack--claude-mem  36 skills, 1 leaves
  others--agricidaniel--claude-seo  35 skills, 1 leaves
  others--ilyautov--small-business-ru  34 skills, 1 leaves
  others--qdrant--skills  33 skills, 1 leaves
  social--anthropics--claude-plugins-official  33 skills, 1 leaves
  others--bmad-code-org--bmad-method  33 skills, 1 leaves
  others--eduardo-sl--go-agent-skills  33 skills, 1 leaves
  community--claude-plugins-community  31 skills, 1 leaves
  others--paramchoudhary--resumeskills  29 skills, 1 leaves
  others--mblode--agent-skills  28 skills, 1 leaves
  others--tjboudreaux--cc-thinking-skills  28 skills, 1 leaves
  platforms--juliusbrussee--caveman  28 skills, 1 leaves
  others--yusufkaraaslan--skill_seekers  26 skills, 1 leaves
  others--sergebulaev--linkedin-skills  26 skills, 1 leaves
  others--wendylabsinc--claude-skills  26 skills, 1 leaves
  high_stars--addyosmani-agent-skills  25 skills, 1 leaves
  others--rorkai--app-store-connect-cli-skills  25 skills, 1 leaves
  others--amirkiarafiei--subagent-cli-skills  25 skills, 1 leaves
  others--muratcankoylan--agent-skills-for-context-engineering  24 skills, 1 leaves
  others--heshamfs--materials-simulation-skills  24 skills, 1 leaves
  others--zeropointrepo--youtube-skills  24 skills, 1 leaves
  others--sanjay3290--ai-skills  24 skills, 1 leaves
  others--helius-labs--core-ai  24 skills, 1 leaves
  others--ganyuanran--aegis  23 skills, 1 leaves
  others--brianrwagner--ai-marketing-claude-code-skills  23 skills, 1 leaves
  others--supercmohq--supercmo-skills  23 skills, 1 leaves
  others--sendmux--skills  22 skills, 1 leaves
  others--snyk--agent-scan  21 skills, 1 leaves
  others--tencent--ai-infra-guard  21 skills, 1 leaves
  social--jnmetacode--superpowers-zh  21 skills, 1 leaves
  others--veniceai--skills  21 skills, 1 leaves
  others--rainmanjam--poka-yoke  20 skills, 1 leaves
  anthropic_official  20 skills, 1 leaves
  others--aidevgtm--gtm-cofounder  19 skills, 1 leaves
  community--agent-html-skills  19 skills, 1 leaves
  others--tronghieu--agent-skills  19 skills, 1 leaves
  others--prompt-security--clawsec  16 skills, 1 leaves
  others--redis--agent-skills  16 skills, 1 leaves
  others--czlonkowski--n8n-skills  15 skills, 1 leaves
  platforms--google--agents-cli  15 skills, 1 leaves
  others--uucz--moyu  15 skills, 1 leaves
  high_stars--superpowers  15 skills, 1 leaves
  others--raintree-technology--hig-doctor  15 skills, 1 leaves
  others--ognjengt--founder-skills  15 skills, 1 leaves
  others--mohamedabdallah-14--unslop  15 skills, 1 leaves
  others--zekainie--universal-examprep-skill  14 skills, 1 leaves
  others--zhanghandong--makepad-skills  14 skills, 1 leaves
  others--zincio--skills  14 skills, 1 leaves
  others--neeeophytee--finding-unknowns-skills  14 skills, 1 leaves
  others--orkas-ai--orkas-videostudio  14 skills, 1 leaves
  others--yanniskiefer--dark-psychology-skills  13 skills, 1 leaves
  others--resciencelab--opc-skills  13 skills, 1 leaves
  others--scrapecreators--social-media-research-skills  13 skills, 1 leaves
  others--transloadit--skills  13 skills, 1 leaves
  others--saleh-alhaddad--itqan-engineering  13 skills, 1 leaves
  others--fishzjp--qa-skills  13 skills, 1 leaves
  others--nextlevelbuilder--ui-ux-pro-max-skill  13 skills, 1 leaves
  others--honeydew-ai--honeydew-ai-coding-agents-plugins  13 skills, 1 leaves
  others--santifer--career-ops  13 skills, 1 leaves
  others--leonxlnx--taste-skill  13 skills, 1 leaves
  others--realkimbarrett--advertising-skills  12 skills, 1 leaves
  platforms--remotion-dev--skills  12 skills, 1 leaves
  platforms--lllllllama--rigorpilot-skills  11 skills, 1 leaves
  others--aklofas--kicad-happy  11 skills, 1 leaves
  others--mcollina--skills  11 skills, 1 leaves
  others--scarletkc--agents  11 skills, 1 leaves
  others--simon-he95--markstream-vue  11 skills, 1 leaves
  platforms--vercel-labs--agent-browser  10 skills, 1 leaves
  others--metalbear-co--skills  10 skills, 1 leaves
  others--noizai--skills  10 skills, 1 leaves
  others--ricardodantas--skills  10 skills, 1 leaves
  others--cloudai-x--threejs-skills  10 skills, 1 leaves
  others--awrshift--claude-memory-kit  10 skills, 1 leaves
  others--egonex-ai--understand-anything  9 skills, 1 leaves
  others--hanhuark--mechanical-engineering-research-skill  9 skills, 1 leaves
  popular--vercel-agent-skills  9 skills, 1 leaves
  others--ehmo--platform-design-skills  8 skills, 1 leaves
  others--ohad6k--emulo  8 skills, 1 leaves
  others--mailtrap--mailtrap-skills  7 skills, 1 leaves
  others--kayforkind--reimagine-it  7 skills, 1 leaves
  others--shouldnotappearcalm--a-share-skill  7 skills, 1 leaves
  others--fvadicamo--dev-agent-skills  7 skills, 1 leaves
  others--ibelick--ui-skills  7 skills, 1 leaves
  others--stjbrown--agent-knowledge  7 skills, 1 leaves
  others--zxkane--aws-skills  6 skills, 1 leaves
  others--testdino-hq--playwright-skill  6 skills, 1 leaves
  others--nanako0129--sepia  6 skills, 1 leaves
  others--hermes-labs-ai--lintlang  6 skills, 1 leaves
  others--uipath--coder_eval  6 skills, 1 leaves
  others--khendzel--skills-janitor  6 skills, 1 leaves
  others--huangchihhungleo--claude-real-video  5 skills, 1 leaves
  others--resend--resend-skills  5 skills, 1 leaves
  others--swaylq--humanize-chinese  5 skills, 1 leaves
  others--rameerez--claude-code-startup-skills  5 skills, 1 leaves
  others--vshulcz--deja-vu  5 skills, 1 leaves
  others--citlyze--citlyze-skills  5 skills, 1 leaves
  others--plasma-ai--fractal  5 skills, 1 leaves
  others--cypress-io--ai-toolkit  5 skills, 1 leaves
  others--frmoretto--clarity-gate  4 skills, 1 leaves
  others--makenotion--claude-code-notion-plugin  4 skills, 1 leaves
  others--zilliztech--mfs  4 skills, 1 leaves
  others--giasip--giasip-skills  4 skills, 1 leaves
  others--charlie85270--dorothy  4 skills, 1 leaves
  others--zapier--zapier-mcp  4 skills, 1 leaves
  others--obra--superpowers-lab  4 skills, 1 leaves
  others--talkstream--ru-text  4 skills, 1 leaves
  others--perso-ai--perso-dubbing-plugin  3 skills, 1 leaves
  others--hedralab--eskill  3 skills, 1 leaves
  others--ilyautov--humanizer-ru  3 skills, 1 leaves
  others--hqhq1025--skill-optimizer  3 skills, 1 leaves
  others--martindelophy--ai-video-editor  3 skills, 1 leaves
  others--gokapso--agent-skills  3 skills, 1 leaves
  others--orziz--odai  3 skills, 1 leaves
  others--optim-agent--optim-agent  3 skills, 1 leaves
  others--officialzeroxyz--zero-plugins  3 skills, 1 leaves
  others--manavmishra--zeroslop  3 skills, 1 leaves
  others--xquik-dev--x-twitter-scraper  3 skills, 1 leaves
  others--vaibhavarora14--job-application-agent  3 skills, 1 leaves
  others--tt-a1i--archify  2 skills, 1 leaves
  others--linked-api--linkedin-skills  2 skills, 1 leaves
  others--zarazhangrui--frontend-slides  2 skills, 1 leaves
  others--thousandflowers--skillreaper  2 skills, 1 leaves
  others--bevibing--tutor-skills  2 skills, 1 leaves
  others--voltagent--voltagent  2 skills, 1 leaves
  others--coderabbitai--skills  2 skills, 1 leaves
  others--qiuner--birdview  2 skills, 1 leaves
  others--bomx--distribb-skill  2 skills, 1 leaves
  others--lukstei--slop-grader  2 skills, 1 leaves
  others--maksim-burtsev--simple-man  2 skills, 1 leaves
  others--kevin7qi--codex-collab  2 skills, 1 leaves
  others--angular--skills  2 skills, 1 leaves
  others--vladimir-human--humanizer-ru  2 skills, 1 leaves
  others--squirrelscan--skills  2 skills, 1 leaves
  others--gitroomhq--postiz-agent  2 skills, 1 leaves
  platforms--vercel-labs--skills  2 skills, 1 leaves
  others--avdlee--swiftui-agent-skill  2 skills, 1 leaves
  others--panniantong--agent-reach  1 skills, 1 leaves
  others--antonbabenko--terraform-skill  1 skills, 1 leaves
  others--smixs--creative-director-skill  1 skills, 1 leaves
  others--oliver-zehentleitner--keep-the-why  1 skills, 1 leaves
  others--scarletkc--vexor  1 skills, 1 leaves
  others--lindblomstefan--skills-library  1 skills, 1 leaves
  others--op7418--nanobanana-ppt-skills  1 skills, 1 leaves
  others--zarazhangrui--codebase-to-course  1 skills, 1 leaves
  others--behisecc--vibesec-skill  1 skills, 1 leaves
  others--kgraph57--mckinsey-style-visualization-skill  1 skills, 1 leaves
  others--modem-dev--skills  1 skills, 1 leaves
  others--conorluddy--ios-simulator-skill  1 skills, 1 leaves
  others--seanzor--claude-speed-reader  1 skills, 1 leaves
  others--fujibee--agmsg  1 skills, 1 leaves
  others--wrsmith108--varlock-claude-skill  1 skills, 1 leaves
  others--renezander030--capcut-cli  1 skills, 1 leaves
  others--lackeyjb--playwright-skill  1 skills, 1 leaves
  others--mvanhorn--last30days-skill  1 skills, 1 leaves
  others--d1vai--d1v-cli  1 skills, 1 leaves
  others--vmware-skills--vmware-aiops  1 skills, 1 leaves
  others--everyinc--charlie-cfo-skill  1 skills, 1 leaves
  others--ericyoung-183--alpha-insights  1 skills, 1 leaves
  others--woniu9524--open-web-bridge  1 skills, 1 leaves
  community--html-plan  1 skills, 1 leaves
  social--graphify-labs--graphify  1 skills, 1 leaves
  others--reliefeai--browser-relay  1 skills, 1 leaves
  others--jthack--ffuf_claude_skill  1 skills, 1 leaves
  others--trycourier--courier-skills  1 skills, 1 leaves
  others--ethos-link--rails-conventions  1 skills, 1 leaves
  others--sametbrr--llm-wiki-manager  1 skills, 1 leaves
  others--cosmoblk--email-marketing-bible  1 skills, 1 leaves
  others--pattern-ai-labs--agentcall  1 skills, 1 leaves
  others--taisly--agent  1 skills, 1 leaves
  others--dannwaneri--spec-writer  1 skills, 1 leaves
  others--continuum-ai-corp--orcareplay  1 skills, 1 leaves
  others--drogers0--gh-image  1 skills, 1 leaves
  others--meodai--skill.color-expert  1 skills, 1 leaves
  others--wshuyi--x-article-publisher-skill  1 skills, 1 leaves
  others--muthuishere--hand-drawn-diagrams  1 skills, 1 leaves
  others--explorium-ai--vibeprospecting-plugin  1 skills, 1 leaves
  others--blader--humanizer  1 skills, 1 leaves
  others--eatmoreduck--boss-zhipin-scraper  1 skills, 1 leaves
  others--dankofly--perfectify  1 skills, 1 leaves
  others--dmoshehun-prog--learn-from-materials  1 skills, 1 leaves
  others--agiwhitelist--auteur  1 skills, 1 leaves
  others--omkamal--pypict-claude-skill  1 skills, 1 leaves
  others--truongduy2611--app-store-preflight-skills  1 skills, 1 leaves
  others--video-db--skills  1 skills, 1 leaves
  others--wgwtest--novel-writing  1 skills, 1 leaves
  others--xquik-dev--tweetclaw  1 skills, 1 leaves
  others--notmyself--claude-win11-speckit-update-skill  1 skills, 1 leaves
  high_stars--andrej-karpathy-skills  1 skills, 1 leaves
  others--shadowpr0--beautiful_prose  1 skills, 1 leaves
  others--komal-skynet--claude-skill-homeassistant  1 skills, 1 leaves
  others--morluto--rea  1 skills, 1 leaves
  others--zscole--model-hierarchy-skill  1 skills, 1 leaves
  others--pspdfkit-labs--nutrient-agent-skill  1 skills, 1 leaves
  others--ryan-yang125--motion-lexicon  1 skills, 1 leaves
  others--op7418--youtube-clipper-skill  1 skills, 1 leaves
  others--exadel-inc--agentic-readiness-assessment  1 skills, 1 leaves
  others--baskduf--fablecodex  1 skills, 1 leaves
  others--efremidze--swift-patterns-skill  1 skills, 1 leaves
  others--csthink--dashmotion  1 skills, 1 leaves
  others--socai-io--jev-social  1 skills, 1 leaves
  others--cloudflare--security-audit-skill  1 skills, 1 leaves
  others--pleaseprompto--notebooklm-skill  1 skills, 1 leaves
  others--cyperx84--claude-skills-mental-models  1 skills, 1 leaves
  others--shadowpr0--security-bluebook-builder  1 skills, 1 leaves
  others--superdesigndev--superdesign-skill  1 skills, 1 leaves
  others--robzolkos--skill-rails-upgrade  1 skills, 1 leaves
  others--takechanman1228--claude-ecom  1 skills, 1 leaves
  others--k-kolomeitsev--data-structure-protocol  1 skills, 1 leaves
  others--ramzesenok--ios-accessibility-audit-skill  1 skills, 1 leaves
  others--degausai--wonda  1 skills, 1 leaves
  others--alisa0808--vibe-creating-skill  1 skills, 1 leaves
  others--jimmysadek--youtube-fetcher-to-markdown  1 skills, 1 leaves
  others--axelv--claude-skill-code-walkthrough  1 skills, 1 leaves
  others--deusyu--translate-book  1 skills, 1 leaves
  others--digidai--product-manager-skills  1 skills, 1 leaves
  others--lewislulu--html-ppt-skill  1 skills, 1 leaves
  others--more-io--claude-apple-bridges  1 skills, 1 leaves
  platforms--designed-by-ai--skills  1 skills, 1 leaves
  community--html-it  1 skills, 1 leaves
  others--wrsmith108--linear-claude-skill  1 skills, 1 leaves
  others--tubo2333--obsidian-knowledge-brain  1 skills, 1 leaves
  others--apitube--news-api-skills  1 skills, 1 leaves
  others--massimodeluisa--recursive-decomposition-skill  1 skills, 1 leaves
  others--rebelytics--one-skill-to-rule-them-all  1 skills, 1 leaves
```

## One skill, several jobs

One skill already sits on more than one job. `html-plan` is a methodology and an HTML artifact. `verification-before-completion` is a methodology and a verification gate. `codebase-diagrams-and-slides` is a repo explanation and a deck. A single parent folder has to drop one of those.

The first measurement used six job names on name plus description only. Of the 19,716 skills, 5,720 matched at least one of those six. **1,179 of those, about 1 in 5, matched two or more.**

| Labels on one skill | Count |
|---:|---:|
| 0 | 13,996 |
| 1 | 4,541 |
| 2 | 979 |
| 3 | 184 |
| 4 | 15 |
| 5 | 1 |

A pair here is a count, not a limit. It means "these two job labels show up on the same skill." A skill with three job labels is counted in each of its two-label combinations. Job, domain, and the other facets do not cap the number of labels.

| Two job labels on the same skill | Skills |
|---|---:|
| methodology + verification | 290 |
| methodology + reflection | 288 |
| reflection + verification | 254 |
| methodology + repo understanding | 224 |
| verification + repo understanding | 159 |
| reflection + repo understanding | 157 |

The later run, which also reads headings and uses eight job names, finds 6,508 skills with no job and 6,273 with two or more. That is the Implementation section.

A tree is a way to browse one facet. Clustering descriptions is a way to propose domain names and to find duplicates. Neither one is the stored label. Assign job labels with a fixed rubric. Let clustering suggest domain labels.

## Borrowed from the ads verticals

Source files, fetched 2026-10-05, live in [`raw_materials/ad-verticals/`](../../raw_materials/ad-verticals/SOURCES.md). The design note is [`ad-vertical-trees.md`](ad-vertical-trees.md). This section is the part adopted into the label system.

Google, IAB, Meta, and TikTok each store a node as an id plus a parent id. The path is rebuilt from the parents. Each tree asks one question. Semantic depth stops near 3. A closed list (languages, US states, car brands) is allowed to go deeper, and it is its own tree. The leftover is a named sibling (`Other In-Market`, TikTok’s `Other Apparel & Accessories`). Audience size is stored on the node. IAB puts purpose, form, source, language, and risk in a second file, beside the aboutness tree. Meta’s special-ad flags and IAB’s `SCD` marks sit beside a category and do not add a level.

### Node

Every semantic node, in every facet, uses this record. The path is display. The id survives a rename.

| Field | Meaning |
|---|---|
| `id` | Stable id inside the facet. Our ids stay the slugs already in use (`methodology`, `software`, `en`). |
| `parent_id` | Empty on a facet root. |
| `name` | Display name. |
| `skill_count` | How many skills sit on this node, including children. A column. |
| `external_ids` | Optional. IAB Content 3.1 unique id, Google Ads topic criterion id, or an IAB descriptive-vector id. Absent when those trees have no node at this grain. |

`rest` is a real child: its `parent_id` is the parent, its `id` is `<parent>/rest`, and it stays even when it holds 5,945 skills. A `names-N` block is not a row in this tree.

Depth of a semantic path is at most 3 (`domain / software / python`, `job / methodology / plan`). Language, Binding, and Provenance are the closed lists, so a clone name or a product name is the whole value of that facet, not a fourth segment glued under Job.

### Facets are the IAB vectors

The eight facets stay. They line up with IAB’s split between the aboutness tree and the descriptive vectors.

| Facet | Ads question it matches | External root |
|---|---|---|
| Domain | What the work is about | IAB Content 3.1, and Google content topics (`verticals.csv`) |
| Job | What the instruction is for | IAB Content Purpose (`1010`) |
| Form | Steps, judgment, or lookup | IAB Content Purpose, finer than Job |
| Artifact | What file must come out | IAB Content Form Factor (`1022`), only for a file shape they name |
| Language | Language of the instruction | IAB `*Content Language Extension` (`1030`), ISO-639-1 |
| Provenance | Who produced the file | IAB Content Source (`1215`), as a class on top of the clone id |
| Audience | Who the words are for | The short exclusive tree. Google detailed demographics is 25 nodes, depth ≤ 3. Our four values stay. |
| Binding | Which product the text is tied to | No external list. Azure, Notion, and Figma are not in the Merchant taxonomy. The id-plus-parent shape is what gets borrowed. |

Provenance keeps the clone as its id. It also takes one IAB source class:

| Clone kind | IAB id | IAB name |
|---|---|---|
| `anthropic_official`, `openai_official` | `1216` | Professionally Produced |
| `community`, `social` packs that collect other people’s skills | `1218` | Aggregated/Curated |
| A single-author repo under `others`, `high_stars`, `platforms`, `popular` | `1217` | User Generated |

Form takes a purpose id where the vector has a node:

| Form | IAB id | IAB name |
|---|---|---|
| technique | `1017` | Instructional Content |
| reference | `5S2VRK` | Informational |
| pattern | — | No vector node for a judgment or a principle |

Job takes a purpose id only where the meaning matches. The other jobs keep our id and no external id.

| Job | IAB id | IAB name |
|---|---|---|
| methodology | `1017` | Instructional Content |
| reflection, and its child `review` | `1021` | Review |
| The research *subject* stays on Domain. A skill whose job is a literature pass can also carry purpose `1011` | `1011` | Academic/Research Content |
| verification, repo-understanding, output-format, discovery, skill-authoring, audience | — | No purpose node |

Artifact takes a form-factor id where the file shape matches.

| Artifact | IAB id | IAB name |
|---|---|---|
| video | `1028` | Video |
| image | `1024` | Images/Galleries |
| document, slides, html | `1027` | Textual |
| spreadsheet, code-change, none | — | No form-factor node |

Language already follows the extension rule: `en`, `zh`, `es`, `pt`, `ko` are ISO-639-1 codes. The facet does not grow a tree under `en`.

### Domain crosswalk

Our domain id stays the label. The external ids are attached when the ads node is the same subject. “Nearest” means the ads node is the right family and the wrong grain, so it is stored as a pointer and is not a substitute for our id. “None” means using their node would merge a split this corpus needs, or they have no such node.

Ids are IAB Content Taxonomy 3.1 unique ids, and Google Ads topic criterion ids from `verticals.csv`.

| Our domain | Fit | IAB id | IAB path | Google topic id | Google path |
|---|---|---|---|---:|---|
| software | nearest | — | — | 31 | `/Computers & Electronics/Programming` |
| ai | nearest | 597 | Technology & Computing / Artificial Intelligence | — | — |
| security | nearest | 618 | Computing / Information and Network Security | 314 | `/Computers & Electronics/Computer Security` |
| data | none | — | — | — | — |
| design | nearest | 204 | Fine Art / Design | — | — |
| finance | same | 52 | Business and Finance | 7 | `/Finance` |
| testing | none | — | — | — | — |
| writing | nearest | 266 | Hobbies & Interests / Content Production / Freelance Writing | — | — |
| frontend | nearest | 629 | Computing / Internet / Web Design and HTML | — | — |
| business | nearest | 53 | Business and Finance / Business | 12 | `/Business & Industrial` |
| media | nearest | 264 | Hobbies & Interests / Content Production | 3 | `/Arts & Entertainment` |
| cloud-devops | nearest | 620 | Computing / Internet / Cloud Computing | 1298 | `/Computers & Electronics/Networking/Distributed & Cloud Computing` |
| legal | same | 383 | Law | 19 | `/Law & Government` |
| productivity | nearest | W3CW2J | Computer Software and Applications / Productivity | — | — |
| marketing | same | 58 | Business / Marketing and Advertising | 25 | `/Business & Industrial/Advertising & Marketing` |
| life-science | nearest | 286 | Medical Health | 45 | `/Health` |
| git | none | — | — | — | — |
| research | nearest | 464 | Science | 174 | `/Science` |
| systems | nearest | 615 | Computer Software and Applications / Operating Systems | 303 | `/Computers & Electronics/Software/Operating Systems` |
| databases | same | 611 | Computer Software and Applications / Databases | — | — |
| backend | none | — | — | — | — |
| education | same | 132 | Education | 958 | `/Jobs & Education` |
| documents | none | — | — | — | — |
| games | same | 680 | Video Gaming | 8 | `/Games` |
| mobile | nearest | — | — | 1382 | `/Computers & Electronics/Software/Operating Systems/Mobile OS` |
| commerce | same | 473 | Shopping | 18 | `/Shopping & Retailers` |
| unspecified | none | — | — | — | — |

Same-grain attachments are finance, legal, marketing, databases, education, games, and commerce. Those seven can be filtered by the external id without moving a skill off our domain. The nearest rows are pointers for anyone joining this corpus to an ads taxonomy. They do not replace `software`, `ai`, or `security`.

Programming under Google topics continues into C & C++, Java, Scripting Languages, Development Tools, and Windows & .NET. Our language children under software (python, typescript, javascript, go, rust) have no row there, so they keep our ids and an empty `external_ids`. IAB’s single Artificial Intelligence node is the same situation for agent, model, llm, and prompt.

Law (`383`) and Medical Health (`286`) carry IAB’s `SCD` mark in the taxonomy file. Legal and life-science therefore take a `sensitive` flag on the node. The flag does not add a child. The discovery assignment of 1,203 is the same kind of flag on the Job side: `quality: raw-word-match`, with the 21 files that actually find another skill left on the discovery label.

### What stays ours

The engineering children, the job children, Binding’s product list, and the clone id have no ads parent worth adopting. `rest` is the borrowed residual. The ≤100 browse index stays a separate file so a large clone can still be paged through. The semantic tree is the id, the parent, the count, and the external id when the table above has one.

## Implementation

The label list for the run that has already been applied is [`config/skill-label-system.yaml`](../../config/skill-label-system.yaml). [`scripts/label_skills.py`](../../scripts/label_skills.py) reads those ids and assigns every `SKILL.md`. That file currently lists the first 8 jobs, the 3 forms, the 26 domains plus `unspecified`, and provenance.

| Output | What it holds |
|---|---|
| [`data/processed/skill-labels.jsonl`](../../data/processed/skill-labels.jsonl) | One JSON object per skill: path, name, description, provenance, channel, form, jobs, domains |
| [`data/processed/skill-label-summary.md`](../../data/processed/skill-label-summary.md) | Counts after the latest run |

Provenance is the git clone path under `public_skills/`. Form, job, and domain are matched on the folder name, the `name` and `description` frontmatter, and markdown headings. The full body is not scanned, so a passing mention of "test" in a paragraph does not become a verification label. A heading or a description does.

Run on 2026-10-05, 19,716 skills, with the 8-job list:

| Facet | Result |
|---|---|
| Form | technique 11,473; pattern 6,910; reference 1,333 |
| Job | 6,508 have none. Of the rest, 6,935 have one job and 6,273 have two or more. Largest jobs: methodology 8,306, verification 5,243, reflection 3,078, repo-understanding 2,454. The raw discovery count is 1,203; 21 of those files are about finding another skill. |
| Domain | 18,633 have a named domain. 1,083 (5.5%) stay `unspecified` |

The 6,508 with no job are the reason the Job list has eight more labels. Those eight take Job coverage from 67% to about 91%. Artifact, Binding, Audience, and Language are specified above and are not in the jsonl yet.
