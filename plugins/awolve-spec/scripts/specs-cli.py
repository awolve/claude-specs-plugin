#!/usr/bin/env python3
"""
Specs CLI — sync, review, and manage spec documents.

Usage:
    specs-cli.py pull [project-id]     — Pull latest specs (all projects, or specific one)
    specs-cli.py push <file_path>      — Push a single spec file
    specs-cli.py status                — Show sync status of local spec files
    specs-cli.py set-status <id> <status> — Set feature or document status
    specs-cli.py create-feature <project-id> <name> [--status STATUS]
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
    specs-cli.py bugs <project-id>     — List bugs for a project
    specs-cli.py bug <project-id> <title> <description> [severity] — Create a bug
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
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

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
    """Make an HTTP request. Returns (status_code, response_body_str)."""
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
        return e.code, body
    except urllib.error.URLError as e:
        raise ConnectionError(f"Network error: {e.reason}") from e


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

def pull_project(project_id, specs_path, service_url, headers, quiet=False):
    """Pull specs for a single project. Returns (synced_count, skipped_count)."""
    manifest_url = f"{service_url}/api/sync/projects/{project_id}/manifest"
    try:
        status, body = api_request(manifest_url, headers=headers)
    except ConnectionError as e:
        if not quiet:
            print(f"specs: pull failed for '{project_id}' — {e}", file=sys.stderr)
        return 0, 0

    if status == 401:
        if not quiet:
            print("specs: authentication expired — run /awolve-spec:login", file=sys.stderr)
        return 0, 0
    if status == 404:
        if not quiet:
            print(f"specs: project '{project_id}' not found", file=sys.stderr)
        return 0, 0
    if status != 200:
        if not quiet:
            print(f"specs: manifest failed for '{project_id}' (HTTP {status})", file=sys.stderr)
        return 0, 0

    manifest = json.loads(body)
    documents = manifest.get("documents", [])
    remote_attachments = manifest.get("attachments", [])
    if not documents and not remote_attachments:
        return 0, 0

    os.makedirs(specs_path, exist_ok=True)
    synced = 0
    skipped = 0

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

        # Check if local file has same content hash
        if os.path.isfile(local_path):
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    local_content = f.read()
                local_hash = file_content_hash(local_content)
                if local_hash == remote_hash:
                    # Content matches — update frontmatter if version/status drifted
                    local_meta, local_body = parse_frontmatter(local_content)
                    if local_meta.get("spec_version") != version or \
                       local_meta.get("feature_status", "") != feature_status or \
                       local_meta.get("doc_status", "") != doc_status:
                        local_meta["spec_version"] = version
                        if feature_status:
                            local_meta["feature_status"] = feature_status
                        if doc_status:
                            local_meta["doc_status"] = doc_status
                        with open(local_path, "w", encoding="utf-8") as fw:
                            fw.write(render_frontmatter(local_meta, local_body))
                    skipped += 1
                    continue
            except (IOError, OSError):
                pass

        # Download
        content_url = f"{service_url}/api/sync/documents/{doc_id}/content"
        try:
            dl_status, dl_body = api_request(content_url, headers=headers)
        except ConnectionError:
            continue

        if dl_status != 200:
            continue

        # Write with frontmatter
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = {
            "spec_version": version,
            "spec_doc_id": doc_id,
            "last_synced": now,
        }
        if feature_status:
            meta["feature_status"] = feature_status
        if doc_status:
            meta["doc_status"] = doc_status
        if source_url:
            meta["source"] = source_url

        os.makedirs(local_dir, exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(render_frontmatter(meta, dl_body))
        synced += 1

    # Binary attachments — mirror the blob storage contents into each feature folder.
    # Dedup is by (filename, size) since binaries don't carry frontmatter. This means
    # we'll re-download if someone changes a file with the exact same size locally,
    # but that's rare enough to accept in v1.
    for att in remote_attachments:
        att_id = att.get("id")
        feature_name = att.get("feature")
        filename = att.get("filename")
        size = att.get("size_bytes", 0)
        if not att_id or not feature_name or not filename:
            continue

        local_dir = os.path.join(specs_path, feature_name)
        local_path = os.path.join(local_dir, filename)

        # Skip if already present with matching size
        if os.path.isfile(local_path):
            try:
                if os.path.getsize(local_path) == size:
                    skipped += 1
                    continue
            except OSError:
                pass

        # Download as binary
        dl_url = f"{service_url}/api/sync/attachments/{att_id}"
        try:
            req = urllib.request.Request(dl_url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, ConnectionError) as e:
            if not quiet:
                print(f"specs: attachment download failed for '{filename}' — {e}", file=sys.stderr)
            continue

        os.makedirs(local_dir, exist_ok=True)
        try:
            with open(local_path, "wb") as f:
                f.write(content)
            synced += 1
        except OSError as e:
            if not quiet:
                print(f"specs: failed to write attachment '{local_path}' — {e}", file=sys.stderr)
            continue

    return synced, skipped


# ---------------------------------------------------------------------------
# Pull (all projects)
# ---------------------------------------------------------------------------

def pull(project_filter=None, quiet=False):
    """Pull specs for all configured projects (or a specific one)."""
    cfg = config.read_config()
    if not cfg:
        if not quiet:
            print("specs: no config found — create .claude/specs.md or .claude/specs.local.md — create .claude/specs.md (shared) or .claude/specs.local.md (personal)", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        if not quiet:
            print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    projects = cfg["projects"]

    if project_filter:
        projects = [p for p in projects if p["id"] == project_filter]
        if not projects:
            print(f"specs: project '{project_filter}' not in config", file=sys.stderr)
            sys.exit(1)

    total_synced = 0
    total_skipped = 0

    for proj in projects:
        synced, skipped = pull_project(proj["id"], proj["path"], service_url, headers, quiet)
        total_synced += synced
        total_skipped += skipped

        if not quiet and (synced or skipped):
            parts = []
            if synced:
                parts.append(f"{synced} updated")
            if skipped:
                parts.append(f"{skipped} unchanged")
            print(f"specs: {proj['id']} — {', '.join(parts)}")

    if not quiet and total_synced == 0 and total_skipped == 0:
        print(f"specs: pulled {len(projects)} project(s) — no files")


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

    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(render_frontmatter(meta, body))

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

        # Try as feature ID without slash
        if new_status in FEATURE_STATUSES:
            # Search local files for a matching feature
            for proj in cfg["projects"]:
                specs_path = proj["path"]
                if not os.path.isdir(specs_path):
                    continue
                for entry in os.listdir(specs_path):
                    if entry == identifier or entry.endswith(identifier):
                        feature_id = f"{proj['id']}/{entry}"
                        import urllib.parse
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


def list_backlog(project_id=None):
    """List backlog items for a project or all configured projects."""
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

        if len(projects) > 1:
            print(f"\n{proj['id']} ({len(active)} active)")
        else:
            print(f"specs: {len(active)} active backlog item(s) in '{proj['id']}'")

        if not active:
            print("  (no active items)")
            continue

        print()
        for item in active:
            priority = item.get("priority", "?")
            status = item.get("status", "?")
            title = item.get("title", "untitled")
            feature_id = item.get("featureId")
            pri_marker = {"high": "!!!", "medium": "!!", "low": "!"}.get(priority, "?")
            promoted = f" → {feature_id}" if feature_id else ""
            print(f"  [{pri_marker}] {title}")
            print(f"       {status}{promoted}")


def create_backlog_item(project_id, title, description=None, priority="medium"):
    """Create a new backlog item."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /awolve-spec:login first", file=sys.stderr)
        sys.exit(1)

    service_url = cfg["service_url"]
    url = f"{service_url}/api/portal/projects/{project_id}/backlog"

    try:
        status_code, body = api_request(
            url, method="POST",
            headers={**headers, "Content-Type": "application/json"},
            data={"title": title, "description": description, "priority": priority},
        )
    except ConnectionError as e:
        print(f"specs: failed to create backlog item — {e}", file=sys.stderr)
        sys.exit(1)

    if status_code not in (200, 201):
        print(f"specs: failed to create backlog item (HTTP {status_code}): {body}", file=sys.stderr)
        sys.exit(1)

    item = json.loads(body)
    print(f"specs: created backlog item '{item.get('title')}' in '{project_id}' (priority: {item.get('priority')})")


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


def create_feature(project_id, name, initial_status="specifying"):
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


def rename_feature(project_id, old_name, new_name):
    """Rename a feature folder and update the service."""
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

    old_dir = os.path.join(specs_path, old_name)
    new_dir = os.path.join(specs_path, new_name)

    if not os.path.isdir(old_dir):
        print(f"specs: feature folder not found: {old_dir}", file=sys.stderr)
        sys.exit(1)

    if os.path.exists(new_dir):
        print(f"specs: target folder already exists: {new_dir}", file=sys.stderr)
        sys.exit(1)

    # Update service
    import urllib.parse
    encoded_id = urllib.parse.quote(old_feature_id, safe="")

    try:
        status_code, body = api_request(
            f"{service_url}/api/features/lookup?id={encoded_id}",
            method="PATCH",
            headers={**headers, "Content-Type": "application/json"},
            data={"name": new_name},
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
        for a in args[1:]:
            if not a.startswith("-"):
                project_filter = a
                break
        pull(project_filter=project_filter, quiet=quiet)
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
        proj = args[1] if len(args) > 1 and not args[1].startswith("-") else None
        list_backlog(proj)
    elif cmd == "backlog-add":
        if len(args) < 3:
            print("Usage: specs-cli.py backlog-add <project-id> <title> [description] [priority]", file=sys.stderr)
            sys.exit(1)
        desc = args[3] if len(args) > 3 else None
        pri = args[4] if len(args) > 4 else "medium"
        create_backlog_item(args[1], args[2], desc, pri)
    elif cmd == "create-feature":
        if len(args) < 3:
            print("Usage: specs-cli.py create-feature <project-id> <name> [--status STATUS]", file=sys.stderr)
            sys.exit(1)
        status_val = "specifying"
        for i, a in enumerate(args):
            if a == "--status" and i + 1 < len(args):
                status_val = args[i + 1]
        create_feature(args[1], args[2], initial_status=status_val)
    elif cmd == "create-doc":
        if len(args) < 4:
            print("Usage: specs-cli.py create-doc <project-id> <feature-name> <filename>", file=sys.stderr)
            sys.exit(1)
        create_document(args[1], args[2], args[3])
    elif cmd == "rename-feature":
        if len(args) < 4:
            print("Usage: specs-cli.py rename-feature <project-id> <old-name> <new-name>", file=sys.stderr)
            sys.exit(1)
        rename_feature(args[1], args[2], args[3])
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
