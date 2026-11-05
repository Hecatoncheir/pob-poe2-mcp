"""Проверки обычной установки, обнаружения PoB и обратимого Lua-моста."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pob_poe2_mcp.bridge import BEGIN, install_bridge, remove_hook, uninstall_bridge
from pob_poe2_mcp.cli import client_config
from pob_poe2_mcp.engine import LOCK, engine_layout, resolve_engine_dir
from pob_poe2_mcp.errors import EngineError
from pob_poe2_mcp.transport import AppTransport


def fake_install(root, repository=False):
    scripts = root / "src" if repository else root
    runtime = root / "runtime" if repository else root
    for path in [scripts / "Launch.lua", scripts / "GameVersions.lua", scripts / "Modules/Main.lua",
                 scripts / "TreeData/0_5/tree.json", runtime / "lua51.dll", runtime / "lua/dkjson.lua"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("-- Исходный файл\n", encoding="utf-8")
    (root / "manifest.xml").write_text('<PoBVersion><Version number="0.23.1"/></PoBVersion>', encoding="utf-8")
    return scripts / "Launch.lua"


class Installation(unittest.TestCase):
    def test_official_source_and_both_layouts_without_headless_files(self):
        self.assertEqual(LOCK["repository"], "https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2.git")
        with tempfile.TemporaryDirectory() as directory:
            for repository in [False, True]:
                root = Path(directory) / str(repository)
                fake_install(root, repository)
                layout = engine_layout(root)
                self.assertEqual(layout.kind, "repository" if repository else "installed")
                self.assertEqual(layout.version, "0.23.1")
                self.assertFalse((layout.scripts / "HeadlessWrapper.lua").exists())

    def test_auto_detection_and_ambiguous_installations(self):
        with patch.dict(os.environ, {}, clear=True), patch("pob_poe2_mcp.engine.installed_engine_dirs", return_value=[Path("one")]):
            self.assertEqual(resolve_engine_dir(), Path("one"))
        with patch.dict(os.environ, {}, clear=True), patch("pob_poe2_mcp.engine.installed_engine_dirs", return_value=[Path("one"), Path("two")]):
            with self.assertRaises(EngineError) as error:
                resolve_engine_dir()
            self.assertEqual(error.exception.code, "MULTIPLE_INSTALLATIONS")

    def test_generated_client_configuration_has_both_modes(self):
        config = client_config()["mcpServers"]
        self.assertEqual(set(config), {"pob-engine", "pob-app"})
        self.assertEqual(config["pob-app"]["args"][-2:], ["--mode", "app"])
        self.assertTrue(Path(config["pob-app"]["command"]).is_absolute())


class BridgeInstallation(unittest.TestCase):
    def test_reinstallation_and_removal_restore_exact_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory, patch("pob_poe2_mcp.engine.sys.platform", "win32"):
            root, state = Path(directory) / "PoB", Path(directory) / "state"
            launch = fake_install(root)
            launch.write_bytes(b"-- original\r\nfunction example() end\r\n\r\n")
            original = launch.read_bytes()
            install_bridge(root, state)
            install_bridge(root, state)
            self.assertEqual(launch.read_text(encoding="utf-8").count(BEGIN), 1)
            config = json.loads((state / "config.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(config["token"]), 32)
            uninstall_bridge(root, state)
            self.assertEqual(launch.read_bytes(), original)

    def test_removal_preserves_later_application_changes(self):
        with tempfile.TemporaryDirectory() as directory, patch("pob_poe2_mcp.engine.sys.platform", "win32"):
            root, state = Path(directory) / "PoB", Path(directory) / "state"
            launch = fake_install(root)
            install_bridge(root, state)
            launch.write_text("-- Позднее обновление\n" + launch.read_text(encoding="utf-8"), encoding="utf-8")
            uninstall_bridge(root, state)
            self.assertIn("Позднее обновление", launch.read_text(encoding="utf-8"))
            self.assertNotIn(BEGIN, launch.read_text(encoding="utf-8"))

    def test_incomplete_hook_is_not_overwritten(self):
        with self.assertRaises(EngineError):
            remove_hook("original\n" + BEGIN)

    def test_app_connection_without_endpoint_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(EngineError) as error:
            AppTransport(endpoint=Path(directory) / "missing.json")
        self.assertEqual(error.exception.code, "BRIDGE_NOT_RUNNING")


if __name__ == "__main__":
    unittest.main()
