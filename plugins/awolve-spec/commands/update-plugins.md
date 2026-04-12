---
description: Refresh the awolve-open-claude-plugins marketplace and reload the session
---

# /awolve-spec:update-plugins

Refresh the `awolve-open-claude-plugins` marketplace (from `awolve/open-claude-plugins`) so newer plugin versions become available locally, then prompt the user to reload the session.

> **Scope note:** this only covers `awolve-open-claude-plugins`. For `awolve-marketplace`, run `/update-awolve-plugins`. `/cortex-update` runs both.

## Instructions

```bash
claude plugin marketplace update awolve-open-claude-plugins
```

Report how many plugins got bumped in the marketplace.

## After the Update

Tell the user to run `/reload-plugins` in their current session to pick up the new versions without restarting Claude Code. Phrase it as a direct instruction — slash commands have to be invoked by the user, not by Claude.

If zero plugins were bumped, say so plainly and skip the reload suggestion.
