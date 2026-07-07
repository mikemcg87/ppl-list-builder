"""Unit tests for the FCA register source builder.

All FCA API traffic is mocked with synthetic fixtures; no live calls.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from src.core.models import FilterConfig, PipelineConfig, ScraperConfig
from src.scrapers.fca_scraper import FCAScraper

FAKE_CREDS = {"FCA_API_EMAIL": "dev@example.com", "FCA_API_KEY": "test-key"}

SEARCH_PAGE = {
    "Status": "FSR-API-04-01-00",
    "Message": "Ok. Search successful",
    "ResultInfo": {"page": "1", "per_page": "20", "total_count": "3"},
    "Data": [
        {
            "URL": "https://register.fca.org.uk/services/V0.1/Firm/111111",
            "Status": "Authorised",
            "Reference Number": "111111",
            "Type of business or Individual": "Firm",
            "Name": "Alpha Mortgage Brokers Ltd (Postcode: AB1 2CD)",
        },
        {
            "URL": "https://register.fca.org.uk/services/V0.1/Firm/222222",
            "Status": "Authorised",
            "Reference Number": "222222",
            "Type of business or Individual": "Firm",
            "Name": "Beta Insurance Services Ltd (Postcode: ZZ9 9ZZ)",
        },
        {
            "URL": "https://register.fca.org.uk/services/V0.1/Firm/333333",
            "Status": "No longer authorised",
            "Reference Number": "333333",
            "Type of business or Individual": "Firm",
            "Name": "Gone Mortgages Ltd (Postcode: CD3 4EF)",
        },
    ],
}

PERMISSIONS = {
    "111111": {
        "Data": [
            {
                "Advising on regulated mortgage contracts": [
                    {"Customer Type": ["All"], "Limitation": ["Valid limitation"]}
                ],
                "Arranging (bringing about) regulated mortgage contracts": [
                    {"Customer Type": ["All"], "Limitation": []}
                ],
                "Agreeing to carry on a regulated activity": [
                    {"Customer Type": [], "Limitation": []}
                ],
            }
        ]
    },
    "222222": {
        "Data": [
            {
                "Insurance distribution": [
                    {"Customer Type": ["All"], "Limitation": []}
                ]
            }
        ]
    },
}

FIRM_DETAILS = {
    "111111": {
        "Data": [
            {
                "Organisation Name": "ALPHA MORTGAGE BROKERS LTD",
                "Status": "Authorised",
                "Companies House Number": "01234567",
            }
        ]
    }
}

ADDRESSES = {
    "111111": {
        "Data": [
            {
                "Address Type": "Principal Place of Business",
                "Website Address": "https://alphamortgages.example.com",
                "Phone Number": "+44 1234 567890",
                "Address Line 1": "1 High Street",
                "Town": "Belfast",
                "Postcode": "AB1 2CD",
            }
        ]
    }
}

EMPTY_PAGE = {
    "Status": "FSR-API-04-01-11",
    "Message": "No search result found",
    "ResultInfo": {"page": "1", "per_page": "20", "total_count": "0"},
    "Data": [],
}


def _json_response(payload):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _fake_get(url, params=None, headers=None, timeout=None):
    """Route mocked HTTP calls to the synthetic fixtures above."""
    params = params or {}
    if url.endswith("/Search"):
        if params.get("q") in ("mortgage", "mortgage broker") and params.get("pgnp") == 1:
            return _json_response(SEARCH_PAGE)
        return _json_response(EMPTY_PAGE)
    for frn, payload in PERMISSIONS.items():
        if url.endswith(f"/Firm/{frn}/Permissions"):
            return _json_response(payload)
    for frn, payload in ADDRESSES.items():
        if url.endswith(f"/Firm/{frn}/Address"):
            return _json_response(payload)
    for frn, payload in FIRM_DETAILS.items():
        if url.endswith(f"/Firm/{frn}"):
            return _json_response(payload)
    raise AssertionError(f"Unexpected FCA API call in test: {url}")


def _make_config(output_path, search_terms=None):
    return ScraperConfig(
        name="fca",
        niche="mortgage_brokers",
        display_name="Mortgage Brokers",
        url="https://register.fca.org.uk/services/V0.1",
        filters=FilterConfig(
            fca_search_terms=search_terms or ["mortgage"],
            fca_required_permissions=[
                "Advising on regulated mortgage contracts",
                "Arranging (bringing about) regulated mortgage contracts",
            ],
        ),
        pipeline=PipelineConfig(source_output=output_path),
        request_delay=0,
    )


class TestFCAScraper(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.output_path = str(Path(self.tmp_dir.name) / "mortgage-brokers.csv")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_missing_credentials_raises_clear_error(self):
        with patch.dict(os.environ, {"FCA_API_EMAIL": "", "FCA_API_KEY": ""}):
            scraper = FCAScraper(_make_config(self.output_path))
        with self.assertRaises(RuntimeError) as ctx:
            scraper.scrape()
        self.assertIn("FCA_API_EMAIL", str(ctx.exception))
        self.assertIn("register.fca.org.uk/Developer", str(ctx.exception))

    @patch("src.scrapers.fca_scraper.requests.get", side_effect=_fake_get)
    def test_scrape_filters_by_status_and_permissions(self, mock_get):
        with patch.dict(os.environ, FAKE_CREDS):
            scraper = FCAScraper(_make_config(self.output_path))
            installers = scraper.scrape()

        self.assertEqual(len(installers), 1)
        firm = installers[0]
        self.assertEqual(firm.company_name, "Alpha Mortgage Brokers Ltd")
        self.assertEqual(firm.fca_frn, "111111")
        self.assertTrue(firm.fca_authorised)
        self.assertFalse(firm.bus_registered)
        self.assertFalse(firm.mcs_registered)
        self.assertEqual(firm.fca_companies_house_number, "01234567")
        self.assertEqual(firm.website, "https://alphamortgages.example.com")
        self.assertEqual(firm.phone, "+441234567890")
        self.assertEqual(firm.location, "Belfast, AB1 2CD")
        self.assertEqual(firm.niche, "mortgage_brokers")
        self.assertEqual(firm.source, "fca")
        self.assertEqual(
            firm.certifications,
            [
                "Advising on regulated mortgage contracts",
                "Arranging (bringing about) regulated mortgage contracts",
            ],
        )

        called_urls = [call.args[0] for call in mock_get.call_args_list]
        # Beta fails the permission filter but must be checked.
        self.assertTrue(any(u.endswith("/Firm/222222/Permissions") for u in called_urls))
        # A "No longer authorised" firm must not trigger any detail lookups.
        self.assertFalse(any("/Firm/333333" in u for u in called_urls))
        # Non-matching firms must not spend detail or address calls.
        self.assertFalse(any(u.endswith("/Firm/222222") for u in called_urls))
        self.assertFalse(any(u.endswith("/Firm/222222/Address") for u in called_urls))

    @patch("src.scrapers.fca_scraper.requests.get", side_effect=_fake_get)
    def test_scrape_writes_source_csv(self, mock_get):
        with patch.dict(os.environ, FAKE_CREDS):
            FCAScraper(_make_config(self.output_path)).scrape()

        df = pd.read_csv(self.output_path)
        self.assertEqual(len(df), 1)
        expected_columns = {
            "company_name", "website", "phone", "email", "location",
            "bus_registered", "mcs_registered", "fca_authorised", "fca_frn",
            "fca_companies_house_number", "certifications", "niche",
            "source_technology", "scraped_at", "source",
        }
        self.assertTrue(expected_columns.issubset(df.columns))
        self.assertEqual(df.iloc[0]["company_name"], "Alpha Mortgage Brokers Ltd")
        self.assertTrue(bool(df.iloc[0]["fca_authorised"]))

    @patch("src.scrapers.fca_scraper.requests.get", side_effect=_fake_get)
    def test_deduplicates_firms_across_search_terms(self, mock_get):
        config = _make_config(self.output_path, search_terms=["mortgage", "mortgage broker"])
        with patch.dict(os.environ, FAKE_CREDS):
            installers = FCAScraper(config).scrape()

        self.assertEqual(len(installers), 1)
        permission_calls = [
            call.args[0]
            for call in mock_get.call_args_list
            if call.args[0].endswith("/Firm/111111/Permissions")
        ]
        self.assertEqual(len(permission_calls), 1)

    @patch("src.scrapers.fca_scraper.requests.get", side_effect=_fake_get)
    def test_per_term_cap_limits_detail_lookups(self, mock_get):
        config = _make_config(self.output_path)
        config.filters.fca_max_firms_per_term = 0
        with patch.dict(os.environ, FAKE_CREDS):
            installers = FCAScraper(config).scrape()

        self.assertEqual(installers, [])
        called_urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertFalse(any("/Permissions" in u for u in called_urls))


class TestFCAPagination(unittest.TestCase):
    def _paged_get(self, url, params=None, headers=None, timeout=None):
        params = params or {}
        pages = {
            1: {
                "ResultInfo": {"page": "1", "per_page": "1", "total_count": "2"},
                "Data": [SEARCH_PAGE["Data"][0]],
            },
            2: {
                "ResultInfo": {"page": "2", "per_page": "1", "total_count": "2"},
                "Data": [SEARCH_PAGE["Data"][1]],
            },
        }
        if url.endswith("/Search"):
            return _json_response(pages[params["pgnp"]])
        return _fake_get(url, params=params, headers=headers, timeout=timeout)

    def test_search_walks_all_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(str(Path(tmp) / "out.csv"))
            with patch.dict(os.environ, FAKE_CREDS):
                scraper = FCAScraper(config)
                with patch(
                    "src.scrapers.fca_scraper.requests.get", side_effect=self._paged_get
                ) as mock_get:
                    installers = scraper.scrape()

        self.assertEqual(len(installers), 1)
        search_pages = [
            call.kwargs.get("params", {}).get("pgnp")
            for call in mock_get.call_args_list
            if call.args[0].endswith("/Search")
        ]
        self.assertEqual(search_pages, [1, 2])


if __name__ == "__main__":
    unittest.main()
