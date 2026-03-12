import json
import shutil
import unittest
from pathlib import Path

import scripts.opz_process_registry as reg


class TestF6T2ProcessRegistry(unittest.TestCase):
    def test_register_list_untrack_cleanup(self):
        root = Path(".tmp_test_registry")
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)

        old_root = reg.ROOT
        old_path = reg.REG_PATH
        try:
            reg.ROOT = root
            reg.REG_PATH = root / "logs" / "codex_process_registry.json"

            rc = reg.main(["register", "--pid", "999999", "--role", "api", "--command", "py -m uvicorn"])
            self.assertEqual(rc, 0)
            self.assertTrue(reg.REG_PATH.exists())

            payload = json.loads(reg.REG_PATH.read_text(encoding="utf-8"))
            self.assertEqual(len(payload.get("entries", [])), 1)
            self.assertEqual(payload["entries"][0]["pid"], 999999)

            rc_tr = reg.main(["is-tracked", "--pid", "999999"])
            self.assertEqual(rc_tr, 0)

            rc_un = reg.main(["unregister", "--pid", "999999"])
            self.assertEqual(rc_un, 0)

            payload2 = json.loads(reg.REG_PATH.read_text(encoding="utf-8"))
            self.assertEqual(len(payload2.get("entries", [])), 0)
        finally:
            reg.ROOT = old_root
            reg.REG_PATH = old_path
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
