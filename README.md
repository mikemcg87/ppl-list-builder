# PPL List Builder

An extensible, general-purpose data scraping and aggregation framework for collecting installer/professional lists from multiple sources. **Phase 1** focuses on scraping UK heat pump installers from the **MCS (Microgeneration Certification Scheme) Directory**.

## Overview

PPL List Builder is a Python-based web scraping framework designed to:
- Collect installer data from multiple sources (currently MCS)
- Extract structured data with validation and deduplication
- Export results to various formats (CSV, JSON, database - future)
- Support optional LLM-powered data enrichment
- Provide a foundation for scaling to new data sources

**Phase 1 Scope**: Scrape ~2,200 UK heat pump installers from the MCS Directory, including their certifications, contact details, and BUS registration status.

## Technology Stack

- **Language**: Python 3.9+
- **Web Automation**: Selenium with ChromeDriver
- **Data Modeling**: Pydantic v2
- **Data Processing**: pandas
- **Configuration**: JSON with Pydantic validation

## Quick Start

### Prerequisites

- Python 3.9 or higher
- pip package manager
- Chrome/Chromium browser (for Selenium)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/michaelmcglade/ppl-list-builder.git
cd ppl-list-builder
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running the Scraper

```bash
# Basic usage with default config
python -m src.main --config config/mcs_config.json

# With custom output file
python -m src.main --config config/mcs_config.json --output results/my-installers.csv

# Without sorting
python -m src.main --config config/mcs_config.json --no-sort

# With debug logging
python -m src.main --config config/mcs_config.json --log-level DEBUG
```

## Configuration

Configuration is managed via JSON files. The included `config/mcs_config.json` contains settings for the MCS scraper:

```json
{
  "name": "mcs",
  "url": "https://www.mcscertified.com/find-an-installer",
  "filters": {
    "heat_pump_types": [
      "Air Source Heat Pump",
      "Exhaust Air Heat Pump",
      "Ground/Water Source Heat Pump"
    ],
    "location": null
  },
  "output_format": "csv",
  "enable_llm_enrichment": false,
  "request_delay": 1.5,
  "retry_attempts": 3,
  "timeout": 30,
  "headless": true
}
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | - | Scraper identifier (e.g., "mcs") |
| `url` | str | - | Target website URL |
| `filters.heat_pump_types` | list | - | Heat pump types to filter |
| `filters.location` | str | null | Location filter (future use) |
| `output_format` | str | "csv" | Output format (csv, json, db) |
| `enable_llm_enrichment` | bool | false | Enable LLM data enrichment |
| `request_delay` | float | 1.5 | Delay between requests (seconds) |
| `retry_attempts` | int | 3 | Number of retry attempts |
| `timeout` | int | 30 | Page load timeout (seconds) |
| `headless` | bool | true | Run browser in headless mode |

## Project Structure

```
ppl-list-builder/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py           # Pydantic data models
│   │   ├── data_source.py      # Abstract base class
│   │   ├── config.py           # Configuration loading
│   │   └── output.py           # Output handlers
│   ├── scrapers/
│   │   ├── __init__.py
│   │   └── mcs_scraper.py      # MCS scraper implementation
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logging.py          # Logging setup
│   │   ├── retry.py            # Retry decorators
│   │   └── helpers.py          # Utility functions
│   └── main.py                 # CLI entry point
├── config/
│   └── mcs_config.json         # MCS scraper configuration
├── output/                     # Generated CSV files
├── logs/                       # Scraper logs
├── tests/
│   ├── __init__.py
│   └── test_mcs_scraper.py     # Unit tests
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Core Components

### Data Models (`src/core/models.py`)

**Installer**: Represents a single heat pump installer with fields:
- `company_name`: str
- `website`: Optional[str]
- `phone`: Optional[str]
- `location`: Optional[str]
- `bus_registered`: bool
- `certifications`: List[str]
- `scraped_at`: datetime (auto-populated)
- `source`: str (default: "mcs")

**FilterConfig**: Configuration for filtering installers
- `heat_pump_types`: List of heat pump types to scrape
- `location`: Optional location filter (future use)

**ScraperConfig**: Complete scraper configuration loaded from JSON

### Abstract DataSource (`src/core/data_source.py`)

Base class for all data scrapers:
- `scrape()`: Execute scraping logic
- `validate_data()`: Validate and clean extracted data
- `enrich_with_llm()`: Optional LLM enrichment

### MCS Scraper (`src/scrapers/mcs_scraper.py`)

Selenium-based scraper for the MCS Directory:
- Navigates to MCS website and applies heat pump type filters
- Handles JavaScript-based pagination
- Clicks "VIEW DETAILS" for each installer to extract additional data
- Extracts: company name, website, phone, location, BUS status, certifications
- Implements robust error handling and retry logic
- Adds configurable delays between requests for rate limiting
- Logs all actions and errors

### Output Handler (`src/core/output.py`)

Exports scraped data to CSV:
- Deduplicates records by company name (case-insensitive)
- Sorts by company name (optional)
- Handles UTF-8 encoding for special characters
- Configurable output path

### Configuration System (`src/core/config.py`)

Loads and validates JSON configuration files using Pydantic:
- Validates all required and optional fields
- Provides clear error messages for invalid configurations
- Returns validated `ScraperConfig` object

### Utilities (`src/utils/`)

**logging.py**: Centralized logging setup with file and console output

**retry.py**: Decorators for retry logic and rate limiting
- `@retry_on_exception()`: Retry on specific exceptions
- `@rate_limit()`: Add delay between function calls

**helpers.py**: Data sanitization and validation utilities
- `sanitize_phone_number()`: Clean phone numbers
- `sanitize_company_name()`: Clean company names
- `is_valid_url()`: Validate URLs
- `extract_domain_from_url()`: Extract domain from URL

## CLI Usage

### Help
```bash
python -m src.main --help
```

### Examples

```bash
# Run with default settings
python -m src.main --config config/mcs_config.json

# Custom output location
python -m src.main --config config/mcs_config.json --output /path/to/results.csv

# Debug mode with verbose logging
python -m src.main --config config/mcs_config.json --log-level DEBUG

# Keep original order (no sorting)
python -m src.main --config config/mcs_config.json --no-sort

# Custom log directory
python -m src.main --config config/mcs_config.json --log-dir /var/log/ppl-builder
```

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest tests/

# Run with verbose output
python -m pytest -v tests/

# Run specific test file
python -m pytest tests/test_mcs_scraper.py

# Run specific test class
python -m pytest tests/test_mcs_scraper.py::TestDataModels
```

Tests cover:
- Pydantic data model validation
- Configuration loading and validation
- Helper function sanitization and validation
- CSV export with deduplication
- Output formatting

## Logging

Logs are written to `logs/` directory with timestamp-based filenames:
- Format: `scraper_YYYYMMDD_HHMMSS.log`
- Log levels: DEBUG, INFO, WARNING, ERROR
- Both file and console output (can be toggled)

Example log output:
```
2025-11-29 15:50:42 - ppl-list-builder - INFO - Loading configuration from config/mcs_config.json...
2025-11-29 15:50:42 - ppl-list-builder - INFO - Configuration loaded successfully
2025-11-29 15:50:43 - ppl-list-builder - INFO - Starting scraper...
2025-11-29 15:50:44 - ppl-list-builder - INFO - Page loaded, applying filters...
2025-11-29 15:50:46 - ppl-list-builder - INFO - Filters applied, results loading...
2025-11-29 15:50:47 - ppl-list-builder - INFO - Scraping page 1...
2025-11-29 15:50:48 - ppl-list-builder - INFO - Found 12 installer cards on current page
```

## Output Format

The generated CSV file contains the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| `company_name` | Installer company name | "Smith Heat Pumps Ltd" |
| `website` | Company website URL | "https://www.smithhp.com" |
| `phone` | Contact phone number | "01234567890" |
| `location` | Company location/address | "London, UK" |
| `bus_registered` | BUS registration status | true/false |
| `certifications` | Heat pump certifications | "[\"Air Source\", \"Ground/Water\"]" |
| `scraped_at` | When record was scraped | "2025-11-29T15:50:48.123456" |
| `source` | Data source | "mcs" |

## Performance

Expected performance characteristics:

- **Scraping Speed**: ~2,200 installers in 15-30 minutes
- **Rate Limiting**: 1-2 second delay between page loads
- **Headless Mode**: ~20% faster than non-headless
- **Memory**: Typically <500MB for full MCS dataset

## Error Handling

The scraper implements robust error handling:

1. **Individual Record Failures**: Skip broken/incomplete records and log them
2. **Page Load Timeouts**: Retry with exponential backoff (3 attempts by default)
3. **Network Errors**: Gracefully handle connection issues and log details
4. **Stale Element References**: Catch Selenium stale reference errors and continue
5. **Missing Fields**: Mark missing fields as `null` and continue

All errors are logged to the log file with context for troubleshooting.

## Extensibility

### Adding a New Data Source

1. Create a new scraper class inheriting from `DataSource`:
```python
from src.core.data_source import DataSource

class MySourceScraper(DataSource):
    def scrape(self) -> List[Installer]:
        # Implement scraping logic
        pass
```

2. Create a configuration file for your source

3. Update `src/main.py` to recognize your scraper:
```python
if config.name == "my-source":
    scraper = MySourceScraper(config)
```

### Adding New Output Formats

Extend the `OutputHandler` class:
```python
@staticmethod
def to_json(data: List[Installer], output_path: str) -> Path:
    # Implement JSON export
    pass
```

### Custom Data Enrichment

Implement LLM enrichment in your scraper:
```python
def enrich_with_llm(self, data: List[Installer]) -> List[Installer]:
    if not self.config.enable_llm_enrichment:
        return data

    # Call LLM API to enrich data
    return enriched_data
```

## Troubleshooting

### Chrome Driver Issues

If you encounter chromedriver errors:
```bash
# webdriver-manager should auto-download, but you can manually specify:
export CHROMEDRIVER_PATH=/path/to/chromedriver
python -m src.main --config config/mcs_config.json
```

### Selenium Timeout Errors

Increase the timeout in the configuration:
```json
{
  "timeout": 60
}
```

### High Failure Rates

1. Increase `retry_attempts` in config
2. Increase `request_delay` to be more respectful to the server
3. Check logs for specific error patterns

### Memory Usage

For very large datasets, process in batches and clear memory:
```python
# Implement in scraper if needed
if len(self.installers) > 5000:
    self._flush_and_save()
    self.installers = []
```

## Rate Limiting & Respect

The scraper includes built-in rate limiting:
- Default 1.5 second delay between page loads
- Headless browser to reduce server load
- Exponential backoff on retries
- No concurrent requests

Please respect the target website's robots.txt and terms of service.

## Future Enhancements

Planned features for future phases:

1. **Additional Data Sources**:
   - Facebook Ads Library
   - Google Ads API
   - Other installer directories

2. **Output Formats**:
   - JSON export
   - SQLite/PostgreSQL database output
   - HTML reports

3. **LLM Enrichment**:
   - Phone number standardization (E.164)
   - Company name normalization
   - Address parsing and standardization

4. **UI**:
   - Web-based configuration builder
   - Real-time scraping dashboard
   - Results visualization

5. **Data Quality**:
   - Deduplication across sources
   - Data quality scoring
   - Validation rules engine

## License

This project is provided as-is for authorized use only.

## Support

For issues, feature requests, or contributions, please refer to the project repository.

## Notes

- Phase 1 focuses on MCS only; architecture is designed to scale
- Configuration-driven approach allows easy customization
- Error handling prioritizes data collection (skip bad records, continue)
- All external dependencies are pinned to specific versions for reproducibility
