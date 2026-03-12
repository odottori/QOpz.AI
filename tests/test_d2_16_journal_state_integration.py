import unittest

from execution.storage import init_execution_schema, record_event
from execution.journal_state import derive_state_from_journal


class TestD2_16_JournalStateIntegration(unittest.TestCase):
    def setUp(self):
        init_execution_schema()

    def test_derive_state_matches_journal(self):
        cid = "D2_16_CID_1"
        record_event(
            client_order_id=cid,
            run_id="D2_16",
            profile="dev",
            event_type="ORDER_STATE",
            prev_state="NEW",
            new_state="SUBMITTED",
            details={"note": "submit"},
        )
        record_event(
            client_order_id=cid,
            run_id="D2_16",
            profile="dev",
            event_type="ORDER_STATE",
            prev_state="SUBMITTED",
            new_state="ACKED",
            details={"note": "ack"},
        )
        derived = derive_state_from_journal(cid)
        self.assertEqual(derived.state, "ACKED")


if __name__ == "__main__":
    unittest.main()
