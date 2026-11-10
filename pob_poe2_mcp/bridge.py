"""Обратимая установка Lua-моста в обычный PoB или его репозиторий."""

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys

from .engine import engine_layout, installed_engine_dirs, resolve_engine_dir
from .errors import EngineError
from .transport import bridge_state_dir
from .wine_paths import wine_installations, wine_path, wine_prefix

BEGIN = "-- BEGIN POB_POE2_MCP_BRIDGE"
END = "-- END POB_POE2_MCP_BRIDGE"


def remove_hook(source):
    if BEGIN not in source:
        return source
    if source.count(BEGIN) != 1 or source.count(END) != 1:
        raise EngineError("INVALID_BRIDGE_HOOK", "Несколько блоков MCP в Launch.lua; файл не изменён")
    start = source.index(BEGIN)
    stop = source.find(END, start)
    if stop == -1:
        raise EngineError("INVALID_BRIDGE_HOOK", "Незавершённый блок MCP в Launch.lua; файл не изменён")
    return source[:start].rstrip() + source[stop + len(END):]


def clean_hash(source):
    return hashlib.sha256(remove_hook(source).strip().encode("utf-8")).hexdigest()


def load_config(state):
    try:
        value = json.loads((state / "config.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def installed_bridge_dirs():
    candidates = list(wine_installations()) if sys.platform == "linux" else installed_engine_dirs()
    saved = load_config(bridge_state_dir()).get("installDir")
    candidates.extend(Path(path).expanduser() for path in [os.environ.get("POB_DIR"), saved] if isinstance(path, str) and path)
    roots = []
    for path in candidates:
        layout = engine_layout(path)
        if layout and (layout.runtime / "Path of Building-PoE2.exe").is_file():
            roots.append(layout.root)
    return list(dict.fromkeys(roots))


def _bridge_layout(pob_dir):
    candidates = installed_bridge_dirs() if not (pob_dir or os.environ.get("POB_DIR")) else []
    if len(candidates) > 1:
        raise EngineError("MULTIPLE_INSTALLATIONS", "Выберите установку PoB через --pob-dir.")
    selected = candidates[0] if candidates else resolve_engine_dir(pob_dir)
    layout = engine_layout(selected)
    if not layout:
        raise EngineError("ENGINE_NOT_CONFIGURED", "Выберите папку с приложением PoB для PoE 2.")
    if sys.platform == "linux" and not (layout.runtime / "Path of Building-PoE2.exe").is_file():
        raise EngineError("POB_WINE_REQUIRED", "Выберите папку официального Path of Building для PoE 2, запущенного через Wine.")
    return layout


def _bridge_script_path(state, layout):
    if sys.platform == "linux":
        return wine_path(state, wine_prefix(layout.root))
    return state.as_posix()


def install_bridge(pob_dir=None, state_dir=None):
    layout = _bridge_layout(pob_dir)
    launch = layout.scripts / "Launch.lua"
    source = launch.read_text(encoding="utf-8")
    state = (Path(state_dir) if state_dir else bridge_state_dir()).resolve()
    bridge_path = _bridge_script_path(state, layout)
    if "]]" in bridge_path:
        raise EngineError("INVALID_PATH", "Путь к мосту содержит ]]")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if sys.platform == "linux":
        state.chmod(0o700)
    cleaned = remove_hook(source)
    backups = state / "backups"
    backups.mkdir(exist_ok=True)
    digest = hashlib.sha256(launch.read_bytes()).hexdigest()
    backup = backups / f"Launch-{digest}.lua"
    if not backup.exists():
        shutil.copy2(launch, backup)
    shutil.copytree(Path(__file__).parent / "lua", state / "lua", dirs_exist_ok=True)
    old_config = load_config(state)
    if old_config.get("cleanSourceHash") == clean_hash(source) and old_config.get("backup"):
        backup = Path(old_config["backup"])
    config = {"token": secrets.token_hex(32), "installDir": str(layout.root),
              "backup": str(backup), "cleanSourceHash": clean_hash(source)}
    if sys.platform == "linux":
        config["hostPlatform"] = "linux"
    (state / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    hook = f'''{BEGIN}
if not POB_MCP_HEADLESS then
    local ok, message = pcall(function()
        dofile([[{bridge_path}/lua/gui_bridge.lua]])(launch, [[{bridge_path}]])
    end)
    if not ok then ConPrintf("MCP: %s", tostring(message)) end
end
{END}
'''
    launch.write_text(cleaned.rstrip() + "\n\n" + hook, encoding="utf-8", newline="\n")
    return {"engineDir": str(layout.root), "backup": str(backup), "restartRequired": True}


def uninstall_bridge(pob_dir=None, state_dir=None):
    layout = _bridge_layout(pob_dir)
    launch = layout.scripts / "Launch.lua"
    source = launch.read_text(encoding="utf-8")
    cleaned = remove_hook(source)
    if cleaned != source:
        state = Path(state_dir) if state_dir else bridge_state_dir()
        config = load_config(state)
        backup = Path(config.get("backup", ""))
        if config.get("cleanSourceHash") == clean_hash(source) and backup.is_file() and BEGIN not in backup.read_text(encoding="utf-8"):
            launch.write_bytes(backup.read_bytes())
        else:
            launch.write_text(cleaned, encoding="utf-8", newline="\n")
    return {"engineDir": str(layout.root), "removed": cleaned != source, "restartRequired": True}
