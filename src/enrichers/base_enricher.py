"""Abstract base class for all data enrichers."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd
import logging

logger = logging.getLogger("ppl-list-builder")


class BaseEnricher(ABC):
    """Abstract base class for data enrichers from ad platforms."""

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize enricher.

        Args:
            config: Optional configuration dict
        """
        self.config = config or {}
        self.platform_name = ""  # Must be set by subclass

    @abstractmethod
    def enrich_row(self, row: Dict) -> Dict:
        """
        Enrich a single row with data from this platform.

        Args:
            row: Dict with company data

        Returns:
            Dict with original data + [platform]_* columns
        """
        pass

    def read_csv(self, input_path: str) -> pd.DataFrame:
        """Read input CSV."""
        df = pd.read_csv(input_path)
        logger.info(f"Loaded {len(df)} rows from {input_path}")
        return df

    def enrich_dataset(
        self, df: pd.DataFrame, limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Enrich all rows in the dataset.

        - Skips rows already enriched by this platform
        - Handles per-row errors gracefully
        - Logs progress

        Args:
            df: DataFrame to enrich
            limit: Optional limit on number of rows to enrich (for testing)

        Returns:
            Enriched DataFrame
        """
        enriched_rows = []
        rows_to_process = df.head(limit) if limit else df
        total_rows = len(rows_to_process)

        logger.info(
            f"Starting enrichment with {self.platform_name} ({total_rows} rows)"
        )

        for idx, row in rows_to_process.iterrows():
            try:
                # Skip if already enriched by this platform
                enriched_col = f"{self.platform_name}_enriched_at"
                if enriched_col in df.columns and pd.notna(row.get(enriched_col)):
                    logger.debug(
                        f"Row {idx+1}/{total_rows} already enriched by {self.platform_name}"
                    )
                    enriched_rows.append(row.to_dict())
                    continue

                # Enrich the row
                enriched_row = self.enrich_row(row.to_dict())
                enriched_rows.append(enriched_row)

                company = enriched_row.get("company_name", "Unknown")
                logger.info(f"[{idx+1}/{total_rows}] Enriched: {company}")

            except Exception as e:
                logger.error(f"Error enriching row {idx}: {e}")
                # Add error info instead of failing
                row_dict = row.to_dict()
                row_dict[f"{self.platform_name}_enrichment_error"] = str(e)
                enriched_rows.append(row_dict)

        logger.info(f"Enrichment complete for {self.platform_name}")
        return pd.DataFrame(enriched_rows)

    def write_csv(self, df: pd.DataFrame, output_path: str) -> None:
        """Write enriched CSV."""
        df.to_csv(output_path, index=False, encoding="utf-8")
        logger.info(f"✓ Wrote enriched data to {output_path}")
