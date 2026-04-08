---
name: specs-delete-feature
description: Delete a feature and all its documents
argument-hint: [project-id] [feature-name]
---

# /awolve-spec:delete-feature

Delete a feature and all its documents from both the local filesystem and the spec service.

## Instructions

**Always confirm with the user before deleting.** List the documents that will be deleted and ask for confirmation.

If the user didn't provide all arguments, ask:
1. Which project?
2. Which feature to delete?

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py delete-feature <project-id> <feature-name>
```

This is a hard delete — the feature, all its documents, version history, comments, and reviews are permanently removed.

**Always suggest archiving first** (via `/awolve-spec:set-status <project/feature> archived`) as a non-destructive alternative.
