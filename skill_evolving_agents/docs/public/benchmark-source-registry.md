# Benchmark source registry: reusable knowledge and expert procedures

This document lists candidate sources for **reusable knowledge** and **expert
procedure** benchmarks. It is a source catalogue, not a label set. A source is
not ground truth merely because it is official, popular, or well written.

See [benchmark-design.md](benchmark-design.md) for the golden-skill, simulator,
multi-turn trace, and internal-stage labeling design.

## 1. Two independent questions

Every source must be scored on two dimensions:

| Question | Meaning |
|---|---|
| **Authority** | How reliable is the source for the claimed facts or procedure? |
| **Agent eligibility** | Can an LLM/agent retrieve it, draft from it, execute it in a sandbox, or must it refuse/escalate? |

A highly authoritative procedure can be **ineligible for execution** — for
example, operating a plane, a train, a surgical procedure, or a power grid.

Eligibility classes:

- `answer` — retrieve and cite the documented procedure.
- `draft` — produce a checklist or plan for a qualified human.
- `execute` — perform in a digital sandbox with observable results.
- `refuse` — refuse autonomous action and escalate.

## 2. Trust tiers

| Tier | Source type | May become a gold label? |
|---|---|---|
| T0 | Law, regulation, standard, official vendor documentation | Yes, for the covered fact or procedure |
| T1 | Named expert book, handbook, or reviewed playbook | Only with independent domain review |
| T2 | Experience-based post with reuse evidence | No; needs cross-source or executable confirmation |
| T3 | Single anecdote, advertisement, affiliate post | No |
| T4 | Model-generated synthesis | Never |

For experience-based sources, engagement is a **candidate-ranking signal**, not
truth. Likes are weaker than saves; saves are weaker than independent reuse,
successful execution, or expert confirmation.

## 3. Regulators, standards bodies, and official procedures

### Physical and safety-critical domains — reference and refusal only

| Domain | Sources | Eligibility |
|---|---|---|
| Aviation | [FAA handbooks and manuals](https://www.faa.gov/regulations_policies/handbooks_manuals/aviation), [Aeronautical Information Manual](https://www.faa.gov/air_traffic/publications/atpubs/aim_html/), 14 CFR, ICAO Annexes and PANS, manufacturer flight crew operating manuals (restricted) | `answer`, `draft` with licensed review, `refuse` execution |
| Rail | [FRA regulations](https://www.fra.dot.gov/), [eCFR Title 49](https://www.ecfr.gov/current/title-49), UIC leaflets, RSSB Rule Book, ERA ERTMS/ETCS specifications, operator rule books (restricted) | `answer`, `draft`, `refuse` |
| Maritime | IMO SOLAS/COLREGS, [USCG navigation center](https://www.navcen.uscg.gov/), ICS Bridge Procedures Guide | `answer`, `draft`, `refuse` |
| Medicine | WHO guidelines, NICE, CDC, FDA labels, NHS guidance, Merck Manual, Harrison's | `answer`, `draft` with clinician, never autonomous treatment |
| Emergency response | FEMA, NFPA, OSHA | `answer`, `draft`, `refuse` |
| Industrial and energy | ISO, IEC, NERC, ASME, API, manufacturer manuals | `answer`, `draft`, `refuse` |
| Automotive repair | NHTSA, SAE, manufacturer service information, [iFixit](https://www.ifixit.com/Guide) | `answer`, `draft`; physical work not eligible |
| Laboratory and biosafety | CDC/NIH biosafety guidance, WHO laboratory manuals | `answer`, `draft`, `refuse` |
| Construction | ICC codes, OSHA, manufacturer installation manuals | `answer`, `draft`, `refuse` |

These sources are valuable because they define mature procedure structure:

- authority, scope, and applicable version;
- required qualifications and preconditions;
- normal, abnormal, and emergency branches;
- go/no-go decision points;
- independent cross-checks and redundancy;
- stop conditions and escalation;
- recorded outcome and post-incident review.

Use that structure in benchmark schemas. Do not turn the operation itself into an
execution target.

### Digital and artifact domains — executable candidates

| Domain | Sources | Eligibility |
|---|---|---|
| Software and CLI | [GitHub Docs](https://docs.github.com), [Microsoft Learn](https://learn.microsoft.com), [AWS Docs](https://docs.aws.amazon.com), [Google Cloud Docs](https://cloud.google.com/docs), [Kubernetes Docs](https://kubernetes.io/docs), [PostgreSQL Docs](https://www.postgresql.org/docs) | `execute` in sandbox |
| Web standards | [IETF RFCs](https://www.ietf.org/standards/rfcs/), [W3C](https://www.w3.org/TR/), [MDN](https://developer.mozilla.org), [OWASP](https://owasp.org) | `answer`, `draft`, `execute` |
| Security and operations | [NIST SP 800](https://csrc.nist.gov/publications), [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks), [Google SRE](https://sre.google/books/) | `answer`, `draft`, `execute` in isolated environments |
| Payments and commerce | [Stripe Docs](https://docs.stripe.com), [Shopify Docs](https://shopify.dev/docs), [Adyen Docs](https://docs.adyen.com) | `answer`, `draft`, `execute` in test mode |
| SaaS administration | Google Workspace Admin Help, Microsoft 365 Admin, Atlassian, Slack, Notion, Salesforce | `answer`, `draft`, `execute` in test tenant |
| SEO and content | [Google Search Central](https://developers.google.com/search/docs), [Bing Webmaster](https://www.bing.com/webmasters/help), [schema.org](https://schema.org) | `answer`, `draft`, `execute` on test site |
| Accessibility and design | [WCAG](https://www.w3.org/WAI/standards-guidelines/wcag/), [Apple HIG](https://developer.apple.com/design/human-interface-guidelines/), [Material](https://m3.material.io) | `answer`, `draft`, `execute` on test UI |
| Documentation method | [Diátaxis](https://diataxis.fr), [Google Technical Writing](https://developers.google.com/tech-writing) | `answer`, `draft`, `execute` on docs |
| CLI-first reference | `man` pages, [tldr](https://tldr.sh), [DevDocs](https://devdocs.io), official CLI references | `answer`, `draft`, `execute` |

## 4. Official manuals and handbooks

| Source | Why it matters |
|---|---|
| [FAA Airplane Flying Handbook](https://www.faa.gov/regulations_policies/handbooks_manuals/aviation) | Official training structure, checklists, decision points |
| [FAA Pilot's Handbook of Aeronautical Knowledge](https://www.faa.gov/regulations_policies/handbooks_manuals/aviation) | Reference knowledge and procedure context |
| [NASA Technical Reports Server](https://ntrs.nasa.gov/) | Primary engineering reports, procedures, failure analyses |
| [NIST publications](https://csrc.nist.gov/publications) | Security, measurement, and process standards |
| [National Park Service Museum Handbook](https://www.nps.gov/museum/publications/handbook.html) | Official museum registration, handling, and care procedures |
| [Smithsonian Institution Archives and Libraries](https://www.si.edu/) | Primary collections and institutional practice |
| [Library of Congress](https://www.loc.gov/) | Primary documents, public-domain manuals, maps, archives |
| [National Archives](https://www.archives.gov/) | Government records and historical procedure sources |
| [Internet Archive](https://archive.org/) | Scanned manuals, out-of-print books, historical media |
| [HathiTrust](https://www.hathitrust.org/) | Large digitized book corpus |
| [Europeana](https://www.europeana.eu/) | European museum, archive, and library collections |

### Restricted or proprietary manuals

Flight crew operating manuals, train operator manuals, manufacturer service
manuals, and some military manuals are often restricted. Record metadata,
edition, and citation only. Do not scrape or republish restricted content.

## 5. Books and canonical references

Books are often the best source for **methodology**, not step-by-step current
software operations.

### Procedure, safety, and error

| Book | Use |
|---|---|
| *The Checklist Manifesto* — Atul Gawande | Checklist design, preconditions, stop conditions |
| *Human Error* — James Reason | Error taxonomy, latent failures, defence in depth |
| *Normal Accidents* — Charles Perrow | Complexity, coupling, and why procedure alone is insufficient |
| *The Design of Everyday Things* — Don Norman | Affordances, feedback, error prevention |
| *Thinking in Systems* — Donella Meadows | System boundaries, feedback, unintended consequences |
| *The Toyota Way* — Jeffrey Liker | Standard work, kaizen, and problem solving |
| *The Fifth Discipline* — Peter Senge | Learning organizations and mental models |
| *Sources of Power* — Gary Klein | Naturalistic decision making and recognition-primed decisions |
| *Drift into Failure* — Sidney Dekker | Safety drift and procedural degradation |

### Software, operations, and documentation

| Book | Use |
|---|---|
| *Site Reliability Engineering* — Google | SLOs, incident response, runbooks, postmortems |
| *The Phoenix Project* — Kim, Behr, Spafford | Delivery flow and operations constraints |
| *Accelerate* — Forsgren, Humble, Kim | Delivery metrics and evidence-based improvement |
| *Continuous Delivery* — Humble and Farley | Repeatable build, test, and release procedures |
| *Designing Data-Intensive Applications* — Martin Kleppmann | Data-system tradeoffs and failure modes |
| *Refactoring* — Martin Fowler | Behavior-preserving transformation |
| *Working Effectively with Legacy Code* — Michael Feathers | Safe change in constrained systems |
| *The Pragmatic Programmer* — Hunt and Thomas | Engineering heuristics and tradeoffs |
| *Docs for Developers* — Bhatti et al. | Documentation workflows and review |
| *Every Page Is Page One* — Mark Baker | Topic-based, reusable documentation |

### Craft, repair, and field reference

| Book | Use |
|---|---|
| *Machinery's Handbook* | Authoritative mechanical reference |
| *Foxfire* series | Experiential craft and folk procedure |
| *Where There Is No Doctor* — Hesperian | Field medicine for non-specialists; review-only |
| *The Knowledge* — Lewis Dartnell | Rebuilding technology and basic processes |
| *Reader's Digest Complete Do-It-Yourself Manual* | Home repair procedures |
| *Haynes* manuals | Vehicle repair procedures |
| *The Whole Earth Catalog* | Historical catalogue of tools, books, and methods |
| *The Art of Travel* — Alain de Botton | Travel reflection, not operational guidance |
| *Lonely Planet* guides | Travel logistics and cultural context |

### Museum, conservation, and heritage practice

| Book | Use |
|---|---|
| *Museum Registration Methods* — Dudley, Wilkinson, et al. | Registration, documentation, and collections care |
| *The Manual of Museum Planning* — Lord, Lord, and Martin | Museum planning and operations |
| *The Manual of Museum Exhibitions* — Lord and Lord | Exhibition development and installation |
| *Preventive Conservation* — various conservation handbooks | Environmental control, handling, storage |
| *The Museum Handbook* — National Park Service | Official U.S. museum procedure reference |
| *AIC* conservation guidance | [American Institute for Conservation](https://www.culturalheritage.org/) |
| *CCI Notes* | [Canadian Conservation Institute](https://www.canada.ca/en/conservation-institute/services/conservation-preservation-publications/canadian-conservation-institute-notes.html) |
| *NEDCC* preservation leaflets | [Northeast Document Conservation Center](https://www.nedcc.org/) |

Museum-level sources are strong candidates for **draft** and **answer**
benchmarks: condition reports, handling procedures, exhibition checklists,
registration metadata, emergency response, and preventive conservation.

## 6. Experience-based reusable knowledge

### RedNote / Xiaohongshu

RedNote is a source of **experiential procedures**: trip planning, app
operation, cooking, study methods, repairs, and personal workflows. It is not an
official policy source.

| Local working mirror | Role |
|---|---|
| `public_skills/others/browser-act--skills/solutions/social-listening/xiaohongshu-search/` | Search notes |
| `.../xiaohongshu-search-full/` | Search and feed extraction |
| `.../xiaohongshu-note-detail/` | Note detail and comments |
| `.../xiaohongshu-user-profile/` | Author profile |
| `public_skills/others/larksuite--cli/skills/lark-doc/references/genres/xiaohongshu.md` | Style contract; explicitly not platform policy |

Official constraints:

- [小红书规则中心](https://school.xiaohongshu.com/rule/detail/109/2566)
- [蒲公英帮助中心](https://pgy.xiaohongshu.com/help/list?id=28&userType=1)
- [小红书开放平台](https://open.xiaohongshu.com/)

Reuse evidence to record:

- saves and save-to-like ratio;
- comments asking for steps, reporting success, or reporting failure;
- independent posts describing the same procedure;
- author history, credentials, and sponsorship disclosure;
- recency and app/version applicability;
- cross-platform reuse;
- successful execution by a second person.

Third-party RedNote skills:

- [DeliciousBuding/xiaohongshu-skill](https://github.com/DeliciousBuding/xiaohongshu-skill)
- [luffy666code/xiaohongshu-skills](https://github.com/luffy666code/xiaohongshu-skills)

These are implementation references, not policy truth.

### Other experience and general-guide platforms

| Source | Use | Weakness |
|---|---|---|
| [wikiHow](https://www.wikihow.com) | Broad step-based procedures | Variable quality, SEO incentives |
| [Instructables](https://www.instructables.com) | Project and craft procedures | Amateur, safety gaps |
| [iFixit](https://www.ifixit.com/Guide) | Repair procedures | Narrow domain |
| [Wikivoyage](https://en.wikivoyage.org) | Travel procedures | Can be stale |
| [Stack Overflow](https://stackoverflow.com) | Software failure modes | Anecdotal, version drift |
| Reddit and Stack Exchange | Edge cases and real failures | Conflicting, unsigned |
| Medium, Substack, dev.to | Worked examples and playbooks | Paywalls, content marketing |
| YouTube and Bilibili | Demonstration | Hard to cite, version drift |
| [Google Search Central](https://developers.google.com/search/docs) | SEO rules | Official for search, not content strategy |

## 7. Local expert and playbook corpus

The workspace has a large local mirror under `public_skills/` (outside this
public repository). It is useful for candidate discovery, but it is not a
verified label set.

High-value subtrees:

- `public_skills/anthropic_official/` — official Anthropic skills and spec.
- `public_skills/openai_official/skills/` — official OpenAI skills.
- `public_skills/platforms/microsoft--azure-skills/` — Microsoft-authored.
- `public_skills/platforms/vercel-labs--skills/` — Vercel-authored.
- `public_skills/platforms/remotion-dev--skills/` — Remotion-authored.
- `public_skills/others/NVIDIA--skills/` — NVIDIA-authored domain skills.
- `public_skills/others/lawve-ai--awesome-legal-skills/` — named legal experts.
- `public_skills/others/deanpeters--Product-Manager-Skills/` — named product expert.
- `public_skills/others/BrianRWagner--ai-marketing-claude-code-skills/` — named marketing expert.
- `public_skills/others/Bomx--distribb-skill/references/` — SEO and distribution playbooks.
- `public_skills/others/openaccountants--openaccountants/` — accounting runbooks.
- `public_skills/others/AgriciDaniel--claude-seo/` — SEO implementation.
- `public_skills/others/kgraph57--mckinsey-style-visualization-skill/` — consulting visualization.

## 8. Validation benchmarks

Use these to test execution and outcomes, not to define content truth:

- WebArena
- OSWorld
- Mind2Web
- WebVoyager
- GAIA
- SWE-bench
- WorkArena / BrowserGym

## 9. Source registry schema

Record every source with:

```text
source_id
title
author or publisher
source_type: law | standard | manual | book | museum_record | experience_post | blog | skill | benchmark
URL or local path
publication date and revision
license and access restrictions
domain
agent_eligibility: answer | draft | execute | refuse
verification_method: citation | checklist_review | sandbox_execution | expert_review
reuse_evidence
safety_class
privacy_class
trust_tier
reviewer_roles
```

## 10. Labeling protocol

1. Select a task family with a real user need.
2. Collect at least three candidate sources across different tiers.
3. Extract a normalized procedure:

```text
task
preconditions and required access
tools and versions
ordered steps
decision points
expected observations
failure modes and recovery
verification / success check
provenance and date
reuse evidence
```

4. Cross-check against an authoritative source.
5. Require a domain expert and a user advocate to review independently.
6. Execute the procedure in a sandbox when eligible.
7. Mark `draft`, `silver`, `gold`, or `rejected`.
8. Keep calibration and held-out sources separate.
9. Record disagreements and the adjudication rationale.

## 11. Access, licensing, and safety

- Do not republish paywalled, copyrighted, or restricted manuals.
- Store citations, metadata, hashes, and original summaries; avoid copying long
  passages.
- Do not scrape RedNote or other platforms against their terms; use official
  APIs or consented exports.
- Redact personal data, account identifiers, and private traces.
- Exclude tasks requiring physical operation, licensed practice, or
  irreversible real-world effects from `execute` benchmarks.
- Treat high-stakes advice as `answer` or `draft`, never as autonomous action.

## 12. Recommended first domains

1. **Software/CLI operations** — official docs, sandbox execution, measurable.
2. **SaaS administration** — test tenants, reversible changes.
3. **SEO/content workflow** — official search docs plus test-site execution.
4. **Museum/heritage procedures** — registration, condition reporting,
   handling, preservation; `draft` and `answer` cases.
5. **Travel planning** — RedNote plus Wikivoyage/official tourism sources;
   produce an itinerary, not bookings or payments.
6. **App operation** — RedNote plus official app help; sandbox/emulator where
   possible.
7. **Aviation/rail** — retrieval, checklist drafting, and refusal cases only.

The order reflects agent eligibility and verification strength, not source
prestige.
