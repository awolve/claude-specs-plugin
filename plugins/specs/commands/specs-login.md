---
name: specs-login
description: Authenticate with the Awolve Spec Service
---

# /specs-login

Authenticate with the Awolve Spec Service so specs can be synced.

## Instructions

### Default: Azure CLI (for Awolve users)

Just run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py login-azure
```

This auto-detects Azure CLI, fetches a token, and configures auto-refresh. Tokens refresh automatically on each API call — no expiry.

If it fails, tell the user to run `az login` first (or `! az login` in Claude Code).

### Alternative: API key (for external users)

If the user doesn't have Azure CLI, they need an API key. They can generate one at https://specs.awolve.ai/portal/settings (log in first, then click "Generate API key"). Ask them for it, then:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py login "<api-key>" "<email>" "https://specs.awolve.ai"
```

### Verify

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py status
```

Then suggest `/specs-pull` to sync specs.
