---
description: Create a new feature in a project
argument-hint: [project-id] [feature-name]
---

# /awolve-spec:create-feature

Create a new feature in a project, registered in both the local filesystem and the spec service.

## Instructions

If the user didn't provide arguments, ask:
1. Which project? (check `.claude/specs.md` or `.claude/specs.local.md` for configured projects)
2. What's the feature name? (kebab-case, e.g. `user-notifications`)

The script auto-assigns the next spec number (e.g. `004-user-notifications`).

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py create-feature <project-id> <feature-name> [--status STATUS] [--description TEXT]
```

Default status is `specifying`. Use `--status idea` for placeholder features.

Optional `--description "One or two sentences…"` sets the feature's short description (visible on the portal list view). Can also be set later via `/awolve-spec:set-description`.

After creation, suggest next steps:
- `/awolve-spec:req` to write requirements
- `/awolve-spec:design` to write the design doc
