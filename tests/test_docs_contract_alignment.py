from __future__ import annotations

import unittest

from tools.docs_contract_check import validate_contract


class TestDocsContractAlignment(unittest.TestCase):
    def test_docs_and_runtime_contract_are_aligned(self) -> None:
        errors = validate_contract()
        self.assertEqual([], errors, f"docs/runtime contract mismatch:\n- " + "\n- ".join(errors))


if __name__ == "__main__":
    unittest.main()
