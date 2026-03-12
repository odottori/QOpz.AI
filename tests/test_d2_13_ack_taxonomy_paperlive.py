from __future__ import annotations

import time
import unittest

from execution.ack_taxonomy import AckStatus, InternalEvent, classify_ack_status


class TestD2_13_AckTaxonomyPaperLive(unittest.TestCase):
    def test_acked_when_ack_event_present(self) -> None:
        submit = 1000.0
        deadline = 1005.0
        events = [
            InternalEvent(ts_utc=1001.0, event_type="ACK", payload={}),
        ]
        self.assertEqual(
            classify_ack_status(events, submit_ts_utc=submit, ack_deadline_ts_utc=deadline),
            AckStatus.ACKED,
        )

    def test_no_ack_when_before_deadline(self) -> None:
        submit = 1000.0
        deadline = 1005.0
        events = [
            InternalEvent(ts_utc=1003.0, event_type="SUBMIT_ATTEMPT", payload={}),
        ]
        self.assertEqual(
            classify_ack_status(events, submit_ts_utc=submit, ack_deadline_ts_utc=deadline),
            AckStatus.NO_ACK,
        )

    def test_timeout_when_deadline_elapsed(self) -> None:
        submit = 1000.0
        deadline = 1005.0
        # latest observed >= deadline
        events = [
            InternalEvent(ts_utc=1006.0, event_type="SUBMIT_ATTEMPT", payload={}),
        ]
        self.assertEqual(
            classify_ack_status(events, submit_ts_utc=submit, ack_deadline_ts_utc=deadline),
            AckStatus.TIMEOUT,
        )

    def test_broker_unavailable_dominates(self) -> None:
        submit = 1000.0
        deadline = 1005.0
        events = [
            InternalEvent(ts_utc=1006.0, event_type="ACK", payload={}),
            InternalEvent(ts_utc=1002.0, event_type="BROKER_UNAVAILABLE", payload={}),
        ]
        self.assertEqual(
            classify_ack_status(events, submit_ts_utc=submit, ack_deadline_ts_utc=deadline),
            AckStatus.BROKER_UNAVAILABLE,
        )
