"""Команды запуска MCP, загрузки движка и диагностики установки."""

import argparse
import json
import subprocess
import sys

from . import __version__
from .api import BuildAPI
from .engine import LOCK, resolve_engine_dir, setup_engine
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
    setup = commands.add_parser("setup", help="Загрузить совместимый движок из GitHub в новый каталог")
    setup.add_argument("--destination", help="Новый каталог; по умолчанию внутри LOCALAPPDATA")
    return result


def doctor(pob_dir, timeout):
    with BuildAPI(pob_dir=pob_dir, timeout=timeout) as api:
        classes = api.call("getCatalog", {"kind": "classes"})
        print(json.dumps({"ok": True, "engineDir": str(api.pob_dir),
                          "pinnedRevision": LOCK["revision"], "classes": classes["total"],
                          "capabilities": api.capabilities}, ensure_ascii=False, indent=2))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "setup":
            directory = setup_engine(args.destination)
            print(f"Движок готов: {directory}")
            print(f'Проверка: pob-poe2-mcp doctor --pob-dir "{directory}"')
            return
        pob_dir = resolve_engine_dir(getattr(args, "pob_dir", None))
        timeout = getattr(args, "timeout", 60)
        if args.command == "doctor":
            doctor(pob_dir, timeout)
            return
        serve(pob_dir=pob_dir, timeout=timeout)
    except (EngineError, OSError, subprocess.SubprocessError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        raise SystemExit(1) from None
