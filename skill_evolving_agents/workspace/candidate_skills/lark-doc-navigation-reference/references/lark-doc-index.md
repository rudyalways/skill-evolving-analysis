# lark-doc navigational index

A durable index for the live lark-doc skill documentation. It records where knowledge lives, which heading and line range governs a topic, and whether the source is still fresh. It never copies the knowledge itself.

## Contents

- [Read trigger](#read-trigger)
- [Source locators](#source-locators)
- [File map](#file-map)
- [Digest ledger](#digest-ledger)
- [Topic-to-heading map](#topic-to-heading-map)
- [Freshness and refresh rule](#freshness-and-refresh-rule)
- [Consult protocol](#consult-protocol)

## Read trigger

Open this file immediately before a lark-doc-dependent workflow that would otherwise reopen the full lark-doc `SKILL.md` or several reference files. This includes Feishu/Lark docx or wiki reading, creation, editing, media handling, history, whiteboard, mindnote, and XML/Markdown authoring tasks, and any step that needs an exact command, flag, scope, or reference-file choice.

A first lark-doc request and a later restatement of the same request each trigger this lookup on their own; no prior turn or restatement is required.

Do not open it for unrelated documentation or for an answer already present in the conversation, and never use it as a replacement for the authoritative section when exact wording governs.

## Source locators

Resolve the live lark-doc skill root in this order, then use paths relative to it:

1. `$LARK_DOC_SKILL_DIR`
2. The normal skill loader or host-provided skill root containing `lark-doc/SKILL.md`
3. `~/.agents/skills/lark-doc`

| Source | Relative path |
| --- | --- |
| Main skill document | `SKILL.md` |
| Reference directory | `references/` |
| Genre contracts | `references/genres/` |
| Alternate documentation layout | `doc/skill.md` and the `doc/` tree |

If the resolved root exposes the same material as `doc/skill.md` and a `doc/` tree instead of top-level `SKILL.md` and `references/`, treat `doc/skill.md` as the entry source and `doc/` as the documentation tree. Rebase every recorded relative path onto the layout actually found before hashing, and record the rebased paths during the refresh.

The recorded digests were captured from the third locator on 2026-11-02. They are baselines, not proof that the path exists here. Recompute before use.

## File map

One row per recorded source file. Read only the file selected by the task; never preload the tree.

| Source file (relative to the resolved root) | Topic label | Read when |
| --- | --- | --- |
| `SKILL.md` | Entry and shortcut routing, scope boundaries | First lookup, topic routing, or when no reference row matches the request. |
| `references/lark-doc-fetch.md` | Read, summarize, scope, and embedded resources | The task reads or inspects an existing document. |
| `references/lark-doc-create-workflow.md` | Authoring from scratch and genre selection | The task creates a new document or chooses a genre contract. |
| `references/lark-doc-create.md` | Empty-document creation and import | The task creates a document or imports existing content. |
| `references/lark-doc-update.md` | Editing, polishing, reorganizing, layout | The task modifies existing document content. |
| `references/lark-doc-script.md` | Draft initialization, URL/token parsing, character counts | The task needs script helpers before an operation. |
| `references/lark-doc-history.md` | History listing, revert, revert status | The task inspects or restores document history. |
| `references/lark-doc-media-insert.md` | Image or file insertion at document end | The task inserts media or a file into a document. |
| `references/lark-doc-media-preview.md` | Media preview | The task previews document media. |
| `references/lark-doc-media-download.md` | Media and whiteboard-thumbnail download | The task downloads document media. |
| `references/lark-doc-resource-cover.md` | Docx cover download, update, delete | The task manages a document cover image. |
| `references/lark-doc-whiteboard.md` | Whiteboard creation and editing | The task creates or edits a document whiteboard. |
| `references/lark-doc-mindnote.md` | Mindnote reading, ids, commands, workflow | The task works with an existing mindnote. |
| `references/lark-doc-xml.md` | Feishu XML tags, tables, colors, escaping | The task authors or edits Feishu XML. |
| `references/lark-doc-xml-extended-blocks.md` | Extended XML blocks, HTML5, OKR | The task needs an extended XML block. |
| `references/lark-doc-md.md` | Markdown escaping, shell quoting, image syntax | The task authors or escapes Markdown. |
| `references/genres/` | Genre content contracts, selected on demand | The create workflow asks for a specific genre contract. |

## Digest ledger

Compare every row with a freshly computed sha256. A row is current only when its file exists at the resolved root and the digest matches. Recompute `SKILL.md` and every recorded reference file, not just the one being routed.

| Source | sha256 |
| --- | --- |
| `SKILL.md` | `0f1aea17fc21aaeb1cc17270d6de7de97780c3a9f53f98f668ce318f91f1a1f7` |
| `references/lark-doc-fetch.md` | `0200e8231902b7c532bcec036ab83fb5b6f928f689ed16c0c906217613c92df6` |
| `references/lark-doc-create-workflow.md` | `f664472c088ac09d8b4b69aa3a49f35c395f1892078b637d7c7812cbc8f9fcaa` |
| `references/lark-doc-create.md` | `4add00b26e81207515ba4e3319e690a6143f604dea72444d97d49931191107bb` |
| `references/lark-doc-update.md` | `1325ceac3355401486cf46a7462cf083b4dada00e7c07e03c1084cea2c7f7c6d` |
| `references/lark-doc-script.md` | `7fb8a1d3031e49ef076b0f3a705b8f6527d2cd31f4797a29f4fb6adc7c29aaeb` |
| `references/lark-doc-history.md` | `a67b4beaacef43626088f92de297fb37021cd1daf829763bbbcb419714854850` |
| `references/lark-doc-media-insert.md` | `715c0ffefbca373c2554f3e60ca907b0a28166469f9eecd124418faac9c1ddae` |
| `references/lark-doc-media-preview.md` | `68eff43a4a1f1fcba852a80332b521ba2ce5041f051fba2d6ec25c246886e919` |
| `references/lark-doc-media-download.md` | `246ef6cfdbd607683792f806e843189170ecbd94e5cfc8acd02cbe43030d5c33` |
| `references/lark-doc-resource-cover.md` | `3d453cc82978d7a4f8d8fad08e80783c209cf7ff7b1bbf3cb56c23f51aa4e457` |
| `references/lark-doc-whiteboard.md` | `86dd68d27a50914c10af97abc040934ddee38521fb555a1d019ad9b4bb0286ff` |
| `references/lark-doc-mindnote.md` | `a239f58aa9d832623d79943a8f8268783da3c07bce1816060e2f01b0d1278e92` |
| `references/lark-doc-xml.md` | `111e58ffcd10f0d333bb02c2c9b97c8c3cec4f20b5fbd0cf5c30132880ced4a5` |
| `references/lark-doc-xml-extended-blocks.md` | `893faaf0a757cd43b9b2031b695982191e56c6469af1a47e1e90b5c1fd342110` |
| `references/lark-doc-md.md` | `74d062a4ac6d436141f4a90f87cbecd45d9f6d8b0d34f3e04077653175dc2e36` |

## Topic-to-heading map

Line numbers are heading starts. Read from the recorded heading to the next heading at the same or higher level. If the digest changed, re-extract headings before trusting any line number.

| Topic | Source | Heading | Line |
| --- | --- | --- | --- |
| Route a request to the right lark-doc shortcut | `SKILL.md` | `## 场景与 Shortcut 路由` | 13 |
| Read, summarize, or locally scope a document | `references/lark-doc-fetch.md` | `# docs +fetch（读取飞书云文档）` | 1 |
| Fetch parameters and detail or scope flags | `references/lark-doc-fetch.md` | `## 参数` | 22 |
| Fetch detail levels | `references/lark-doc-fetch.md` | `## 选择详细度：--detail` | 38 |
| Fetch read scopes | `references/lark-doc-fetch.md` | `## 选择读取范围：--scope` | 48 |
| Fetch return shape | `references/lark-doc-fetch.md` | `## 返回值` | 76 |
| Embedded resources encountered while reading | `references/lark-doc-fetch.md` | `## 处理文档内嵌资源` | 123 |
| Author a document from scratch | `references/lark-doc-create-workflow.md` | `# Lark Doc Authoring` | 1 |
| Creation step plan | `references/lark-doc-create-workflow.md` | `## Step Plan` | 17 |
| Choose a genre contract while authoring | `references/lark-doc-create-workflow.md` | `### Step 2：选择 genre content contract` | 23 |
| Create an empty document or import existing content | `references/lark-doc-create.md` | `# docs +create（创建飞书云文档）` | 1 |
| Create command and parameters | `references/lark-doc-create.md` | `## 参数` | 41 |
| Edit, polish, reorganize, or re-layout content | `references/lark-doc-update.md` | `# docs +update（更新飞书云文档）` | 1 |
| Recommended update flow | `references/lark-doc-update.md` | `## 推荐流程` | 27 |
| Update parameters and instruction cheat sheet | `references/lark-doc-update.md` | `## 指令速查` | 63 |
| Update safety rules | `references/lark-doc-update.md` | `## 通用安全规则` | 76 |
| Initialize a draft, parse a URL or token, count characters | `references/lark-doc-script.md` | ``# `docs +script` `` | 1 |
| Draft initialization script | `references/lark-doc-script.md` | `## init-draft` | 12 |
| Parse script | `references/lark-doc-script.md` | `## parse` | 37 |
| List history, revert, or check revert status | `references/lark-doc-history.md` | `# docs history（历史版本与回滚）` | 1 |
| History safety constraints | `references/lark-doc-history.md` | `## 安全约束` | 7 |
| Insert an image or file at document end | `references/lark-doc-media-insert.md` | `# docs +media-insert（文档末尾插入图片/文件）` | 2 |
| Media insert source selection | `references/lark-doc-media-insert.md` | `## 来源选择（Agent 必读）` | 8 |
| Preview document media | `references/lark-doc-media-preview.md` | `# docs +media-preview（预览文档素材）` | 2 |
| Download document media or whiteboard thumbnails | `references/lark-doc-media-download.md` | `# docs +media-download（下载文档素材/画板缩略图）` | 2 |
| Download, update, or delete a Docx cover | `references/lark-doc-resource-cover.md` | `# docs +resource-*（Docx 封面图资源）` | 1 |
| Create or update a whiteboard in a document | `references/lark-doc-whiteboard.md` | `# lark-doc 画板处理指南` | 1 |
| Whiteboard responsibility boundary | `references/lark-doc-whiteboard.md` | `## 两个 Skill 的职责边界` | 3 |
| Edit an existing whiteboard | `references/lark-doc-whiteboard.md` | `### 步骤 3B：编辑已有画板 — 启动 lark-whiteboard SubAgent` | 130 |
| Work with an existing mindnote | `references/lark-doc-mindnote.md` | `# 飞书思维笔记（Mindnote）` | 1 |
| Resolve a mindnote id | `references/lark-doc-mindnote.md` | ``## 获取 `mindnote_id` `` | 12 |
| Mindnote commands and parameters | `references/lark-doc-mindnote.md` | `## 命令` | 26 |
| Mindnote recommended workflow | `references/lark-doc-mindnote.md` | `## 推荐工作流` | 109 |
| Feishu XML tags, tables, colors, escaping | `references/lark-doc-xml.md` | `# 飞书 XML 语法` | 1 |
| Extended XML blocks, HTML5, OKR | `references/lark-doc-xml-extended-blocks.md` | `# XML 扩展块补充说明` | 1 |
| Markdown escaping, shell quoting, image syntax | `references/lark-doc-md.md` | `# Markdown 格式参考` | 1 |
| Confirm what lark-doc does not own | `SKILL.md` | `## 不在本 Skill 范围` | 46 |

## Freshness and refresh rule

Run a freshness pass at the start of every consult.

1. Resolve the live root using the locator order above. If no root is found, mark every digest `unavailable`; do not route from this index.
2. For every digest row, compute sha256 for the resolved file. Use `shasum -a 256` or `sha256sum`. Require 64 hexadecimal characters.
3. If all files exist and all digests match, report `matched` and use the maps.
4. If any file is missing or differs, if a digest is unrecorded, or if the topic is not mapped, report `refreshed` and rebuild before lookup. Enumerate the documentation tree with `find "$LARK_DOC_ROOT" -type f -name '*.md' | sort`, then list headings with `grep -nE '^#{1,6} '`.
5. For each affected file, update only the file rows, heading routes, line ranges, and digests that the real enumeration and heading listing support. Add a file or route only when the live path or heading exists; remove or rewrite rows whose source or heading is gone.
6. Replace each old digest with the newly computed value in the same pass; never write a digest that was not computed from the resolved file. If a source cannot be read, record its digest as `unavailable` rather than guessing, and do not use its stale routes as current guidance.
7. Record the refresh date and the refreshed field list, keeping the index free of body text and excerpts.

## Consult protocol

1. Report the freshness result before using the map.
2. Select exactly one file whose topic and read-when condition match; when several match, choose the narrowest.
3. Cite the governing heading, source file, and line range read.
4. Read only the mapped range; do not dump the full lark-doc source or unrelated references.
5. If the mapped range does not answer the need, run the refresh rule before widening the read.
6. Leave the live lark-doc files untouched; only this index may be updated.
