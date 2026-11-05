"""Выбор и явная загрузка совместимого движка без зависимостей от Flutter."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from .errors import EngineError

LOCK = json.loads((Path(__file__).parent / "data/engine-lock.json").read_text(encoding="utf-8"))
REQUIRED_FILES = (
    "src/Launch.lua", "src/TreeData/0_5/tree.json",
    "runtime/lua51.dll", "runtime/lua/dkjson.lua",
)


@dataclass(frozen=True)
class EngineLayout:
    root: Path
    scripts: Path
    runtime: Path
    kind: str

    @property
    def version(self):
        for manifest in [self.root / "manifest.xml", self.scripts / "manifest.xml"]:
            if manifest.is_file():
                version = ET.parse(manifest).find("Version")
                if version is not None:
                    return version.get("number", "unknown")
        return "unknown"


def engine_layout(directory):
    root = Path(directory).expanduser().resolve()
    if root.is_file():
        root = root.parent
    scripts = root / "src" if (root / "src/Launch.lua").is_file() else root
    runtime = root / "runtime" if (root / "runtime/lua51.dll").is_file() else root
    required = [scripts / "Launch.lua", scripts / "GameVersions.lua", scripts / "Modules/Main.lua",
                scripts / "TreeData/0_5/tree.json", runtime / "lua51.dll", runtime / "lua/dkjson.lua"]
    if not all(path.is_file() for path in required):
        return None
    return EngineLayout(root, scripts, runtime, "repository" if scripts != root else "installed")


def registry_candidates():
    if sys.platform != "win32":
        return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
        for view in [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]:
            try:
                with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ | view) as key:
                    yield from uninstall_locations(key, winreg)
            except OSError:
                continue


def uninstall_locations(key, registry):
    for index in range(registry.QueryInfoKey(key)[0]):
        try:
            with registry.OpenKey(key, registry.EnumKey(key, index)) as entry:
                name = registry.QueryValueEx(entry, "DisplayName")[0]
                if "Path of Building" in name and "PoE2" in name:
                    yield Path(registry.QueryValueEx(entry, "InstallLocation")[0].strip('"'))
        except OSError:
            continue


def installed_engine_dirs():
    candidates = list(registry_candidates())
    for variable in ["APPDATA", "LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"]:
        base = os.environ.get(variable)
        if base:
            candidates.extend(Path(base) / name for name in ["Path of Building Community (PoE2)", "Path of Building (PoE2)"])
    return list(dict.fromkeys(path.resolve() for path in candidates if engine_layout(path)))


def default_engine_dir():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    return base / "pob-poe2-mcp" / "engines" / LOCK["revision"]


def resolve_engine_dir(pob_dir=None):
    explicit = pob_dir or os.environ.get("POB_DIR")
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path.parent if path.is_file() else path
    installed = installed_engine_dirs()
    if len(installed) > 1:
        raise EngineError("MULTIPLE_INSTALLATIONS", "Найдены несколько установок PoB; выберите --pob-dir: " + "; ".join(map(str, installed)))
    return installed[0] if installed else default_engine_dir().resolve()


def validate_engine(pob_dir):
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise EngineError("UNSUPPORTED_PLATFORM", "Нужны Windows и 64-разрядный Python 3.11 или новее.")
    if not engine_layout(pob_dir):
        raise EngineError(
            "ENGINE_NOT_CONFIGURED",
            f"Движок PoB не найден в {pob_dir}. Нужна установленная версия PoE2 или репозиторий с src/ и runtime/. "
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
