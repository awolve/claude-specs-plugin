---
description: List comments on a bug
---

# /awolve-spec:bug-comments

List the comment thread on a bug, oldest first. Use this to see resolution context and triage discussion attached to a bug record.

## Instructions

Parse the user's argument. Expected forms:

- `<project> <bug-number>` — explicit project + bug ref
- `<bug-number>` — use the configured project (only when exactly one is in config)

Bug references accept the short numeric form (with or without `#`). Add `--json` if the user asks for machine-readable output.

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py bug-comments <project-id> <bug-number> [--json]
```

Examples:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py bug-comments spec-service 15
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py bug-comments spec-service 15 --json
```

## Notes

- To add a new comment, use `/awolve-spec:bug-comment`.
- To see the bug description and metadata alongside its comment count, use `/awolve-spec:view-bug` first.
