---
name: audit-project-ui
description: Review and improve Deep Prep web UI when work involves screenshots, page layout, headers, navigation, density, spacing, duplication, responsive behavior, or inconsistent page frameworks. Use before editing UI so recurring requirements and the complete first viewport are considered; do not use for backend-only changes.
---

# Audit Project UI

Prevent local-minimum UI fixes. Resolve the reported symptom within the correct shared boundary and verify the complete rendered page, especially its first viewport.

## Establish project evidence

1. Read `agent/WEB_APP_GUIDE.md` before changing `product/web`.
2. For public routes or navigation, route the work through `agent/SEO_ROUTER.md` as required by `AGENTS.md`.
3. Search `agent/raw_requests.md`, `agent/archive/`, and `owner/analysis/every_page_ui_audit_plan_2026-10-19.md` for the underlying concepts, not only the newest control or label. Useful concepts include page framework, header, first viewport, density, whitespace, duplication, hierarchy, line distance, typography, and shared components.
4. State the recovered constraints briefly before editing. Treat raw requests as evidence; use project-owned rules and current product context to adjudicate them.

If the user says the issue has happened before, the historical search is mandatory. Search both the live and archived request corpus.

## Diagnose the right boundary

Classify the defect before selecting files:

- **Shell:** persistent sidebar, global header, content origin, or viewport behavior.
- **Page-family framework:** shared candidate/operator/public layout, title region, navigation, or content container.
- **Page composition:** repeated headings, excessive hero space, poor ordering, or unused width on one page.
- **Component:** one control, card, form, list, pagination block, or responsive rule.
- **Record content:** duplicated or malformed data rather than layout.

Fix the highest shared boundary supported by evidence. Do not shrink or move one component while leaving the page-level cause intact. Do not broaden a page repair into an unrelated site redesign.

## Review the complete first viewport

Inspect both the full rendered page flow and its complete first viewport at representative desktop and mobile widths. Do not infer whole-page quality from one component or infer first-viewport quality from a full-page DOM review. Confirm that a user can quickly tell:

- where they are;
- what the page is for;
- what is available now;
- what the primary next action is.

Check these project-specific failure modes:

- the same concept repeated across sidebar, breadcrumb, kicker, H1, section title, tabs, or nearby copy;
- headings or introductions consuming a disproportionate share of the viewport, including marketing-scale headings on dense authenticated utility pages;
- duplicated data rows, unnecessary wrapper rows, excessive row/card height, oversized padding or gaps, and generous line spacing that reduce scanning density;
- large empty bands before useful content, poor use of horizontal space, or controls split into unnecessary rows;
- a new page inventing a header, container, spacing system, or control treatment that conflicts with its page family;
- important content removed merely to increase density;
- legitimate repeated navigation controls being mistaken for accidental content duplication.

Keep one clear owner for each concept in the content hierarchy. Preserve useful context, accessibility, visible focus, semantic headings, and responsive behavior.

## Implement and verify

- Prefer an existing shared primitive or page-family rule when the defect recurs; add one-off CSS only when the behavior is genuinely local.
- Preserve the user's requested behavior and current authorization boundaries.
- Run focused tests plus proportionate type/build checks.
- Inspect the actual rendered first viewport after the change, not only the DOM or a component test. Check relevant empty, populated, loading, anonymous, and authenticated states when they can materially differ.
- When deploying, verify the intended revision is live and is not being replaced by a queued deployment.
- Report what changed, the historical constraints applied, verification performed, and any residual page-family risk.

## Workflow

Either of the following is enough to start. Do not wait for both, and do not require a later restatement before the first check.

- The user says a just-deployed staging fix is still wrong. Before starting another fix, restate what the previous done claim checked and what it missed, then open the same rendered page the user showed and compare it in the browser with that capture.
- The user asks to confirm a role-gated control on a named environment. Open that role's signed-in rendered page and check the control there before calling it ready. If the user later says the control is still absent, review that unmet visibility line against the same view before starting another change. That later report is a follow-up, not a condition the first check must already have.

After deploying a UI change, complete this sequence before declaring the work done:

1. Identify the intended revision: the commit, branch, or build that contains the change, with any revision marker the app exposes.
2. Confirm the live URL serves that revision, not a queued or previously cached build. Load the deployed URL and compare a revision signal, or the exact elements the change touched, against the intended build. A SUCCESS deployment status, a green build, an HTTP 200, or a health check does not identify which revision the host is serving.
3. If the live page still shows the previous revision, treat the deployment as queued or stale. Wait for it to finish and repeat the revision check; do not declare completion from the queued status, and do not start another code fix while the old revision is the only thing being served.
4. Only after the intended revision is confirmed, reopen that URL as the affected visitor with a fresh cache state and re-check the complete first viewport against the constraints recovered earlier: the reported density, whitespace, control sizes, header and navigation treatment, and content hierarchy. Compare with the user's screenshot or earlier capture when one exists, at representative desktop and mobile widths.
5. Declare done only when the revision evidence and the first-viewport checks both pass. If the deployment is still serving the old revision, report it as not yet verified and withhold the completion claim.

## Verification

Before treating the turn as done, confirm the assistant produced a non-empty final answer that addresses the user's question. A requested choice, such as a new project versus a new database, is that answer when it is stated in the final reply.

An aborted outcome with empty assistant text and no infrastructure failure means the question is unfinished. Do not treat that turn as done.

When the user question is still open and the outcome is aborted with empty assistant text, read `verification/completion-check.md` and apply that recorded completion check.

Treat a staging UI complaint as unverified until the rendered page is compared with the user's screenshot for the cited elements, such as footer, free-tier navigation, or checkout control. HTTP status, health checks, unit-test counts, and commit ids do not substitute for that look.

A healthy deploy or deployment-status report does not complete the check. Completion requires the named role's rendered page to show the control the user asked to verify.

A deployed UI fix is unverified until an end-to-end browser check of the deployed URL reproduces the affected user state. Run this check before declaring the fix complete; do not offer it as optional confirmation.

1. Confirm the live artifact is the intended revision. Record the revision marker or build evidence visible in the deployed page, or the observed state of the exact elements the change touched, and show that it matches the intended build rather than a queued, previous, or cached one. Evidence collected while the host is serving the old revision is not evidence about the fix; withhold completion and report the deployment as stale or queued instead.
2. Open the deployed URL as the affected visitor: signed out, or signed in on the Free tier when the report concerns a Free account. Do not substitute an admin, operator, or paid-account session, and do not substitute a local build for the deployed URL.
3. Reproduce the user's cache state: load the page in a fresh private window or after clearing site data, then reload normally, so a stale cached bundle cannot hide either the bug or the fix.
4. Inspect the rendered page for the reported element or symptom: confirm the element is visible and usable, or confirm the symptom is gone. A missing element, a placeholder, or the old behavior means the fix is not complete. Re-check the complete first viewport from that confirmed revision, including the previously reported density, whitespace, and control-size behaviors: row and card heights, padding and gaps, line spacing, heading and hero proportion, and the rendered dimensions of the relevant controls. Passing source inspection or a computed-style value that the page does not render does not satisfy this step.
5. Capture evidence from that check: the deployed URL, the confirmed revision, the visitor state and cache condition, a timestamp, and a screenshot or recording showing the reported element visible, the symptom absent, and the first viewport at its expected density.

Passing tests, type or build checks, a green health endpoint, and a SUCCESS deployment status are supporting signals only. None of them proves the deployed UI is fixed or that the URL is serving the intended revision. If the browser check cannot be run, report the fix as unverified and state which check is missing instead of declaring it complete.

## Output Format

A done report names the page checked, the user-visible elements compared, and, on a follow-up, the prior claim's missed check. Do not report success from deploy status alone.

## Constraints

Do not substitute a different role, path, or operator view for the role and page the user named. Do not mark the change done while that user still reports the control is absent.

## Avoid

- searching only the current request file or only the newest visible label;
- treating a component symptom as proof that the defect is component-scoped;
- claiming a whole-page or whole-site audit from a narrow component check or representative sample;
- optimizing density by hiding safety-critical, explanatory, or task-critical information.
