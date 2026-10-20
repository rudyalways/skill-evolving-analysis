---
id: N2026-10-05-002
title: What ad vertical trees imply for the skill label trees
date: 2026-10-05
tags: [taxonomy, skill-labels]
status: processed
source: raw_materials/ad-verticals/
related: ["notes/synthesis/skill-label-system.md"]
summary: Google, IAB, Meta, and TikTok keep one question per tree, cap semantic depth, and leave large nodes large.
---

# What ad vertical trees imply for the skill label trees

> Written 2026-10-05. Files are in [`raw_materials/ad-verticals/`](../../raw_materials/ad-verticals/SOURCES.md). Counts below are from those files.

The skill label file cuts every branch until a leaf holds at most 100 skills. That produces `names-0` blocks and hangs domain and clone off Job. None of the ad systems do that. They keep a node large, and they keep each question in its own tree.

## How each system cuts the tree

Google Ads does not have one vertical tree. It has several, and a campaign picks which question it is asking.

| Tree | Question | Nodes | Roots | Depth where the mass sits | Deepest |
|---|---|---:|---:|---|---:|
| Affinity | What is this person into, as a habit | 258 | 15 | 2–3 | 4 |
| In-market | What are they about to buy | 954 | 26 | 2–5 | 7 |
| Life events | What milestone are they in | 40 | 11 | 1–2 | 3 |
| Detailed demographics | What long-term fact is true of them | 25 | 5 | 2–3 | 3 |
| Content topics (`verticals.csv`) | What is this page or video about | 2,558 | 26 | 3 | 8 |
| Products and services | What thing or service is for sale | 3,180 | 22 | 3–4 | 7 |
| Merchant product taxonomy | Same question, for a product feed | 5,595 | 22 | 3–5 | 7 |

A node is `id`, `parent id`, and a path. The path is the display of the parent links. Channel availability (Search, Display, Video, …) is a column of YES/NO on the help-page CSVs, not another slash in the path. The help-page affinity CSV has 154 rows. The API affinity CSV has 258. Same name, two snapshots. The API file is the one to treat as current.

The deep nodes are closed lists, not finer concepts. In-market depth 7 is “trips to a US state” (55 children) and “cars by brand” (48 children). Content topics go to depth 8 in the same kind of list. A concept node stops at 2 or 3.

Every large parent that is not a closed list stays large. Affinity’s biggest semantic parent is Sports Fans, with 21 children, and it stops. There is no rule that a category must be split because many people are in it.

Residual is a named sibling. The help page documents `Affinity Audiences > Other Interests` and `In-Market Audiences > Other In-Market` as the bucket Google fills when a user matches the parent and none of the children. Health is listed in the tree and then barred from use by a policy sentence, not by a deeper label.

IAB splits the same way, and then says so in the file format.

- Content Taxonomy 3.1 is “what is this about”: 673 nodes, 62 roots, tiers 1–4, most nodes at tier 2.
- Descriptive vectors are other questions, each its own short tree: Content Environment (8), Content Purpose (4), Content Source (3), Content Form Factor (7), Brand Suitability and Risk (4), plus language and geo extensions. A page gets one aboutness path and several vector values.
- Ad Product Taxonomy 2.0 is “what is being advertised”, a different tree (583 nodes, max tier 3). IAB’s own release note says they cut it from 5 tiers to 3 and deleted a large number of rows. Depth was the thing they removed.

Meta’s detailed targeting is the same pattern under different names: `interests`, `behaviors`, `life_events`, `industries`, and the demographic classes are separate catalogues. Each node has an id, a parent, a path, and an audience-size range. Size is stored. It is not a reason to add a child. The long tail is a search box (keywords, employers, schools), which Google calls a custom segment. Special Ad Categories are four policy flags on the campaign — housing, employment, financial products and services, politics. Turning one on disables targeting options. It does not add a level under Finance.

TikTok’s ads industry list is the strict version of the same idea. Twenty-one parents, 237 children, and then it stops. Nineteen parents include an `Other …` child (`Other Apparel & Accessories`, and the same for the rest). Creating an ad account requires the child id, not the parent. The id itself encodes the level (`22000000000` vs `22102000000`). Shop product categories are a second, deeper tree, and they are not mixed into the industry list.

## What is worth borrowing

The eight facets already match the IAB split: Job, Domain, Form, Artifact, Binding, Audience, Language, and Provenance are vectors. The part that does not match is the path inside a facet.

1. A facet path should stop at a named concept. Job stops at `job / methodology / plan` or `job / methodology / rest`. Domain stops at `domain / software / python` or `domain / software / rest`. Provenance is already its own facet, so the clone does not belong under Job. `names-4` is a sort bucket. Ad trees do not have one.

2. A node may hold more than 100 skills. Affinity, in-market, and the Merchant taxonomy all have parents with thousands of implied members and a few dozen children. The count is a column. The next child is added when someone can name it, the way Google named Running Apparel under Activewear, not when a counter crosses 100.

3. `rest` should behave like TikTok’s `Other` and Google’s `Other In-Market`: a permanent sibling, reported with its count, left in place. A `rest` of 5,945 methodology skills means the child list is incomplete (plan, workflow, debug, tdd, brainstorm do not cover the parent). It does not mean those 5,945 need a name-range.

4. Identity is an id plus a parent id. The path is rebuilt from the parent pointers, which is how every file in `raw_materials/ad-verticals/` is shaped. Renaming Sports Fans does not move the id. The skill leaf file uses the path as the id, so a rename is a new label.

5. Semantic depth stays at 3, which is where IAB landed after cutting Ad Product from 5 to 3, and where Google affinity actually lives. Depth beyond that is reserved for a closed enumeration that is already its own facet: language codes, a product binding, a clone name. US states and car brands are that kind of list. Alphabetical blocks of skill titles are not.

6. Policy problems stay beside the tree. Meta’s special-ad flag and Google’s health rule do not subdivide the category. The discovery count of 1,203 is that kind of problem: a bad assignment, recorded as a quality flag, not as `discovery / rest / ai / <clone> / names-N`.

7. One canonical file per tree, dated. The help page and the API already disagree by about 100 affinity rows. The skill note and the leaf file need the same rule: the jsonl is the snapshot, and a later recount does not silently grow a second tree.

The 100-skill leaf file can stay as an index for browsing a huge clone. It is not the vertical. The vertical is the shallow, id-backed, one-question tree, with `rest` left visible where a real child has not been named yet.

## Can the ads verticals be the label system?

They can be one slice of one facet. They cannot replace the eight facets, and they cannot replace Domain as it stands.

IAB already separated the questions. Content Taxonomy is aboutness. Descriptive vectors are purpose, form, source, language, and risk. Ad Product is a second aboutness tree for what is sold. That is the same split as Job versus Domain versus Form versus Language versus Provenance. Loading Google’s in-market tree into Job, or into all eight facets, would glue those questions back together.

The only facet with the same question as an ads vertical is Domain: what the work is about. Google content topics and IAB Content 3.1 are the lists that match. Affinity is a person. In-market and the Merchant taxonomy are a product someone might buy. Binding is the nearer cousin of those product trees, and it still does not fit: Binding here is Azure, Notion, Figma, Shopify. The Merchant tree’s deep nodes are dresses, vegetables, and drill bits.

Domain still should not be swapped for those lists. The ads trees do name software. Google content topics have `/Computers & Electronics/Programming` (C & C++, Java, Scripting Languages, Development Tools, Windows & .NET), `/Computers & Electronics/Software`, and `/Computers & Electronics/Computer Security` (Antivirus & Malware, Network Security). IAB Content 3.1 has Artificial Intelligence as one node, Programming Languages as one node, plus Databases, Cloud Computing, and Information and Network Security. The failure is the grain, and the unit being classified.

On the greedy cover, software, ai, security, unspecified, data, and design reach 89.1% of the 19,716 skills before finance, the first label that is also a normal ads vertical. Under an ads tree those skills land on a handful of nodes: one AI node for 7,890 skills, Scripting Languages for Python and TypeScript together, Antivirus for the security work. Testing, git, frontend, backend, and every Job have no node. The same files then go deep where this corpus is empty: in-market depth 7 is US states and car brands, and the Merchant tree’s largest parents are tools, kitchen utensils, and vegetables. Commerce, as its own domain, newly reaches 3 skills.

What can be reused:

- The shape: id, parent, path as display, depth capped near 3, `rest` as a permanent sibling, size as a column.
- A crosswalk, not a replacement. Tier 1 and tier 2 of Google content topics, or of IAB Content 3.1, can be a second column on the commercial domains that already exist: finance, legal, marketing, media, education, games, life-science, commerce. A skill keeps `domain/finance` and gains something like `iab:52` (Business and Finance). The engineering domains stay, because no ads vertical names them.
- A ninth facet that is “ads vertical” would ask Domain’s question a second time. Skip it.

The reusable artifact is a map from the current domain id to the nearest IAB or Google topic id, for the domains those trees actually name. The engineering spine stays a tree those files do not contain.
