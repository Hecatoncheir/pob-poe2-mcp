"""Иконки читаются из Lua и исходного PoB, прозрачность сохраняется без GDI."""

import base64
import struct
import unittest
import zlib

from pob_poe2_mcp.api import BuildAPI
from pob_poe2_mcp.server import Server
from pob_poe2_mcp.texture_data import Mip, Textures
from pob_poe2_mcp.tree_icons import decode_bc1, png_rgba
from test_integration import HAS_ENGINE, ENGINE


class IconCodec(unittest.TestCase):
    def test_bc1_colors_and_transparency(self):
        red = Mip(4, 4, 71, 8, struct.pack('<HHI', 0xf800, 0, 0))
        self.assertEqual(decode_bc1(red), bytes([255, 0, 0, 255]) * 16)
        clear = Mip(4, 4, 71, 8, struct.pack('<HHI', 0, 0xffff, 0xffffffff))
        self.assertEqual(decode_bc1(clear), bytes(64))
        png = png_rgba(4, 4, decode_bc1(clear))
        self.assertEqual(png[25], 6)
        size = struct.unpack_from('>I', png, 33)[0]
        self.assertEqual(zlib.decompress(png[41:41 + size]), bytes(68))

    @unittest.skipUnless(HAS_ENGINE, 'Нужен исходный PoB')
    def test_texture_path_cannot_escape_pob(self):
        with self.assertRaises(ValueError):
            Textures(ENGINE).source('../../outside.dds.zst')

    @unittest.skipUnless(HAS_ENGINE, 'Нужен настоящий Lua')
    def test_all_original_node_icons_and_unknown_key(self):
        server = Server(pob_dir=ENGINE)
        self.addCleanup(server.close)
        server.initialized = True
        server.execute_tool('pob_create_build', {'level': 90})
        tree = server.execute_tool('pob_get_tree', {})
        keys = sorted({node['icon'] for node in tree['nodes'] if node.get('icon')})
        revision = server.api.revision
        for start in range(0, len(keys), 32):
            response = server.handle('tools/call', {'name': 'pob_tree_icons', 'arguments': {'icons': keys[start:start + 32]}})
            self.assertFalse(response['isError'], response)
            for icon in response['structuredContent']['result']['icons']:
                self.assertNotIn('error', icon, icon)
                self.assertTrue(base64.b64decode(icon['png']).startswith(b'\x89PNG'))
        unknown = server.execute_tool('pob_tree_icons', {'icons': ['../../outside']})
        self.assertIn('error', unknown['icons'][0])
        self.assertEqual(server.api.revision, revision)
