"""Одинаковый XML, полная группа, предупреждения и независимые ошибки кандидатов."""

import hashlib
import unittest

from pob_poe2_mcp.api import BuildAPI, EngineError
from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir
from pob_poe2_mcp.gem_supports import compatible_supports, compare_supports, preview_support
from pob_poe2_mcp.server import Server

ENGINE = resolve_engine_dir()
FIREBALL = 'Metadata/Items/Gems/SkillGemFireball'
CONTROLLED = 'Metadata/Items/Gems/SkillGemControlledDestructionSupport'


class BatchValidation(unittest.TestCase):
    def test_empty_repeated_and_oversized_candidates_fail_before_export(self):
        for ids in ([], ['a', 'a'], [str(index) for index in range(9)]):
            with self.assertRaises(EngineError):
                compare_supports(None, [], 1, ids, 60)


@unittest.skipUnless(engine_layout(ENGINE), 'Нужен исходный Lua')
class SupportComparison(unittest.TestCase):
    def setUp(self):
        self.api = BuildAPI(pob_dir=ENGINE)
        self.addCleanup(self.api.close)
        classes = self.api.call('getCatalog', {'kind': 'classes'})['entries']
        witch = next(entry['id'] for entry in classes if entry['name'] == 'Witch')
        self.api.call('createBuild', {'classId': witch, 'level': 90})

    def gem(self, name):
        entries = self.api.call('getCatalog', {'kind': 'gems', 'query': name})['entries']
        return {'id': next(entry['id'] for entry in entries if entry['name'] == name)}

    def assert_unchanged(self, xml, revision):
        self.assertEqual(self.api.call('exportBuild')['xml'], xml)
        self.assertEqual(self.api.revision, revision)

    def test_multi_active_group_matches_single_preview_and_keeps_each_error(self):
        wall = self.gem('Flame Wall')
        casting = self.gem('Rapid Casting I')
        attack = self.gem('Rapid Attacks I')['id']
        gems = [wall, {'id': FIREBALL, 'quality': 10}, casting]
        group = self.api.call('addSkillGroup', {'gems': gems})['groupId']
        self.api.call('setConfig', {'values': {'flameWallAddedDamage': True}})
        xml = self.api.call('exportBuild')['xml']
        revision = self.api.revision
        info = compatible_supports(self.api, gems, 60, group, 2)
        self.assertIn(CONTROLLED, info['supportIds'])
        self.assertNotIn(attack, info['supportIds'])
        self.assertEqual(info['sockets']['supportCount'], 1)
        self.assertIsNone(info['sockets']['capacity'])
        result = compare_supports(self.api, gems, 2,
                                  [CONTROLLED, attack, casting['id'], 'unknown'], 60, group)
        self.assertEqual(result['xmlHash'], hashlib.sha256(xml.encode('utf-8')).hexdigest())
        self.assertEqual(result['baseRevision'], revision)
        first, *errors = result['entries']
        control = preview_support(self.api, gems, 2, CONTROLLED, 60, group)
        self.assertGreater(first['delta'], 0)
        for key in ('before', 'after', 'delta', 'warnings'):
            self.assertEqual(first[key], control[key])
        self.assertTrue(all(entry['error']['message'] for entry in errors))
        self.assert_unchanged(xml, revision)

    def test_item_skill_uses_slot_supports_without_changing_equipment(self):
        raw = ('Rarity: UNIQUE\nLiminal Coil\nTwisted Wand\n--------\n'
               'Grants Skill: Level 20 Coiling Bolts (implicit)\n100% increased Spell Damage')
        self.api.call('equipItem', {'slot': 'Weapon 1', 'raw': raw})
        group = next(row for row in self.api.call('getBuildReport')['groups']
                     if row.get('source') and row.get('supportScope') == 'slot')
        gems = [{'id': group['gems'][0]['skillId'], 'sourceIndex': 1}]
        xml = self.api.call('exportBuild')['xml']
        revision = self.api.revision
        info = compatible_supports(self.api, gems, 60, group['id'], 1)
        self.assertEqual(info['sockets']['scope'], 'slot')
        self.assertIsNone(info['sockets']['capacity'])
        result = compare_supports(self.api, gems, 1, [CONTROLLED], 60, group['id'])
        self.assertGreater(result['entries'][0]['delta'], 0)
        self.assert_unchanged(xml, revision)

    def test_socket_warning_is_not_a_per_skill_capacity(self):
        primary = {'id': FIREBALL}
        group = self.api.call('addSkillGroup', {'gems': [primary]})['groupId']
        ids = compatible_supports(self.api, [primary], 60, group, 1)['supportIds'][:6]
        for count in (5, 6):
            gems = [primary, *({'id': value} for value in ids[:count])]
            info = compatible_supports(self.api, gems, 60, group, 1)
            self.assertEqual(info['sockets']['supportCount'], count)
            self.assertIsNone(info['sockets']['capacity'])
            self.assertEqual(any('too many gems' in text for text in info['warnings']), count == 6)

    def test_mcp_schema_routes_comparison_and_rejects_nine_candidates(self):
        server = Server(pob_dir=ENGINE)
        server.api = self.api
        server.handle('initialize', {})
        arguments = {'gems': [{'id': FIREBALL}], 'targetIndex': 1,
                     'supportIds': [CONTROLLED, 'unknown']}
        result = server.handle('tools/call', {'name': 'pob_compare_supports',
                                            'arguments': arguments})
        self.assertFalse(result['isError'], result['content'])
        rows = result['structuredContent']['result']['entries']
        self.assertGreater(rows[0]['delta'], 0)
        self.assertIn('error', rows[1])
        rejected = server.handle('tools/call', {'name': 'pob_compare_supports',
            'arguments': {**arguments, 'supportIds': [str(index) for index in range(9)]}})
        self.assertTrue(rejected['isError'])
