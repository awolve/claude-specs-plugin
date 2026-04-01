---
name: specs-delete-doc
description: Delete a document
argument-hint: [file-path]
---

# /specs-delete-doc

Delete a spec document from both the local filesystem and the spec service.

## Instructions

**Always confirm with the user before deleting.** Show the file path and ask for confirmation.

If the user didn't provide a file path, ask which document to delete.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync.py delete-doc <file-path>
```

This is a hard delete — the document, its version history, comments, and reviews are permanently removed.

Suggest archiving the feature (via `/specs-set-status`) as an alternative if the user wants to keep history.
