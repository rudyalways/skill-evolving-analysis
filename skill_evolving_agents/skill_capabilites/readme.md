# Skill capabilities

`skill_capabilites.json` is the pipeline's normalized, self-contained
capability vocabulary. A valid label is either
`<dimension>/<value>` or `<dimension>/<value>/<specialization>`.

The large repository-level `data/skill_capabilites` directory is an analytical
report over public skills. Its clone leaves and placement counts are evidence,
not valid capability names, and are intentionally excluded here.

Agents should create an OOD record without hesitation when no defined path is
accurate; they must not force a real gap into a nearby label. A distinct,
reusable, non-duplicate, evidence-backed OOD record should use its proposed
normalized path and recommend promotion clearly in `reasoning`.

Unknown paths remain in `newly_detected_skill_capabilites_missing` until the
canonical JSON is updated. Run sessions use temporary taxonomy copies, so a
recommendation is durable but a direct in-session taxonomy edit is not.