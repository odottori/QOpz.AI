import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api import term_structure_cache as cache
from api.opz_api import app


class TestTermStructureCache(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        changed = patch.object(cache, 'CACHE_DIR', Path(self.temp.name))
        changed.start()
        self.addCleanup(changed.stop)
        self.client = TestClient(app)
        self.universe = patch('api.opz_api.opz_universe_latest', return_value={'items': [{'symbol': 'SPY'}]})
        self.universe.start()
        self.addCleanup(self.universe.stop)

    def test_get_never_contacts_broker(self):
        with patch('scripts.fetch_iv_history_ibkr.capture_ibkr_universe_term_structure', side_effect=AssertionError('GET contacted broker')):
            response = self.client.get('/opz/universe/term_structure?profile=paper')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'], [])
        self.assertTrue(response.json()['stale'])

    def test_explicit_refresh_persists_and_reads_cache(self):
        items = [{'symbol': 'SPY', 'chains': [{'expiry': '2027-01-15', 'iv': 0.2}]}]
        with patch('scripts.fetch_iv_history_ibkr.capture_ibkr_universe_term_structure', return_value=items) as broker:
            response = self.client.post('/opz/universe/term_structure/refresh?profile=paper')
            self.assertEqual(response.status_code, 200, response.text)
            result = self.client.get('/opz/universe/term_structure?profile=paper').json()
        broker.assert_called_once()
        self.assertEqual(result['items'], items)
        self.assertFalse(result['stale'])
        self.assertTrue(result['captured_at'])

    def test_failed_refresh_preserves_previous_snapshot(self):
        items = [{'symbol': 'SPY', 'chains': [{'expiry': '2027-01-15'}]}]
        cache.save_cache('paper', items)
        with patch('scripts.fetch_iv_history_ibkr.capture_ibkr_universe_term_structure', return_value=[]):
            response = self.client.post('/opz/universe/term_structure/refresh?profile=paper')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(cache.read_cache('paper', ['SPY'], 3)['items'], items)

    def test_profile_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            cache.save_cache('../outside', [])

    def test_non_object_cache_is_stale_not_server_error(self):
        for value in ['[]', 'null', '"text"', '3']:
            with self.subTest(value=value):
                (cache.CACHE_DIR / 'paper.json').write_text(value, encoding='utf-8')
                response = self.client.get('/opz/universe/term_structure?profile=paper')
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['items'], [])
                self.assertTrue(response.json()['stale'])
