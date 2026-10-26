---
name: authored-cli-helper
description: Author and validate a repository-local operational CLI helper with a stable machine-readable JSON contract, strict argument parsing, loopback-only server defaults, and nonzero-on-failure behavior. Use when adding a reusable ops command, hardening a development or review server to bind loopback only, or proving a newly authored script with a syntax check plus a live read-only invocation and negative cases.
---

# Authored CLI helper

## Overview

Own the bounded task of adding or revising one repository-local operational CLI
helper and proving its contract: explicit inputs, machine-readable JSON output,
deterministic exit codes, safe defaults, and no partial publication on failure.
The helper is intentionally a small representative, not a framework or a copy of
an existing source script.

## When to Use

Use when any one of these conditions holds, even if the others are absent:

- An agent must add a reusable operational command to a repository rather than
  run a one-off shell command.
- A development or review server must be hardened so it binds only to a
  loopback host before it starts listening.
- A newly authored script must be validated with a runtime syntax check and at
  least one live read-only invocation that emits parseable JSON.
- Malformed arguments, a missing required input, or a non-loopback host must be
  shown to fail with a nonzero exit and no partial output.

## Do Not Use

Do not use for one-off shell commands, throwaway exploration scripts, broad
application feature work, production deployment, TLS or authentication
infrastructure, or any change that would expose an unauthenticated server
beyond loopback. Do not use it to design a general CLI framework, to migrate a
whole command surface, or to validate behavior that requires production
credentials or network access outside the local machine.

## Workflow

1. Fix the contract before writing code. Name the command and subcommands, every
   accepted option, required inputs, positional handling including the `--`
   delimiter, the JSON keys emitted on success, exit codes, side effects, and
   the exact failure behavior. Keep the contract smaller than the apparent
   request.
2. Inspect the repository's existing operational CLI location and reuse its
   stores, libraries, and conventions rather than duplicating them. If no path
   exists, place the helper at the repository's conventional ops path, such as
   `scripts/ops-cli.mjs`.
3. Implement strict parsing. Accept only documented options, reject unknown and
   duplicate flags, reject an option value that is missing or itself looks like
   a flag, and treat `--` as the end of option parsing so every later token is
   preserved as a positional. Reject stray positionals before the delimiter.
4. Apply safe defaults before any side effect. Default the server host to a
   loopback address and check the requested host against an explicit allowlist
   (`127.0.0.1`, `::1`, `localhost`) before creating a server or calling
   `listen`. Fail closed for every other host, including `0.0.0.0`.
5. Build the complete result object before writing it. Emit exactly one JSON
   object plus a newline on stdout on success and exit zero. On a controlled
   failure, write one JSON error object to stderr, write nothing to stdout, and
   exit with the documented nonzero code; reserve a separate nonzero code for
   unexpected internal failures.
6. Validate in this order: run the runtime syntax check on every authored
   module, run one live read-only command and parse its JSON, then run the
   negative cases for an unknown flag, a missing required input, and a
   non-loopback host. Finally confirm that `--` preserves the positionals that
   follow it.
7. Record each command with its observed exit code and the JSON keys observed
   from the live run. Do not claim a check passed unless its exit code and
   output were actually observed.

`scripts/ops-cli.mjs` is the bounded representative of this contract, with
`list` and `serve` subcommands. Its fixture is
`scripts/fixtures/manifest.json`. Adapt the contract to the repository instead
of copying repository-specific names or absolute paths. Case definitions in
`evals/evals.json` describe the positive run and the three required near-miss
rejections.

## Constraints

- Keep the helper bounded and non-destructive: read-only commands by default.
- Write only to an explicit temporary or repository-local target that the
  caller named; never write by default and never publish partial output.
- Never hardcode a user name, home directory, machine path, port that may be in
  use, credential, or copied vendor log.
- Reject unknown flags, duplicate flags, empty required values, and unexpected
  positionals instead of silently ignoring them.
- Never bind a review or development server to a non-loopback host and never
  add TLS, authentication, or deployment adapters under this scope.
- Return a nonzero exit for every failure. Do not exit zero after printing an
  error object, and do not print a success object before all checks pass.
- Keep the authored surface to one helper module plus its fixture and eval
  cases; do not expand into a broader command-line migration.

## Verification

Run each check from the repository root and record its observed exit code:

1. `node --check scripts/ops-cli.mjs` must exit 0.
2. `node scripts/ops-cli.mjs list --manifest scripts/fixtures/manifest.json`
   must exit 0 and print one parseable object with `ok`, `command`, `manifest`,
   `count`, and `entries`.
3. `node scripts/ops-cli.mjs list --manifest scripts/fixtures/manifest.json -- health`
   must exit 0 and show only the `health` entry, proving the delimiter
   preserved the positional.
4. `node scripts/ops-cli.mjs serve --host 127.0.0.1` must exit 0 and print
   `ok`, `command`, `host`, `port`, and `loopback`.
5. `node scripts/ops-cli.mjs list --manifest scripts/fixtures/manifest.json --bogus`
   must exit 2 with empty stdout.
6. `node scripts/ops-cli.mjs list` must exit 2 with empty stdout.
7. `node scripts/ops-cli.mjs serve --host 0.0.0.0` must exit 2 with empty
   stdout and must not bind a socket.

Parse stdout with a JSON parser rather than pattern matching. Confirm the
negative cases produced no partial success object. Validate
`evals/evals.json` against the eval schema when the harness supplies one, and
keep its positive and near-miss cases runnable without the source repository.

## Output Format

Report concisely and evidence first:

- The files added or changed, by relative path.
- Each exact validation command with its observed exit code.
- The JSON keys produced by the successful live run.
- The result of each negative case: unknown argument, missing required input,
  non-loopback host, and the `--` positional check.
- Any residual risk, such as a repository-specific runtime not being exercised.

Keep the report as prose or a compact list. Do not write logs, status records,
or metadata.

## Limitations

The helper is a bounded representative derived from a validated contract, not a
copy of any source script. It does not cover production authentication, TLS
termination, deployment adapters, long-running daemon management, or shell
portability across operating systems. The live `serve` check binds and closes a
loopback socket; it does not prove production serving behavior.
