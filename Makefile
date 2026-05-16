.PHONY: help test compile help-main help-tier help-domains help-enrich demo-tier tier-solar domains-solar tier-heat-pumps

PY ?= python3

help:
	@printf "%s\n" "PPL List Builder commands"
	@printf "%s\n" "  make test              Run unit tests"
	@printf "%s\n" "  make compile           Compile key Python entrypoints"
	@printf "%s\n" "  make help-main         Show source scraper CLI"
	@printf "%s\n" "  make help-enrich       Show enrichment CLI"
	@printf "%s\n" "  make help-tier         Show tiering CLI"
	@printf "%s\n" "  make help-domains      Show domain finder CLI"
	@printf "%s\n" "  make demo-tier         Build tiers from synthetic example data"
	@printf "%s\n" "  make tier-solar        Build Solar PV tiered CSV from configured inputs"
	@printf "%s\n" "  make domains-solar     Resolve Solar PV PLATINUM domains with Brave"
	@printf "%s\n" "  make tier-heat-pumps   Build heat-pump tiered CSV from configured inputs"

test:
	$(PY) -m unittest discover

compile:
	$(PY) -m py_compile src/main.py src/core/models.py src/scrapers/mcs_scraper.py scripts/build_prospect_tiers.py scripts/find_domains.py scripts/enrich_companies.py

help-main:
	$(PY) -m src.main --help

help-enrich:
	$(PY) scripts/enrich_companies.py --help

help-tier:
	$(PY) scripts/build_prospect_tiers.py --help

help-domains:
	$(PY) scripts/find_domains.py --help

demo-tier:
	$(PY) scripts/build_prospect_tiers.py --ch examples/sample_companies_house.csv --fb examples/sample_facebook_ads.csv --out output/sample_prospects_tiered.csv

tier-solar:
	$(PY) scripts/build_prospect_tiers.py --niche config/solar_pv.json

domains-solar:
	$(PY) scripts/find_domains.py --niche config/solar_pv.json --tier PLATINUM --provider brave

tier-heat-pumps:
	$(PY) scripts/build_prospect_tiers.py --niche config/mcs_config.json
