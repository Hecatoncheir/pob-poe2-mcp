"""Запуск Lua-сценария через имеющийся Windows runtime без установки пакетов."""

import argparse
import ctypes
import os
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pob-dir", type=Path, required=True)
    parser.add_argument("--script", type=Path, default=PACKAGE_DIR / "lua/headless_server.lua")
    args = parser.parse_args()
    root = args.pob_dir.resolve()
    script = args.script.resolve()
    scripts = root / "src" if (root / "src/Launch.lua").is_file() else root
    runtime = root / "runtime" if (root / "runtime/lua51.dll").is_file() else root
    if os.name != "nt":
        parser.error("Этот адаптер предназначен для Windows runtime проекта.")
    with os.add_dll_directory(str(runtime)):
        lua = ctypes.CDLL(str(runtime / "lua51.dll"))
        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lua.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
        lua.lua_tolstring.restype = ctypes.c_char_p
        lua.lua_close.argtypes = [ctypes.c_void_p]
        handle = lua.luaL_newstate()
        if not handle:
            raise RuntimeError("Не удалось создать Lua-состояние.")
        try:
            lua.luaL_openlibs(handle)
            os.chdir(scripts)
            # JSON-совместимое экранирование подходит для ASCII-путей в Lua.
            # Длинная строка позволяет передавать путь без исполнения shell-кода.
            path = str(script).replace("\\", "/")
            package_path = str(PACKAGE_DIR).replace("\\", "/")
            if "]]" in path or "]]" in package_path:
                raise ValueError("Недопустимый путь сценария.")
            runtime_path = str(runtime).replace("\\", "/")
            if "]]" in runtime_path:
                raise ValueError("Недопустимый путь runtime.")
            code = f'''POB_MCP_PACKAGE_DIR = [[{package_path}]]
POB_MCP_RUNTIME_DIR = [[{runtime_path}]]
POB_MCP_HEADLESS = true
''' + '''
package.path = POB_MCP_RUNTIME_DIR .. "/lua/?.lua;" .. POB_MCP_RUNTIME_DIR .. "/lua/?/init.lua;" .. package.path
package.cpath = POB_MCP_RUNTIME_DIR .. "/?.dll;" .. package.cpath
arg = {}
local originalLoadfile = loadfile
function loadfile(path)
    local file, err = io.open(path, "rb")
    if not file then return nil, err end
    local source = file:read("*a")
    file:close()
    if source:sub(1, 1) == "#" then
        source = source:gsub("^[^\\n]*", "", 1)
        return loadstring(source, "@" .. path)
    end
    return originalLoadfile(path)
end
function dofile(path)
    local chunk, err = loadfile(path)
    if not chunk then error(err) end
    return chunk()
end
''' + f"\ndofile([[{path}]])\n"
            status = lua.luaL_loadstring(handle, code.encode("utf-8"))
            if status == 0:
                status = lua.lua_pcall(handle, 0, 0, 0)
            if status:
                message = lua.lua_tolstring(handle, -1, None)
                raise RuntimeError(message.decode("utf-8", errors="replace") if message else "Ошибка Lua")
        finally:
            lua.lua_close(handle)


if __name__ == "__main__":
    main()
