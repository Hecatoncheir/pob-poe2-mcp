"""Исходные текстуры PoB: слои и mip-уровни DDS, PNG через системный GDI+."""

import atexit
import ctypes as C
from dataclasses import dataclass
from functools import lru_cache
import struct

from .engine import engine_layout
from .tree_assets import decompress_zstd


@dataclass
class Mip:
    width: int
    height: int
    format: int
    pitch: int
    data: bytes


def pitch_and_size(width, height, format_id):
    if format_id in (28, 29, 87, 91):
        return width * 4, width * height * 4
    block = 8 if format_id in (71, 72) else 16
    pitch = max(1, (width + 3) // 4) * block
    return pitch, pitch * max(1, (height + 3) // 4)


class DDS:
    def __init__(self, data):
        if len(data) < 148 or data[:4] != b'DDS ' or data[84:88] != b'DX10':
            raise ValueError('Ожидался DDS DX10')
        self.format, dimension, flags, self.layers, _ = struct.unpack_from('<5I', data, 128)
        if self.format not in (28, 29, 71, 72, 87, 91, 98, 99) or dimension != 3 or flags & 4:
            raise ValueError('Неподдерживаемая текстура DDS')
        height, width = struct.unpack_from('<II', data, 12)
        levels = max(1, struct.unpack_from('<I', data, 28)[0])
        if not 1 <= levels <= 16 or not 1 <= width <= 8192 or not 1 <= height <= 8192 or not 1 <= self.layers <= 4096:
            raise ValueError('Недопустимые размеры текстуры DDS')
        self.levels, self.stride = [], 0
        for level in range(levels):
            w, h = max(1, width >> level), max(1, height >> level)
            pitch, size = pitch_and_size(w, h, self.format)
            self.levels.append((self.stride, w, h, pitch, size))
            self.stride += size
        if 148 + self.stride * self.layers > len(data):
            raise ValueError('Данные текстуры DDS обрезаны')
        self.data = data

    def selected_level(self, target):
        compressed = self.format in (71, 72, 98, 99)
        candidates = [i for i, (_, w, h, _, _) in enumerate(self.levels)
                      if min(w, h) >= target and (not compressed or w % 4 == 0 and h % 4 == 0)]
        return max(candidates, default=0)

    def mips(self, index, first):
        if not 1 <= index <= self.layers:
            raise ValueError('Слой DDS вне допустимого диапазона')
        result = []
        for offset, width, height, pitch, size in self.levels[first:]:
            start = 148 + (index - 1) * self.stride + offset
            result.append(Mip(width, height, self.format, pitch, self.data[start:start + size]))
        return result


class Startup(C.Structure):
    _fields_ = [('version', C.c_uint32), ('callback', C.c_void_p), ('thread', C.c_int32), ('codecs', C.c_int32)]


class Rect(C.Structure):
    _fields_ = [(name, C.c_int32) for name in ['x', 'y', 'width', 'height']]


class BitmapData(C.Structure):
    _fields_ = [('width', C.c_uint32), ('height', C.c_uint32), ('stride', C.c_int32),
                ('format', C.c_int32), ('pixels', C.c_void_p), ('reserved', C.c_size_t)]


def gdip_ok(status):
    if status:
        raise ValueError(f'Ошибка декодирования PNG в GDI+: {status}')


@lru_cache(maxsize=1)
def gdiplus():
    dll = C.WinDLL('gdiplus')
    signatures = {'GdiplusStartup': [C.c_void_p, C.c_void_p, C.c_void_p],
                  'GdipCreateBitmapFromFile': [C.c_wchar_p, C.c_void_p],
                  'GdipGetImageWidth': [C.c_void_p, C.c_void_p], 'GdipGetImageHeight': [C.c_void_p, C.c_void_p],
                  'GdipBitmapLockBits': [C.c_void_p, C.c_void_p, C.c_uint32, C.c_int32, C.c_void_p],
                  'GdipBitmapUnlockBits': [C.c_void_p, C.c_void_p], 'GdipDisposeImage': [C.c_void_p]}
    for name, args in signatures.items():
        method = getattr(dll, name)
        method.argtypes, method.restype = args, C.c_int32
    dll.GdiplusShutdown.argtypes = [C.c_size_t]
    token = C.c_size_t()
    gdip_ok(dll.GdiplusStartup(C.byref(token), C.byref(Startup(1)), None))
    atexit.register(dll.GdiplusShutdown, token)
    return dll


def png_mip(path):
    dll, image = gdiplus(), C.c_void_p()
    gdip_ok(dll.GdipCreateBitmapFromFile(str(path), C.byref(image)))
    try:
        width, height = C.c_uint32(), C.c_uint32()
        gdip_ok(dll.GdipGetImageWidth(image, C.byref(width)))
        gdip_ok(dll.GdipGetImageHeight(image, C.byref(height)))
        rect, bits = Rect(0, 0, width.value, height.value), BitmapData()
        gdip_ok(dll.GdipBitmapLockBits(image, C.byref(rect), 1, 0x26200A, C.byref(bits)))
        try:
            data = b''.join(C.string_at(bits.pixels + row * bits.stride, width.value * 4) for row in range(height.value))
        finally:
            dll.GdipBitmapUnlockBits(image, C.byref(bits))
        return Mip(width.value, height.value, 87, width.value * 4, data)
    finally:
        dll.GdipDisposeImage(image)


def target_size(command):
    positions, uv = command['positions'], command['uv']
    width = max(positions[::2]) - min(positions[::2])
    height = max(positions[1::2]) - min(positions[1::2])
    span_u = max(uv[::2]) - min(uv[::2])
    span_v = max(uv[1::2]) - min(uv[1::2])
    return max(width / max(span_u, 0.001), height / max(span_v, 0.001), 1)


class Textures:
    def __init__(self, pob_dir):
        self.layout = engine_layout(pob_dir) if pob_dir else None
        if pob_dir and self.layout is None:
            raise ValueError('Каталог ресурсов PoB не найден')
        self.root = self.layout.scripts.resolve() if self.layout else None
        self.sources = {}

    def source(self, name):
        if self.root is None:
            raise ValueError('Для текстур дерева нужен каталог установленного PoB')
        if name not in self.sources:
            path = (self.root / name).resolve()
            if not path.is_relative_to(self.root):
                raise ValueError('Текстура находится вне каталога PoB')
            if name.endswith('.dds.zst'):
                data = decompress_zstd(path.read_bytes(), self.layout.runtime / 'zstd.dll')
                self.sources[name] = DDS(data)
            elif name.endswith('.png'):
                self.sources[name] = png_mip(path)
            else:
                raise ValueError('Неподдерживаемый формат текстуры: ' + name)
        return self.sources[name]

    def get(self, command):
        name = command['file']
        if not name:
            return ('white',), [Mip(1, 1, 87, 4, bytes([255, 255, 255, 255]))]
        source = self.source(name)
        if isinstance(source, Mip):
            return (name,), [source]
        first = source.selected_level(target_size(command))
        index = command.get('index', 1)
        return (name, index, first), source.mips(index, first)
