---
name: bug
description: Report a new bug
---

# /bug

Report a new bug for a project.

## Instructions

Gather these from the user:
1. **Project** — which project? Check config for options. If only one, use it.
2. **Title** — short summary of the bug (required)
3. **Description** — detailed description of what went wrong (required). Supports markdown.
4. **Severity** — low, medium (default), high, or critical
5. **Screenshots** — if the user pasted a screenshot in the conversation, save it to a temp file and attach it

To attach images, use `--attach`:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync.py bug "<project-id>" "<title>" "<description>" "<severity>" --attach /path/to/screenshot.png
```

Multiple images: add `--attach <path>` for each one. Images are base64-encoded into the bug description.

If the user pastes a screenshot in the conversation:
1. The image is available as a file — check if it was saved to a temp path
2. If so, attach it with `--attach`
3. If not available as a file, mention that screenshots can be added via the portal

After creating, show the bug number and portal link.
