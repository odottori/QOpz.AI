import unittest


from execution.ack import classify_ack, AckStatus


class TestD2_9_AckClassification(unittest.TestCase):
    def test_acked_when_ack_event_present(self):
        events = [
            {"event_type": "SUBMITTED", "ts_utc": "2026-02-25T10:00:00+00:00"},
            {"event_type": "ACK", "ts_utc": "2026-02-25T10:00:00.123+00:00"},
        ]
        res = classify_ack(events, ack_deadline_ms=5_000, submit_event_type="SUBMITTED", ack_event_type="ACK")
        self.assertEqual(res.status, AckStatus.ACKED)
        self.assertIsNotNone(res.ack_latency_ms)
        self.assertGreaterEqual(res.ack_latency_ms, 0)

    def test_timeout_when_no_ack_and_deadline_elapsed(self):
        # submit far in the past -> elapsed >= deadline
        events = [{"event_type": "SUBMITTED", "ts_utc": "2000-01-01T00:00:00+00:00"}]
        res = classify_ack(events, ack_deadline_ms=1_000, submit_event_type="SUBMITTED", ack_event_type="ACK")
        self.assertEqual(res.status, AckStatus.TIMEOUT)
