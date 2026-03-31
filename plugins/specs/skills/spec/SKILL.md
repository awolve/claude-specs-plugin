---
name: specs:spec
description: Spec-driven development — create, sync, and manage spec documents. Use when the user mentions specs, wants to create a spec, work on specs, read specs, edit specs, plan a feature, or discuss feature specifications.
---

# Specs Plugin

Spec-driven development workflow and sync with the Awolve Spec Service (specs.awolve.ai).

## Spec-driven development

If you're going to spec it, spec it properly. There is one spec format with three canonical files — use the ones that make sense for the feature.

### Canonical files

| File | Purpose | When to use |
|------|---------|-------------|
| `requirements.md` | What to build and why | When stakeholders need to approve the what |
| `design.md` | How to build it | Always — minimum viable spec |
| `plan.md` | Implementation breakdown | When the build needs a task breakdown |

These are the only spec document names. Other files in the folder are supporting material (diagrams, schemas) — only valid if referenced by one of the three.

### Commands — spec creation

| Command | What it does |
|---------|-------------|
| `/spec requirements` | Write `requirements.md` — push to service — stop for review |
| `/spec design` | Write `design.md` — push — stop for review |
| `/spec infra` | Enrich `design.md` with infrastructure details (SIGL-inspired) |
| `/spec plan` | Write `plan.md` — push — ready to implement |
| `/retro-spec` | Document work after the fact (`design.md` + optional `plan.md`) |

Each phase is a separate command invocation. Do not write multiple spec files in one session unless the user explicitly asks.

### Flows

**Stakeholder-driven:** requirements → review → design → review → (infra) → plan → review → implement
**Self-directed:** design → (infra) → plan → implement
**Small feature:** design → implement
**No spec:** build it → optionally `/retro-spec`

### Commands — sync and management

- `/specs-pull` — Pull latest spec files from the service
- `/specs-login` — Authenticate with the spec service
- `/specs-status` — Show sync status of local spec files
- `/specs-set-status` — Change feature or document status
- `/backlog` — List backlog items
- `/backlog-add` — Add a backlog item
- `/bugs` — List bugs
- `/bug` — Report a bug

## Important: Always pull before reading specs

**Before reading or working with spec files, always run `/specs-pull` first** to ensure you have the latest versions. The SessionStart hook handles this for new sessions, but mid-session you must pull manually.

Do not assume local spec files are current — pull first, then read.

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
