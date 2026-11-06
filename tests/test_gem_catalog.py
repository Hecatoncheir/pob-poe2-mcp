"""Иконки GGG, проверка кеша и совместимость через настоящий Lua."""

import base64
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir
from pob_poe2_mcp.gem_remote_images import RemoteGemImages
from pob_poe2_mcp.server import Server

ENGINE = resolve_engine_dir()
FIREBALL = 'Metadata/Items/Gems/SkillGemFireball'
CONTROLLED = 'Metadata/Items/Gems/SkillGemControlledDestructionSupport'
URL = 'https://cdn.poe2db.tw/image/Art/test.webp'


class ImageResponse(io.BytesIO):
    def geturl(self):
        return URL


class ImageCache(unittest.TestCase):
    def test_hash_check_retry_and_offline_cache(self):
        data = b'RIFF\x04\x00\x00\x00WEBPtest'
        with tempfile.TemporaryDirectory() as directory:
            images = RemoteGemImages(directory)
            digest = hashlib.sha256(data).hexdigest()
            images.entries = {'gem': {'url': URL, 'sha256': digest}}
            with patch('pob_poe2_mcp.gem_remote_images.urlopen', return_value=ImageResponse(data)) as fetch:
                self.assertEqual(images.read('gem')[0], data)
                self.assertEqual(images.read('gem')[0], data)
                self.assertEqual(fetch.call_count, 1)
            (Path(directory) / (digest + '.webp')).write_bytes(b'bad')
            with patch('pob_poe2_mcp.gem_remote_images.urlopen', return_value=ImageResponse(data)):
                self.assertEqual(images.read('gem')[0], data)
            (Path(directory) / (digest + '.webp')).write_bytes(b'bad')
            with patch('pob_poe2_mcp.gem_remote_images.urlopen', return_value=ImageResponse(b'RIFFbad!WEBPbad')):
                with self.assertRaises(ValueError):
                    images.read('gem')

    def test_arbitrary_addresses_and_unknown_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            images = RemoteGemImages(directory)
            images.entries = {'gem': {'url': 'https://localhost/private', 'sha256': '0' * 64}}
            with patch('pob_poe2_mcp.gem_remote_images.urlopen') as fetch:
                with self.assertRaises(ValueError):
                    images.read('gem')
                with self.assertRaises(ValueError):
                    images.read('unknown')
                fetch.assert_not_called()


@unittest.skipUnless(engine_layout(ENGINE), 'Нужен установленный исходный PoB')
class OriginalGems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server(pob_dir=ENGINE)
        cls.server.handle('initialize', {})
        classes = cls.server.call_tool('pob_catalog', {'kind': 'classes'})['entries']
        cls.server.call_tool('pob_create_build', {'level': 90, 'classId': classes[0]['id']})

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def call(self, name, args):
        result = self.server.handle('tools/call', {'name': name, 'arguments': args})
        self.assertFalse(result['isError'], result['content'])
        return result['structuredContent']['result']

    def test_original_images_and_support_classification(self):
        gem = self.call('pob_catalog', {'kind': 'gems', 'query': 'Controlled Destruction'})['entries'][0]
        self.assertTrue(gem['support'])
        active = self.call('pob_catalog', {'kind': 'gems', 'query': FIREBALL})['entries'][0]
        self.assertFalse(active['support'])
        before = self.server.api.revision
        icons = self.call('pob_gem_icons', {'ids': [FIREBALL, CONTROLLED]})['icons']
        self.assertEqual(base64.b64decode(icons[0]['data'])[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(base64.b64decode(icons[1]['data'])[8:12], b'WEBP')
        self.assertEqual(self.server.api.revision, before)

    def test_filter_uses_original_support_rules_without_changing_build(self):
        before = self.call('pob_export_xml', {})['xml']
        revision = self.server.api.revision
        supports = self.call('pob_gem_supports', {'gems': [{'id': FIREBALL, 'level': 5}]})
        self.assertEqual(supports['source'], 'original-lua')
        self.assertIn(CONTROLLED, supports['supportIds'])
        martial = self.call('pob_catalog', {'kind': 'gems', 'query': 'Rapid Attacks I'})['entries'][0]['id']
        self.assertNotIn(martial, supports['supportIds'])
        self.assertEqual(self.server.api.revision, revision)
        self.assertEqual(self.call('pob_export_xml', {})['xml'], before)
        rejected = self.server.handle('tools/call', {'name': 'pob_gem_supports', 'arguments': {'gems': [{'id': CONTROLLED}]}})
        self.assertTrue(rejected['isError'])
        self.assertEqual(self.call('pob_export_xml', {})['xml'], before)
