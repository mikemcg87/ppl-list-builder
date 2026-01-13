# PPL List Builder - Product Requirements Document

## Project Vision

**PPL List Builder** is an extensible, general-purpose data scraping and aggregation framework designed to collect installer/professional lists from multiple sources. Phase 1 focuses on scraping UK heat pump installers from the MCS Directory. The framework is architected to support future extensions including Facebook Ads Library, Google Ads API, and LLM-powered data enrichment.

---

## Phase 1 Scope: MCS Heat Pump Installer List Scraper

### Functional Requirements

#### 1. Web Scraping
- Navigate to: https://www.mcscertified.com/find-an-installer
- Apply filters:
  - Air Source Heat Pump
  - Exhaust Air Heat Pump
  - Ground/Water Source Heat Pump
- Handle JavaScript-based pagination (~186 pages, ~12 results per page = ~2,200 installers)
- Click "VIEW DETAILS" on each installer card to access additional information

#### 2. Data Extraction (per installer)
Extract the following fields per installer:
- **Company Name** (visible on list)
- **Website URL** (from details page)
- **Phone Number** (from details page)
- **Location/Address** (from details page)
- **BUS Registration Status** (Yes/No - from details page)
- **Heat Pump Certifications** (Air Source, Ground/Water, Exhaust - visible on list)

#### 3. Data Collection Process
- Iterate through all paginated pages
- For each installer card: extract visible data
- Click "VIEW DETAILS" to access detailed information
- Return to list and continue to next page
- Handle duplicates (prevent re-scraping)
- Log progress and errors

#### 4. Output
- **Format**: CSV file (`heat-pump-installers.csv`)
- **Columns**: Company Name | Website | Phone | Location | BUS Registered | Certifications
- **No duplicates** (validated by company name or ID)
- Optional sorting by company name

---

## Technical Architecture

### Technology Stack
- **Language**: Python 3.9+
- **Web Automation**: Selenium with ChromeDriver
- **Data Modeling**: Pydantic v2
- **Dependencies**: selenium, webdriver-manager, pandas, pydantic
- **Optional**: OpenAI API or similar (for LLM enrichment - Phase 1 optional)

### Core Architecture Design

```
ppl-list-builder/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── models.py           # Pydantic models for data structures
│   │   ├── data_source.py      # Abstract base class for data sources
│   │   ├── config.py           # Configuration model and loading
│   │   └── output.py           # Output handlers (CSV, future: JSON, DB)
│   ├── scrapers/
│   │   ├── __init__.py
│   │   └── mcs_scraper.py      # MCS-specific scraper implementation
│   ├── utils/
│   │   ├── logging.py          # Logging setup
│   │   ├── retry.py            # Retry logic and error handling
│   │   └── helpers.py          # General utility functions
│   └── main.py                 # CLI entry point
├── config/
│   └── mcs_config.json         # MCS scraper configuration
├── tests/
│   └── test_mcs_scraper.py     # Basic tests
├── requirements.txt
└── README.md
```

### Data Models (Pydantic)

#### Core Data Model
```python
class Installer(BaseModel):
    company_name: str
    website: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    bus_registered: bool  # Yes/No
    certifications: List[str]  # ["Air Source", "Ground/Water", "Exhaust"]

    # Metadata
    scraped_at: datetime
    source: str = "mcs"
```

#### Filter Model
```python
class FilterConfig(BaseModel):
    heat_pump_types: List[str]  # ["Air Source", "Exhaust Air", "Ground/Water"]
    location: Optional[str] = None  # Future: postcode/region filtering
```

#### Scraper Configuration
```python
class ScraperConfig(BaseModel):
    name: str  # "mcs"
    url: str
    filters: FilterConfig
    output_format: str = "csv"  # csv, json, db (future)
    enable_llm_enrichment: bool = False  # Optional LLM cleanup/validation
    request_delay: float = 1.5  # Seconds between page loads
    retry_attempts: int = 3
    timeout: int = 30
    headless: bool = True
```

### Configuration System

The scraper is configured via JSON:

**`config/mcs_config.json`**:
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

Configuration is loaded and validated using Pydantic at startup.

---

## Functional Details

### 1. Data Source Abstraction

Create an abstract `DataSource` base class that all scrapers inherit from:

```python
class DataSource(ABC):
    def __init__(self, config: ScraperConfig):
        self.config = config

    @abstractmethod
    def scrape(self) -> List[Installer]:
        """Execute the scraping process."""
        pass

    def validate_data(self, data: List[Installer]) -> List[Installer]:
        """Validate and clean extracted data."""
        pass

    def enrich_with_llm(self, data: List[Installer]) -> List[Installer]:
        """Optional: Enrich data using LLM (if enabled)."""
        pass
```

MCS scraper inherits from `DataSource`.

### 2. MCS Scraper Implementation

**Key requirements**:
- Use Selenium to navigate and interact with the MCS site
- Handle JavaScript-rendered content
- Extract visible data from installer cards
- Click "VIEW DETAILS" to fetch additional data
- Handle pagination (next page button)
- Implement robust error handling for missing/broken data
- Add delays between requests (respect rate limiting: 1-2 seconds)
- Log all actions and errors
- Support checkpoint/restart if scraping fails mid-run

**Error Handling**:
- Skip individual broken/incomplete records (log them)
- Retry failed page loads up to `retry_attempts` times
- Timeout after `timeout` seconds per page
- Log all errors to file with timestamp and context

### 3. Output Handler (CSV)

- Use pandas for CSV output
- Columns: Company Name | Website | Phone | Location | BUS Registered | Certifications
- Handle special characters and encoding (UTF-8)
- Deduplicate by company name (case-insensitive)
- Optional: Sort by company name alphabetically
- File location: `output/heat-pump-installers.csv` (or configurable)

### 4. Optional LLM Enrichment (Phase 1: Low Priority)

If `enable_llm_enrichment: true` in config:
- After scraping, pass installer records to LLM
- Use LLM to:
  - Validate phone numbers (E.164 format)
  - Standardize company names (remove redundant words)
  - Extract or clean addresses
  - Flag suspicious/incomplete records
- Log LLM operations
- Gracefully degrade if LLM API unavailable

---

## Non-Functional Requirements

### Performance
- Complete scraping of ~2,200 installers in 15-30 minutes
- Respect rate limiting (1-2 second delays between page loads)
- Use headless browser for speed

### Reliability
- Robust error handling (skip broken records, retry on timeout)
- Detailed logging to file and stdout
- Support restart/checkpoint (ability to resume from failed page)
- Handle network timeouts gracefully

### Code Quality
- Modular, pluggable architecture
- Type hints throughout (Python)
- Clear separation of concerns (scraping, validation, output)
- Extensible for future data sources

### Constraints
- Don't hammer the MCS server (rate limiting essential)
- Respect robots.txt / terms of service
- No authentication required (public-facing directory)
- Headless browser preferred for speed

---

## Extensibility Points (Not Phase 1, but design for these)

The framework is designed to support future extensions without major refactoring:

1. **New Data Sources**
   - Implement new scrapers by inheriting from `DataSource`
   - Example: Facebook Ads Library, Google Ads API, other installer directories

2. **New Filters**
   - Add fields to `FilterConfig` model
   - Implement filter logic in scraper's filter application

3. **New Output Formats**
   - Create new output handlers: JSON, SQLite, PostgreSQL, HTML reports
   - Interface: `OutputHandler` abstract class

4. **LLM Integration**
   - Optional enrichment/validation of extracted data
   - Pluggable LLM provider (OpenAI, Anthropic, etc.)

5. **UI Configuration**
   - Current: JSON config files
   - Future: Web UI to build/edit configs, run scrapers, view results

---

## Success Criteria for Phase 1

1. ✅ Successfully scrapes all ~2,200 MCS heat pump installers
2. ✅ Extracts all required fields (company name, website, phone, location, BUS status, certifications)
3. ✅ Outputs clean CSV file with no duplicates
4. ✅ Completes in 15-30 minutes with proper rate limiting
5. ✅ Comprehensive error logging (handles broken records gracefully)
6. ✅ Code is modular and extensible (easy to add new scrapers)
7. ✅ Configuration is managed via JSON (Pydantic validated)
8. ✅ Optional LLM enrichment doesn't break anything if disabled

---

## Deliverables

1. **Runnable Python application** with CLI entry point
2. **CSV output file** with all installers
3. **Configuration file** (JSON) for scraper settings
4. **Error log** documenting any issues during scraping
5. **README** with setup, usage, and architecture overview
6. **Tests** validating scraper logic and data model integrity

---

## Notes

- Phase 1 focuses on MCS only; don't overengineer for future sources yet
- Architecture should be flexible enough to add sources/features without major refactoring
- CSV output is sufficient for now; can add JSON/DB exports later
- LLM enrichment is optional and should degrade gracefully if unavailable
- Keep error handling pragmatic (skip bad records, log them, continue)
