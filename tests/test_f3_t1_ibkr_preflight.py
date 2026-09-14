from __future__ import annotations

import unittest
from unittest.mock import patch

from execution.config_loader import broker_port_matches_profile, describe_broker_port, expected_broker_port, load_profile_config
from execution.ibkr_preflight import build_broker_profile_expectation, run_broker_preflight
from execution.ibkr_tws import IbkrProbeResult


class BrokerPortSemanticsTests(unittest.TestCase):
    def test_expected_ports_are_stable(self):
        self.assertEqual(expected_broker_port("paper", broker_kind="tws"), 7497)
        self.assertEqual(expected_broker_port("paper", broker_kind="gateway"), 4002)
        self.assertEqual(expected_broker_port("live", broker_kind="tws"), 7496)
        self.assertEqual(expected_broker_port("live", broker_kind="gateway"), 4001)
        self.assertEqual(expected_broker_port("dev", broker_kind="tws"), 7497)

    def test_port_descriptions_are_explicit(self):
        self.assertEqual(describe_broker_port(7497)["label"], "tws_paper")
        self.assertEqual(describe_broker_port(7496)["label"], "tws_live")
        self.assertEqual(describe_broker_port(4002)["label"], "gateway_paper")
        self.assertEqual(describe_broker_port(4001)["label"], "gateway_live")

    def test_config_files_match_profile_semantics(self):
        for profile in ("dev", "paper", "live"):
            cfg = load_profile_config(profile)
            self.assertTrue(broker_port_matches_profile(profile, int(cfg["broker"]["port"])), msg=profile)


class BrokerPreflightTests(unittest.TestCase):
    def test_build_profile_expectation_for_live(self):
        exp = build_broker_profile_expectation("live")
        self.assertEqual(exp.profile_target_mode, "live")
        self.assertEqual(exp.expected_tws_port, 7496)
        self.assertEqual(exp.configured_port, 7496)
        self.assertTrue(exp.port_matches_profile)
        self.assertEqual(exp.warnings, [])

    def test_preflight_without_probe_is_ok_for_paper(self):
        payload = run_broker_preflight(profile="paper", do_probe=False)
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["probe"])
        self.assertEqual(payload["configured"]["port"], 7497)
        self.assertEqual(payload["expected"]["gateway_port"], 4002)

    def test_preflight_with_probe_uses_readonly_probe_result(self):
        probe = IbkrProbeResult(
            ok=True,
            host="127.0.0.1",
            port=7497,
            client_id=7,
            duration_sec=0.321,
            note="OK",
            account="DU123456",
            positions_count=2,
            summary_kv={"NetLiquidation": "25000", "BuyingPower": "50000"},
        )
        with patch("execution.ibkr_preflight.run_f3_t1_probe", return_value=probe) as mocked:
            payload = run_broker_preflight(profile="paper", do_probe=True, timeout_sec=1.5)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["probe"]["port"], 7497)
        self.assertEqual(payload["probe"]["summary_keys"], ["BuyingPower", "NetLiquidation"])
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
