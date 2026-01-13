"""Pydantic data models for PPL List Builder."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Installer(BaseModel):
    """Data model for a heat pump installer."""

    company_name: str = Field(..., description="Company name")
    website: Optional[str] = Field(None, description="Company website URL")
    phone: Optional[str] = Field(None, description="Company phone number")
    email: Optional[str] = Field(None, description="Company email address")
    location: Optional[str] = Field(None, description="Company location/address")
    bus_registered: bool = Field(..., description="Whether company is registered with Boiler Upgrade Scheme")
    certifications: List[str] = Field(..., description="List of heat pump certifications")

    # Metadata
    scraped_at: datetime = Field(default_factory=datetime.now, description="When the record was scraped")
    source: str = Field(default="mcs", description="Data source identifier")


class FilterConfig(BaseModel):
    """Configuration for filtering installers."""

    heat_pump_types: List[str] = Field(..., description="Types of heat pumps to filter")
    location: Optional[str] = Field(None, description="Location/postcode filter (future use)")


class ScraperConfig(BaseModel):
    """Configuration for scraper settings."""

    name: str = Field(..., description="Scraper name identifier")
    url: str = Field(..., description="Target website URL")
    filters: FilterConfig = Field(..., description="Filter configuration")
    output_format: str = Field(default="csv", description="Output format (csv, json, db)")
    enable_llm_enrichment: bool = Field(default=False, description="Enable LLM enrichment")
    request_delay: float = Field(default=1.5, description="Delay between requests in seconds")
    retry_attempts: int = Field(default=3, description="Number of retry attempts")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    headless: bool = Field(default=True, description="Run browser in headless mode")
