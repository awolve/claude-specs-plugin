# Changelog

## 0.13.0 — 2026-04-10
- **Binary attachments**. Completes the filesystem-sync half of the spec-service file upload feature (service side shipped in spec-service 0.13.0).
  - `pull` now also downloads feature attachments to the local feature folder alongside .md docs. Deduped by `(filename, size)` — re-downloads on size mismatch, skips otherwise.
  - New `attach` command and `/awolve-spec:attach` slash command for uploading a local binary file (image, PDF, Excel, etc.) to a feature. Feature is inferred from the file path if not specified explicitly.
  - Multipart upload built inline (no third-party deps) so the CLI stays stdlib-only.
- Requires spec-service v0.13.0 or later (earlier versions will reject the attachment API calls).

## 0.10.9 — 2026-04-02
- UX: API key login reads from clipboard (`--from-clipboard`) — copy key, run command, done
- Validates key starts with `sk_` before calling service
- Clears clipboard after successful login

## 0.10.8 — 2026-04-02
- Fix: API key login supports `SPECS_API_KEY` env var — works in Claude Code `!` commands where getpass fails
- Falls back gracefully with instructions if interactive input unavailable

## 0.10.7 — 2026-04-02
- Fix: `/specs-login` removes Bash from allowed-tools so it must ask auth method first

## 0.10.6 — 2026-04-02
- Fix: `/specs-login` now forces auth method question — cannot be skipped or assumed
- Docs: added update command to README and SKILL.md
- Docs: updated README with full command list and current setup flow

## 0.10.5 — 2026-04-02
- UX: `/specs-login` now asks user to choose auth method (Azure CLI or API key) before proceeding

## 0.10.4 — 2026-04-02
- Security: API key login now uses `getpass` (hidden prompt) — key never appears in args or conversation
- Login verifies key against service before saving
- Command instructs user to run via `!` prefix so key stays in their terminal

## 0.10.3 — 2026-04-02
- Fix: create-feature now sends required `title` and `contextPath` to API (was failing with 400)
- Fix: create-doc now sends required `content` to API (was failing with 400)
- Fix: list-features reads `documentCount` instead of missing `documents` array
- Fix: frontmatter parsing tolerates BOM, `\r\n` line endings, and trailing whitespace
- Fix: push strips any leaked/double frontmatter from body before sending
- Fix: render_frontmatter normalizes body join to prevent double-newline compounding
- Refactor: create_backlog_item passes dict instead of pre-serialized JSON string

## 0.10.2 — 2026-04-01
- Fix: specs-pull updates local frontmatter (spec_version, feature_status, doc_status) when content matches but metadata has drifted — prevents stale base_version causing false 409 conflicts on push

## 0.10.1 — 2026-03-31
- Align marketplace and plugin versions

## 0.10.0 — 2026-03-31
- Feature and document management commands (create, rename, delete features and documents)

## 0.9.1 — 2026-03-31
- Fix: remove explicit hooks reference — auto-discovered by convention

## 0.9.0 — 2026-03-31
- Phased spec commands: `/spec requirements`, `/spec design`, `/spec infra`, `/spec plan`

## 0.8.1 — 2026-03-29
- Fix: register hooks in plugin manifest
