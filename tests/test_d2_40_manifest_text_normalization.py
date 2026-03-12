import tempfile
import unittest
from pathlib import Path


class TestD240ManifestTextNormalization(unittest.TestCase):
    def _write(self, p: Path, data: bytes) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def test_verify_manifest_treats_gitignore_and_lock_as_text(self) -> None:
        from tools import verify_manifest as vm

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p_gitignore = root / ".gitignore"
            p_lock = root / "requirements.lock"

            # Same logical content, different EOL bytes
            lf = b"a\n\nb\n"
            crlf = b"a\r\n\r\nb\r\n"

            self._write(p_gitignore, lf)
            sha_lf, size_lf = vm._sha256_normalized(p_gitignore)
            self._write(p_gitignore, crlf)
            sha_crlf, size_crlf = vm._sha256_normalized(p_gitignore)
            self.assertEqual(sha_lf, sha_crlf)
            self.assertEqual(size_lf, size_crlf)

            self._write(p_lock, lf)
            sha_lf, size_lf = vm._sha256_normalized(p_lock)
            self._write(p_lock, crlf)
            sha_crlf, size_crlf = vm._sha256_normalized(p_lock)
            self.assertEqual(sha_lf, sha_crlf)
            self.assertEqual(size_lf, size_crlf)

    def test_rebuild_manifest_treats_gitignore_and_lock_as_text(self) -> None:
        from tools import rebuild_manifest as rm

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p_gitignore = root / ".gitignore"
            p_lock = root / "requirements.lock"

            lf = b"x\n\ny\n"
            crlf = b"x\r\n\r\ny\r\n"

            self._write(p_gitignore, lf)
            sha_lf, size_lf = rm._sha256(p_gitignore)
            self._write(p_gitignore, crlf)
            sha_crlf, size_crlf = rm._sha256(p_gitignore)
            self.assertEqual(sha_lf, sha_crlf)
            self.assertEqual(size_lf, size_crlf)

            self._write(p_lock, lf)
            sha_lf, size_lf = rm._sha256(p_lock)
            self._write(p_lock, crlf)
            sha_crlf, size_crlf = rm._sha256(p_lock)
            self.assertEqual(sha_lf, sha_crlf)
            self.assertEqual(size_lf, size_crlf)


if __name__ == "__main__":
    unittest.main()
