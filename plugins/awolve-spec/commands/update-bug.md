---
description: Update a bug's title, description, or severity
---

# /awolve-spec:update-bug

Edit fields on an existing bug. Use this when the original framing has been overtaken by what actually shipped, or when triage uncovers a different severity than the reporter assigned.

## Instructions

Parse the user's argument. Expected forms:

- `<project> <bug-number> <fields>` — explicit project + bug ref + one or more field flags
- `<bug-number> <fields>` — use the configured project (only when exactly one is in config)

Bug references accept the short numeric form (with or without `#`).

At least one field flag is required: `--title`, `--description`, `--severity` (low|medium|high|critical).

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py update-bug <project-id> <bug-number> [--title T] [--description T] [--severity S]
```

Examples:

```bash
# Correct a stale description after the fix took a different shape than the original "Proposed fix"
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py update-bug myoffice 1 --description "Reverted to plain-text default; HTML opt-in via --html. See <commit-sha>."

# Bump severity after triage
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py update-bug spec-service 15 --severity high

# Tighten the title
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py update-bug spec-service 15 --title "Add update-bug and bug-comment commands to specs-cli"
```

## Notes

- For status changes use `/awolve-spec:set-bug-status` — it emits a dedicated `status_change` audit event.
- To attach resolution context (commit SHA, rollout notes) without rewriting the description, prefer `/awolve-spec:bug-comment` so the original report stays intact.
- Each change is recorded in the audit log.
