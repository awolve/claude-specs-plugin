---
description: Write plan.md for a feature — implementation approach and task breakdown
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion]
argument-hint: [project/feature-name]
---

# /spec plan

Write `plan.md` for a feature. Covers the implementation approach, sequencing, task breakdown, and dependencies. Use this when the feature is complex enough to need a structured implementation plan.

## Instructions

### 1. Resolve project and feature

The user's argument "$ARGUMENTS" may contain a project name, feature name, or both.

Find the feature folder. It must have a `design.md` — if it doesn't, tell the user to run `/spec design` first.

### 2. Read existing context

Read all existing spec files in the feature folder:
- `requirements.md` (if present) — what needs to be built
- `design.md` (required) — how it will be built

### 3. Write plan.md

Create `${SPEC_DIR}/{NNN}-{feature-name}/plan.md`:

```markdown
# {Feature Name} — Plan

## Approach

[Brief implementation strategy — what order, why that order, key sequencing decisions. 2-4 sentences.]

## Tasks

- [ ] 1. [Phase or major component]
  - [ ] 1.1 [Specific task]
    - Files: [files to create/modify]
  - [ ] 1.2 [Specific task]
    - Files: [files to create/modify]

- [ ] 2. [Next phase]
  - [ ] 2.1 [Task]
  ...

## Dependencies

- [External dependencies to install]
- [APIs or services to set up]
- [Other teams or repos involved]
```

**Task guidelines:**
- Each leaf task should be a few hours of work at most
- Tasks should produce testable results
- Include file paths for clarity
- Order tasks so each builds on the previous

Adapt the template — if dependencies aren't relevant, skip that section. If phases don't make sense for this feature, use a flat task list.

### 4. Register and push

If the document is new (no spec_doc_id frontmatter), register it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/sync.py create-doc <project-id> <feature-name> plan.md
```

Then re-read the file to pick up the sync frontmatter. The PostToolUse hook handles pushes from here.

If the file already has sync frontmatter, the PostToolUse hook handles the push automatically.

### 5. Stop

Tell the user:

```
Plan written: {path to plan.md}

Ready to implement. Start with task 1.1.
```
