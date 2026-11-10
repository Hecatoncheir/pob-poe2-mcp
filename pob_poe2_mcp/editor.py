"""Клиент локального канала открытого редактора PoB II."""

from http.client import HTTPConnection, HTTPException
import json
from pathlib import Path

from .api import MAX_MESSAGE
from .errors import EngineError

EDITOR_TOOLS = {
    "pob_catalog", "pob_check_build", "pob_export_xml", "pob_inspect_item",
    "pob_tree_action", "pob_add_item", "pob_equip_item", "pob_select_weapon_set",
    "pob_add_skill_group", "pob_update_skill_group", "pob_delete_skill_group",
    "pob_select_main_skill", "pob_set_config",
}


class EditorClient:
    def __init__(self, endpoint, timeout):
        self.endpoint = Path(endpoint).expanduser()
        self.timeout = timeout
        self.token = None
        self.revision = None

    def _connection_details(self):
        try:
            details = json.loads(self.endpoint.read_text(encoding="utf-8"))
            port, token = details["port"], details["token"]
            if type(port) is not int or not 1024 <= port <= 65535:
                raise ValueError()
            if not isinstance(token, str) or len(token) < 32 or not token.isascii() or not token.isprintable():
                raise ValueError()
            return port, token
        except (OSError, ValueError, KeyError, TypeError):
            self.revision = None
            raise EngineError("EDITOR_DISABLED", "Включите правки через MCP для открытой сборки PoB II.") from None

    def call(self, tool, arguments):
        port, token = self._connection_details()
        if token != self.token:
            self.token = token
            self.revision = None
        payload = {"tool": tool, "arguments": arguments, "revision": self.revision}
        reply = self._post(port, token, payload)
        if "error" in reply:
            error = reply["error"]
            raise EngineError(error["code"], error["message"])
        self.revision = reply["revision"]
        return reply["result"]

    def _post(self, port, token, payload):
        connection = HTTPConnection("127.0.0.1", port, timeout=self.timeout)
        try:
            connection.request(
                "POST", "/edit", json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            if response.status != 200:
                raise OSError()
            body = response.read(MAX_MESSAGE + 1)
            if len(body) > MAX_MESSAGE:
                raise ValueError()
            return json.loads(body)
        except (OSError, HTTPException, ValueError):
            self.revision = None
            raise EngineError("EDITOR_UNAVAILABLE", "Нет ответа PoB II. Проверьте переключатель MCP и заново запросите отчёт.") from None
        finally:
            connection.close()
