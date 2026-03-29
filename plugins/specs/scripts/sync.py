#!/usr/bin/env python3
"""
Core sync logic for the specs plugin.

Usage:
    sync.py pull [project-id]     — Pull latest specs (all projects, or specific one)
    sync.py push <file_path>      — Push a single spec file
    sync.py status                — Show sync status of local spec files
    sync.py set-status <id> <status> — Set feature or document status
    sync.py bugs <project-id>     — List bugs for a project
    sync.py bug <project-id> <title> <description> [severity] — Create a bug
    sync.py post-tool-use         — Hook: read tool use JSON from stdin, push if spec
    sync.py --help                — Show this help
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

FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_frontmatter(content):
    """Parse YAML frontmatter. Returns (metadata_dict, body_without_frontmatter)."""
    m = FM_PATTERN.match(content)
    if not m:
        return {}, content
    fm_text = m.group(1)
    body = content[m.end():]
    meta = {}
    for line in fm_text.strip().splitlines():
        match = re.match(r"^([\w_]+)\s*:\s*(.+)$", line.strip())
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
    """Render metadata dict and body back into markdown with frontmatter."""
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + body


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
    headers.setdefault("User-Agent", "claude-specs-plugin/0.1.0")

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
            print("specs: authentication expired — run /specs-login", file=sys.stderr)
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
    if not documents:
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
            print("specs: not authenticated — run /specs-login first", file=sys.stderr)
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
        print("specs: not authenticated — run /specs-login first", file=sys.stderr)
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
        print("specs: authentication expired — run /specs-login", file=sys.stderr)
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

    push(file_path)


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
        print("specs: not authenticated — run /specs-login first", file=sys.stderr)
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
            f"{service_url}/api/features/{encoded_id}",
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
                            f"{service_url}/api/features/{encoded_id}",
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
        print("specs: not authenticated — run /specs-login first", file=sys.stderr)
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


def create_bug(project_id, title, description, severity="medium"):
    """Create a bug report."""
    cfg = config.read_config()
    if not cfg:
        print("specs: no config found", file=sys.stderr)
        sys.exit(1)

    headers = auth.get_headers()
    if not headers:
        print("specs: not authenticated — run /specs-login first", file=sys.stderr)
        sys.exit(1)

    if severity not in BUG_SEVERITIES:
        print(f"specs: invalid severity '{severity}'. Must be one of: {', '.join(BUG_SEVERITIES)}", file=sys.stderr)
        sys.exit(1)

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
            print("Usage: sync.py push <file_path>", file=sys.stderr)
            sys.exit(1)
        push(args[1])
    elif cmd == "status":
        show_status()
    elif cmd == "set-status":
        if len(args) < 3:
            print("Usage: sync.py set-status <feature-or-doc-id> <status>", file=sys.stderr)
            print(f"  Feature statuses: {', '.join(FEATURE_STATUSES)}", file=sys.stderr)
            print(f"  Document statuses: {', '.join(DOCUMENT_STATUSES)}", file=sys.stderr)
            sys.exit(1)
        set_status(args[1], args[2])
    elif cmd == "bugs":
        proj = args[1] if len(args) > 1 and not args[1].startswith("-") else None
        list_bugs(proj)
    elif cmd == "bug":
        if len(args) < 4:
            print("Usage: sync.py bug <project-id> <title> <description> [severity]", file=sys.stderr)
            sys.exit(1)
        sev = args[4] if len(args) > 4 else "medium"
        create_bug(args[1], args[2], args[3], sev)
    elif cmd == "post-tool-use":
        handle_post_tool_use()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
