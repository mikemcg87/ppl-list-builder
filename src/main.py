"""CLI entry point for PPL List Builder."""

import sys
import argparse
import logging
import os
from pathlib import Path

import pandas as pd

from src.core.config import load_config
from src.enrichers import CompaniesHouseEnricher, FacebookAdsEnricher
from src.utils.logging import setup_logging
from scripts.build_prospect_tiers import assign_tier, lead_score, split_director


def _add_missing_companies_house_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add CH columns that make tiering explicit when no API key is configured."""
    out = df.copy()
    defaults = {
        "ch_match_status": "not_run",
        "ch_company_status": "",
        "ch_primary_director": "",
        "ch_director_count": 0,
    }
    for col, value in defaults.items():
        if col not in out.columns:
            out[col] = value
    return out


def _build_tiered_csv(config, logger: logging.Logger) -> None:
    """Build a tiered CSV from the source output and optional enrichers."""
    source_path = Path(config.pipeline.source_output)
    if not source_path.exists():
        logger.warning(f"Source CSV not found, cannot build tiers: {source_path}")
        return

    df = pd.read_csv(source_path)
    ch_key = os.getenv("COMPANIES_HOUSE_API_KEY")
    if ch_key:
        logger.info("Running free Companies House enrichment before tiering...")
        df = CompaniesHouseEnricher(api_key=ch_key).enrich_dataset(df)
        Path(config.pipeline.companies_house_output).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(config.pipeline.companies_house_output, index=False, encoding="utf-8")
    else:
        logger.warning("COMPANIES_HOUSE_API_KEY not set; tiered CSV will mark rows SKIP/not_run")
        df = _add_missing_companies_house_columns(df)

    sc_key = os.getenv("SCRAPECREATORS_API_KEY")
    if config.pipeline.run_paid_enrichers and sc_key:
        logger.info("Running paid/credit-based Facebook Ads enrichment before tiering...")
        fb = FacebookAdsEnricher(api_key=sc_key).enrich_dataset(df)
        Path(config.pipeline.facebook_output).parent.mkdir(parents=True, exist_ok=True)
        fb.to_csv(config.pipeline.facebook_output, index=False, encoding="utf-8")
        fb_cols = [c for c in fb.columns if c.startswith("facebook_") or c == "company_name"]
        df = df.drop(columns=[c for c in df.columns if c.startswith("facebook_")], errors="ignore")
        df = df.merge(fb[fb_cols], on="company_name", how="left")
    elif config.pipeline.run_paid_enrichers:
        logger.warning("SCRAPECREATORS_API_KEY not set; skipping paid Facebook Ads enrichment")

    df["tier"] = df.apply(assign_tier, axis=1, tiering=config.tiering)
    df["lead_score"] = df.apply(lead_score, axis=1, tiering=config.tiering)
    director_col = config.tiering.required_director_column
    if len(df):
        first_names, last_names = zip(*df[director_col].map(split_director))
        df["director_first_name"] = first_names
        df["director_last_name"] = last_names
    else:
        df["director_first_name"] = []
        df["director_last_name"] = []

    tier_order = {"PLATINUM": 0, "GOLD": 1, "SILVER": 2, "BRONZE": 3, "SKIP": 4}
    df["_tier_rank"] = df["tier"].map(tier_order)
    df = df.sort_values(["_tier_rank", "lead_score"], ascending=[True, False]).drop(
        columns=["_tier_rank"]
    )
    out = Path(config.pipeline.tiered_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")
    logger.info(f"Tiered CSV saved to: {out}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PPL List Builder - Extensible data scraping framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main --config config/mcs_config.json
  python -m src.main --config config/solar_pv.json
  python -m src.main --config config/mcs_config.json --output output/results.csv
  python -m src.main --config config/mcs_config.json --no-sort
        """
    )

    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to scraper configuration JSON file"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output CSV file path (default: niche config pipeline.source_output)"
    )

    parser.add_argument(
        "--no-sort",
        action="store_true",
        help="Don't sort results by company name"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )

    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs",
        help="Directory for log files (default: logs)"
    )

    args = parser.parse_args()

    # Set up logging
    log_level = getattr(logging, args.log_level)
    logger = setup_logging(log_dir=args.log_dir, log_level=log_level)

    try:
        # Load configuration
        logger.info(f"Loading configuration from {args.config}...")
        config = load_config(args.config)
        logger.info("Configuration loaded successfully")
        if args.output:
            config.pipeline.source_output = args.output

        # Create scraper based on config name
        if config.name == "mcs":
            from src.scrapers.mcs_scraper import MCScraper

            scraper = MCScraper(config)
        elif config.name == "fca":
            from src.scrapers.fca_scraper import FCAScraper

            scraper = FCAScraper(config)
        else:
            logger.error(f"Unknown scraper: {config.name}")
            return 1

        # Run scraper
        logger.info("Starting scraper...")
        installers = scraper.scrape()

        # Note: Results are saved incrementally during scraping
        # No additional export needed
        logger.info(f"✓ Scraping complete!")
        logger.info(f"Incremental CSV saved to: {scraper.output_path}")
        logger.info(f"Run 'python3 scripts/finalize_csv.py' to deduplicate and sort")
        if config.pipeline.auto_build_tiers:
            _build_tiered_csv(config, logger)

        return 0

    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        return 1

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
