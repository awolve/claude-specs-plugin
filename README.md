# Awolve Specs Plugin

Claude Code plugin for syncing spec files with [Awolve Spec Service](https://specs.awolve.ai).

## What it does

- **Auto-pulls** latest spec files when you start a Claude Code session
- **Auto-pushes** spec changes when you edit a spec file
- Keeps local spec files in sync so Claude Code always has the latest context

## Install

Run these as slash commands inside Claude Code:

```
/plugin marketplace add awolve/claude-specs-plugin
/plugin install specs@specs-marketplace
/reload-plugins
```

## Setup

1. **Generate API key** — go to [specs.awolve.ai/portal/settings](https://specs.awolve.ai/portal/settings) and generate a key
2. **Login** — run `/specs-login` in Claude Code and paste your API key
3. **Configure project** — create `.claude/specs.local.md` in your project root:

```yaml
---
project: my-project
specs_path: ./specs
service_url: https://specs.awolve.ai
---
```

3. **Done** — specs will sync automatically on each session

## Commands

| Command | What |
|---------|------|
| `/specs-pull` | Manually pull latest spec files |
| `/specs-login` | Authenticate with the spec service |
| `/specs-status` | Show sync status of local spec files |

## How it works

- **SessionStart hook** — pulls latest specs from the service, writes them to `specs_path` with version metadata in YAML frontmatter
- **PostToolUse hook** — detects edits to spec files, pushes changes as new versions with optimistic locking (409 on conflict)
- **No dependencies** — pure Python 3 stdlib, works everywhere
