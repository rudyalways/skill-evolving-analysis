---
name: merge-gate-triage
description: Triages a blocked merge or pre-push quality gate by using its named failure mode to separate untracked-workspace contamination from a change-independent defect, then fixes the actual cause. Use when a gate exits nonzero with a named mode such as working-tree-iteration-only or clean-checkout, especially after a rebase or when the failing check looks unrelated to the pushed diff.
---

## Overview

A merge or pre-push quality gate can block for two very different reasons that
produce the same red build: files in the workspace that are not in the commit,
or a defect already present in repository history. This skill uses the gate's
own named failure mode to decide which is which, then removes the workspace
pollution or fixes the inherited defect without misattributing it to the
current change.

It owns triage from the first nonzero gate exit to a green rerun. It does not
own ordinary debugging of a failure already localized to the diff.

## When to Use

Any one of these is enough to invoke the skill:

- A merge or pre-push quality gate exits nonzero and names a failure mode,
  such as `working-tree-iteration-only`, `clean-checkout`, or an equivalent
  workspace or checkout mode.
- The gate starts failing immediately after a rebase, cherry-pick, branch
  switch, or fresh clone while the pushed change is small or unrelated.
- The failing check touches files the current diff does not modify, or the
  failure survives reverting the changed files locally.
- The same gate command can be rerun unchanged and reports a specific named
  mode or failing assertion.

## Do Not Use

- Do not use for an ordinary test failure that a stack trace already localizes
  to a function or line in the current change; debug it directly.
- Do not use for credential, network, registry, disk-space, or CI
  infrastructure errors; repair the environment instead.
- Do not use when the gate emits no named failure mode and cannot be rerun
  unchanged; there is nothing to classify.
- Do not use quarantine or blame to hide a real defect in the current diff or
  to make a gate pass without fixing the cause.
- Do not use for general merge review or release decisions.

## Workflow

1. Capture evidence before editing anything. Record the exact gate command,
   its working directory, exit code, and full output, including the named
   failure mode and any assertion text. Record `git status --porcelain
   --ignored`, `git log -1 --oneline`, and the merge base
   (`git merge-base HEAD <base>`). Do not change code, flags, or metadata.

2. Classify from the named mode, not from intuition.
   - `working-tree-iteration-only` or an equivalent workspace, dirty-tree, or
     untracked-files mode: the gate iterates the working tree and sees files
     outside the commit. Go to step 3.
   - `clean-checkout` or an equivalent checkout, archive, or HEAD mode: the
     gate examines committed content only, so workspace contamination is not
     the cause. Skip to step 5.
   - No mode, or two modes are plausible: stop and report. Do not guess.

3. Quarantine untracked and generated artifacts.
   - Create a hold directory outside the repository, for example
     `HOLD="$(mktemp -d "${TMPDIR:-/tmp}/gate-hold.XXXXXX")"`.
   - Install a restore trap before moving anything, for example
     `trap 'restore_from_hold' EXIT INT TERM`, where the function moves every
     held path back to its recorded absolute location and removes empty
     parents. Record a manifest of the paths and their original locations.
   - Move each untracked or ignored build, cache, coverage, or test artifact
     with `mv`, recreating its relative parent directories under `HOLD`. Move,
     never delete and never overwrite. Leave tracked edits in place; they are
     part of the change.
   - If an untracked path is intended source for the change, stop: the change
     is incomplete. Do not quarantine it and do not silently hide it.
   - Rerun the exact same gate command from the same directory. Same binary,
     same flags, same environment.

4. Read the quarantined rerun.
   - Exit 0: the failure was workspace contamination. Restore the held paths
     through the trap, confirm the workspace matches the pre-quarantine
     manifest, and report. No code or commit changes.
   - Still nonzero in `clean-checkout`, or now progressing past the workspace
     mode to a concrete assertion: the remaining failure is independent of the
     current diff. Go to step 5.
   - Nonzero with a different mode or assertion that only appears while files
     are held: the quarantine changed the failure. Re-examine instead of
     claiming change-independence.

5. Isolate the failure with history. Use the exact failing file, assertion, or
   symbol named in the output; do not search the whole repository.
   - Run `git blame -L <start>,<end> -- <path>` on the failing lines. Add
     `-C -M` when code may have moved or been renamed.
   - Confirm the blamed commit is an ancestor of the merge base, and that
     `git diff <merge-base>..HEAD -- <path>` does not touch the failing lines
     or the fix site.
   - When practical, confirm on a pristine checkout of the merge base in a
     throwaway worktree outside the repository:
     `git worktree add "$HOLD/base" <merge-base>` and run the same gate there.
     A failure with no current diff is strong change-independent evidence.

6. Fix the actual cause.
   - If blame shows the lines predate the merge base or the current diff's
     commits, fix the defect in a separate commit on top of the feature branch.
     State the inherited defect and the blamed commit in the commit message.
     Do not amend, rebase, or squash it into the feature commit.
   - Keep the fix minimal and confined to the defect. Add a regression test only
     if the gate requires coverage, and keep it in the same separate commit.
   - If blame shows the failing lines were introduced or last changed by a
     commit in the current diff, the failure is feature-caused. Stop the
     inherited-defect path, fix it in the normal feature commit, and do not
     create a separate "inherited" commit.

7. Rerun the same gate command unchanged. A green exit is required. If the
   rerun fails at a different assertion, return to step 5 with that new line;
   do not bundle unrelated fixes into the same commit.

8. Clean up and confirm. Restore quarantined paths, remove the temporary
   worktree, verify `git status` shows no stray artifacts or hold directories
   inside the repository, and report the outcome.

## Constraints

- Capture the command and named mode before any edit, and rerun byte-identical
  commands; never widen, narrow, or skip a gate check to get green.
- Move untracked artifacts into a hold directory outside the repository and
  restore them on every exit path, including interrupt and failure, using a
  trap. Never delete, truncate, or overwrite untracked files.
- Never use `git clean`, `git checkout -- .`, `git reset --hard`, or `git add -A`
  to make the workspace look clean; those destroy evidence.
- Keep inherited-defect fixes in their own commit, never amended or squashed
  into the feature commit, and never mixed with unrelated changes.
- Change no code until a rerun names a specific failing assertion and blame
  evidence shows the defect predates the current diff.
- Do not accept the current diff as the cause of a failure that reproduces
  without it, and do not excuse a failure that blame places inside the diff.
- Do not commit the hold directory or temporary worktree.

## Verification

- The gate command is recorded verbatim and each rerun is unchanged.
- After quarantine, `git status --porcelain` shows no contaminating untracked
  paths, and the rerun output is captured with its exit code.
- If the rerun passes, the pre-quarantine manifest and file contents are
  restored exactly, and no commit was created.
- If the failure is inherited, the report contains the blamed line range,
  commit, and date; the diff from the merge base does not touch those lines;
  the fix commit is separate, based on the feature tip, and touches only the
  defect and its regression coverage.
- The same gate command exits 0 on the final run, and `git status` shows no
  stray artifacts, hold directories, or worktrees.

## Output Format

Report concisely, with evidence:

- Gate command and the first named failure mode.
- Classification: workspace contamination, change-independent defect, or
  feature-caused failure.
- Quarantine: hold path, paths moved, and restore status.
- Each rerun in order, with exit code and the mode or assertion it reported.
- For an inherited defect: failing assertion, `file:line`, blamed range and
  commit, why the current diff is not responsible, fix commit hash and subject,
  and final gate result.
- Any unresolved item or escalation instead of a guessed classification.

## Limitations

- Requires a gate that names its failure modes and can rerun unchanged without
  network, credentials, or shared cached state.
- Blame identifies the last change to a line, not the original design cause;
  moved or renamed code may need `-C -M` and manual reading.
- Quarantine does not help when the gate reads absolute paths, caches, or
  generated files from outside the repository.
- Cannot distinguish flaky or environment-dependent failures from defects;
  repeated runs are needed before trusting a single green result.
- An inherited fix may be large or owned by another team; escalate rather than
  expanding the current change.
