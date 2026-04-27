import os
import shlex
from typing import Any
from urllib.parse import urlparse

from app.utils.browser import format_viewport_size, parse_viewport_size

PLAYWRIGHT_MCP_SERVER_KEY = "__poco_playwright"


def build_playwright_mcp_config() -> dict[str, Any]:
    """Build Playwright MCP server config for browser-enabled tasks."""
    cdp_endpoint = (
        os.environ.get("POCO_BROWSER_CDP_ENDPOINT", "http://127.0.0.1:9222").strip()
        or "http://127.0.0.1:9222"
    )
    # Validate scheme — prevents file:// or ftp:// misconfiguration.
    # Full SSRF protection (IP allowlisting, metadata endpoint blocking)
    # requires network-level policy enforcement in cloud environments.
    parsed_endpoint = urlparse(cdp_endpoint)
    if parsed_endpoint.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid CDP endpoint scheme: {parsed_endpoint.scheme}. "
            "Only http/https are allowed."
        )

    viewport_raw = (os.environ.get("POCO_BROWSER_VIEWPORT_SIZE") or "").strip()
    viewport = parse_viewport_size(viewport_raw) or (1366, 768)
    viewport_size = format_viewport_size(*viewport)

    output_mode = (os.environ.get("PLAYWRIGHT_MCP_OUTPUT_MODE") or "").strip().lower()
    if output_mode not in {"file", "stdout"}:
        output_mode = "file"

    image_responses = (
        (os.environ.get("PLAYWRIGHT_MCP_IMAGE_RESPONSES") or "").strip().lower()
    )
    if image_responses not in {"allow", "omit"}:
        image_responses = "omit"

    playwright_launch_command = (
        "exec npx -y @playwright/mcp@latest "
        f"--cdp-endpoint {shlex.quote(cdp_endpoint)} "
        "--caps vision "
        f"--viewport-size {shlex.quote(viewport_size)} "
        f"--output-mode {shlex.quote(output_mode)} "
        f"--image-responses {shlex.quote(image_responses)}"
    )

    # Wait for Chrome's CDP endpoint before starting the MCP server to avoid flakiness on startup.
    wait_then_start = f"""
python3 - <<'PY'
import time
import urllib.request

url = {cdp_endpoint!r} + "/json/version"
deadline = time.time() + 15
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            resp.read()
        break
    except Exception:
        time.sleep(0.1)
else:
    raise SystemExit("CDP endpoint not ready: " + url)
PY
{playwright_launch_command}
""".strip()

    return {"command": "bash", "args": ["-lc", wait_then_start]}


def inject_playwright_mcp(mcp_servers: dict[str, Any]) -> dict[str, Any]:
    """Inject built-in Playwright MCP (CDP mode) into the server map."""
    if PLAYWRIGHT_MCP_SERVER_KEY in mcp_servers:
        return mcp_servers

    injected = dict(mcp_servers)
    injected[PLAYWRIGHT_MCP_SERVER_KEY] = build_playwright_mcp_config()
    return injected
