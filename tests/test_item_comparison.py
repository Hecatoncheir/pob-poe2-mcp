"""Примерка использует исходный калькулятор и не меняет рабочую сборку."""

import unittest
from pob_poe2_mcp.api import BuildAPI, EngineError
from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir
from tests.test_equipment import RING, WAND

ENGINE = resolve_engine_dir()


@unittest.skipUnless(engine_layout(ENGINE), 'Нужен исходный Lua')
class ItemComparison(unittest.TestCase):
    def setUp(self):
        self.api = BuildAPI(pob_dir=ENGINE)
        self.addCleanup(self.api.close)
        self.api.call('createBuild', {'level': 90})

    def test_preview_matches_committed_stats_and_preserves_xml(self):
        before = self.api.call('exportBuild')['xml']
        revision = self.api.revision
        result = self.api.call('compareItem', {'slot': 'Ring 1', 'raw': RING})
        comparison = result['comparison']
        self.assertEqual(comparison['revision'], revision)
        life = next(row for row in comparison['rows'] if row['id'] == 'Life')
        self.assertGreater(life['after'], life['before'])
        self.assertTrue(life['benefit'])
        self.assertIn('+', life['changeText'])
        self.assertEqual(self.api.call('exportBuild')['xml'], before)
        self.assertEqual(self.api.revision, revision)
        self.api.call('equipItem', {'slot': 'Ring 1', 'raw': RING, 'expectedRevision': revision})
        self.assertEqual(life['after'], self.api.call('getBuildReport')['stats']['Life'])

    def test_same_item_is_not_removed_and_weaker_item_has_negative_change(self):
        self.api.call('equipItem', {'slot': 'Ring 1', 'raw': RING})
        item_id = self.api.call('getBuildReport')['items'][0]['id']
        same = self.api.call('compareItem', {'slot': 'Ring 1', 'itemId': item_id})['comparison']
        self.assertFalse(any(row.get('changeText') for row in same['rows']))
        weaker = self.api.call('compareItem', {'slot': 'Ring 1', 'raw': RING.replace('+50 to maximum Life', '+5 to maximum Life')})
        life = next(row for row in weaker['comparison']['rows'] if row['id'] == 'Life')
        self.assertFalse(life['benefit'])
        self.assertLess(life['after'], life['before'])

    def test_rejects_stale_preview_without_replacing_current_item(self):
        preview = self.api.call('compareItem', {'slot': 'Ring 1', 'raw': RING})
        self.api.call('equipItem', {'slot': 'Weapon 1', 'raw': WAND})
        before = self.api.call('exportBuild')['xml']
        with self.assertRaises(EngineError) as error:
            self.api.call('equipItem', {'slot': 'Ring 1', 'raw': RING, 'expectedRevision': preview['comparison']['revision']})
        self.assertEqual(error.exception.code, 'STALE_REVISION')
        self.assertEqual(self.api.call('exportBuild')['xml'], before)

    def test_incompatible_and_inactive_slot_do_not_produce_misleading_comparison(self):
        result = self.api.call('compareItem', {'slot': 'Ring 1', 'raw': WAND})
        self.assertFalse(result['compatible'])
        self.assertNotIn('comparison', result)
        result = self.api.call('compareItem', {'slot': 'Weapon 1 Swap', 'raw': WAND})
        self.assertIn('reason', result['comparison'])

    def test_spell_calculation_matches_equipping_in_each_weapon_set(self):
        self.api.call('addSkillGroup', {'gems': [{'id': 'Metadata/Items/Gems/SkillGemFireball', 'level': 5}]})
        raw = WAND + 'Implicits: 0\n50% increased Spell Damage\n'
        for index, slot in [(1, 'Weapon 1'), (2, 'Weapon 1 Swap')]:
            self.api.call('selectWeaponSet', {'index': index})
            before = self.api.call('exportBuild')['xml']
            comparison = self.api.call('compareItem', {'slot': slot, 'raw': raw})['comparison']
            self.assertEqual(self.api.call('exportBuild')['xml'], before)
            self.api.call('equipItem', {'slot': slot, 'raw': raw, 'expectedRevision': comparison['revision']})
            stats = self.api.call('getBuildReport')['stats']
            for row in comparison['rows']:
                if row['actor'] == 'player' and row['id'] in stats and 'after' in row:
                    self.assertAlmostEqual(row['after'], stats[row['id']], places=7, msg=row['id'])

    def test_minion_output_is_included_from_original_calculator(self):
        self.api.call('addSkillGroup', {'gems': [{'id': 'Metadata/Items/Gems/SkillGemSkeletalWarrior', 'level': 5}]})
        result = self.api.call('compareItem', {'slot': 'Ring 1', 'raw': RING})
        self.assertTrue(any(row['actor'] == 'minion' for row in result['comparison']['rows']))
