---
description: Update the awolve-open-claude-plugins marketplace (awolve-spec / awolve-cortex / hookify) and reload the session
---

# /awolve-spec:update-plugins

Refresh the `awolve-open-claude-plugins` marketplace (from `awolve/open-claude-plugins`) so new versions of the awolve-spec, awolve-cortex, and hookify plugins become available locally, then prompt the user to reload the session.

> **Scope note:** this command does NOT cover `awolve-marketplace` (cortex / admin / developer / general plugins). For those, run `/update-awolve-plugins`. `/cortex-update` runs both.

## Instructions

```bash
claude plugin marketplace update awolve-open-claude-plugins
```

Report how many plugins got bumped in the marketplace.

## After the Update

Tell the user to run `/reload-plugins` in their current session to pick up the new versions without restarting Claude Code. Phrase it as a direct instruction — slash commands have to be invoked by the user, not by Claude.

If zero plugins were bumped, say so plainly and skip the reload suggestion.
