"""Штатный PowerBuilder: значения, путь, ограничения и неизменность XML."""
import unittest

from pob_poe2_mcp.api import BuildAPI, EngineError
from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir
from pob_poe2_mcp.server import Server

ENGINE = resolve_engine_dir()


@unittest.skipUnless(engine_layout(ENGINE), 'Нужен установленный PoB')
class NodePower(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = BuildAPI(pob_dir=ENGINE)

    @classmethod
    def tearDownClass(cls):
        cls.api.close()

    def setUp(self):
        self.api.call('createBuild', {'level': 90})

    def calculate(self, **options):
        job = self.api.call('getNodePower', {'action': 'start', 'stat': 'Evasion', **options})
        for _ in range(3000):
            result = self.api.call('getNodePower', {'action': 'poll', 'job': job['job'], 'includeScene': True})
            if result['complete']:
                return result
        self.fail('PowerBuilder не завершился')

    def test_original_report_distance_heatmap_and_xml(self):
        api = self.api
        catalog = api.call('getNodePower', {'action': 'catalog'})['entries']
        self.assertIn('Evasion', {row['id'] for row in catalog})
        self.assertEqual(len(catalog), len({row['id'] for row in catalog}))
        before, revision = api.call('exportBuild')['xml'], api.revision
        normal = api.call('getTreeGeometry', {'includeScene': True})['scene']
        result = self.calculate(maxDistance=5)
        self.assertTrue(result['entries'])
        self.assertTrue(all(0 < row['pathDist'] <= 5 for row in result['entries']))
        self.assertTrue(all(not row.get('allocated') for row in result['entries']))
        powers = [row['power'] for row in result['entries']]
        self.assertEqual(powers, sorted(powers, reverse=True))
        self.assertNotEqual(normal['commands'], result['scene']['commands'])
        self.assertEqual(normal['scale'], result['scene']['scale'])
        self.assertEqual(api.revision, revision)
        self.assertEqual(api.call('exportBuild')['xml'], before)
        target = result['entries'][0]
        stats = api.call('getBuildReport')['stats']
        api.call('treeAction', {'id': target['id'], 'action': 'allocate', 'attribute': 1})
        after = api.call('getBuildReport')['stats']
        self.assertAlmostEqual((after['Evasion'] - stats['Evasion']) / target['pathDist'], target['pathPower'])

    def test_cancel_supersede_and_stale_revision(self):
        api = self.api
        first = api.call('getNodePower', {'action': 'start', 'stat': 'Life', 'maxDistance': 5})
        second = api.call('getNodePower', {'action': 'start', 'stat': 'Evasion', 'maxDistance': 10})
        with self.assertRaises(EngineError):
            api.call('getNodePower', {'action': 'poll', 'job': first['job']})
        api.call('getNodePower', {'action': 'cancel', 'job': first['job']})
        api.call('getNodePower', {'action': 'poll', 'job': second['job']})
        api.call('setCustomMods', {'text': '+10 to Evasion Rating'})
        with self.assertRaises(EngineError) as caught:
            api.call('getNodePower', {'action': 'poll', 'job': second['job']})
        self.assertEqual(caught.exception.code, 'STALE_REVISION')
        third = api.call('getNodePower', {'action': 'start', 'stat': 'Evasion'})
        api.call('getNodePower', {'action': 'cancel', 'job': third['job']})
        with self.assertRaises(EngineError):
            api.call('getNodePower', {'action': 'poll', 'job': third['job']})

    def test_public_mcp_tokens_and_validation(self):
        with_server = Server(pob_dir=ENGINE)
        try:
            with_server.handle('initialize', {})
            with_server.handle('tools/call', {'name': 'pob_create_build', 'arguments': {'level': 90}})
            invalid = with_server.handle('tools/call', {'name': 'pob_node_power', 'arguments': {'action': 'start', 'stat': 'Evasion', 'maxDistance': 0}})
            self.assertTrue(invalid['isError'])
            start = with_server.handle('tools/call', {'name': 'pob_node_power', 'arguments': {'action': 'start', 'stat': 'Evasion', 'maxDistance': 5}})
            job = start['structuredContent']['result']['job']
            for _ in range(3000):
                result = with_server.handle('tools/call', {'name': 'pob_node_power', 'arguments': {'action': 'poll', 'job': job, 'includeScene': True}})
                self.assertFalse(result['isError'], result)
                report = result['structuredContent']['result']
                if report['complete']:
                    break
            self.assertTrue(report['complete'])
            token = report['scene']['commands'][0]['texture']
            self.assertNotIn('file', report['scene']['commands'][0])
            self.assertTrue(with_server.scene_assets.read(token)['png'])
        finally:
            with_server.close()
