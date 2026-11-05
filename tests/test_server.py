"""Проверки транспорта, выбора движка и ресурсов без запуска Lua."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pob_poe2_mcp.cli import positive_timeout
from pob_poe2_mcp.engine import LOCK, resolve_engine_dir, setup_engine
from pob_poe2_mcp.errors import EngineError
from pob_poe2_mcp.server import METHODS, TOOLS, Server

ROOT = Path(__file__).resolve().parents[1]


class Configuration(unittest.TestCase):
    def test_explicit_path_takes_precedence_over_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            explicit = Path(directory) / "Явный путь"
            with patch.dict(os.environ, {"POB_DIR": str(Path(directory) / "other")}):
                self.assertEqual(resolve_engine_dir(explicit), explicit.resolve())
                self.assertEqual(resolve_engine_dir(), (Path(directory) / "other").resolve())

    def test_setup_refuses_to_overwrite_existing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "preserve.txt"
            marker.write_text("Сохранить", encoding="utf-8")
            with patch("pob_poe2_mcp.engine.sys.platform", "win32"), self.assertRaises(EngineError):
                setup_engine(directory)
            self.assertEqual(marker.read_text(encoding="utf-8"), "Сохранить")

    def test_lock_and_tool_manifest(self):
        self.assertEqual(len(LOCK["revision"]), 40)
        self.assertEqual({tool["name"] for tool in TOOLS}, set(METHODS) | {"pob_check_build"})
        self.assertIn('pob_tree_icons', {tool['name'] for tool in TOOLS})

    def test_timeout_rejects_nan_infinity_and_nonpositive_values(self):
        for value in ["nan", "inf", "-inf", "0", "-1"]:
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                positive_timeout(value)


class Transport(unittest.TestCase):
    def exchange(self, lines):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "run.py"), "serve", "--pob-dir", directory],
                cwd=directory, input="\n".join(lines) + "\n", capture_output=True,
                encoding="utf-8", timeout=15,
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        return [json.loads(line) for line in process.stdout.splitlines()]

    def request(self, method, params=None, request_id=1):
        return json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})

    def test_discovery_without_engine_and_configuration_error(self):
        responses = self.exchange([
            self.request("initialize", {"protocolVersion": "2025-11-25"}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            self.request("tools/list", request_id=2),
            self.request("tools/call", {"name": "pob_create_build", "arguments": {}}, 3),
            self.request("ping", request_id=4),
        ])
        self.assertEqual(len(responses), 4)
        self.assertIn('pob_tree_icons', {tool['name'] for tool in responses[1]['result']['tools']})
        self.assertTrue(responses[2]["result"]["isError"])
        self.assertIn(json.loads(responses[2]["result"]["content"][0]["text"])["code"],
                      ["ENGINE_NOT_CONFIGURED", "UNSUPPORTED_PLATFORM"])
        self.assertEqual(responses[3]["result"], {})

    def test_invalid_json_and_unknown_method_do_not_break_transport(self):
        responses = self.exchange([
            "{", self.request("initialize"), self.request("unknown", request_id=2),
            self.request("ping", request_id=3),
        ])
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[2]["error"]["code"], -32601)
        self.assertEqual(responses[3]["id"], 3)

    def test_schema_validation_does_not_start_engine(self):
        server = Server()
        server.handle("initialize", {})
        result = server.handle("tools/call", {"name": "pob_create_build", "arguments": {"level": 101}})
        self.assertTrue(result["isError"])
        self.assertIsNone(server.api)


if __name__ == "__main__":
    unittest.main()
