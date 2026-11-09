"""Редактирование сохраняет число групп и скрытые параметры исходного PoB."""

import unittest
import xml.etree.ElementTree as ET

from pob_poe2_mcp.api import BuildAPI, EngineError
from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir
from pob_poe2_mcp.gem_supports import compatible_supports

ENGINE = resolve_engine_dir()
FIREBALL = 'Metadata/Items/Gems/SkillGemFireball'
SUPPORT = 'Metadata/Items/Gems/SkillGemControlledDestructionSupport'
COILING_BOLTS = 'CoilingBoltsPlayer'


def groups(xml):
    return ET.fromstring(xml).find('Skills/SkillSet').findall('Skill')


@unittest.skipUnless(engine_layout(ENGINE), 'Нужен исходный Lua')
class EditGroups(unittest.TestCase):
    def setUp(self):
        self.api = BuildAPI(pob_dir=ENGINE)
        self.addCleanup(self.api.close)
        classes = self.api.call('getCatalog', {'kind': 'classes'})['entries']
        self.api.call('createBuild', {'level': 90, 'classId': classes[0]['id']})
        for label in ['Первая', 'Вторая']:
            self.api.call('addSkillGroup', {'label': label, 'gems': [{'id': FIREBALL, 'level': 5}]})

    def item_skill(self):
        report = self.api.call('getBuildReport')
        return next(group for group in report['groups']
                    if group['gems'] and group['gems'][0]['skillId'] == COILING_BOLTS)

    def test_item_skill_supports_change_dps_and_round_trip_through_xml(self):
        raw = ('Rarity: UNIQUE\nLiminal Coil\nTwisted Wand\n--------\n'
               'Grants Skill: Level 20 Coiling Bolts (implicit)\n100% increased Spell Damage')
        self.api.call('equipItem', {'slot': 'Weapon 1', 'raw': raw})
        group = self.item_skill()
        group_id = group['id']
        primary = {'id': COILING_BOLTS, 'sourceIndex': 1}
        self.api.call('selectMainSkill', {'control': 'groups', 'id': group_id})
        before = self.api.call('getSnapshot')['output']['TotalDPS']
        revision = self.api.revision
        xml = self.api.call('exportBuild')['xml']
        supports = compatible_supports(self.api, [primary], 60, group_id)['supportIds']
        self.assertEqual(self.api.call('exportBuild')['xml'], xml)
        self.assertIn(SUPPORT, supports)
        incompatible = self.api.call('getCatalog', {'kind': 'gems', 'query': 'Rapid Attacks I'})['entries'][0]['id']
        self.assertNotIn(incompatible, supports)
        for draft in ([primary, {'id': incompatible}], [{'id': FIREBALL, 'sourceIndex': 1}]):
            with self.assertRaises(EngineError):
                self.api.call('updateSkillGroup', {'groupId': group_id, 'gems': draft})
        self.assertEqual(self.api.revision, revision)
        self.assertEqual(self.item_skill(), group)
        self.assertEqual(self.api.call('getSnapshot')['output']['TotalDPS'], before)

        self.api.call('updateSkillGroup', {'groupId': group_id, 'gems': [primary, {'id': SUPPORT, 'quality': 12}]})
        edited = self.item_skill()
        self.assertEqual(edited['source'], group['source'])
        self.assertEqual(edited['gems'][0], group['gems'][0])
        self.assertEqual(edited['gems'][1]['quality'], 12)
        self.assertGreater(self.api.call('getSnapshot')['output']['TotalDPS'], before)
        self.assertTrue(self.api.call('getGemTooltip', {'groupId': group_id, 'sourceIndex': 2})['lines'])
        saved = self.api.call('exportBuild')['xml']
        self.api.call('loadBuild', {'xml': saved})
        self.assertEqual(self.item_skill()['gems'], edited['gems'])
        group_id = self.item_skill()['id']
        self.api.call('updateSkillGroup', {'groupId': group_id, 'gems': [primary, {'id': SUPPORT, 'sourceIndex': 2, 'quality': 16}]})
        self.assertEqual(self.item_skill()['gems'][1]['quality'], 16)
        self.api.call('updateSkillGroup', {'groupId': group_id, 'gems': [primary]})
        self.assertEqual(self.item_skill()['gems'], group['gems'])
        self.assertAlmostEqual(self.api.call('getSnapshot')['output']['TotalDPS'], before)

    def test_updates_only_selected_group_and_preserves_original_fields(self):
        root = ET.fromstring(self.api.call('exportBuild')['xml'])
        node = root.find('Skills/SkillSet/Skill')
        node.attrib.update(slot='Helmet', includeInFullDPS='false', groupCount='3')
        node[0].attrib.update(count='3', corrupted='true', corruptLevel='1', enableGlobal1='false')
        self.api.call('loadBuild', {'xml': ET.tostring(root, encoding='unicode')})
        before = groups(self.api.call('exportBuild')['xml'])
        result = self.api.call('updateSkillGroup', {'groupId': 1, 'gems': [{'id': FIREBALL, 'sourceIndex': 1, 'level': 8}, {'id': SUPPORT, 'quality': 15}]})
        self.assertEqual(result['groupId'], 1)
        after = groups(self.api.call('exportBuild')['xml'])
        self.assertEqual(len(after), 2)
        self.assertEqual(before[0].attrib, after[0].attrib)
        for key in ['count', 'corrupted', 'corruptLevel', 'enableGlobal1']:
            self.assertEqual(before[0][0].attrib[key], after[0][0].attrib[key])
        self.assertEqual(ET.tostring(before[1]), ET.tostring(after[1]))
        report = self.api.call('getBuildReport')['groups']
        self.assertEqual(report[0]['gems'][0]['level'], 8)
        self.assertEqual(report[0]['gems'][1]['quality'], 15)
        self.assertEqual(report[0]['gems'][1]['sourceIndex'], 2)

    def test_bad_reference_rolls_back_and_removal_does_not_duplicate_group(self):
        self.api.call('updateSkillGroup', {'groupId': 1, 'gems': [{'id': FIREBALL, 'sourceIndex': 1}, {'id': SUPPORT}]})
        before = self.api.call('exportBuild')['xml']
        before_report = self.api.call('getBuildReport')
        revision = self.api.revision
        with self.assertRaises(EngineError):
            self.api.call('updateSkillGroup', {'groupId': 1, 'gems': [{'id': FIREBALL, 'sourceIndex': 2}]})
        self.assertEqual(self.api.revision, revision)
        after_report = self.api.call('getBuildReport')
        self.assertEqual(after_report['groups'], before_report['groups'])
        self.assertEqual(after_report['stats'], before_report['stats'])
        self.assertEqual(len(groups(self.api.call('exportBuild')['xml'])), len(groups(before)))
        self.api.call('updateSkillGroup', {'groupId': 1, 'gems': [{'id': FIREBALL, 'sourceIndex': 1, 'level': 5}]})
        report = self.api.call('getBuildReport')
        self.assertEqual(len(report['groups']), 2)
        self.assertEqual(len(report['groups'][0]['gems']), 1)

    def test_delete_updates_main_selection_and_removes_last_group(self):
        self.api.call('selectMainSkill', {'control': 'groups', 'id': 2})
        self.api.call('deleteSkillGroup', {'groupId': 1})
        report = self.api.call('getBuildReport')
        self.assertEqual(len(report['groups']), 1)
        self.assertEqual(report['groups'][0]['customLabel'], 'Вторая')
        self.assertEqual(report['snapshot']['buildInfo']['groups']['selected'], 1)
        self.api.call('deleteSkillGroup', {'groupId': 1})
        self.assertEqual(self.api.call('getBuildReport')['groups'], [])

    def test_delete_selected_last_group_and_reject_bad_id(self):
        self.api.call('selectMainSkill', {'control': 'groups', 'id': 2})
        self.api.call('deleteSkillGroup', {'groupId': 2})
        before = self.api.call('getBuildReport')
        self.assertEqual(before['snapshot']['buildInfo']['groups']['selected'], 1)
        revision = self.api.revision
        with self.assertRaises(EngineError):
            self.api.call('deleteSkillGroup', {'groupId': 99})
        self.assertEqual(self.api.revision, revision)
        self.assertEqual(self.api.call('getBuildReport')['groups'], before['groups'])
