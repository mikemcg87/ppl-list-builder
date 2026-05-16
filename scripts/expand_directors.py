#!/usr/bin/env python3
"""Explode the semicolon-joined ch_director_names into per-director columns.

Adds:
  director_2_name, director_2_first, director_2_last, director_2_role,
  director_3_*, director_4_*, director_5_*

Also adds a `family_business` flag when 2+ directors share a surname,
because that can be useful for fit review and personalization.
"""

import argparse
import re
from collections import Counter
from pathlib import Path

import pandas as pd


def split_ch_name(full: str) -> tuple[str, str]:
    """'SURNAME, Forename Middle' -> ('Forename', 'Surname')."""
    if not isinstance(full, str) or "," not in full:
        return ("", "")
    surname, forenames = full.split(",", 1)
    forename = forenames.strip().split(" ")[0]
    return (forename.title(), surname.strip().title())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/prospects_tiered.csv")
    parser.add_argument("--output", default="output/prospects_tiered.csv")
    parser.add_argument("--max-directors", type=int, default=5)
    args = parser.parse_args()

    df = pd.read_csv(args.input, keep_default_na=False)

    for n in range(2, args.max_directors + 1):
        for col in ("name", "first", "last", "role"):
            df[f"director_{n}_{col}"] = ""

    df["family_business"] = False
    df["surname_count"] = 0

    for idx, row in df.iterrows():
        names = (row.get("ch_director_names") or "").split(";")
        roles = (row.get("ch_director_roles") or "").split(";")
        names = [n.strip() for n in names if n.strip()]
        roles = [r.strip() for r in roles if r.strip()]

        # Skip the primary (already in director_first_name / _last_name).
        secondary = list(zip(names[1:], roles[1:]))
        for i, (full, role) in enumerate(secondary, start=2):
            if i > args.max_directors:
                break
            first, last = split_ch_name(full)
            df.at[idx, f"director_{i}_name"] = full
            df.at[idx, f"director_{i}_first"] = first
            df.at[idx, f"director_{i}_last"] = last
            df.at[idx, f"director_{i}_role"] = role

        # Family-business heuristic: 2+ directors sharing the same surname.
        surnames = [split_ch_name(n)[1] for n in names]
        surnames = [s for s in surnames if s]
        counts = Counter(surnames)
        most_common = counts.most_common(1)
        if most_common and most_common[0][1] >= 2:
            df.at[idx, "family_business"] = True
            df.at[idx, "surname_count"] = most_common[0][1]

    df.to_csv(args.output, index=False, encoding="utf-8")

    print(f"Wrote {len(df)} rows to {args.output}")
    print()
    print("Family-business flag by tier:")
    for tier in ("PLATINUM", "GOLD", "SILVER", "BRONZE"):
        sub = df[df["tier"] == tier]
        fam = sub["family_business"].sum()
        print(f"  {tier:9s} family: {fam}/{len(sub)} ({fam/len(sub)*100:.0f}%)")
    print()
    print("Sample PLATINUM family businesses:")
    fam = df[(df["tier"] == "PLATINUM") & df["family_business"]].head(8)
    print(
        fam[
            [
                "company_name",
                "ch_director_count",
                "surname_count",
                "ch_primary_director",
                "director_2_name",
            ]
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
