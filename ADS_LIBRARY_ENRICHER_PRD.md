# Ads Library Enricher - Product Requirements Document

## Project Overview

**Name:** Ads Library Enricher
**Purpose:** Enrich company lists (CSV format) with advertising data from multiple platforms (Facebook, Google, LinkedIn, etc.)
**Phase 1 Focus:** Facebook Ads Library enrichment using ScrapeCreators API
**Input:** CSV files with company data (company_name, website, etc.)
**Output:** Same CSV with new ad platform columns appended

---

## Use Case

A user has a CSV spreadsheet with company names and websites. They want to know:
- Is this company running Facebook ads?
- How many active ads do they have?
- What's their estimated ad spend?
- When was the company last running ads?

By enriching the CSV with this data, they can identify high-intent companies (those actively spending on customer acquisition) and prioritize outreach.

**Example:**
```
Input CSV:
company_name, website, phone, location, bus_registered, certifications, scraped_at, source
Green Energy Ltd, https://greenergyltd.co.uk, 01234567890, London, True, [...], 2025-11-29, mcs

Output CSV (after enrichment):
company_name, website, phone, location, bus_registered, certifications, scraped_at, source,
facebook_ads_running, facebook_ads_count, facebook_ads_status, facebook_spend_estimate, facebook_last_updated, facebook_enriched_at
Green Energy Ltd, https://greenergyltd.co.uk, 01234567890, London, True, [...], 2025-11-29, mcs,
True, 5, active, £1200-1500, 2025-11-28, 2025-11-30T14:32:00
```

---

## Architecture

### Core Design Pattern: BaseEnricher

All enrichers inherit from an abstract `BaseEnricher` class:

```python
class BaseEnricher(ABC):
    def __init__(self, config: Dict = None):
        self.platform_name = ""  # "facebook", "google", etc.

    @abstractmethod
    def enrich_row(self, row: Dict) -> Dict:
        """Enrich a single company row with ads data"""
        pass

    def read_csv(self, input_path: str) -> pd.DataFrame:
        """Read input CSV"""

    def enrich_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        """Enrich all rows, handle errors, skip already-enriched"""

    def write_csv(self, df: pd.DataFrame, output_path: str):
        """Write enriched CSV"""
```

### Naming Convention

Each enricher adds columns with a consistent prefix: `[platform]_[field]`

**Facebook enricher columns:**
- `facebook_ads_running` (boolean: True/False/None)
- `facebook_ads_count` (integer: number of active ads)
- `facebook_ads_status` (string: "active", "paused", "none")
- `facebook_spend_estimate` (string: e.g., "£1,200-1,500")
- `facebook_last_updated` (datetime: when ads were last updated)
- `facebook_enriched_at` (datetime: when enrichment was run)
- `facebook_enrichment_error` (string, optional: error message if enrichment failed)

This pattern allows multiple enrichers to coexist without column conflicts:
- `facebook_ads_running`, `facebook_ads_count`, ...
- `google_ads_running`, `google_ads_count`, ...
- `linkedin_ads_running`, `linkedin_ads_count`, ...

---

## Phase 1 Implementation: FacebookAdsEnricher

### Scope

Build the `FacebookAdsEnricher` class that:
1. Takes a CSV with company data
2. For each company, queries ScrapeCreators Facebook Ads Library API
3. Appends ads data columns to the CSV
4. Handles errors gracefully (bad data, API timeouts, missing companies)
5. Supports resume capability (skip already-enriched rows)
6. Outputs enriched CSV to file

### Input CSV Structure

**Required columns:**
- `company_name` (string): Company name to search
- `website` (string, optional): Website URL (can be used as fallback search term)

**All other columns from source:** Pass through unchanged (phone, location, certifications, etc.)

**Example input:**
```
company_name,website,phone,location,bus_registered,certifications,scraped_at,source
Green Energy Ltd,https://greenergyltd.co.uk,01234567890,London,True,"[Air Source, Ground Source]",2025-11-29T17:00:00,mcs
Eco Heat Solutions,https://ecoheat.uk,01234567891,Manchester,True,"[Air Source]",2025-11-29T17:01:00,mcs
```

### API Integration: ScrapeCreators

**Service:** ScrapeCreators Facebook Ads Library API
**Base URL:** `https://api.scrapecreators.com/`
**Endpoint:** `GET /facebookAdLibrary/search`
**Authentication:** API Key (passed as `token` parameter)
**Pricing:** $1.88 per 1,000 requests (PAYG)
**Rate Limiting:** Unknown — test with 50 requests first, monitor response times

**API Parameters:**
```
query: string (company name or domain)
limit: integer (10 suggested)
token: string (API key)
```

**Expected Response Structure:**
```json
{
  "results": [
    {
      "id": "ad_12345",
      "company": "Green Energy Ltd",
      "status": "active",
      "ad_count": 5,
      "impressions": 125000,
      "spend_estimate": "£1,200-1,500",
      "created_date": "2025-11-01",
      "last_updated": "2025-11-29"
    }
  ],
  "total_results": 1,
  "query_success": true
}
```

**Search Strategy:**
1. **Primary search:** By company name (exact match)
2. **Fallback search:** By domain extracted from website URL (if provided)
3. **No results:** Mark row with `facebook_ads_running: False` (company not running ads, not an error)

### Output CSV Structure

**Original columns + new Facebook columns:**
```
company_name,website,phone,location,bus_registered,certifications,scraped_at,source,
facebook_ads_running,facebook_ads_count,facebook_ads_status,facebook_spend_estimate,facebook_last_updated,facebook_enriched_at
```

**Data types:**
- `facebook_ads_running`: boolean (True/False/None for error)
- `facebook_ads_count`: integer (0 if no ads)
- `facebook_ads_status`: string ("active", "paused", "none")
- `facebook_spend_estimate`: string (as returned by API, e.g., "£1,200-1,500")
- `facebook_last_updated`: datetime string (ISO format)
- `facebook_enriched_at`: datetime string (ISO format, when enrichment ran)
- `facebook_enrichment_error`: string (optional, only if error occurred)

---

## Implementation Details

### FacebookAdsEnricher Class

**Location:** `src/enrichers/facebook_ads.py`

**Key Methods:**

1. **`__init__(api_key: str, config: Dict = None)`**
   - Store API key
   - Set `platform_name = "facebook"`
   - Initialize config (retry attempts, timeout, etc.)

2. **`enrich_row(row: Dict) -> Dict`**
   - Input: Dict with `company_name`, `website`, etc.
   - Output: Same dict + facebook_* columns
   - Logic:
     - Validate company_name (skip if empty)
     - Extract domain from website URL (fallback search)
     - Call ScrapeCreators API with company name
     - Parse response, extract relevant fields
     - Handle "no results" (return ads_running=False, not an error)
     - Handle API errors (return None for ads_running, add error message)

3. **`enrich_dataset(df: DataFrame) -> DataFrame`** (inherited from BaseEnricher)
   - Iterate through all rows
   - Skip rows already enriched (check `facebook_enriched_at` column)
   - Call `enrich_row()` for each row
   - Log progress
   - Handle per-row errors gracefully (don't fail entire dataset)
   - Return enriched DataFrame

4. **`write_csv(df: DataFrame, output_path: str)`** (inherited from BaseEnricher)
   - Write enriched DataFrame to CSV
   - UTF-8 encoding
   - Preserve all columns (original + new)

### Base Implementation: BaseEnricher

**Location:** `src/enrichers/base_enricher.py`

```python
from abc import ABC, abstractmethod
import pandas as pd
import logging
from datetime import datetime

logger = logging.getLogger("ppl-list-builder")

class BaseEnricher(ABC):
    """Abstract base class for all data enrichers."""

    def __init__(self, config: Dict = None):
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

    def enrich_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Enrich all rows in the dataset.

        - Skips rows already enriched by this platform
        - Handles per-row errors gracefully
        - Logs progress
        """
        enriched_rows = []

        for idx, row in df.iterrows():
            try:
                # Skip if already enriched by this platform
                enriched_col = f"{self.platform_name}_enriched_at"
                if enriched_col in df.columns and pd.notna(row.get(enriched_col)):
                    logger.debug(f"Row {idx} already enriched by {self.platform_name}")
                    enriched_rows.append(row.to_dict())
                    continue

                # Enrich the row
                enriched_row = self.enrich_row(row.to_dict())
                enriched_rows.append(enriched_row)

                company = enriched_row.get('company_name', 'Unknown')
                logger.info(f"[{idx+1}/{len(df)}] Enriched: {company}")

            except Exception as e:
                logger.error(f"Error enriching row {idx}: {e}")
                # Add error info instead of failing
                row[f"{self.platform_name}_enrichment_error"] = str(e)
                enriched_rows.append(row.to_dict())

        return pd.DataFrame(enriched_rows)

    def write_csv(self, df: pd.DataFrame, output_path: str):
        """Write enriched CSV."""
        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"Wrote enriched data to {output_path}")
```

### Error Handling

**API Errors:**
- Timeout (30 sec default): Retry up to 3 times with exponential backoff (1s, 2s, 5s)
- Rate limit (429): Pause 5 minutes, resume from last successful row
- Invalid API key: Fail early with helpful message
- Connection error: Log and continue to next row

**Data Errors:**
- Missing `company_name`: Skip row, log warning
- Empty API response (no ads found): `facebook_ads_running = False` (not an error)
- Malformed API response: Log error, mark row with error flag

**Resume Capability:**
- Check for `facebook_enriched_at` column
- If present and not null, skip that row (already enriched)
- If resuming interrupted run, start from first row without this column

---

## CLI Interface

**Script location:** `scripts/enrich_companies.py`

**Basic usage:**
```bash
python scripts/enrich_companies.py \
    --input output/heat-pump-installers.csv \
    --output output/heat-pump-installers-enriched.csv \
    --platforms facebook \
    --api-key YOUR_SCRAPECREATORS_KEY
```

**Full options:**
```bash
python scripts/enrich_companies.py \
    --input INPUT_CSV \
    --output OUTPUT_CSV \
    --platforms [facebook, google, linkedin] \
    --api-key API_KEY \
    --limit 50 \               # (optional) Test mode: enrich only first 50 rows
    --log-level [DEBUG, INFO, WARNING, ERROR] \  # (optional, default: INFO)
    --log-dir logs             # (optional, default: logs)
    --resume                   # (optional) Skip already-enriched rows
```

**Examples:**

Test mode (first 50 companies):
```bash
python scripts/enrich_companies.py \
    --input output/heat-pump-installers.csv \
    --output output/test-enriched.csv \
    --platforms facebook \
    --api-key YOUR_KEY \
    --limit 50
```

Full run:
```bash
python scripts/enrich_companies.py \
    --input output/heat-pump-installers.csv \
    --output output/heat-pump-installers-enriched.csv \
    --platforms facebook \
    --api-key YOUR_KEY
```

Resume after interruption:
```bash
python scripts/enrich_companies.py \
    --input output/heat-pump-installers.csv \
    --output output/heat-pump-installers-enriched.csv \
    --platforms facebook \
    --api-key YOUR_KEY \
    --resume
```

**Output:**
- Success: "✓ Enrichment complete! Results saved to [output_path]"
- Console logging during run (progress, errors)
- Log file: `logs/ppl-list-builder.log` with detailed info

---

## File Structure

```
ppl-list-builder/
├── src/
│   ├── enrichers/
│   │   ├── __init__.py
│   │   ├── base_enricher.py       # Abstract base class
│   │   └── facebook_ads.py        # Facebook Ads enricher (Phase 1)
│   ├── core/
│   │   ├── models.py              # (existing) Pydantic models
│   │   ├── config.py              # (existing)
│   │   └── ...
│   └── ...existing files...
├── scripts/
│   ├── enrich_companies.py        # CLI entry point (NEW)
│   └── ...existing scripts...
├── output/
│   ├── heat-pump-installers.csv                    # MCS scraper output (existing)
│   └── heat-pump-installers-enriched.csv           # Enricher output (NEW)
├── logs/
│   └── ppl-list-builder.log
├── .env                           # API keys (DO NOT COMMIT)
└── ...
```

---

## Implementation Checklist

### Phase 1: Facebook Ads Enricher

- [ ] Create `src/enrichers/base_enricher.py` with BaseEnricher abstract class
- [ ] Create `src/enrichers/facebook_ads.py` with FacebookAdsEnricher implementation
- [ ] Create `scripts/enrich_companies.py` CLI script
- [ ] Update `.env.example` with SCRAPECREATORS_API_KEY placeholder
- [ ] Add error handling (timeouts, API errors, validation)
- [ ] Add resume capability (skip already-enriched rows)
- [ ] Add progress logging
- [ ] Test with first 50 companies
- [ ] Run on full dataset (2,200 companies)
- [ ] Verify output CSV has correct columns and data

### Phase 2 (Future): Add More Enrichers

- [ ] Create `src/enrichers/google_ads.py` with GoogleAdsEnricher
- [ ] Create `src/enrichers/linkedin_ads.py` with LinkedInAdsEnricher
- [ ] Update CLI to support multiple enrichers
- [ ] Combine enricher outputs

---

## Success Criteria

✅ **Functional:**
- Input: `heat-pump-installers.csv` (from MCS scraper, ~2,200 rows)
- Process: For each company, query Facebook Ads Library API
- Output: Same CSV with 6 new columns (facebook_ads_*)

✅ **Performance:**
- Complete enrichment of 2,200 companies in <2 hours
- Reasonable API response times (<5 sec per request)

✅ **Reliability:**
- Handle API timeouts/errors gracefully
- Resume capability works (skip already-enriched)
- Detailed logging of all actions

✅ **Code Quality:**
- Modular design (BaseEnricher extensible for future platforms)
- Clean error handling
- Type hints throughout
- Pydantic models for config (if needed)

✅ **Testability:**
- Test mode: `--limit 50` to enrich only first 50 rows
- Log all API requests/responses for debugging
- Verify output CSV structure and data types

---

## Notes for Implementation

1. **API Key Management:**
   - Store in `.env` file (never commit)
   - Read at runtime: `api_key = os.getenv('SCRAPECREATORS_API_KEY')`
   - Provide example in `.env.example`

2. **Pandas CSV Handling:**
   - Read: `pd.read_csv(input_path)`
   - Write: `df.to_csv(output_path, index=False, encoding='utf-8')`
   - Preserve all columns from input

3. **Datetime Handling:**
   - Use `datetime.now().isoformat()` for timestamps
   - Parse API responses (if they return datetime strings)
   - Store as strings in CSV (ISO format)

4. **Logging:**
   - Use Python's `logging` module
   - Reuse existing logger from `src.utils.logging`
   - Log to file + console

5. **Dependencies:**
   - pandas (already in project)
   - requests (for API calls)
   - python-dotenv (for .env loading)
   - pydantic (already in project, optional for config)

6. **Testing:**
   - Before full run, test with `--limit 50`
   - Verify API response structure matches assumptions
   - Check output CSV for correct columns and data
   - Spot-check 5-10 companies manually

---

## Deliverables

1. ✅ `src/enrichers/base_enricher.py` — Abstract base class
2. ✅ `src/enrichers/facebook_ads.py` — Facebook enricher implementation
3. ✅ `scripts/enrich_companies.py` — CLI script
4. ✅ `.env.example` — Example environment variables
5. ✅ Updated `requirements.txt` with new dependencies
6. ✅ Enriched CSV output: `output/heat-pump-installers-enriched.csv`
7. ✅ README section explaining how to use the enricher

---

## Future Extensibility

This design is built to support additional enrichers without refactoring:

**Adding Google Ads Enricher (example):**
```python
class GoogleAdsEnricher(BaseEnricher):
    def __init__(self, api_key: str = None):
        super().__init__()
        self.platform_name = "google"
        # Implement enrich_row() with Google API logic
```

**Using it:**
```bash
python scripts/enrich_companies.py \
    --input output/heat-pump-installers.csv \
    --output output/heat-pump-installers-fully-enriched.csv \
    --platforms facebook google
```

The pipeline automatically:
- Runs FacebookAdsEnricher (adds facebook_* columns)
- Runs GoogleAdsEnricher (adds google_* columns)
- Returns single CSV with all columns combined
