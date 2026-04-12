---
description: Show recent audit activity — "what happened since my last visit" / "what happened yesterday"
---

# /awolve-spec:log

Answer questions about recent activity in the spec service using the audit log.

## When to use

Trigger on natural-language questions like:
- "What happened yesterday / this week / since my last visit?"
- "Who changed X recently?"
- "Show me recent activity in <project>"
- "What did <person> do yesterday?"
- "Any new comments / bugs / specs today?"
- "Has anyone updated <feature> lately?"

## Instructions

### 1. Pick a scope

Decide whether the user wants **one project** or **all projects**:

- If they name a project (e.g. "in spec-service", "for melbye"), use that project id.
- If they say "everywhere", "all projects", "the whole thing", or ask a question without naming a project, use `--all`.
- If they ask "what happened since I was here" or "anything new?" — default to `--all --since-last-visit --mark-read` so the visit cursor advances.

### 2. Pick a time window

Map natural language to the `--since` flag:

| User says | Use |
|---|---|
| "today" | `--since 1d` |
| "yesterday" | `--since 2d` (covers the last ~48h so all of "yesterday" is included) |
| "this week" / "past week" | `--since 7d` |
| "past hour" | `--since 1h` |
| "since Monday" (or a weekday) | `--since <N>d` where N = days back to that weekday |
| "since 2026-03-15" | `--since 2026-03-15` |
| "since my last visit" | `--since-last-visit` (no `--since` needed) |

### 3. Pick filters

- Person name / email → `--author bjorn.allvin@awolve.ai`
- Specific entity → `--entity feature` / `--entity document` / `--entity version` / `--entity comment` / `--entity review` / `--entity bug` / `--entity backlog` / `--entity attachment` / `--entity project_access` / `--entity project` / `--entity client` / `--entity portal_user` / `--entity api_key` / `--entity auth_token`
- Limit → `--limit 100` (default 50, max 1000)

### 4. Run the command

Single project:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py log <project-id> [flags]
```

All projects:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py log --all [flags]
```

### 5. Summarize the output

The command returns colored ANSI output — don't dump it verbatim. Instead:

- Group related events ("5 version edits on melbye-tender-tool/requirements.md", not 5 separate lines)
- Call out human-interesting events first: feature creates, status changes, new bugs, reviews, comments, access grants. Deprioritize bulk version updates (those are usually routine CLI syncs).
- Use bullet points organized by project when `--all` is in play
- Mention the person and rough time ("Bjorn 2h ago")
- If the user used `--since-last-visit`, note that the visit cursor was advanced so re-running won't show these again
- If nothing happened, say so plainly — don't pad

### 6. Offer next steps

After the summary, suggest useful follow-ups:
- "Want me to dig into a specific change?"
- "Run again for a different project with /awolve-spec:log <project>"
- "Open the portal history view: https://specs.awolve.ai/portal/<project>/history"

## Examples

**"What happened yesterday?"**
→ `specs log --all --since 2d` — summarize grouped by project.

**"What's new in spec-service since I last checked?"**
→ `specs log spec-service --since-last-visit --mark-read` — list new events, note cursor advanced.

**"Did Michael do anything today?"**
→ `specs log --all --since 1d --author michael.holmberg@awolve.ai`

**"Any new bugs this week?"**
→ `specs log --all --since 7d --entity bug`
