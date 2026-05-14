---
description: Update a feature's display title without renaming the slug
argument-hint: [feature-id] [text]
---

# /awolve-spec:set-title

Update a feature's display `title` — the human-readable name shown on the portal feature list and detail header. Use this when the slug is correct but the title needs a touch-up (e.g. fixing the every-word-capitalized output of the auto-derivation that runs during rename).

## Instructions

If the user didn't provide arguments, ask:
1. Which feature? (format: `project-id/001-feature-name`)
2. What should the new title be?

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py set-title <feature-id> "<text>"
```

If the user refers to a feature by name (e.g. "update 002-user-roles"), resolve the project from config and local files to get the full `project-id/feature-name` ID.

## Notes

- To rename the slug (folder name) as well, use `/awolve-spec:rename-feature` instead — that updates both `name` and `title` in one round trip.
- An empty title is rejected — pass non-empty text. There's no "clear" path because every feature must have a title.
- The audit log records this as a `feature.update` event (the lookup PATCH route emits one when only the title changes).
