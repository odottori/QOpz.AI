import unittest
from datetime import datetime, timezone, timedelta

from execution.order_reducer import reduce_events_to_state, reconcile_invariants


class TestD2_15_StateMachineHardening(unittest.TestCase):
    def test_reducer_is_deterministic(self):
        t0 = datetime(2026, 2, 26, 0, 0, 0, tzinfo=timezone.utc)
        events = [
            {"ts_utc": (t0 + timedelta(seconds=2)).isoformat(), "event_type": "REJECTED_BROKER_UNAVAILABLE", "prev_state": "SUBMITTED", "new_state": "REJECTED"},
            {"ts_utc": (t0 + timedelta(seconds=1)).isoformat(), "event_type": "SUBMIT_ATTEMPT", "prev_state": "NEW", "new_state": "SUBMITTED"},
        ]
        # input order is shuffled; reducer must sort and still land deterministically
        self.assertEqual(reduce_events_to_state(events), "REJECTED")

    def test_reducer_rejects_illegal_transition(self):
        t0 = datetime(2026, 2, 26, 0, 0, 0, tzinfo=timezone.utc)
        events = [
            {"ts_utc": t0.isoformat(), "event_type": "BAD", "prev_state": "NEW", "new_state": "FILLED"},
        ]
        with self.assertRaises(ValueError):
            reduce_events_to_state(events)

    def test_reducer_rejects_prev_state_mismatch(self):
        t0 = datetime(2026, 2, 26, 0, 0, 0, tzinfo=timezone.utc)
        events = [
            {"ts_utc": t0.isoformat(), "event_type": "SUBMIT_ATTEMPT", "prev_state": "SUBMITTED", "new_state": "SUBMITTED"},
        ]
        with self.assertRaises(ValueError):
            reduce_events_to_state(events)

    def test_invariant_broker_unavailable_dominates(self):
        t0 = datetime(2026, 2, 26, 0, 0, 0, tzinfo=timezone.utc)
        events = [
            {"ts_utc": t0.isoformat(), "event_type": "SUBMIT_ATTEMPT", "prev_state": "NEW", "new_state": "SUBMITTED"},
            {"ts_utc": (t0 + timedelta(seconds=1)).isoformat(), "event_type": "REJECTED_BROKER_UNAVAILABLE", "prev_state": "SUBMITTED", "new_state": "REJECTED"},
        ]
        v = reconcile_invariants(events, final_state="REJECTED", outcome="REJECTED_BROKER_UNAVAILABLE")
        self.assertEqual(v, [])

    def test_invariant_filled_requires_fill_event(self):
        t0 = datetime(2026, 2, 26, 0, 0, 0, tzinfo=timezone.utc)
        events = [
            {"ts_utc": t0.isoformat(), "event_type": "SUBMIT_ATTEMPT", "prev_state": "NEW", "new_state": "SUBMITTED"},
            {"ts_utc": (t0 + timedelta(seconds=1)).isoformat(), "event_type": "ACK", "prev_state": "SUBMITTED", "new_state": "SUBMITTED"},
        ]
        v = reconcile_invariants(events, final_state="FILLED", outcome="FILLED")
        self.assertIn("FILLED_REQUIRES_FILL_EVENT", v)


if __name__ == "__main__":
    unittest.main()
