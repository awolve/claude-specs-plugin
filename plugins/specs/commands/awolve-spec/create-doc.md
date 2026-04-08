---
name: specs-create-doc
description: Add a document to an existing feature
argument-hint: [project-id] [feature-name] [filename]
---

# /awolve-spec create-doc

Add a new document to an existing feature, registered in the spec service with sync frontmatter.

## Instructions

If the user didn't provide all arguments, ask:
1. Which project?
2. Which feature? (list folders in specs path if needed)
3. What filename? (e.g. `design.md`, `requirements.md`, `plan.md`)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py create-doc <project-id> <feature-name> <filename>
```

The file is created locally with sync frontmatter. If the file already exists without frontmatter, frontmatter is added. From this point, the PostToolUse hook handles auto-push on edits.
