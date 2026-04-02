---
name: specs-login
description: Authenticate with the Awolve Spec Service
allowed-tools: [Bash, AskUserQuestion]
---

# /specs-login

Authenticate with the Awolve Spec Service so specs can be synced.

## Instructions

### Step 1: Ask the user which auth method they want

Use AskUserQuestion:

> How do you want to authenticate with the spec service?
>
> 1. **Azure CLI** — for Awolve team members (uses `az login`)
> 2. **API key** — for external collaborators (key from the portal)

### Step 2a: Azure CLI

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py login-azure
```

This auto-detects Azure CLI, fetches a token, and configures auto-refresh. Tokens refresh automatically on each API call — no expiry.

If it fails, tell the user to run `! az login` first, then retry.

### Step 2b: API key

**IMPORTANT:** Never ask the user to paste the API key into the chat. Tell them to run the login command themselves — the key is entered securely via a hidden prompt (no echo).

Tell the user:

> Run this in the prompt (the `!` prefix runs it in your terminal so the key stays private):
>
> `! python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py login-apikey`
>
> If you don't have an API key yet, generate one at https://specs.awolve.ai/portal/settings

Then wait for them to confirm it worked before proceeding.

### Step 3: Verify

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py status
```

Then suggest `/specs-pull` to sync specs.
