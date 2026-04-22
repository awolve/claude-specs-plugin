---
description: Set or clear the parent (epic) of a backlog item
---

# /awolve-spec:backlog-set-parent

Reparent a backlog item. The item becomes a child of the given epic, or top-level if you pass `none`.

## Instructions

Parse the user's argument. Expected forms:

- `<project> <item> <parent>` — explicit project + both refs
- `<item> <parent>` — use the configured project (only one)

References accept UUIDs or `#N` numeric form (with or without `#`). `none` (or `null`) as the parent reference clears the existing parent.

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-set-parent <project-id> <item-id-or-#N> <parent-id-or-#N|none>
```

Examples:

```bash
# Make item #7 a child of #4 (turning #4 into an epic if it wasn't already)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-set-parent my-project 7 4

# Detach #7 from its parent (back to top-level)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-set-parent my-project 7 none
```

## Errors the API returns

- `parent_not_found` — referenced parent doesn't exist or is soft-deleted
- `parent_wrong_project` — parent belongs to a different project
- `parent_must_be_top_level` — parent itself has a parent; only one level of nesting allowed
- `parent_not_an_epic` — referenced item exists but isn't marked as an epic. Mark it as an epic first via the portal modal or by recreating with `--epic`.
- `parent_self_reference` — trying to make an item its own parent
- `epic_has_children` — trying to demote an item (set `parentId`) that itself has children — would create a 2-level chain. Detach the children first.
- `child_cannot_be_epic` — trying to mark an item as an epic while it still has a parent. Clear its parent first.
- `epic_cannot_have_parent` — trying to give a parent to an existing epic. Demote it first by toggling `isEpic` off.

## When to use this

- Restructuring a backlog: pulling related top-level items under a new epic
- Detaching a child after it's been promoted to a feature spec
- Reorganizing after a planning conversation

For new items, prefer creating them with `--parent` directly via `/awolve-spec:backlog-add` rather than creating then reparenting.
