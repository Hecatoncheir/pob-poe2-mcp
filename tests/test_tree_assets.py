"""Проверки исходных DDS-иконок, прозрачности и скрытия служебных связей."""

import struct
import sys
import unittest
from unittest.mock import MagicMock, Mock, call, patch

from pob_poe2_mcp.bitmap import Canvas
from pob_poe2_mcp.image_tree import visible_connections
from pob_poe2_mcp.server import Server
from pob_poe2_mcp.tree_assets import Raster
from pob_poe2_mcp.texture_data import DDS
from pob_poe2_mcp.d3d11 import Renderer
from test_images import decode_png, sample_data


def solid_block(color):
    return struct.pack('<HHI', color, 0, 0)


def texture_array():
    header = bytearray(148)
    header[:4], header[84:88] = b'DDS ', b'DX10'
    struct.pack_into('<I', header, 4, 124)
    struct.pack_into('<II', header, 12, 4, 4)
    struct.pack_into('<I', header, 28, 2)
    struct.pack_into('<5I', header, 128, 71, 3, 0, 2, 0)
    return bytes(header) + solid_block(0xf800) * 2 + solid_block(0x001f) * 2


class TreeResources(unittest.TestCase):
    def test_dds_layers_and_mips_select_the_requested_icon(self):
        array = DDS(texture_array())
        self.assertEqual(array.mips(1, 0)[0].data, solid_block(0xf800))
        smaller = array.mips(2, 1)[0]
        self.assertEqual((smaller.width, smaller.height), (2, 2))
        self.assertEqual(smaller.data, solid_block(0x001f))
        self.assertEqual(array.selected_level(2), 0)
        with self.assertRaises(ValueError):
            array.mips(3, 0)
        with self.assertRaises(ValueError):
            DDS(texture_array()[:-1])

    @unittest.skipUnless(sys.platform == 'win32', 'Нужен Windows Direct3D 11')
    def test_native_bc1_and_transparency(self):
        command = {'positions': [0, 0, 8, 0, 8, 8, 0, 8], 'uv': [0, 0, 1, 0, 1, 1, 0, 1], 'color': [1, 1, 1, 1]}
        with Renderer(8, 8) as renderer:
            texture = renderer.texture('blue', DDS(texture_array()).mips(2, 0))
            renderer.draw(command, texture)
            before = renderer.raster().pixels
            self.assertEqual(before[:4], bytes([255, 0, 0, 255]))
            transparent = bytearray(texture_array())
            transparent[148:156] = struct.pack('<HHI', 0, 0xffff, 0xffffffff)
            texture = renderer.texture('transparent', DDS(bytes(transparent)).mips(1, 0))
            renderer.draw(command, texture)
            self.assertEqual(renderer.raster().pixels, before)

    def test_only_links_between_class_and_ascendancy_are_hidden(self):
        nodes = [{'id': 1, 'type': 'ClassStart'}, {'id': 2, 'type': 'AscendClassStart'},
                 {'id': 3, 'type': 'Normal'}, {'id': 4, 'type': 'AscendClassStart'}]
        edges = [[1, 2], [3, 2], [1, 3], [4, 1]]
        visible = visible_connections({'nodes': nodes, 'edges': edges})
        self.assertEqual([(a['id'], b['id']) for a, b in visible], [(3, 2), (1, 3)])

    def test_app_tree_uses_readonly_export_and_isolated_lua_session(self):
        original = sample_data()['report']
        server = Server(mode='app')
        server.api = Mock(pob_dir='PoB', timeout=60, closed=False)
        server.api.call.side_effect = [original, {'xml': '<PathOfBuilding2/>'}]
        engine = MagicMock()
        engine.__enter__.return_value = engine
        engine.call.side_effect = [None, sample_data()]
        with patch('pob_poe2_mcp.server.BuildAPI', return_value=engine) as factory:
            data = server.execute_tool('pob_render_image', {'view': 'tree'})
        self.assertIs(data['report'], original)
        self.assertEqual(server.api.call.call_args_list, [call('getBuildReport'), call('exportBuild')])
        factory.assert_called_once_with(pob_dir='PoB', timeout=60)
        self.assertEqual(engine.call.call_args_list,
                         [call('loadBuild', {'xml': '<PathOfBuilding2/>'}), call('getBuildImageData', {'view': 'tree'})])

    def test_app_stats_do_not_start_an_extra_engine(self):
        server = Server(mode='app')
        server.api = Mock(closed=False)
        server.api.call.return_value = sample_data()['report']
        with patch('pob_poe2_mcp.server.BuildAPI', side_effect=AssertionError('Лишний процесс')):
            server.execute_tool('pob_render_image', {'view': 'stats'})
        server.api.call.assert_called_once_with('getBuildReport')

    @unittest.skipUnless(sys.platform == 'win32', 'Нужен Windows GDI')
    def test_sprite_transparency_preserves_background(self):
        with Canvas(8, 8) as canvas:
            canvas.rectangle(0, 0, 8, 8, (20, 30, 40))
            canvas.sprite(0, 0, 4, Raster(1, 1, bytes([0, 0, 255, 255])))
            canvas.sprite(4, 0, 4, Raster(1, 1, bytes(4)))
            _, rows = decode_png(canvas.png())
        self.assertEqual(rows[1:4], bytes([255, 0, 0]))
        self.assertEqual(rows[13:16], bytes([20, 30, 40]))


if __name__ == '__main__':
    unittest.main()
