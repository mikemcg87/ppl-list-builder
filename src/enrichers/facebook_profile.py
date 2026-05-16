"""Facebook page profile enricher.

For each prospect, looks up their Facebook page, then pulls:
  - public email (great Hunter fallback)
  - listed website (often more accurate than our Brave-derived one)
  - page category, founded date, address
  - follower-context fields where available
  - first recent post (for personalisation)

Two-step: company-name search to get page_id, then profile + posts.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

import requests

from .base_enricher import BaseEnricher

logger = logging.getLogger("ppl-list-builder")

SEARCH_URL = "https://api.scrapecreators.com/v1/facebook/adLibrary/search/companies"
PROFILE_URL = "https://api.scrapecreators.com/v1/facebook/profile"
POSTS_URL = "https://api.scrapecreators.com/v1/facebook/profile/posts"


class FacebookProfileEnricher(BaseEnricher):
    """Adds fb_page_*, fb_public_email, fb_website, fb_recent_post_* columns."""

    def __init__(
        self,
        api_key: str,
        config: Optional[Dict] = None,
        tier_filter: Optional[list[str]] = None,
        with_posts: bool = True,
    ):
        super().__init__(config)
        self.platform_name = "fbprofile"
        self.api_key = api_key
        self.timeout = self.config.get("timeout", 30)
        self.tier_filter = tier_filter
        self.with_posts = with_posts

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key}

    def _find_page(self, company_name: str) -> Optional[str]:
        try:
            r = requests.get(
                SEARCH_URL,
                params={"query": company_name},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return None
            results = r.json().get("searchResults") or []
            if not results:
                return None
            # Take the first match — same heuristic the FB ads enricher uses.
            return results[0].get("page_id")
        except requests.RequestException:
            return None

    def _profile(self, page_id: str) -> Optional[dict]:
        url = f"https://www.facebook.com/{page_id}"
        try:
            r = requests.get(
                PROFILE_URL,
                params={"url": url},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return None
            return r.json()
        except requests.RequestException:
            return None

    def _recent_post(self, page_id: str) -> Optional[dict]:
        try:
            r = requests.get(
                POSTS_URL,
                params={"pageId": page_id},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return None
            posts = (r.json() or {}).get("posts") or (r.json() or {}).get("results") or []
            return posts[0] if posts else None
        except requests.RequestException:
            return None

    def enrich_row(self, row: Dict) -> Dict:
        out = row.copy()

        if self.tier_filter and row.get("tier") not in self.tier_filter:
            return out

        company = (row.get("company_name") or "").strip()
        if not company:
            out["fbprofile_error"] = "missing_company"
            return out

        page_id = self._find_page(company)
        if not page_id:
            out["fbprofile_status"] = "no_match"
            out["fbprofile_enriched_at"] = datetime.now().isoformat()
            return out

        profile = self._profile(page_id) or {}
        out["fbprofile_page_id"] = page_id
        out["fbprofile_status"] = "matched" if profile else "profile_failed"
        out["fb_public_email"] = profile.get("email") or ""
        out["fb_website"] = profile.get("website") or ""
        out["fb_category"] = profile.get("category") or ""
        out["fb_address"] = profile.get("address") or ""
        out["fb_creation_date"] = profile.get("creationDate") or ""
        out["fb_page_url"] = profile.get("url") or ""
        ad_status = (profile.get("adLibrary") or {}).get("adStatus") or ""
        out["fb_page_ad_status"] = ad_status
        intro = profile.get("pageIntro") or ""
        out["fb_page_intro"] = intro[:500]

        if self.with_posts:
            post = self._recent_post(page_id)
            if post:
                out["fb_recent_post_text"] = (post.get("message") or post.get("text") or "")[:300]
                out["fb_recent_post_date"] = post.get("creation_time") or post.get("created_time") or ""

        out["fbprofile_enriched_at"] = datetime.now().isoformat()
        return out
