#!/usr/bin/env python3
"""Export a clean, human-scannable outreach list (PLATINUM + GOLD with email)."""

import argparse
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/prospects_tiered.csv")
    parser.add_argument("--output", default="output/outreach_list.csv")
    args = parser.parse_args()

    df = pd.read_csv(args.input, keep_default_na=False)
    mask = (
        df["tier"].isin(["PLATINUM", "GOLD"])
        & df["hunter_email"].str.contains("@", na=False)
        & (df["hunter_email"] != "")
    )
    out = df[mask].copy()

    cols = [
        "tier",
        "lead_score",
        "company_name",
        "ch_primary_director",
        "bus_registered",
        "hunter_email",
        "hunter_score",
        "hunter_position",
        "phone",
        "website",
        "location",
        "facebook_ads_count",
        "google_ads_count",
        "google_ads_formats",
        "fb_public_email",
        "fb_category",
        "fb_creation_date",
        "fb_match_confidence",
        "linkedin_url",
        "linkedin_employees",
        "linkedin_hq",
        "linkedin_industry",
        "linkedin_director_profile",
        "ch_director_count",
        "family_business",
        "ch_address",
        "ch_incorporated_on",
        "ch_last_accounts",
        "ch_accounts_type",
        "ch_recent_appointments",
        "ch_recent_resignations",
    ]
    cols = [c for c in cols if c in out.columns]
    out = out[cols].sort_values(["tier", "lead_score"], ascending=[True, False])

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8")

    print(f"Wrote {len(out)} prospects to {args.output}")
    print()
    print(f"PLATINUM: {(out['tier']=='PLATINUM').sum()}")
    print(f"GOLD:     {(out['tier']=='GOLD').sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
