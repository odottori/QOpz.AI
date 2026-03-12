from __future__ import annotations

import unittest
from datetime import datetime, timezone

from execution.broker_event_schema import (
    BrokerEvent,
    BrokerVenue,
    InternalEventType,
    normalize_broker_event,
)


class TestD2_14_BrokerEventSchema(unittest.TestCase):
    def test_normalize_ack(self):
        be = BrokerEvent(
            venue=BrokerVenue.IBKR,
            ts_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            event_type="OrderACK",
            payload={"message": "accepted"},
        )
        ie = normalize_broker_event(be)
        self.assertEqual(ie.type, InternalEventType.ACK)
        self.assertEqual(ie.message, "accepted")

    def test_normalize_fill(self):
        be = BrokerEvent(
            venue=BrokerVenue.IBKR,
            ts_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            event_type="FILL",
            payload={"qty": 1},
        )
        ie = normalize_broker_event(be)
        self.assertEqual(ie.type, InternalEventType.FILL)

    def test_normalize_reject(self):
        be = BrokerEvent(
            venue=BrokerVenue.IBKR,
            ts_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            event_type="Rejected",
            payload={"message": "rejected by broker"},
        )
        ie = normalize_broker_event(be)
        self.assertEqual(ie.type, InternalEventType.REJECTED_BY_BROKER)

    def test_normalize_unknown(self):
        be = BrokerEvent(
            venue=BrokerVenue.UNKNOWN,
            ts_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            event_type="SomethingElse",
            payload={},
        )
        ie = normalize_broker_event(be)
        self.assertEqual(ie.type, InternalEventType.ERROR)
