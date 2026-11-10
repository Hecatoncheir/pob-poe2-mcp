"""Команды запуска MCP, загрузки движка и диагностики установки."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from . import __version__
from .api import BuildAPI
from .bridge import install_bridge, uninstall_bridge
from .engine import LOCK, engine_layout, resolve_engine_dir, setup_engine
from .errors import EngineError
from .server import main as serve


def positive_timeout(value):
    timeout = float(value)
    if not 0 < timeout < float("inf"):
        raise argparse.ArgumentTypeError("Ожидалось конечное положительное число секунд")
    return timeout


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="command")
    for name, help_text in [("serve", "Запустить MCP stdio"), ("doctor", "Проверить запуск настоящего Lua")]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--pob-dir", help="Каталог с src/ и runtime/; иначе POB_DIR или каталог setup")
        command.add_argument("--timeout", type=positive_timeout, default=60, help="Ожидание Lua в секундах")
        modes = ["engine", "app", "editor"] if name == "serve" else ["engine", "app"]
        command.add_argument("--mode", choices=modes, default="engine")
        if name == "serve":
            command.add_argument("--editor-endpoint", help="Файл подключения, созданный редактором PoB II")
    for name, help_text in [("install-bridge", "Подключить MCP к текущей сборке окна PoB"), ("uninstall-bridge", "Удалить подключение из Launch.lua")]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--pob-dir", help="Каталог PoB; по умолчанию автоматический поиск")
    setup = commands.add_parser("setup", help="Загрузить совместимый движок из GitHub в новый каталог")
    setup.add_argument("--destination", help="Новый каталог; по умолчанию внутри LOCALAPPDATA")
    config = commands.add_parser("config", help="Показать готовую настройку MCP-клиента с абсолютными путями")
    config.add_argument("--mode", choices=["engine", "app", "editor", "both"], default="both")
    config.add_argument("--editor-endpoint")
    return result


def client_config(mode="both", editor_endpoint=None):
    module = ["-X", "utf8", "-m", "pob_poe2_mcp"]
    if mode == "editor":
        if not editor_endpoint:
            raise EngineError("EDITOR_NOT_CONFIGURED", "Укажите --editor-endpoint для режима editor.")
        script = Path(__file__).resolve().parents[1] / "run.py"
        entry = ["-X", "utf8", str(script)] if script.is_file() else module
        args = [*entry, "serve", "--mode", "editor", "--editor-endpoint", str(Path(editor_endpoint).expanduser().resolve())]
        return {"mcpServers": {"pob2-editor": {"command": sys.executable, "args": args}}}
    modes = ["engine", "app"] if mode == "both" else [mode]
    return {"mcpServers": {"pob-" + name: {
        "command": sys.executable,
        "args": [*module, "serve", "--mode", name],
    } for name in modes}}


def doctor(pob_dir, timeout, mode="engine"):
    with BuildAPI(pob_dir=pob_dir, timeout=timeout, mode=mode) as api:
        classes = api.call("getCatalog", {"kind": "classes"})
        layout = engine_layout(api.pob_dir)
        print(json.dumps({"ok": True, "engineDir": str(api.pob_dir),
                          "mode": mode, "layout": layout.kind, "installedVersion": layout.version,
                          "pinnedRepository": LOCK["repository"],
                          "pinnedRevision": LOCK["revision"], "classes": classes["total"],
                          "capabilities": api.capabilities}, ensure_ascii=False, indent=2))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "config":
            print(json.dumps(client_config(args.mode, args.editor_endpoint), ensure_ascii=False, indent=2))
            return
        if args.command == "setup":
            directory = setup_engine(args.destination)
            print(f"Движок готов: {directory}")
            print(f'Проверка: pob-poe2-mcp doctor --pob-dir "{directory}"')
            return
        if args.command in ["install-bridge", "uninstall-bridge"]:
            action = install_bridge if args.command == "install-bridge" else uninstall_bridge
            print(json.dumps(action(args.pob_dir), ensure_ascii=False, indent=2))
            print("Перезапустите PoB, чтобы изменение вступило в силу.")
            return
        mode = getattr(args, "mode", "engine")
        pob_dir = getattr(args, "pob_dir", None)
        if mode == "engine":
            pob_dir = resolve_engine_dir(pob_dir)
        timeout = getattr(args, "timeout", 60)
        if args.command == "doctor":
            doctor(pob_dir, timeout, mode)
            return
        editor_endpoint = getattr(args, "editor_endpoint", None)
        if mode == "editor" and not editor_endpoint:
            raise EngineError("EDITOR_NOT_CONFIGURED", "Укажите --editor-endpoint для режима editor.")
        serve(pob_dir=pob_dir, timeout=timeout, mode=mode, editor_endpoint=editor_endpoint)
    except (EngineError, OSError, subprocess.SubprocessError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        raise SystemExit(1) from None
