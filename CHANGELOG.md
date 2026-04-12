# Changelog

## 0.14.0 — 2026-04-12

**Robust pull + `specs log` command** (spec 010 phases 3b + 4, plugin side). Companion to spec-service v0.18.0 which shipped the `/changes` and `/history` endpoints.

### Pull robustness

- **Atomic writes** — every file write (.md docs and binary attachments) goes through a tempfile → fsync → os.replace. A crash mid-write can never leave a half-written file in your specs folder.
- **HTTP retries** — `api_request()` now retries transient failures:
  - GET: 3 attempts for 502/503/504 and `ConnectionError`, exponential backoff (0.5s → 1s → 2s) with ±25% jitter.
  - Mutating methods (PUT/POST/PATCH/DELETE): 1 retry for `ConnectionError` only, and only if the error happened before the request was sent. Never retry on HTTPError — we trust any status the server actually returned.
  - 401 and 409 are never retried (they're semantic signals).
- **Drift detection via `last_synced_hash`** — every synced file now carries a `last_synced_hash` frontmatter field recording the body hash the client last saw from the server. On subsequent pulls, if the local hash differs from `last_synced_hash` AND the remote hash has also changed, the pull writes the remote content to `<file>.remote` and leaves the local file untouched. The pull summary reports conflicts so you can review and reconcile them manually.
- **`push()` sets `last_synced_hash`** after a successful push so the new value is consistent — a subsequent pull will treat the just-pushed version as "clean".
- **Deletion handling** — when a local file's `spec_doc_id` isn't in the remote manifest (feature or document was deleted in the portal), `pull` moves the local file into `.specs-trash/YYYY-MM-DD/<relative-path>` by default. Three flags control this:
  - `pull --prune` — permanently delete instead of trashing
  - `pull --keep` — leave orphans alone (previous default behavior)
  - `pull` (default) — trash, recoverable
  Collisions in the trash get a numeric suffix so nothing is ever overwritten.

### State file

- New per-project state file at `.claude/specs.state.json` tracking sync and visit cursors across pulls. Shape:
  ```json
  {
    "version": 1,
    "projects": {
      "spec-service": {
        "last_sync_cursor": "01HXX...",
        "last_visit_cursor": "01HXX...",
        "last_full_sync": "2026-04-12T00:00:15Z",
        "last_pulled_at": "2026-04-12T00:00:15Z"
      }
    }
  }
  ```
- Written atomically after every pull and every `log --mark-read`. Add to `.gitignore` — it's per-clone state.

### `specs log` — new command

Stream audit events from the spec service for a project:

```bash
specs log <project>                          # 50 most recent events (desc)
specs log <project> --since 7d               # last 7 days
specs log <project> --since 2026-04-01       # since absolute date
specs log <project> --author bjorn@awolve.ai # filter by actor
specs log <project> --entity feature         # filter by entity type
specs log <project> --limit 200              # up to 1000
specs log <project> --json                   # machine-readable
specs log <project> --since-last-visit       # "what happened since I last looked"
specs log <project> --since-last-visit --mark-read  # advance the visit cursor
```

Output is colored by entity type (feature / doc / version / comment / review / bug / etc.), grouped by day, and shows actor + relative time. `--since-last-visit` reads the project's `last_visit_cursor` from the state file; `--mark-read` advances it to the newest event shown. Re-running the same command with `--mark-read` after a clean read shows "(no new events since your last visit)".

### Known soft limits

- `specs log --since <duration>` is a client-side filter applied after the server returns the window. The underlying endpoint is cursor-based (ULID), not timestamp-based, so the duration filter is a display convenience — for very old windows you'll need to paginate via `--limit`.
- `specs log --since-last-visit` relies on the state file's `last_visit_cursor`. First run with an empty state file returns everything the server has — expected, since "last visit" is undefined.

### Requires

- spec-service v0.18.0 or later. Older versions return the manifest without a `cursor` field, which the plugin tolerates but deletion detection + delta sync fall back to "full manifest every time".

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
