"""Ресурсы готовой сцены PassiveTreeView; команды рисования принадлежат Lua."""

import base64
import ctypes as C
from functools import lru_cache
import hashlib
import json
import sys

from .native_runtime import native_directory
from .texture_data import Textures, DDS
from .tree_icons import decode_bc1, png_rgba


def decode_bc7(mip):
    if sys.platform == 'win32':
        return decode_gpu(mip)
    name = 'libpob-textures.dylib' if sys.platform == 'darwin' else 'libpob-textures.so'
    library = C.CDLL(str(native_directory() / name))
    method = library.pob_decode_bc7
    method.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_void_p]
    method.restype = None
    result = C.create_string_buffer(mip.width * mip.height * 4)
    method(mip.data, mip.width, mip.height, result)
    return result.raw


def decode_gpu(mip):
    from .d3d11 import Renderer
    with Renderer(mip.width, mip.height) as renderer:
        renderer.context.call('OMSetBlendState', None, None, 0xffffffff)
        texture = renderer.texture('source', [mip])
        command = {'positions': [0, 0, mip.width, 0, mip.width, mip.height, 0, mip.height],
                   'uv': [0, 0, 1, 0, 1, 1, 0, 1], 'color': [1, 1, 1, 1]}
        renderer.blends['ALPHA'] = None
        renderer.draw(command, texture)
        pixels = bytearray(renderer.raster().pixels)
    pixels[0::4], pixels[2::4] = pixels[2::4], pixels[0::4]
    return bytes(pixels)


class SceneAssets:
    def __init__(self, pob_dir):
        self.textures = Textures(pob_dir)
        self.assets = {}
        self.encoded = lru_cache(maxsize=2048)(self._encode)

    def prepare(self, scene):
        commands = []
        for original in scene['commands']:
            if original.get('mask') is not None:
                raise ValueError('Маска оригинальной сцены пока не поддерживается')
            descriptor = (original['file'], original.get('index', 1))
            token = hashlib.sha256(json.dumps(descriptor).encode()).hexdigest()
            self.assets[token] = descriptor
            commands.append({'texture': token,
                'positions': [round(v, 6) for v in original['positions']],
                'uv': [round(v, 8) for v in original['uv']],
                'color': original['color'], 'blend': original['blend'], 'clamp': original['clamp']})
        return {**scene, 'commands': commands}

    def _encode(self, name, index):
        if not name:
            return png_rgba(1, 1, bytes([255, 255, 255, 255]))
        if name.endswith('.png'):
            path = (self.textures.root / name).resolve()
            if not path.is_relative_to(self.textures.root):
                raise ValueError('Ресурс находится вне каталога PoB')
            data = path.read_bytes()
            if len(data) > 3 * 1024 * 1024:
                raise ValueError('Слишком большой PNG сцены')
            return data
        source = self.textures.source(name)
        if not isinstance(source, DDS):
            raise ValueError('Неизвестная текстура сцены')
        mip = source.mips(index, source.selected_level(512))[0]
        if mip.format in (71, 72):
            pixels = decode_bc1(mip)
        elif mip.format in (98, 99):
            pixels = decode_bc7(mip)
        else:
            pixels = mip.data
            if mip.format in (87, 91):
                pixels = bytearray(pixels)
                pixels[0::4], pixels[2::4] = pixels[2::4], pixels[0::4]
        return png_rgba(mip.width, mip.height, pixels)

    def read(self, token):
        if token not in self.assets:
            raise ValueError('Текстура не принадлежит готовой сцене. Сначала pob_get_tree(includeScene=true).')
        png = self.encoded(*self.assets[token])
        return {'token': token, 'png': base64.b64encode(png).decode('ascii')}
