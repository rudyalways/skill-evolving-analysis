---
name: batch-doc-variant-publishing
description: Publish several localized or copied document variants from local XML drafts by validating every draft, normalizing the XML root, creating documents one at a time with a short yield, polling each session, and fetching each token to confirm the title. Use when a request asks for multiple language versions or multiple copies of a document in one batch.
---

## Overview

Own batch publishing from prepared XML drafts to verified documents. The value of
this skill is the order of operations and the evidence it produces: validate all
drafts before creating any, reduce every draft to the single root element the
create command accepts, create one document per draft in sequence, poll each
create session to completion, and fetch every returned token to confirm its
title. It does not author document content, translate text, or judge translation
quality.

## When to Use

Use this skill when any one of these conditions holds; a first request is
enough, and a later restatement of the same batch request is also enough on its
own:

- The user asks for several language versions of a document.
- The user asks for multiple copies of one document in a single batch.
- The user supplies more than one local XML draft and asks to publish them.
- The user asks how to publish or batch-publish a set of prepared XML drafts.
- A previous turn requested the batch and a later turn restates or resumes it.

## Do Not Use

Do not use for creating or editing a single document. Do not use for non-XML
formats, for documents that already exist and only need edits, or when no local
draft is available. Do not use it to decide content, wording, or translation
quality, and do not use it for sharing or permission changes.

## Workflow

1. Enumerate every draft in a stable order and record its path. Do not start
   creating before the whole set is known.
2. Validate every draft with the document CLI parse command, for example
   `docs parse <draft>`. Stop at the first failed draft, report that draft and
   its parse error, and create nothing. Re-validate a draft after fixing it.
3. Compare the top-level root element of every draft. The create command accepts
   one root shape. If one draft wraps the expected root in an extra outer
   element, remove only that wrapper while preserving its children, then re-run
   the parse command on that draft. Never send a mixed-root batch to create.
4. Create one document per draft, in sequence and never in parallel, with a
   short yield such as `--yield 1s`, for example `docs create <draft> --yield 1s`.
   The short yield must return a session identifier; do not redirect its stdout
   to a file. If the batch is long, use the short yield and continue polling
   rather than asking one call to block.
5. Poll the returned session with the CLI session-status command until its
   `exit_code` is `0`. Keep polling while it is still running. On completion,
   capture `ok`, `token`, and the document URL. If `ok` is false, stop and report
   the session error instead of creating a replacement.
6. Fetch each created token with the document fetch command, for example
   `docs fetch <token>`, and read the returned title. Compare it with the draft
   title or the title the user requested. A variant is not published until its
   own fetch succeeds and its title matches.

## Constraints

- Validate every draft before the first create. A parse failure blocks the whole
  batch rather than only that draft.
- Never mix draft root shapes in one batch. Normalize the odd draft and
  re-validate it before creating.
- Do not run creates in parallel, and do not interleave a new create before the
  previous session has reached a terminal state.
- Never append a shell redirect and a long yield to a long-running create. An
  empty result can leave a zero-byte output file and lose the document URL.
  Use a short yield and poll the returned session instead.
- If a create prints nothing, check whether a session was started before
  rerunning; poll an existing session rather than creating a duplicate.
- Do not report success from a command's exit code alone while a session is
  still running, and do not count a variant as done before its token is fetched.

## Verification

Produce one evidence row per variant containing the draft path, `ok: true`, the
created token, the URL, the fetched title, and whether it matches the draft
title. Confirm that the number of verified documents equals the number of
drafts, and that no token or title is duplicated across variants. Note any draft
that required root normalization. A batch with any unverified, duplicated, or
title-mismatched variant is incomplete.

## Output Format

Report one line per variant in draft order:

```text
<draft path> -> token=<token> | <URL> | title="<fetched title>" | verified
```

After the lines, report `<verified count> of <draft count> documents verified`.
Call out any draft that needed root normalization and any failed draft or
session with its error. Do not present partial output as a successful batch.

## Limitations

Covers only the document CLI's XML-draft path and its create-session behavior as
observed. Other input formats, permissions, sharing, and content review are out
of scope. Long documents may need repeated polling before the create session
completes, and the skill depends on the CLI's parse, create, session-status, and
fetch commands being available.
