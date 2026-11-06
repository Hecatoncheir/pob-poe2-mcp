"""Экипировку и описание проверяет настоящий Lua, ошибочная замена сохраняет сборку."""

import unittest

from pob_poe2_mcp.api import BuildAPI, EngineError
from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir
from pob_poe2_mcp.server import METHODS, TOOLS

ENGINE = resolve_engine_dir()
WAND = 'Rarity: Normal\nWithered Wand\n'
RING = 'Item Class: Rings\nRarity: Rare\nTide Loop\nLazuli Ring\n--------\nItem Level: 80\n--------\n+50 to maximum Life\n+20% to Fire Resistance\n'


@unittest.skipUnless(engine_layout(ENGINE), 'Нужен исходный Lua')
class Equipment(unittest.TestCase):
    def setUp(self):
        self.api = BuildAPI(pob_dir=ENGINE)
        self.addCleanup(self.api.close)
        self.api.call('createBuild', {'level': 90})

    def report(self):
        return self.api.call('getBuildReport')

    def test_inspection_uses_original_description_without_mutation(self):
        xml = self.api.call('exportBuild')['xml']
        revision = self.api.revision
        before = self.report()
        preview = self.api.call('inspectItem', {'raw': RING, 'slot': 'Ring 1'})
        self.assertEqual(preview['source'], 'original-lua')
        self.assertTrue(preview['compatible'])
        self.assertIn('Ring 1', preview['slots'])
        self.assertNotIn('Boots', preview['slots'])
        self.assertEqual(preview['item']['base'], 'Lazuli Ring')
        lines = '\n'.join(line.get('text', '') for line in preview['lines'])
        self.assertIn('Tide Loop', lines)
        self.assertIn('+50 to maximum Life', lines)
        self.assertNotIn('Tip: ', lines)
        self.assertEqual(self.api.revision, revision)
        self.assertEqual(self.api.call('exportBuild')['xml'], xml)
        self.assertEqual(self.report()['stats'], before['stats'])

    def test_replace_remove_existing_item_and_xml_roundtrip(self):
        before = self.report()['stats']['Life']
        self.api.call('equipItem', {'slot': 'Ring 1', 'raw': RING})
        changed = self.report()
        self.assertGreater(changed['stats']['Life'], before)
        item_id = changed['items'][0]['id']
        inspection = self.api.call('inspectItem', {'itemId': item_id, 'slot': 'Ring 1'})
        self.assertTrue(inspection['compatible'])
        self.api.call('equipItem', {'slot': 'Ring 1', 'itemId': 0})
        removed = self.report()
        self.assertEqual(removed['stats']['Life'], before)
        self.assertEqual(len(removed['items']), 1)
        self.api.call('equipItem', {'slot': 'Ring 2', 'itemId': item_id})
        equipped = self.report()
        xml = self.api.call('exportBuild')['xml']
        self.api.call('loadBuild', {'xml': xml})
        restored = self.report()
        self.assertEqual(equipped['items'], restored['items'])
        self.assertEqual({s['name']: s['itemId'] for s in equipped['slots']}, {s['name']: s['itemId'] for s in restored['slots']})
        self.assertEqual(equipped['stats'], restored['stats'])

    def test_invalid_replacement_preserves_working_item_and_revision(self):
        self.api.call('equipItem', {'slot': 'Ring 1', 'raw': RING})
        self.api.call('loadBuild', {'xml': self.api.call('exportBuild')['xml']})
        before = self.report()
        revision = self.api.revision
        for params in [
            {'slot': 'Ring 1', 'raw': WAND},
            {'slot': 'Ring 1', 'raw': 'not an item'},
            {'slot': 'Ring 1', 'itemId': 9999},
            {'slot': 'invented', 'itemId': 0},
            {'slot': 'Ring 1', 'raw': RING, 'itemId': 1},
        ]:
            with self.subTest(params=params), self.assertRaises(EngineError):
                self.api.call('equipItem', params)
            self.assertEqual(self.api.revision, revision)
            for field in ['items', 'slots', 'stats']:
                self.assertEqual(self.report()[field], before[field])

    def test_requirements_unsupported_and_original_weapon_switch(self):
        raw = RING.replace('Item Level: 80', 'Item Level: 80\nRequirements:\nLevel: 99') + 'unrecognized modifier\n'
        result = self.api.call('inspectItem', {'raw': raw, 'slot': 'Ring 1'})
        self.assertTrue(result['item']['unsupported'])
        text = '\n'.join(line.get('text', '') for line in result['lines'])
        self.assertIn('99', text)
        self.api.call('equipItem', {'slot': 'Weapon 1 Swap', 'raw': WAND})
        self.api.call('selectWeaponSet', {'index': 2})
        report = self.report()
        self.assertEqual(report['weaponSet'], 2)
        self.assertTrue(next(slot for slot in report['slots'] if slot['name'] == 'Weapon 1 Swap')['visible'])
        self.api.call('selectWeaponSet', {'index': 1})
        self.assertEqual(self.report()['weaponSet'], 1)


class EquipmentManifest(unittest.TestCase):
    def test_public_contract_declares_read_only_inspection(self):
        tools = {tool['name']: tool for tool in TOOLS}
        self.assertEqual(METHODS['pob_inspect_item'], 'inspectItem')
        self.assertTrue(tools['pob_inspect_item']['annotations']['readOnlyHint'])
        self.assertTrue(tools['pob_equip_item']['annotations']['destructiveHint'])
