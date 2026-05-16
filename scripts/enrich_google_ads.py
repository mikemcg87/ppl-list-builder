#!/usr/bin/env python3
"""Enrich the prospect list with Google Ads activity, using existing
website domains. Designed to run on the 50 PLATINUM+GOLD-with-domain rows.

Reads SCRAPECREATORS_API_KEY from .env. Skips rows without a website.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.enrichers import GoogleAdsDomainEnricher
from src.utils.logging import setup_logging

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/prospects_tiered.csv")
    parser.add_argument("--output", default="output/prospects_tiered.csv")
    parser.add_argument(
        "--filter-tier",
        nargs="*",
        default=["PLATINUM", "GOLD"],
        help="Tiers to enrich (default: PLATINUM GOLD)",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    setup_logging(log_dir="logs", log_level=logging.INFO)
    logger = logging.getLogger("ppl-list-builder")

    api_key = os.getenv("SCRAPECREATORS_API_KEY")
    if not api_key:
        logger.error("Set SCRAPECREATORS_API_KEY in .env")
        return 1

    df = pd.read_csv(args.input, keep_default_na=False)
    logger.info(f"Loaded {len(df)} rows")

    # We only want to spend credits on rows that have a website *and* match the
    # tier filter. Mark everything else for skip up-front so the enricher's
    # built-in "skip already enriched" logic doesn't accidentally re-run.
    target_mask = df["tier"].isin(args.filter_tier) & df["website"].astype(str).str.strip().ne("")
    targets = df[target_mask]
    if args.limit:
        targets = targets.head(args.limit)
    logger.info(f"Targeting {len(targets)} rows ({args.filter_tier} with domain)")

    enricher = GoogleAdsDomainEnricher(api_key=api_key)

    new_cols = [
        "google_ads_running",
        "google_ads_count",
        "google_ads_formats",
        "google_ads_first_creative",
        "google_enriched_at",
        "google_error",
        "google_skip_reason",
    ]
    for c in new_cols:
        if c not in df.columns:
            df[c] = ""

    for i, (idx, row) in enumerate(targets.iterrows(), start=1):
        enriched = enricher.enrich_row(row.to_dict())
        for c in new_cols:
            v = enriched.get(c, "")
            if isinstance(v, bool):
                v = "True" if v else "False"
            elif v is None:
                v = ""
            else:
                v = str(v)
            df.at[idx, c] = v
        running = enriched.get("google_ads_running")
        count = enriched.get("google_ads_count")
        company = row.get("company_name", "")
        logger.info(f"[{i}/{len(targets)}] {company}: running={running} count={count}")

        if i % 10 == 0:
            df.to_csv(args.output, index=False, encoding="utf-8")

    df.to_csv(args.output, index=False, encoding="utf-8")
    logger.info(f"✓ Saved to {args.output}")

    enriched_rows = df[target_mask].copy() if args.limit is None else df.iloc[targets.index]
    running_count = (enriched_rows["google_ads_running"] == True).sum()
    logger.info(
        f"Summary: {running_count} of {len(targets)} prospects are running Google ads"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
