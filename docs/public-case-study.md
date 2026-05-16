# Public Case Study

PPL List Builder is a public-safe version of a prospect-intelligence workflow used for outbound campaign preparation.

## Problem

Manual prospect research is slow and inconsistent. For each new vertical, the useful question is not just "who exists?", but:

- is the company still active?
- is there a named decision maker?
- is there a trusted source signal?
- is there current commercial intent, such as active ads?
- is the domain/contact data good enough for outreach?

## Approach

The system treats each vertical as a small deployment problem:

1. identify a source-of-truth directory or register;
2. build a niche-specific scraper or ingestion adapter;
3. normalize rows into a shared prospect schema;
4. enrich through Companies House and commercial-signal providers;
5. score prospects into operational tiers;
6. review the list manually before CRM import.

## What The Code Demonstrates

- Selenium ingestion for source directories with niche-specific filters.
- Pydantic config and data models for repeatable vertical expansion.
- Companies House, ad-signal, domain-discovery, and email enrichment adapters.
- Cost-aware provider routing: Brave by default, SerpApi opt-in, Hunter capped to top-tier rows.
- Human-in-the-loop QA before Notion/GHL export.

## Public Data Boundary

The repo does not include scraped prospect data, CRM exports, send queues, or campaign logs. `examples/` contains synthetic rows only.
