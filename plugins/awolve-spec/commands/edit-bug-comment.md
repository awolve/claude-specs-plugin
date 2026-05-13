---
description: Edit a bug comment (author or internal user). Audited.
---

# /awolve-spec:edit-bug-comment

Edit the body of an existing bug comment. The server allows the original author OR any internal Awolve user to edit. Every body change writes a `bug_comment.update` audit event.

## Instructions

Parse the user's argument. Expected forms:

- `<project> <bug-number> <comment-id> <body>` — explicit project + bug ref + comment UUID + new body
- `<bug-number> <comment-id> <body>` — use the configured project (only when exactly one is in config)

Bug references accept the short numeric form (with or without `#`). The comment ID is the UUID shown in brackets by `/awolve-spec:bug-comments`. Quote the body if it contains spaces.

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py edit-bug-comment <project-id> <bug-number> <comment-id> "<body>"
```

Examples:

```bash
# Fix a typo in a resolution note
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py edit-bug-comment spec-service 15 7f5d… "Shipped in awolve-spec v0.16.3 — commit abc1234."
```

## Notes

- Use `/awolve-spec:bug-comments <project> <bug-number>` first to find the comment ID.
- 403 means you're external and not the author.
- The edit is logged with the bug's project as the audit scope, so it shows up in `/awolve-spec:log` for that project.
