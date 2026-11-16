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

    def test_preview_measures_one_support_in_full_draft_without_mutation(self):
        classes = self.call('pob_catalog', {'kind': 'classes'})['entries']
        witch = next(entry['id'] for entry in classes if entry['name'] == 'Witch')
        self.call('pob_create_build', {'level': 90, 'classId': witch})
        self.call('pob_add_skill_group', {'gems': [{'id': FIREBALL}], 'label': 'Основная группа'})
        fireball = {'id': FIREBALL, 'quality': 10}
        wall = self._gem('Flame Wall')
        casting = self._gem('Rapid Casting I')
        group = self.call('pob_add_skill_group', {'gems': [fireball, wall, casting]})
        self.call('pob_set_config', {'values': {
            'enemyLevel': 67, 'enemyIsBoss': 'None', 'flameWallAddedDamage': True,
        }})
        xml = self.call('pob_export_xml', {})['xml']
        revision = self.server.api.revision
        gems = [{**wall, 'sourceIndex': 2}, {**fireball, 'sourceIndex': 1},
                {**casting, 'sourceIndex': 3}]
        args = {'groupId': group['groupId'], 'gems': gems, 'targetIndex': 2, 'supportId': CONTROLLED}
        measured = self.call('pob_preview_support', args)
        self.assertEqual(measured['source'], 'original-lua')
        self.assertGreater(measured['before'], 0)
        self.assertGreater(measured['delta'], 0)
        self.assertAlmostEqual(measured['delta'], measured['after'] - measured['before'])

        control = self.call('pob_preview_support', {**args, 'gems': [
            {**gems[0], 'enabled': False}, *gems[1:],
        ]})
        self.assertGreater(measured['before'], control['before'])
        self.assertGreater(measured['delta'], control['delta'])
        rejected = self.server.handle('tools/call', {
            'name': 'pob_preview_support',
            'arguments': {**args, 'supportId': self._gem('Rapid Attacks I')['id']},
        })
        self.assertTrue(rejected['isError'])
        self.assertEqual(self.server.api.revision, revision)
        self.assertEqual(self.call('pob_export_xml', {})['xml'], xml)
        self.call('pob_select_main_skill', {'control': 'groups', 'id': group['groupId']})
        reference = self.call('pob_check_build', {})['report']
        self.assertAlmostEqual(measured['before'], reference['stats']['TotalDPS'])

    def _gem(self, name):
        rows = self.call('pob_catalog', {'kind': 'gems', 'query': name})['entries']
        return {'id': next(gem['id'] for gem in rows if gem['name'] == name)}
