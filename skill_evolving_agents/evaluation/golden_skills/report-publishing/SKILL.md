---
name: report-publishing
description: Turn a research brief into a published CMS report page with a concise title, required sections, source link, cover image, and correct metadata.
---

# Report publishing

## When to use

Use when a user asks for a report to be published on a website or CMS, the report
needs findings and sources, and a test account or API token is available.

## Inputs

- topic
- audience
- required points
- CMS base URL
- authorization token when required

## Workflow

1. Confirm the CMS endpoint and authorization.
2. Inspect existing pages to avoid duplicate titles and slugs.
3. Create a draft with a unique lowercase hyphenated slug and a title of at most
   60 characters.
4. Upload a cover image with alt text.
5. Add Summary, Method, Findings, and Sources sections. Include every required
   point and at least one source URL.
6. Publish the draft.
7. Read the public page back and confirm status, title, slug, metadata,
   sections, source, and image.
8. On a publish timeout, retry once. If authorization is missing, stop and
   escalate.

## Verification

- page status is `published`;
- title is at most 60 characters;
- slug is lowercase and hyphenated;
- meta description is 50–160 characters;
- body contains Summary, Method, Findings, and Sources;
- body contains at least one `https://` source;
- a cover image exists;
- no other page has the same title;
- every task-required point appears in the body.

## Failure handling

- Missing or invalid authorization: do not attempt to bypass login; stop and ask
  for a test account or token.
- Slug conflict: choose a new unique slug.
- Duplicate title: choose a distinct title.
- Publish timeout: retry once, then report the failure.
