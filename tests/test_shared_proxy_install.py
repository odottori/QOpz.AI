import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import install_shared_proxy as installer


class TestSharedProxyInstall(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.nginx = self.root / 'nginx'
        sites = self.nginx / 'sites-enabled'
        sites.mkdir(parents=True)
        self.originals = {}
        for name, host in [('qopzai.conf', 'qopzai.duckdns.org'), ('qedgeai.conf', 'qedgeai.duckdns.org')]:
            target = sites / name
            data = f'server {{\n    listen 443 ssl;\n    server_name {host};\n    location /existing/ {{ return 200; }}\n}}\n'.encode()
            target.write_bytes(data)
            self.originals[target] = data
        self.patch = patch.object(installer, 'NGINX', self.nginx)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.backup = self.root / 'backup'
        self.preflight = patch.object(installer, 'preflight_http', return_value={'/': 404, '/polyedge/': 404, '/quantlens/': 404})
        self.preflight.start()
        self.addCleanup(self.preflight.stop)

    def test_existing_ip_application_refuses_before_config_mutation(self):
        with patch.object(installer, 'preflight_http', side_effect=RuntimeError('existing app')):
            with self.assertRaisesRegex(RuntimeError, 'existing app'):
                installer.install(self.backup, '178.104.94.34')
        for target, original in self.originals.items():
            self.assertEqual(target.read_bytes(), original)
        self.assertFalse((self.backup / 'proxy-manifest.json').exists())

    def test_install_preserves_other_locations_and_rollback_restores_bytes(self):
        with patch.object(installer, 'run') as command:
            installer.install(self.backup, '178.104.94.34')
            for target in self.originals:
                self.assertIn(b'location /existing/ { return 200; }', target.read_bytes())
            command.assert_any_call('nginx', '-t')
            installer.restore(self.backup)
        for target, original in self.originals.items():
            self.assertEqual(target.read_bytes(), original)
        self.assertFalse((self.nginx / 'sites-enabled/qopz-shared-http.conf').exists())

    def test_validation_error_restores_configuration(self):
        with patch.object(installer, 'run', side_effect=[subprocess.CalledProcessError(1, 'nginx'), None, None]):
            with self.assertRaises(subprocess.CalledProcessError):
                installer.install(self.backup, '178.104.94.34')
        for target, original in self.originals.items():
            self.assertEqual(target.read_bytes(), original)

    def test_rollback_does_not_overwrite_concurrent_edits(self):
        with patch.object(installer, 'run'):
            installer.install(self.backup, '178.104.94.34')
            http = self.nginx / 'sites-enabled/qopz-shared-http.conf'
            http.write_text('concurrent external change')
            with self.assertRaises(RuntimeError):
                installer.restore(self.backup)
            self.assertEqual(http.read_text(), 'concurrent external change')

    def test_late_conflict_causes_no_partial_restore(self):
        with patch.object(installer, 'run'):
            installer.install(self.backup, '178.104.94.34')
            target = self.nginx / 'sites-enabled/qopzai.conf'
            target.write_text('concurrent site change')
            before = {file: file.read_bytes() for file in self.nginx.rglob('*.conf')}
            with self.assertRaises(RuntimeError):
                installer.restore(self.backup)
            self.assertEqual(before, {file: file.read_bytes() for file in self.nginx.rglob('*.conf')})

    def test_http_before_https_does_not_hide_tls_server(self):
        host = 'qopzai.duckdns.org'
        text = f'server {{ listen 80; server_name {host}; return 301 https://$host$request_uri; }}\nserver {{ listen 443 ssl; server_name {host}; }}'
        result = installer.tls_locations(text, host, '    include /etc/nginx/snippets/qopz-shared-location.conf;')
        self.assertNotIn('include', result.split('\nserver')[0])
        self.assertIn('include', result.split('\nserver')[1])

    def test_failed_atomic_replace_never_truncates_live_file(self):
        target = next(iter(self.originals))
        with patch.object(installer.os, 'replace', side_effect=OSError('simulated disk error')):
            with self.assertRaises(OSError):
                installer.atomic_write(target, b'new data')
        self.assertEqual(target.read_bytes(), self.originals[target])

    def test_commented_include_is_not_active_integration(self):
        include = '    include /etc/nginx/snippets/qopz-shared-location.conf;'
        text = 'server { listen 443 ssl; server_name qopzai.duckdns.org;\n#' + include + '\n}'
        result = installer.tls_locations(text, 'qopzai.duckdns.org', include)
        active = '\n'.join(line for line in result.splitlines() if not line.lstrip().startswith('#'))
        self.assertIn(include, active)
