"""Проверка аутентифицированного подключения без запуска второго движка."""

import json
from pathlib import Path
import socketserver
import tempfile
import threading
import unittest
from unittest.mock import patch

from pob_poe2_mcp.api import BuildAPI


class AppConnection(unittest.TestCase):
    def test_api_uses_token_and_current_app_revision(self):
        requests = []
        token = "a" * 64

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    request = json.loads(line)
                    requests.append(request)
                    result = {"platform": "windows-app"} if request["method"] == "initialize" else {"level": 42}
                    response = {"protocol": 1, "id": request["id"], "revision": 7, "result": result}
                    self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))
                    self.wfile.flush()

        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server, tempfile.TemporaryDirectory() as directory:
            thread = threading.Thread(target=server.handle_request, daemon=True)
            thread.start()
            endpoint = Path(directory) / "endpoint.json"
            endpoint.write_text(json.dumps({"port": server.server_address[1], "token": token, "installDir": directory}), encoding="utf-8")
            with patch("pob_poe2_mcp.api.ProcessTransport", side_effect=AssertionError("Не должен запускаться")):
                with BuildAPI(mode="app", endpoint=endpoint) as api:
                    self.assertEqual(api.capabilities["platform"], "windows-app")
                    self.assertEqual(api.call("getSnapshot"), {"level": 42})
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual([request["token"] for request in requests], [token, token])
        self.assertEqual(requests[1]["params"]["revision"], 7)


if __name__ == "__main__":
    unittest.main()
