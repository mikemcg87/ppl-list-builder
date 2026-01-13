"""Abstract base class for data sources."""

from abc import ABC, abstractmethod
from typing import List
from src.core.models import Installer, ScraperConfig


class DataSource(ABC):
    """Abstract base class for all data scrapers."""

    def __init__(self, config: ScraperConfig):
        """Initialize data source with configuration.

        Args:
            config: ScraperConfig instance with scraper settings
        """
        self.config = config

    @abstractmethod
    def scrape(self) -> List[Installer]:
        """Execute the scraping process.

        Returns:
            List of Installer objects extracted from the source
        """
        pass

    def validate_data(self, data: List[Installer]) -> List[Installer]:
        """Validate and clean extracted data.

        Args:
            data: List of Installer objects to validate

        Returns:
            List of validated Installer objects
        """
        # Default implementation: return data as-is
        # Subclasses can override for custom validation
        return data

    def enrich_with_llm(self, data: List[Installer]) -> List[Installer]:
        """Optionally enrich data using LLM if enabled.

        Args:
            data: List of Installer objects to enrich

        Returns:
            List of enriched Installer objects
        """
        if not self.config.enable_llm_enrichment:
            return data

        # Default implementation: return data as-is if enrichment not implemented
        # Subclasses can override for LLM enrichment
        return data
