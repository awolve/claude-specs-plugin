---
name: specs-rename-doc
description: Rename a document
argument-hint: [file-path] [new-filename]
---

# /awolve-spec:rename-doc

Rename a spec document file and update the spec service record.

## Instructions

If the user didn't provide all arguments, ask:
1. Which file to rename? (path to the .md file)
2. What's the new filename?

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py rename-doc <file-path> <new-filename>
```

The `spec_doc_id` is preserved — only the filename changes in both the filesystem and the service.

**Note:** This requires the document rename endpoint on the spec service. If it returns an error, the endpoint may not be deployed yet.
