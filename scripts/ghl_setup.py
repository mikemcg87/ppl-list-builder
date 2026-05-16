#!/usr/bin/env python3
"""GHL one-time setup: create outreach custom fields and pipeline.

Idempotent — re-running checks for existing fields/pipelines by name and
skips them. Reads credentials from the local environment.

Run before ghl_import.py.
"""

import argparse
import os
import sys
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("GHL_PRIVATE_TOKEN")
LOC = os.getenv("GHL_LOCATION_ID")
BASE = os.getenv("GHL_API_BASE", "https://services.leadconnectorhq.com")
VERSION = os.getenv("GHL_API_VERSION", "2021-07-28")

H = {
    "Authorization": f"Bearer {TOKEN}",
    "Version": VERSION,
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Field schema. dataType options: TEXT, LARGE_TEXT, NUMERICAL, MONETARY, PHONE,
# CHECKBOX, RADIO, SELECT, MULTIPLE_OPTIONS, DATE, FILE_UPLOAD, TEXTBOX_LIST.
HP_CUSTOM_FIELDS = [
    {"name": "HP Tier", "dataType": "TEXT"},
    {"name": "HP Lead Score", "dataType": "NUMERICAL"},
    {"name": "HP FB Ads Count", "dataType": "NUMERICAL"},
    {"name": "HP Google Ads Count", "dataType": "NUMERICAL"},
    {"name": "HP Total Ad Signal", "dataType": "NUMERICAL"},
    {"name": "HP BUS Registered", "dataType": "TEXT"},
    {"name": "HP Family Business", "dataType": "TEXT"},
    {"name": "HP LinkedIn URL", "dataType": "TEXT"},
    {"name": "HP LinkedIn Employees", "dataType": "NUMERICAL"},
    {"name": "HP LinkedIn HQ", "dataType": "TEXT"},
    {"name": "HP LinkedIn Industry", "dataType": "TEXT"},
    {"name": "HP Director LinkedIn", "dataType": "TEXT"},
    {"name": "HP FB Public Email", "dataType": "TEXT"},
    {"name": "HP Accounts Size Band", "dataType": "TEXT"},
    {"name": "HP Last Accounts Filed", "dataType": "DATE"},
    {"name": "HP CH Director Count", "dataType": "NUMERICAL"},
    {"name": "HP Recent Appointments", "dataType": "NUMERICAL"},
    {"name": "HP Recent Resignations", "dataType": "NUMERICAL"},
    {"name": "HP Source Cohort", "dataType": "TEXT"},
]

# Pipeline structure. GHL recreates pipelines wholesale on PUT; we only create
# if missing.
HP_PIPELINE_NAME = os.getenv("GHL_PIPELINE_NAME", "Example Outreach")
HP_PIPELINE_STAGES = [
    "To send",
    "Email 1 sent",
    "Email 2 sent",
    "Email 3 sent",
    "Email 4 sent",
    "Replied — interested",
    "Replied — not now",
    "Replied — no",
    "Bounced",
    "Booked call",
    "Closed won",
    "Closed lost",
]


def list_custom_fields() -> list[dict]:
    r = requests.get(f"{BASE}/locations/{LOC}/customFields", headers=H, timeout=30)
    r.raise_for_status()
    return r.json().get("customFields", [])


def create_custom_field(name: str, data_type: str) -> dict:
    body = {"name": name, "dataType": data_type}
    r = requests.post(
        f"{BASE}/locations/{LOC}/customFields", headers=H, json=body, timeout=30
    )
    if r.status_code >= 400:
        print(f"  ! failed: {name}  {r.status_code}  {r.text[:200]}")
        return {}
    return r.json().get("customField") or r.json()


def list_pipelines() -> list[dict]:
    r = requests.get(
        f"{BASE}/opportunities/pipelines?locationId={LOC}", headers=H, timeout=30
    )
    r.raise_for_status()
    return r.json().get("pipelines", [])


def create_pipeline(name: str, stage_names: list[str]) -> dict:
    body = {
        "name": name,
        "locationId": LOC,
        "stages": [
            {"name": s, "position": i} for i, s in enumerate(stage_names)
        ],
    }
    # Pipeline create endpoint on v2:
    r = requests.post(
        f"{BASE}/opportunities/pipelines", headers=H, json=body, timeout=30
    )
    if r.status_code >= 400:
        print(f"  ! pipeline create failed: {r.status_code}  {r.text[:300]}")
        return {}
    return r.json().get("pipeline") or r.json()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not TOKEN or not LOC:
        print("Missing GHL_PRIVATE_TOKEN or GHL_LOCATION_ID")
        return 1

    print(f"Location: {LOC}")
    print()

    # --- Custom fields ---
    print("=== Custom fields ===")
    existing = list_custom_fields()
    existing_names = {f.get("name", "").strip() for f in existing}
    print(f"Existing: {len(existing)} fields ({len(existing_names)} unique names)")

    to_create = [f for f in HP_CUSTOM_FIELDS if f["name"] not in existing_names]
    print(f"Need to create: {len(to_create)} new HP_* fields")
    for f in to_create:
        print(f"  + {f['name']} ({f['dataType']})")

    if to_create and not args.dry_run:
        print()
        print("Creating fields...")
        for f in to_create:
            created = create_custom_field(f["name"], f["dataType"])
            if created:
                fid = created.get("id") or created.get("_id") or "?"
                print(f"  ✓ {f['name']} → {fid}")
    elif to_create:
        print("(dry-run, skipping)")

    # --- Pipeline ---
    print()
    print("=== Pipeline ===")
    pipelines = list_pipelines()
    pipeline_names = {p.get("name", "").strip() for p in pipelines}
    print(f"Existing pipelines: {sorted(pipeline_names)}")

    if HP_PIPELINE_NAME in pipeline_names:
        existing_pipeline = next(
            p for p in pipelines if p.get("name") == HP_PIPELINE_NAME
        )
        print(f"'{HP_PIPELINE_NAME}' already exists: {existing_pipeline.get('id')}")
        for s in existing_pipeline.get("stages", []):
            print(f"  - {s.get('name')} ({s.get('id')})")
    else:
        print(f"Pipeline '{HP_PIPELINE_NAME}' does not exist.")
        if not args.dry_run:
            print("Creating...")
            created = create_pipeline(HP_PIPELINE_NAME, HP_PIPELINE_STAGES)
            if created:
                print(f"  ✓ created: {created.get('id')}")
                for s in created.get("stages", []):
                    print(f"    - {s.get('name')} ({s.get('id')})")
        else:
            print("(dry-run, skipping)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
