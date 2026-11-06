"""MCP stdio для создания и проверки PoB-сборок; stdout содержит только JSON-RPC."""

import json
import base64
import math
import sys
from pathlib import Path

from . import __version__
from .api import BuildAPI, EngineError, MAX_MESSAGE
from .images import render_build_image, validate_image_args
from .tree_icons import TreeIcons
from .tree_scene_assets import SceneAssets
from .gem_assets import GemAssets
from .gem_supports import compatible_supports

MANIFEST = Path(__file__).parent / "data/tools.json"
TOOLS = json.loads(MANIFEST.read_text(encoding="utf-8"))
METHODS = {
    "pob_catalog": "getCatalog", "pob_create_build": "createBuild",
    "pob_import_xml": "loadBuild", "pob_add_skill_group": "addSkillGroup",
    "pob_add_item": "addItem", "pob_set_config": "setConfig",
    "pob_set_custom_mods": "setCustomMods", "pob_tree_action": "treeAction",
    "pob_tree_options": "treeOptions", "pob_select_main_skill": "selectMainSkill",
    "pob_node_tooltip": "getNodeTooltip", "pob_export_xml": "exportBuild",
    "pob_render_image": "getBuildImageData",
    "pob_get_tree": "getTreeGeometry",
    "pob_tree_icons": "getTreeIconAssets",
    "pob_tree_textures": None,
    "pob_tree_hover": "getTreeHover",
    "pob_node_power": "getNodePower",
    "pob_gem_icons": "getGemIconAssets",
    "pob_gem_tooltip": "getGemTooltip",
    "pob_gem_supports": None,
    "pob_update_skill_group": "updateSkillGroup",
    "pob_delete_skill_group": "deleteSkillGroup",
    "pob_inspect_item": "inspectItem",
    "pob_compare_item": "compareItem",
    "pob_trade_catalog": "getTradeCatalog",
    "pob_trade_search": "buildTradeSearch",
    "pob_equip_item": "equipItem",
    "pob_select_weapon_set": "selectWeaponSet",
}
READ_ONLY_TOOLS = {"pob_catalog", "pob_check_build", "pob_node_tooltip", "pob_export_xml", "pob_render_image", "pob_get_tree", "pob_tree_icons", "pob_tree_textures", "pob_tree_hover", "pob_node_power"}
READ_ONLY_TOOLS.update({'pob_gem_icons', 'pob_gem_supports', 'pob_gem_tooltip'})
READ_ONLY_TOOLS.add('pob_inspect_item')
READ_ONLY_TOOLS.update({'pob_compare_item', 'pob_trade_catalog', 'pob_trade_search'})


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
    def __init__(self, pob_dir=None, timeout=60, mode="engine"):
        self.api = None
        self.initialized = False
        self.pob_dir = pob_dir
        self.timeout = timeout
        self.mode = mode
        self.icons = None
        self.scene_assets = None
        self.gem_assets = None

    def execute_tool(self, name, args):
        if self.api is None:
            self.api = BuildAPI(pob_dir=self.pob_dir, timeout=self.timeout, mode=self.mode)
        try:
            if name == 'pob_gem_supports':
                return compatible_supports(self.api, args['gems'], self.timeout, args.get('groupId'))
            if name == 'pob_node_power' and self.mode != 'engine':
                raise ValueError('Отчёт узлов требует отдельной сессии engine')
            if name == 'pob_tree_textures':
                if self.scene_assets is None:
                    raise ValueError('Сначала загрузите готовую сцену дерева')
                return self.scene_assets.read(args['token'])
            if name == 'pob_render_image' and self.mode == 'app':
                return self.app_image_data(args)
            return self.api.check(args.get("targets")) if name == "pob_check_build" else self.api.call(METHODS[name], args)
        except (EngineError, ValueError):
            if self.mode == "app" and self.api.closed:
                self.api = None
            raise

    def app_image_data(self, args):
        report = self.api.call('getBuildReport')
        if args.get('view', 'overview') not in ('tree', 'node'):
            return {'report': report}
        xml = self.api.call('exportBuild')['xml']
        with BuildAPI(pob_dir=self.api.pob_dir, timeout=self.timeout) as engine:
            engine.call('loadBuild', {'xml': xml})
            data = engine.call('getBuildImageData', args)
        data['report'] = report
        return data

    def call_tool(self, name, args):
        previous_api = self.api
        try:
            return self.execute_tool(name, args)
        except (EngineError, ValueError):
            if previous_api is None or self.api is not None or name not in READ_ONLY_TOOLS:
                raise
        return self.execute_tool(name, args)

    def tool_response(self, name, args, result):
        image = None
        if name == 'pob_gem_icons':
            if self.gem_assets is None:
                self.gem_assets = GemAssets(self.api.pob_dir)
            result = self.gem_assets.render(result)
        if name in ('pob_get_tree', 'pob_tree_hover', 'pob_node_power') and 'scene' in result:
            if self.scene_assets is None:
                self.scene_assets = SceneAssets(self.api.pob_dir)
            result['scene'] = self.scene_assets.prepare(result['scene'])
        if name == 'pob_tree_icons':
            if self.icons is None:
                self.icons = TreeIcons(self.api.pob_dir)
            result = self.icons.render(result)
        if name == 'pob_render_image':
            image, result = render_build_image(result, args, getattr(self.api, 'pob_dir', None))
        payload = {"revision": self.api.revision, "result": result}
        content = [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]
        if image is not None:
            content.append({"type": "image", "mimeType": "image/png", "data": base64.b64encode(image).decode('ascii')})
        return {"content": content, "structuredContent": payload, "isError": False}

    def handle(self, method, params):
        if method == "initialize":
            self.initialized = True
            requested = params.get("protocolVersion")
            version = requested if requested in ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"] else "2025-11-25"
            mode_info = " Режим app: операции изменяют текущую сборку открытого окна PoB; сохранение выполняет пользователь." if self.mode == "app" else " Режим engine: отдельная сессия расчёта на файлах установленного PoB."
            return {"protocolVersion": version, "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pob-poe2-mcp", "version": __version__},
                    "instructions": "Все игровые расчёты выполняет Lua. Сначала прочитайте каталоги. Проверяйте warnings, ошибки камней, unsupported модификаторы и config. Не называйте сборку проверенной в игре: проверен только расчёт PoB." + mode_info}
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
            if name == 'pob_render_image':
                validate_image_args(args)
            result = self.call_tool(name, args)
            return self.tool_response(name, args, result)
        except (EngineError, ValueError) as error:
            return {"content": [{"type": "text", "text": json.dumps({"code": getattr(error, "code", "INVALID_ARGUMENTS"), "message": str(error)}, ensure_ascii=False)}], "isError": True}

    def close(self):
        if self.api:
            self.api.close()


def main(pob_dir=None, timeout=60, mode="engine"):
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    server = Server(pob_dir=pob_dir, timeout=timeout, mode=mode)
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
