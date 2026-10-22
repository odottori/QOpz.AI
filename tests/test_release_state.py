import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import opz_release_state as state


class TestReleaseState(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.backup = self.base / 'backup'
        self.backup.mkdir()
        self.root = self.base / 'release-B'
        self.root.mkdir()
        self.env = self.base / 'runtime.env'
        (self.backup / 'current-link.before').write_text('')

    def test_failed_initial_publication_restores_absent_descriptor(self):
        with patch.object(Path, 'symlink_to', side_effect=OSError('link failure')):
            with self.assertRaises(OSError):
                state.publish(self.base, self.backup, self.root, self.env)
        self.assertTrue((self.base / 'current-release.json').exists())
        state.restore(self.base, self.backup, self.root)
        self.assertFalse((self.base / 'current-release.json').exists())

    @unittest.skipIf(os.name == 'nt', 'Real symlink transaction is also tested on deployment Linux')
    def test_previous_release_restored_after_successful_publication(self):
        previous = self.base / 'release-A'
        previous.mkdir()
        (self.base / 'current').symlink_to(previous)
        before = b'{"commit":"release-A","env":"original-A"}'
        (self.base / 'current-release.json').write_bytes(before)
        (self.backup / 'current-release.before.json').write_bytes(before)
        (self.backup / 'current-link.before').write_text(str(previous))
        state.publish(self.base, self.backup, self.root, self.env)
        self.assertEqual((self.base / 'current').readlink(), self.root)
        state.restore(self.base, self.backup, self.root)
        self.assertEqual((self.base / 'current').readlink(), previous)
        self.assertEqual((self.base / 'current-release.json').read_bytes(), before)

    @unittest.skipIf(os.name == 'nt', 'Requires real Linux symlinks')
    def test_link_swap_failure_restores_previous_descriptor_and_link(self):
        previous = self.base / 'release-A'
        previous.mkdir()
        (self.base / 'current').symlink_to(previous)
        before = b'{"commit":"release-A"}'
        (self.base / 'current-release.json').write_bytes(before)
        (self.backup / 'current-release.before.json').write_bytes(before)
        (self.backup / 'current-link.before').write_text(str(previous))
        replace = os.replace

        def fail_link(source, destination):
            if Path(destination) == self.base / 'current':
                raise OSError('link swap failure')
            return replace(source, destination)

        with patch.object(state.os, 'replace', side_effect=fail_link):
            with self.assertRaises(OSError):
                state.publish(self.base, self.backup, self.root, self.env)
        state.restore(self.base, self.backup, self.root)
        self.assertEqual((self.base / 'current').readlink(), previous)
        self.assertEqual((self.base / 'current-release.json').read_bytes(), before)

    def test_concurrent_descriptor_refuses_without_touching_metadata(self):
        foreign = json.dumps({'commit': 'release-C'}).encode()
        (self.base / 'current-release.json').write_bytes(foreign)
        with self.assertRaisesRegex(RuntimeError, 'changed concurrently'):
            state.restore(self.base, self.backup, self.root)
        self.assertEqual((self.base / 'current-release.json').read_bytes(), foreign)
