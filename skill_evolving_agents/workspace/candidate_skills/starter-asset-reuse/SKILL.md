---
name: starter-asset-reuse
description: Reuse a captured starter asset, such as the service-starter config template, by copying and adapting it instead of regenerating equivalent content inline. Use when scaffolding a service config that matches the recorded starter contract.
---

# Starter Asset Reuse

## Overview

Own the decision to reuse a captured starter artifact as a copyable template
rather than reauthoring the same bounded content in each session. Two artifact
families are in scope: the service-starter configuration under
`assets/templates/service-starter/config.yml`, and an authored pipeline
configuration captured after validation under
`assets/templates/outlink-discovery-pipeline/pipeline.v1.json`. A pipeline
template is captured from a `site-ops.pipeline/v1` configuration that has
already been schema-validated and registered, then reused in later lifecycle
stages instead of being regenerated. Reuse is appropriate only when the
requested deliverable matches a recorded contract.

## When to Use

Activate when any of these conditions holds:

- The requested deliverable matches a recorded starter artifact, especially a
  service-starter config whose contract is the `service`, `healthcheck`,
  `readiness`, and `timeout_seconds` fields.
- The same starter patch has already been produced, so the current request is a
  restatement or repeat rather than a new design.
- The request explicitly asks to scaffold, copy, or adapt a known starter
  template instead of writing an equivalent config from scratch.
- A `site-ops.pipeline/v1` configuration has been authored, schema-validated,
  and registered, and a later lifecycle stage now needs that same pipeline.
- A later lifecycle stage asks for a pipeline that already exists in the
  validated inventory, even if the request is worded as fresh authoring.

## Do Not Use

Do not use this skill when:

- No captured artifact matches the requested shape or contract.
- The deliverable is a genuinely different service contract that needs fields,
  nesting, or behavior the template does not contain.
- Adapting the template would require inventing undocumented values, secrets,
  credentials, or environment-specific overrides.
- A pipeline request lacks the observed `site-ops.pipeline/v1` schema or any
  validation evidence, so the captured template cannot be stretched to cover it.
- A pipeline field is undocumented or absent from the captured schema and the
  request would require inventing it.
- The pipeline content was never schema-validated or registered; capture must
  not turn an unvalidated draft into a reusable template.

## Workflow

1. Select the matching artifact: `assets/templates/service-starter/config.yml`
   for a service starter, or
   `assets/templates/outlink-discovery-pipeline/pipeline.v1.json` for an
   authored pipeline. Read the whole template before copying anything.
2. To instantiate an authored pipeline, copy
   `assets/templates/outlink-discovery-pipeline/pipeline.v1.json` to the target
   location with a direct file copy. Do not regenerate the pipeline
   configuration, redraft the stages, or reconstruct the definition from
   memory. Keep the captured `site-ops.pipeline/v1` schema, `id`, `owner`,
   `stages`, `reviewPolicyRef`, `targetAdapterRef`, and `limits` as they are.
3. Adapt only documented values the request actually changes, such as the input
   source configuration in `inputPorts` (`name` and `schemaRef`). Leave every
   other value at its template default. If a needed value is undocumented,
   absent from the captured template, or not covered by validation evidence,
   stop and report it instead of inventing a field or stretching the template.
4. Validate or register the emitted pipeline before use: confirm it parses as
   JSON, run the schema-field check, and run
   `pnpm ops:workbench pipeline list --json`. Record both results. Do not use
   an unvalidated or unregistered pipeline downstream.
5. For a service starter, compare the requested contract with the template.
   Confirm that the top-level `service`, `healthcheck`, `readiness`, and
   `timeout_seconds` fields cover the request. If they do not, stop and use the
   appropriate design path instead of stretching this template.
6. Copy the selected service template to the target location with a direct file
   copy so its structure and comments are preserved.
7. Adapt only the values the request actually changes, such as the service
   name, healthcheck path, or timeout. Leave every unmentioned value at its
   template default. If a required value is unavailable in the finding, keep
   the documented placeholder and report it as unresolved rather than
   inventing an undocumented field.
8. Re-read the emitted file. For a service config, confirm it parses as YAML
   and check the contract keys. For a pipeline, confirm the documented
   adaptation is the only difference from the copied template.
9. Report the copied path, the adapted fields, any unresolved placeholders, and
   the validation results for the selected artifact.

## Constraints

- Do not regenerate an equivalent config inline when the template exists.
- Keep adaptations limited to values the request actually changes; preserve
  key names, ordering, and unrelated content.
- Never embed credentials, tokens, or environment-specific secrets in the
  template or in the emitted file.
- Do not expand the starter into a full deployment manifest or add undocumented
  fields unless the request explicitly asks for a different contract.
- Do not overwrite an existing target file without confirming that replacement
  is intended.

## Verification

Check that the emitted file:

- Exists at the reported path and parses as YAML for a service starter or JSON
  for a pipeline.
- For a service starter, contains the `service`, `healthcheck`, `readiness`,
  and `timeout_seconds` keys with non-empty, valid values.
- For a pipeline, keeps the `site-ops.pipeline/v1` schema field and passes the
  schema-field check. Run the pipeline-list check with
  `pnpm ops:workbench pipeline list --json` and confirm the instantiated
  pipeline is listed once, matching the intended registration.
- Record the schema-field and pipeline-list check results. Treat the
  schema-field check as the JSON analogue of `node --check`; do not report
  completion when either check fails.
- Differs from the selected template only in the intentionally adapted fields,
  and contains no undocumented fields.
- Contains no credentials or environment-specific secrets.

Behavioral cases for activation and near-miss boundaries are recorded in
`evals/evals.json`.

## Output Format

Report:

- The copied artifact path.
- The adapted fields and their new values.
- Any placeholder left unresolved.
- A short confirmation that the result matches the starter contract.

## Limitations

The service template covers a single small service config. It is a starter, not
a complete deployment manifest, and it does not supply secrets, environment
overrides, scaling policy, or service-specific infrastructure. When the request
needs any of those, the service template is not a sufficient match.

The pipeline template is limited to the observed `site-ops.pipeline/v1` schema
and the fields captured with validation evidence. It is not a general pipeline
authoring system. Content unavailable in the finding remains a documented
placeholder rather than a reconstructed pipeline definition, and the template
must not be extended with undocumented fields.
