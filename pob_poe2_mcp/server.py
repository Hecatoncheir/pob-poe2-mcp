"""MCP stdio для создания и проверки PoB-сборок; stdout содержит только JSON-RPC."""

import json
import math
import sys
from pathlib import Path

from . import __version__
from .api import BuildAPI, EngineError, MAX_MESSAGE

MANIFEST = Path(__file__).parent / "data/tools.json"
TOOLS = json.loads(MANIFEST.read_text(encoding="utf-8"))
METHODS = {
    "pob_catalog": "getCatalog", "pob_create_build": "createBuild",
    "pob_import_xml": "loadBuild", "pob_add_skill_group": "addSkillGroup",
    "pob_add_item": "addItem", "pob_set_config": "setConfig",
    "pob_set_custom_mods": "setCustomMods", "pob_tree_action": "treeAction",
    "pob_tree_options": "treeOptions", "pob_select_main_skill": "selectMainSkill",
    "pob_node_tooltip": "getNodeTooltip", "pob_export_xml": "exportBuild",
}


def validate(value, schema):
    """Проверка используемого подмножества JSON Schema до обращения к Lua."""
    kind = schema.get("type")
    valid = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "boolean": isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
    }.get(kind, True)
    if not valid or ("enum" in schema and value not in schema["enum"]):
        raise ValueError("Неверный тип или значение аргумента")
    if kind in ["integer", "number"]:
        if not math.isfinite(value) or value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise ValueError("Число вне допустимого диапазона")
    if kind == "string" and len(value) > schema.get("maxLength", MAX_MESSAGE):
        raise ValueError("Строка превышает лимит")
    if kind == "object":
        properties = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", [])):
            raise ValueError("Отсутствует обязательный аргумент")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError("Неизвестный аргумент")
        for key, item in value.items():
            child = properties.get(key, schema.get("additionalProperties"))
            if isinstance(child, dict):
                validate(item, child)
    if kind == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10000):
            raise ValueError("Неверный размер списка")
        for item in value:
            validate(item, schema["items"])


class Server:
    def __init__(self, pob_dir=None, timeout=60):
        self.api = None
        self.initialized = False
        self.pob_dir = pob_dir
        self.timeout = timeout

    def handle(self, method, params):
        if method == "initialize":
            self.initialized = True
            requested = params.get("protocolVersion")
            version = requested if requested in ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"] else "2025-11-25"
            return {"protocolVersion": version, "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pob-poe2-mcp", "version": __version__},
                    "instructions": "Все игровые расчёты выполняет Lua. Сначала прочитайте каталоги. Проверяйте warnings, ошибки камней, unsupported модификаторы и config. Не называйте сборку проверенной в игре: проверен только расчёт PoB."}
        if method == "ping":
            return {}
        if not self.initialized:
            raise ValueError("Сначала initialize")
        if method == "tools/list":
            return {"tools": TOOLS}
        if method != "tools/call":
            raise LookupError("Неизвестный метод MCP")
        name, args = params.get("name"), params.get("arguments", {})
        tool = next((tool for tool in TOOLS if tool["name"] == name), None)
        if not tool:
            raise ValueError("Неизвестный инструмент")
        try:
            validate(args, tool["inputSchema"])
            if self.api is None:
                self.api = BuildAPI(pob_dir=self.pob_dir, timeout=self.timeout)
            result = self.api.check(args.get("targets")) if name == "pob_check_build" else self.api.call(METHODS[name], args)
            payload = {"revision": self.api.revision, "result": result}
            return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "structuredContent": payload, "isError": False}
        except (EngineError, ValueError) as error:
            return {"content": [{"type": "text", "text": json.dumps({"code": getattr(error, "code", "INVALID_ARGUMENTS"), "message": str(error)}, ensure_ascii=False)}], "isError": True}

    def close(self):
        if self.api:
            self.api.close()


def main(pob_dir=None, timeout=60):
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    server = Server(pob_dir=pob_dir, timeout=timeout)
    try:
        while True:
            line = sys.stdin.buffer.readline(MAX_MESSAGE + 1)
            if not line:
                break
            request = None
            try:
                if len(line) > MAX_MESSAGE:
                    raise ValueError("Сообщение превышает лимит")
                request = json.loads(line)
                if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                    raise ValueError("Неверный JSON-RPC")
                if "id" not in request:
                    continue
                params = request.get("params", {})
                if not isinstance(params, dict):
                    raise ValueError("params должен быть объектом")
                result = server.handle(request["method"], params)
                response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
            except Exception as error:
                response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                            "error": {"code": -32700 if isinstance(error, json.JSONDecodeError) else -32601 if isinstance(error, LookupError) else -32602 if isinstance(error, ValueError) else -32603, "message": str(error)}}
            print(json.dumps(response, ensure_ascii=False), flush=True)
            if len(line) > MAX_MESSAGE:
                break
    finally:
        server.close()


if __name__ == "__main__":
    main()
