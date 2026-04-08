---
description: Write design.md for a feature — how to build it
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion]
argument-hint: [project/feature-name]
---

# /awolve-spec:design

Write `design.md` for a feature. This is the core spec document — every spec has one. Describes how the feature will be built: architecture, components, interfaces, key decisions.

## Instructions

### 1. Resolve project and feature

The user's argument "$ARGUMENTS" may contain a project name, feature name, or both (as `project/feature-name`).

If no argument given, look for an existing feature folder that has `requirements.md` but no `design.md`. If multiple candidates, ask the user.

Find the specs path and feature folder. If the feature folder doesn't exist, determine the next spec number and create it (same as `/awolve-spec:req`).

### 2. Read existing context

If `requirements.md` exists in the feature folder, read it — the design must address all requirements.

Research the codebase to understand the current architecture and how this feature fits in.

### 3. Discuss design with the user

Use AskUserQuestion to clarify:
- Are there specific technical constraints or preferences?
- Any components or patterns to reuse?
- Known risks or concerns?

### 4. Write design.md

Create `${SPEC_DIR}/{NNN}-{feature-name}/design.md`:

```markdown
# {Feature Name} — Design

## Overview

[High-level summary of the technical approach — 2-3 sentences]

## Architecture

[How this fits into the existing system]

## Components

### [Component 1]
- **Purpose:** [What it does]
- **Location:** [Where it lives]
- **Interface:** [How it's used]

### [Component 2]
...

## Data Models

[New types, interfaces, or schema changes needed]

## Key Decisions

### Decision: [Title]
**Context:** [Why this decision was needed]
**Options:**
1. [Option A] — Pros: [...] / Cons: [...]
2. [Option B] — Pros: [...] / Cons: [...]
**Chosen:** [Which option and why]

## Error Handling

[How errors will be handled]

## Testing Strategy

[How this will be tested]
```

Adapt the template to the feature — not every section applies to every feature. Skip sections that don't add value. Add sections that are needed but not in the template.

### 5. Register and push

If this is a new feature (folder didn't exist before), register it in the spec service:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py create-feature <project-id> <feature-name>
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py create-doc <project-id> <feature-name> design.md
```

Then re-read the file to pick up the sync frontmatter that was added. The PostToolUse hook will handle pushes from here.

If the feature already exists but the document is new (no spec_doc_id frontmatter), register just the document:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py create-doc <project-id> <feature-name> design.md
```

If the file already has sync frontmatter, the PostToolUse hook handles the push automatically.

### 6. Stop

Tell the user:

```
Design written: {path to design.md}

Next steps:
- If this feature touches infrastructure, run `/awolve-spec:infra` to detail the infra changes
- Otherwise, run `/awolve-spec:plan` to create the implementation plan
- Or get the design reviewed on the spec portal first
```

Do NOT proceed to write plan.md. Each phase is a separate invocation.
