---
name: bugs
description: List open bugs for a project
---

# /bugs

List open bugs for a project.

## Instructions

First determine which project to show bugs for. If the user specifies one, use it. Otherwise:
- Check the specs config for configured projects
- If only one project, use that
- If multiple, ask which one

Then run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py bugs <project-id>
```

Show the results. If there are critical or high severity bugs, highlight them.

Also mention that bugs can be viewed in the portal at `specs.awolve.ai/portal/<project>/bugs`.
