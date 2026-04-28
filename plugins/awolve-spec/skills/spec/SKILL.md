---
name: awolve-spec:spec
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
| `/awolve-spec:req` | Write `requirements.md` — push to service — stop for review |
| `/awolve-spec:design` | Write `design.md` — push — stop for review |
| `/awolve-spec:infra` | Enrich `design.md` with infrastructure details (SIGL-inspired) |
| `/awolve-spec:plan` | Write `plan.md` — push — ready to implement |
| `/awolve-spec:retro` | Document work after the fact (`design.md` + optional `plan.md`) |

Each phase is a separate command invocation. Do not write multiple spec files in one session unless the user explicitly asks.

### Flows

**Stakeholder-driven:** requirements → review → design → review → (infra) → plan → review → implement
**Self-directed:** design → (infra) → plan → implement
**Small feature:** design → implement
**No spec:** build it → optionally `/awolve-spec:retro`

### Commands — sync and management

- `/awolve-spec:pull` — Pull latest spec files from the service
- `/awolve-spec:login` — Authenticate with the spec service
- `/awolve-spec:status` — Show sync status of local spec files
- `/awolve-spec:set-status` — Change feature or document status
- `/awolve-spec:create-feature` — Create a new feature in a project
- `/awolve-spec:create-doc` — Add a document to an existing feature
- `/awolve-spec:rename-feature` — Rename a feature
- `/awolve-spec:rename-doc` — Rename a document
- `/awolve-spec:delete-doc` — Delete a document
- `/awolve-spec:delete-feature` — Delete a feature and all its documents
- `/awolve-spec:list-features` — List all features in a project
- `/awolve-spec:backlog` — List backlog items (tree by default; `--epics`, `--flat`, `--status`, `--priority` flags)
- `/awolve-spec:backlog-add` — Add a backlog item (`--parent <id-or-#N>` nests under an epic, `--epic` creates an empty epic placeholder)
- `/awolve-spec:backlog-set-parent` — Reparent an existing backlog item (or pass `none` to clear)
- `/awolve-spec:backlog-update` — Update title/description/priority/status on an existing item
- `/awolve-spec:backlog-delete` — Soft-delete an item (cascades to children if it's an epic)
- `/awolve-spec:bugs` — List open bugs for a project
- `/awolve-spec:view-bug` — Show full details of a single bug (description, severity, repro)
- `/awolve-spec:bug` — Report a new bug
- `/awolve-spec:set-bug-status` — Change a bug's status (open/triaged/in_progress/resolved/closed)

## specs-cli.py reference

Most slash commands wrap `${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py`. When a slash command does not exist for what you need, call the CLI directly — don't grep the script source and don't reach for the raw HTTP API. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py --help` to confirm.

Full subcommand surface:

| Subcommand | Purpose |
|------------|---------|
| `pull [project-id] [--prune\|--keep] [--force-full]` | Pull latest specs |
| `push <file-path>` | Push a single spec file |
| `status` | Show sync status of local spec files |
| `log <project-id\|--all> [--since DUR] [--json] [--since-last-visit] [--mark-read]` | Audit log stream |
| `set-status <id> <status>` | Change feature or document status |
| `set-description <feature-id> <text>` | Set or clear feature shortDescription |
| `create-feature <project-id> <name> [--status] [--description]` | Create feature (service auto-assigns the number — do NOT include a numeric prefix in `<name>`) |
| `create-doc <project-id> <feature-name> <filename>` | Add a document to a feature |
| `rename-feature <project-id> <old> <new>` | Rename feature folder + service |
| `rename-doc <file-path> <new-filename>` | Rename a document |
| `delete-doc <file-path>` | Delete a document |
| `delete-feature <project-id> <feature-name>` | Delete a feature and its docs |
| `list-features <project-id>` | List all features in a project |
| `list-docs <project-id> <feature-name>` | List all docs in a feature |
| `bugs <project-id>` | List open bugs (tabular summary only) |
| `view-bug <project-id> <bug-number> [--json]` | Full bug details |
| `bug <project-id> <title> <description> [severity] [--attach file ...]` | Report a bug |
| `set-bug-status <project-id> <bug-number> <status>` | Change bug status (open/triaged/in_progress/resolved/closed) |
| `comments <file-path>` / `comment <file-path> <body> [--inline --anchor <text>]` | Read / add comments |
| `resolve-comment <comment-id>` | Resolve a comment |
| `reviews <file-path>` / `review <file-path> <verdict> [body]` | Read / submit reviews |
| `versions <file-path>` / `save <file-path> <summary>` | Version history / snapshot |
| `backlog [project-id] [--epics\|--flat] [--status STATUS] [--priority PRIORITY]` | List backlog items. Default = tree view (epic head + indented children). `--epics` filters to items where `isEpic = true` (including empty epics); `--flat` ignores hierarchy. |
| `backlog-add <project-id> <title> [description] [priority] [--parent <id-or-#N>] [--epic]` | Add a backlog item. `--parent` nests it under an existing epic (parent must have `isEpic = true`); `--epic` creates the item as an epic placeholder. The two flags are mutually exclusive. |
| `backlog-set-parent <project-id> <item-id-or-#N> <parent-id-or-#N\|none>` | Reparent an item (or pass `none` to detach). Errors include `parent_not_an_epic`, `parent_must_be_top_level`, `epic_has_children`, `child_cannot_be_epic`. |
| `backlog-update <project-id> <item-id-or-#N> [--title T] [--description T] [--priority P] [--status S]` | Update fields on an existing item. At least one flag required. For parent/epic changes use `backlog-set-parent`. |
| `backlog-delete <project-id> <item-id-or-#N>` | Soft-delete an item. If the item is an epic, the server cascades to all active children in one transaction. Confirm with the user before calling — destructive and visible in the portal. |
| `service-status` | Health check |
| `attach <file-path> [<project-id>/<feature-name>]` | Upload binary attachment |

Service base URL lives in `~/.claude-specs/config.yaml` (`service_url`). The portal UI is `<service_url>/portal/<project>/...` — useful for linking a user to a resource.

### Conventions when calling the CLI directly

- Pass `--json` where available (`comments`, `reviews`, `versions`, `log`, `view-bug`) when you need to parse output.
- Never pass a numeric prefix to `create-feature <name>` — the service rejects it with HTTP 500 and auto-numbers the feature anyway.
- Feature identifiers in URLs and subcommand arguments are the folder name (e.g. `030-terminal-resume-session`), not the UUID.

### Backlog hierarchy (epics)

Backlog items can be organized into one level of nesting: an **epic** (`isEpic: true`, top-level only) holds zero or more **child items** (regular items with `parentId` pointing at the epic). Epics are opt-in and explicit — created via `--epic` on `backlog-add` or via the portal modal. Empty epics are valid placeholders. Children can only be nested under explicit epics (not arbitrary top-level items).

When the user asks you to add **multiple related items** in one go (e.g. "add tasks for the onboarding flow"), prefer creating an epic first via `backlog-add … --epic` and then adding the rest with `--parent <epic-#N>`. This gives them a tidy tree view in the portal Backlog tab. For one-off items, leave them top-level.

## Important: Always pull before reading specs

**Before reading or working with spec files, always run `/awolve-spec:pull` first** to ensure you have the latest versions. The SessionStart hook handles this for new sessions, but mid-session you must pull manually.

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

Authentication is stored in `~/.claude-specs/auth.json` (per-machine, created by `/awolve-spec:login`).

## Updating the plugin

```
/plugin marketplace update awolve-open-claude-plugins
```
