"""Описание камней формирует оригинальный PoB без изменения сборки."""

import unittest

from pob_poe2_mcp.api import BuildAPI, EngineError
from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir

ENGINE = resolve_engine_dir()
FIREBALL = 'Metadata/Items/Gems/SkillGemFireball'
CONTROLLED = 'Metadata/Items/Gems/SkillGemControlledDestructionSupport'


@unittest.skipUnless(engine_layout(ENGINE), 'Нужен исходный Lua')
class GemTooltip(unittest.TestCase):
    def setUp(self):
        self.api = BuildAPI(pob_dir=ENGINE)
        self.addCleanup(self.api.close)
        self.api.call('createBuild', {'level': 90})

    def text(self, params):
        result = self.api.call('getGemTooltip', params)
        self.assertEqual(result['source'], 'original-lua')
        self.assertTrue(result['lines'])
        self.assertFalse(result['lines'][0].get('separator'))
        self.assertFalse(result['lines'][-1].get('separator'))
        return '\n'.join(line.get('text', '') for line in result['lines'])

    def test_catalogue_level_quality_and_support_are_read_only(self):
        before = self.api.call('exportBuild')['xml']
        stats = self.api.call('getBuildReport')['stats']
        revision = self.api.revision
        active = self.text({'id': FIREBALL, 'level': 5, 'quality': 20})
        self.assertIn('Fireball', active)
        self.assertIn('Level:', active)
        self.assertIn('Quality:', active)
        self.assertIn('20%', active)
        self.assertIn('fire', active.lower())
        self.assertNotEqual(active, self.text({'id': FIREBALL, 'level': 1, 'quality': 0}))
        self.assertIn('Controlled Destruction', self.text({'id': CONTROLLED}))
        self.assertEqual(self.api.revision, revision)
        self.assertEqual(self.api.call('exportBuild')['xml'], before)
        self.assertEqual(self.api.call('getBuildReport')['stats'], stats)

    def test_installed_gem_uses_real_level_and_quality(self):
        self.api.call('addSkillGroup', {'gems': [{'id': FIREBALL, 'level': 5, 'quality': 20}, {'id': CONTROLLED}]})
        before = self.api.call('exportBuild')['xml']
        revision = self.api.revision
        text = self.text({'groupId': 1, 'sourceIndex': 1})
        self.assertIn('Fireball', text)
        self.assertIn('20%', text)
        self.assertIn('Controlled Destruction', self.text({'groupId': 1, 'sourceIndex': 2}))
        self.assertEqual(self.api.revision, revision)
        self.assertEqual(self.api.call('exportBuild')['xml'], before)

    def test_invalid_reference_does_not_change_build(self):
        before = self.api.call('exportBuild')['xml']
        revision = self.api.revision
        for params in [{}, {'id': 'unknown'}, {'groupId': 99, 'sourceIndex': 1}, {'groupId': 1}, {'id': FIREBALL, 'groupId': 1, 'sourceIndex': 1}]:
            with self.assertRaises(EngineError):
                self.api.call('getGemTooltip', params)
        self.assertEqual(self.api.revision, revision)
        self.assertEqual(self.api.call('exportBuild')['xml'], before)
