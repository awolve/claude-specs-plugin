"""
Read spec configuration from .claude/specs.md (committed) and .claude/specs.local.md (personal override).

Priority: specs.local.md > specs.md (local overrides committed config entirely if present)

Supports multi-project config:
---
service_url: https://specs.awolve.ai
projects:
  - id: my-service
    path: path/to/my-service/specs
  - id: client-project
    path: path/to/client-project/specs
---
"""

import os
import re

DEFAULT_SERVICE_URL = "https://specs.awolve.ai"


def find_project_root():
    """Walk up from cwd to find a directory containing .claude/specs.md or .claude/specs.local.md"""
    d = os.getcwd()
    while True:
        for name in ("specs.local.md", "specs.md"):
            candidate = os.path.join(d, ".claude", name)
            if os.path.isfile(candidate):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _expand_path(path_str, project_root):
    """Resolve a path relative to project root, expanding ~ if present."""
    path_str = os.path.expanduser(path_str)
    if os.path.isabs(path_str):
        return os.path.normpath(path_str)
    return os.path.normpath(os.path.join(project_root, path_str))


def _parse_config_file(config_path, project_root):
    """Parse a single config file. Returns config dict or None."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError):
        return None

    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return None

    fm_text = fm_match.group(1)

    # Extract service_url
    service_url = DEFAULT_SERVICE_URL
    url_match = re.search(r"^service_url\s*:\s*(.+)$", fm_text, re.MULTILINE)
    if url_match:
        service_url = url_match.group(1).strip().strip("\"'").rstrip("/")

    # Parse projects list
    projects = []
    projects_match = re.search(r"^projects\s*:\s*\n((?:\s+-.+\n?(?:\s+\w.+\n?)*)*)", fm_text, re.MULTILINE)
    if projects_match:
        projects_block = projects_match.group(1)
        entries = re.split(r"\n\s+-\s+", "\n" + projects_block)
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            id_match = re.search(r"(?:^|\n)\s*id\s*:\s*(.+)", entry)
            path_match = re.search(r"(?:^|\n)\s*path\s*:\s*(.+)", entry)
            if id_match:
                proj_id = id_match.group(1).strip().strip("\"'")
                proj_path = path_match.group(1).strip().strip("\"'") if path_match else "./specs"
                projects.append({
                    "id": proj_id,
                    "path": _expand_path(proj_path, project_root),
                })

    # Backwards compat: single-project format
    if not projects:
        single_match = re.search(r"^project\s*:\s*(.+)$", fm_text, re.MULTILINE)
        if single_match:
            proj_id = single_match.group(1).strip().strip("\"'")
            path_match = re.search(r"^specs_path\s*:\s*(.+)$", fm_text, re.MULTILINE)
            proj_path = path_match.group(1).strip().strip("\"'") if path_match else "./specs"
            projects.append({
                "id": proj_id,
                "path": _expand_path(proj_path, project_root),
            })

    if not projects:
        return None

    return {
        "service_url": service_url,
        "projects": projects,
        "project_root": project_root,
    }


def read_config():
    """
    Read spec config. Checks .claude/specs.local.md first (personal override),
    falls back to .claude/specs.md (committed/shared).

    Returns dict with keys:
      - service_url: str
      - projects: list of {id, path (absolute)}
      - project_root: str

    Returns None if no config found.
    """
    project_root = find_project_root()
    if project_root is None:
        return None

    # Try local override first
    local_path = os.path.join(project_root, ".claude", "specs.local.md")
    if os.path.isfile(local_path):
        cfg = _parse_config_file(local_path, project_root)
        if cfg:
            return cfg

    # Fall back to committed config
    shared_path = os.path.join(project_root, ".claude", "specs.md")
    if os.path.isfile(shared_path):
        cfg = _parse_config_file(shared_path, project_root)
        if cfg:
            return cfg

    return None


def find_project_for_file(config, file_path):
    """Given a file path, find which project it belongs to (if any)."""
    file_abs = os.path.abspath(file_path)
    for proj in config["projects"]:
        proj_path = proj["path"]
        if file_abs.startswith(proj_path + os.sep) or file_abs == proj_path:
            return proj
    return None
