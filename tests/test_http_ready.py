import io
import json
import subprocess
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
from unittest.mock import MagicMock, patch

from scripts import opz_http_ready as ready


class TestHttpReady(unittest.TestCase):
    def response(self, body=b'{"status":"ok"}', content_type='application/json'):
        response = MagicMock()
        response.status = 200
        response.headers = {'Content-Type': content_type}
        response.read.return_value = body
        response.__enter__.return_value = response
        return response

    def test_reload_delay_retries_404_then_requires_real_json(self):
        error = urllib.error.HTTPError('http://local/qopz/health', 404, 'old worker', {}, io.BytesIO(b'old'))
        opener = MagicMock()
        opener.open.side_effect = [error, self.response()]
        with patch.object(ready.urllib.request, 'build_opener', return_value=opener):
            first = ready.probe_once('http://local/qopz/health', '178.104.94.34', 1)
            second = ready.probe_once('http://local/qopz/health', '178.104.94.34', 1)
        processes = [subprocess.CompletedProcess([], 0, json.dumps(row)) for row in [first, second]]
        with patch.object(ready.subprocess, 'run', side_effect=processes), patch.object(ready.time, 'sleep'):
            result = ready.wait_ready('http://local/qopz/health', '178.104.94.34')
        self.assertEqual(result['statuses'], [404, 200])
        self.assertTrue(result['ok'])

    def test_html_200_does_not_pass(self):
        opener = MagicMock()
        for mime in ['text/html', 'application/jsonp', 'text/plain; note=application/json']:
            opener.open.return_value = self.response(content_type=mime)
            with patch.object(ready.urllib.request, 'build_opener', return_value=opener):
                self.assertFalse(ready.probe_once('http://local/qopz/health', 'host', 1)['ready'])

    def test_deadline_fails_closed(self):
        process = subprocess.CompletedProcess([], 0, '{"status":200,"ready":true}')
        with patch.object(ready.subprocess, 'run', return_value=process), \
             patch.object(ready.time, 'monotonic', side_effect=[0, 0, 31]):
            with self.assertRaisesRegex(RuntimeError, 'readiness failed'):
                ready.wait_ready('http://local/qopz/health', 'host', timeout=30)

    def server(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}'

    def test_redirect_never_reaches_alternative_endpoint(self):
        visited = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                visited.append(self.path)
                if self.path == '/start':
                    self.send_response(302)
                    self.send_header('Location', '/target')
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')

        url = self.server(Handler)
        result = ready.probe_once(url + '/start', 'host', 1)
        self.assertEqual(result, {'status': 302, 'ready': False})
        self.assertEqual(visited, ['/start'])

    def test_real_slow_server_is_bounded_by_parent_budget(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                for byte in b'{"status":"ok"}':
                    try:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.15)
                    except OSError:
                        break

        url = self.server(Handler)
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'readiness failed'):
            ready.wait_ready(url, 'host', timeout=0.5)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_real_truncated_chunk_is_retried_then_valid_json_succeeds(self):
        attempts = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def do_GET(self):
                attempts.append(1)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                if len(attempts) == 1:
                    self.send_header('Transfer-Encoding', 'chunked')
                    self.end_headers()
                    self.wfile.write(b'10\r\n{"status"')
                    self.close_connection = True
                else:
                    body = b'{"status":"ok"}'
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

        result = ready.wait_ready(self.server(Handler), 'host', timeout=5)
        self.assertEqual(result['statuses'], ['IncompleteRead', 200])
        self.assertTrue(result['ok'])
