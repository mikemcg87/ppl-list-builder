#!/usr/bin/env python3
"""Run FB profile + LinkedIn + CH filings enrichments on the outreach
list (PLATINUM + GOLD with email). Operates in-place on the master CSV
so columns flow back into the prospect database.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.enrichers import (
    CompaniesHouseFilingsEnricher,
    FacebookProfileEnricher,
    LinkedinCompanyEnricher,
)
from src.utils.logging import setup_logging

load_dotenv()


def _coerce(v):
    if isinstance(v, bool):
        return "True" if v else "False"
    if v is None:
        return ""
    return str(v)


def run_enricher(df, target_idx, enricher, label):
    logger = logging.getLogger("ppl-list-builder")
    logger.info(f"=== {label}: {len(target_idx)} rows ===")
    for i, idx in enumerate(target_idx, start=1):
        row = df.loc[idx].to_dict()
        result = enricher.enrich_row(row)
        for k, v in result.items():
            if k == "company_name":
                continue
            if k not in df.columns:
                df[k] = ""
            # Force object dtype so we can store the coerced string value
            # regardless of the column's prior numeric/bool dtype.
            if df[k].dtype != object:
                df[k] = df[k].astype(object)
            df.at[idx, k] = _coerce(v)
        if i % 10 == 0:
            logger.info(f"  [{i}/{len(target_idx)}] last: {row.get('company_name')}")
    return df


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/prospects_tiered.csv")
    parser.add_argument("--output", default="output/prospects_tiered.csv")
    parser.add_argument("--filter-tier", nargs="*", default=["PLATINUM", "GOLD"])
    parser.add_argument(
        "--require-email",
        action="store_true",
        default=True,
        help="Only enrich rows with a verified hunter_email",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip", nargs="*", default=[], choices=["fb", "linkedin", "chfilings"])
    args = parser.parse_args()

    setup_logging(log_dir="logs", log_level=logging.INFO)
    logger = logging.getLogger("ppl-list-builder")

    sc_key = os.getenv("SCRAPECREATORS_API_KEY")
    brave_key = os.getenv("BRAVE_API_KEY")
    ch_key = os.getenv("COMPANIES_HOUSE_API_KEY")

    if not sc_key and "fb" not in args.skip and "linkedin" not in args.skip:
        logger.error("SCRAPECREATORS_API_KEY not set")
        return 1
    if not brave_key and "linkedin" not in args.skip:
        logger.error("BRAVE_API_KEY not set")
        return 1
    if not ch_key and "chfilings" not in args.skip:
        logger.error("COMPANIES_HOUSE_API_KEY not set")
        return 1

    df = pd.read_csv(args.input, keep_default_na=False)

    mask = df["tier"].isin(args.filter_tier)
    if args.require_email:
        mask &= df["hunter_email"].astype(str).str.contains("@", na=False)
        mask &= df["hunter_email"].astype(str) != ""
    targets = df[mask].index.tolist()
    if args.limit:
        targets = targets[: args.limit]
    logger.info(f"Targets: {len(targets)} rows")

    if "fb" not in args.skip:
        fb = FacebookProfileEnricher(api_key=sc_key)
        df = run_enricher(df, targets, fb, "Facebook profile")
        df.to_csv(args.output, index=False, encoding="utf-8")
        logger.info(f"Saved after fb to {args.output}")

    if "linkedin" not in args.skip:
        li = LinkedinCompanyEnricher(api_key=sc_key, brave_key=brave_key)
        df = run_enricher(df, targets, li, "LinkedIn company")
        df.to_csv(args.output, index=False, encoding="utf-8")
        logger.info(f"Saved after linkedin to {args.output}")

    if "chfilings" not in args.skip:
        chf = CompaniesHouseFilingsEnricher(api_key=ch_key)
        df = run_enricher(df, targets, chf, "Companies House filings")
        df.to_csv(args.output, index=False, encoding="utf-8")
        logger.info(f"Saved after chfilings to {args.output}")

    logger.info("✓ All enrichments complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
