---
name: specs-login
description: Authenticate with the Awolve Spec Service
allowed-tools: [AskUserQuestion]
---

# /awolve-spec login

Authenticate with the Awolve Spec Service so specs can be synced.

## Instructions

Your ONLY job is to ask the user which auth method they want. Do NOT run any commands.

Use AskUserQuestion to ask:

> How do you want to authenticate with the spec service?
>
> 1. **Azure CLI** — for Awolve team members (uses `az login`)
> 2. **API key** — for external collaborators (key from the portal)

Then, based on their answer:

**If Azure CLI:** run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py login-azure` and then `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py status` to verify. If it fails, tell the user to run `! az login` first, then retry.

**If API key:** tell the user:

> 1. Go to https://specs.awolve.ai/portal/settings and generate an API key (if you don't have one)
> 2. Copy the key to your clipboard
> 3. Run: `! python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py login-apikey --from-clipboard`
>
> The key is read from your clipboard, verified, and saved. Your clipboard is cleared afterwards.

Then verify with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py status` and suggest `/awolve-spec pull`.
