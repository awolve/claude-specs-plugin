---
name: backlog
description: List backlog items for a project
---

# /awolve-spec backlog

List backlog items (ideas, feature requests) for a project.

## Instructions

First determine which project to show backlog for. If the user specifies one, use it. Otherwise:
- Check the specs config for configured projects
- If only one project, use that
- If multiple, ask which one

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py backlog <project-id>
```

Show the results. Highlight high-priority items.

Also mention that backlog items can be viewed and managed in the portal at `specs.awolve.ai/portal/<project>` under the Backlog tab.
