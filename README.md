# Awolve Specs Plugin

Claude Code plugin for syncing spec files with [Awolve Spec Service](https://specs.awolve.ai).

## What it does

- **Auto-pulls** latest spec files when you start a Claude Code session
- **Auto-pushes** spec changes when you edit a spec file
- Keeps local spec files in sync so Claude Code always has the latest context

## Install

Run these as slash commands inside Claude Code:

```
/plugin marketplace add awolve/open-claude-plugins
/plugin install specs@awolve-open-claude-plugins
/reload-plugins
```

## Update

```
/plugin marketplace update awolve-open-claude-plugins
```

## Setup

1. **Login** — run `/specs-login` in Claude Code (Azure CLI or API key)
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

| Command | What |
|---------|------|
| `/specs-pull` | Pull latest spec files |
| `/specs-login` | Authenticate (Azure CLI or API key) |
| `/specs-status` | Show sync status |
| `/specs-create-feature` | Create a new feature |
| `/specs-create-doc` | Add a document to a feature |
| `/specs-list-features` | List features in a project |
| `/specs-set-status` | Change feature or document status |
| `/specs-rename-feature` | Rename a feature |
| `/specs-rename-doc` | Rename a document |
| `/specs-delete-feature` | Delete a feature and all documents |
| `/specs-delete-doc` | Delete a document |
| `/spec requirements` | Write requirements.md for a feature |
| `/spec design` | Write design.md for a feature |
| `/spec infra` | Enrich design.md with infrastructure details |
| `/spec plan` | Write plan.md — implementation breakdown |
| `/retro-spec` | Document work after the fact |
| `/bugs` | List open bugs |
| `/bug` | Report a bug |
| `/backlog` | List backlog items |
| `/backlog-add` | Add a backlog item |

## How it works

- **SessionStart hook** — pulls latest specs from the service, writes them to configured paths with version metadata in YAML frontmatter
- **PostToolUse hook** — detects edits to spec files, pushes changes as new versions with optimistic locking (409 on conflict)
- **No dependencies** — pure Python 3 stdlib, works everywhere
