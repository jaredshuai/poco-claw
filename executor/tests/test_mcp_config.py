import os
import unittest
from unittest.mock import patch

from app.core.mcp_config import (
    PLAYWRIGHT_MCP_SERVER_KEY,
    build_playwright_mcp_config,
    inject_playwright_mcp,
)


class TestBuildPlaywrightMcpConfig(unittest.TestCase):
    def test_builds_launcher_with_cdp_probe(self) -> None:
        with patch.dict(
            os.environ,
            {
                "POCO_BROWSER_CDP_ENDPOINT": "http://custom:9999",
                "POCO_BROWSER_VIEWPORT_SIZE": "1920x1080",
                "PLAYWRIGHT_MCP_OUTPUT_MODE": "stdout",
                "PLAYWRIGHT_MCP_IMAGE_RESPONSES": "allow",
            },
            clear=False,
        ):
            config = build_playwright_mcp_config()

        self.assertEqual(config["command"], "bash")
        command = config["args"][-1]
        self.assertIn("http://custom:9999", command)
        self.assertIn("/json/version", command)
        self.assertIn("1920x1080", command)
        self.assertIn("stdout", command)
        self.assertIn("allow", command)

    def test_cdp_probe_uses_monotonic_timeout(self) -> None:
        config = build_playwright_mcp_config()

        command = config["args"][-1]
        self.assertIn("time.monotonic() + 15", command)
        self.assertIn("while time.monotonic() < deadline:", command)
        self.assertNotIn("time.time()", command)

    def test_rejects_invalid_cdp_scheme(self) -> None:
        with patch.dict(
            os.environ,
            {"POCO_BROWSER_CDP_ENDPOINT": "ftp://custom:9999"},
            clear=False,
        ):
            with self.assertRaises(ValueError):
                build_playwright_mcp_config()

    def test_defaults_when_env_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "POCO_BROWSER_CDP_ENDPOINT": "",
                "POCO_BROWSER_VIEWPORT_SIZE": "",
                "PLAYWRIGHT_MCP_OUTPUT_MODE": "",
                "PLAYWRIGHT_MCP_IMAGE_RESPONSES": "",
            },
            clear=False,
        ):
            config = build_playwright_mcp_config()

        self.assertEqual(config["command"], "bash")
        command = config["args"][-1]
        self.assertIn("http://127.0.0.1:9222", command)
        self.assertIn("1366x768", command)


class TestInjectPlaywrightMcp(unittest.TestCase):
    def test_injects_playwright_server_when_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "POCO_BROWSER_CDP_ENDPOINT": "http://localhost:9222",
                "POCO_BROWSER_VIEWPORT_SIZE": "",
                "PLAYWRIGHT_MCP_OUTPUT_MODE": "",
                "PLAYWRIGHT_MCP_IMAGE_RESPONSES": "",
            },
            clear=False,
        ):
            result = inject_playwright_mcp({})

        self.assertIn(PLAYWRIGHT_MCP_SERVER_KEY, result)
        self.assertEqual(result[PLAYWRIGHT_MCP_SERVER_KEY]["command"], "bash")

    def test_preserves_existing_server(self) -> None:
        existing = {PLAYWRIGHT_MCP_SERVER_KEY: {"command": "existing"}}

        result = inject_playwright_mcp(existing)

        self.assertIs(result, existing)
        self.assertEqual(result[PLAYWRIGHT_MCP_SERVER_KEY]["command"], "existing")

    def test_does_not_mutate_input(self) -> None:
        original = {}
        with patch.dict(
            os.environ,
            {
                "POCO_BROWSER_CDP_ENDPOINT": "http://localhost:9222",
                "POCO_BROWSER_VIEWPORT_SIZE": "",
                "PLAYWRIGHT_MCP_OUTPUT_MODE": "",
                "PLAYWRIGHT_MCP_IMAGE_RESPONSES": "",
            },
            clear=False,
        ):
            result = inject_playwright_mcp(original)

        self.assertNotIn(PLAYWRIGHT_MCP_SERVER_KEY, original)
        self.assertIn(PLAYWRIGHT_MCP_SERVER_KEY, result)
