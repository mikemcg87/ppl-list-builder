#!/usr/bin/env python3
"""Merge source + Companies House + ads enrichments into a single
tiered prospect list, ready for outreach prioritisation and Hunter top-up.

  PLATINUM = source quality signal + active ads + named director (HOT)
  GOLD     = source quality signal + named director              (WARM)
  SILVER   = Active FB ads + named director                   (WARM)
  BRONZE   = Named director only                              (COLD)
  SKIP     = No CH match or dissolved                         (drop)
"""

import argparse
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.core.config import load_config


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() == "true"
    return False


def _has_named_director(row: pd.Series, director_col: str) -> bool:
    return isinstance(row.get(director_col), str) and bool(row[director_col].strip())


def _load_niche_config(path: str | None):
    if not path:
        return None
    return load_config(path)


def assign_tier(row: pd.Series, tiering=None) -> str:
    primary_signal = "bus_registered"
    status_col = "ch_company_status"
    status_value = "active"
    director_col = "ch_primary_director"
    if tiering:
        primary_signal = tiering.primary_quality_signal
        status_col = tiering.required_status_column
        status_value = tiering.required_status_value
        director_col = tiering.required_director_column

    if row.get("ch_match_status") != "matched":
        return "SKIP"
    if row.get(status_col) != status_value:
        return "SKIP"
    if not _has_named_director(row, director_col):
        return "SKIP"

    trusted_source = _truthy(row.get(primary_signal))
    fb_ads = _truthy(row.get("facebook_ads_running"))
    g_ads = _truthy(row.get("google_ads_running")) and _truthy(row.get("domain_confident"))
    ads = fb_ads or g_ads

    if trusted_source and ads:
        return "PLATINUM"
    if trusted_source:
        return "GOLD"
    if ads:
        return "SILVER"
    return "BRONZE"


def lead_score(row: pd.Series, tiering=None) -> int:
    primary_signal = "bus_registered"
    director_col = "ch_primary_director"
    weights = {
        "primary_quality_signal": 30,
        "facebook_ads_running": 40,
        "google_ads_running": 30,
        "multiple_directors": 15,
        "named_director": 5,
    }
    if tiering:
        primary_signal = tiering.primary_quality_signal
        director_col = tiering.required_director_column
        weights.update(tiering.score_weights or {})

    score = 0
    if _truthy(row.get(primary_signal)):
        score += weights["primary_quality_signal"]
    if _truthy(row.get("facebook_ads_running")):
        score += weights["facebook_ads_running"]
        try:
            if float(row.get("facebook_ads_count") or 0) >= 5:
                score += 10
        except (TypeError, ValueError):
            pass
    if _truthy(row.get("google_ads_running")) and _truthy(row.get("domain_confident")):
        score += weights["google_ads_running"]
        try:
            if float(row.get("google_ads_count") or 0) >= 10:
                score += 10
        except (TypeError, ValueError):
            pass
    try:
        if float(row.get("ch_director_count") or 0) >= 2:
            score += weights["multiple_directors"]
    except (TypeError, ValueError):
        pass
    if _has_named_director(row, director_col):
        score += weights["named_director"]
    return score


def split_director(full: str) -> tuple[str, str]:
    """Companies House returns 'SURNAME, Forename Middlename'. Split it."""
    if not isinstance(full, str) or "," not in full:
        return ("", "")
    surname, forenames = full.split(",", 1)
    forename = forenames.strip().split(" ")[0]
    return (forename, surname.strip().title())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--niche",
        "--config",
        dest="config",
        help="Optional niche config JSON; supplies default paths and tiering rules",
    )
    parser.add_argument("--ch", default="output/heat-pump-installers-with-directors.csv")
    parser.add_argument("--fb", default="output/enriched_fb.csv")
    parser.add_argument("--out", default="output/prospects_tiered.csv")
    args = parser.parse_args()

    config = _load_niche_config(args.config)
    if config:
        # Use config paths only when the caller left the old defaults in place.
        if args.ch == "output/heat-pump-installers-with-directors.csv":
            args.ch = config.pipeline.companies_house_output
        if args.fb == "output/enriched_fb.csv":
            args.fb = config.pipeline.facebook_output
        if args.out == "output/prospects_tiered.csv":
            args.out = config.pipeline.tiered_output

    ch = pd.read_csv(args.ch)
    fb_path = Path(args.fb)
    if fb_path.exists():
        fb = pd.read_csv(fb_path)
    else:
        fb = pd.DataFrame({"company_name": ch["company_name"]})

    fb_cols = [c for c in fb.columns if c.startswith("facebook_") or c == "company_name"]
    # Drop any pre-existing facebook_* columns on the CH side so the merge doesn't
    # produce _x/_y duplicates and lose the unsuffixed names downstream code expects.
    ch = ch.drop(columns=[c for c in ch.columns if c.startswith("facebook_")], errors="ignore")
    merged = ch.merge(fb[fb_cols], on="company_name", how="left")

    tiering = config.tiering if config else None
    merged["tier"] = merged.apply(assign_tier, axis=1, tiering=tiering)
    merged["lead_score"] = merged.apply(lead_score, axis=1, tiering=tiering)

    director_col = tiering.required_director_column if tiering else "ch_primary_director"
    if len(merged):
        forenames, surnames = zip(*merged[director_col].map(split_director))
        merged["director_first_name"] = forenames
        merged["director_last_name"] = surnames
    else:
        merged["director_first_name"] = []
        merged["director_last_name"] = []

    tier_order = {"PLATINUM": 0, "GOLD": 1, "SILVER": 2, "BRONZE": 3, "SKIP": 4}
    merged["_tier_rank"] = merged["tier"].map(tier_order)
    merged = merged.sort_values(
        ["_tier_rank", "lead_score"], ascending=[True, False]
    ).drop(columns=["_tier_rank"])

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.out, index=False, encoding="utf-8")

    print(f"Wrote {len(merged)} rows to {args.out}")
    print()
    print("Tier breakdown:")
    print(merged["tier"].value_counts().to_string())
    print()
    print("Top 10 PLATINUM:")
    plat_cols = [
        "company_name",
        "ch_primary_director",
        "website" if "website" in merged.columns else "phone",
        "location",
        "facebook_ads_count",
        "lead_score",
    ]
    plat_cols = [c for c in plat_cols if c in merged.columns]
    print(merged[merged["tier"] == "PLATINUM"][plat_cols].head(10).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
