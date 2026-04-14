---
description: Show full details of a single bug — description, severity, repro steps
---

# /view-bug

Fetch the full details of a single bug by its short number (the `#N` shown by `/awolve-spec:bugs`).

## Instructions

Parse the user's argument. Expected forms:

- `<bug-number>` — e.g. `5` or `#5`. Use the configured project if exactly one is in config; otherwise ask which project.
- `<project-id> <bug-number>` — explicit project.

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py view-bug <project-id> <bug-number>
```

Add `--json` if the user asks for machine-readable output.

Show the result. If the bug description contains a proposed fix, offer to apply it. Do not apply without confirmation.
