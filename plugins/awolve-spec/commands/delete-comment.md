---
description: Delete a spec-doc comment (author only). Hard delete, audited.
---

# /awolve-spec:delete-comment

Delete a spec-document comment. The server only allows the original author to delete. The deletion is a hard delete (no soft-delete tombstone) but a `comment.delete` audit event captures the comment number and a 100-char body excerpt.

## Instructions

Parse the user's argument. Expected form:

- `<comment-id>` — the UUID from `/awolve-spec:comments` output.

Before calling, confirm with the user that they want to delete — this is destructive and visible in the audit log.

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py delete-comment <comment-id>
```

## Notes

- Use `/awolve-spec:comments <file-path>` first to find the comment ID.
- 403 means you aren't the author.
- If the comment has replies, the server deletes those too in the same transaction.
- Prefer `/awolve-spec:edit-comment` if you want to keep the thread but change the wording, or `/awolve-spec:resolve-comment` to mark it handled without removing it.
