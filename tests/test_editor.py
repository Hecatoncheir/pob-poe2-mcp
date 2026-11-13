"""Проверки маршрута MCP к открытому редактору по локальному HTTP."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from pob_poe2_mcp.server import Server


class EditorMode(unittest.TestCase):
    def test_routes_to_editor_and_keeps_revision_after_refused_edit(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.path, self.headers["Authorization"], request))
                tool = request["tool"]
                if tool == "pob_check_build":
                    reply = {"result": {"report": {"level": 90}}, "revision": 5}
                elif tool == "pob_create_build":
                    reply = {"result": {"id": "build.xml"}, "revision": 5}
                elif request["revision"] == 5:
                    reply = {"result": {"changed": True}, "revision": 6}
                else:
                    reply = {"error": {"code": "STALE_REVISION", "message": "Обновите отчёт"}}
                data = json.dumps(reply).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        with tempfile.TemporaryDirectory() as directory, HTTPServer(("127.0.0.1", 0), Handler) as http:
            worker = Thread(target=http.serve_forever, daemon=True)
            worker.start()
            try:
                endpoint = Path(directory) / "endpoint.json"
                token = "a" * 64
                endpoint.write_text(json.dumps({"port": http.server_port, "token": token}), encoding="utf-8")
                with patch("pob_poe2_mcp.server.BuildAPI", side_effect=AssertionError("Отдельный Lua не нужен")):
                    self._exercise(endpoint, http.server_port)
                self.assertEqual([entry[0] for entry in requests], ["/edit"] * 6)
                self.assertEqual([entry[1] for entry in requests], ["Bearer " + token] * 5 + ["Bearer " + "b" * 64])
                self.assertEqual([entry[2]["revision"] for entry in requests], [None, None, 5, 5, 6, None])
                self.assertEqual(requests[2][2]["tool"], "pob_create_build")
                self.assertEqual(requests[2][2]["arguments"], {"level": 90})
            finally:
                http.shutdown()
                worker.join(timeout=2)

    def _exercise(self, endpoint, port):
        server = Server(mode="editor", editor_endpoint=endpoint)
        server.handle("initialize", {})
        tools = {tool["name"] for tool in server.handle("tools/list", {})["tools"]}
        self.assertIn("pob_tree_action", tools)
        self.assertIn("pob_equip_item", tools)
        self.assertIn("pob_update_skill_group", tools)
        self.assertIn("pob_create_build", tools)

        args = {"name": "pob_tree_action", "arguments": {"id": 42, "action": "allocate"}}
        self.assertTrue(server.handle("tools/call", args)["isError"])
        report = server.handle("tools/call", {"name": "pob_check_build"})
        self.assertEqual(report["structuredContent"]["revision"], 5)
        created = server.handle("tools/call", {"name": "pob_create_build", "arguments": {"level": 90}})
        self.assertEqual(created["structuredContent"]["result"], {"id": "build.xml"})
        changed = server.handle("tools/call", args)
        self.assertEqual(changed["structuredContent"]["revision"], 6)
        self.assertTrue(server.handle("tools/call", args)["isError"])
        self.assertEqual(server.editor.revision, 6)
        endpoint.write_text(json.dumps({"port": port, "token": "b" * 64}), encoding="utf-8")
        self.assertTrue(server.handle("tools/call", args)["isError"])


if __name__ == "__main__":
    unittest.main()
