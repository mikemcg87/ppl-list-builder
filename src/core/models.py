"""Pydantic data models for PPL List Builder."""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Installer(BaseModel):
    """Data model for an installer/prospect source record."""

    company_name: str = Field(..., description="Company name")
    website: Optional[str] = Field(None, description="Company website URL")
    phone: Optional[str] = Field(None, description="Company phone number")
    email: Optional[str] = Field(None, description="Company email address")
    location: Optional[str] = Field(None, description="Company location/address")
    bus_registered: bool = Field(..., description="Whether company is registered with Boiler Upgrade Scheme")
    mcs_registered: bool = Field(default=True, description="Whether record came from MCS certified directory")
    certifications: List[str] = Field(..., description="List of source certifications")
    niche: str = Field(default="heat_pumps", description="Prospect niche identifier")
    source_technology: Optional[str] = Field(None, description="Source directory technology/category")

    # Metadata
    scraped_at: datetime = Field(default_factory=datetime.now, description="When the record was scraped")
    source: str = Field(default="mcs", description="Data source identifier")


class FilterConfig(BaseModel):
    """Configuration for filtering installers."""

    heat_pump_types: List[str] = Field(default_factory=list, description="Legacy heat-pump filters")
    technologies: List[str] = Field(default_factory=list, description="Source directory technologies to filter")
    mcs_image_src_contains: Optional[str] = Field(
        None,
        description="Substring used to click the MCS technology tile image",
    )
    mcs_tile_text: Optional[str] = Field(
        None,
        description="Technology tile text fallback for MCS source pages",
    )
    location: Optional[str] = Field(None, description="Location/postcode filter (future use)")


class TieringConfig(BaseModel):
    """Per-niche tiering and scoring signals."""

    primary_quality_signal: str = Field(
        default="bus_registered",
        description="Boolean source-trust signal used for GOLD/PLATINUM",
    )
    required_status_column: str = Field(default="ch_company_status")
    required_status_value: str = Field(default="active")
    required_director_column: str = Field(default="ch_primary_director")
    score_weights: Dict[str, int] = Field(
        default_factory=lambda: {
            "primary_quality_signal": 30,
            "facebook_ads_running": 40,
            "google_ads_running": 30,
            "multiple_directors": 15,
            "named_director": 5,
        }
    )


class PipelineConfig(BaseModel):
    """Default file paths for a niche pipeline run."""

    auto_build_tiers: bool = Field(
        default=False,
        description="After source scraping, build the niche tiered CSV from available enrichments",
    )
    run_paid_enrichers: bool = Field(
        default=False,
        description="Allow source CLI to run paid/credit-based enrichers such as ScrapeCreators",
    )
    source_output: str = Field(default="output/heat-pump-installers.csv")
    companies_house_output: str = Field(
        default="output/heat-pump-installers-with-directors.csv"
    )
    facebook_output: str = Field(default="output/enriched_fb.csv")
    tiered_output: str = Field(default="output/prospects_tiered.csv")
    domain_output: str = Field(default="output/prospects_tiered.csv")
    google_output: str = Field(default="output/final_leads_with_google.csv")


class ScraperConfig(BaseModel):
    """Configuration for scraper settings."""

    name: str = Field(..., description="Scraper name identifier")
    niche: str = Field(default="heat_pumps", description="Prospect niche identifier")
    display_name: str = Field(default="Heat Pumps", description="Human-readable niche")
    url: str = Field(..., description="Target website URL")
    filters: FilterConfig = Field(..., description="Filter configuration")
    tiering: TieringConfig = Field(default_factory=TieringConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    search_terms: List[str] = Field(
        default_factory=lambda: ["heat pump", "installer", "UK"],
        description="Terms used for domain discovery queries",
    )
    output_format: str = Field(default="csv", description="Output format (csv, json, db)")
    enable_llm_enrichment: bool = Field(default=False, description="Enable LLM enrichment")
    request_delay: float = Field(default=1.5, description="Delay between requests in seconds")
    retry_attempts: int = Field(default=3, description="Number of retry attempts")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    headless: bool = Field(default=True, description="Run browser in headless mode")
