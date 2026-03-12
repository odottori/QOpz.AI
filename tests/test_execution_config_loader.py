import unittest

from execution.config_loader import load_profile_config


class ConfigLoaderTests(unittest.TestCase):
    def test_load_paper_has_broker_defaults(self):
        cfg = load_profile_config("paper")
        self.assertIn("broker", cfg)
        self.assertIn("host", cfg["broker"])
        self.assertIn("port", cfg["broker"])
        # Backward compatible keys: both must exist
        self.assertIn("clientId", cfg["broker"])
        self.assertIn("client_id", cfg["broker"])
        self.assertIsInstance(cfg["broker"]["clientId"], int)
        self.assertIsInstance(cfg["broker"]["client_id"], int)


if __name__ == "__main__":
    unittest.main()
