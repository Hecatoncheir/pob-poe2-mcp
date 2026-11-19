"""Клиент локального канала открытого редактора PoB II."""

from http.client import HTTPConnection, HTTPException
import json
from pathlib import Path

from .api import MAX_MESSAGE
from .errors import EngineError

EDITOR_TOOLS = {
    "pob_catalog", "pob_create_build", "pob_check_build", "pob_export_xml", "pob_inspect_item",
    "pob_tree_action", "pob_add_item", "pob_equip_item", "pob_select_weapon_set",
    "pob_add_skill_group", "pob_update_skill_group", "pob_delete_skill_group",
    "pob_select_main_skill", "pob_set_config",
    "pob_import_xml", "pob_set_custom_mods", "pob_tree_options", "pob_node_tooltip",
    "pob_render_image", "pob_get_tree", "pob_tree_icons", "pob_tree_textures",
    "pob_tree_hover", "pob_node_power", "pob_gem_icons", "pob_gem_supports",
    "pob_preview_support", "pob_gem_tooltip", "pob_compare_item",
    "pob_trade_catalog", "pob_trade_search", "pob_import_character",
}
EDITOR_APP_TOOLS = {
    "pob_editor_status", "pob_editor_app", "pob_editor_components",
    "pob_editor_library", "pob_editor_history", "pob_editor_notes",
    "pob_editor_files", "pob_editor_progression", "pob_editor_ui",
    "pob_editor_job",
}
EDITOR_TOOLS |= EDITOR_APP_TOOLS


class EditorClient:
    def __init__(self, endpoint, timeout):
        self.endpoint = Path(endpoint).expanduser()
        self.timeout = timeout
        self.token = None
        self.revision = None
        self.content = []

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
            raise EngineError("EDITOR_DISABLED", "Включите правки через MCP в PoB II.") from None

    def call(self, tool, arguments):
        self.content = []
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
        self.content = [item for item in reply.get("content", []) if item.get("type") == "image"]
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
