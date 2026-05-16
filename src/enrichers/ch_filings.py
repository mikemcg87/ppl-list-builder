"""Companies House filing-history enricher.

Pulls recent filings for each prospect (using their existing ch_company_number)
and surfaces signals that aren't on the main company endpoint:
  - last accounts filed date
  - accounts type (micro / small / abbreviated — proxy for size)
  - recent appointments / resignations (instability signal)
  - last confirmation statement (annual filing — confirms still active)

Free, requires the same API key as the existing CompaniesHouseEnricher.
"""

import logging
import time
from datetime import datetime
from typing import Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

from .base_enricher import BaseEnricher

logger = logging.getLogger("ppl-list-builder")

BASE_URL = "https://api.company-information.service.gov.uk"


class CompaniesHouseFilingsEnricher(BaseEnricher):
    """Adds ch_last_accounts, ch_accounts_type, ch_recent_appointments,
    ch_recent_resignations, ch_last_confirmation columns."""

    def __init__(
        self,
        api_key: str,
        config: Optional[Dict] = None,
        tier_filter: Optional[list[str]] = None,
    ):
        super().__init__(config)
        self.platform_name = "chfilings"
        self.auth = HTTPBasicAuth(api_key, "")
        self.timeout = self.config.get("timeout", 30)
        self.request_delay = self.config.get("request_delay", 0.6)
        self.tier_filter = tier_filter

    def _get(self, path: str) -> Optional[dict]:
        for attempt in range(3):
            try:
                r = requests.get(
                    BASE_URL + path,
                    auth=self.auth,
                    timeout=self.timeout,
                )
                if r.status_code == 429:
                    time.sleep(60 * (attempt + 1))
                    continue
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                time.sleep(self.request_delay)
                return r.json()
            except requests.RequestException:
                time.sleep(2 ** attempt)
        return None

    def enrich_row(self, row: Dict) -> Dict:
        out = row.copy()

        if self.tier_filter and row.get("tier") not in self.tier_filter:
            return out

        cn = row.get("ch_company_number")
        if not isinstance(cn, str) or not cn.strip():
            try:
                cn_num = float(cn)
                cn = str(int(cn_num)).zfill(8)
            except (TypeError, ValueError):
                out["chfilings_error"] = "missing_company_number"
                return out

        cn = cn.strip()

        data = self._get(f"/company/{cn}/filing-history?items_per_page=50")
        if not data:
            out["chfilings_status"] = "no_data"
            out["chfilings_enriched_at"] = datetime.now().isoformat()
            return out

        items = data.get("items") or []
        out["chfilings_status"] = "matched"
        out["ch_total_filings"] = len(items)

        # Find last accounts and last confirmation statement.
        last_accounts_date = ""
        accounts_type = ""
        last_confirmation = ""
        appointments = 0
        resignations = 0
        for item in items:
            cat = (item.get("category") or "").lower()
            desc = (item.get("description") or "").lower()
            date = item.get("date") or ""
            if cat == "accounts" and not last_accounts_date:
                last_accounts_date = date
                # Description tells us the size band: e.g. 'accounts-with-accounts-type-micro'
                accounts_type = item.get("description") or ""
            if cat == "confirmation-statement" and not last_confirmation:
                last_confirmation = date
            if cat == "officers":
                if "appointment" in desc:
                    appointments += 1
                elif "resignation" in desc or "termination" in desc:
                    resignations += 1

        out["ch_last_accounts"] = last_accounts_date
        out["ch_accounts_type"] = accounts_type
        out["ch_last_confirmation"] = last_confirmation
        out["ch_recent_appointments"] = appointments
        out["ch_recent_resignations"] = resignations
        out["chfilings_enriched_at"] = datetime.now().isoformat()
        return out
