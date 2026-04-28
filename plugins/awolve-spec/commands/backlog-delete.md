---
description: Soft-delete a backlog item (cascades to children)
---

# /awolve-spec:backlog-delete

Remove a backlog item from the active list. The deletion is a **soft-delete** — the row stays in the database with `deletedAt` set and the audit log records who deleted it. An admin can restore via the API if needed.

If the item is an **epic** with active children, the server cascades the soft-delete to all children in the same transaction and writes a single audit event listing the affected ids.

## Instructions

Parse the user's argument. Expected forms:

- `<project> <item>` — explicit project + item ref
- `<item>` — use the configured project (only when one is configured)

References accept UUIDs or `#N` numeric form (with or without `#`).

**Confirm before running.** This is a destructive action visible in the portal and audit log. Show the user the title and child count (if it's an epic) and ask for confirmation. Only proceed once they say yes.

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-delete <project-id> <item-id-or-#N>
```

Examples:

```bash
# Delete a single item
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-delete spec-service 14

# Delete an epic (children cascade)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-delete spec-service 7
```

## Notes

- For "no longer relevant" without losing the trace, prefer `/awolve-spec:backlog-update --status archived` over deletion.
- Hard delete is intentionally not exposed — keep the audit trail.
