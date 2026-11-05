"""Проверки настоящего Lua API и MCP без изменения эталонов и файлов сборок."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pob_poe2_mcp.api import BuildAPI, EngineError
from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir
from pob_poe2_mcp.server import TOOLS, validate

ROOT = Path(__file__).resolve().parents[1]
ENGINE = resolve_engine_dir()
HAS_ENGINE = sys.platform == "win32" and engine_layout(ENGINE) is not None


@unittest.skipUnless(HAS_ENGINE, "Нужен движок: задайте POB_DIR или выполните setup")
class AssistantAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = BuildAPI(pob_dir=ENGINE)

    @classmethod
    def tearDownClass(cls):
        cls.api.close()

    def test_create_detail_export_reload(self):
        api = self.api
        classes = api.call("getCatalog", {"kind": "classes"})["entries"]
        class_id = next(entry["id"] for entry in classes if entry["name"] == "Sorceress")
        api.call("createBuild", {"name": "Проверка API", "level": 90, "classId": class_id})
        gem = api.call("getCatalog", {"query": "Fireball"})["entries"][0]
        api.call("addSkillGroup", {"label": "Основное умение", "gems": [{"id": gem["id"], "level": 20}]})
        api.call("setConfig", {"values": {"enemyIsBoss": "None"}})
        api.call("addItem", {"raw": "Rarity: Normal\nWithered Wand\n", "slot": "Weapon 1"})
        before = api.call("getBuildReport")
        self.assertEqual(before["snapshot"]["buildInfo"]["level"], 90)
        self.assertEqual(before["groups"][0]["gems"][0]["level"], 20)
        self.assertGreater(len(before["stats"]), 100)
        self.assertEqual(before["config"]["enemyIsBoss"], "None")
        self.assertEqual(before["items"][0]["base"], "Withered Wand")
        self.assertTrue(any(slot["name"] == "Weapon 1" and slot["itemId"] == 1 for slot in before["slots"]))
        api.call("setCustomMods", {"text": "100% increased Spell Damage"})
        modified = api.call("getBuildReport")
        self.assertGreater(modified["stats"]["TotalDPS"], before["stats"]["TotalDPS"])
        self.assertTrue(any("100% increased Spell Damage" in block["text"] for block in modified["customMods"]))
        xml = api.call("exportBuild")["xml"]
        api.call("loadBuild", {"xml": xml})
        after = api.call("getBuildReport")
        self.assertAlmostEqual(after["stats"]["TotalDPS"], modified["stats"]["TotalDPS"])
        self.assertEqual(after["groups"], modified["groups"])
        self.assertEqual(after["items"], modified["items"])
        check = api.check([{"stat": "TotalDPS", "min": 1}, {"stat": "MissingStat", "min": 0}])
        self.assertFalse(check["targetsPassed"])
        self.assertIsNone(check["checks"][1]["actual"])

    def test_errors_rollback_revision(self):
        api = self.api
        api.call("createBuild", {"level": 1})
        api.call("loadBuild", {"xml": api.call("exportBuild")["xml"]})
        before = api.call("exportBuild")["xml"]
        before_report = api.call("getBuildReport")
        revision = api.revision
        for method, params in [
            ("addSkillGroup", {"gems": [{"id": "invented"}]}),
            ("addItem", {"raw": "Rarity: Normal\nWithered Wand\n", "slot": "Boots"}),
            ("setConfig", {"values": {"enemyIsBoss": "invented"}}),
            ("treeAction", {"id": -1, "action": "allocate"}),
            ("createBuild", {"level": 101}),
        ]:
            with self.assertRaises(EngineError):
                api.call(method, params)
            self.assertEqual(api.revision, revision)
            after_report = api.call("getBuildReport")
            for field in ["stats", "config", "groups", "items", "allocatedNodes"]:
                self.assertEqual(after_report[field], before_report[field], field)
            self.assertEqual(after_report["snapshot"]["buildInfo"], before_report["snapshot"]["buildInfo"])
        with self.assertRaises(EngineError) as caught:
            api.call("getBuildReport", {"revision": revision - 1})
        self.assertEqual(caught.exception.code, "STALE_REVISION")

    def test_pagination(self):
        first = self.api.call("getCatalog", {"kind": "bases", "limit": 2})
        second = self.api.call("getCatalog", {"kind": "bases", "limit": 2, "offset": 2})
        self.assertEqual(len(first["entries"]), 2)
        self.assertNotEqual(first["entries"], second["entries"])

    def test_image_data_is_consistent_and_does_not_modify_build(self):
        api = self.api
        api.call('createBuild', {'classId': 2, 'level': 90})
        before = api.call('exportBuild')['xml']
        revision = api.revision
        image_data = api.call('getBuildImageData', {'view': 'tree'})
        self.assertGreater(len(image_data['tree']['nodes']), 100)
        self.assertGreater(len(image_data['tree']['edges']), 100)
        allocated = {node['id'] for node in image_data['tree']['nodes'] if node['allocated']}
        self.assertEqual(allocated, set(image_data['report']['allocatedNodes']))
        self.assertEqual(image_data['report']['snapshot']['buildInfo']['level'], 90)
        self.assertEqual(api.revision, revision)
        self.assertEqual(api.call('exportBuild')['xml'], before)
        node = next(node for node in image_data['tree']['nodes'] if node['type'] == 'Notable')
        detailed = api.call('getBuildImageData', {'view': 'node', 'id': node['id']})
        self.assertTrue(detailed['tooltip']['lines'])
        self.assertEqual(api.call('exportBuild')['xml'], before)

    def test_original_tree_icons_scale_with_viewport_and_zoom(self):
        api = self.api
        api.call('createBuild', {'classId': 2, 'level': 90})
        before = api.call('exportBuild')['xml']
        regular = api.call('getBuildImageData', {'view': 'tree', 'width': 800, 'height': 600})['scene']
        enlarged = api.call('getBuildImageData', {'view': 'tree', 'width': 1600, 'height': 1100, 'zoom': 2})['scene']

        def frame_width(scene):
            frame = next(command for command in scene['commands'] if command['file'].endswith('_64_64_BC1.dds.zst'))
            return max(frame['positions'][::2]) - min(frame['positions'][::2])

        self.assertGreater(enlarged['scale'], regular['scale'])
        self.assertAlmostEqual(frame_width(regular) / regular['scale'], frame_width(enlarged) / enlarged['scale'])
        self.assertEqual(api.call('exportBuild')['xml'], before)

    def test_live_session_uses_same_api_and_preserves_manual_changes(self):
        process = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "pob_poe2_mcp/runner.py"),
             "--pob-dir", str(ENGINE), "--script", str(ROOT / "tests/session_live.lua")],
            capture_output=True, encoding="utf-8", timeout=90,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("LIVE_SESSION_OK", process.stdout)

    def test_node_catalog_after_ascendancy_selection(self):
        api = self.api
        api.call("createBuild", {"classId": 2, "level": 90})
        api.call("treeOptions", {"ascendancy": 2})
        choices = api.call("getCatalog", {"kind": "nodes", "query": "Concoction"})
        self.assertTrue(any(node["name"] == "Brew Concoction" for node in choices["entries"]))
        attributes = api.call("getCatalog", {"kind": "nodes", "query": "Attribute", "limit": 200})
        options = [node["attributeOptions"] for node in attributes["entries"] if node.get("attributeOptions")]
        self.assertTrue(options)
        self.assertTrue(all(isinstance(option["name"], str) for choices in options for option in choices))

    def test_tree_and_warnings_from_lua(self):
        api = self.api
        api.call("createBuild", {"classId": 2, "level": 90})
        gem = api.call("getCatalog", {"query": "Fireball"})["entries"][0]
        api.call("addSkillGroup", {"gems": [{"id": gem["id"], "level": 20}]})
        report = api.call("getBuildReport")
        self.assertTrue(any("Intelligence" in warning for warning in report["warnings"]))
        nodes = api.call("getCatalog", {"kind": "nodes", "query": "Dexterity", "limit": 200})["entries"]
        candidates = [node for node in nodes if node.get("path") and node["type"] != "Mastery"]
        node = min(candidates, key=lambda node: len(node["path"]))
        tooltip = api.call("getNodeTooltip", {"id": node["id"]})
        self.assertTrue(tooltip["lines"])
        api.call("treeAction", {"id": node["id"], "action": "allocate", "attribute": 2})
        self.assertIn(node["id"], api.call("getBuildReport")["allocatedNodes"])
        api.call("treeAction", {"id": node["id"], "action": "refund"})
        self.assertNotIn(node["id"], api.call("getBuildReport")["allocatedNodes"])


class MCP(unittest.TestCase):
    def test_schema_rejects_wrong_arguments(self):
        schema = next(tool["inputSchema"] for tool in TOOLS if tool["name"] == "pob_create_build")
        for args in [{"level": True}, {"level": 101}, {"lua": "print(1)"}]:
            with self.assertRaises(ValueError):
                validate(args, schema)

    @unittest.skipUnless(HAS_ENGINE, "Нужен движок: задайте POB_DIR или выполните setup")
    def test_stdio_real_lua(self):
        requests = [
            {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
            {"method": "notifications/initialized"},
            {"id": 2, "method": "tools/list"},
            {"id": 3, "method": "tools/call", "params": {"name": "pob_create_build", "arguments": {"level": 90}}},
            {"id": 4, "method": "tools/call", "params": {"name": "pob_check_build", "arguments": {"targets": [{"stat": "Life", "min": 1}]}}},
            {"id": 5, "method": "tools/call", "params": {"name": "pob_create_build", "arguments": {"level": 101}}},
            {"id": 6, "method": "tools/call", "params": {"name": "pob_export_xml", "arguments": {}}},
            {"id": 7, "method": "tools/call", "params": {"name": "pob_render_image", "arguments": {"view": "stats", "query": "Life", "width": 640, "height": 480}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "run.py"), "serve", "--pob-dir", str(ENGINE)],
                cwd=directory,
                input="\n".join(json.dumps({"jsonrpc": "2.0", **r}) for r in requests) + "\n",
                capture_output=True, encoding="utf-8", timeout=90,
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(responses), 7)
        self.assertEqual(len(responses[1]["result"]["tools"]), len(TOOLS))
        self.assertTrue(responses[3]["result"]["structuredContent"]["result"]["targetsPassed"])
        self.assertTrue(responses[4]["result"]["isError"])
        self.assertIn("<PathOfBuilding2>", responses[5]["result"]["structuredContent"]["result"]["xml"])
        rendered = responses[6]['result']
        self.assertFalse(rendered['isError'], rendered)
        self.assertEqual(rendered['content'][1]['type'], 'image')
        self.assertEqual(rendered['content'][1]['mimeType'], 'image/png')
        self.assertEqual(rendered['structuredContent']['revision'], responses[5]['result']['structuredContent']['revision'])


if __name__ == "__main__":
    unittest.main()
