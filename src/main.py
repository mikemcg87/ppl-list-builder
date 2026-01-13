"""CLI entry point for PPL List Builder."""

import sys
import argparse
import logging
from pathlib import Path

from src.core.config import load_config
from src.core.output import OutputHandler
from src.scrapers.mcs_scraper import MCScraper
from src.utils.logging import setup_logging


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PPL List Builder - Extensible data scraping framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main --config config/mcs_config.json
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
        default="output/heat-pump-installers.csv",
        help="Output CSV file path (default: output/heat-pump-installers.csv)"
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

        # Create scraper based on config name
        if config.name == "mcs":
            scraper = MCScraper(config)
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

        return 0

    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        return 1

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
