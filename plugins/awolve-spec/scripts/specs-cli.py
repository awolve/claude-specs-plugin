#!/usr/bin/env python3
"""
Specs CLI — sync, review, and manage spec documents.

Usage:
    specs-cli.py pull [project-id] [--prune|--keep] [--force-full]
                                       — Pull latest specs (all projects, or specific one)
                                         --prune        permanently delete orphaned local files
                                         --keep         leave orphans alone (no trash)
                                         --force-full   bypass delta sync, always fetch manifest
    specs-cli.py log <project-id|--all> [--since DUR] [--author EMAIL] [--entity TYPE]
                                       [--limit N] [--json] [--since-last-visit] [--mark-read]
                                       — Stream audit events (one project, or --all for every configured project)
    specs-cli.py push <file_path>      — Push a single spec file
    specs-cli.py status                — Show sync status of local spec files
    specs-cli.py set-status <id> <status> — Set feature or document status
    specs-cli.py set-description <feature-id> <text>
                                       — Set or clear a feature's shortDescription (pass "" to clear)
    specs-cli.py create-feature <project-id> <name> [--status STATUS] [--description TEXT]
                                       — Create a new feature in a project
    specs-cli.py create-doc <project-id> <feature-name> <filename>
                                       — Add a document to an existing feature
    specs-cli.py rename-feature <project-id> <old-name> <new-name>
                                       — Rename a feature folder and update the service
    specs-cli.py rename-doc <file-path> <new-filename>
                                       — Rename a document file and update the service
    specs-cli.py delete-doc <file-path>
                                       — Delete a document from filesystem and service
    specs-cli.py delete-feature <project-id> <feature-name>
                                       — Delete a feature and all its documents
    specs-cli.py list-features <project-id>
                                       — List all features in a project
    specs-cli.py list-docs <project-id> <feature-name>
                                       — List all documents in a feature
    specs-cli.py backlog [project-id] [--epics|--flat] [--status STATUS] [--priority PRIORITY]
                                       — List backlog items (default: tree view, grouped by epic)
    specs-cli.py backlog-add <project-id> <title> [description] [priority] [--parent <id-or-#N>]
                                       — Create a backlog item; optional --parent makes it a child of an epic
    specs-cli.py backlog-set-parent <project-id> <item-id-or-#N> <parent-id-or-#N|none>
                                       — Reparent a backlog item (or pass 'none' to clear the parent)
    specs-cli.py bugs <project-id>     — List bugs for a project
    specs-cli.py bug <project-id> <title> <description> [severity] — Create a bug
    specs-cli.py view-bug <project-id> <bug-number> [--json]
                                       — Show full details of a single bug (description, severity, repro, etc.)
    specs-cli.py set-bug-status <project-id> <bug-number> <status>
                                       — Change a bug's status (open|triaged|in_progress|resolved|closed)
    specs-cli.py comments <file-path>  — List comments on a spec document
    specs-cli.py comment <file-path> <body> [--inline --anchor <text>]
                                       — Add a comment to a spec document
    specs-cli.py resolve-comment <comment-id> — Resolve a comment
    specs-cli.py reviews <file-path>   — List reviews on a spec document
    specs-cli.py review <file-path> <verdict> [body]
                                       — Submit a review (approved|changes_requested)
    specs-cli.py versions <file-path>  — List version history
    specs-cli.py save <file-path> <summary> [--source <source>]
                                       — Save current file as a named version
    specs-cli.py service-status        — Check spec service health
    specs-cli.py post-tool-use         — Hook: read tool use JSON from stdin, push if spec
    specs-cli.py attach <file-path> [<project-id>/<feature-name>]
                                       — Upload a binary file as an attachment to a feature
                                         (if no feature id given, inferred from file path)
    specs-cli.py --help                — Show this help
"""

import hashlib
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

# Add scripts dir to path for sibling imports
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

import auth
import config


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

# Tolerant: optional BOM, \r\n or \n, optional trailing whitespace on delimiter lines
FM_PATTERN = re.compile(
    r"^\ufeff?"           # optional BOM
    r"---[ \t]*\r?\n"     # opening ---
    r"(.*?)\r?\n"         # frontmatter body (lazy)
    r"---[ \t]*\r?\n?",   # closing ---
    re.DOTALL,
)


def parse_frontmatter(content):
    """Parse YAML frontmatter. Returns (metadata_dict, body_without_frontmatter).

    Tolerates BOM, \\r\\n line endings, and trailing whitespace on delimiters.
    """
    m = FM_PATTERN.match(content)
    if not m:
        return {}, content
    fm_text = m.group(1)
    body = content[m.end():]
    meta = {}
    for line in fm_text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([\w_]+)\s*:\s*(.+)$", line)
        if match:
            key = match.group(1)
            val = match.group(2).strip().strip("\"'")
            try:
                val = int(val)
            except (ValueError, TypeError):
                pass
            meta[key] = val
    return meta, body


def render_frontmatter(meta, body):
    """Render metadata dict and body back into markdown with frontmatter.

    Normalises the join: body always starts with exactly one blank line.
    """
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    # Ensure exactly one blank line between frontmatter and body
    body = body.lstrip("\r\n")
    lines.append("")
    return "\n".join(lines) + "\n" + body


def strip_frontmatter(content):
    """Remove any leading frontmatter block(s) from content.

    Handles the case where frontmatter leaked into body (double frontmatter).
    """
    while True:
        m = FM_PATTERN.match(content)
        if not m:
            return content
        content = content[m.end():]


def file_content_hash(content):
    """SHA-256 hash of body content (without frontmatter)."""
    _, body = parse_frontmatter(content)
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def api_request(url, method="GET", headers=None, data=None):
    """Make an HTTP request with transient-failure retries.

    Returns (status_code, response_body_str).

    Retry policy (spec 010 phase 3b):
    - GET: retry on ConnectionError and 502/503/504, up to 3 attempts total.
      Backoff 0.5s → 1s → 2s with ±25% jitter.
    - PUT/POST/PATCH/DELETE: retry on ConnectionError only, once, and only
      if the error happened *before* the request was sent. After the server
      has returned any status code we trust it and do not retry.
    - 409 Conflict and 401 Unauthorized are never retried — they're semantic
      signals the caller needs to handle.
    """
    headers = headers or {}
    headers.setdefault("User-Agent", "awolve-specs-plugin/1.0.0")

    body_bytes = None
    if data is not None:
        if isinstance(data, str):
            body_bytes = data.encode("utf-8")
            headers.setdefault("Content-Type", "text/markdown; charset=utf-8")
        elif isinstance(data, dict):
            body_bytes = json.dumps(data).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

    is_get = method.upper() == "GET"
    max_attempts = 3 if is_get else 2
    backoff_base = 0.5

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            # Only retry GETs on 502/503/504, and only if attempts remain.
            if is_get and e.code in (502, 503, 504) and attempt + 1 < max_attempts:
                _sleep_with_jitter(backoff_base * (2 ** attempt))
                continue
            return e.code, body
        except urllib.error.URLError as e:
            last_exc = ConnectionError(f"Network error: {e.reason}")
            # URLError before we got any response — safe to retry for both
            # GET and mutating methods (the request was never accepted).
            if attempt + 1 < max_attempts:
                _sleep_with_jitter(backoff_base * (2 ** attempt))
                continue
            raise last_exc from e

    # Unreachable, but keeps mypy happy
    raise last_exc or ConnectionError("Network error (no attempts made)")


def _sleep_with_jitter(base_seconds):
    """Sleep for `base_seconds` ± 25% jitter. Used by the retry backoff."""
    jitter = base_seconds * 0.25
    time.sleep(max(0.05, base_seconds + random.uniform(-jitter, jitter)))


# ---------------------------------------------------------------------------
# Atomic file writes (spec 010 phase 3b)
# ---------------------------------------------------------------------------

def atomic_write(path, content, binary=False):
    """Write `content` to `path` atomically: tempfile → fsync → os.replace.

    Prevents half-written files if the process crashes or the disk fills up
    mid-write. The tempfile is created in the same directory as the target
    so the final `os.replace` is a same-filesystem rename (atomic on POSIX
    and modern Windows).
    """
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    mode = "wb" if binary else "w"
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        if binary:
            os.close(fd)
            with open(tmp, mode) as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
        else:
            with os.fdopen(fd, mode, encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# State file — per-project sync + visit cursors (spec 010 phase 4)
# ---------------------------------------------------------------------------

_STATE_FILENAME = "specs.state.json"
_FULL_SYNC_INTERVAL = timedelta(days=7)


def _state_path(project_root):
    """Return the absolute path to .claude/specs.state.json for a project root."""
    return os.path.join(project_root, ".claude", _STATE_FILENAME)


def state_load(project_root):
    """Load the state file. Returns a dict; empty if missing or corrupt."""
    path = _state_path(project_root)
    if not os.path.isfile(path):
        return {"version": 1, "projects": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "projects" not in data:
            return {"version": 1, "projects": {}}
        return data
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "projects": {}}


def state_save(project_root, state):
    """Persist the state file atomically."""
    path = _state_path(project_root)
    atomic_write(path, json.dumps(state, indent=2, sort_keys=True))


def state_get_project(state, project_id):
    """Get the state record for a project, creating an empty one if missing."""
    projects = state.setdefault("projects", {})
    return projects.setdefault(project_id, {})


def state_update_project(state, project_id, **kwargs):
    """Shallow-merge kwargs into the project's state record."""
    rec = state_get_project(state, project_id)
    rec.update(kwargs)
    return rec


def state_needs_full_sync(project_state):
    """True if the project has never been fully synced or is past the interval."""
    last = project_state.get("last_full_sync")
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - dt) > _FULL_SYNC_INTERVAL


# ---------------------------------------------------------------------------
# Trash — move orphaned local files to .specs-trash/ on pull (spec 010 phase 3b)
# ---------------------------------------------------------------------------

def trash_move(specs_path, file_path):
    """Move a file into .specs-trash/YYYY-MM-DD/ relative to specs_path.

    Collisions get a numeric suffix (foo-1.md, foo-2.md, ...) so nothing in
    the trash is ever overwritten.
    """
    rel = os.path.relpath(file_path, specs_path)
    today = datetime.now().strftime("%Y-%m-%d")
    trash_dir = os.path.join(specs_path, ".specs-trash", today, os.path.dirname(rel))
    os.makedirs(trash_dir, exist_ok=True)
    base = os.path.basename(rel)
    target = os.path.join(trash_dir, base)
    # Collision suffix
    if os.path.exists(target):
        stem, ext = os.path.splitext(base)
        n = 1
        while os.path.exists(os.path.join(trash_dir, f"{stem}-{n}{ext}")):
            n += 1
        target = os.path.join(trash_dir, f"{stem}-{n}{ext}")
    shutil.move(file_path, target)
    return target


# ---------------------------------------------------------------------------
# Doc ID resolution
# ---------------------------------------------------------------------------

def resolve_doc_id(file_path):
    """Resolve a local spec file path to a spec service document ID.

    Returns (cfg, headers, service_url, doc_id, project_id, feature_name, filename).
    Exits on error.
    """
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    abs_path = os.path.abspath(file_path)

    # Try frontmatter first
    if os.path.isfile(abs_path):
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read(2048)
            meta, _ = parse_frontmatter(content)
            if meta.get("spec_doc_id"):
                proj = config.find_project_for_file(cfg, abs_path)
                project_id = proj["id"] if proj else "unknown"
                return cfg, headers, service_url, meta["spec_doc_id"], project_id, "", os.path.basename(abs_path)
        except (IOError, OSError):
            pass

    # Fall back to API lookup
    proj = config.find_project_for_file(cfg, abs_path)
    if not proj:
        print(f"specs: {file_path} is not inside any configured specs path", file=sys.stderr)
        sys.exit(1)

    # Extract feature name from path: .../specs/{feature-name}/{filename}
    rel = os.path.relpath(abs_path, proj["path"])
    parts = rel.replace("\\", "/").split("/")
    if len(parts) < 2:
        print(f"specs: cannot determine feature from path {file_path}", file=sys.stderr)
        sys.exit(1)

    feature_name = parts[0]
    filename = parts[-1]
    feature_id = f"{proj['id']}/{feature_name}"

    import urllib.parse
    encoded_id = urllib.parse.quote(feature_id, safe="")

    try:
        status_code, body = api_request(
            f"{service_url}/api/features/lookup?id={encoded_id}",
            headers=headers,
        )
    except ConnectionError as e:
        print(f"specs: failed to look up feature — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code != 200:
        print(f"specs: feature '{feature_id}' not found (HTTP {status_code})", file=sys.stderr)
        sys.exit(1)

    feature_data = json.loads(body)
    documents = feature_data.get("documents", [])
    for doc in documents:
        if doc.get("filename") == filename:
            return cfg, headers, service_url, doc["id"], proj["id"], feature_name, filename

    print(f"specs: document '{filename}' not found in feature '{feature_id}'", file=sys.stderr)
    sys.exit(1)


def _init_and_auth():
    """Common init: read config, get auth headers. Returns (cfg, headers, service_url)."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)
    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)
    return cfg, headers, cfg["service_url"]


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def list_comments(file_path, as_json=False):
    """List comments on a spec document."""
    _, headers, service_url, doc_id, *_ = resolve_doc_id(file_path)

    try:
        status_code, body = api_request(
            f"{service_url}/api/documents/{doc_id}/comments",
            headers=headers,
        )
    except ConnectionError as e:
        print(f"specs: failed to fetch comments — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code != 200:
        print(f"specs: failed to fetch comments (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    comments = json.loads(body)

    if as_json:
        print(json.dumps(comments, indent=2))
        return

    unresolved = [c for c in comments if not c.get("resolved")]
    resolved = [c for c in comments if c.get("resolved")]

    if not comments:
        print("specs: no comments")
        return

    if unresolved:
        print(f"=== Unresolved ({len(unresolved)}) ===\n")
        for c in unresolved:
            _print_comment(c)

    if resolved:
        print(f"=== Resolved ({len(resolved)}) ===\n")
        for c in resolved:
            _print_comment(c)


def _print_comment(c):
    """Print a single comment."""
    author = c.get("author", "?")
    date = c.get("createdAt", "?")[:10]
    body = c.get("body", "")
    ctype = c.get("type", "thread")
    anchor = c.get("anchorText", "")
    comment_id = c.get("id", "?")

    prefix = f"  [{ctype}]" if ctype == "inline" else "  "
    print(f"{prefix} {author} ({date}) [{comment_id}]")
    if anchor:
        print(f"    anchor: \"{anchor}\"")
    print(f"    {body}")
    print()


def add_comment(file_path, body, inline=False, anchor_text=None):
    """Add a comment to a spec document."""
    _, headers, service_url, doc_id, *_ = resolve_doc_id(file_path)

    payload = {"body": body, "type": "inline" if inline else "thread"}
    if inline and anchor_text:
        payload["anchorText"] = anchor_text

    try:
        status_code, resp = api_request(
            f"{service_url}/api/documents/{doc_id}/comments",
            method="POST",
            headers={**headers, "Content-Type": "application/json"},
            data=payload,
        )
    except ConnectionError as e:
        print(f"specs: failed to add comment — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 201):
        print(f"specs: failed to add comment (HTTP {status_code}): {resp}", file=sys.stderr)
        sys.exit(1)

    print("specs: comment added")


def resolve_comment(comment_id):
    """Mark a comment as resolved."""
    _, headers, service_url = _init_and_auth()

    try:
        status_code, resp = api_request(
            f"{service_url}/api/comments/{comment_id}",
            method="PATCH",
            headers={**headers, "Content-Type": "application/json"},
            data={"resolved": True},
        )
    except ConnectionError as e:
        print(f"specs: failed to resolve comment — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 201):
        print(f"specs: failed to resolve comment (HTTP {status_code}): {resp}", file=sys.stderr)
        sys.exit(1)

    print(f"specs: comment {comment_id} resolved")


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

def list_reviews(file_path, as_json=False):
    """List reviews on a spec document."""
    _, headers, service_url, doc_id, *_ = resolve_doc_id(file_path)

    try:
        status_code, body = api_request(
            f"{service_url}/api/documents/{doc_id}/reviews",
            headers=headers,
        )
    except ConnectionError as e:
        print(f"specs: failed to fetch reviews — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code != 200:
        print(f"specs: failed to fetch reviews (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    reviews = json.loads(body)

    if as_json:
        print(json.dumps(reviews, indent=2))
        return

    if not reviews:
        print("specs: no reviews")
        return

    for r in reviews:
        author = r.get("author", "?")
        date = r.get("createdAt", "?")[:10]
        verdict = r.get("verdict", "?")
        rbody = r.get("body", "")
        version = r.get("version", "?")
        marker = "+" if verdict == "approved" else "!"
        print(f"  [{marker}] {author} ({date}) — {verdict} (v{version})")
        if rbody:
            print(f"      {rbody}")
        print()


def submit_review(file_path, verdict, body=None):
    """Submit a review on a spec document."""
    _, headers, service_url, doc_id, *_ = resolve_doc_id(file_path)

    if verdict not in ("approved", "changes_requested"):
        print(f"specs: verdict must be 'approved' or 'changes_requested', got '{verdict}'", file=sys.stderr)
        sys.exit(1)

    payload = {"verdict": verdict}
    if body:
        payload["body"] = body

    try:
        status_code, resp = api_request(
            f"{service_url}/api/documents/{doc_id}/reviews",
            method="POST",
            headers={**headers, "Content-Type": "application/json"},
            data=payload,
        )
    except ConnectionError as e:
        print(f"specs: failed to submit review — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 201):
        print(f"specs: failed to submit review (HTTP {status_code}): {resp}", file=sys.stderr)
        sys.exit(1)

    print(f"specs: review submitted — {verdict}")


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

def list_versions(file_path, as_json=False):
    """List version history of a spec document."""
    _, headers, service_url, doc_id, *_ = resolve_doc_id(file_path)

    try:
        status_code, body = api_request(
            f"{service_url}/api/documents/{doc_id}/versions",
            headers=headers,
        )
    except ConnectionError as e:
        print(f"specs: failed to fetch versions — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code != 200:
        print(f"specs: failed to fetch versions (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    versions = json.loads(body)

    if as_json:
        print(json.dumps(versions, indent=2))
        return

    if not versions:
        print("specs: no versions")
        return

    for v in versions:
        num = v.get("version", "?")
        author = v.get("author", "?")
        date = v.get("createdAt", "?")[:10]
        summary = v.get("summary", "")
        source = v.get("source", "?")
        print(f"  v{num}  {author} ({date})  [{source}]")
        if summary:
            print(f"    {summary}")
        print()


def save_version(file_path, summary, source="manual"):
    """Save the current file as a new named version in the spec service."""
    _, headers, service_url, doc_id, *_ = resolve_doc_id(file_path)

    abs_path = os.path.abspath(file_path)
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError) as e:
        print(f"specs: cannot read {file_path} — {e}", file=sys.stderr)
        sys.exit(1)

    _, body = parse_frontmatter(content)

    payload = {
        "content": body.strip(),
        "summary": summary,
        "source": source,
    }

    try:
        status_code, resp = api_request(
            f"{service_url}/api/documents/{doc_id}/versions",
            method="POST",
            headers={**headers, "Content-Type": "application/json"},
            data=payload,
        )
    except ConnectionError as e:
        print(f"specs: failed to save version — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 201):
        print(f"specs: failed to save version (HTTP {status_code}): {resp}", file=sys.stderr)
        sys.exit(1)

    try:
        resp_data = json.loads(resp)
        version_num = resp_data.get("version", "?")
    except (json.JSONDecodeError, AttributeError):
        version_num = "?"

    print(f"specs: saved version v{version_num} — {summary}")


# ---------------------------------------------------------------------------
# Service status
# ---------------------------------------------------------------------------

def service_status():
    """Check spec service health."""
    _, headers, service_url = _init_and_auth()

    try:
        status_code, body = api_request(f"{service_url}/api/status", headers=headers)
    except ConnectionError as e:
        print(f"specs: service unreachable — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code != 200:
        print(f"specs: service returned HTTP {status_code}", file=sys.stderr)
        sys.exit(1)

    print(f"specs: service OK")
    try:
        data = json.loads(body)
        for k, v in data.items():
            print(f"  {k}: {v}")
    except json.JSONDecodeError:
        pass


# ---------------------------------------------------------------------------
# Pull (single project)
# ---------------------------------------------------------------------------

def _scan_local_specs(specs_path):
    """Walk a specs directory and index existing files by spec_doc_id.

    Returns a dict: { doc_id: absolute_path }. Files without a spec_doc_id
    in their frontmatter are skipped — they're either draft specs not yet
    registered with the service, or unrelated markdown.
    """
    index = {}
    if not os.path.isdir(specs_path):
        return index
    for root, dirs, files in os.walk(specs_path):
        # Never recurse into the trash
        if ".specs-trash" in dirs:
            dirs.remove(".specs-trash")
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read(4096)
            except (IOError, OSError):
                continue
            meta, _ = parse_frontmatter(content)
            doc_id = meta.get("spec_doc_id")
            if doc_id:
                index[doc_id] = fpath
    return index


def pull_project(
    project_id,
    specs_path,
    service_url,
    headers,
    state=None,
    delete_mode="trash",
    force_full=False,
    quiet=False,
):
    """Pull specs for a single project.

    Returns a dict with counts and outcomes:
        {
            "synced": int,          # files written (new or updated)
            "unchanged": int,       # hash matched, possibly frontmatter retouched
            "trashed": int,         # local files orphaned by remote deletion
            "conflicts": list[str], # paths where .remote sidecar was written
            "skipped_errors": int,  # transient failures mid-pull
            "cursor": str | None,   # advanced if the manifest returned one
        }

    Parameters (spec 010 phase 3b + 4):
      state        — the loaded state dict (from state_load); mutated in place
                     to record last_sync_cursor and last_full_sync. Pass None
                     to skip state management.
      delete_mode  — "trash" (default), "prune" (hard delete), or "keep"
                     (leave orphans alone)
      force_full   — bypass delta sync and always fetch the full manifest
    """
    report = {
        "synced": 0,
        "unchanged": 0,
        "trashed": 0,
        "conflicts": [],
        "skipped_errors": 0,
        "cursor": None,
    }

    manifest_url = f"{service_url}/api/sync/projects/{project_id}/manifest"
    try:
        status, body = api_request(manifest_url, headers=headers)
    except ConnectionError as e:
        if not quiet:
            print(f"specs: pull failed for '{project_id}' — {e}", file=sys.stderr)
        return report

    if status == 401:
        if not quiet:
            print("specs: authentication expired — run /awolve-spec:login", file=sys.stderr)
        return report
    if status == 404:
        if not quiet:
            print(f"specs: project '{project_id}' not found", file=sys.stderr)
        return report
    if status != 200:
        if not quiet:
            print(f"specs: manifest failed for '{project_id}' (HTTP {status})", file=sys.stderr)
        return report

    manifest = json.loads(body)
    documents = manifest.get("documents", [])
    remote_attachments = manifest.get("attachments", [])
    manifest_cursor = manifest.get("cursor")

    os.makedirs(specs_path, exist_ok=True)

    # Index remote doc ids so we can find local orphans at the end.
    remote_doc_ids = {doc["id"] for doc in documents}

    for doc in documents:
        doc_id = doc["id"]
        feature_name = doc.get("feature", "general")
        filename = doc.get("filename", f"{doc_id}.md")
        remote_hash = doc.get("content_hash", "")
        version = doc.get("version", 1)
        feature_status = doc.get("feature_status", "")
        doc_status = doc.get("doc_status", "")
        source_url = doc.get("source_url", "")

        local_dir = os.path.join(specs_path, feature_name)
        local_path = os.path.join(local_dir, filename)

        # ---- Hash-match fast path ----
        if os.path.isfile(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    local_content = f.read()
                local_hash = file_content_hash(local_content)
                if local_hash == remote_hash:
                    # Content matches — update frontmatter if version/status drifted
                    local_meta, local_body = parse_frontmatter(local_content)
                    if (local_meta.get("spec_version") != version or
                        local_meta.get("feature_status", "") != feature_status or
                        local_meta.get("doc_status", "") != doc_status or
                        local_meta.get("last_synced_hash") != remote_hash):
                        local_meta["spec_version"] = version
                        local_meta["last_synced_hash"] = remote_hash
                        if feature_status:
                            local_meta["feature_status"] = feature_status
                        if doc_status:
                            local_meta["doc_status"] = doc_status
                        atomic_write(local_path, render_frontmatter(local_meta, local_body))
                    report["unchanged"] += 1
                    continue

                # ---- Hash mismatch: check for local drift before overwriting ----
                local_meta, _ = parse_frontmatter(local_content)
                last_synced_hash = local_meta.get("last_synced_hash")
                if last_synced_hash and last_synced_hash != local_hash:
                    # Local was modified since last sync AND remote has also
                    # changed. Write remote to .remote sidecar, leave local
                    # alone, report the conflict.
                    sidecar = local_path + ".remote"
                    content_url = f"{service_url}/api/sync/documents/{doc_id}/content"
                    try:
                        dl_status, dl_body = api_request(content_url, headers=headers)
                    except ConnectionError:
                        report["skipped_errors"] += 1
                        continue
                    if dl_status != 200:
                        report["skipped_errors"] += 1
                        continue
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    sidecar_meta = {
                        "spec_version": version,
                        "spec_doc_id": doc_id,
                        "last_synced": now,
                        "last_synced_hash": remote_hash,
                    }
                    if feature_status:
                        sidecar_meta["feature_status"] = feature_status
                    if doc_status:
                        sidecar_meta["doc_status"] = doc_status
                    if source_url:
                        sidecar_meta["source"] = source_url
                    atomic_write(sidecar, render_frontmatter(sidecar_meta, dl_body))
                    report["conflicts"].append(local_path)
                    continue
            except (IOError, OSError):
                pass

        # ---- Download + write (new file or remote-newer, no local drift) ----
        content_url = f"{service_url}/api/sync/documents/{doc_id}/content"
        try:
            dl_status, dl_body = api_request(content_url, headers=headers)
        except ConnectionError:
            report["skipped_errors"] += 1
            continue

        if dl_status != 200:
            report["skipped_errors"] += 1
            continue

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = {
            "spec_version": version,
            "spec_doc_id": doc_id,
            "last_synced": now,
            "last_synced_hash": remote_hash,
        }
        if feature_status:
            meta["feature_status"] = feature_status
        if doc_status:
            meta["doc_status"] = doc_status
        if source_url:
            meta["source"] = source_url

        atomic_write(local_path, render_frontmatter(meta, dl_body))
        report["synced"] += 1

    # ---- Binary attachments ----
    for att in remote_attachments:
        att_id = att.get("id")
        feature_name = att.get("feature")
        filename = att.get("filename")
        size = att.get("size_bytes", 0)
        if not att_id or not feature_name or not filename:
            continue

        local_dir = os.path.join(specs_path, feature_name)
        local_path = os.path.join(local_dir, filename)

        if os.path.isfile(local_path):
            try:
                if os.path.getsize(local_path) == size:
                    report["unchanged"] += 1
                    continue
            except OSError:
                pass

        dl_url = f"{service_url}/api/sync/attachments/{att_id}"
        try:
            req = urllib.request.Request(dl_url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, ConnectionError) as e:
            if not quiet:
                print(f"specs: attachment download failed for '{filename}' — {e}", file=sys.stderr)
            report["skipped_errors"] += 1
            continue

        try:
            atomic_write(local_path, content, binary=True)
            report["synced"] += 1
        except OSError as e:
            if not quiet:
                print(f"specs: failed to write attachment '{local_path}' — {e}", file=sys.stderr)
            report["skipped_errors"] += 1
            continue

    # ---- Deletion handling: trash / prune / keep ----
    if delete_mode != "keep":
        local_index = _scan_local_specs(specs_path)
        for doc_id, local_path in local_index.items():
            if doc_id in remote_doc_ids:
                continue
            # Orphan — not in remote manifest
            try:
                if delete_mode == "prune":
                    os.unlink(local_path)
                else:
                    trash_move(specs_path, local_path)
                report["trashed"] += 1
            except OSError as e:
                if not quiet:
                    print(f"specs: could not {delete_mode} orphan '{local_path}' — {e}", file=sys.stderr)

    # ---- Advance sync cursor + full-sync timestamp ----
    if manifest_cursor:
        report["cursor"] = manifest_cursor
        if state is not None:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            state_update_project(
                state,
                project_id,
                last_sync_cursor=manifest_cursor,
                last_full_sync=now_iso,
                last_pulled_at=now_iso,
            )

    return report


# ---------------------------------------------------------------------------
# Pull (all projects)
# ---------------------------------------------------------------------------

def pull(project_filter=None, quiet=False, delete_mode="trash", force_full=False):
    """Pull specs for all configured projects (or a specific one)."""
    cfg = config.read_config()
    if not cfg:
        if not quiet:
            print("specs: no config found — create .claude/specs.md or .claude/specs.local.md", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        if not quiet:
            print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    projects = cfg["projects"]
    project_root = cfg["project_root"]

    if project_filter:
        projects = [p for p in projects if p["id"] == project_filter]
        if not projects:
            print(f"specs: project '{project_filter}' not in config", file=sys.stderr)
            sys.exit(1)

    # Load the sync state file once; pull_project mutates it per project.
    state = state_load(project_root)

    total_synced = 0
    total_unchanged = 0
    total_trashed = 0
    total_conflicts = []
    total_errors = 0

    for proj in projects:
        report = pull_project(
            proj["id"], proj["path"], service_url, headers,
            state=state,
            delete_mode=delete_mode,
            force_full=force_full,
            quiet=quiet,
        )
        total_synced += report["synced"]
        total_unchanged += report["unchanged"]
        total_trashed += report["trashed"]
        total_conflicts.extend(report["conflicts"])
        total_errors += report["skipped_errors"]

        if not quiet:
            parts = []
            if report["synced"]:
                parts.append(f"{report['synced']} updated")
            if report["unchanged"]:
                parts.append(f"{report['unchanged']} unchanged")
            if report["trashed"]:
                label = "pruned" if delete_mode == "prune" else "trashed"
                parts.append(f"{report['trashed']} {label}")
            if report["conflicts"]:
                parts.append(f"{len(report['conflicts'])} conflict{'s' if len(report['conflicts']) != 1 else ''}")
            if report["skipped_errors"]:
                parts.append(f"{report['skipped_errors']} errors")
            if parts:
                print(f"specs: {proj['id']} — {', '.join(parts)}")

    # Persist state after all projects processed so partial failures don't
    # leave a stale cursor (we still advance per-project in pull_project).
    try:
        state_save(project_root, state)
    except OSError as e:
        if not quiet:
            print(f"specs: warning — failed to save state: {e}", file=sys.stderr)

    if not quiet:
        if total_conflicts:
            print()
            print(f"specs: {len(total_conflicts)} conflict{'s' if len(total_conflicts) != 1 else ''} — local drift + remote change:", file=sys.stderr)
            for path in total_conflicts:
                print(f"  {path}  ({path}.remote written alongside)", file=sys.stderr)
            print("  Review .remote files, reconcile manually, delete .remote files, then push.", file=sys.stderr)
        if total_synced == 0 and total_unchanged == 0 and total_trashed == 0 and not total_conflicts:
            print(f"specs: pulled {len(projects)} project(s) — no changes")


# ---------------------------------------------------------------------------
# Log — stream audit events for a project (spec 010 phase 4)
# ---------------------------------------------------------------------------

_ENTITY_BADGES = {
    "feature":        ("feat",   "\033[35m"),
    "document":       ("doc",    "\033[34m"),
    "version":        ("ver",    "\033[32m"),
    "comment":        ("cmt",    "\033[33m"),
    "review":         ("rev",    "\033[95m"),
    "backlog":        ("bklg",   "\033[36m"),
    "bug":            ("bug",    "\033[31m"),
    "bug_comment":    ("bug·c",  "\033[31m"),
    "attachment":     ("att",    "\033[37m"),
    "project":        ("proj",   "\033[96m"),
    "project_access": ("access", "\033[91m"),
    "project_domain": ("domain", "\033[92m"),
    "client":         ("client", "\033[35m"),
    "portal_user":    ("user",   "\033[95m"),
    "api_key":        ("key",    "\033[33m"),
    "auth_token":     ("token",  "\033[33m"),
    "system":         ("sys",    "\033[90m"),
}
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"


def _parse_since(since_str):
    """Parse '--since' into a duration or absolute date.

    Accepts:
      '7d', '24h', '30m'  — durations relative to now
      '2026-04-01'         — absolute ISO date

    Returns a datetime in UTC, or None if the string can't be parsed.
    """
    if not since_str:
        return None
    s = since_str.strip()
    # Duration: Nd, Nh, Nm, Nw
    m = re.match(r"^(\d+)([smhdw])$", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        delta = {
            "s": timedelta(seconds=n),
            "m": timedelta(minutes=n),
            "h": timedelta(hours=n),
            "d": timedelta(days=n),
            "w": timedelta(weeks=n),
        }[unit]
        return datetime.now(timezone.utc) - delta
    # Absolute ISO date/datetime
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _relative_time(iso_str):
    """Relative time for log display — e.g. '3m ago', '2h ago', '5d ago'."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return iso_str
    diff = datetime.now(timezone.utc) - dt
    secs = int(diff.total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    if secs < 86400 * 7:
        return f"{secs // 86400}d ago"
    return dt.strftime("%Y-%m-%d")


def specs_log(
    project_id,
    since=None,
    author=None,
    entity_type=None,
    limit=50,
    as_json=False,
    since_last_visit=False,
    mark_read=False,
):
    """Stream audit events for a project, or for all configured projects when
    project_id is None (`--all`). Events from every project are merged and
    sorted by timestamp so "what happened yesterday" works across the whole
    workspace.
    """
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found — create .claude/specs.md or .claude/specs.local.md", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    # Pick the project list: one specific project, or all configured ones
    if project_id is None:
        projects_to_query = cfg["projects"]
        if not projects_to_query:
            print("specs: no projects configured", file=sys.stderr)
            sys.exit(1)
    else:
        if not any(p["id"] == project_id for p in cfg["projects"]):
            print(f"specs: project '{project_id}' not in config", file=sys.stderr)
            sys.exit(1)
        projects_to_query = [p for p in cfg["projects"] if p["id"] == project_id]

    service_url = cfg["service_url"]
    project_root = cfg["project_root"]
    state = state_load(project_root)

    # Build the per-project query params (same for each project except since-cursor)
    base_qs = {"limit": str(min(max(limit, 1), 1000))}

    # Only apply current-user filter for --since-last-visit (matches prior behavior)
    if since_last_visit:
        base_qs["order"] = "asc"  # chronological so we can find the newest event
        current_actor = headers.get("X-Actor") or _current_user_email(headers)
        if current_actor:
            base_qs["actor_not"] = current_actor
    else:
        base_qs["order"] = "desc"

    if author:
        base_qs["actor"] = author
    if entity_type:
        base_qs["entity_type"] = entity_type

    from urllib.parse import urlencode

    # Fetch from every selected project, attach project_id to each event so
    # the display can call it out, and merge.
    all_events = []
    per_project_newest = {}  # project_id → newest event id (for --mark-read)
    errors = []

    for proj in projects_to_query:
        pid = proj["id"]
        qs = dict(base_qs)
        if since_last_visit:
            proj_state = state_get_project(state, pid)
            cursor = proj_state.get("last_visit_cursor")
            if cursor:
                qs["since"] = cursor

        url = f"{service_url}/api/sync/projects/{pid}/changes?{urlencode(qs)}"
        try:
            status, body = api_request(url, headers=headers)
        except ConnectionError as e:
            errors.append(f"{pid}: {e}")
            continue

        if status == 401:
            print("specs: authentication expired — run /awolve-spec:login", file=sys.stderr)
            sys.exit(1)
        if status != 200:
            errors.append(f"{pid}: HTTP {status}")
            continue

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            errors.append(f"{pid}: invalid JSON response")
            continue

        project_events = data.get("events", [])
        # Tag each event with its project id so multi-project output can show it
        for ev in project_events:
            ev["_projectId"] = pid
        all_events.extend(project_events)

        if project_events:
            # Record newest id for --mark-read regardless of order direction
            ids = [e["id"] for e in project_events]
            per_project_newest[pid] = max(ids)

    # Client-side --since filter (display convenience; server pages on ids, not timestamps)
    since_dt = _parse_since(since)
    if since_dt:
        all_events = [
            e for e in all_events
            if _parse_iso(e.get("createdAt", "")) and _parse_iso(e["createdAt"]) >= since_dt
        ]

    # Merge: sort by id (ULIDs sort lexicographically by time). Display order
    # matches the per-project order chosen above.
    all_events.sort(key=lambda e: e["id"], reverse=(base_qs["order"] == "desc"))

    # Apply the combined limit after the merge — otherwise "--limit 50 --all"
    # would return up to 50 × N projects events.
    all_events = all_events[: int(base_qs["limit"])]

    if as_json:
        print(json.dumps(all_events, indent=2))
    else:
        multi_project = len(projects_to_query) > 1
        _print_log_events(all_events, since_last_visit=since_last_visit, multi_project=multi_project)

    # --mark-read: advance the visit cursor per project
    if mark_read and per_project_newest:
        for pid, newest_id in per_project_newest.items():
            state_update_project(state, pid, last_visit_cursor=newest_id)
        try:
            state_save(project_root, state)
            if project_id is None:
                print(f"\nspecs: marked {len(per_project_newest)} project(s) read", file=sys.stderr)
            else:
                print(f"\nspecs: marked read up to {per_project_newest[project_id]}", file=sys.stderr)
        except OSError as e:
            print(f"specs: warning — failed to save state: {e}", file=sys.stderr)

    # Surface per-project errors at the end so they don't drown out successes
    for err in errors:
        print(f"specs: log skipped {err}", file=sys.stderr)


def _print_log_events(events, since_last_visit=False, multi_project=False):
    """Render log events in human-readable colored output.

    When `multi_project` is True, each row is prefixed with the originating
    project id so a merged cross-project feed stays legible.
    """
    if not events:
        if since_last_visit:
            print("(no new events since your last visit)")
        else:
            print("(no events)")
        return

    # Compute column width for project id so the output stays aligned
    proj_width = 0
    if multi_project:
        proj_width = max((len(ev.get("_projectId", "")) for ev in events), default=0)

    # Group by day
    last_day = None
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev["createdAt"].replace("Z", "+00:00"))
        except ValueError:
            continue
        day = dt.strftime("%Y-%m-%d")
        if day != last_day:
            if last_day is not None:
                print()
            print(f"{_BOLD}{day}{_RESET}")
            last_day = day

        badge_label, badge_color = _ENTITY_BADGES.get(
            ev["entityType"], (ev["entityType"][:6], "\033[37m"),
        )
        time_str = dt.strftime("%H:%M")
        relative = _relative_time(ev["createdAt"])
        proj_prefix = ""
        if multi_project:
            proj_prefix = f"{_DIM}[{ev.get('_projectId', '?'):{proj_width}}]{_RESET}  "
        print(
            f"  {_DIM}{time_str}{_RESET}  "
            f"{proj_prefix}"
            f"{badge_color}{badge_label:>8}{_RESET}  "
            f"{ev['summary']}  "
            f"{_DIM}— {ev['actor']} · {relative}{_RESET}"
        )


def _parse_iso(s):
    """Parse an ISO timestamp, returning None on failure."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _current_user_email(headers):
    """Best-effort lookup of the current user's email from the auth state.

    Used by `--since-last-visit` to set actor_not. Falls back to None if we
    can't determine it — in which case the user will see their own events
    in the feed, but nothing breaks.
    """
    try:
        return auth.get_current_user_email()  # type: ignore[attr-defined]
    except AttributeError:
        return None


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

def push(file_path):
    """Push a single spec file to the service."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found — create .claude/specs.md or .claude/specs.local.md", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    abs_path = os.path.abspath(file_path)

    # Find which project this file belongs to
    proj = config.find_project_for_file(cfg, abs_path)
    if not proj:
        print(f"specs: {file_path} is not inside any configured specs path", file=sys.stderr)
        sys.exit(1)

    # Read file
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError) as e:
        print(f"specs: cannot read {file_path} — {e}", file=sys.stderr)
        sys.exit(1)

    meta, body = parse_frontmatter(content)
    doc_id = meta.get("spec_doc_id")
    base_version = meta.get("spec_version")

    if not doc_id:
        print(f"specs: {file_path} has no spec_doc_id — skipping", file=sys.stderr)
        return

    if base_version is None:
        print(f"specs: {file_path} has no spec_version — skipping", file=sys.stderr)
        return

    # Safety: strip any leaked frontmatter from body (e.g. double frontmatter)
    body = strip_frontmatter(body)

    # Push
    push_url = f"{service_url}/api/sync/documents/{doc_id}/content?base_version={base_version}"
    headers["Content-Type"] = "text/markdown; charset=utf-8"

    try:
        status_code, resp_body = api_request(push_url, method="PUT", headers=headers, data=body.strip())
    except ConnectionError as e:
        print(f"specs: push failed — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code == 409:
        print(f"specs: CONFLICT — remote has newer version. Pull first.", file=sys.stderr)
        return
    if status_code == 401:
        print("specs: authentication expired — run /awolve-spec:login", file=sys.stderr)
        sys.exit(1)
    if status_code not in (200, 201, 204):
        print(f"specs: push failed (HTTP {status_code}): {resp_body}", file=sys.stderr)
        sys.exit(1)

    # Update local frontmatter
    try:
        resp_data = json.loads(resp_body) if resp_body.strip() else {}
    except json.JSONDecodeError:
        resp_data = {}

    new_version = resp_data.get("version", base_version + 1)
    meta["spec_version"] = new_version
    meta["last_synced"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Record the body hash we just pushed so future pulls can detect local
    # drift correctly. Without this, a subsequent manual edit would look
    # indistinguishable from an unmodified synced file.
    meta["last_synced_hash"] = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()

    atomic_write(abs_path, render_frontmatter(meta, body))

    rel = os.path.relpath(abs_path, proj["path"])
    print(f"specs: pushed {proj['id']}/{rel} (v{new_version})")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def show_status():
    """Show sync status of all configured projects."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found — create .claude/specs.md or .claude/specs.local.md — create .claude/specs.md (shared) or .claude/specs.local.md (personal)", file=sys.stderr)
        sys.exit(1)

    print(f"specs: {len(cfg['projects'])} project(s) configured")
    print(f"  service: {cfg['service_url']}")
    print()

    for proj in cfg["projects"]:
        specs_path = proj["path"]
        print(f"  {proj['id']}")
        print(f"    path: {specs_path}")

        if not os.path.isdir(specs_path):
            print(f"    (directory not found)")
            print()
            continue

        found = 0
        for root, _dirs, files in os.walk(specs_path):
            for fname in sorted(files):
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read(2048)
                except (IOError, OSError):
                    continue
                meta, _ = parse_frontmatter(content)
                if not meta.get("spec_doc_id"):
                    continue
                rel = os.path.relpath(fpath, specs_path)
                version = meta.get("spec_version", "?")
                last_synced = meta.get("last_synced", "never")
                print(f"    {rel:40s}  v{version}  synced: {last_synced}")
                found += 1

        if found == 0:
            print(f"    (no synced spec files)")
        print()


# ---------------------------------------------------------------------------
# PostToolUse hook
# ---------------------------------------------------------------------------

def handle_post_tool_use():
    """Read PostToolUse JSON from stdin. Push if a spec file was edited."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return

    if not raw.strip():
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    cfg = config.read_config()
    if not cfg:
        return

    # Check if file is inside any configured project's specs path
    proj = config.find_project_for_file(cfg, file_path)
    if not proj:
        return

    # Check that file has spec frontmatter
    abs_file = os.path.abspath(file_path)
    if not os.path.isfile(abs_file):
        return
    try:
        with open(abs_file, "r", encoding="utf-8") as f:
            content = f.read(2048)
    except (IOError, OSError):
        return

    meta, _ = parse_frontmatter(content)
    if not meta.get("spec_doc_id"):
        return

    try:
        push(file_path)
    except SystemExit as e:
        # push() calls sys.exit(1) on errors — catch it so the error
        # message (already printed to stderr by push()) is visible
        # instead of silently dying
        if e.code != 0:
            print(f"specs: auto-push failed for {os.path.basename(file_path)} — see error above", file=sys.stderr)
    except Exception as e:
        print(f"specs: auto-push failed for {os.path.basename(file_path)} — {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Set status
# ---------------------------------------------------------------------------

FEATURE_STATUSES = ["idea", "specifying", "in_progress", "completed", "archived"]
DOCUMENT_STATUSES = ["specifying", "ready", "approved"]


def set_status(identifier, new_status):
    """
    Set the status of a feature or document.

    identifier can be:
    - A feature ID like "my-project/001-feature-name"
    - A document UUID (spec_doc_id from frontmatter)
    - A local file path (reads doc_id from frontmatter)
    """
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]

    # Determine if this is a feature or document
    is_file_path = os.path.isfile(identifier)
    is_feature_id = "/" in identifier and not is_file_path

    if is_file_path:
        # Read doc_id from frontmatter
        with open(identifier, "r", encoding="utf-8") as f:
            content = f.read()
        meta, _ = parse_frontmatter(content)
        doc_id = meta.get("spec_doc_id")
        if not doc_id:
            print(f"specs: {identifier} has no spec_doc_id in frontmatter", file=sys.stderr)
            sys.exit(1)

        if new_status not in DOCUMENT_STATUSES:
            print(f"specs: invalid document status '{new_status}'. Must be one of: {', '.join(DOCUMENT_STATUSES)}", file=sys.stderr)
            sys.exit(1)

        status_code, resp_body = api_request(
            f"{service_url}/api/documents/{doc_id}",
            method="PATCH",
            headers={**headers, "Content-Type": "application/json"},
            data={"status": new_status},
        )
        if status_code not in (200, 201):
            print(f"specs: failed to update document status (HTTP {status_code}): {resp_body}", file=sys.stderr)
            sys.exit(1)

        rel = os.path.basename(identifier)
        print(f"specs: document {rel} → {new_status}")

    elif is_feature_id:
        if new_status not in FEATURE_STATUSES:
            print(f"specs: invalid feature status '{new_status}'. Must be one of: {', '.join(FEATURE_STATUSES)}", file=sys.stderr)
            sys.exit(1)

        import urllib.parse
        encoded_id = urllib.parse.quote(identifier, safe="")
        status_code, resp_body = api_request(
            f"{service_url}/api/features/lookup?id={encoded_id}",
            method="PATCH",
            headers={**headers, "Content-Type": "application/json"},
            data={"status": new_status},
        )
        if status_code not in (200, 201):
            print(f"specs: failed to update feature status (HTTP {status_code}): {resp_body}", file=sys.stderr)
            sys.exit(1)

        print(f"specs: feature {identifier} → {new_status}")

    else:
        # Try as document UUID
        if new_status in DOCUMENT_STATUSES:
            status_code, resp_body = api_request(
                f"{service_url}/api/documents/{identifier}",
                method="PATCH",
                headers={**headers, "Content-Type": "application/json"},
                data={"status": new_status},
            )
            if status_code in (200, 201):
                print(f"specs: document {identifier} → {new_status}")
                return

        # Try as feature ID without slash — collect all matches first to
        # detect ambiguity (bug #9: same feature name in multiple projects).
        if new_status in FEATURE_STATUSES:
            import urllib.parse
            matches = []  # [(feature_id, project_id, entry), ...]
            for proj in cfg["projects"]:
                specs_path = proj["path"]
                if not os.path.isdir(specs_path):
                    continue
                for entry in os.listdir(specs_path):
                    if entry == identifier or entry.endswith(identifier):
                        matches.append((f"{proj['id']}/{entry}", proj["id"], entry))

            if len(matches) > 1:
                projects_list = ", ".join(m[1] for m in matches)
                print(
                    f"specs: feature name '{identifier}' exists in multiple projects: {projects_list}\n"
                    f"  Use the qualified form: specs-cli.py set-status <project>/<feature> <status>",
                    file=sys.stderr,
                )
                sys.exit(1)

            if len(matches) == 1:
                feature_id = matches[0][0]
                encoded_id = urllib.parse.quote(feature_id, safe="")
                status_code, resp_body = api_request(
                    f"{service_url}/api/features/lookup?id={encoded_id}",
                    method="PATCH",
                    headers={**headers, "Content-Type": "application/json"},
                    data={"status": new_status},
                )
                if status_code in (200, 201):
                    print(f"specs: feature {feature_id} → {new_status}")
                    return

        print(f"specs: could not find feature or document '{identifier}'", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Bugs
# ---------------------------------------------------------------------------

BUG_SEVERITIES = ["low", "medium", "high", "critical"]
BUG_STATUSES = ["open", "triaged", "in_progress", "resolved", "closed"]


def list_bugs(project_id=None):
    """List bugs for a project or all configured projects."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    projects = cfg["projects"]

    if project_id:
        projects = [p for p in projects if p["id"] == project_id]
        if not projects:
            print(f"specs: project '{project_id}' not in config", file=sys.stderr)
            sys.exit(1)

    for proj in projects:
        url = f"{service_url}/api/portal/projects/{proj['id']}/bugs"
        try:
            status_code, body = api_request(url, headers=headers)
        except ConnectionError as e:
            print(f"specs: failed to fetch bugs for '{proj['id']}' — {e}", file=sys.stderr)
            continue

        if status_code != 200:
            print(f"specs: failed to fetch bugs for '{proj['id']}' (HTTP {status_code})", file=sys.stderr)
            continue

        bugs = json.loads(body)
        open_bugs = [b for b in bugs if b.get("status") not in ("closed", "resolved")]

        if len(projects) > 1:
            print(f"\n{proj['id']} ({len(open_bugs)} open)")
        else:
            print(f"specs: {len(open_bugs)} open bug(s) in '{proj['id']}'")

        if not open_bugs:
            print("  (no open bugs)")
            continue

        print()
        for bug in open_bugs:
            severity = bug.get("severity", "?")
            status = bug.get("status", "?")
            number = bug.get("number", "?")
            title = bug.get("title", "untitled")
            reporter = bug.get("reporterName") or bug.get("reporterEmail", "?")
            sev_marker = {"critical": "!!!", "high": "!!", "medium": "!", "low": "."}.get(severity, "?")
            print(f"  #{number:<4} [{sev_marker}] {title}")
            print(f"        {status} — reported by {reporter}")


def view_bug(project_id, bug_number, as_json=False):
    """Show full details for a single bug by its short number."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    projects = [p for p in cfg["projects"] if p["id"] == project_id]
    if not projects:
        print(f"specs: project '{project_id}' not in config", file=sys.stderr)
        sys.exit(1)

    try:
        number = int(str(bug_number).lstrip("#"))
    except ValueError:
        print(f"specs: bug number must be an integer, got '{bug_number}'", file=sys.stderr)
        sys.exit(1)

    url = f"{service_url}/api/portal/projects/{project_id}/bugs"
    try:
        status_code, body = api_request(url, headers=headers)
    except ConnectionError as e:
        print(f"specs: failed to fetch bugs — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code != 200:
        print(f"specs: failed to fetch bugs (HTTP {status_code})", file=sys.stderr)
        sys.exit(1)

    bugs = json.loads(body)
    match = next((b for b in bugs if b.get("number") == number), None)
    if not match:
        print(f"specs: bug #{number} not found in '{project_id}'", file=sys.stderr)
        sys.exit(1)

    if as_json:
        print(json.dumps(match, indent=2))
        return

    severity = match.get("severity", "?")
    sev_marker = {"critical": "!!!", "high": "!!", "medium": "!", "low": "."}.get(severity, "?")
    reporter = match.get("reporterName") or match.get("reporterEmail", "?")
    title = match.get("title", "untitled")
    status = match.get("status", "?")
    created = match.get("createdAt", "?")
    updated = match.get("updatedAt", "?")
    description = match.get("description") or "(no description)"
    steps = match.get("steps")
    expected = match.get("expected")
    actual = match.get("actual")
    environment = match.get("environment")
    comment_count = match.get("commentCount", 0)

    print(f"#{number} [{sev_marker} {severity}] {title}")
    print(f"  status:    {status}")
    print(f"  reporter:  {reporter}")
    print(f"  created:   {created}")
    if updated != created:
        print(f"  updated:   {updated}")
    if environment:
        print(f"  env:       {environment}")
    print(f"  comments:  {comment_count}")
    print(f"  portal:    {service_url}/portal/{project_id}/bugs/{match.get('id', '')}")
    print()
    print("Description:")
    print(description)
    if steps:
        print("\nSteps to reproduce:")
        print(steps)
    if expected:
        print("\nExpected:")
        print(expected)
    if actual:
        print("\nActual:")
        print(actual)


def set_bug_status(project_id, bug_number, status):
    """Update a bug's status by its short number."""
    if status not in BUG_STATUSES:
        print(f"specs: invalid status '{status}'. Valid: {', '.join(BUG_STATUSES)}", file=sys.stderr)
        sys.exit(1)

    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    projects = [p for p in cfg["projects"] if p["id"] == project_id]
    if not projects:
        print(f"specs: project '{project_id}' not in config", file=sys.stderr)
        sys.exit(1)

    try:
        number = int(str(bug_number).lstrip("#"))
    except ValueError:
        print(f"specs: bug number must be an integer, got '{bug_number}'", file=sys.stderr)
        sys.exit(1)

    # Resolve short number to UUID by fetching the project's bug list.
    list_url = f"{service_url}/api/portal/projects/{project_id}/bugs"
    try:
        status_code, body = api_request(list_url, headers=headers)
    except ConnectionError as e:
        print(f"specs: failed to fetch bugs — {e}", file=sys.stderr)
        sys.exit(1)
    if status_code != 200:
        print(f"specs: failed to fetch bugs (HTTP {status_code})", file=sys.stderr)
        sys.exit(1)

    bugs = json.loads(body)
    match = next((b for b in bugs if b.get("number") == number), None)
    if not match:
        print(f"specs: bug #{number} not found in '{project_id}'", file=sys.stderr)
        sys.exit(1)

    bug_id = match["id"]
    patch_url = f"{service_url}/api/portal/bugs/{bug_id}"
    try:
        status_code, body = api_request(patch_url, method="PATCH", headers=headers, data={"status": status})
    except ConnectionError as e:
        print(f"specs: failed to update bug — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code != 200:
        print(f"specs: failed to update bug #{number} (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    print(f"specs: bug #{number} '{match.get('title', '')}' → {status}")


def list_backlog(project_id=None, view="tree", status_filter=None, priority_filter=None):
    """List backlog items for a project or all configured projects.

    Spec 013:
      view='tree'  (default) — group items by parent: epic header + indented children
      view='epics' — show only top-level items that have at least one child
      view='flat'  — flat list, no grouping (legacy behavior)
    Filters: optional status (single value) and priority (single value).
    """
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    projects = cfg["projects"]

    if project_id:
        projects = [p for p in projects if p["id"] == project_id]
        if not projects:
            print(f"specs: project '{project_id}' not in config", file=sys.stderr)
            sys.exit(1)

    for proj in projects:
        url = f"{service_url}/api/portal/projects/{proj['id']}/backlog"
        try:
            status_code, body = api_request(url, headers=headers)
        except ConnectionError as e:
            print(f"specs: failed to fetch backlog for '{proj['id']}' — {e}", file=sys.stderr)
            continue

        if status_code != 200:
            print(f"specs: failed to fetch backlog for '{proj['id']}' (HTTP {status_code})", file=sys.stderr)
            continue

        items = json.loads(body)
        active = [i for i in items if i.get("status") not in ("completed", "archived")]
        if status_filter:
            active = [i for i in active if i.get("status") == status_filter]
        if priority_filter:
            active = [i for i in active if i.get("priority") == priority_filter]

        if len(projects) > 1:
            print(f"\n{proj['id']} ({len(active)} active)")
        else:
            print(f"specs: {len(active)} active backlog item(s) in '{proj['id']}'")

        if not active:
            print("  (no active items)")
            continue

        print()
        if view == "flat":
            for item in active:
                _print_backlog_row(item, indent=0)
        elif view == "epics":
            epics = [i for i in active if i.get("isEpic")]
            if not epics:
                print("  (no epics)")
            for item in epics:
                _print_backlog_row(item, indent=0)
        else:  # tree
            children_by_parent = {}
            for it in active:
                pid = it.get("parentId")
                if pid:
                    children_by_parent.setdefault(pid, []).append(it)
            for item in active:
                if item.get("parentId"):
                    continue
                _print_backlog_row(item, indent=0)
                kids = children_by_parent.get(item.get("id"), [])
                for k in kids:
                    _print_backlog_row(k, indent=2)


def _print_backlog_row(item, indent=0):
    pad = " " * indent
    priority = item.get("priority", "?")
    status = item.get("status", "?")
    title = item.get("title", "untitled")
    number = item.get("number")
    feature_id = item.get("featureId")
    is_epic = item.get("isEpic", False)
    pri_marker = {"high": "!!!", "medium": "!!", "low": "!"}.get(priority, "?")
    promoted = f" → {feature_id}" if feature_id else ""
    histogram = ""
    counts = item.get("childStatusCounts") or {}
    if counts:
        order = ["idea", "planned", "in_progress", "completed", "archived"]
        parts = [f"{counts[s]} {s}" for s in order if counts.get(s)]
        histogram = " · children: " + " · ".join(parts) if parts else ""
    elif is_epic:
        histogram = " · (no items yet)"
    num_str = f"#{number} " if number else ""
    epic_tag = "[EPIC] " if is_epic else ""
    print(f"  {pad}[{pri_marker}] {num_str}{epic_tag}{title}{histogram}")
    print(f"       {pad}{status}{promoted}")


def _resolve_backlog_id(headers, service_url, project_id, ref):
    """Resolve a backlog reference (uuid, '#42', or '42') to its uuid id within a project.

    Returns (id, item_dict) or (None, None) if not found.
    """
    if not ref:
        return (None, None)
    s = str(ref).lstrip("#").strip()
    # If it looks like a UUID (has dashes), treat as id
    if "-" in s and len(s) >= 32:
        # Fetch via list (single round-trip, project-scoped)
        url = f"{service_url}/api/portal/projects/{project_id}/backlog"
        sc, body = api_request(url, headers=headers)
        if sc != 200:
            return (None, None)
        for it in json.loads(body):
            if it.get("id") == s:
                return (s, it)
        return (None, None)
    # Otherwise treat as numeric #N
    try:
        n = int(s)
    except ValueError:
        return (None, None)
    url = f"{service_url}/api/portal/projects/{project_id}/backlog"
    sc, body = api_request(url, headers=headers)
    if sc != 200:
        return (None, None)
    for it in json.loads(body):
        if it.get("number") == n:
            return (it.get("id"), it)
    return (None, None)


def create_backlog_item(project_id, title, description=None, priority="medium", parent=None, is_epic=False):
    """Create a new backlog item. `parent` may be a uuid or a numeric #N reference.
    `is_epic=True` marks this item as an epic (can have children, can't have a parent)."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    if is_epic and parent:
        print("specs: --epic and --parent are mutually exclusive (epics can't have a parent)", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]

    parent_id = None
    if parent:
        parent_id, parent_item = _resolve_backlog_id(headers, service_url, project_id, parent)
        if not parent_id:
            print(f"specs: parent '{parent}' not found in project '{project_id}'", file=sys.stderr)
            sys.exit(1)
        if not parent_item.get("isEpic"):
            print(f"specs: '#{parent_item.get('number')}' is not an epic — only epics can have children", file=sys.stderr)
            sys.exit(1)

    url = f"{service_url}/api/portal/projects/{project_id}/backlog"
    payload = {"title": title, "description": description, "priority": priority}
    if parent_id:
        payload["parentId"] = parent_id
    if is_epic:
        payload["isEpic"] = True

    try:
        status_code, body = api_request(
            url, method="POST",
            headers={**headers, "Content-Type": "application/json"},
            data=payload,
        )
    except ConnectionError as e:
        print(f"specs: failed to create backlog item — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 201):
        print(f"specs: failed to create backlog item (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    item = json.loads(body)
    kind = "epic" if is_epic else "backlog item"
    parent_note = f" under epic '{parent}'" if parent_id else ""
    print(f"specs: created {kind} '{item.get('title')}' in '{project_id}' (priority: {item.get('priority')}){parent_note}")


def set_backlog_parent(project_id, item_ref, parent_ref):
    """Set or clear the parent of a backlog item. parent_ref of 'none' clears."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]

    item_id, item = _resolve_backlog_id(headers, service_url, project_id, item_ref)
    if not item_id:
        print(f"specs: item '{item_ref}' not found in project '{project_id}'", file=sys.stderr)
        sys.exit(1)

    if str(parent_ref).lower() in ("none", "null", ""):
        new_parent_id = None
    else:
        new_parent_id, new_parent_item = _resolve_backlog_id(headers, service_url, project_id, parent_ref)
        if not new_parent_id:
            print(f"specs: parent '{parent_ref}' not found in project '{project_id}'", file=sys.stderr)
            sys.exit(1)
        if not new_parent_item.get("isEpic"):
            print(f"specs: '#{new_parent_item.get('number')}' is not an epic — only epics can have children", file=sys.stderr)
            sys.exit(1)

    url = f"{service_url}/api/portal/backlog/{item_id}"
    try:
        status_code, body = api_request(
            url, method="PATCH",
            headers={**headers, "Content-Type": "application/json"},
            data={"parentId": new_parent_id},
        )
    except ConnectionError as e:
        print(f"specs: failed to update parent — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 201):
        try:
            err = json.loads(body).get("error", body)
        except (json.JSONDecodeError, AttributeError):
            err = body
        print(f"specs: failed to update parent (HTTP {status_code}): {err}", file=sys.stderr)
        sys.exit(1)

    if new_parent_id:
        print(f"specs: '#{item.get('number')}' is now a child of '{parent_ref}'")
    else:
        print(f"specs: '#{item.get('number')}' parent cleared (now top-level)")


def _embed_images(description, image_paths):
    """Append base64-encoded images to the description markdown."""
    import base64
    import mimetypes
    for path in image_paths:
        abs_path = os.path.abspath(path)
        if not os.path.isfile(abs_path):
            print(f"specs: image not found: {path}", file=sys.stderr)
            continue
        mime = mimetypes.guess_type(abs_path)[0] or "image/png"
        with open(abs_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        name = os.path.basename(abs_path)
        description += f"\n\n![{name}](data:{mime};base64,{data})"
    return description


def create_bug(project_id, title, description, severity="medium", image_paths=None):
    """Create a bug report, optionally with attached images."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    if severity not in BUG_SEVERITIES:
        print(f"specs: invalid severity '{severity}'. Must be one of: {', '.join(BUG_SEVERITIES)}", file=sys.stderr)
        sys.exit(1)

    # Embed images into description
    if image_paths:
        description = _embed_images(description, image_paths)

    service_url = cfg["service_url"]

    url = f"{service_url}/api/portal/projects/{project_id}/bugs"
    try:
        status_code, body = api_request(
            url, method="POST", headers={**headers, "Content-Type": "application/json"},
            data={"title": title, "description": description, "severity": severity},
        )
    except ConnectionError as e:
        print(f"specs: failed to create bug — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 201):
        print(f"specs: failed to create bug (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    bug = json.loads(body)
    print(f"specs: bug #{bug.get('number', '?')} created — {title}")
    print(f"  view: {service_url}/portal/{project_id}/bugs/{bug['id']}")


# ---------------------------------------------------------------------------
# Feature management
# ---------------------------------------------------------------------------

def _next_spec_number(specs_path):
    """Determine the next spec number by scanning existing folders."""
    if not os.path.isdir(specs_path):
        return 1
    max_num = 0
    for entry in os.listdir(specs_path):
        m = re.match(r"^(\d+)-", entry)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return max_num + 1


def _find_project(cfg, project_id):
    """Find a project in config by ID. Returns project dict or exits."""
    for proj in cfg["projects"]:
        if proj["id"] == project_id:
            return proj
    print(f"specs: project '{project_id}' not in config", file=sys.stderr)
    sys.exit(1)


def set_description(feature_id, description):
    """Set or clear a feature's shortDescription. Pass "" to clear."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    if "/" not in feature_id:
        print(f"specs: feature id must be 'project/name' (got '{feature_id}')", file=sys.stderr)
        sys.exit(1)

    import urllib.parse
    service_url = cfg["service_url"]
    encoded_id = urllib.parse.quote(feature_id, safe="")
    status_code, resp_body = api_request(
        f"{service_url}/api/features/lookup?id={encoded_id}",
        method="PATCH",
        headers={**headers, "Content-Type": "application/json"},
        data={"short_description": description},
    )
    if status_code not in (200, 201):
        print(f"specs: failed to update description (HTTP {status_code}): {resp_body}", file=sys.stderr)
        sys.exit(1)

    if description == "":
        print(f"specs: feature {feature_id} description cleared")
    else:
        print(f"specs: feature {feature_id} description updated")


def create_feature(project_id, name, initial_status="specifying", description=None):
    """Create a new feature in a project."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    proj = _find_project(cfg, project_id)
    specs_path = proj["path"]
    service_url = cfg["service_url"]

    # Determine folder name
    if re.match(r"^\d+-", name):
        folder_name = name
    else:
        num = _next_spec_number(specs_path)
        folder_name = f"{num:03d}-{name}"

    feature_id = f"{project_id}/{folder_name}"

    # Extract number from the folder name prefix (always present — we either
    # matched one in `name` above, or computed `num` and formatted it in).
    number_match = re.match(r"^(\d+)-", folder_name)
    feature_number = int(number_match.group(1)) if number_match else None

    # Create local folder
    local_dir = os.path.join(specs_path, folder_name)
    os.makedirs(local_dir, exist_ok=True)
    context_path = os.path.relpath(local_dir, os.getcwd())

    # Humanize folder name for title: "003-user-notifications" -> "User Notifications"
    title = re.sub(r"^\d+-", "", folder_name).replace("-", " ").title()

    # Register in service
    payload = {
        "project": project_id,
        "name": folder_name,
        "title": title,
        "contextPath": context_path,
    }
    if feature_number is not None:
        payload["number"] = feature_number

    try:
        status_code, body = api_request(
            f"{service_url}/api/features",
            method="POST",
            headers={**headers, "Content-Type": "application/json"},
            data=payload,
        )
    except ConnectionError as e:
        print(f"specs: failed to create feature — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code == 409:
        print(f"specs: feature '{feature_id}' already exists", file=sys.stderr)
        sys.exit(1)
    if status_code not in (200, 201):
        print(f"specs: failed to create feature (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    # Set status if not the API default ("draft")
    if initial_status != "draft":
        import urllib.parse
        encoded_id = urllib.parse.quote(feature_id, safe="")
        api_request(
            f"{service_url}/api/features/lookup?id={encoded_id}",
            method="PATCH",
            headers={**headers, "Content-Type": "application/json"},
            data={"status": initial_status},
        )

    # Set shortDescription if provided (POST /api/features doesn't accept it yet)
    if description is not None:
        import urllib.parse
        encoded_id = urllib.parse.quote(feature_id, safe="")
        status_code, resp_body = api_request(
            f"{service_url}/api/features/lookup?id={encoded_id}",
            method="PATCH",
            headers={**headers, "Content-Type": "application/json"},
            data={"short_description": description},
        )
        if status_code not in (200, 201):
            print(f"specs: warning — feature created but description PATCH failed (HTTP {status_code}): {resp_body}", file=sys.stderr)

    print(f"specs: created feature '{feature_id}'")
    print(f"  path: {local_dir}")
    print(f"  status: {initial_status}")
    print(f"  portal: {service_url}/portal/{project_id}/specs/{folder_name}")


def create_document(project_id, feature_name, filename):
    """Add a document to an existing feature."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    proj = _find_project(cfg, project_id)
    specs_path = proj["path"]
    service_url = cfg["service_url"]

    feature_id = f"{project_id}/{feature_name}"

    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    local_dir = os.path.join(specs_path, feature_name)
    if not os.path.isdir(local_dir):
        print(f"specs: feature folder not found: {local_dir}", file=sys.stderr)
        print(f"  run: specs-cli.py create-feature {project_id} {feature_name}", file=sys.stderr)
        sys.exit(1)

    local_path = os.path.join(local_dir, filename)
    if os.path.isfile(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()
        meta, _ = parse_frontmatter(content)
        if meta.get("spec_doc_id"):
            print(f"specs: {filename} already tracked (doc_id: {meta['spec_doc_id']})", file=sys.stderr)
            return

    # Read existing content or create placeholder
    if os.path.isfile(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            existing = f.read()
        _, initial_content = parse_frontmatter(existing)
        initial_content = initial_content.strip() or f"# {filename.replace('.md', '').replace('-', ' ').title()}"
    else:
        initial_content = f"# {filename.replace('.md', '').replace('-', ' ').title()}"

    # Register document in service
    import urllib.parse
    encoded_feature = urllib.parse.quote(feature_id, safe="")

    payload = {"filename": filename, "content": initial_content}
    try:
        status_code, body = api_request(
            f"{service_url}/api/features/lookup/documents?id={encoded_feature}",
            method="POST",
            headers={**headers, "Content-Type": "application/json"},
            data=payload,
        )
    except ConnectionError as e:
        print(f"specs: failed to create document — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 201):
        print(f"specs: failed to create document (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    resp = json.loads(body)
    doc_id = resp.get("id")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "spec_doc_id": doc_id,
        "spec_version": 1,
        "last_synced": now,
    }

    if os.path.isfile(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            existing_body = f.read()
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(render_frontmatter(meta, existing_body))
    else:
        title = filename.replace(".md", "").replace("-", " ").title()
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(render_frontmatter(meta, f"\n# {title}\n"))

    print(f"specs: created document '{filename}' in '{feature_id}'")
    print(f"  path: {local_path}")
    print(f"  doc_id: {doc_id}")


def _derive_title(slug):
    """Derive a human-readable title from a feature slug.

    '003-agentic-context-service' → 'Agentic Context Service'
    'my-feature' → 'My Feature'
    """
    name = re.sub(r"^\d+-", "", slug)
    return name.replace("-", " ").replace("_", " ").strip().title()


def rename_feature(project_id, old_name, new_name, title_override=None):
    """Rename a feature folder and update the service (name + title)."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    proj = _find_project(cfg, project_id)
    specs_path = proj["path"]
    service_url = cfg["service_url"]

    # Preserve number prefix
    old_match = re.match(r"^(\d+)-", old_name)
    new_match = re.match(r"^(\d+)-", new_name)
    if old_match and not new_match:
        new_name = f"{old_match.group(1)}-{new_name}"

    old_feature_id = f"{project_id}/{old_name}"
    new_feature_id = f"{project_id}/{new_name}"
    new_title = title_override or _derive_title(new_name)

    old_dir = os.path.join(specs_path, old_name)
    new_dir = os.path.join(specs_path, new_name)

    if not os.path.isdir(old_dir):
        print(f"specs: feature folder not found: {old_dir}", file=sys.stderr)
        sys.exit(1)

    if os.path.exists(new_dir):
        print(f"specs: target folder already exists: {new_dir}", file=sys.stderr)
        sys.exit(1)

    # Update service — send both name and title (bug #6 fix).
    import urllib.parse
    encoded_id = urllib.parse.quote(old_feature_id, safe="")

    try:
        status_code, body = api_request(
            f"{service_url}/api/features/lookup?id={encoded_id}",
            method="PATCH",
            headers={**headers, "Content-Type": "application/json"},
            data={"name": new_name, "title": new_title},
        )
    except ConnectionError as e:
        print(f"specs: failed to rename feature — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code == 409:
        print(f"specs: feature '{new_feature_id}' already exists in service", file=sys.stderr)
        sys.exit(1)
    if status_code not in (200, 201):
        print(f"specs: failed to rename feature (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    os.rename(old_dir, new_dir)

    print(f"specs: renamed '{old_feature_id}' → '{new_feature_id}'")
    print(f"  title: {new_title}")
    print(f"  path: {new_dir}")


def rename_document(file_path, new_filename):
    """Rename a document file and update the service."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    abs_path = os.path.abspath(file_path)

    if not os.path.isfile(abs_path):
        print(f"specs: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    if not new_filename.endswith(".md"):
        new_filename = f"{new_filename}.md"

    with open(abs_path, "r", encoding="utf-8") as f:
        content = f.read()
    meta, body = parse_frontmatter(content)
    doc_id = meta.get("spec_doc_id")

    if not doc_id:
        print(f"specs: {file_path} has no spec_doc_id — not tracked by service", file=sys.stderr)
        sys.exit(1)

    try:
        status_code, resp_body = api_request(
            f"{service_url}/api/documents/{doc_id}",
            method="PATCH",
            headers={**headers, "Content-Type": "application/json"},
            data={"filename": new_filename},
        )
    except ConnectionError as e:
        print(f"specs: failed to rename document — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code == 409:
        print(f"specs: document '{new_filename}' already exists in this feature", file=sys.stderr)
        sys.exit(1)
    if status_code not in (200, 201):
        print(f"specs: failed to rename document (HTTP {status_code}): {resp_body}", file=sys.stderr)
        sys.exit(1)

    new_path = os.path.join(os.path.dirname(abs_path), new_filename)
    os.rename(abs_path, new_path)

    print(f"specs: renamed '{os.path.basename(abs_path)}' → '{new_filename}'")
    print(f"  path: {new_path}")


def delete_document(file_path):
    """Delete a document from filesystem and service."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    abs_path = os.path.abspath(file_path)

    if not os.path.isfile(abs_path):
        print(f"specs: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    with open(abs_path, "r", encoding="utf-8") as f:
        content = f.read()
    meta, _ = parse_frontmatter(content)
    doc_id = meta.get("spec_doc_id")

    if not doc_id:
        print(f"specs: {file_path} has no spec_doc_id — not tracked by service", file=sys.stderr)
        os.remove(abs_path)
        print(f"specs: deleted local file: {file_path}")
        return

    try:
        status_code, body = api_request(
            f"{service_url}/api/documents/{doc_id}",
            method="DELETE",
            headers=headers,
        )
    except ConnectionError as e:
        print(f"specs: failed to delete from service — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 204, 404):
        print(f"specs: failed to delete document (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    os.remove(abs_path)
    print(f"specs: deleted '{os.path.basename(abs_path)}' (doc_id: {doc_id})")


def delete_feature(project_id, feature_name):
    """Delete a feature and all its documents."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    proj = _find_project(cfg, project_id)
    specs_path = proj["path"]
    service_url = cfg["service_url"]

    feature_id = f"{project_id}/{feature_name}"
    local_dir = os.path.join(specs_path, feature_name)

    import urllib.parse
    encoded_id = urllib.parse.quote(feature_id, safe="")

    try:
        status_code, body = api_request(
            f"{service_url}/api/features/lookup?id={encoded_id}",
            method="DELETE",
            headers=headers,
        )
    except ConnectionError as e:
        print(f"specs: failed to delete from service — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 204, 404):
        print(f"specs: failed to delete feature (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    if os.path.isdir(local_dir):
        import shutil
        shutil.rmtree(local_dir)

    print(f"specs: deleted feature '{feature_id}'")


def list_docs(project_id, feature_name):
    """List all documents in a feature."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    feature_id = f"{project_id}/{feature_name}"

    import urllib.parse
    encoded_id = urllib.parse.quote(feature_id, safe="")

    try:
        status_code, body = api_request(
            f"{service_url}/api/features/lookup?id={encoded_id}",
            headers=headers,
        )
    except ConnectionError as e:
        print(f"specs: failed to look up feature — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code != 200:
        print(f"specs: feature '{feature_id}' not found (HTTP {status_code})", file=sys.stderr)
        sys.exit(1)

    feature_data = json.loads(body)
    documents = feature_data.get("documents", [])

    if not documents:
        print(f"specs: no documents in '{feature_id}'")
        return

    print(f"specs: {len(documents)} document(s) in '{feature_id}'")
    print()
    for doc in documents:
        filename = doc.get("filename", "?")
        doc_status = doc.get("status", "?")
        version = doc.get("versionCount", "?")
        print(f"  {filename:40s}  v{version}  {doc_status}")


def list_features(project_id):
    """List all features in a project."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]

    try:
        status_code, body = api_request(
            f"{service_url}/api/features?project={project_id}",
            headers=headers,
        )
    except ConnectionError as e:
        print(f"specs: failed to list features — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code != 200:
        print(f"specs: failed to list features (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    features = json.loads(body)
    if not features:
        print(f"specs: no features in '{project_id}'")
        return

    print(f"specs: {len(features)} feature(s) in '{project_id}'")
    print()
    for f in features:
        name = f.get("name", "?")
        feat_status = f.get("status", "?")
        doc_count = f.get("documentCount", 0)
        status_marker = {
            "idea": ".",
            "specifying": "*",
            "in_progress": ">",
            "completed": "+",
            "archived": "x",
        }.get(feat_status, "?")
        print(f"  [{status_marker}] {name:40s}  {feat_status:15s}  {doc_count} doc(s)")


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def _build_multipart(entity_type, entity_id, file_path):
    """Build a multipart/form-data body for attachment upload.

    Returns (content_type, body_bytes).
    """
    import mimetypes
    import uuid
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    mime, _ = mimetypes.guess_type(filename)
    if not mime:
        mime = "application/octet-stream"

    boundary = f"----awolve-spec-{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts = []

    def add_field(name, value):
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(value.encode() if isinstance(value, str) else value)

    add_field("entityType", entity_type)
    add_field("entityId", entity_id)

    parts.append(f"--{boundary}".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode()
    )
    parts.append(f"Content-Type: {mime}".encode())
    parts.append(b"")
    parts.append(file_bytes)

    parts.append(f"--{boundary}--".encode())
    parts.append(b"")

    body = crlf.join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return content_type, body


def attach_file(file_path, feature_identifier=None):
    """Upload a local file as a binary attachment to a feature.

    If feature_identifier is None, infer the feature from the file path
    (file must live inside a configured specs directory).
    """
    if not os.path.isfile(file_path):
        print(f"specs: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    cfg = config.read_config()
    if not cfg:
        print("specs: no config found — run /awolve-spec:login", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]

    # Resolve the target feature
    if feature_identifier:
        # Expect "project-id/feature-name"
        if "/" not in feature_identifier:
            print(
                f"specs: feature identifier must be 'project-id/feature-name', got: {feature_identifier}",
                file=sys.stderr,
            )
            sys.exit(1)
        project_id, feature_name = feature_identifier.split("/", 1)
    else:
        # Infer from file path — find matching project and feature folder
        abs_file = os.path.abspath(file_path)
        proj = config.find_project_for_file(cfg, abs_file)
        if not proj:
            print(
                f"specs: {file_path} is not inside any configured specs directory — pass <project-id>/<feature-name> explicitly",
                file=sys.stderr,
            )
            sys.exit(1)
        project_id = proj["id"]
        # Feature is the first path component under the specs path
        specs_path = os.path.abspath(proj["path"])
        rel = os.path.relpath(abs_file, specs_path)
        parts = rel.split(os.sep)
        if len(parts) < 2:
            print(
                f"specs: {file_path} must be inside a feature folder (e.g. 001-my-feature/)",
                file=sys.stderr,
            )
            sys.exit(1)
        feature_name = parts[0]

    # Look up feature id from the service
    list_url = f"{service_url}/api/portal/projects/{project_id}/features"
    try:
        status, body = api_request(list_url, headers=headers)
    except ConnectionError as e:
        print(f"specs: {e}", file=sys.stderr)
        sys.exit(1)
    if status != 200:
        print(f"specs: failed to list features (HTTP {status})", file=sys.stderr)
        sys.exit(1)

    features_list = json.loads(body)
    feature = None
    for f in features_list:
        if f.get("name") == feature_name or f.get("id", "").endswith(f"/{feature_name}"):
            feature = f
            break
    if not feature:
        print(f"specs: feature '{feature_name}' not found in project '{project_id}'", file=sys.stderr)
        sys.exit(1)

    feature_id = feature["id"]
    upload_filename = os.path.basename(file_path)

    # Check for existing attachment with the same filename and delete it first
    # (bug #8: re-uploading the same filename previously created duplicates).
    try:
        att_status, att_body = api_request(
            f"{service_url}/api/portal/attachments?entityType=feature&entityId={urllib.parse.quote(feature_id, safe='')}",
            headers=headers,
        )
        if att_status == 200:
            existing_atts = json.loads(att_body) if isinstance(att_body, str) else att_body
            for att in existing_atts:
                if att.get("filename") == upload_filename:
                    del_status, _ = api_request(
                        f"{service_url}/api/portal/attachments/{att['id']}",
                        method="DELETE",
                        headers=headers,
                    )
                    if del_status in (200, 204):
                        print(f"specs: replaced existing attachment '{upload_filename}'")
                    break
    except Exception:
        pass  # best-effort — upload will still succeed, just may duplicate

    content_type, body_bytes = _build_multipart("feature", feature_id, file_path)

    upload_url = f"{service_url}/api/portal/attachments"
    upload_headers = dict(headers)
    upload_headers["Content-Type"] = content_type
    upload_headers["Content-Length"] = str(len(body_bytes))

    req = urllib.request.Request(upload_url, data=body_bytes, headers=upload_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp_body = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        msg = ""
        try:
            msg = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        print(f"specs: upload failed (HTTP {e.code}): {msg}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"specs: upload failed — {e.reason}", file=sys.stderr)
        sys.exit(1)

    if status not in (200, 201):
        print(f"specs: upload failed (HTTP {status}): {resp_body[:200]}", file=sys.stderr)
        sys.exit(1)

    try:
        att = json.loads(resp_body)
    except json.JSONDecodeError:
        att = {}

    print(f"specs: uploaded '{os.path.basename(file_path)}' to {project_id}/{feature_name}")
    if att.get("id"):
        print(f"  id: {att['id']}")
        print(f"  size: {att.get('sizeBytes', '?')} bytes")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print(__doc__.strip())
        sys.exit(0)

    cmd = args[0]
    quiet = "--quiet" in args

    if cmd == "pull":
        project_filter = None
        delete_mode = "trash"
        force_full = False
        for a in args[1:]:
            if a == "--prune":
                delete_mode = "prune"
            elif a == "--keep":
                delete_mode = "keep"
            elif a == "--force-full":
                force_full = True
            elif a == "--quiet":
                pass
            elif not a.startswith("-") and project_filter is None:
                project_filter = a
        pull(project_filter=project_filter, quiet=quiet, delete_mode=delete_mode, force_full=force_full)
    elif cmd == "log":
        project_id = None
        since_arg = None
        author_arg = None
        entity_arg = None
        limit_arg = 50
        json_out = False
        since_last_visit = False
        mark_read = False
        all_projects = False
        i = 1
        while i < len(args):
            a = args[i]
            if a == "--all":
                all_projects = True; i += 1
            elif a == "--since" and i + 1 < len(args):
                since_arg = args[i + 1]; i += 2
            elif a == "--author" and i + 1 < len(args):
                author_arg = args[i + 1]; i += 2
            elif a == "--entity" and i + 1 < len(args):
                entity_arg = args[i + 1]; i += 2
            elif a == "--limit" and i + 1 < len(args):
                try:
                    limit_arg = int(args[i + 1])
                except ValueError:
                    print(f"specs: invalid --limit '{args[i + 1]}'", file=sys.stderr)
                    sys.exit(1)
                i += 2
            elif a == "--json":
                json_out = True; i += 1
            elif a == "--since-last-visit":
                since_last_visit = True; i += 1
            elif a == "--mark-read":
                mark_read = True; i += 1
            elif not a.startswith("-") and project_id is None:
                project_id = a; i += 1
            else:
                i += 1

        if not all_projects and project_id is None:
            print("Usage: specs-cli.py log <project-id|--all> [--since DUR] [--author EMAIL] [--entity TYPE] [--limit N] [--json] [--since-last-visit] [--mark-read]", file=sys.stderr)
            sys.exit(1)
        if all_projects and project_id is not None:
            print("specs: cannot combine --all with a project id", file=sys.stderr)
            sys.exit(1)

        specs_log(
            project_id,  # None when --all is passed
            since=since_arg,
            author=author_arg,
            entity_type=entity_arg,
            limit=limit_arg,
            as_json=json_out,
            since_last_visit=since_last_visit,
            mark_read=mark_read,
        )
    elif cmd == "push":
        if len(args) < 2:
            print("Usage: specs-cli.py push <file_path>", file=sys.stderr)
            sys.exit(1)
        push(args[1])
    elif cmd == "status":
        show_status()
    elif cmd == "set-status":
        if len(args) < 3:
            print("Usage: specs-cli.py set-status <feature-or-doc-id> <status>", file=sys.stderr)
            print(f"  Feature statuses: {', '.join(FEATURE_STATUSES)}", file=sys.stderr)
            print(f"  Document statuses: {', '.join(DOCUMENT_STATUSES)}", file=sys.stderr)
            sys.exit(1)
        set_status(args[1], args[2])
    elif cmd == "bugs":
        proj = args[1] if len(args) > 1 and not args[1].startswith("-") else None
        list_bugs(proj)
    elif cmd == "view-bug":
        as_json = "--json" in args
        positional = [a for a in args[1:] if a != "--json"]
        if len(positional) < 2:
            print("Usage: specs-cli.py view-bug <project-id> <bug-number> [--json]", file=sys.stderr)
            sys.exit(1)
        view_bug(positional[0], positional[1], as_json=as_json)
    elif cmd == "set-bug-status":
        if len(args) < 4:
            print("Usage: specs-cli.py set-bug-status <project-id> <bug-number> <status>", file=sys.stderr)
            print(f"  Statuses: {', '.join(BUG_STATUSES)}", file=sys.stderr)
            sys.exit(1)
        set_bug_status(args[1], args[2], args[3])
    elif cmd == "bug":
        # Parse --attach flags
        images = []
        filtered = []
        i = 1
        while i < len(args):
            if args[i] == "--attach" and i + 1 < len(args):
                images.append(args[i + 1])
                i += 2
            else:
                filtered.append(args[i])
                i += 1
        if len(filtered) < 3:
            print("Usage: specs-cli.py bug <project-id> <title> <description> [severity] [--attach file ...]", file=sys.stderr)
            sys.exit(1)
        sev = filtered[3] if len(filtered) > 3 else "medium"
        create_bug(filtered[0], filtered[1], filtered[2], sev, images or None)
    elif cmd == "backlog":
        # Spec 013: --epics / --flat / --status / --priority
        positional = [a for a in args[1:] if not a.startswith("--")]
        proj = positional[0] if positional else None
        view = "tree"
        if "--epics" in args: view = "epics"
        elif "--flat" in args: view = "flat"
        status_filter = None
        priority_filter = None
        for i, a in enumerate(args):
            if a == "--status" and i + 1 < len(args): status_filter = args[i + 1]
            if a == "--priority" and i + 1 < len(args): priority_filter = args[i + 1]
        list_backlog(proj, view=view, status_filter=status_filter, priority_filter=priority_filter)
    elif cmd == "backlog-add":
        # Spec 013: --parent <id-or-#N> and --epic
        skip_next = False
        positional = []
        for i, a in enumerate(args[1:], 1):
            if skip_next:
                skip_next = False
                continue
            if a.startswith("--"):
                if a == "--parent" and i + 1 < len(args):
                    skip_next = True
                continue
            positional.append(a)
        if len(positional) < 2:
            print("Usage: specs-cli.py backlog-add <project-id> <title> [description] [priority] [--parent <id-or-#N>] [--epic]", file=sys.stderr)
            sys.exit(1)
        desc = positional[2] if len(positional) > 2 else None
        pri = positional[3] if len(positional) > 3 else "medium"
        parent_val = None
        for i, a in enumerate(args):
            if a == "--parent" and i + 1 < len(args): parent_val = args[i + 1]
        is_epic_flag = "--epic" in args
        create_backlog_item(positional[0], positional[1], desc, pri, parent=parent_val, is_epic=is_epic_flag)
    elif cmd == "backlog-set-parent":
        if len(args) < 4:
            print("Usage: specs-cli.py backlog-set-parent <project-id> <item-id-or-#N> <parent-id-or-#N|none>", file=sys.stderr)
            sys.exit(1)
        set_backlog_parent(args[1], args[2], args[3])
    elif cmd == "create-feature":
        if len(args) < 3:
            print("Usage: specs-cli.py create-feature <project-id> <name> [--status STATUS] [--description TEXT]", file=sys.stderr)
            sys.exit(1)
        status_val = "specifying"
        description_val = None
        for i, a in enumerate(args):
            if a == "--status" and i + 1 < len(args):
                status_val = args[i + 1]
            elif a == "--description" and i + 1 < len(args):
                description_val = args[i + 1]
        create_feature(args[1], args[2], initial_status=status_val, description=description_val)
    elif cmd == "set-description":
        if len(args) < 3:
            print("Usage: specs-cli.py set-description <feature-id> <text>", file=sys.stderr)
            sys.exit(1)
        set_description(args[1], args[2])
    elif cmd == "create-doc":
        if len(args) < 4:
            print("Usage: specs-cli.py create-doc <project-id> <feature-name> <filename>", file=sys.stderr)
            sys.exit(1)
        create_document(args[1], args[2], args[3])
    elif cmd == "rename-feature":
        if len(args) < 4:
            print("Usage: specs-cli.py rename-feature <project-id> <old-name> <new-name> [--title TEXT]", file=sys.stderr)
            sys.exit(1)
        title_val = None
        for i, a in enumerate(args):
            if a == "--title" and i + 1 < len(args):
                title_val = args[i + 1]
        rename_feature(args[1], args[2], args[3], title_override=title_val)
    elif cmd == "rename-doc":
        if len(args) < 3:
            print("Usage: specs-cli.py rename-doc <file-path> <new-filename>", file=sys.stderr)
            sys.exit(1)
        rename_document(args[1], args[2])
    elif cmd == "delete-doc":
        if len(args) < 2:
            print("Usage: specs-cli.py delete-doc <file-path>", file=sys.stderr)
            sys.exit(1)
        delete_document(args[1])
    elif cmd == "delete-feature":
        if len(args) < 3:
            print("Usage: specs-cli.py delete-feature <project-id> <feature-name>", file=sys.stderr)
            sys.exit(1)
        delete_feature(args[1], args[2])
    elif cmd == "list-features":
        if len(args) < 2:
            print("Usage: specs-cli.py list-features <project-id>", file=sys.stderr)
            sys.exit(1)
        list_features(args[1])
    elif cmd == "list-docs":
        if len(args) < 3:
            print("Usage: specs-cli.py list-docs <project-id> <feature-name>", file=sys.stderr)
            sys.exit(1)
        list_docs(args[1], args[2])
    elif cmd == "comments":
        if len(args) < 2:
            print("Usage: specs-cli.py comments <file-path> [--json]", file=sys.stderr)
            sys.exit(1)
        list_comments(args[1], as_json="--json" in args)
    elif cmd == "comment":
        if len(args) < 3:
            print("Usage: specs-cli.py comment <file-path> <body> [--inline --anchor <text>]", file=sys.stderr)
            sys.exit(1)
        inline = "--inline" in args
        anchor = None
        for i, a in enumerate(args):
            if a == "--anchor" and i + 1 < len(args):
                anchor = args[i + 1]
        add_comment(args[1], args[2], inline=inline, anchor_text=anchor)
    elif cmd == "resolve-comment":
        if len(args) < 2:
            print("Usage: specs-cli.py resolve-comment <comment-id>", file=sys.stderr)
            sys.exit(1)
        resolve_comment(args[1])
    elif cmd == "reviews":
        if len(args) < 2:
            print("Usage: specs-cli.py reviews <file-path> [--json]", file=sys.stderr)
            sys.exit(1)
        list_reviews(args[1], as_json="--json" in args)
    elif cmd == "review":
        if len(args) < 3:
            print("Usage: specs-cli.py review <file-path> <approved|changes_requested> [body]", file=sys.stderr)
            sys.exit(1)
        review_body = args[3] if len(args) > 3 and not args[3].startswith("-") else None
        submit_review(args[1], args[2], body=review_body)
    elif cmd == "versions":
        if len(args) < 2:
            print("Usage: specs-cli.py versions <file-path> [--json]", file=sys.stderr)
            sys.exit(1)
        list_versions(args[1], as_json="--json" in args)
    elif cmd == "save":
        if len(args) < 3:
            print("Usage: specs-cli.py save <file-path> <summary> [--source <source>]", file=sys.stderr)
            sys.exit(1)
        source = "manual"
        for i, a in enumerate(args):
            if a == "--source" and i + 1 < len(args):
                source = args[i + 1]
        save_version(args[1], args[2], source=source)
    elif cmd == "service-status":
        service_status()
    elif cmd == "post-tool-use":
        handle_post_tool_use()
    elif cmd == "attach":
        if len(args) < 2:
            print(
                "Usage: specs-cli.py attach <file-path> [<project-id>/<feature-name>]\n"
                "  If the feature identifier is omitted, it is inferred from the file path.",
                file=sys.stderr,
            )
            sys.exit(1)
        file_path = args[1]
        feature_id = args[2] if len(args) >= 3 else None
        attach_file(file_path, feature_id)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
