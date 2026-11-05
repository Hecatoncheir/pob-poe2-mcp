"""Выбор и явная загрузка совместимого движка без зависимостей от Flutter."""

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from .errors import EngineError

LOCK = json.loads((Path(__file__).parent / "data/engine-lock.json").read_text(encoding="utf-8"))
REQUIRED_FILES = (
    "src/HeadlessWrapper.lua", "src/Launch.lua", "src/TreeData/0_5/tree.json",
    "runtime/lua51.dll", "runtime/lua/dkjson.lua",
)


def default_engine_dir():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    return base / "pob-poe2-mcp" / "engines" / LOCK["revision"]


def resolve_engine_dir(pob_dir=None):
    return Path(pob_dir or os.environ.get("POB_DIR") or default_engine_dir()).expanduser().resolve()


def validate_engine(pob_dir):
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise EngineError("UNSUPPORTED_PLATFORM", "Нужны Windows и 64-разрядный Python 3.11 или новее.")
    missing = [name for name in REQUIRED_FILES if not (pob_dir / name).is_file()]
    if missing:
        raise EngineError(
            "ENGINE_NOT_CONFIGURED",
            f"Движок PoB не найден в {pob_dir}; отсутствуют: {', '.join(missing)}. "
            "Выполните pob-poe2-mcp setup или укажите --pob-dir / POB_DIR.",
        )
    return pob_dir


def run_git(directory, *args):
    subprocess.run(
        ["git", "-C", str(directory), *args], check=True,
        stdout=sys.stderr, stderr=sys.stderr,
    )


def setup_engine(destination=None):
    """Загрузить закреплённую ревизию в новый каталог, не меняя существующий."""
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise EngineError("UNSUPPORTED_PLATFORM", "Готовый движок поддерживает Windows x64.")
    target = Path(destination).expanduser().resolve() if destination else default_engine_dir().resolve()
    if target.exists():
        raise EngineError("DESTINATION_EXISTS", f"Каталог уже существует: {target}. Укажите новый --destination.")
    if not shutil.which("git"):
        raise EngineError("GIT_NOT_FOUND", "Для setup нужен Git в PATH: https://git-scm.com/downloads")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pob-mcp-", dir=target.parent) as temporary:
        checkout = Path(temporary) / "checkout"
        checkout.mkdir()
        run_git(checkout, "init", "--quiet")
        run_git(checkout, "remote", "add", "origin", LOCK["repository"])
        run_git(checkout, "sparse-checkout", "init", "--cone")
        run_git(checkout, "sparse-checkout", "set", "src", "runtime")
        run_git(checkout, "fetch", "--depth=1", "--filter=blob:none", "origin", LOCK["revision"])
        run_git(checkout, "checkout", "--detach", "FETCH_HEAD")
        validate_engine(checkout)
        checkout.rename(target)
    return target
