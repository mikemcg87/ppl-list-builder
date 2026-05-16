"""Google Ads enricher that uses the row's `website` column directly.

Skips the domain-discovery step (SerpApi) since we've already resolved
domains via Brave. Hits ScrapeCreators' /v1/google/company/ads endpoint
with the domain, returns count of currently-active Google ads.
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

from .base_enricher import BaseEnricher

logger = logging.getLogger("ppl-list-builder")

ENDPOINT = "https://api.scrapecreators.com/v1/google/company/ads"


class GoogleAdsDomainEnricher(BaseEnricher):
    """Adds google_ads_running, google_ads_count, google_ads_creative columns
    using the row's existing website. Free of SerpApi dependency."""

    def __init__(
        self,
        api_key: str,
        config: Optional[Dict] = None,
        tier_filter: Optional[str] = None,
    ):
        super().__init__(config)
        self.platform_name = "google"
        self.api_key = api_key
        self.timeout = self.config.get("timeout", 30)
        self.tier_filter = tier_filter

    @staticmethod
    def _domain(website: str) -> Optional[str]:
        if not isinstance(website, str) or not website.strip():
            return None
        s = website.strip()
        if not s.startswith(("http://", "https://")):
            s = "https://" + s
        try:
            host = urlparse(s).netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            return host or None
        except Exception:
            return None

    def _fetch(self, domain: str) -> Optional[Dict]:
        try:
            r = requests.get(
                ENDPOINT,
                params={"domain": domain},
                headers={"x-api-key": self.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            return {"_error": str(e)}
        if r.status_code == 429:
            return {"_error": "rate_limited"}
        if r.status_code >= 400:
            return {"_error": f"http_{r.status_code}", "_body": r.text[:200]}
        try:
            return r.json()
        except ValueError:
            return {"_error": "bad_json"}

    def enrich_row(self, row: Dict) -> Dict:
        out = row.copy()

        if self.tier_filter and row.get("tier") != self.tier_filter:
            return out

        domain = self._domain(row.get("website") or "")
        if not domain:
            out["google_skip_reason"] = "missing_domain"
            return out

        payload = self._fetch(domain)
        out["google_enriched_at"] = datetime.now().isoformat()

        if payload is None or "_error" in payload:
            out["google_error"] = (payload or {}).get("_error", "no_response")
            return out

        ads = payload.get("ads") or payload.get("results") or []
        if not isinstance(ads, list):
            ads = []

        if not ads:
            out["google_ads_running"] = False
            out["google_ads_count"] = 0
            return out

        # Most useful ad-level signal: format mix and a sample creative for
        # personalisation. ScrapeCreators returns various keys depending on ad
        # format — we capture both the count and one example.
        first = ads[0] if ads else {}
        creative = (
            first.get("ad_text")
            or first.get("body")
            or first.get("description")
            or first.get("title")
            or ""
        )
        formats = sorted({(a.get("format") or a.get("type") or "unknown") for a in ads})

        out.update(
            {
                "google_ads_running": True,
                "google_ads_count": len(ads),
                "google_ads_formats": ",".join(str(f) for f in formats),
                "google_ads_first_creative": str(creative)[:300],
            }
        )
        return out
