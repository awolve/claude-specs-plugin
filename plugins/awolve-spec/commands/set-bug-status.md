---
description: Change a bug's status (open, triaged, in_progress, resolved, closed)
---

# /set-bug-status

Update a bug's status by its short number.

## Instructions

Parse the user's argument. Expected forms:

- `<bug-number> <status>` — e.g. `5 resolved`. Use the configured project if exactly one is in config; otherwise ask which project.
- `<project-id> <bug-number> <status>` — explicit project.

Valid statuses: `open`, `triaged`, `in_progress`, `resolved`, `closed`.

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py set-bug-status <project-id> <bug-number> <status>
```

After closing a bug, remind the user to commit and push the actual fix if they haven't — the status change is just bookkeeping.
