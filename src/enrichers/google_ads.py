"""Google Ads enricher using SerpApi."""

import re
import os # Added for env var access
from typing import Dict, Optional
import requests
import logging
import time
from datetime import datetime
import sys
from pathlib import Path
import pandas as pd

# Ensure we can import from src.utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.utils.helpers import extract_domain_from_url # Ensure this import is present
from .base_enricher import BaseEnricher

logger = logging.getLogger("ppl-list-builder")


class GoogleAdsEnricher(BaseEnricher):
    """Enriches company data with Google Ads information via ScrapeCreators (Unofficial API)."""

    def __init__(self, api_key: str, config: Optional[Dict] = None):
        """
        Initialize Google Ads enricher.

        Args:
            api_key: ScrapeCreators API key
            config: Optional configuration dict
        """
        super().__init__(config)
        self.platform_name = "google"
        self.api_key = api_key
        self.base_url = "https://api.scrapecreators.com/v1/google/company/ads" # Placeholder/generic endpoint
        # Note: Documentation search found multiple potential endpoints.
        # ScrapeCreators likely mimics the structure of Facebook or uses a specific endpoint.
        # Assuming standard structure: /v1/googleAdTransparency/search or similar.
        
        # Based on search results: "https://docs.scrapecreators.com/v1/google/company/ads"
        # Let's try the company/ads endpoint directly with domain or text.
        
        self.timeout = self.config.get("timeout", 60)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 1)

    def _clean_company_name(self, name: str) -> str:
        # Re-enable cleaning logic
        if not name:
            return ""
        clean = re.sub(r'\s+(?:ltd|limited|plc|llp|inc|incorporated)\.?$', '', name, flags=re.IGNORECASE)
        return clean.strip()

    def _get_company_domain_serpapi(self, company_name: str) -> Optional[str]:
        """
        Use SerpApi Google Search to find the official website of the company.
        """
        url = "https://serpapi.com/search"
        params = {
            "engine": "google",
            "q": f"{company_name} official site",
            "gl": "uk",
            "api_key": os.getenv("SERPAPI_API_KEY") # We need to access this key now
        }
        
        if not params["api_key"]:
            logger.warning("No SerpApi key available for domain lookup.")
            return None
            
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                organic = data.get("organic_results", [])
                if organic:
                    # Get the link of the first organic result
                    link = organic[0].get("link")
                    # Extract domain
                    domain = extract_domain_from_url(link)
                    return domain
            return None
        except Exception as e:
            logger.debug(f"Error searching domain for '{company_name}': {e}")
            return None

    def _search_ads(self, query: str) -> Optional[Dict]:
        """
        Query ScrapeCreators for company ads using Domain (Hybrid Approach).
        """
        if not query or not query.strip():
            return None

        # Strategy 3: Hybrid Approach
        # 1. Find domain using SerpApi (Google Search) - extremely reliable
        # 2. Query ScrapeCreators using that domain - should be reliable if they support domain lookup
        
        # Use the original query (company name) to find the domain
        domain = self._get_company_domain_serpapi(query)
        
        if not domain:
            logger.info(f"Could not find domain for '{query}' via SerpApi")
            return None
            
        logger.info(f"Found domain for '{query}': {domain}")
        
        # Step 2: Get ads using Domain
        url = "https://api.scrapecreators.com/v1/google/company/ads"
        
        params = {
            "domain": domain,
            "limit": 100
        }
        headers = {"x-api-key": self.api_key}

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"API query: {domain} (attempt {attempt + 1})")
                response = requests.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )

                if response.status_code == 429:
                    time.sleep(5)
                    continue

                if response.status_code != 200:
                    logger.error(f"ScrapeCreators Error: {response.status_code} - {response.text}")
                    return None

                return response.json()

            except Exception as e:
                logger.error(f"API error for '{domain}': {e}")
                return None

        return None

    def _parse_api_response(self, response: Optional[Dict]) -> Dict:
        if not response:
            return {"google_ads_running": False}

        # Assuming structure: { "results": [ ... ] } or "ads": [...]
        ads = response.get("results", []) or response.get("ads", [])

        if not ads:
            return {"google_ads_running": False}

        ad_count = len(ads)
        first_ad = ads[0]
        
        # Extract fields (keys might vary, will need to inspect response)
        advertiser_name = first_ad.get("advertiserName", "") or first_ad.get("title", "")
        ad_body = first_ad.get("body", "") or first_ad.get("description", "")

        return {
            "google_ads_running": True,
            "google_ads_count": ad_count,
            "google_ads_status": "active",
            "google_ads_advertiser_name": advertiser_name,
            "google_ads_body": ad_body,
            "google_enriched_at": datetime.now().isoformat(),
        }

    def enrich_row(self, row: Dict) -> Dict:
        """
        Enrich a single row with Google ads data.

        Args:
            row: Company data dict

        Returns:
            Enriched row dict
        """
        enriched_row = row.copy()

        company_name = row.get("company_name", "")
        if pd.isna(company_name):
             company_name = ""
        else:
             company_name = str(company_name).strip()

        if not company_name:
            logger.warning("Skipping row with empty company_name")
            enriched_row["google_enrichment_error"] = "Missing company_name"
            return enriched_row

        # Query SerpApi by company name
        # We use cleaned company name to improve match rate
        clean_name = self._clean_company_name(company_name)
        
        # Fallback: If cleaned name yields no results, and it's short (likely generic), 
        # or if it's very different from original, we might want to try variations.
        # For now, let's just search the cleaned name.
        
        # ADDED: Log the query we are about to make to confirm it looks right
        logger.info(f"Searching Google Ads for: '{clean_name}'")
        
        api_response = self._search_ads(clean_name)
        
        # If clean name failed but was different from original, maybe try original? 
        # (Optional optimization, but let's stick to clean name for now as it's likely better)

        # Parse response and add fields
        google_data = self._parse_api_response(api_response)
        enriched_row.update(google_data)

        return enriched_row
