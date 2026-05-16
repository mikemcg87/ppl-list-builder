"""Companies House enricher — adds UK director/officer data to a company list.

Uses the free Companies House public API:
  https://developer.company-information.service.gov.uk/

Auth: HTTP Basic, API key as username, empty password.
Rate limit: 600 requests per 5 minutes per key.
"""

from typing import Dict, List, Optional
import logging
import re
import time
from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth

from .base_enricher import BaseEnricher

logger = logging.getLogger("ppl-list-builder")

BASE_URL = "https://api.company-information.service.gov.uk"

# Officer roles that imply ownership / decision-making authority.
DECISION_MAKER_ROLES = {
    "director",
    "llp-member",
    "llp-designated-member",
    "managing-officer",
}

# Words that often appear in company suffixes — strip before fuzzy matching.
NAME_NOISE = re.compile(
    r"\b(ltd|limited|llp|plc|uk|the|and|&|company|co|services|"
    r"group|holdings)\b|[^a-z0-9 ]",
    re.IGNORECASE,
)


def _normalise(name: str) -> str:
    return re.sub(r"\s+", " ", NAME_NOISE.sub(" ", name or "")).strip().lower()


class CompaniesHouseEnricher(BaseEnricher):
    """Looks up each company in the UK Companies House register and pulls
    director names, appointment dates, and the company number."""

    def __init__(self, api_key: str, config: Optional[Dict] = None):
        super().__init__(config)
        self.platform_name = "ch"
        self.auth = HTTPBasicAuth(api_key, "")
        self.timeout = self.config.get("timeout", 30)
        self.max_retries = self.config.get("max_retries", 3)
        # Companies House allows 600 req / 5 min = 2 req/s. Leave headroom.
        self.request_delay = self.config.get("request_delay", 0.6)
        self.max_directors = self.config.get("max_directors", 5)

    def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        url = f"{BASE_URL}{path}"
        for attempt in range(self.max_retries):
            try:
                resp = requests.get(
                    url, params=params, auth=self.auth, timeout=self.timeout
                )
                if resp.status_code == 429:
                    wait = 60 * (attempt + 1)
                    logger.warning(f"Rate limited by Companies House, waiting {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                time.sleep(self.request_delay)
                return resp.json()
            except requests.Timeout:
                logger.warning(f"Timeout on {path} (attempt {attempt + 1})")
                time.sleep(2 ** attempt)
            except requests.RequestException as e:
                logger.error(f"Companies House error on {path}: {e}")
                return None
        return None

    def _find_company_number(
        self, company_name: str, postcode: Optional[str] = None
    ) -> Optional[Dict]:
        """Search Companies House and pick the best matching active company."""
        data = self._get("/search/companies", {"q": company_name, "items_per_page": 10})
        if not data:
            return None

        items = data.get("items", [])
        if not items:
            return None

        target = _normalise(company_name)
        scored: List[tuple] = []
        for item in items:
            title = item.get("title", "")
            normalised_title = _normalise(title)
            score = 0
            if normalised_title == target:
                score += 100
            elif target and (target in normalised_title or normalised_title in target):
                score += 50
            if item.get("company_status") == "active":
                score += 20
            if postcode:
                addr = (item.get("address_snippet") or "").lower()
                if postcode.lower().split()[0] in addr:
                    score += 10
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best = scored[0]
        if best_score < 50:
            # Weak match — flag for manual review rather than guess.
            return None
        return best

    def _get_officers(self, company_number: str) -> List[Dict]:
        data = self._get(f"/company/{company_number}/officers", {"items_per_page": 35})
        if not data:
            return []
        officers = []
        for item in data.get("items", []):
            # Skip resigned officers.
            if item.get("resigned_on"):
                continue
            role = (item.get("officer_role") or "").lower()
            if role not in DECISION_MAKER_ROLES:
                continue
            officers.append(
                {
                    "name": item.get("name", ""),
                    "role": role,
                    "appointed_on": item.get("appointed_on", ""),
                    "nationality": item.get("nationality", ""),
                    "occupation": item.get("occupation", ""),
                    "year_of_birth": (item.get("date_of_birth") or {}).get("year"),
                }
            )
        # Most recent appointments first — usually the active leadership.
        officers.sort(key=lambda o: o.get("appointed_on") or "", reverse=True)
        return officers

    def enrich_row(self, row: Dict) -> Dict:
        out = row.copy()
        company_name = (row.get("company_name") or "").strip()
        if not company_name:
            out["ch_enrichment_error"] = "Missing company_name"
            return out

        postcode = None
        location = row.get("location")
        if not isinstance(location, str):
            location = ""
        # crude UK postcode extraction
        m = re.search(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", location.upper())
        if m:
            postcode = m.group(0)

        match = self._find_company_number(company_name, postcode=postcode)
        if not match:
            out.update(
                {
                    "ch_match_status": "no_match",
                    "ch_enriched_at": datetime.now().isoformat(),
                }
            )
            return out

        officers = self._get_officers(match["company_number"])
        top = officers[: self.max_directors]

        out.update(
            {
                "ch_match_status": "matched",
                "ch_company_number": match.get("company_number"),
                "ch_registered_name": match.get("title"),
                "ch_company_status": match.get("company_status"),
                "ch_incorporated_on": match.get("date_of_creation"),
                "ch_address": match.get("address_snippet"),
                "ch_director_count": len(officers),
                "ch_director_names": "; ".join(o["name"] for o in top),
                "ch_director_roles": "; ".join(o["role"] for o in top),
                "ch_director_appointed": "; ".join(o["appointed_on"] or "" for o in top),
                "ch_primary_director": top[0]["name"] if top else "",
                "ch_primary_director_appointed": top[0]["appointed_on"] if top else "",
                "ch_enriched_at": datetime.now().isoformat(),
            }
        )
        return out
