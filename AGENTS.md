# PPL List Builder Working Agreement

This repo builds UK B2B prospect lists for Second Wind/database-reactivation outreach. Keep changes focused on list quality, repeatable runs, and API-budget discipline.

## Canonical Pipeline

Use niche configs in `config/*.json`. Heat pumps are the original reference niche; Solar PV is the second reference niche.

Core commands:

- Test: `python3 -m unittest discover`
- Source scrape: `python3 -m src.main --config config/<niche>.json`
- Companies House: `python3 scripts/enrich_companies.py --niche config/<niche>.json --platforms companies_house`
- Facebook Ads: `python3 scripts/enrich_companies.py --niche config/<niche>.json --platforms facebook`
- Tiering: `python3 scripts/build_prospect_tiers.py --niche config/<niche>.json`
- Brave domains: `python3 scripts/find_domains.py --niche config/<niche>.json --tier PLATINUM --provider brave`
- Google Ads by domain: `python3 scripts/enrich_companies.py --niche config/<niche>.json --platforms google --filter-tier PLATINUM`

## API Budget Rules

- Brave Search is the default for domain discovery.
- Do not use SerpApi unless the user explicitly asks for it; the explicit opt-in path is `google_serpapi`.
- Do not run Hunter broadly. Hunter requires `--filter-tier PLATINUM`, and tests should be capped with `--limit`.
- Treat ScrapeCreators runs as spend-sensitive. Stop and ask before any single run may exceed £10.
- Companies House is free and safe to use, subject to rate limits.
- Never commit `.env` or API keys.

## Source Of Truth

- Niche configs live in `config/<niche>.json`.
- Current niche docs live in `docs/niches/`.
- Delivery/client-operation docs live in `docs/delivery/`.
- Generated CSVs and logs live in `output/` and `logs/`; do not rely on them as source code.
- If a script is exploratory or legacy, document that instead of deleting it during unrelated work.

## Adding A Niche

1. Validate that the niche has a source-of-truth path: public directory, regulator register, trade body, or clean Companies House SIC seed plus validation.
2. Add/update `config/<niche>.json`.
3. Make the source builder produce at least `company_name`, `website`, `phone`, `location`, `source`, `niche`, and a trust signal such as `mcs_registered`, `fca_authorised`, or `nacfb_member`.
4. Set `tiering.primary_quality_signal` to that trust signal.
5. Run a small sample before scaling paid enrichers.
6. Document blockers in `docs/codex-tasks/` when credentials, paid data, captchas, or account access are needed.

## Change Discipline

- Preserve the existing heat-pump pipeline.
- Prefer small config-driven changes over broad abstractions.
- Use `rg` and targeted reads before wide refactors.
- Do not move or rename output files unless the user asks; instead improve future output paths through config.
- Before finalizing changes, run `python3 -m unittest discover` and relevant CLI `--help` checks.
