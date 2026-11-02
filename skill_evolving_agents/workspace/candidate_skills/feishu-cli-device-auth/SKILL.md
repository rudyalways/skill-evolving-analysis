---
name: feishu-cli-device-auth
description: Complete Feishu/Lark CLI login through the terminal-led device-authorization flow: answer CLI prompts, render the verification URL as a QR code or user code, keep the login process waiting, and verify the authenticated session. Use when lark-cli reports missing or expired authorization or a Feishu setup task needs a signed-in CLI; do not drive the browser consent page by clicking or reloading.
---

# Feishu CLI device authentication

## Overview

Feishu/Lark CLI authentication is a terminal-led device flow. `lark-cli` prints a verification URL and user code, the user approves from a device, and the waiting CLI process completes the login. The browser consent page is a provider surface that the agent may not be able to operate; it is not the control surface for this procedure.

## When to Use

Use this skill when any one of the following is true:

- `lark-cli auth status` reports that authorization is missing or expired.
- A Feishu CLI command fails because the CLI lacks authorization.
- A Feishu setup or document task requires a signed-in user identity.

Use it before any task that depends on the CLI holding a valid user token.

## Do Not Use

- `auth status` already reports a valid session with sufficient scopes.
- A configured bot or app token is the intended identity.
- The task uses a non-Feishu authentication system.

## Workflow

1. Run `lark-cli auth status` and confirm that authorization is missing or expired.
2. Start `lark-cli auth login` in an interactive terminal session and answer the app-configuration and permission prompts. Record the app ID and the successful configuration line.
3. Capture the device verification URL and `user_code` from the CLI output.
4. Render the URL as a QR image with `lark-cli auth qrcode`, passing the captured verification URL and a local PNG output path. Present that image together with the user code.
5. Leave the `auth login` process running and wait for the user to approve. Do not start another flow while this one is active.
6. If the browser lands on a scope-authorization page with no actionable consent control, or the flow produces no progress after a reload, stop the stalled process and start a fresh `lark-cli auth login` to mint a new flow and QR code.
7. After approval, run `lark-cli auth status` and verify the identity and scopes before resuming the original task.

## Constraints

- Do not use browser accessibility clicks or repeated reloads of the scope-authorization page as the primary authorization path.
- Keep exactly one device flow active. Replace a consumed, expired, or stalled flow with a fresh login instead of retrying its URL.
- If a browser element action fails because its accessibility handle is stale or missing, refresh the accessibility state and re-resolve the element before any retry.
- Treat the QR image and user code as sensitive. Do not persist credentials beyond the requested output path.

## Verification

Verify success with `lark-cli auth status`: it must report an authenticated user identity with the required scopes, and the app ID must match the one configured during login. Only then run the smallest read or write command that exercises the requested scope. Report the observed identity, app ID, and command result rather than assuming approval succeeded.

## Output Format

Report:

- The pre-login authentication state.
- The verification URL and user code, or the QR artifact path.
- The CLI process state while waiting.
- The fresh-flow action taken if the first flow stalled.
- The final auth status with identity and scopes.

State explicitly whether the user still needs to approve the device flow.

## Limitations

This procedure is Feishu/Lark-specific and depends on `lark-cli` flags that may vary by version. User approval and any browser-side consent remain outside the agent's control. The flow expires if the QR code is not scanned in time, and a provider-side scope change may still be required.
