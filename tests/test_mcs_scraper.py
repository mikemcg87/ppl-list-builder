"""Unit tests for MCS scraper and core functionality."""

import unittest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from src.core.models import Installer, FilterConfig, ScraperConfig
from src.core.config import load_config
from src.core.output import OutputHandler
from src.utils.helpers import (
    sanitize_phone_number, sanitize_company_name, extract_domain_from_url, is_valid_url
)


class TestDataModels(unittest.TestCase):
    """Test Pydantic data models."""

    def test_installer_model(self):
        """Test Installer model creation and validation."""
        installer = Installer(
            company_name="Test Company",
            website="https://test.com",
            phone="01234 567890",
            location="London, UK",
            bus_registered=True,
            certifications=["Air Source", "Ground/Water"]
        )

        self.assertEqual(installer.company_name, "Test Company")
        self.assertEqual(installer.source, "mcs")
        self.assertIsInstance(installer.scraped_at, datetime)
        self.assertTrue(installer.bus_registered)
        self.assertEqual(len(installer.certifications), 2)

    def test_filter_config_model(self):
        """Test FilterConfig model."""
        filters = FilterConfig(
            heat_pump_types=["Air Source", "Ground/Water"],
            location="London"
        )

        self.assertEqual(len(filters.heat_pump_types), 2)
        self.assertEqual(filters.location, "London")

    def test_scraper_config_model(self):
        """Test ScraperConfig model with defaults."""
        filters = FilterConfig(
            heat_pump_types=["Air Source"],
            location=None
        )

        config = ScraperConfig(
            name="mcs",
            url="https://example.com",
            filters=filters
        )

        self.assertEqual(config.name, "mcs")
        self.assertEqual(config.request_delay, 1.5)
        self.assertEqual(config.retry_attempts, 3)
        self.assertTrue(config.headless)


class TestHelperFunctions(unittest.TestCase):
    """Test utility helper functions."""

    def test_sanitize_phone_number(self):
        """Test phone number sanitization."""
        # Valid phone
        result = sanitize_phone_number("01234 567890")
        self.assertEqual(result, "01234567890")

        # With dashes
        result = sanitize_phone_number("01234-567-890")
        self.assertEqual(result, "01234567890")

        # With parentheses
        result = sanitize_phone_number("(01234) 567890")
        self.assertEqual(result, "01234567890")

        # Empty string
        result = sanitize_phone_number("")
        self.assertIsNone(result)

        # No digits
        result = sanitize_phone_number("abc def")
        self.assertIsNone(result)

    def test_sanitize_company_name(self):
        """Test company name sanitization."""
        result = sanitize_company_name("  Test  Company  ")
        self.assertEqual(result, "Test Company")

        result = sanitize_company_name("Test   Company")
        self.assertEqual(result, "Test Company")

    def test_extract_domain_from_url(self):
        """Test domain extraction from URL."""
        result = extract_domain_from_url("https://www.example.com/path")
        self.assertEqual(result, "example.com")

        result = extract_domain_from_url("http://subdomain.example.co.uk")
        self.assertIsNotNone(result)
        self.assertIn("example", result)

        result = extract_domain_from_url("")
        self.assertIsNone(result)

    def test_is_valid_url(self):
        """Test URL validation."""
        self.assertTrue(is_valid_url("https://www.example.com"))
        self.assertTrue(is_valid_url("http://example.com/path"))
        self.assertFalse(is_valid_url("not a url"))
        self.assertFalse(is_valid_url(""))


class TestOutputHandler(unittest.TestCase):
    """Test output handling functionality."""

    def test_output_handler_csv_export(self):
        """Test CSV export with deduplication and sorting."""
        # Create test data
        installer1 = Installer(
            company_name="Alpha Company",
            website="https://alpha.com",
            phone="01234 567890",
            location="London",
            bus_registered=True,
            certifications=["Air Source"]
        )

        installer2 = Installer(
            company_name="Beta Company",
            website="https://beta.com",
            phone="01234 567891",
            location="Manchester",
            bus_registered=False,
            certifications=["Ground/Water"]
        )

        # Duplicate of first installer
        installer3 = Installer(
            company_name="alpha company",  # Different case
            website="https://alpha2.com",
            phone="01234 567892",
            location="Leeds",
            bus_registered=True,
            certifications=["Exhaust Air"]
        )

        data = [installer1, installer2, installer3]

        # Export to temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            output_path = f.name

        try:
            result_path = OutputHandler.to_csv(
                data,
                output_path=output_path,
                sort_by_company=True,
                deduplicate=True
            )

            # Read and verify results
            import pandas as pd
            df = pd.read_csv(result_path)

            # Should have 2 rows (duplicate removed)
            self.assertEqual(len(df), 2)

            # Should be sorted by company name
            self.assertEqual(df.iloc[0]["company_name"], "Alpha Company")
            self.assertEqual(df.iloc[1]["company_name"], "Beta Company")

        finally:
            import os
            if os.path.exists(output_path):
                os.remove(output_path)


class TestConfiguration(unittest.TestCase):
    """Test configuration loading."""

    def test_load_config_from_json(self):
        """Test loading configuration from JSON file."""
        import tempfile
        import json

        config_data = {
            "name": "mcs",
            "url": "https://www.mcscertified.com",
            "filters": {
                "heat_pump_types": ["Air Source"],
                "location": None
            },
            "output_format": "csv",
            "enable_llm_enrichment": False,
            "request_delay": 2.0,
            "retry_attempts": 5,
            "timeout": 30,
            "headless": True
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            self.assertEqual(config.name, "mcs")
            self.assertEqual(config.request_delay, 2.0)
            self.assertEqual(config.retry_attempts, 5)
            self.assertEqual(len(config.filters.heat_pump_types), 1)

        finally:
            import os
            if os.path.exists(config_path):
                os.remove(config_path)

    def test_load_config_file_not_found(self):
        """Test error handling when config file not found."""
        with self.assertRaises(FileNotFoundError):
            load_config("/nonexistent/path/config.json")


if __name__ == "__main__":
    unittest.main()
