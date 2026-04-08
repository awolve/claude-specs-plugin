---
description: Document work after the fact — create design.md (and optionally plan.md) from what was built
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion]
argument-hint: [project/feature-name]
---

# /awolve-spec:retro

Document work that was already done. Creates `design.md` (always) and optionally `plan.md` with tasks checked off as a record of what was built.

Never creates `requirements.md` — fabricating requirements after the fact adds no value.

## Instructions

### 1. Resolve project and feature

The user's argument "$ARGUMENTS" may contain a project name, feature name, or both.

If no argument given, ask the user what they just built.

Find the specs path for the project. Determine the next spec number and create the feature folder.

### 2. Understand what was built

Analyze recent work:

```bash
git log --oneline -20
git diff HEAD~5 --stat
```

Ask the user to confirm or clarify:
- What did you build?
- Any key decisions worth recording?

### 3. Write design.md

Create `design.md` documenting what was built — architecture, components, key decisions. Follow the same format as `/awolve-spec:design` but written in past tense (what was built, not what will be built).

### 4. Optionally write plan.md

If the work had distinct phases worth documenting, create `plan.md` with tasks already checked off:

```markdown
# {Feature Name} — Plan

## Approach

[What was done and in what order]

## Tasks

- [x] 1. [What was done first]
- [x] 2. [What was done next]
- [x] 3. [What was done last]
```

Skip `plan.md` if the work was straightforward enough that a task list adds nothing.

### 5. Bootstrap and push

```bash
python3 scripts/bootstrap-specs.py <project-id> <specs-path>
```

### 6. Done

Tell the user:

```
Retro-spec created: {path to feature folder}
  - design.md [+ plan.md if created]
```
