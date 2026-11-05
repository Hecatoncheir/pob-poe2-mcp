"""Проверки PNG, полноты отчётов и соответствия изображения данным Lua."""

import base64
import json
import struct
import sys
import unittest
from unittest.mock import patch
import zlib

from pob_poe2_mcp.bitmap import Canvas, encode_png
from pob_poe2_mcp.image_text import content_rows, warning_lines
from pob_poe2_mcp.images import render_build_image, wrapped_rows
from pob_poe2_mcp.server import Server, TOOLS, validate


def sample_data():
    info = {'name': 'Проверочная сборка', 'level': 90, 'class': 'Ranger', 'ascendancy': 'Pathfinder',
            'groups': {'selected': 1, 'entries': [{'id': 1, 'label': 'Fireball'}]},
            'skills': {'selected': 1, 'entries': []}}
    report = {'snapshot': {'buildInfo': info}, 'stats': {'Life': 2258, 'TotalDPS': 591.481672, 'TailStat': 77},
              'config': {'enemyIsBoss': 'None'}, 'configPlaceholders': {'enemyLevel': 90},
              'groups': [{'id': 1, 'label': 'Fireball', 'enabled': True, 'gems': [
                  {'name': 'Fireball', 'level': 20, 'quality': 0, 'enabled': True, 'error': 'Ошибка поддержки'}]}],
              'items': [{'id': 3, 'name': 'Кольцо', 'base': 'Lazuli Ring', 'raw': 'Rarity: Unique\nПоследняя строка',
                         'unsupported': [{'line': 'Unknown modifier'}]}],
              'slots': [{'name': 'Ring 1', 'itemId': 3}], 'allocatedNodes': [1, 2], 'notes': 'Заметка автора',
              'warnings': ['Требуется интеллект'], 'pointDisplay': '1 / 123', 'sets': {}, 'activeSets': {},
              'customMods': [{'title': 'Допущение', 'text': 'Unknown custom', 'enabled': True,
                              'unparsed': [{'line': 'Unknown custom'}]}]}
    tree = {'nodes': [
        {'id': 1, 'x': 0, 'y': 0, 'allocated': True, 'type': 'ClassStart', 'name': 'Ranger'},
        {'id': 2, 'x': 500, 'y': 400, 'allocated': True, 'type': 'Notable', 'name': 'Имя узла'},
        {'id': 3, 'x': 1500, 'y': 1800, 'allocated': False, 'type': 'Normal', 'name': 'Другой узел'}],
        'edges': [[1, 2], [2, 3]]}
    scene = {'width': 320, 'height': 240, 'scale': 1, 'offsetX': 0, 'offsetY': 0, 'commands': []}
    return {'report': report, 'tree': tree, 'scene': scene, 'tooltip': {'lines': [{'text': 'Подсказка узла'}], 'path': [1, 2]}}


def decode_png(png):
    if png[:8] != b'\x89PNG\r\n\x1a\n':
        raise AssertionError('Не PNG')
    cursor, compressed, dimensions = 8, b'', None
    while cursor < len(png):
        length = struct.unpack('!I', png[cursor:cursor + 4])[0]
        kind = png[cursor + 4:cursor + 8]
        data = png[cursor + 8:cursor + 8 + length]
        crc = struct.unpack('!I', png[cursor + 8 + length:cursor + 12 + length])[0]
        if crc != zlib.crc32(kind + data):
            raise AssertionError('Повреждён CRC PNG')
        if kind == b'IHDR':
            dimensions = struct.unpack('!II', data[:8])
        if kind == b'IDAT':
            compressed += data
        cursor += length + 12
    return dimensions, zlib.decompress(compressed)


class ImageData(unittest.TestCase):
    def test_png_converts_top_down_bgra_to_rgb_with_valid_chunks(self):
        png = encode_png(2, 1, bytes([10, 20, 30, 0, 40, 50, 60, 0]))
        dimensions, pixels = decode_png(png)
        self.assertEqual(dimensions, (2, 1))
        self.assertEqual(pixels, bytes([0, 30, 20, 10, 60, 50, 40]))

    def test_reports_include_tail_values_and_all_warning_sources(self):
        data = sample_data()
        text = '\n'.join(line for line, _ in content_rows(data, 'all'))
        for value in ['TailStat: 77', 'Последняя строка', 'enemyLevel: 90', 'Unknown custom', 'Заметка автора']:
            self.assertIn(value, text)
        self.assertEqual(len(warning_lines(data['report'])), 4)
        self.assertIn('Ring 1', '\n'.join(line for line, _ in content_rows(data, 'item', 3)))

    def test_filter_and_object_ids_are_checked(self):
        data = sample_data()
        self.assertEqual(content_rows(data, 'stats', query='TailStat'), [('TailStat: 77', 'body')])
        with self.assertRaises(ValueError):
            content_rows(data, 'item', 999)

    def test_wrapping_preserves_long_words_and_cyrillic(self):
        class Measurer:
            width = 160

            def measure(self, text, *_):
                return len(text) * 10

        source = 'Привет' * 100
        rows = wrapped_rows(Measurer(), [(source, 'body')])
        self.assertEqual(''.join(text for text, _ in rows), source)

    def test_bad_image_arguments_do_not_connect_to_pob(self):
        server = Server(mode='app')
        server.handle('initialize', {})
        schema = next(tool['inputSchema'] for tool in TOOLS if tool['name'] == 'pob_render_image')
        with self.assertRaises(ValueError):
            validate({'width': 10000}, schema)
        for arguments in [{'view': 'node'}, {'view': 'item'}, {'view': 'tree', 'page': 2}, {'height': -1}]:
            result = server.handle('tools/call', {'name': 'pob_render_image', 'arguments': arguments})
            self.assertTrue(result['isError'])
            self.assertIsNone(server.api)


@unittest.skipUnless(sys.platform == 'win32', 'Рисование PNG использует Windows GDI')
class NativeImages(unittest.TestCase):
    def test_all_views_return_valid_nonempty_png(self):
        data = sample_data()
        for view in ['overview', 'tree', 'stats', 'skills', 'items', 'config', 'notes', 'warnings', 'node', 'item', 'all']:
            with self.subTest(view=view):
                png, metadata = render_build_image(data, {'view': view, 'id': 3, 'width': 800, 'height': 600})
                dimensions, pixels = decode_png(png)
                self.assertEqual(dimensions, (800, 600))
                self.assertGreater(len(set(pixels)), 20)
                self.assertEqual(metadata['warningCount'], 4)

    def test_pagination_keeps_last_stat_and_rejects_out_of_range_page(self):
        data = sample_data()
        data['report']['stats'] = {f'Показатель{i:04}': i for i in range(100)}
        _, metadata = render_build_image(data, {'view': 'stats', 'height': 480, 'width': 640})
        self.assertGreater(metadata['pages'], 1)
        _, last = render_build_image(data, {'view': 'stats', 'height': 480, 'width': 640, 'page': metadata['pages']})
        self.assertEqual(last['pages'], metadata['pages'])
        with self.assertRaises(ValueError):
            render_build_image(data, {'view': 'stats', 'page': metadata['pages'] + 100})

    def test_mcp_returns_image_block_and_small_metadata_without_mutating_revision(self):
        server = Server()
        server.handle('initialize', {})

        class API:
            revision = 12

        server.api = API()
        with patch.object(server, 'call_tool', return_value=sample_data()) as call:
            result = server.handle('tools/call', {'name': 'pob_render_image', 'arguments': {'view': 'tree'}})
        self.assertFalse(result['isError'], result)
        self.assertEqual(result['structuredContent']['revision'], 12)
        image = next(block for block in result['content'] if block['type'] == 'image')
        self.assertEqual(decode_png(base64.b64decode(image['data']))[0], (1600, 1100))
        self.assertNotIn('report', result['structuredContent']['result'])
        self.assertEqual(len(call.call_args_list), 1)
        self.assertLess(len(json.dumps(result).encode('utf-8')), 8 * 1024 * 1024)

    def test_canvas_can_be_closed_twice(self):
        canvas = Canvas(640, 480)
        canvas.text(10, 10, 'Кириллица и \U0001f30d', (255, 255, 255))
        canvas.close()
        canvas.close()


if __name__ == '__main__':
    unittest.main()
