# Cursor CLI in Docker

This demo builds a Linux image, installs the Cursor agent CLI inside it, and starts a container. It also tries the macOS CLI mount and shows that it does not run.

## What is on this Mac

Two different programs:

| Command | What it is | Can a Linux container run it? |
| --- | --- | --- |
| `/usr/local/bin/cursor` | Launcher for `Cursor.app` | No. It starts the macOS app. |
| `~/.local/bin/agent` | Agent CLI. A shell script plus a Mach-O arm64 `node` and Mach-O addons. | No. Docker Desktop here is `linux/arm64`. A Mach-O binary exits with an exec-format error. |

Login is a third thing, not a path next to the binary.

- The editor session is the macOS keychain item `Cursor Safe Storage`.
- The CLI session is its own store. On macOS that file is `~/.cursor/auth.json`. On Linux it is `/root/.config/cursor/auth.json`.
- On this Mac, `agent status` reports `Not logged in`, and `~/.cursor/auth.json` is absent. The editor being signed in does not sign in the CLI.

Mounting `~/.local/bin/agent` or `~/.local/share/cursor-agent` therefore does not produce a logged-in Linux agent.

## Run

```bash
cd demos/cursor-in-docker
./run-demo.sh
```

The script builds `cursor-cli-demo`, prints the Linux CLI version, shows the mounted macOS `node` failing, and leaves a container named `cursor-cli-demo` running.

## Sign in inside the container

Browser login, completed on the Mac:

```bash
docker exec -it cursor-cli-demo bash -lc 'NO_OPEN_BROWSER=1 agent login'
```

Open the URL the command prints. That writes `/root/.config/cursor/auth.json` in the container. Removing the container removes that file. To keep it, add `-v cursor-cli-auth:/root/.config/cursor` when you `docker run`. That volume is a container credential store. It is not the Mac keychain.

API key, for a non-interactive run. Create one at [Cursor Dashboard → API Keys](https://cursor.com/dashboard):

```bash
docker rm -f cursor-cli-demo
docker run -d --name cursor-cli-demo \
  -e CURSOR_API_KEY \
  -v "$PWD:/work" \
  cursor-cli-demo
docker exec cursor-cli-demo agent status
```

`agent` reads `CURSOR_API_KEY` itself. The image does not contain the key. `-e CURSOR_API_KEY` forwards the variable already set in the host shell.

A one-shot prompt:

```bash
docker exec cursor-cli-demo agent -p --trust --workspace /work "say hello in one line"
```
