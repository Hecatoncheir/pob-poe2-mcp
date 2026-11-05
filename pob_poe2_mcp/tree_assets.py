"""Общие данные изображений и чтение Zstandard из runtime PoB."""

import ctypes
import ctypes.util
import sys
from dataclasses import dataclass
from functools import lru_cache
from .native_runtime import native_directory


def zstd_path(runtime):
    if sys.platform == 'win32':
        return runtime / 'zstd.dll'
    name = 'libzstd.dylib' if sys.platform == 'darwin' else 'libzstd.so'
    bundled = native_directory() / name
    if bundled.is_file():
        return bundled
    system = ctypes.util.find_library('zstd')
    if system:
        return system
    raise ValueError('Для иконок нужен native-архив MCP с библиотекой Zstandard')


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    pixels: bytes


@lru_cache(maxsize=4)
def zstd_library(dll_path):
    dll = ctypes.CDLL(str(dll_path))
    dll.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    dll.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
    dll.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    dll.ZSTD_decompress.restype = ctypes.c_size_t
    return dll


def decompress_zstd(source, dll_path):
    dll = zstd_library(dll_path)
    size = dll.ZSTD_getFrameContentSize(source, len(source))
    if not 0 < size <= 512 * 1024 * 1024:
        raise ValueError('Неизвестный или слишком большой размер ресурса Zstandard')
    buffer = ctypes.create_string_buffer(size)
    written = dll.ZSTD_decompress(buffer, size, source, len(source))
    if written != size:
        raise ValueError('Не удалось распаковать ресурс Zstandard')
    return buffer.raw
