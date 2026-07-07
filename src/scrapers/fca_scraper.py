"""FCA Financial Services Register source builder.

Builds a source-of-truth prospect list from the free FS Register API:
  https://register.fca.org.uk/Developer/s/

Auth: free signup, then two headers — X-AUTH-EMAIL and X-AUTH-KEY.
Rate limit: 10 requests per 10 seconds, so keep request_delay >= 1.0.

The public API only supports name search, not search-by-permission, so this
scraper seeds candidates from configured name search terms, then keeps only
firms whose status is "Authorised" and that hold at least one of the
configured permissions (for example "Advising on regulated mortgage
contracts"). Appointed Representatives hold no permissions of their own and
are therefore excluded by design. For a permission-complete universe the FCA
sells the Register Extract Service; this free path trades recall for cost.
"""

import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd
import requests
from dotenv import load_dotenv

from src.core.data_source import DataSource
from src.core.models import Installer, ScraperConfig
from src.utils.helpers import sanitize_company_name, sanitize_phone_number

load_dotenv()

logger = logging.getLogger("ppl-list-builder")

DEFAULT_BASE_URL = "https://register.fca.org.uk/services/V0.1"
SIGNUP_URL = "https://register.fca.org.uk/Developer/s/"

# Search result names look like "Example Broker Ltd (Postcode: AB1 2CD)".
POSTCODE_SUFFIX = re.compile(r"\s*\(Postcode:[^)]*\)\s*$", re.IGNORECASE)


class FCAScraper(DataSource):
    """Prospect source builder for the FCA Financial Services Register."""

    def __init__(self, config: ScraperConfig):
        super().__init__(config)
        self.api_email = os.getenv("FCA_API_EMAIL")
        self.api_key = os.getenv("FCA_API_KEY")
        self.base_url = (
            config.url.rstrip("/") if config.url.startswith("http") else DEFAULT_BASE_URL
        )
        self.output_path = config.pipeline.source_output
        self.installers: List[Installer] = []
        self.processed_frns: Set[str] = set()
        self.failed_records: List[dict] = []

    def _headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "X-AUTH-EMAIL": self.api_email,
            "X-AUTH-KEY": self.api_key,
        }

    def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """GET a register endpoint with retry and rate-limit handling."""
        url = f"{self.base_url}{path}"
        for attempt in range(self.config.retry_attempts):
            try:
                resp = requests.get(
                    url, params=params, headers=self._headers(), timeout=self.config.timeout
                )
                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    logger.warning(f"Rate limited by FCA register, waiting {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                time.sleep(self.config.request_delay)
                return resp.json()
            except requests.Timeout:
                logger.warning(f"Timeout on {path} (attempt {attempt + 1})")
                time.sleep(2 ** attempt)
            except requests.RequestException as e:
                logger.error(f"FCA register error on {path}: {e}")
                return None
        return None

    def scrape(self) -> List[Installer]:
        """Search the register, filter by status and permissions, save CSV."""
        if not self.api_email or not self.api_key:
            raise RuntimeError(
                "FCA_API_EMAIL and FCA_API_KEY are not set. "
                f"Register for a free API key at {SIGNUP_URL} and add both to .env"
            )

        search_terms = self.config.filters.fca_search_terms or self.config.search_terms
        all_installers: List[Installer] = []

        for term in search_terms:
            logger.info(f"Searching FCA register for: {term}")
            kept = 0
            for hit in self._search_firms(term):
                cap = self.config.filters.fca_max_firms_per_term
                if cap is not None and kept >= cap:
                    logger.info(f"Reached per-term cap of {cap} firms for '{term}'")
                    break
                installer = self._build_installer(hit)
                if installer:
                    self.installers.append(installer)
                    all_installers.append(installer)
                    kept += 1
                    logger.info(f"Scraped: {installer.company_name} (FRN {installer.fca_frn})")
            self._save_to_csv_incremental()

        logger.info(f"Scraping complete. Total firms: {len(all_installers)}")
        if self.failed_records:
            logger.warning(f"Failed records: {len(self.failed_records)}")
        return all_installers

    def _search_firms(self, term: str):
        """Yield authorised firm search hits for one term, across all pages."""
        page = 1
        while True:
            data = self._get("/Search", {"q": term, "type": "firm", "pgnp": page})
            if not data:
                return
            items = data.get("Data") or []
            if not items:
                return
            for item in items:
                frn = str(item.get("Reference Number") or "").strip()
                if not frn or frn in self.processed_frns:
                    continue
                self.processed_frns.add(frn)
                if item.get("Status") != "Authorised":
                    continue
                yield item

            result_info = data.get("ResultInfo") or {}
            try:
                total = int(result_info.get("total_count") or 0)
                per_page = int(result_info.get("per_page") or len(items))
            except (TypeError, ValueError):
                return
            if per_page <= 0 or page * per_page >= total:
                return
            page += 1

    def _build_installer(self, hit: Dict) -> Optional[Installer]:
        """Turn an authorised search hit into an Installer, or None if filtered."""
        frn = str(hit.get("Reference Number"))
        company_name = sanitize_company_name(POSTCODE_SUFFIX.sub("", hit.get("Name") or ""))
        if not company_name:
            return None

        try:
            matched_permissions = self._matched_permissions(frn)
            if matched_permissions is None:
                return None

            companies_house_number = self._companies_house_number(frn)
            website, phone, location = self._principal_address(frn)

            return Installer(
                company_name=company_name,
                website=website,
                phone=phone,
                email=None,
                location=location,
                bus_registered=False,
                mcs_registered=False,
                fca_authorised=True,
                fca_frn=frn,
                fca_companies_house_number=companies_house_number,
                certifications=matched_permissions,
                niche=self.config.niche,
                source_technology=None,
                scraped_at=datetime.now(),
                source="fca",
            )
        except Exception as e:
            logger.debug(f"Error building record for FRN {frn}: {e}")
            self.failed_records.append({"frn": frn, "error": str(e)})
            return None

    def _matched_permissions(self, frn: str) -> Optional[List[str]]:
        """Return the firm's matching permissions, or None if it fails the filter."""
        required = self.config.filters.fca_required_permissions
        data = self._get(f"/Firm/{frn}/Permissions")
        permissions = (data or {}).get("Data")
        if isinstance(permissions, list):
            permissions = permissions[0] if permissions else {}
        if not isinstance(permissions, dict):
            permissions = {}

        if not required:
            return sorted(permissions)

        required_lower = {p.lower() for p in required}
        matched = sorted(p for p in permissions if p.lower() in required_lower)
        return matched or None

    def _companies_house_number(self, frn: str) -> Optional[str]:
        data = self._get(f"/Firm/{frn}")
        items = (data or {}).get("Data") or []
        if not items:
            return None
        number = (items[0].get("Companies House Number") or "").strip()
        return number or None

    def _principal_address(self, frn: str):
        """Return (website, phone, location) from the principal place of business."""
        data = self._get(f"/Firm/{frn}/Address")
        items = (data or {}).get("Data") or []
        if not items:
            return None, None, None
        address = next(
            (a for a in items if "principal" in (a.get("Address Type") or "").lower()),
            items[0],
        )
        website = (address.get("Website Address") or "").strip() or None
        phone = sanitize_phone_number(address.get("Phone Number") or "")
        location_parts = [
            (address.get("Town") or "").strip(),
            (address.get("Postcode") or "").strip(),
        ]
        location = ", ".join(part for part in location_parts if part) or None
        return website, phone, location

    def _save_to_csv_incremental(self) -> None:
        """Append newly scraped firms to the source CSV, mirroring the MCS scraper."""
        if not self.installers:
            logger.debug("No new firms to save")
            return

        try:
            output_dir = Path(self.output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            data = []
            for installer in self.installers:
                data.append({
                    "company_name": installer.company_name,
                    "website": installer.website,
                    "phone": installer.phone,
                    "email": installer.email,
                    "location": installer.location,
                    "bus_registered": installer.bus_registered,
                    "mcs_registered": installer.mcs_registered,
                    "fca_authorised": installer.fca_authorised,
                    "fca_frn": installer.fca_frn,
                    "fca_companies_house_number": installer.fca_companies_house_number,
                    "certifications": str(installer.certifications),
                    "niche": installer.niche,
                    "source_technology": installer.source_technology,
                    "scraped_at": installer.scraped_at.isoformat(),
                    "source": installer.source,
                })

            df = pd.DataFrame(data)
            if not Path(self.output_path).exists():
                df.to_csv(self.output_path, index=False, encoding="utf-8")
                logger.info(f"Created CSV file with {len(df)} firms: {self.output_path}")
            else:
                df.to_csv(self.output_path, mode="a", index=False, header=False, encoding="utf-8")
                logger.info(f"Appended {len(df)} firms to {self.output_path}")

            self.installers = []

        except Exception as e:
            logger.error(f"Error saving to CSV incrementally: {e}", exc_info=True)
