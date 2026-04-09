# Awolve Spec Plugin

Claude Code plugin for spec-driven development with the [Awolve Spec Service](https://specs.awolve.ai).

## What it does

- **Auto-pulls** latest spec files when you start a Claude Code session
- **Auto-pushes** spec changes when you edit a spec file
- Keeps local spec files in sync so Claude Code always has the latest context

## Install

Run these as slash commands inside Claude Code:

```
/plugin marketplace add awolve/open-claude-plugins
/plugin install awolve-spec@awolve-open-claude-plugins
/reload-plugins
```

## Update

```
/plugin marketplace update awolve-open-claude-plugins
```

## Setup

1. **Login** — run `/awolve-spec:login` in Claude Code (Azure CLI or API key)
2. **Configure project** — create `.claude/specs.md` (shared) or `.claude/specs.local.md` (personal override):

```yaml
---
service_url: https://specs.awolve.ai
projects:
  - id: my-project
    path: ./specs
---
```

3. **Done** — specs will sync automatically on each session

## Commands

Run `/awolve-spec:help` for the full list, or see below:

### Setup & Sync

| Command | Description |
|---------|-------------|
| `/awolve-spec:login` | Authenticate (Azure CLI or API key) |
| `/awolve-spec:status` | Show sync status and auth info |
| `/awolve-spec:pull` | Pull latest spec files |

### Spec Writing

| Command | Description |
|---------|-------------|
| `/awolve-spec:req` | Write requirements.md — what to build and why |
| `/awolve-spec:design` | Write design.md — how to build it |
| `/awolve-spec:plan` | Write plan.md — implementation approach and task breakdown |
| `/awolve-spec:infra` | Enrich design.md with infrastructure specifications |
| `/awolve-spec:retro` | Document work after the fact from what was built |

### Features & Documents

| Command | Description |
|---------|-------------|
| `/awolve-spec:list-features` | List all features in a project |
| `/awolve-spec:create-feature` | Create a new feature |
| `/awolve-spec:rename-feature` | Rename a feature |
| `/awolve-spec:delete-feature` | Delete a feature and all its documents |
| `/awolve-spec:create-doc` | Add a document to an existing feature |
| `/awolve-spec:rename-doc` | Rename a document |
| `/awolve-spec:delete-doc` | Delete a document |
| `/awolve-spec:set-status` | Change feature or document status |

### Backlog & Bugs

| Command | Description |
|---------|-------------|
| `/awolve-spec:backlog` | List backlog items |
| `/awolve-spec:backlog-add` | Add a new idea or feature request |
| `/awolve-spec:bugs` | List open bugs |
| `/awolve-spec:bug` | Report a new bug |

## How it works

- **SessionStart hook** — pulls latest specs from the service, writes them to configured paths with version metadata in YAML frontmatter
- **PostToolUse hook** — detects edits to spec files, pushes changes as new versions with optimistic locking (409 on conflict)
- **No dependencies** — pure Python 3 stdlib, works everywhere
