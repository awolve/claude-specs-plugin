---
description: Write requirements.md for a feature — what to build and why
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion]
argument-hint: [project/feature-name]
---

# /spec requirements

Write `requirements.md` for a feature. Use this when stakeholders need to approve *what* gets built before design begins.

## Instructions

### 1. Resolve project and feature

The user's argument "$ARGUMENTS" may contain a project name, feature name, or both (as `project/feature-name`).

If no argument given, ask the user:
- Which project is this for?
- What's the feature name?

Find the specs path for the project. Check if:
- The project has a specs config in `.claude/specs.md` or `.claude/specs.local.md`
- The feature folder already exists

If the feature folder doesn't exist, determine the next spec number:

```bash
ls -d ${SPEC_DIR}/*/ 2>/dev/null | sort -V | tail -1
```

Create the folder: `${SPEC_DIR}/{NNN}-{feature-name}/`

### 2. Gather requirements

Use AskUserQuestion to gather:
- Who are the users of this feature?
- What problem does this solve?
- What are the key behaviors needed?
- What are the constraints?
- What is explicitly out of scope?

### 3. Write requirements.md

Create `${SPEC_DIR}/{NNN}-{feature-name}/requirements.md`:

```markdown
# {Feature Name} — Requirements

## Overview

[What this feature does and why it's needed — 2-3 sentences]

## User Stories

**As a** [user type]
**I want** [capability]
**So that** [value/benefit]

## Acceptance Criteria

1. WHEN [event] THEN system SHALL [response]
2. IF [precondition] THEN system SHALL [response]

## Edge Cases

- [Edge case 1]
- [Edge case 2]

## Constraints

- [Technical constraints]
- [Business constraints]

## Out of Scope

- [What this feature explicitly does NOT include]
```

### 4. Register and push

If this is a new feature (folder didn't exist before), register it in the spec service:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync.py create-feature <project-id> <feature-name>
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync.py create-doc <project-id> <feature-name> requirements.md
```

Then re-read the file to pick up the sync frontmatter that was added. The PostToolUse hook will handle pushes from here.

If the feature already exists but the document is new, register just the document:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync.py create-doc <project-id> <feature-name> requirements.md
```

If the file already has sync frontmatter, the PostToolUse hook handles the push automatically.

### 5. Stop

Tell the user:

```
Requirements written: {path to requirements.md}

Next step: get this reviewed on the spec portal. Once approved, run `/spec design` to write the design.
```

Do NOT proceed to write design.md or plan.md. The spec service gates progression between phases.
