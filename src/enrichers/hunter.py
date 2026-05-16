"""Hunter.io Email Finder enricher.

Finds the most likely email for a named person at a given domain.
Caches every API response to disk so re-runs never re-spend credits.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

from .base_enricher import BaseEnricher

logger = logging.getLogger("ppl-list-builder")

ENDPOINT = "https://api.hunter.io/v2/email-finder"


class HunterEnricher(BaseEnricher):
    """Adds hunter_email, confidence, verification_status, position to each row.

    Skips rows missing first_name, last_name, or website. Skips rows with
    a tier filter set if the row's tier doesn't match. Reads from a local
    JSON cache before hitting the API.
    """

    def __init__(
        self,
        api_key: str,
        config: Optional[Dict] = None,
        cache_path: str = "output/.hunter_cache.json",
        tier_filter: Optional[str] = None,
    ):
        super().__init__(config)
        self.platform_name = "hunter"
        self.api_key = api_key
        self.timeout = self.config.get("timeout", 30)
        self.tier_filter = tier_filter
        self.cache_path = Path(cache_path)
        self.cache: Dict[str, Dict] = {}
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text())
            except json.JSONDecodeError:
                logger.warning(f"Could not parse {self.cache_path}, starting fresh")

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=2))

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

    def _cache_key(self, domain: str, first: str, last: str) -> str:
        return f"{domain}|{first.lower()}|{last.lower()}"

    def _call_api(self, domain: str, first: str, last: str) -> Dict:
        params = {
            "domain": domain,
            "first_name": first,
            "last_name": last,
            "api_key": self.api_key,
        }
        try:
            r = requests.get(ENDPOINT, params=params, timeout=self.timeout)
        except requests.RequestException as e:
            return {"_error": str(e)}

        if r.status_code == 429:
            return {"_error": "rate_limited", "_status": 429}
        if r.status_code == 401 or r.status_code == 403:
            return {"_error": "auth_failed", "_status": r.status_code}
        if r.status_code == 451:
            return {"_error": "claims_required", "_status": 451}

        try:
            payload = r.json()
        except ValueError:
            return {"_error": "bad_json", "_status": r.status_code}

        if r.status_code >= 400:
            errors = payload.get("errors", [])
            msg = errors[0].get("details") if errors else f"http_{r.status_code}"
            return {"_error": msg, "_status": r.status_code}

        return payload

    def enrich_row(self, row: Dict) -> Dict:
        out = row.copy()

        if self.tier_filter and row.get("tier") != self.tier_filter:
            return out

        first = (row.get("director_first_name") or "").strip()
        last = (row.get("director_last_name") or "").strip()
        if not first or not last:
            out["hunter_skip_reason"] = "missing_director_name"
            return out

        domain = self._domain(row.get("website") or "")
        if not domain:
            out["hunter_skip_reason"] = "missing_domain"
            return out

        key = self._cache_key(domain, first, last)
        if key in self.cache:
            payload = self.cache[key]
            cached = True
        else:
            payload = self._call_api(domain, first, last)
            self.cache[key] = payload
            self._save_cache()
            cached = False

        out["hunter_cached"] = cached
        out["hunter_enriched_at"] = datetime.now().isoformat()

        if "_error" in payload:
            out["hunter_error"] = payload["_error"]
            return out

        data = payload.get("data") or {}
        out["hunter_email"] = data.get("email") or ""
        out["hunter_score"] = data.get("score")
        out["hunter_position"] = data.get("position") or ""
        out["hunter_seniority"] = data.get("seniority") or ""
        out["hunter_verification_status"] = (data.get("verification") or {}).get("status") or ""
        out["hunter_company"] = data.get("company") or ""
        out["hunter_linkedin"] = data.get("linkedin_url") or ""

        # Hunter's "meta" includes credit usage — useful to log.
        meta = payload.get("meta") or {}
        if "results" in meta and not cached:
            logger.debug(f"Hunter results: {meta.get('results')} for {domain}")

        return out
