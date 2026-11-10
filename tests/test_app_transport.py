"""Проверка аутентифицированного подключения без запуска второго движка."""

import json
from contextlib import contextmanager
from pathlib import Path
import socketserver
import tempfile
import threading
import unittest
from unittest.mock import patch

from pob_poe2_mcp.api import BuildAPI
from pob_poe2_mcp.errors import EngineError
from pob_poe2_mcp.server import Server


@contextmanager
def bridge(directory, revision=7, drop=(), close_after=(), error=None, pause=None, results=None):
    requests = []
    token = str(revision).zfill(64)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                request = json.loads(line)
                requests.append(request)
                if request['token'] != token:
                    return
                method = request['method']
                if method in drop:
                    return
                if pause and method == 'getSnapshot':
                    pause.wait(3)
                    return
                response = {'protocol': 1, 'id': request['id'], 'revision': revision}
                if error and method != 'initialize':
                    response['error'] = {'code': error, 'message': 'Проверочная ошибка'}
                else:
                    response['result'] = (results or {}).get(method, {'platform': 'windows-app', 'entries': []})
                self.wfile.write((json.dumps(response) + '\n').encode('utf-8'))
                self.wfile.flush()
                if method in close_after:
                    return

    class TCPServer(socketserver.ThreadingTCPServer):
        daemon_threads = True

    with TCPServer(('127.0.0.1', 0), Handler) as tcp:
        endpoint = Path(directory) / 'endpoint.json'
        endpoint.write_text(json.dumps({'port': tcp.server_address[1], 'token': token,
                                       'installDir': str(directory)}), encoding='utf-8')
        endpoint.with_name('config.json').write_text(json.dumps({'token': token}), encoding='utf-8')
        thread = threading.Thread(target=lambda: tcp.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            yield requests
        finally:
            tcp.shutdown()
            thread.join(timeout=2)


class AppConnection(unittest.TestCase):
    def test_timeout_does_not_wait_for_blocked_reader_to_close(self):
        release = threading.Event()
        errors = []

        def request(endpoint):
            try:
                with BuildAPI(mode='app', endpoint=endpoint, timeout=1) as api:
                    api.timeout = 0.1
                    api.call('getSnapshot')
            except EngineError as error:
                errors.append(error.code)

        with tempfile.TemporaryDirectory() as directory, bridge(directory, pause=release):
            worker = threading.Thread(target=request, args=(Path(directory) / 'endpoint.json',), daemon=True)
            worker.start()
            try:
                worker.join(timeout=1)
                self.assertFalse(worker.is_alive(), 'Тайм-аут завис при закрытии reader')
                self.assertEqual(errors, ['TIMEOUT'])
            finally:
                release.set()
                worker.join(timeout=2)

    def test_api_uses_token_and_current_app_revision(self):
        requests = []
        token = "a" * 64

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    request = json.loads(line)
                    requests.append(request)
                    result = {"platform": "windows-app"} if request["method"] == "initialize" else {"level": 42}
                    response = {"protocol": 1, "id": request["id"], "revision": 7, "result": result}
                    self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))
                    self.wfile.flush()

        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server, tempfile.TemporaryDirectory() as directory:
            thread = threading.Thread(target=server.handle_request, daemon=True)
            thread.start()
            endpoint = Path(directory) / "endpoint.json"
            endpoint.write_text(json.dumps({"port": server.server_address[1], "token": token, "installDir": directory}), encoding="utf-8")
            with patch("pob_poe2_mcp.api.ProcessTransport", side_effect=AssertionError("Не должен запускаться")):
                with BuildAPI(mode="app", endpoint=endpoint) as api:
                    self.assertEqual(api.capabilities["platform"], "windows-app")
                    self.assertEqual(api.call("getSnapshot"), {"level": 42})
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual([request["token"] for request in requests], [token, token])
        self.assertEqual(requests[1]["params"]["revision"], 7)


class AppReconnection(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        state = patch('pob_poe2_mcp.transport.bridge_state_dir', return_value=self.directory)
        state.start()
        self.addCleanup(state.stop)
        self.server = Server(mode='app', timeout=1)
        self.server.handle('initialize', {})
        self.addCleanup(self.server.close)

    def call(self, tool='pob_catalog', **arguments):
        return self.server.handle('tools/call', {'name': tool, 'arguments': arguments})

    def test_read_reconnects_using_new_endpoint_token_and_revision(self):
        with bridge(self.directory, close_after=('getCatalog',)) as old_requests:
            self.assertFalse(self.call()['isError'])
        with bridge(self.directory, revision=19) as new_requests:
            result = self.call()
            self.assertFalse(result['isError'], result)
            self.assertEqual(result['structuredContent']['revision'], 19)
            self.assertEqual(new_requests[-1]['params']['revision'], 19)
            self.assertNotEqual(old_requests[0]['token'], new_requests[0]['token'])

    def test_lost_mutation_response_is_not_replayed(self):
        with bridge(self.directory, drop=('addItem',)) as old_requests:
            self.assertFalse(self.call()['isError'])
            with bridge(self.directory, revision=19) as new_requests:
                result = self.call('pob_add_item', raw='Rarity: Normal\nWithered Wand\n')
                self.assertTrue(result['isError'])
                self.assertIsNone(self.server.api)
                self.assertEqual([r['method'] for r in old_requests].count('addItem'), 1)
                self.assertEqual(new_requests, [])
                self.assertFalse(self.call()['isError'])
                self.assertEqual([r['method'] for r in new_requests], ['initialize', 'getCatalog'])

    def test_read_retry_is_bounded_and_next_call_can_recover(self):
        with bridge(self.directory, close_after=('getCatalog',)):
            self.assertFalse(self.call()['isError'])
        with bridge(self.directory, revision=19, drop=('getCatalog',)) as requests:
            self.assertTrue(self.call()['isError'])
            self.assertIsNone(self.server.api)
            self.assertEqual([r['method'] for r in requests], ['initialize', 'getCatalog'])
        with bridge(self.directory, revision=31):
            self.assertFalse(self.call()['isError'])

    def test_closed_app_error_does_not_poison_subsequent_connection(self):
        with bridge(self.directory, drop=('getCatalog',)):
            result = self.call()
            self.assertTrue(result['isError'])
            self.assertIsNone(self.server.api)
        (self.directory / 'endpoint.json').unlink()
        result = self.call()
        self.assertEqual(json.loads(result['content'][0]['text'])['code'], 'BRIDGE_NOT_RUNNING')
        with bridge(self.directory, revision=19):
            self.assertFalse(self.call()['isError'])

    def test_revision_conflict_does_not_reconnect_or_retry(self):
        with bridge(self.directory, error='STALE_REVISION') as requests:
            result = self.call()
            self.assertEqual(json.loads(result['content'][0]['text'])['code'], 'STALE_REVISION')
            self.assertIsNotNone(self.server.api)
            self.assertFalse(self.server.api.closed)
            self.assertEqual([r['method'] for r in requests], ['initialize', 'getCatalog'])

    def test_restart_required_before_attaching_to_updated_bridge(self):
        with bridge(self.directory) as requests:
            (self.directory / 'config.json').write_text(json.dumps({'token': 'b' * 64}), encoding='utf-8')
            result = self.call('pob_get_build_directory')
            self.assertEqual(json.loads(result['content'][0]['text'])['code'], 'BRIDGE_RESTART_REQUIRED')
            self.assertEqual(requests, [])

    def test_linux_bridge_returns_host_directory_and_character_data(self):
        builds = self.directory / 'PoB Builds'
        builds.mkdir()
        character = {'name': 'ЛедянаяИскра', 'class': 'Witch', 'level': 90, 'league': 'Standard'}
        full = {**character, 'passives': {'hashes': []}, 'equipment': [], 'skills': [], 'jewels': []}
        results = {
            'initialize': {'platform': 'linux-app'},
            'getBuildDirectory': {
                'directory': r'C:\POB BUILDS',
                'wine': {'prefix': str(self.directory), 'workingDirectory': 'C:/'},
            },
            'listCharacters': {'characters': [character]},
            'getCharacter': {'character': full},
        }
        with bridge(self.directory, results=results) as requests:
            with patch('pob_poe2_mcp.wine_paths._drives', return_value={'c:': self.directory}):
                folder = self.call('pob_get_build_directory')
            resolved = Path(folder['structuredContent']['result']['directory'])
            self.assertTrue(resolved.samefile(builds), resolved)
            self.assertEqual(self.call('pob_list_characters')['structuredContent']['result'], {'characters': [character]})
            self.assertEqual(self.call('pob_get_character', name=character['name'])['structuredContent']['result'], {'character': full})
            self.assertEqual(requests[-1]['params']['name'], character['name'])


if __name__ == "__main__":
    unittest.main()
