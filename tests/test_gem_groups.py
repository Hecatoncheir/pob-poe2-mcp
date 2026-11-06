"""Редактирование сохраняет число групп и скрытые параметры исходного PoB."""

import unittest
import xml.etree.ElementTree as ET

from pob_poe2_mcp.api import BuildAPI, EngineError
from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir

ENGINE = resolve_engine_dir()
FIREBALL = 'Metadata/Items/Gems/SkillGemFireball'
SUPPORT = 'Metadata/Items/Gems/SkillGemControlledDestructionSupport'


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
