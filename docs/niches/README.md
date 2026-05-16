# Niche Onboarding Playbook

This repo now treats heat pumps as the reference niche, not the only niche.
The universal pipeline is:

1. Build a source-of-truth CSV from a niche directory or clean register.
2. Enrich company identity through Companies House.
3. Enrich current demand signals through Facebook Ads and Google Ads.
4. Resolve missing domains with Brave Search only by default.
5. Build PLATINUM/GOLD/SILVER/BRONZE/SKIP tiers from the niche config.
6. Use Hunter only for `PLATINUM` rows, and only when explicitly requested.

## Current Niche Shortlist

| Niche | Verdict | Source-of-truth approach | Why it fits Second Wind |
| --- | --- | --- | --- |
| Solar PV | Implemented second reference vertical | MCS installer directory filtered to Solar PV | £5k-£15k installs, heavy lead-gen activity, easy dead-quote reactivation angle |
| Mortgage brokers | Stubbed | FCA Financial Services Register, then Companies House | High commissions, sales teams, large stale enquiry databases, but source ingestion needs FCA-specific handling |
| Windows, doors, conservatories | Stubbed | FENSA approved installer directory, possibly TrustMark/FENSA cross-check | High competition and big historic lead databases, but lower average ticket and noisier operators |
| Commercial finance brokers | Stubbed | NACFB member directory plus Companies House | B2B, high lifetime value, CRM-heavy sales process, but less obvious consumer-style ad-spend signal |

Rejected for this pass:

- Personal injury solicitors: high value, but SRA/FCA-style regulated sourcing and claims-management filtering make it a separate compliance-heavy build.
- Commercial cleaning: recurring B2B value, but no clean universal register and ad-spend signals are weaker.
- Boiler replacement: good volume, but lower ticket and no source as clean as MCS Solar PV.

## Universal vs Niche-Specific

Universal enrichers:

- `src/enrichers/companies_house.py`: generic UK registered-company and director lookup.
- `src/enrichers/facebook_ads.py`: generic company-name ad lookup via ScrapeCreators.
- `src/enrichers/google_ads_domain.py`: generic domain-based Google Ads lookup via ScrapeCreators.
- `scripts/find_domains.py`: generic Brave-first domain resolution.
- `src/enrichers/hunter.py`: generic email finder, but rate-constrained and only for `PLATINUM`.

Niche-specific pieces:

- Source scraper or ingestion adapter.
- `config/<niche>.json`.
- `tiering.primary_quality_signal`, for example `bus_registered` for heat pumps and `mcs_registered` for Solar PV.
- Domain search terms in `search_terms`.

## Per-Niche Tiering Template

Use this shape in `config/<niche>.json`:

```json
{
  "niche": "example_niche",
  "display_name": "Example Niche",
  "search_terms": ["example service", "UK"],
  "tiering": {
    "primary_quality_signal": "source_verified",
    "required_status_column": "ch_company_status",
    "required_status_value": "active",
    "required_director_column": "ch_primary_director",
    "score_weights": {
      "primary_quality_signal": 30,
      "facebook_ads_running": 40,
      "google_ads_running": 30,
      "multiple_directors": 15,
      "named_director": 5
    }
  }
}
```

Tier meanings:

- `PLATINUM`: active company, named director, trusted source signal, and active Facebook or Google ads.
- `GOLD`: active company, named director, trusted source signal, no ads found.
- `SILVER`: active company, named director, ads found, weak/missing source signal.
- `BRONZE`: active company with named director only.
- `SKIP`: no Companies House match, dissolved/inactive company, or no named decision maker.

## API Cost Per 1,000 Prospects

| Service | Usage | Cost profile |
| --- | --- | --- |
| MCS/source scraping | 1 directory scrape | Free, but browser-based and site-fragile |
| Companies House | About 2 requests per company | Free, rate-limited to 600 requests per 5 minutes |
| Brave Search | Only missing-domain rows, usually top tiers | Free tier allows about 2,000 queries/month |
| ScrapeCreators Facebook Ads | 1 company search plus 1 ads request per enriched company | Paid by account plan/credit balance; watch volume before full-list runs |
| ScrapeCreators Google Ads | 1 domain ads request per company with a domain | Paid by account plan/credit balance; run after Brave/domain capture |
| Hunter.io | `PLATINUM` only, max small tests | Free tier is near limit; not part of broad enrichment |
| SerpApi | Avoid | Near limit; only available through explicit `google_serpapi` opt-in |

Practical default for 1,000 new prospects: Companies House across all rows, Facebook Ads across all rows if ScrapeCreators budget permits, Brave only for missing top-tier domains, Google Ads only where a domain exists, Hunter only for a capped `PLATINUM` batch.

## Runbook

Solar PV source scrape:

```bash
python -m src.main --config config/solar_pv.json
```

For Solar PV, `config/solar_pv.json` sets `pipeline.auto_build_tiers = true`, so the same command writes `output/solar-pv-prospects-tiered.csv` after scraping. If `COMPANIES_HOUSE_API_KEY` is present, it enriches director/status data before tiering. Paid ScrapeCreators ad enrichment is not run from `src.main` unless `pipeline.run_paid_enrichers` is set to `true`.

Companies House:

```bash
python scripts/enrich_companies.py --niche config/solar_pv.json --platforms companies_house
```

Facebook Ads:

```bash
python scripts/enrich_companies.py --niche config/solar_pv.json --platforms facebook
```

Tiering:

```bash
python scripts/build_prospect_tiers.py --niche config/solar_pv.json
```

Domain discovery for PLATINUM only, Brave-first:

```bash
python scripts/find_domains.py --niche config/solar_pv.json --tier PLATINUM --provider brave
```

Google Ads by resolved domain:

```bash
python scripts/enrich_companies.py --niche config/solar_pv.json --platforms google --filter-tier PLATINUM
```

Hunter, only after tiering:

```bash
python scripts/enrich_companies.py --niche config/solar_pv.json --platforms hunter --filter-tier PLATINUM --limit 20
```

## Adding the Next Niche

1. Confirm source availability before coding: public directory, regulator register, or Companies House SIC strategy.
2. Create `config/<niche>.json` by copying `config/solar_pv.json`.
3. Set `pipeline.*` output paths so runs do not overwrite heat-pump or solar output.
4. Set `tiering.primary_quality_signal` to the source trust flag produced by the scraper.
5. Add or update a source scraper only if an existing adapter cannot produce `company_name`, `website`, `phone`, `location`, `source`, `niche`, and the trust flag.
6. Run a small source scrape first, then Companies House, then tiering.
7. Only expand ads enrichment once the source and Companies House match rate look sane.
