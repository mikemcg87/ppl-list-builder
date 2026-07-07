# Pipeline Runbook

This is the current operating map for the prospect-list pipeline. Older docs describe the original heat-pump scraper; this file is the concise command reference.

## Niche Configs

| Config | Status | Notes |
| --- | --- | --- |
| `config/mcs_config.json` | Reference | Heat pumps, MCS source, BUS quality signal |
| `config/solar_pv.json` | Runnable | Solar PV, MCS source, MCS registration quality signal |
| `config/mortgage_brokers.json` | Runnable | Mortgage brokers, FCA register API source, FCA authorisation quality signal. Needs free `FCA_API_EMAIL`/`FCA_API_KEY` in `.env` (signup: https://register.fca.org.uk/Developer/s/). Name-search seeded, then permission-filtered; excludes Appointed Representatives |
| `config/commercial_finance_brokers.json` | Stub | Needs NACFB/FCA/Companies House source builder |
| `config/windows_doors.json` | Stub | Needs FENSA source builder |

## Standard Flow

1. Build source list:

```bash
python3 -m src.main --config config/solar_pv.json
```

2. Enrich Companies House:

```bash
python3 scripts/enrich_companies.py --niche config/solar_pv.json --platforms companies_house
```

3. Enrich Facebook Ads, if ScrapeCreators budget allows:

```bash
python3 scripts/enrich_companies.py --niche config/solar_pv.json --platforms facebook
```

4. Build tiers:

```bash
python3 scripts/build_prospect_tiers.py --niche config/solar_pv.json
```

5. Resolve PLATINUM domains with Brave:

```bash
python3 scripts/find_domains.py --niche config/solar_pv.json --tier PLATINUM --provider brave
```

6. Enrich Google Ads by existing domain:

```bash
python3 scripts/enrich_companies.py --niche config/solar_pv.json --platforms google --filter-tier PLATINUM
```

7. Hunter only for capped PLATINUM batches:

```bash
python3 scripts/enrich_companies.py --niche config/solar_pv.json --platforms hunter --filter-tier PLATINUM --limit 20
```

## Command Shortcuts

Use `make help` for common commands. The Makefile intentionally wraps only safe/local commands plus tier/domain helpers. It does not run paid enrichers by default.

## Canonical Scripts

Use these first:

- `src/main.py`: source scrape entrypoint.
- `scripts/enrich_companies.py`: Companies House, Facebook Ads, Google Ads by domain, Hunter.
- `scripts/build_prospect_tiers.py`: tier assignment.
- `scripts/find_domains.py`: Brave-first domain discovery.
- `scripts/ghl_import.py` and `scripts/push_to_notion.py`: downstream exports when needed.

Likely legacy or exploratory scripts:

- `scripts/enrich_google_ads.py`
- `scripts/test_selenium_ads.py`
- `scripts/rank_and_filter.py`
- `scripts/finalize_csv.py`

Do not delete legacy scripts casually; mark or replace them once a canonical command covers the same workflow.

## Verification

Run:

```bash
python3 -m unittest discover
python3 -m py_compile src/main.py src/core/models.py src/scrapers/mcs_scraper.py src/scrapers/fca_scraper.py scripts/build_prospect_tiers.py scripts/find_domains.py scripts/enrich_companies.py
python3 -m src.main --help
python3 scripts/enrich_companies.py --help
python3 scripts/build_prospect_tiers.py --help
python3 scripts/find_domains.py --help
```
