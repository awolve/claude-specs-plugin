---
description: Update a backlog item's title, description, priority, or status
---

# /awolve-spec:backlog-update

Edit fields on an existing backlog item. Use this when the framing of an item has shifted, the priority has changed, or the status needs to advance without going through the portal.

## Instructions

Parse the user's argument. Expected forms:

- `<project> <item> <fields>` — explicit project + item ref + one or more fields
- `<item> <fields>` — use the configured project (only when one is configured)

Item references accept UUIDs or `#N` numeric form (with or without `#`).

At least one field flag is required: `--title`, `--description`, `--priority` (low|medium|high), `--status` (idea|planned|in_progress|completed|archived).

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-update <project-id> <item-id-or-#N> [--title T] [--description T] [--priority P] [--status S]
```

Examples:

```bash
# Reframe a stale item
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-update spec-service 14 --title "Edit/delete affordance for backlog items"

# Bump priority and mark in-progress
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-update spec-service 14 --priority high --status in_progress

# Replace the description
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-update spec-service 14 --description "Add backlog-update and backlog-delete to the CLI."
```

## Notes

- To reparent or toggle the epic flag, use `/awolve-spec:backlog-set-parent` instead — clearer error reporting and validation.
- To remove an item entirely, use `/awolve-spec:backlog-delete` (soft-delete).
- The server records each change in the audit log.
