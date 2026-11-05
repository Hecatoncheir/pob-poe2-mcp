"""Запуск исходного Lua в нативном runtime Windows, Linux или macOS."""

import argparse
import ctypes
from contextlib import nullcontext
import sys
import os
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR.parent))
from pob_poe2_mcp.native_runtime import check_native_runtime, native_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pob-dir", type=Path, required=True)
    parser.add_argument("--script", type=Path, default=PACKAGE_DIR / "lua/headless_server.lua")
    args = parser.parse_args()
    root = args.pob_dir.resolve()
    script = args.script.resolve()
    scripts = root / "src" if (root / "src/Launch.lua").is_file() else root
    runtime = root / "runtime" if (root / "runtime/lua/dkjson.lua").is_file() else root
    library = check_native_runtime(runtime)
    context = os.add_dll_directory(str(runtime)) if os.name == "nt" else nullcontext()
    with context:
        lua = ctypes.CDLL(library, mode=getattr(ctypes, "RTLD_GLOBAL", 0))
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
            native_path = str(native_directory()).replace("\\", "/")
            if "]]" in native_path:
                raise ValueError("Недопустимый путь нативного runtime.")
            extension = "dll" if os.name == "nt" else "so"
            code = f'''POB_MCP_NATIVE_DIR = [[{native_path}]]
POB_MCP_NATIVE_EXTENSION = "{extension}"
POB_MCP_PACKAGE_DIR = [[{package_path}]]
POB_MCP_RUNTIME_DIR = [[{runtime_path}]]
POB_MCP_HEADLESS = true
''' + '''
package.path = POB_MCP_RUNTIME_DIR .. "/lua/?.lua;" .. POB_MCP_RUNTIME_DIR .. "/lua/?/init.lua;" .. package.path
package.cpath = POB_MCP_NATIVE_DIR .. "/?." .. POB_MCP_NATIVE_EXTENSION .. ";" .. POB_MCP_RUNTIME_DIR .. "/?." .. POB_MCP_NATIVE_EXTENSION .. ";" .. package.cpath
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
