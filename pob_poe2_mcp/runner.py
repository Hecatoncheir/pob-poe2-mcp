"""Запуск Lua-сценария через имеющийся Windows runtime без установки пакетов."""

import argparse
import ctypes
import os
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pob-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.pob_dir.resolve()
    script = PACKAGE_DIR / "lua/headless_server.lua"
    runtime = root / "runtime"
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
            os.chdir(root / "src")
            # JSON-совместимое экранирование подходит для ASCII-путей в Lua.
            # Длинная строка позволяет передавать путь без исполнения shell-кода.
            path = str(script).replace("\\", "/")
            package_path = str(PACKAGE_DIR).replace("\\", "/")
            if "]]" in path or "]]" in package_path:
                raise ValueError("Недопустимый путь сценария.")
            code = '''
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath
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
''' + f"\nPOB_MCP_PACKAGE_DIR = [[{package_path}]]\ndofile([[{path}]])\n"
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
