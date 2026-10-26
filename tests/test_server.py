import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient
import server


class ServerTests(unittest.TestCase):
    def test_auth_tools_and_bounded_speech_without_device(self):
        config = {'mcp_token': 'test-only-' * 5}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(server, 'settings', return_value=config), \
             patch.object(server, 'ROOT', Path(directory)), \
             patch.object(server, 'synthesize', return_value=b'fake-audio') as synth, \
             patch.object(server, 'play', return_value=0.5) as play:
            _, app = server.build()
            with TestClient(app) as client:
                self.assertEqual(client.get('/mcp').status_code, 401)
                headers = {'Authorization': 'Bearer ' + config['mcp_token'],
                           'Accept': 'application/json, text/event-stream'}
                def call(method, params):
                    return client.post('/mcp', headers=headers,
                                       json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
                self.assertEqual(call('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                    'clientInfo': {'name': 'test', 'version': '1'}}).status_code, 200)
                listed = call('tools/list', {}).json()['result']['tools']
                self.assertEqual({x['name'] for x in listed}, {'speaker_say', 'speaker_music'})
                response = call('tools/call', {'name': 'speaker_say', 'arguments': {'text': 'x' * 301}})
                self.assertIn('text_length', response.text); synth.assert_not_called(); play.assert_not_called()
                response = call('tools/call', {'name': 'speaker_say', 'arguments': {'text': '合成测试'}})
                self.assertIn('played_seconds', response.text)
                synth.assert_called_once_with('合成测试'); play.assert_called_once_with(b'fake-audio')

    def test_bad_token_cannot_start(self):
        with patch.object(server, 'settings', return_value={'mcp_token': ''}):
            with self.assertRaises(ValueError): server.build()
