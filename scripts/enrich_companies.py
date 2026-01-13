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

from src.enrichers import FacebookAdsEnricher, GoogleAdsEnricher
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
        "--input",
        "-i",
        required=True,
        help="Input CSV path with company data",
    )

    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output CSV path for enriched data",
    )

    parser.add_argument(
        "--platforms",
        "-p",
        nargs="*",
        default=["facebook"],
        choices=["facebook", "google", "linkedin"],
        help="Platforms to enrich (space-separated, default: facebook)",
    )

    parser.add_argument(
        "--api-key",
        "-k",
        help="API key for ScrapeCreators (defaults to env var SCRAPECREATORS_API_KEY)",
    )

    parser.add_argument(
        "--serpapi-key",
        help="API key for SerpApi (defaults to env var SERPAPI_API_KEY)",
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

        if "facebook" in args.platforms and not sc_api_key:
            logger.error(
                "No ScrapeCreators API key provided for Facebook enrichment. "
                "Pass --api-key or set SCRAPECREATORS_API_KEY"
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
                # For Hybrid approach, we need BOTH keys
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
