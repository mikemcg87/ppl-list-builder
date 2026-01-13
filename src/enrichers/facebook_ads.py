"""Facebook Ads Library enricher using ScrapeCreators API."""

from typing import Dict, Optional
import requests
import logging
import time
from datetime import datetime
from urllib.parse import urlparse

from .base_enricher import BaseEnricher

logger = logging.getLogger("ppl-list-builder")


class FacebookAdsEnricher(BaseEnricher):
    """Enriches company data with Facebook Ads Library information."""

    def __init__(self, api_key: str, config: Optional[Dict] = None):
        """
        Initialize Facebook Ads enricher.

        Args:
            api_key: ScrapeCreators API key
            config: Optional configuration dict
        """
        super().__init__(config)
        self.platform_name = "facebook"
        self.api_key = api_key
        self.base_url = "https://api.scrapecreators.com/v1/facebook/adLibrary/"
        self.timeout = self.config.get("timeout", 30)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 1)

    def _extract_domain(self, website_url: Optional[str]) -> Optional[str]:
        """Extract domain from URL."""
        if not website_url:
            return None
        try:
            parsed = urlparse(website_url)
            domain = parsed.netloc or parsed.path
            return domain.split("/")[0] if domain else None
        except Exception:
            return None

    def _get_company_page_id(self, company_name: str) -> Optional[str]:
        """
        Search for company to get its page_id.

        Args:
            company_name: Company name to search

        Returns:
            Page ID or None if not found
        """
        if not company_name or not company_name.strip():
            return None

        url = f"{self.base_url}search/companies"
        params = {"query": company_name}
        headers = {"x-api-key": self.api_key}

        try:
            response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            search_results = data.get("searchResults", [])
            if search_results:
                # Return first result's page_id
                return search_results[0].get("page_id")
            return None

        except requests.RequestException as e:
            logger.debug(f"Error searching for company '{company_name}': {e}")
            return None

    def _search_ads(self, query: str) -> Optional[Dict]:
        """
        Query ScrapeCreators API for company ads using page_id.

        Args:
            query: Company name to search

        Returns:
            API response or None if error
        """
        if not query or not query.strip():
            return None

        # Step 1: Get company page_id
        page_id = self._get_company_page_id(query)
        if not page_id:
            logger.debug(f"Could not find page_id for '{query}'")
            return None

        # Step 2: Get ads for this page_id using company/ads endpoint
        url = f"{self.base_url}company/ads"
        params = {
            "pageId": page_id,
            "limit": 100
        }
        headers = {"x-api-key": self.api_key}

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"API query: {query} (attempt {attempt + 1})")
                response = requests.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )

                if response.status_code == 429:  # Rate limit
                    wait_time = 300
                    logger.warning(
                        f"Rate limited. Waiting {wait_time}s before retry..."
                    )
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response.json()

            except requests.Timeout:
                if attempt < self.max_retries - 1:
                    wait = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Timeout for '{query}'. Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                    continue
                else:
                    logger.error(f"Timeout for '{query}' after {self.max_retries} retries")
                    return None

            except requests.RequestException as e:
                logger.error(f"API error for '{query}': {e}")
                return None

        return None

    def _parse_api_response(self, response: Optional[Dict]) -> Dict:
        """
        Parse API response from company/ads endpoint.

        Args:
            response: API response dict from ScrapeCreators

        Returns:
            Dict with extracted fields
        """
        if not response:
            return {"facebook_ads_running": False}

        # company/ads endpoint returns results array
        ads = response.get("results", [])

        if not ads:
            return {"facebook_ads_running": False}

        # Company is running ads - count them
        ad_count = len(ads)

        # Get details from first ad
        first_ad = ads[0]
        status = "active" if first_ad.get("is_active") else "inactive"
        spend_estimate = first_ad.get("spend_estimate", "")

        return {
            "facebook_ads_running": True,
            "facebook_ads_count": ad_count,
            "facebook_ads_status": status,
            "facebook_ads_page_name": first_ad.get("page_name", ""),
            "facebook_ads_spend_estimate": spend_estimate,
            "facebook_enriched_at": datetime.now().isoformat(),
        }

    def enrich_row(self, row: Dict) -> Dict:
        """
        Enrich a single row with Facebook ads data.

        Args:
            row: Company data dict

        Returns:
            Enriched row dict
        """
        enriched_row = row.copy()

        company_name = row.get("company_name", "").strip()

        if not company_name:
            logger.warning("Skipping row with empty company_name")
            enriched_row["facebook_enrichment_error"] = "Missing company_name"
            return enriched_row

        # Query ScrapeCreators API by company name
        api_response = self._search_ads(company_name)

        # Parse response and add fields
        facebook_data = self._parse_api_response(api_response)
        enriched_row.update(facebook_data)

        return enriched_row
