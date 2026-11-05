"""PNG и рисование через штатный Windows GDI, без сторонних пакетов."""

import ctypes
from ctypes import wintypes
from functools import lru_cache
import struct
import sys
import zlib

from .errors import EngineError


def png_chunk(kind, data):
    return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))


def encode_png(width, height, bgra):
    """Сохранить непрозрачный буфер GDI в RGB PNG без изменения размеров."""
    if len(bgra) != width * height * 4:
        raise ValueError('Размер буфера изображения не совпадает с размерами PNG')
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    stride = width * 3
    rows = b''.join(b'\0' + rgb[offset:offset + stride] for offset in range(0, len(rgb), stride))
    header = struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', header) + png_chunk(b'IDAT', zlib.compress(rows)) + png_chunk(b'IEND', b'')


class BitmapInfo(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG), ('height', wintypes.LONG),
                ('planes', wintypes.WORD), ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
                ('imageSize', wintypes.DWORD), ('xppm', wintypes.LONG), ('yppm', wintypes.LONG),
                ('used', wintypes.DWORD), ('important', wintypes.DWORD)]


def colorref(color):
    return color[0] | color[1] << 8 | color[2] << 16


@lru_cache(maxsize=1)
def libraries():
    if sys.platform != 'win32':
        raise EngineError('UNSUPPORTED_PLATFORM', 'Создание PNG требует Windows, как и runtime PoB')
    gdi, user = ctypes.WinDLL('gdi32', use_last_error=True), ctypes.WinDLL('user32', use_last_error=True)
    handle, integer, pointer = ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p
    signatures = {
        'CreateCompatibleDC': (handle, [handle]),
        'CreateDIBSection': (handle, [handle, pointer, wintypes.UINT, pointer, handle, wintypes.DWORD]),
        'SelectObject': (handle, [handle, handle]), 'DeleteObject': (integer, [handle]),
        'DeleteDC': (integer, [handle]), 'CreateSolidBrush': (handle, [wintypes.DWORD]),
        'CreatePen': (handle, [integer, integer, wintypes.DWORD]),
        'MoveToEx': (integer, [handle, integer, integer, pointer]),
        'LineTo': (integer, [handle, integer, integer]),
        'Ellipse': (integer, [handle, integer, integer, integer, integer]),
        'SetBkMode': (integer, [handle, integer]), 'SetTextColor': (wintypes.DWORD, [handle, wintypes.DWORD]),
        'TextOutW': (integer, [handle, integer, integer, ctypes.c_wchar_p, integer]),
        'GetTextExtentPoint32W': (integer, [handle, ctypes.c_wchar_p, integer, pointer]),
        'CreateFontW': (handle, [integer] * 5 + [wintypes.DWORD] * 8 + [ctypes.c_wchar_p]),
        'SaveDC': (integer, [handle]), 'RestoreDC': (integer, [handle, integer]),
        'IntersectClipRect': (integer, [handle, integer, integer, integer, integer]),
        'GdiFlush': (integer, []),
    }
    for name, (restype, argtypes) in signatures.items():
        function = getattr(gdi, name)
        function.restype, function.argtypes = restype, argtypes
    user.FillRect.restype = integer
    user.FillRect.argtypes = [handle, pointer, handle]
    blend = ctypes.WinDLL('msimg32', use_last_error=True)
    blend.AlphaBlend.restype = integer
    blend.AlphaBlend.argtypes = [handle] + [integer] * 4 + [handle] + [integer] * 4 + [wintypes.DWORD]
    return gdi, user, blend


class Canvas:
    def __init__(self, width, height):
        self.gdi, self.user, self.blend = libraries()
        self.width, self.height = width, height
        self.fonts = {}
        self.sprites = {}
        self.dc = self.gdi.CreateCompatibleDC(None)
        self.bitmap = None
        if not self.dc:
            raise EngineError('IMAGE_RENDER_FAILED', 'Windows не создал контекст рисования')
        self.bits = ctypes.c_void_p()
        info = BitmapInfo(ctypes.sizeof(BitmapInfo), width, -height, 1, 32, 0)
        self.bitmap = self.gdi.CreateDIBSection(self.dc, ctypes.byref(info), 0, ctypes.byref(self.bits), None, 0)
        if not self.dc or not self.bitmap:
            self.close()
            raise EngineError('IMAGE_RENDER_FAILED', 'Windows не создал буфер изображения')
        self.previous_bitmap = self.gdi.SelectObject(self.dc, self.bitmap)
        self.previous_font = None
        self.gdi.SetBkMode(self.dc, 1)

    def rectangle(self, x, y, width, height, color):
        brush = self.gdi.CreateSolidBrush(colorref(color))
        rect = wintypes.RECT(round(x), round(y), round(x + width), round(y + height))
        try:
            self.user.FillRect(self.dc, ctypes.byref(rect), brush)
        finally:
            self.gdi.DeleteObject(brush)

    def line(self, x1, y1, x2, y2, color, width=1):
        pen = self.gdi.CreatePen(0, width, colorref(color))
        previous = self.gdi.SelectObject(self.dc, pen)
        try:
            self.gdi.MoveToEx(self.dc, round(x1), round(y1), None)
            self.gdi.LineTo(self.dc, round(x2), round(y2))
        finally:
            self.gdi.SelectObject(self.dc, previous)
            self.gdi.DeleteObject(pen)

    def circle(self, x, y, radius, fill, outline):
        brush = self.gdi.CreateSolidBrush(colorref(fill))
        pen = self.gdi.CreatePen(0, 1, colorref(outline))
        old_brush = self.gdi.SelectObject(self.dc, brush)
        old_pen = self.gdi.SelectObject(self.dc, pen)
        try:
            self.gdi.Ellipse(self.dc, round(x - radius), round(y - radius), round(x + radius), round(y + radius))
        finally:
            self.gdi.SelectObject(self.dc, old_brush)
            self.gdi.SelectObject(self.dc, old_pen)
            self.gdi.DeleteObject(brush)
            self.gdi.DeleteObject(pen)

    def font(self, size, bold=False):
        key = size, bold
        if key not in self.fonts:
            font = self.gdi.CreateFontW(-size, 0, 0, 0, 700 if bold else 400, 0, 0, 0, 1, 0, 0, 4, 0, 'Segoe UI')
            if not font:
                raise EngineError('IMAGE_RENDER_FAILED', 'Windows не создал шрифт')
            self.fonts[key] = font
        previous = self.gdi.SelectObject(self.dc, self.fonts[key])
        if self.previous_font is None:
            self.previous_font = previous

    def text(self, x, y, text, color, size=18, bold=False):
        self.font(size, bold)
        self.gdi.SetTextColor(self.dc, colorref(color))
        length = len(text.encode('utf-16-le')) // 2
        self.gdi.TextOutW(self.dc, round(x), round(y), text, length)

    def measure(self, text, size=18, bold=False):
        self.font(size, bold)
        measured = wintypes.SIZE()
        self.gdi.GetTextExtentPoint32W(self.dc, text, len(text.encode('utf-16-le')) // 2, ctypes.byref(measured))
        return measured.cx

    def sprite(self, x, y, size, raster, opacity=255):
        key = id(raster)
        if key not in self.sprites:
            source = Canvas(raster.width, raster.height)
            ctypes.memmove(source.bits, raster.pixels, len(raster.pixels))
            self.sprites[key] = raster, source
        source = self.sprites[key][1]
        blend = (opacity << 16) | (1 << 24)
        if not self.blend.AlphaBlend(self.dc, round(x), round(y), size, size, source.dc,
                                    0, 0, raster.width, raster.height, blend):
            raise EngineError('IMAGE_RENDER_FAILED', 'Windows не смог отрисовать иконку')

    def paste(self, x, y, raster):
        if x < 0 or y < 0 or x + raster.width > self.width or y + raster.height > self.height:
            raise ValueError('Изображение не помещается на холст')
        self.gdi.GdiFlush()
        for row in range(raster.height):
            offset = ((y + row) * self.width + x) * 4
            start = row * raster.width * 4
            ctypes.memmove(self.bits.value + offset, raster.pixels[start:start + raster.width * 4], raster.width * 4)

    def clip(self, x, y, width, height):
        saved = self.gdi.SaveDC(self.dc)
        self.gdi.IntersectClipRect(self.dc, round(x), round(y), round(x + width), round(y + height))
        return saved

    def unclip(self, saved):
        self.gdi.RestoreDC(self.dc, saved)

    def png(self):
        self.gdi.GdiFlush()
        return encode_png(self.width, self.height, ctypes.string_at(self.bits, self.width * self.height * 4))

    def close(self):
        if not self.dc:
            return
        for _, source in self.sprites.values():
            source.close()
        self.sprites.clear()
        if getattr(self, 'previous_font', None):
            self.gdi.SelectObject(self.dc, self.previous_font)
        for font in self.fonts.values():
            self.gdi.DeleteObject(font)
        self.fonts.clear()
        if getattr(self, 'previous_bitmap', None):
            self.gdi.SelectObject(self.dc, self.previous_bitmap)
        if self.bitmap:
            self.gdi.DeleteObject(self.bitmap)
        if self.dc:
            self.gdi.DeleteDC(self.dc)
        self.bitmap, self.dc = None, None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
