"""Tests for niche-aware tiering and config defaults."""

import unittest

import pandas as pd

from scripts.build_prospect_tiers import assign_tier, lead_score
from src.core.config import load_config


class TestNicheConfig(unittest.TestCase):
    def test_solar_config_uses_mcs_signal(self):
        config = load_config("config/solar_pv.json")

        row = pd.Series(
            {
                "ch_match_status": "matched",
                "ch_company_status": "active",
                "ch_primary_director": "SMITH, Jane",
                "mcs_registered": True,
                "bus_registered": False,
                "facebook_ads_running": True,
                "facebook_ads_count": 6,
                "google_ads_running": False,
                "domain_confident": False,
                "ch_director_count": 2,
            }
        )

        self.assertEqual(assign_tier(row, config.tiering), "PLATINUM")
        self.assertGreaterEqual(lead_score(row, config.tiering), 90)

    def test_heat_pump_config_still_uses_bus_signal(self):
        config = load_config("config/mcs_config.json")

        row = pd.Series(
            {
                "ch_match_status": "matched",
                "ch_company_status": "active",
                "ch_primary_director": "SMITH, Jane",
                "mcs_registered": True,
                "bus_registered": False,
                "facebook_ads_running": False,
                "google_ads_running": False,
                "domain_confident": False,
                "ch_director_count": 1,
            }
        )

        self.assertEqual(assign_tier(row, config.tiering), "BRONZE")


if __name__ == "__main__":
    unittest.main()
