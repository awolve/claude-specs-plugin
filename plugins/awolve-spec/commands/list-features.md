---
description: List all features in a project
argument-hint: [project-id]
---

# /awolve-spec:list-features

List all features in a project from the spec service.

## Instructions

If the user didn't provide a project ID, check the config for configured projects. If there's only one, use it. Otherwise ask which project.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py list-features <project-id>
```

Shows feature name, status, and document count for each feature.
