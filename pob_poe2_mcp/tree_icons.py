"""Оригинальные иконки DDS BC1 в переносимый PNG RGBA; игровых правил здесь нет."""

import base64
from functools import lru_cache
import struct
import zlib

from .texture_data import Textures, DDS


def rgb565(value):
    r, g, b = value >> 11, (value >> 5) & 63, value & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2, 255)


def palette(first, second):
    a, b = rgb565(first), rgb565(second)
    if first > second:
        return [a, b, tuple((2 * a[i] + b[i]) // 3 for i in range(3)) + (255,),
                tuple((a[i] + 2 * b[i]) // 3 for i in range(3)) + (255,)]
    return [a, b, tuple((a[i] + b[i]) // 2 for i in range(3)) + (255,), (0, 0, 0, 0)]


def decode_bc1(mip):
    pixels = bytearray(mip.width * mip.height * 4)
    offset = 0
    for top in range(0, mip.height, 4):
        for left in range(0, mip.width, 4):
            first, second, indices = struct.unpack_from('<HHI', mip.data, offset)
            colors = palette(first, second)
            offset += 8
            for index in range(16):
                x, y = left + index % 4, top + index // 4
                if x < mip.width and y < mip.height:
                    start = (y * mip.width + x) * 4
                    pixels[start:start + 4] = bytes(colors[(indices >> (index * 2)) & 3])
    return bytes(pixels)


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def png_rgba(width, height, pixels):
    rows = b''.join(b'\0' + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))
    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


def crop(mip, pixels, uv):
    left, top = round(uv[0] * mip.width), round(uv[1] * mip.height)
    right, bottom = round(uv[2] * mip.width), round(uv[3] * mip.height)
    if not 0 <= left < right <= mip.width or not 0 <= top < bottom <= mip.height:
        raise ValueError('Некорректная область иконки PoB')
    data = b''.join(pixels[(y * mip.width + left) * 4:(y * mip.width + right) * 4] for y in range(top, bottom))
    return right - left, bottom - top, data


class TreeIcons:
    def __init__(self, pob_dir):
        self.textures = Textures(pob_dir)
        self.encode = lru_cache(maxsize=2048)(self._encode)

    def _encode(self, name, index, uv):
        source = self.textures.source(name)
        if not isinstance(source, DDS) or source.format not in (71, 72):
            raise ValueError('Иконка не является исходным DDS BC1')
        mip = source.mips(index, source.selected_level(64))[0]
        width, height, pixels = crop(mip, decode_bc1(mip), uv)
        return base64.b64encode(png_rgba(width, height, pixels)).decode('ascii')

    def render(self, assets):
        result = []
        for asset in assets['icons']:
            entry = {'key': asset['key']}
            try:
                if 'error' in asset:
                    raise ValueError(asset['error'])
                entry['png'] = self.encode(asset['file'], asset['index'], tuple(asset['uv']))
            except (ValueError, OSError) as error:
                entry['error'] = str(error)
            result.append(entry)
        return {'icons': result}
