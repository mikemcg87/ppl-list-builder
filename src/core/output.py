"""Output handlers for processed data."""

from pathlib import Path
from typing import List, Union
import pandas as pd
from src.core.models import Installer


class OutputHandler:
    """Handler for exporting data to various formats."""

    @staticmethod
    def to_csv(
        data: List[Installer],
        output_path: Union[str, Path] = "output/heat-pump-installers.csv",
        sort_by_company: bool = True,
        deduplicate: bool = True
    ) -> Path:
        """Export installer data to CSV file.

        Args:
            data: List of Installer objects to export
            output_path: Path for the output CSV file
            sort_by_company: Sort results by company name alphabetically
            deduplicate: Remove duplicate records by company name

        Returns:
            Path object pointing to the created CSV file
        """
        output_path = Path(output_path)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to list of dictionaries
        data_dicts = [installer.model_dump() for installer in data]

        # Create DataFrame
        df = pd.DataFrame(data_dicts)

        # Deduplicate by company name (case-insensitive)
        if deduplicate and len(df) > 0:
            df["company_name_lower"] = df["company_name"].str.lower()
            df = df.drop_duplicates(subset=["company_name_lower"], keep="first")
            df = df.drop(columns=["company_name_lower"])

        # Sort by company name if requested
        if sort_by_company and len(df) > 0:
            df = df.sort_values("company_name")

        # Reorder columns for readability
        column_order = [
            "company_name",
            "website",
            "phone",
            "location",
            "bus_registered",
            "certifications",
            "scraped_at",
            "source"
        ]
        available_columns = [col for col in column_order if col in df.columns]
        df = df[available_columns]

        # Write to CSV with UTF-8 encoding
        df.to_csv(output_path, index=False, encoding="utf-8")

        return output_path
