#!/usr/bin/env node
/**
 * Bounded repository-local operational CLI.
 *
 * Contract:
 *   node scripts/ops-cli.mjs list --manifest <path> [-- <id>...]
 *   node scripts/ops-cli.mjs serve [--host <loopback-host>] [--port <0-65535>]
 *
 * On success: one JSON object on stdout and exit 0.
 * On any controlled failure: nothing on stdout, one JSON error on stderr,
 * and exit 2. Unexpected failures exit 1.
 *
 * The helper is read-only. `serve` validates the host against the loopback
 * allowlist before creating or binding a server, and then closes the socket.
 */

import { readFileSync } from "node:fs";
import { createServer } from "node:net";

const EXIT_OK = 0;
const EXIT_USAGE = 2;

const COMMANDS = new Set(["list", "serve"]);
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1", "localhost"]);
const ALLOWED_OPTIONS = {
  list: new Set(["manifest"]),
  serve: new Set(["host", "port"]),
};

class CliError extends Error {
  constructor(message, code = EXIT_USAGE) {
    super(message);
    this.name = "CliError";
    this.code = code;
  }
}

function fail(message) {
  throw new CliError(message);
}

function parseArgs(argv) {
  if (argv.length === 0) {
    fail("missing command; expected one of: list, serve");
  }

  const [command, ...rest] = argv;
  if (!COMMANDS.has(command)) {
    fail(`unknown command: ${command}`);
  }

  const options = new Map();
  const positionals = [];
  let afterDelimiter = false;

  for (let index = 0; index < rest.length; index += 1) {
    const token = rest[index];

    if (afterDelimiter) {
      positionals.push(token);
      continue;
    }
    if (token === "--") {
      afterDelimiter = true;
      continue;
    }
    if (token.startsWith("-") && token !== "-") {
      const equalsAt = token.indexOf("=");
      const key = equalsAt === -1 ? token.slice(2) : token.slice(2, equalsAt);
      if (!key) {
        fail("empty option name");
      }
      if (!ALLOWED_OPTIONS[command].has(key)) {
        fail(`unknown option for ${command}: --${key}`);
      }
      if (options.has(key)) {
        fail(`duplicate option: --${key}`);
      }
      let value;
      if (equalsAt !== -1) {
        value = token.slice(equalsAt + 1);
      } else {
        const next = rest[index + 1];
        if (next === undefined || next === "--" || next.startsWith("-")) {
          fail(`option --${key} requires a value`);
        }
        value = next;
        index += 1;
      }
      if (value === "") {
        fail(`option --${key} requires a non-empty value`);
      }
      options.set(key, value);
      continue;
    }

    fail(`unexpected positional argument: ${token}; place positionals after --`);
  }

  for (const key of options.keys()) {
    if (!ALLOWED_OPTIONS[command].has(key)) {
      fail(`unknown option for ${command}: --${key}`);
    }
  }

  return { command, options, positionals };
}

function readManifest(manifestPath) {
  let raw;
  try {
    raw = readFileSync(manifestPath, "utf8");
  } catch {
    fail(`cannot read manifest: ${manifestPath}`);
  }

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    fail(`manifest is not valid JSON: ${manifestPath}`);
  }

  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    fail("manifest must be a JSON object");
  }
  if (!Array.isArray(parsed.entries)) {
    fail("manifest must contain an entries array");
  }

  return parsed.entries.map((entry, index) => {
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
      fail(`manifest entry ${index} must be an object`);
    }
    if (typeof entry.id !== "string" || entry.id === "") {
      fail(`manifest entry ${index} needs a non-empty string id`);
    }
    if (typeof entry.target !== "string" || entry.target === "") {
      fail(`manifest entry ${index} needs a non-empty string target`);
    }
    if (typeof entry.read_only !== "boolean") {
      fail(`manifest entry ${entry.id} needs a boolean read_only`);
    }
    return { id: entry.id, target: entry.target, read_only: entry.read_only };
  });
}

function runList(options, positionals) {
  if (!options.has("manifest")) {
    fail("list requires --manifest <path>");
  }
  if (positionals.includes("")) {
    fail("positional entry ids must be non-empty");
  }

  const manifestPath = options.get("manifest");
  const entries = readManifest(manifestPath);

  let selected = entries;
  if (positionals.length > 0) {
    const requested = new Set(positionals);
    const known = new Set(entries.map((entry) => entry.id));
    for (const id of requested) {
      if (!known.has(id)) {
        fail(`unknown entry id: ${id}`);
      }
    }
    selected = entries.filter((entry) => requested.has(entry.id));
  }

  return {
    ok: true,
    command: "list",
    manifest: manifestPath,
    count: selected.length,
    entries: selected,
  };
}

function parsePort(value) {
  if (!/^\d+$/.test(value)) {
    fail(`port must be an integer: ${value}`);
  }
  const port = Number(value);
  if (!Number.isSafeInteger(port) || port < 0 || port > 65535) {
    fail(`port must be between 0 and 65535: ${value}`);
  }
  return port;
}

async function runServe(options, positionals) {
  if (positionals.length > 0) {
    fail("serve does not accept positional arguments");
  }

  const host = options.get("host") ?? "127.0.0.1";
  const port = options.has("port") ? parsePort(options.get("port")) : 0;

  if (!LOOPBACK_HOSTS.has(host)) {
    fail(`refusing non-loopback host: ${host}`);
  }

  const boundPort = await new Promise((resolve, reject) => {
    const server = createServer((socket) => socket.destroy());
    server.once("error", reject);
    server.listen({ host, port, exclusive: true }, () => {
      const address = server.address();
      const actualPort = typeof address === "object" && address !== null ? address.port : port;
      server.close((closeError) => {
        if (closeError) {
          reject(closeError);
        } else {
          resolve(actualPort);
        }
      });
    });
  });

  return {
    ok: true,
    command: "serve",
    host,
    port: boundPort,
    loopback: true,
  };
}

async function main() {
  const { command, options, positionals } = parseArgs(process.argv.slice(2));
  if (command === "list") {
    return runList(options, positionals);
  }
  return runServe(options, positionals);
}

main()
  .then((result) => {
    process.stdout.write(`${JSON.stringify(result)}\n`);
    process.exitCode = EXIT_OK;
  })
  .catch((error) => {
    const code = error instanceof CliError ? error.code : 1;
    const message = error instanceof Error ? error.message : String(error);
    const reason = code === EXIT_USAGE ? "usage" : "internal";
    process.stderr.write(`${JSON.stringify({ ok: false, error: { code: reason, message } })}\n`);
    process.exitCode = code;
  });
