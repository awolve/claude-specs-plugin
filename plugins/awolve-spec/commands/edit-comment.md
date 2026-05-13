---
description: Edit a spec-doc comment (author only). Audited.
---

# /awolve-spec:edit-comment

Edit the body of a spec-document comment. The server only allows the original author to edit. Every body change writes a `comment.update` audit event.

## Instructions

Parse the user's argument. Expected form:

- `<comment-id> <body>` — the UUID from `/awolve-spec:comments` output, plus the new body. Quote the body if it contains spaces.

Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py edit-comment <comment-id> "<body>"
```

Examples:

```bash
# Tighten an unclear comment after re-reading the spec
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/specs-cli.py edit-comment 7f5d… "Section 3 still needs an explicit rollback plan — the rest looks good."
```

## Notes

- Use `/awolve-spec:comments <file-path>` first to find the comment ID.
- 403 means you aren't the author. Add a follow-up comment via `/awolve-spec:comment` instead.
- To mark a comment resolved (instead of editing it), use `/awolve-spec:resolve-comment`.
- The previous body is preserved in the audit event metadata (first 100 chars), so the edit history is recoverable.
