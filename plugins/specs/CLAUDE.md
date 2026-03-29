# Specs Plugin

Claude Code plugin that syncs spec files with the Awolve Spec Service (specs.awolve.ai).

## How it works

- **Session start hook** pulls the latest specs automatically
- **PostToolUse hook** detects when a spec file is written/edited and pushes changes
- **Commands** (`/specs-pull`, `/specs-login`, `/specs-status`) for manual control

## Configuration files

Two config files, different purposes:

- **`.claude/specs.md`** — Committed to git. Shared config for all team members. Use for client repos where everyone has the same paths.
- **`.claude/specs.local.md`** — NOT committed (.gitignore). Personal override for machine-specific paths. Overrides specs.md entirely when present.

Resolution: `specs.local.md` > `specs.md`. Only one is used, never merged.

## Project structure

- `.claude-plugin/plugin.json` — Plugin manifest
- `hooks/` — Hook definitions (SessionStart, PostToolUse)
- `commands/` — Slash commands (/specs-pull, /specs-login, /specs-status)
- `skills/` — Skill trigger description
- `scripts/` — Python 3 scripts (no external dependencies)

## Development

```bash
python3 scripts/sync.py --help
python3 scripts/auth.py status
python3 scripts/config.py  # (no CLI, imported by sync.py)
```
