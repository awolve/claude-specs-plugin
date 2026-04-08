---
description: Add a new idea or feature request to the project backlog
---

# /awolve-spec:backlog-add

Add a new backlog item (idea, feature request) to a project.

## Instructions

First determine which project to add the item to. If the user specifies one, use it. Otherwise:
- Check the specs config for configured projects
- If only one project, use that
- If multiple, ask which one

Ask the user for:
- **Title** (required) — short description of the idea
- **Description** (optional) — more detail about what and why
- **Priority** (optional, default: medium) — low, medium, or high

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog-add <project-id> "<title>" "<description>" <priority>
```

Confirm the item was created. Mention they can promote it to a full spec later from the portal.
