---
name: specs-rename-feature
description: Rename a feature
argument-hint: [project-id] [old-name] [new-name]
---

# /specs-rename-feature

Rename a feature folder and update the spec service record.

## Instructions

If the user didn't provide all arguments, ask:
1. Which project?
2. Which feature to rename?
3. What's the new name?

The number prefix is preserved — only the name part changes (e.g. `003-old-name` becomes `003-new-name`).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync.py rename-feature <project-id> <old-name> <new-name>
```

**Note:** This requires the rename endpoint on the spec service. If it returns an error, the endpoint may not be deployed yet.
