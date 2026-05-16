# Solar PV Implementation Notes

## Why Solar PV

Solar PV is the second reference niche because it is the closest structural match to heat pumps:

- The source-of-truth is still MCS, so the scraper can be generalised instead of duplicated.
- Typical residential system values are comfortably above the Second Wind threshold.
- Solar installers commonly run lead-gen funnels and can plausibly have stale quote databases.
- Reactivation messaging is straightforward: old quotes, battery add-ons, energy bills, and price changes.

## Implemented Source

`config/solar_pv.json` uses the existing MCS directory URL and selects the Solar PV technology tile through:

- `filters.mcs_image_src_contains = "Solar-PV"`
- `filters.mcs_tile_text = "Solar PV"`

Rows produced by the MCS scraper include:

- `niche = solar_pv`
- `source_technology = Solar Photovoltaic`
- `mcs_registered = true`

Solar tiering uses `mcs_registered` as the trusted source signal, replacing the heat-pump-specific `bus_registered` signal.

## API Calls Used

No paid or rate-constrained enrichment run was executed during this implementation pass.

Expected calls for a full 1,000-row Solar PV run:

| Service | Expected calls |
| --- | ---: |
| MCS source scrape | Browser pages only |
| Companies House | About 2,000 API requests |
| Facebook Ads via ScrapeCreators | Up to 2,000 ScrapeCreators requests, depending on page-id hit rate |
| Brave Search | Only missing-domain rows selected for domain resolution |
| Google Ads via ScrapeCreators | One request per row with a domain |
| Hunter.io | Capped to PLATINUM only, max 20 for test |
| SerpApi | 0 |

## Email Finding Without Hunter

For Solar PV, broad Hunter enrichment is deliberately not part of the default run. The fallback is:

1. Use MCS-provided email where available.
2. Use website/domain capture and generic contact page review for `PLATINUM`.
3. Use LinkedIn/company director names for manual top-tier targeting.
4. Run Hunter only on capped `PLATINUM` batches when explicitly requested.

Trade-off: this protects the Hunter quota but means Solar PV email coverage will be weaker than a fully paid heat-pump enrichment pass until a replacement email source is chosen.
