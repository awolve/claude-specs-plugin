---
description: Set or clear a feature's short description
argument-hint: [feature-id] [text]
---

# /awolve-spec:set-description

Set or clear a feature's `shortDescription` — the one or two sentence summary shown on the portal feature list.

## Instructions

If the user didn't provide arguments, ask:
1. Which feature? (format: `project-id/001-feature-name`)
2. What should the description be? (pass an empty string to clear)

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py set-description <feature-id> "<text>"
```

If the user refers to a feature by name (e.g. "update 002-user-roles"), resolve the project from config and local files to get the full `project-id/feature-name` ID.
