#!/usr/bin/env python3
"""Finalize CSV: deduplicate and sort heat pump installer data."""

import argparse
import logging
from pathlib import Path
from datetime import datetime
import pandas as pd
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ppl-list-builder-finalize")


def finalize_csv(input_path: str, output_path: str = None, sort_order: str = "asc") -> None:
    """Finalize CSV by deduplicating and sorting.

    Args:
        input_path: Path to CSV file to finalize
        output_path: Path to write finalized CSV (defaults to input_path)
        sort_order: Sort order for company names ("asc" or "desc")
    """
    input_file = Path(input_path)

    if not input_file.exists():
        logger.error(f"CSV file not found: {input_path}")
        sys.exit(1)

    if output_path is None:
        output_path = input_path

    logger.info(f"Finalizing CSV: {input_path}")
    logger.info("Deduplicating and sorting...")

    try:
        # Read CSV file
        df = pd.read_csv(input_file, encoding='utf-8')
        logger.info(f"Read {len(df)} total records from CSV")

        # Deduplicate by company name (case-insensitive)
        df['company_name_lower'] = df['company_name'].str.lower()
        df_deduplicated = df.drop_duplicates(subset=['company_name_lower'], keep='first')
        df_deduplicated = df_deduplicated.drop(columns=['company_name_lower'])

        logger.info(f"After deduplication: {len(df_deduplicated)} unique records")

        # Sort by company name (case-insensitive)
        ascending = sort_order.lower() == "asc"
        df_sorted = df_deduplicated.sort_values('company_name', key=lambda x: x.str.lower(), ascending=ascending)

        # Write back to CSV
        df_sorted.to_csv(output_path, index=False, encoding='utf-8')

        logger.info(f"✓ Finalized CSV: {len(df_sorted)} unique installers")
        logger.info(f"✓ Saved to: {output_path}")

        # Print summary stats
        logger.info("\n=== Summary ===")
        logger.info(f"Original records: {len(df)}")
        logger.info(f"Duplicates removed: {len(df) - len(df_sorted)}")
        logger.info(f"Final records: {len(df_sorted)}")
        logger.info(f"BUS registered: {df_sorted['bus_registered'].sum()}")
        logger.info(f"With email: {df_sorted['email'].notna().sum()}")
        logger.info(f"With website: {df_sorted['website'].notna().sum()}")
        logger.info(f"With phone: {df_sorted['phone'].notna().sum()}")

    except Exception as e:
        logger.error(f"Error finalizing CSV: {e}", exc_info=True)
        sys.exit(1)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Finalize MCS installer CSV: deduplicate and sort"
    )
    parser.add_argument(
        "--input",
        "-i",
        default="output/heat-pump-installers.csv",
        help="Input CSV path (default: output/heat-pump-installers.csv)"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output CSV path (defaults to input path)"
    )
    parser.add_argument(
        "--sort",
        "-s",
        default="asc",
        choices=["asc", "desc"],
        help="Sort order: asc (A-Z) or desc (Z-A)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )

    args = parser.parse_args()

    # Set logging level
    logger.setLevel(getattr(logging, args.log_level))

    finalize_csv(args.input, args.output, args.sort)


if __name__ == "__main__":
    main()
