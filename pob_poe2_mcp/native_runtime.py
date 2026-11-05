"""Поиск нативного LuaJIT; установка библиотек в систему не выполняется."""

import ctypes.util
import os
from pathlib import Path
import struct
import sys

from .errors import EngineError


def native_directory():
    explicit = os.environ.get("POB_MCP_NATIVE_DIR")
    return Path(explicit).expanduser().resolve() if explicit else Path(__file__).parent / "native"


def lua_library(runtime):
    if struct.calcsize("P") != 8:
        raise EngineError("UNSUPPORTED_PLATFORM", "Нужен 64-разрядный Python.")
    if sys.platform == "win32":
        return str(Path(runtime) / "lua51.dll")
    if sys.platform not in {"linux", "darwin"}:
        raise EngineError("UNSUPPORTED_PLATFORM", "Поддерживаются Windows, Linux и macOS.")
    explicit = os.environ.get("POB_MCP_LUA_LIBRARY")
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    filename = "libluajit-5.1.dylib" if sys.platform == "darwin" else "libluajit-5.1.so.2"
    bundled = native_directory() / filename
    if bundled.is_file():
        return str(bundled)
    system = ctypes.util.find_library("luajit-5.1")
    if system:
        return system
    raise EngineError("LUA_RUNTIME_NOT_FOUND", "Нужен нативный LuaJIT: распакуйте native-архив MCP для своей ОС либо задайте POB_MCP_LUA_LIBRARY.")


def check_native_runtime(runtime):
    library = lua_library(runtime)
    if sys.platform != "win32" and not (native_directory() / "lua-utf8.so").is_file():
        raise EngineError("LUA_UTF8_NOT_FOUND", "Не найден нативный модуль lua-utf8.so; нужен полный native-архив MCP.")
    return library
