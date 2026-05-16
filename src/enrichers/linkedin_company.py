"""LinkedIn company page enricher.

Two-step: Brave search to discover the LinkedIn URL, ScrapeCreators to fetch
the page details (employee count, headquarters, follower count, founded year).
"""

import logging
import os
import re
from datetime import datetime
from typing import Dict, Optional

import requests

from .base_enricher import BaseEnricher

logger = logging.getLogger("ppl-list-builder")

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
SC_URL = "https://api.scrapecreators.com/v1/linkedin/company"

LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/[a-zA-Z0-9\-_/.]+", re.IGNORECASE)


class LinkedinCompanyEnricher(BaseEnricher):
    """Adds linkedin_url, linkedin_employees, linkedin_followers, linkedin_hq."""

    def __init__(
        self,
        api_key: str,
        brave_key: str,
        config: Optional[Dict] = None,
        tier_filter: Optional[list[str]] = None,
    ):
        super().__init__(config)
        self.platform_name = "linkedin"
        self.api_key = api_key
        self.brave_key = brave_key
        self.timeout = self.config.get("timeout", 30)
        self.tier_filter = tier_filter

    def _find_linkedin_url(self, company_name: str, location: str = "") -> Optional[str]:
        # No quotes — Brave's exact-phrase operator is too restrictive for many
        # multi-word company names and misses real /company/ pages.
        query = f"{company_name} linkedin company"
        if location:
            query += f" {location}"
        try:
            r = requests.get(
                BRAVE_URL,
                params={"q": query, "country": "GB", "count": 10},
                headers={
                    "X-Subscription-Token": self.brave_key,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                },
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return None
            web = (r.json() or {}).get("web") or {}
            personal_url = ""
            for item in web.get("results") or []:
                url = item.get("url") or ""
                # Prefer company pages
                if "/company/" in url.lower():
                    m = LINKEDIN_RE.search(url)
                    if m:
                        return m.group(0).rstrip("/")
                # Capture personal /in/ as fallback for the director
                if "/in/" in url.lower() and not personal_url:
                    personal_url = url.rstrip("/")
            return personal_url or None
        except requests.RequestException:
            return None

    def _fetch(self, linkedin_url: str) -> Optional[dict]:
        try:
            r = requests.get(
                SC_URL,
                params={"url": linkedin_url},
                headers={"x-api-key": self.api_key},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return None
            return r.json()
        except requests.RequestException:
            return None

    def enrich_row(self, row: Dict) -> Dict:
        out = row.copy()

        if self.tier_filter and row.get("tier") not in self.tier_filter:
            return out

        company = (row.get("company_name") or "").strip()
        if not company:
            out["linkedin_error"] = "missing_company"
            return out

        loc = row.get("location") if isinstance(row.get("location"), str) else ""
        url = self._find_linkedin_url(company, loc)
        if not url:
            out["linkedin_status"] = "no_url_found"
            out["linkedin_enriched_at"] = datetime.now().isoformat()
            return out

        out["linkedin_url"] = url

        # If we only found a /in/ personal URL, store that and skip the
        # company-page fetch (different endpoint, different shape).
        if "/company/" not in url:
            out["linkedin_status"] = "personal_url_only"
            out["linkedin_director_profile"] = url
            out["linkedin_enriched_at"] = datetime.now().isoformat()
            return out

        data = self._fetch(url)
        if not data:
            out["linkedin_status"] = "fetch_failed"
            out["linkedin_enriched_at"] = datetime.now().isoformat()
            return out

        # ScrapeCreators returns a varying shape — handle both top-level and `data` nested.
        d = data.get("data") if isinstance(data.get("data"), dict) else data

        out["linkedin_status"] = "matched"
        out["linkedin_followers"] = d.get("followers") or d.get("follower_count") or ""

        # `employees` is sometimes a count, sometimes a list of profile cards.
        emp_field = (
            d.get("employees")
            or d.get("staff_count")
            or d.get("employee_count")
            or d.get("employeeCount")
        )
        emp_count = ""
        emp_sample = []
        if isinstance(emp_field, list):
            emp_count = len(emp_field)
            emp_sample = [e.get("name", "") for e in emp_field[:5] if isinstance(e, dict)]
        elif isinstance(emp_field, (int, float, str)):
            emp_count = emp_field

        out["linkedin_employees"] = str(emp_count) if emp_count != "" else ""
        out["linkedin_employee_sample"] = "; ".join(emp_sample)
        out["linkedin_employees_range"] = d.get("staff_count_range") or d.get("employees_range") or ""
        out["linkedin_industry"] = d.get("industry") or ""
        out["linkedin_hq"] = (
            d.get("headquarters")
            or (d.get("hq") if isinstance(d.get("hq"), str) else "")
            or ""
        )
        out["linkedin_founded"] = d.get("founded") or d.get("founded_on") or ""
        out["linkedin_specialties"] = ", ".join(d.get("specialties", [])) if isinstance(d.get("specialties"), list) else ""
        out["linkedin_about"] = (d.get("about") or d.get("description") or "")[:500]
        out["linkedin_website"] = d.get("website") or ""

        # If any employee card has the same first+last as the director, capture
        # their personal LinkedIn URL — gold for outreach.
        director_first = (row.get("director_first_name") or "").lower().strip()
        director_last = (row.get("director_last_name") or "").lower().strip()
        if director_first and director_last and isinstance(emp_field, list):
            for emp in emp_field:
                if not isinstance(emp, dict):
                    continue
                name = (emp.get("name") or "").lower()
                if director_first in name and director_last in name:
                    out["linkedin_director_profile"] = emp.get("link") or ""
                    break

        out["linkedin_enriched_at"] = datetime.now().isoformat()
        return out
