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

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync.py bug "<project-id>" "<title>" "<description>" "<severity>"
```

After creating, show the bug number and portal link.

If the user describes a bug in conversation without explicitly running /bug, you can offer to file it as a bug report.
