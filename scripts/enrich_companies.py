#!/usr/bin/env python3
"""Enrich company CSV with ads data from multiple platforms."""

import argparse
import logging
import sys
import os
from pathlib import Path
import pandas as pd

from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.enrichers import (
    CompaniesHouseEnricher,
    FacebookAdsEnricher,
    GoogleAdsEnricher,
    GoogleAdsDomainEnricher,
    HunterEnricher,
)
from src.core.config import load_config
from src.utils.logging import setup_logging

# Load environment variables
load_dotenv()

logger = logging.getLogger("ppl-list-builder")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Enrich company CSV with ads data from multiple platforms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/enrich_companies.py \\
    --input output/heat-pump-installers.csv \\
    --output output/heat-pump-installers-enriched.csv \\
    --platforms facebook \\
    --api-key YOUR_KEY

  python scripts/enrich_companies.py \\
    --input output/heat-pump-installers.csv \\
    --output output/test-enriched.csv \\
    --platforms facebook \\
    --api-key YOUR_KEY \\
    --limit 50
        """,
    )

    parser.add_argument(
        "--niche",
        "--config",
        dest="config",
        help="Optional niche config JSON; supplies default input/output paths",
    )

    parser.add_argument(
        "--input",
        "-i",
        required=False,
        help="Input CSV path with company data",
    )

    parser.add_argument(
        "--output",
        "-o",
        required=False,
        help="Output CSV path for enriched data",
    )

    parser.add_argument(
        "--platforms",
        "-p",
        nargs="*",
        default=["facebook"],
        choices=["facebook", "google", "google_serpapi", "linkedin", "companies_house", "hunter"],
        help="Platforms to enrich (space-separated, default: facebook)",
    )

    parser.add_argument(
        "--api-key",
        "-k",
        help="API key for ScrapeCreators (defaults to env var SCRAPECREATORS_API_KEY)",
    )

    parser.add_argument(
        "--serpapi-key",
        help="API key for SerpApi. Explicit opt-in only; Brave/domain-first paths are preferred.",
    )

    parser.add_argument(
        "--ch-key",
        help="API key for Companies House (defaults to env var COMPANIES_HOUSE_API_KEY)",
    )

    parser.add_argument(
        "--hunter-key",
        help="API key for Hunter.io (defaults to env var HUNTER_API_KEY)",
    )

    parser.add_argument(
        "--filter-tier",
        help="Only enrich rows where tier == this value (e.g. PLATINUM)",
    )

    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Limit to first N rows (for testing, default: all)",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Directory for log files (default: logs)",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip rows already enriched (resume mode)",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = getattr(logging, args.log_level)
    logger_instance = setup_logging(log_dir=args.log_dir, log_level=log_level)

    try:
        config = load_config(args.config) if args.config else None
        if config and not args.input:
            if args.platforms == ["companies_house"]:
                args.input = config.pipeline.source_output
            elif args.platforms == ["facebook"]:
                args.input = config.pipeline.companies_house_output
            elif args.platforms == ["google"]:
                args.input = config.pipeline.domain_output
            else:
                args.input = config.pipeline.source_output
        if config and not args.output:
            if args.platforms == ["companies_house"]:
                args.output = config.pipeline.companies_house_output
            elif args.platforms == ["facebook"]:
                args.output = config.pipeline.facebook_output
            elif args.platforms == ["google"]:
                args.output = config.pipeline.google_output
            else:
                args.output = config.pipeline.source_output
        if not args.input or not args.output:
            logger.error("Pass --input/--output, or pass --niche config/<niche>.json")
            return 1

        # Validate inputs
        input_file = Path(args.input)
        if not input_file.exists():
            logger.error(f"Input file not found: {args.input}")
            return 1

        output_file = Path(args.output)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Get API keys
        sc_api_key = args.api_key or os.getenv("SCRAPECREATORS_API_KEY")
        serpapi_key = args.serpapi_key or os.getenv("SERPAPI_API_KEY")
        ch_api_key = args.ch_key or os.getenv("COMPANIES_HOUSE_API_KEY")
        hunter_api_key = args.hunter_key or os.getenv("HUNTER_API_KEY")

        if "facebook" in args.platforms and not sc_api_key:
            logger.error(
                "No ScrapeCreators API key provided for Facebook enrichment. "
                "Pass --api-key or set SCRAPECREATORS_API_KEY"
            )
            return 1

        if "companies_house" in args.platforms and not ch_api_key:
            logger.error(
                "No Companies House API key provided. "
                "Pass --ch-key or set COMPANIES_HOUSE_API_KEY"
            )
            return 1
            
        # Load initial CSV
        try:
            df = pd.read_csv(args.input)
            logger.info(f"Loaded {len(df)} rows from {args.input}")
        except Exception as e:
            logger.error(f"Failed to load input CSV: {e}")
            return 1

        # Run enrichers sequentially
        for platform in args.platforms:
            enricher = None
            if platform == "facebook":
                logger.info("Starting Facebook Ads enrichment...")
                enricher = FacebookAdsEnricher(api_key=sc_api_key)
            elif platform == "google":
                logger.info("Starting Google Ads enrichment using existing website/domain column...")
                if not sc_api_key:
                     logger.error("ScrapeCreators key required for Google Ads.")
                     return 1
                enricher = GoogleAdsDomainEnricher(api_key=sc_api_key)
            elif platform == "google_serpapi":
                # Explicit legacy path only.
                if serpapi_key:
                    os.environ["SERPAPI_API_KEY"] = serpapi_key
                    
                if not sc_api_key:
                     logger.error("ScrapeCreators key required for Google Ads (ads data).")
                     return 1
                     
                # If we are using hybrid, we strictly need SERPAPI_API_KEY in env.
                if not os.getenv("SERPAPI_API_KEY"):
                     logger.warning("SERPAPI_API_KEY not found. Hybrid domain lookup will fail.")
                
                logger.info("Starting Google Ads enrichment (Hybrid: SerpApi for domain -> ScrapeCreators for ads)...")
                enricher = GoogleAdsEnricher(api_key=sc_api_key)
            elif platform == "companies_house":
                logger.info("Starting Companies House enrichment...")
                enricher = CompaniesHouseEnricher(api_key=ch_api_key)
            elif platform == "hunter":
                if args.filter_tier != "PLATINUM":
                    logger.error("Hunter is rate-constrained. Pass --filter-tier PLATINUM explicitly.")
                    return 1
                if not hunter_api_key:
                    logger.error(
                        "No Hunter.io API key. Pass --hunter-key or set HUNTER_API_KEY"
                    )
                    return 1
                logger.info(
                    f"Starting Hunter.io enrichment (tier filter: {args.filter_tier or 'none'})..."
                )
                enricher = HunterEnricher(
                    api_key=hunter_api_key,
                    tier_filter=args.filter_tier,
                )

            if enricher:
                # Enrich dataset (updates df in place or returns new one)
                # enrich_dataset returns a new DataFrame with the enriched data
                df = enricher.enrich_dataset(df, limit=args.limit)
        
        # Write final CSV
        output_path = args.output
        df.to_csv(output_path, index=False, encoding="utf-8")
        logger.info(f"✓ Enrichment complete! Results saved to: {output_path}")

        return 0

        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
