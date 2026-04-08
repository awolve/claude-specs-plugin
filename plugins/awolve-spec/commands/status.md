---
name: specs-status
description: Show sync status of local spec files
---

# /awolve-spec:status

Show the sync status of local spec files and authentication.

## Instructions

Run these two commands:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py status
```

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/auth.py status
```

If not authenticated, suggest running `/awolve-spec:login`.

If no config found, explain the two config options:
- `.claude/specs.md` — committed, shared with the team. Use when paths are the same for everyone (e.g. `./specs` for external devs).
- `.claude/specs.local.md` — personal, not committed. Use when paths are machine-specific.

Only suggest `specs.local.md` if the user needs personal overrides. Default to `specs.md` for new setups.

## Gitignore checks (REQUIRED)

ALWAYS run these checks and fix issues without asking:

**1. Check specs.local.md:**
```bash
git check-ignore .claude/specs.local.md 2>/dev/null || echo "NOT_IGNORED"
```
If NOT_IGNORED: add `.claude/specs.local.md` to `.gitignore` immediately.

**2. Check all relative specs paths:**
Read the config file and for each project with a relative path (starts with `./` or doesn't start with `/` or `~`):
```bash
git check-ignore <path> 2>/dev/null || echo "NOT_IGNORED"
```
If NOT_IGNORED: add the path (e.g. `specs/`) to `.gitignore` immediately. Relative specs paths MUST be gitignored — they contain pulled files that should not be committed. Do not ask, just add them.

**3. After fixing:** Show what was added to `.gitignore`.
