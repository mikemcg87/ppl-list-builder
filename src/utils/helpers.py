"""General utility helper functions."""

import re
from typing import Optional


def sanitize_phone_number(phone: str) -> Optional[str]:
    """Clean and standardize phone number.

    Args:
        phone: Raw phone number string

    Returns:
        Cleaned phone number or None if invalid
    """
    if not phone:
        return None

    # Remove common punctuation and whitespace
    cleaned = re.sub(r"[\s\-\(\)\.]+", "", phone)

    # Check if it contains at least some digits
    if not re.search(r"\d", cleaned):
        return None

    return cleaned.strip()


def sanitize_company_name(name: str) -> str:
    """Clean and standardize company name.

    Args:
        name: Raw company name string

    Returns:
        Cleaned company name
    """
    if not name:
        return ""

    # Strip whitespace
    name = name.strip()

    # Remove multiple spaces
    name = re.sub(r"\s+", " ", name)

    return name


def extract_domain_from_url(url: str) -> Optional[str]:
    """Extract domain name from URL.

    Args:
        url: URL string

    Returns:
        Domain name or None if invalid URL
    """
    if not url:
        return None

    # Simple regex to extract domain
    match = re.search(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})", url)

    return match.group(1) if match else None


def is_valid_url(url: str) -> bool:
    """Check if string is a valid URL.

    Args:
        url: URL string to validate

    Returns:
        True if URL appears valid, False otherwise
    """
    if not url:
        return False

    url_pattern = r"^https?://[^\s/$.?#].[^\s]*$"
    return bool(re.match(url_pattern, url, re.IGNORECASE))
