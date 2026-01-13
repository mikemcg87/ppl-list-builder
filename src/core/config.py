"""Configuration loading and validation."""

import json
from pathlib import Path
from typing import Union
from pydantic import ValidationError
from src.core.models import ScraperConfig


def load_config(config_path: Union[str, Path]) -> ScraperConfig:
    """Load and validate scraper configuration from JSON file.

    Args:
        config_path: Path to the JSON configuration file

    Returns:
        Validated ScraperConfig object

    Raises:
        FileNotFoundError: If configuration file doesn't exist
        json.JSONDecodeError: If JSON is invalid
        ValidationError: If configuration doesn't match ScraperConfig schema
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, "r") as f:
            config_dict = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON in configuration file: {e.msg}",
            e.doc,
            e.pos
        )

    try:
        config = ScraperConfig(**config_dict)
        return config
    except ValidationError as e:
        raise ValidationError(f"Configuration validation failed: {e}")
