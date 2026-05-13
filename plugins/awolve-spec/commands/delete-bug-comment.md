---
description: Delete a bug comment (author or internal user). Hard delete, audited.
---

# /awolve-spec:delete-bug-comment

Delete a bug comment. The server allows the original author OR any internal Awolve user to delete. The deletion is a hard delete (no soft-delete tombstone) but a `bug_comment.delete` audit event captures the comment ID and a 100-char body excerpt.

## Instructions

Parse the user's argument. Expected forms:

- `<project> <bug-number> <comment-id>` — explicit project + bug ref + comment UUID
- `<bug-number> <comment-id>` — use the configured project (only when exactly one is in config)

Bug references accept the short numeric form. The comment ID is the UUID shown in brackets by `/awolve-spec:bug-comments`.

Before calling, confirm with the user that they want to delete — this is destructive and visible in the audit log.

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py delete-bug-comment <project-id> <bug-number> <comment-id>
```

## Notes

- Use `/awolve-spec:bug-comments <project> <bug-number>` first to find the comment ID.
- 403 means you're external and not the author.
- Prefer `/awolve-spec:edit-bug-comment` if you want to keep the thread but change the wording.
