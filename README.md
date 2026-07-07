# PPL List Builder

Config-driven UK B2B prospect-intelligence pipeline for building reviewable, CRM-ready outreach lists from public source-of-truth directories.

The project started with UK heat-pump installers from the MCS directory, then expanded into a reusable pattern for additional verticals such as Solar PV. The emphasis is list quality, source validation, provider-cost control, and human review before outreach.

## What It Does

PPL List Builder turns a vertical source into a scored prospect workflow:

1. Scrape or ingest a source-of-truth directory.
2. Validate company identity through Companies House.
3. Enrich commercial signals such as Facebook/Google ad activity.
4. Resolve official domains with Brave-first discovery.
5. Score and tier prospects into `PLATINUM`, `GOLD`, `SILVER`, `BRONZE`, or `SKIP`.
6. Export reviewable lists for Notion and selected records for GHL/HighLevel.

Generated prospect data is not committed to this repo. Local `output/`, `logs/`, `exports/`, and private campaign notes are ignored.

## Why It Exists

The pipeline supports Flow Local's "Second Wind" offer: finding high-fit local service businesses likely to have stale enquiry databases and enough commercial value to justify reactivation campaigns.

It is intentionally human-in-the-loop. Automated scores help prioritise prospects, but manual review catches weak domains, wrong emails, poor-fit businesses, and contextual details useful for personalised outreach.

## Architecture

```mermaid
flowchart LR
  A["Source directory / register"] --> B["Niche scraper or ingestion adapter"]
  B --> C["Canonical prospect CSV"]
  C --> D["Companies House validation"]
  D --> E["Ad and domain enrichment"]
  E --> F["Tiering and lead scoring"]
  F --> G["Human QA in CSV/Notion"]
  G --> H["Selected import to GHL/HighLevel"]
```

## Current Verticals

| Config | Status | Source | Quality Signal |
| --- | --- | --- | --- |
| `config/mcs_config.json` | Reference | MCS installer directory | BUS registration |
| `config/solar_pv.json` | Runnable | MCS installer directory | MCS registration |
| `config/mortgage_brokers.json` | Runnable | FCA Financial Services Register API | FCA authorisation with mortgage permissions |
| `config/commercial_finance_brokers.json` | Stub | NACFB/FCA / Companies House | TBD |
| `config/windows_doors.json` | Stub | FENSA / TrustMark | TBD |

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m unittest discover
```

Run the Solar PV source scrape:

```bash
python3 -m src.main --config config/solar_pv.json
```

Run the mortgage-broker source build (needs free `FCA_API_EMAIL`/`FCA_API_KEY` in `.env`, signup at https://register.fca.org.uk/Developer/s/):

```bash
python3 -m src.main --config config/mortgage_brokers.json
```

Build prospect tiers from existing source and enrichment outputs:

```bash
python3 scripts/build_prospect_tiers.py --niche config/solar_pv.json
```

Resolve top-tier domains with Brave:

```bash
python3 scripts/find_domains.py --niche config/solar_pv.json --tier PLATINUM --provider brave
```

See [`docs/pipeline.md`](docs/pipeline.md) for the full operating runbook.
See [`docs/publication-checklist.md`](docs/publication-checklist.md) before publishing or linking this repo publicly.

Run the synthetic demo without any API keys:

```bash
make demo-tier
```

This writes `output/sample_prospects_tiered.csv` from the fake rows in `examples/`.

## Provider Cost Rules

The pipeline is deliberately conservative about paid providers:

- Companies House is the default identity-validation layer.
- Brave Search is the default domain-discovery provider.
- SerpApi is explicit opt-in only.
- Hunter is restricted to capped `PLATINUM` batches.
- ScrapeCreators ad enrichment should be run only when the account budget supports it.

## Key Files

| Path | Purpose |
| --- | --- |
| `src/main.py` | Source scrape CLI entrypoint |
| `src/scrapers/mcs_scraper.py` | Selenium scraper for the MCS installer directory |
| `src/scrapers/fca_scraper.py` | FCA Financial Services Register API source builder |
| `src/core/models.py` | Pydantic models and niche pipeline config |
| `scripts/enrich_companies.py` | Companies House, ad, Google Ads, and Hunter enrichment |
| `scripts/build_prospect_tiers.py` | Tiering and lead scoring |
| `scripts/find_domains.py` | Brave-first domain discovery |
| `scripts/push_to_notion.py` | Optional Notion review export |
| `scripts/ghl_import.py` | Optional GHL/HighLevel contact and opportunity import |
| `docs/niches/README.md` | Niche onboarding playbook |
| `examples/` | Synthetic demo data only |

## Public Data Policy

This repository should contain code, configs, docs, and synthetic examples only. Do not commit:

- scraped prospect CSVs;
- GHL import trackers;
- Hunter caches;
- campaign send queues;
- raw logs or screenshots;
- private cold-email drafts or live CRM prompt notes;
- API keys, location IDs, pipeline IDs, or stage IDs.

Use `.env` for local credentials and generated `output/` files for local data.

## Development

Run tests:

```bash
python3 -m unittest discover
```

Compile the main command surface:

```bash
python3 -m py_compile \
  src/main.py \
  src/core/models.py \
  src/scrapers/mcs_scraper.py \
  src/scrapers/fca_scraper.py \
  scripts/build_prospect_tiers.py \
  scripts/find_domains.py \
  scripts/enrich_companies.py
```

## Adding A New Vertical

1. Confirm the vertical has a reliable source: public directory, regulator register, trade body, or validated Companies House strategy.
2. Create `config/<niche>.json`.
3. Ensure the source builder emits `company_name`, `website`, `phone`, `location`, `source`, `niche`, and a trust signal.
4. Set `tiering.primary_quality_signal` for that vertical.
5. Run source scrape, Companies House validation, tiering, then limited enrichment.

Do not broaden paid enrichment until the source quality and Companies House match rate are sane.
