# Specs Sync Skill

This plugin syncs spec documents between the local filesystem and the Awolve Spec Service (specs.awolve.ai).

## When to use

- When the user mentions specs, spec files, or spec documents
- When working on features that have spec documents
- When the user wants to see the latest version of a spec
- When the user edits a spec file and it needs to be pushed upstream

## Commands

- `/specs-pull` — Pull latest spec files from the service
- `/specs-login` — Authenticate with the spec service
- `/specs-status` — Show sync status of local spec files

## How it works

Spec files are synced from the spec service. Each synced file has YAML frontmatter with `spec_version`, `spec_doc_id`, and `last_synced`. On session start, latest specs are pulled. When you edit a spec file, it is automatically pushed.

## Configuration

**IMPORTANT:** There are two config files with different purposes:

| File | Purpose | Committed to git? |
|------|---------|-------------------|
| `.claude/specs.md` | Shared project config — same for all team members | Yes |
| `.claude/specs.local.md` | Personal override — machine-specific paths | No (.gitignore) |

**Resolution order:** `specs.local.md` takes priority over `specs.md`. If `specs.local.md` exists, `specs.md` is ignored entirely.

### When to use which

**Use `.claude/specs.md` (committed) when:**
- Setting up a project repo — all devs share the same config
- The paths are the same for everyone (e.g. `./specs`)
- You want new team members to have config automatically after cloning

**Use `.claude/specs.local.md` (personal) when:**
- Paths are machine-specific (e.g. pointing to shared file storage)
- You need to override the committed config for your setup
- Testing or temporary config changes

### Config format

```yaml
---
service_url: https://specs.awolve.ai
projects:
  - id: project-name
    path: ./specs
---
```

Multi-project example:

```yaml
---
service_url: https://specs.awolve.ai
projects:
  - id: my-service
    path: path/to/my-service/specs
  - id: client-project
    path: path/to/client-project/specs
---
```

### Helping users set up config

When a user needs to set up specs config:

1. **Check if `.claude/specs.md` already exists** — if so, it may already work
2. **For single-project repos:** Create `.claude/specs.md` (committed) with `path: ./specs`
3. **For multi-project repos:** Create `.claude/specs.md` (committed) with appropriate paths
4. **Only create `.claude/specs.local.md`** if the user has a machine-specific path override
5. **Never create both** unless the user explicitly needs a personal override

Authentication is stored in `~/.claude-specs/auth.json` (per-machine, created by `/specs-login`).
