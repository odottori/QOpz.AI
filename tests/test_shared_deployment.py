import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException

from api import control_plane

ROOT = Path(__file__).resolve().parents[1]


class TestSharedDeployment(unittest.TestCase):
    def test_external_gateway_actions_never_touch_even_owned_old_container(self):
        with patch.object(control_plane, '_MANAGE_IBWR', False), \
             patch.object(control_plane, '_docker_client') as docker:
            status = control_plane._ibwr_action('status', 'test')
            self.assertEqual(status['service_state'], 'EXTERNAL')
            self.assertFalse(status['managed'])
            for action in ['on', 'off']:
                with self.assertRaises(HTTPException) as error:
                    control_plane._ibwr_action(action, 'test')
                self.assertEqual(error.exception.status_code, 409)
            docker.assert_not_called()

    def test_docker_selection_never_crosses_project(self):
        foreign = {'Id': 'foreign', 'Labels': {'com.docker.compose.service': 'ibg', 'com.docker.compose.project': 'app'}}
        unlabelled = {'Id': 'unlabelled', 'Labels': {'com.docker.compose.service': 'ibg'}}
        owned = {'Id': 'owned', 'Labels': {'com.docker.compose.service': 'ibg', 'com.docker.compose.project': 'qopz'}}
        with patch.object(control_plane, '_PROJECT', 'qopz'):
            self.assertIsNone(control_plane._find_compose_service([foreign, unlabelled], 'ibg'))
            self.assertEqual(control_plane._find_compose_service([foreign, owned], 'ibg')['Id'], 'owned')

    def test_mount_is_read_only_and_preserves_logs(self):
        text = (ROOT / 'ui/src/App.tsx').read_text(encoding='utf-8')
        mount = text.split('// On mount:', 1)[1].split('// Heartbeat', 1)[0]
        self.assertIn('void doFetchFeedLog();', mount)
        self.assertIn('void refreshAll();', mount)
        self.assertNotIn('true, false', mount)
        refresh = text.split('if (triggerRefresh) {', 1)[1].split('async function doFetchControlStatus', 1)[0]
        self.assertNotIn('/opz/system/log/clear', refresh)
        bootstrap = text.split('async function refreshAll()', 1)[1].split('async function doPreview', 1)[0]
        self.assertIn('AbortSignal.timeout(15_000)', bootstrap)
        self.assertLess(bootstrap.index('void doFetchSysStatus();'), bootstrap.index('await Promise.allSettled'))
        self.assertIn('setNarratorTutorial(value); return value;', bootstrap)

    def test_narrator_reads_existing_canonical_guide(self):
        from api.opz_api import opz_narrator_tutorial
        result = opz_narrator_tutorial()
        self.assertTrue(result['exists'])
        self.assertEqual(Path(result['path']), ROOT / 'docs/guide/guida_completa.md')
        self.assertIn('# QOpz.AI', result['content'])

    def test_api_badge_does_not_claim_broker_connection(self):
        text = (ROOT / 'ui/src/App.tsx').read_text(encoding='utf-8')
        self.assertIn('"API ONLINE"', text)
        self.assertIn('Non certifica la connessione IBKR.', text)
        self.assertNotIn('apiOnline ? TOOLTIPS.ibkr_connected', text)

    def test_shared_prefix_and_loopback_gateway(self):
        docker = (ROOT / 'Dockerfile.nginx').read_text(encoding='utf-8')
        compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
        snippet = (ROOT / 'docker/qopz-shared-location.conf').read_text(encoding='utf-8')
        nginx = (ROOT / 'docker/nginx.conf').read_text(encoding='utf-8')
        self.assertIn('VITE_BASE_PATH=/qopz/', docker)
        self.assertIn('127.0.0.1:${NGINX_PORT:-8080}:80', compose)
        self.assertNotIn('location / {', snippet)
        self.assertIn('location /qopz/guide/ {', nginx)
        self.assertIn('absolute_redirect off;', nginx)
