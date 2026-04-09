---
description: Show available awolve-spec commands and what they do
---

# /awolve-spec:help

Show a quick reference of all available awolve-spec commands.

## Instructions

Print the following command reference. Do NOT run any scripts — just display this information.

### Setup & Sync
| Command | Description |
|---------|-------------|
| `/awolve-spec:login` | Authenticate with the spec service (Azure CLI or API key) |
| `/awolve-spec:status` | Show sync status and authentication info |
| `/awolve-spec:pull` | Pull latest spec files from the service |

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
| `/awolve-spec:set-status` | Change the status of a feature or document |

### Backlog & Bugs
| Command | Description |
|---------|-------------|
| `/awolve-spec:backlog` | List backlog items for a project |
| `/awolve-spec:backlog-add` | Add a new idea or feature request to the backlog |
| `/awolve-spec:bugs` | List open bugs |
| `/awolve-spec:bug` | Report a new bug |

### Skill
| Skill | Description |
|-------|-------------|
| `/awolve-spec:spec` | General spec skill — triggers on spec-related questions |

Offer to run any command the user is interested in.
