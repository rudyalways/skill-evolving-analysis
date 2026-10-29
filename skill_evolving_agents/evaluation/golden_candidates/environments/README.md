# Candidate environment categories

Each candidate has one primary environment category. A cloud skill may also
require auth/payment; inspect `metadata.json` for flags.

| Category | Count | Resource need |
|---|---:|---|
| [cloud_tenant](cloud_tenant/INDEX.md) | 36 | Cloud account/tenant and its CLI/API. |
| [local_cli](local_cli/INDEX.md) | 33 | Local CLI or script; network/auth not required. |
| [workspace](workspace/INDEX.md) | 28 | Local files and directories; document/artifact work; no execution runtime required. |
| [lab_vm](lab_vm/INDEX.md) | 20 | VM, security lab, or isolated host. |
| [browser_public](browser_public/INDEX.md) | 16 | Browser automation against public pages; no login. |
| [gpu_hardware](gpu_hardware/INDEX.md) | 16 | GPU/accelerator or specialized hardware. |
| [http_auth](http_auth/INDEX.md) | 8 | Authenticated HTTP/API/SaaS workflow. |
| [desktop_app](desktop_app/INDEX.md) | 7 | Desktop GUI application. |
| [browser_auth](browser_auth/INDEX.md) | 2 | Browser automation with login/session. |

## Defined but currently empty

- `local_runtime` — local Python/Node/library runtime, no network/auth.
- `local_cli_auth` — local CLI requiring an account/token.
- `remote_cli` — remote shell/cloud CLI over the network.
- `http_public` — public HTTP/API/web fetch, no auth.
- `simulator` — game/robotics/network simulator.
- `hybrid` — multiple environment categories.

A skill can require auth or payment inside `cloud_tenant`, `http_auth`,
`browser_auth`, or `desktop_app`; check its metadata for the secondary flags.
