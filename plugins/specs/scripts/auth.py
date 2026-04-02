"""
Authentication for the Awolve Spec Service.

Supports two auth methods:
1. Azure CLI (Awolve users) — auto-refreshes token on each request, never expires
2. Stored API key (external users) — long-lived, stored in ~/.claude-specs/auth.json

Config stored in ~/.claude-specs/auth.json:
{
    "method": "azure-cli" | "api-key",
    "service_url": "https://specs.awolve.ai",
    "email": "user@awolve.ai",
    "api_key": "..." (only for api-key method)
}
"""

import json
import os
import subprocess
import sys

AUTH_DIR = os.path.expanduser("~/.claude-specs")
AUTH_FILE = os.path.join(AUTH_DIR, "auth.json")


def _read_auth():
    """Read stored auth config. Returns dict or empty dict."""
    if not os.path.isfile(AUTH_FILE):
        return {}
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _write_auth(data):
    """Write auth config to disk."""
    os.makedirs(AUTH_DIR, mode=0o700, exist_ok=True)
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.chmod(AUTH_FILE, 0o600)


def _get_azure_token():
    """Get a fresh token from Azure CLI. Returns (token, env_name) or (None, None).

    Tries in order:
    1. SPECS_AZURE_CONFIG_DIR env var (explicit override)
    2. ~/.cortex-envs/cortex-web/.azure (Cortex terminals — always logged in)
    3. Default az CLI (uses AZURE_CONFIG_DIR or ~/.azure)
    """
    alt_azure_config = os.environ.get("SPECS_AZURE_CONFIG_DIR", "")
    if alt_azure_config:
        alt_azure_config = os.path.expanduser(alt_azure_config)
    cortex_web_config = os.path.expanduser("~/.cortex-envs/cortex-web/.azure")
    envs_to_try = []
    if alt_azure_config and os.path.isdir(alt_azure_config):
        envs_to_try.append(({**os.environ, "AZURE_CONFIG_DIR": alt_azure_config}, "alternate"))
    if os.path.isdir(cortex_web_config):
        envs_to_try.append(({**os.environ, "AZURE_CONFIG_DIR": cortex_web_config}, "cortex-web"))
    envs_to_try.append((None, "default"))

    for env, name in envs_to_try:
        try:
            result = subprocess.run(
                ["az", "account", "get-access-token",
                 "--resource", "https://graph.microsoft.com",
                 "--query", "accessToken", "-o", "tsv"],
                capture_output=True, text=True, env=env, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip(), name
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return None, None


def _get_azure_email():
    """Get current Azure CLI user email. Uses same config dir resolution as _get_azure_token."""
    alt_azure_config = os.environ.get("SPECS_AZURE_CONFIG_DIR", "")
    if alt_azure_config:
        alt_azure_config = os.path.expanduser(alt_azure_config)
    cortex_web_config = os.path.expanduser("~/.cortex-envs/cortex-web/.azure")
    if alt_azure_config and os.path.isdir(alt_azure_config):
        env = {**os.environ, "AZURE_CONFIG_DIR": alt_azure_config}
    elif os.path.isdir(cortex_web_config):
        env = {**os.environ, "AZURE_CONFIG_DIR": cortex_web_config}
    else:
        env = None
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "user.name", "-o", "tsv"],
            capture_output=True, text=True, env=env, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_auth():
    """Get stored auth info. Returns dict or None."""
    data = _read_auth()
    method = data.get("method")
    if not method:
        return None
    return data


def get_headers():
    """
    Get HTTP headers for authenticated requests.
    For azure-cli: fetches a fresh token each time (auto-refresh, never expires).
    For api-key: uses stored key.
    Returns dict with Authorization header, or None if not authenticated.
    """
    data = _read_auth()
    method = data.get("method")

    if method == "azure-cli":
        token, _ = _get_azure_token()
        if not token:
            print("specs: Azure CLI token unavailable — run 'az login' or '/specs-login'", file=sys.stderr)
            return None
        return {"Authorization": f"Bearer {token}"}

    elif method == "api-key":
        key = data.get("api_key")
        if not key:
            return None
        return {"Authorization": f"Bearer {key}"}

    return None


def _verify_token(token, service_url):
    """Verify a token works against the spec service. Returns True if valid."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(
            f"{service_url}/api/portal/projects",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False
        return True  # other errors (500, etc.) — token might be fine
    except Exception:
        return False


def login_azure(service_url=None):
    """Set up Azure CLI auth method. Tries alternate Azure config first, then default."""
    token, env_name = _get_azure_token()
    if not token:
        print("specs: Azure CLI not available or not logged in", file=sys.stderr)
        print("specs: run 'az login' first", file=sys.stderr)
        return False

    url = service_url or _read_auth().get("service_url", "https://specs.awolve.ai")

    # Verify the token works against our spec service
    if not _verify_token(token, url):
        email = _get_azure_email() or "unknown"
        print(f"specs: Azure CLI token ({email}, env: {env_name}) was rejected by {url}", file=sys.stderr)
        print(f"specs: your Azure account may not have access to this spec service", file=sys.stderr)
        print(f"specs: use an API key instead: /specs-login with --api-key", file=sys.stderr)
        return False

    email = _get_azure_email() or "unknown"

    data = _read_auth()
    data["method"] = "azure-cli"
    data["email"] = email
    data["service_url"] = url
    data["azure_env"] = env_name
    data.pop("api_key", None)
    _write_auth(data)
    print(f"specs: logged in as {email} (Azure CLI, env: {env_name} — token auto-refreshes)")
    return True


def login_apikey(api_key=None, email=None, service_url=None, from_clipboard=False):
    """Set up API key auth method.

    Resolution order: api_key arg > SPECS_API_KEY env > clipboard (if --from-clipboard) > getpass.
    """
    if not api_key:
        api_key = os.environ.get("SPECS_API_KEY", "").strip()

    if not api_key and from_clipboard:
        try:
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                api_key = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("specs: clipboard not available (pbpaste not found)", file=sys.stderr)
            return False

    if not api_key:
        try:
            import getpass
            api_key = getpass.getpass("API key: ").strip()
        except (EOFError, OSError):
            print("specs: cannot read key interactively", file=sys.stderr)
            print("specs: copy key to clipboard and retry with --from-clipboard", file=sys.stderr)
            return False

    if not api_key:
        print("specs: no key provided — aborting", file=sys.stderr)
        return False

    if not api_key.startswith("sk_"):
        print("specs: invalid key — must start with sk_", file=sys.stderr)
        return False

    url = service_url or _read_auth().get("service_url", "https://specs.awolve.ai")

    # Verify the key works before saving
    if not _verify_token(api_key, url):
        print(f"specs: API key rejected by {url} — check the key and try again", file=sys.stderr)
        return False

    data = _read_auth()
    data["method"] = "api-key"
    data["api_key"] = api_key
    data["service_url"] = url
    _write_auth(data)

    # Clear clipboard if we read from it
    if from_clipboard:
        try:
            subprocess.run(["pbcopy"], input=b"", timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    print("specs: logged in (API key)")
    return True


def login(token, email=None, service_url=None):
    """Legacy login with raw token. Stored as api-key method."""
    return login_apikey(token, email, service_url)


def logout():
    """Remove stored credentials."""
    if os.path.isfile(AUTH_FILE):
        os.remove(AUTH_FILE)
    print("specs: logged out")


def status():
    """Print current auth status."""
    data = _read_auth()
    method = data.get("method")

    if method == "azure-cli":
        email = data.get("email", "unknown")
        url = data.get("service_url", "default")
        env_name = data.get("azure_env", "default")
        token, _ = _get_azure_token()
        if token:
            print(f"specs: authenticated as {email} via Azure CLI, env: {env_name} ({url})")
            print(f"specs: token auto-refreshes — no expiry")
        else:
            print(f"specs: Azure CLI configured (env: {env_name}) but token unavailable — run 'az login'")
    elif method == "api-key":
        email = data.get("email", "unknown")
        url = data.get("service_url", "default")
        print(f"specs: authenticated as {email} via API key ({url})")
    else:
        print("specs: not authenticated — run /specs-login")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        status()
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "login-azure":
        ok = login_azure()
        sys.exit(0 if ok else 1)
    elif cmd == "login-apikey":
        # Secure: reads key from clipboard, env var, or getpass — never in args
        url = None
        for i, a in enumerate(sys.argv):
            if a == "--service-url" and i + 1 < len(sys.argv):
                url = sys.argv[i + 1]
        clipboard = "--from-clipboard" in sys.argv
        ok = login_apikey(service_url=url, from_clipboard=clipboard)
        sys.exit(0 if ok else 1)
    elif cmd == "login":
        if len(sys.argv) < 3:
            # Default: try Azure CLI
            ok = login_azure()
            sys.exit(0 if ok else 1)
        t = sys.argv[2]
        e = sys.argv[3] if len(sys.argv) > 3 else None
        u = sys.argv[4] if len(sys.argv) > 4 else None
        login_apikey(t, e, u)
    elif cmd == "logout":
        logout()
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
