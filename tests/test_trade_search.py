"""Ссылка строится из локальных данных PoB без запроса объявлений."""

import json
import unittest
from urllib.parse import parse_qs, urlparse
from pob_poe2_mcp.engine import engine_layout, resolve_engine_dir
from pob_poe2_mcp.server import Server

ENGINE = resolve_engine_dir()


@unittest.skipUnless(engine_layout(ENGINE), 'Нужен исходный Lua')
class TradeSearch(unittest.TestCase):
    def setUp(self):
        self.server = Server(pob_dir=ENGINE)
        self.addCleanup(self.server.close)
        self.server.handle('initialize', {})
        self.server.call_tool('pob_create_build', {'level': 90})

    def call(self, name, arguments):
        result = self.server.handle('tools/call', {'name': name, 'arguments': arguments})
        self.assertFalse(result['isError'], result['content'])
        return result['structuredContent']['result']

    def test_catalogue_and_query_preserve_xml_and_use_original_ids(self):
        before = self.call('pob_export_xml', {})['xml']
        revision = self.server.api.revision
        catalog = self.call('pob_trade_catalog', {'slot': 'Ring 1'})
        self.assertEqual(catalog['source'], 'original-lua')
        self.assertIn('Lazuli Ring', catalog['bases'])
        self.assertIn('divine', [c['id'] for c in catalog['currencies']])
        stat = next(s for s in catalog['stats'] if s['type'] == 'explicit' and s['label'] == '# to maximum Life')
        result = self.call('pob_trade_search', {'slot': 'Ring 1', 'league': 'Лига & Test', 'base': 'Lazuli Ring', 'maxPrice': 5, 'currency': 'divine', 'filters': [{'id': stat['id'], 'min': 80}]})
        url = urlparse(result['url'])
        self.assertEqual(url.netloc, 'www.pathofexile.com')
        self.assertIn('/trade2/search/poe2/', url.path)
        self.assertEqual(json.loads(parse_qs(url.query)['q'][0]), result['query'])
        query = result['query']['query']
        self.assertEqual(query['filters']['type_filters']['filters']['category']['option'], 'accessory.ring')
        self.assertEqual(query['filters']['trade_filters']['filters']['price'], {'option': 'divine', 'max': 5})
        self.assertEqual(query['stats'][0]['filters'][0]['id'], stat['id'])
        self.assertEqual(self.server.api.revision, revision)
        self.assertEqual(self.call('pob_export_xml', {})['xml'], before)

    def test_invalid_filters_bases_and_budget_are_rejected(self):
        for extra in [{'filters': [{'id': 'unknown'}]}, {'base': 'Withered Wand'}, {'maxPrice': -1, 'currency': 'divine'}, {'maxPrice': 1, 'currency': 'unknown'}, {'league': ''}]:
            result = self.server.handle('tools/call', {'name': 'pob_trade_search', 'arguments': {'slot': 'Ring 1', 'league': 'Standard', **extra}})
            self.assertTrue(result['isError'], result)

    def test_option_filter_uses_original_option_value(self):
        catalog = self.call('pob_trade_catalog', {'slot': 'Ring 1'})
        stat = next(s for s in catalog['stats'] if s.get('fixedOption') and s['numeric'])
        result = self.call('pob_trade_search', {'slot': 'Ring 1', 'league': 'Standard', 'filters': [{'id': stat['id'], 'min': 2}]})
        row = result['query']['query']['stats'][0]['filters'][0]
        self.assertEqual(row['value'], {'option': int(stat['fixedOption']), 'min': 2})
        self.assertEqual(row['id'], stat['queryId'])

