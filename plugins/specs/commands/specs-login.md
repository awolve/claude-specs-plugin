---
name: specs-login
description: Authenticate with the Awolve Spec Service
allowed-tools: [AskUserQuestion]
---

# /specs-login

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

**If API key:** tell the user to run this themselves (the `!` prefix keeps the key private):

> `! python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py login-apikey`
>
> If you don't have an API key yet, generate one at https://specs.awolve.ai/portal/settings

Then verify with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py status` and suggest `/specs-pull`.
