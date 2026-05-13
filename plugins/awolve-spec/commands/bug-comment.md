---
description: Add a comment to a bug
---

# /awolve-spec:bug-comment

Add a comment to an existing bug. Use this to attach resolution context (commit SHA, package version, rollout notes) or to discuss triage without rewriting the original report.

## Instructions

Parse the user's argument. Expected forms:

- `<project> <bug-number> <body>` — explicit project + bug ref + comment body
- `<bug-number> <body>` — use the configured project (only when exactly one is in config)

Bug references accept the short numeric form (with or without `#`). The body is a single argument — quote it if it contains spaces.

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py bug-comment <project-id> <bug-number> "<body>"
```

Examples:

```bash
# Attach the fix commit to the bug record
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py bug-comment spec-service 15 "Shipped in plugin v0.16.2 — commit abc1234."

# Note that a proposed fix was reconsidered
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py bug-comment myoffice 1 "Reverted course — keeping plain-text default. Will add a stderr warning instead."
```

## Notes

- To view existing comments before adding one, use `/awolve-spec:bug-comments`.
- The author shown on the comment is your portal identity (the email behind the current login).
- Each comment is recorded in the audit log as a `bug_comment.create` event on the bug's project.
