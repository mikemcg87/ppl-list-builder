#!/usr/bin/env python3
"""Find a company's website domain by searching Brave or SerpApi.

Designed for the small PLATINUM tier, not for the full list. Brave is the
default because SerpApi is rate-constrained in this project.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import pandas as pd
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.core.config import load_config

load_dotenv()

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# Domains to ignore — directories, social, generic listings.
BLOCKLIST = {
    "facebook.com",
    "linkedin.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "checkatrade.com",
    "trustatrader.com",
    "trustpilot.com",
    "yell.com",
    "google.com",
    "google.co.uk",
    "bing.com",
    "duckduckgo.com",
    "wikipedia.org",
    "mcscertified.com",
    "find-and-update.company-information.service.gov.uk",
    "endole.co.uk",
    "companieshouse.gov.uk",
    "ukcompanieslist.co.uk",
    "opencorporates.com",
    "rocketreape.com",
    "rocketreach.co",
    "apollo.io",
    "zoominfo.com",
    "indeed.com",
    "glassdoor.com",
    "amazon.co.uk",
    "thomsonlocal.com",
    "192.com",
    "trustmark.org.uk",
    "mybuilder.com",
    "rated-people.com",
    "ratedpeople.com",
    "cylex-uk.co.uk",
    "scoot.co.uk",
    "freeindex.co.uk",
    "tuugo.co.uk",
    "uk.kompass.com",
    "kompass.com",
    "uk-business-directory.com",
    "bizdb.co.uk",
    "yelp.co.uk",
    "yelp.com",
    "tripadvisor.co.uk",
    "wales.com",
    "gov.uk",
    "service.gov.uk",
    "ukhomeenergy.co.uk",
    "oilcompare.co.uk",
    "houzz.co.uk",
    "houzz.com",
    "houzz.co",
    "daikin.co.uk",
    "daikin.com",
    "vaillant.co.uk",
    "mitsubishielectric.co.uk",
    "samsung.com",
    "lg.com",
    "worcester-bosch.co.uk",
    "octopusenergy.com",
    "recc.org.uk",
    "theiaa.co.uk",
    "findcertifiedinstallers.co.uk",
    "trustamark.org.uk",
    "which.co.uk",
}


def _share_token(company_name: str, domain: str) -> bool:
    """Cheap relevance check: does the domain contain a meaningful word from the company?"""
    stop = {"ltd", "limited", "the", "and", "uk", "group", "services", "co", "company"}
    words = re.findall(r"[A-Za-z]{3,}", company_name.lower())
    words = [w for w in words if w not in stop]
    domain_main = domain.split(".")[0].lower()
    return any(w in domain_main or domain_main in w for w in words)


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _unwrap_ddg(href: str) -> str:
    """DuckDuckGo wraps results in /l/?uddg=<encoded>."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.path == "/l/" or parsed.netloc.endswith("duckduckgo.com"):
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return href


def _slugify(name: str) -> str:
    s = re.sub(r"\b(ltd|limited|llp|plc|the|and|&)\b", " ", name, flags=re.IGNORECASE)
    s = re.sub(r"[^a-z0-9]+", "", s.lower())
    return s


def _slug_variants(name: str) -> list[str]:
    """Generate plausible domain slugs from a company name."""
    raw = re.sub(r"\b(ltd|limited|llp|plc|the)\b", " ", name, flags=re.IGNORECASE)
    raw = re.sub(r"[^a-zA-Z0-9 ]+", " ", raw).strip()
    words = [w for w in raw.split() if w]
    if not words:
        return []
    joined = "".join(w.lower() for w in words)
    hyphen = "-".join(w.lower() for w in words)
    variants = {joined, hyphen}
    if len(words) >= 2:
        # initials + last word, e.g. "P M Norman" -> "pmnorman"
        initials = "".join(w[0] for w in words[:-1]).lower() + words[-1].lower()
        variants.add(initials)
    return [v for v in variants if 3 <= len(v) <= 40]


def _check_domain(domain: str) -> bool:
    """Return True if domain resolves to a real, branded site (not a parking page)."""
    for scheme in ("https://", "http://"):
        try:
            r = requests.get(
                scheme + domain,
                headers={"User-Agent": UA},
                timeout=10,
                allow_redirects=True,
            )
            if r.status_code >= 400:
                continue
            text = r.text.lower()
            # Common parking / for-sale signals
            parked = (
                "domain is for sale" in text
                or "buy this domain" in text
                or "sedoparking" in text
                or "godaddy.com/domains" in text
                or "this domain may be for sale" in text
            )
            if parked:
                continue
            return True
        except requests.RequestException:
            continue
    return False


def _guess_domain(company_name: str) -> str | None:
    suffixes = (".co.uk", ".com", ".uk", ".ltd.uk")
    for slug in _slug_variants(company_name):
        for suffix in suffixes:
            domain = slug + suffix
            if _check_domain(domain):
                return domain
    return None


def _bing_search(query: str) -> list[str]:
    try:
        r = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "count": 15},
            headers={"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"},
            timeout=20,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! bing failed: {e}")
        return []
    # Bing result anchors live inside <h2><a href="...">
    return re.findall(r'<h2><a[^>]+href="([^"]+)"', r.text)


def _ddg_search(query: str) -> list[str]:
    try:
        r = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": UA},
            timeout=20,
        )
        r.raise_for_status()
    except requests.RequestException:
        return []
    raws = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', r.text)
    return [_unwrap_ddg(raw) for raw in raws]


def _brave_search(query: str, api_key: str) -> list[str]:
    try:
        r = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "country": "GB", "count": 10},
            headers={
                "X-Subscription-Token": api_key,
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            },
            timeout=30,
        )
        if r.status_code == 429:
            print("  ! brave rate-limited", flush=True)
            return []
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! brave failed: {e}", flush=True)
        return []
    data = r.json()
    web = (data.get("web") or {}).get("results") or []
    return [item.get("url") for item in web if item.get("url")]


def _serpapi_search(query: str, api_key: str) -> list[str]:
    try:
        r = requests.get(
            "https://serpapi.com/search",
            params={
                "q": query,
                "engine": "google",
                "google_domain": "google.co.uk",
                "gl": "uk",
                "hl": "en",
                "num": 10,
                "api_key": api_key,
            },
            timeout=30,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! serpapi failed: {e}")
        return []
    data = r.json()
    return [item.get("link") for item in data.get("organic_results", []) if item.get("link")]


def find_domain(
    company_name: str,
    location: str = "",
    api_key: str | None = None,
    provider: str = "brave",
    search_terms: list[str] | None = None,
) -> str | None:
    if not api_key:
        return None
    terms = search_terms or ["installer", "UK"]
    query = f'"{company_name}" {" ".join(terms)}'
    if location:
        query += f" {location}"
    searcher = _brave_search if provider == "brave" else _serpapi_search
    candidates: list[str] = []
    for url in searcher(query, api_key):
        domain = _extract_domain(url)
        if not domain:
            continue
        if any(domain == b or domain.endswith("." + b) for b in BLOCKLIST):
            continue
        candidates.append(domain)

    # Prefer domains that share a token with the company name; among those,
    # prefer .co.uk / .uk over .com (UK installers usually own one).
    relevant = [d for d in candidates if _share_token(company_name, d)]
    pool = relevant or candidates

    def rank(d: str) -> tuple[int, int]:
        tld_score = 0
        if d.endswith(".co.uk"):
            tld_score = 3
        elif d.endswith(".uk"):
            tld_score = 2
        elif d.endswith(".com"):
            tld_score = 1
        return (tld_score, -len(d))

    pool.sort(key=rank, reverse=True)
    return pool[0] if pool else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--niche",
        "--config",
        dest="config",
        help="Optional niche config JSON; supplies default paths and search terms",
    )
    parser.add_argument("--input", default="output/prospects_tiered.csv")
    parser.add_argument("--output", default="output/prospects_tiered.csv")
    parser.add_argument(
        "--tier", default="PLATINUM", help="Only resolve domains for this tier"
    )
    parser.add_argument("--delay", type=float, default=1.1)
    parser.add_argument(
        "--provider",
        choices=["serpapi", "brave"],
        default="brave",
        help="Search provider to use (default: brave — free tier friendlier)",
    )
    parser.add_argument("--serpapi-key", default=os.getenv("SERPAPI_API_KEY"))
    parser.add_argument("--brave-key", default=os.getenv("BRAVE_API_KEY"))
    args = parser.parse_args()

    config = load_config(args.config) if args.config else None
    if config:
        if args.input == "output/prospects_tiered.csv":
            args.input = config.pipeline.tiered_output
        if args.output == "output/prospects_tiered.csv":
            args.output = config.pipeline.domain_output
        search_terms = config.search_terms
    else:
        search_terms = ["heat pump", "installer", "UK"]

    api_key = args.brave_key if args.provider == "brave" else args.serpapi_key
    if not api_key:
        env_name = "BRAVE_API_KEY" if args.provider == "brave" else "SERPAPI_API_KEY"
        print(f"Need {env_name} (in .env or pass --{args.provider}-key)")
        return 1

    df = pd.read_csv(args.input)
    if "website" not in df.columns:
        df["website"] = ""

    targets = df[df["tier"] == args.tier]
    print(f"Resolving domains for {len(targets)} {args.tier} rows...")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    found = 0
    consecutive_failures = 0
    processed = 0
    for idx, row in targets.iterrows():
        existing = row.get("website")
        if isinstance(existing, str) and existing.strip():
            continue
        name = row["company_name"]
        loc = row.get("location") if isinstance(row.get("location"), str) else ""
        domain = find_domain(
            name,
            loc,
            api_key=api_key,
            provider=args.provider,
            search_terms=search_terms,
        )
        df.at[idx, "website"] = domain or ""
        status = domain or "—"
        print(f"  [{idx}] {name:50s} → {status}", flush=True)
        if domain:
            found += 1
            consecutive_failures = 0
        else:
            consecutive_failures += 1
        processed += 1

        # Persist every 10 rows so a crash can't wipe progress.
        if processed % 10 == 0:
            df.to_csv(args.output, index=False, encoding="utf-8")

        # Bail out fast if upstream is dead — likely rate-limit / quota.
        if consecutive_failures >= 15:
            print(
                f"\n! 15 consecutive failures — likely rate-limit or quota. Stopping.",
                flush=True,
            )
            break

        time.sleep(args.delay)

    df.to_csv(args.output, index=False, encoding="utf-8")
    print(f"\nFound {found}/{processed} domains. Saved to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
