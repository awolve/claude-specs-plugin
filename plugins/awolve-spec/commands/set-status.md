---
description: Change the status of a feature or document
---

# /awolve-spec:set-status

Change the status of a feature or document in the spec service.

## Instructions

Ask the user what they want to update:

1. **Feature status** — which feature and what status?
   - Valid statuses: `idea`, `specifying`, `in_progress`, `completed`, `archived`

2. **Document status** — which document and what status?
   - Valid statuses: `specifying`, `ready`, `approved`

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py set-status <feature-or-doc-id> <status>
```

If the user refers to a spec by name (e.g. "mark 001-statistics as completed"), look up the feature ID from the config and local files.

If the user wants to change a document status, use the doc ID from the file's frontmatter (`spec_doc_id`).

Show the updated status after the change.
