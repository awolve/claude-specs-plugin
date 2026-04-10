---
description: Upload a binary file as an attachment to a spec feature
argument-hint: <file-path> [<project-id>/<feature-name>]
---

# /awolve-spec:attach

Upload a local binary file (image, PDF, Excel, etc.) as an attachment to a spec feature. The file is stored in Azure Blob Storage via the spec service and mirrored back to every team member's local feature folder on the next `/awolve-spec:pull`.

## When to use

- You have a mockup, PDF, Excel, or other binary file that belongs to a spec feature and should be shared with the team
- You want the file to show up in the portal's "Supporting documents & files" section on the spec feature page
- The file already lives on disk (e.g. you dropped it into the feature folder) and you want it pushed to blob storage

## Instructions

Parse the `$ARGUMENTS`:

- **First arg** is the local file path (required). May be absolute or relative.
- **Second arg** (optional) is `<project-id>/<feature-name>`. If omitted, the feature is inferred from the file path (the file must live inside a configured specs directory, under a feature subfolder).

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py attach $ARGUMENTS
```

## Notes

- Max file size: 25 MB
- Any content type accepted (images render inline in the portal, other files download)
- Same file uploaded twice creates a duplicate — the server does not dedupe by name or content. Delete the old one via the portal if you want to replace it cleanly.
- On subsequent pulls (`/awolve-spec:pull`), all team members get the file synced to their local feature folder

If the user is not authenticated, tell them to run `/awolve-spec:login` first.
