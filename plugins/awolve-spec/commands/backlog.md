---
description: List backlog items for a project (with optional view modes and filters)
---

# /awolve-spec:backlog

List backlog items (ideas, feature requests, todos) for a project. Spec 013 added one level of optional epic→child nesting and view modes.

## Instructions

Determine the project. If the user specifies one, use it; if exactly one project is configured, use that; otherwise ask.

Run with optional flags:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog <project-id> [--epics|--flat] [--status STATUS] [--priority PRIORITY]
```

### View modes (default: tree)

- **default (tree)** — items grouped by epic. Top-level items render at depth 0; their children appear indented underneath. Standalone items (no parent, no children) render at the top level too.
- **`--epics`** — show only items explicitly marked as epics (`isEpic = true`), including empty ones. Useful for a roadmap-level overview.
- **`--flat`** — flat list, no grouping (legacy behavior).

### Filters

- **`--status STATUS`** — only show items with this status (`idea`, `planned`, `in_progress`, `completed`, `archived`).
- **`--priority PRIORITY`** — only show items with this priority (`low`, `medium`, `high`).

The default view filters out `completed` and `archived` items so you see active work only. Pass `--status completed` to see them explicitly.

### Output format

Each row shows priority marker (`!!!` high, `!!` medium, `!` low), the item number (`#42`), the title, and the status. Epic rows are prefixed with `[EPIC]` and include a child status histogram inline; empty epics (no children yet) show `· (no items yet)`:

```
  [!!] #5 [EPIC] User onboarding · children: 2 idea · 1 in_progress · 3 completed
       in_progress
    [!!] #6 Email verification flow
         in_progress
    [!] #7 Welcome screen copy
         completed
  [!!] #8 [EPIC] Payments · (no items yet)
       idea
```

Highlight high-priority items. Mention that the same backlog can be viewed and managed in the portal at `specs.awolve.ai/portal/<project>` under the Backlog tab, with richer filtering, view-mode switching, and inline editing.
