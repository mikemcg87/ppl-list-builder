#!/usr/bin/env python3
"""Import reviewed outreach prospects into GHL as contacts + opportunities.

For each row:
  1. Look up or create a contact (dedup by email)
  2. Set custom field values
  3. Apply cohort/tier/signal tags
  4. Create an opportunity in the configured pipeline/stage

Idempotent — re-running updates existing contacts rather than duplicating.
"""

import argparse
import os
import re
import sys
import time
from typing import Any

import pandas as pd
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

PIPELINE_ID = os.getenv("GHL_PIPELINE_ID", "")
TO_SEND_STAGE_ID = os.getenv("GHL_TO_SEND_STAGE_ID", "")
COHORT_TAG = os.getenv("GHL_COHORT_TAG", "cohort:example")
PIPELINE_NAME = os.getenv("GHL_PIPELINE_NAME", "Configured Outreach")


def get_custom_field_map() -> dict[str, str]:
    r = requests.get(f"{BASE}/locations/{LOC}/customFields", headers=H, timeout=30)
    r.raise_for_status()
    fields = r.json().get("customFields", [])
    return {f["name"]: f["id"] for f in fields if f.get("name", "").startswith("HP ")}


def split_director_name(full: str) -> tuple[str, str]:
    """Convert 'SURNAME, Forename Middlename' -> ('Forename', 'Surname-titlecase')."""
    if not isinstance(full, str) or "," not in full:
        return ("", "")
    surname, forenames = full.split(",", 1)
    forename = forenames.strip().split(" ")[0]
    return (forename.title(), surname.strip().title())


def normalise_phone(p: Any) -> str:
    if not isinstance(p, str):
        return ""
    s = re.sub(r"[^\d+]", "", p)
    if not s:
        return ""
    if s.startswith("+"):
        return s
    if s.startswith("0"):
        return "+44" + s[1:]
    if s.startswith("44"):
        return "+" + s
    return s


def search_contact_by_email(email: str) -> dict | None:
    r = requests.get(
        f"{BASE}/contacts/?locationId={LOC}&query={email}",
        headers=H,
        timeout=30,
    )
    if r.status_code != 200:
        return None
    contacts = r.json().get("contacts", [])
    for c in contacts:
        if (c.get("email") or "").lower() == email.lower():
            return c
    return None


def upsert_contact(payload: dict) -> dict | None:
    """Create or update a contact. GHL has a /contacts/upsert endpoint."""
    r = requests.post(f"{BASE}/contacts/upsert", headers=H, json=payload, timeout=30)
    if r.status_code >= 400:
        print(f"    ! upsert failed: {r.status_code}  {r.text[:300]}")
        return None
    data = r.json()
    return data.get("contact") or data.get("data") or {}


def create_opportunity(contact_id: str, name: str, monetary_value: float = 0) -> dict | None:
    body = {
        "pipelineId": PIPELINE_ID,
        "pipelineStageId": TO_SEND_STAGE_ID,
        "name": name,
        "status": "open",
        "contactId": contact_id,
        "locationId": LOC,
        "monetaryValue": monetary_value,
    }
    r = requests.post(f"{BASE}/opportunities/", headers=H, json=body, timeout=30)
    if r.status_code >= 400:
        print(f"    ! opportunity failed: {r.status_code}  {r.text[:300]}")
        return None
    data = r.json()
    return data.get("opportunity") or data.get("data") or {}


def list_opportunities_for_contact(contact_id: str) -> list[dict]:
    r = requests.get(
        f"{BASE}/opportunities/search?location_id={LOC}&contact_id={contact_id}",
        headers=H,
        timeout=30,
    )
    if r.status_code != 200:
        return []
    return r.json().get("opportunities", [])


def build_payload(row: dict, field_map: dict[str, str]) -> dict:
    director_first, director_last = split_director_name(row.get("ch_primary_director") or "")
    email = (row.get("hunter_email") or "").strip()
    phone = normalise_phone(row.get("phone"))
    company = (row.get("company_name") or "").strip()
    tier = row.get("tier") or "GOLD"

    # Tags strategy — multiple categorical tags, comma-separated.
    niche = row.get("niche") or "unknown"
    tags = ["source:ppl-list-builder", f"niche:{niche}", COHORT_TAG]
    tags.append(f"tier:{tier.lower()}")
    if str(row.get("family_business")).lower() == "true":
        tags.append("signal:family-business")
    try:
        fb = float(row.get("facebook_ads_count") or 0)
    except (TypeError, ValueError):
        fb = 0
    try:
        g = float(row.get("google_ads_count") or 0)
    except (TypeError, ValueError):
        g = 0
    if fb > 0:
        tags.append("signal:fb-active")
    if g > 0:
        tags.append("signal:google-active")
    if (fb + g) >= 20:
        tags.append("signal:high-ad-spend")

    # Custom field values keyed by field id.
    cf_values = {}

    def add(name: str, value: Any):
        fid = field_map.get(name)
        if fid is None:
            return
        if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
            return
        cf_values[fid] = value

    add("HP Tier", tier)
    add("HP Lead Score", row.get("lead_score"))
    add("HP FB Ads Count", int(fb) if fb else 0)
    add("HP Google Ads Count", int(g) if g else 0)
    add("HP Total Ad Signal", int(fb + g))
    add("HP BUS Registered", "Yes" if str(row.get("bus_registered")).lower() == "true" else "No")
    add("HP Family Business", "Yes" if str(row.get("family_business")).lower() == "true" else "No")
    add("HP LinkedIn URL", row.get("linkedin_url"))
    try:
        emp = int(float(row.get("linkedin_employees") or 0))
        if emp:
            add("HP LinkedIn Employees", emp)
    except (TypeError, ValueError):
        pass
    add("HP LinkedIn HQ", row.get("linkedin_hq"))
    add("HP LinkedIn Industry", row.get("linkedin_industry"))
    add("HP Director LinkedIn", row.get("linkedin_director_profile"))
    add("HP FB Public Email", row.get("fb_public_email"))
    add("HP Accounts Size Band", str(row.get("ch_accounts_type", "")).replace("accounts-with-accounts-type-", "").replace("-", " "))
    if row.get("ch_last_accounts"):
        add("HP Last Accounts Filed", row.get("ch_last_accounts"))
    try:
        dc = int(float(row.get("ch_director_count") or 0))
        if dc:
            add("HP CH Director Count", dc)
    except (TypeError, ValueError):
        pass
    try:
        appts = int(float(row.get("ch_recent_appointments") or 0))
        add("HP Recent Appointments", appts)
    except (TypeError, ValueError):
        pass
    try:
        resigns = int(float(row.get("ch_recent_resignations") or 0))
        add("HP Recent Resignations", resigns)
    except (TypeError, ValueError):
        pass
    add("HP Source Cohort", COHORT_TAG)

    custom_fields_array = [{"id": fid, "value": v} for fid, v in cf_values.items()]

    payload = {
        "locationId": LOC,
        "firstName": director_first,
        "lastName": director_last,
        "email": email,
        "phone": phone if phone else None,
        "companyName": company,
        "source": "ppl-list-builder",
        "tags": tags,
        "customFields": custom_fields_array,
    }
    # Drop None values
    return {k: v for k, v in payload.items() if v is not None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/outreach_list.csv")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-opportunities", action="store_true")
    args = parser.parse_args()

    if not TOKEN or not LOC:
        print("Missing GHL_PRIVATE_TOKEN or GHL_LOCATION_ID")
        return 1
    if not PIPELINE_ID or not TO_SEND_STAGE_ID:
        print("Missing GHL_PIPELINE_ID or GHL_TO_SEND_STAGE_ID")
        return 1

    df = pd.read_csv(args.input, keep_default_na=False)
    if args.limit:
        df = df.head(args.limit)

    print(f"Importing {len(df)} contacts to GHL location {LOC}")
    print(f"Pipeline: {PIPELINE_NAME} ({PIPELINE_ID})")
    print(f"Cohort tag: {COHORT_TAG}")
    print()

    field_map = get_custom_field_map()
    print(f"Custom field map: {len(field_map)} HP fields found")
    if len(field_map) < 19:
        print("! Warning: expected 19 HP fields. Run ghl_setup.py first.")

    if args.dry_run:
        print()
        print("DRY RUN — no API calls. Sample payload for first row:")
        sample = build_payload(df.iloc[0].to_dict(), field_map)
        import json as _j
        print(_j.dumps(sample, indent=2, default=str))
        return 0

    print()
    successes = 0
    failures = 0
    tracker_rows: list[dict] = []
    tracker_path = "output/ghl_imported.csv"
    if os.path.exists(tracker_path):
        try:
            existing_tracker = pd.read_csv(tracker_path, keep_default_na=False)
            tracker_rows = existing_tracker.to_dict(orient="records")
        except Exception:
            tracker_rows = []
    seen_emails = {r.get("email", "").lower() for r in tracker_rows if r.get("email")}

    for i, (_, row) in enumerate(df.iterrows(), start=1):
        company = row.get("company_name", "?")
        email = row.get("hunter_email", "")
        if not email or "@" not in email:
            print(f"  [{i}/{len(df)}] skip (no email): {company}")
            continue

        payload = build_payload(row.to_dict(), field_map)
        contact = upsert_contact(payload)
        if not contact:
            failures += 1
            continue

        cid = contact.get("id") or contact.get("_id")
        if not cid:
            print(f"  [{i}/{len(df)}] {company}: upserted but no contact id returned")
            failures += 1
            continue

        opp_status = "skipped"
        opp_id = ""
        if not args.skip_opportunities:
            existing_opps = list_opportunities_for_contact(cid)
            in_our_pipeline = [o for o in existing_opps if o.get("pipelineId") == PIPELINE_ID]
            if in_our_pipeline:
                opp_id = in_our_pipeline[0].get("id", "")
                opp_status = f"exists ({opp_id[:8]})"
            else:
                opp = create_opportunity(cid, company)
                opp_id = opp.get("id", "") if opp else ""
                opp_status = f"created ({opp_id[:8]})" if opp else "failed"

        print(f"  [{i}/{len(df)}] ✓ {company:50s} contact={cid[:8]} opp={opp_status}")
        successes += 1

        # Record in tracker (replace existing row if present).
        tracker_rows = [r for r in tracker_rows if r.get("email", "").lower() != email.lower()]
        tracker_rows.append({
            "email": email,
            "company_name": company,
            "tier": row.get("tier", ""),
            "ghl_contact_id": cid,
            "ghl_opportunity_id": opp_id,
            "cohort_tag": COHORT_TAG,
            "imported_at": pd.Timestamp.now().isoformat(),
        })
        # Save every 10 rows so a crash doesn't lose tracking.
        if i % 10 == 0:
            pd.DataFrame(tracker_rows).to_csv(tracker_path, index=False, encoding="utf-8")

        time.sleep(0.3)

    # Final tracker save
    pd.DataFrame(tracker_rows).to_csv(tracker_path, index=False, encoding="utf-8")

    print()
    print(f"Done. {successes} succeeded, {failures} failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
