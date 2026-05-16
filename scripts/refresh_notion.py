#!/usr/bin/env python3
"""Refresh the configured Notion prospect database with the latest tiering.

Finds the existing database, archives all current pages, ensures the schema
includes enrichment columns, and re-pushes from output/outreach_list.csv.

Reads NOTION_TOKEN from environment (one-shot, never persisted).
"""

import argparse
import os
import sys
from typing import Any

import httpx
import pandas as pd

API = "https://api.notion.com/v1"
DATABASE_TITLE = os.getenv("NOTION_DATABASE_TITLE", "Installer Prospects")


def headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


def trunc(text: Any, n: int = 1900) -> str:
    s = "" if text is None else str(text)
    return s if len(s) <= n else s[: n - 1] + "…"


def find_database(client: httpx.Client, h: dict) -> str:
    r = client.post(
        f"{API}/search",
        headers=h,
        json={
            "query": DATABASE_TITLE,
            "filter": {"property": "object", "value": "database"},
        },
    )
    for d in r.json().get("results", []):
        title = "".join(t.get("plain_text", "") for t in d.get("title", []))
        if DATABASE_TITLE in title:
            return d["id"]
    raise RuntimeError(f"Couldn't find '{DATABASE_TITLE}' database")


def ensure_google_ads_property(client: httpx.Client, h: dict, db_id: str) -> None:
    """Add Google Ads columns to the database schema if missing."""
    r = client.get(f"{API}/databases/{db_id}", headers=h)
    r.raise_for_status()
    existing = r.json().get("properties", {})
    new_props: dict[str, Any] = {}
    if "Google Ads" not in existing:
        new_props["Google Ads"] = {"number": {"format": "number"}}
    if "Total ad signal" not in existing:
        new_props["Total ad signal"] = {"number": {"format": "number"}}
    if "FB public email" not in existing:
        new_props["FB public email"] = {"email": {}}
    if "FB category" not in existing:
        new_props["FB category"] = {"rich_text": {}}
    if "LinkedIn URL" not in existing:
        new_props["LinkedIn URL"] = {"url": {}}
    if "LinkedIn employees" not in existing:
        new_props["LinkedIn employees"] = {"number": {"format": "number"}}
    if "LinkedIn HQ" not in existing:
        new_props["LinkedIn HQ"] = {"rich_text": {}}
    if "LinkedIn industry" not in existing:
        new_props["LinkedIn industry"] = {"rich_text": {}}
    if "Director LinkedIn" not in existing:
        new_props["Director LinkedIn"] = {"url": {}}
    if "Last accounts filed" not in existing:
        new_props["Last accounts filed"] = {"date": {}}
    if "Accounts size band" not in existing:
        new_props["Accounts size band"] = {"rich_text": {}}
    if "Recent appointments" not in existing:
        new_props["Recent appointments"] = {"number": {"format": "number"}}
    if "Recent resignations" not in existing:
        new_props["Recent resignations"] = {"number": {"format": "number"}}
    if not new_props:
        return
    client.patch(
        f"{API}/databases/{db_id}",
        headers=h,
        json={"properties": new_props},
    )
    print(f"Added schema columns: {list(new_props.keys())}")


def archive_existing(client: httpx.Client, h: dict, db_id: str) -> int:
    """Archive every page currently in the database. Notion paginates query
    results in batches of 100."""
    cursor = None
    page_ids: list[str] = []
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = client.post(f"{API}/databases/{db_id}/query", headers=h, json=body)
        r.raise_for_status()
        data = r.json()
        page_ids.extend(p["id"] for p in data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    for pid in page_ids:
        client.patch(f"{API}/pages/{pid}", headers=h, json={"archived": True})
    return len(page_ids)


def url_or_none(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def add_row(client: httpx.Client, h: dict, db_id: str, row: dict) -> None:
    props: dict[str, Any] = {
        "Company": {"title": [{"text": {"content": trunc(row.get("company_name") or "Unknown")}}]},
        "Tier": {"select": {"name": row.get("tier") or "GOLD"}},
        "Status": {"select": {"name": "Not contacted"}},
    }

    director = row.get("ch_primary_director")
    if isinstance(director, str) and director:
        props["Director"] = {"rich_text": [{"text": {"content": trunc(director)}}]}

    email = row.get("hunter_email")
    if isinstance(email, str) and "@" in email:
        props["Email"] = {"email": email}

    score = row.get("hunter_score")
    if pd.notna(score) and str(score).strip():
        try:
            props["Email confidence"] = {"number": float(score)}
        except (TypeError, ValueError):
            pass

    pos = row.get("hunter_position")
    if isinstance(pos, str) and pos.strip():
        props["Position"] = {"rich_text": [{"text": {"content": trunc(pos)}}]}

    phone = row.get("phone")
    if isinstance(phone, str) and phone.strip():
        props["Phone"] = {"phone_number": phone.strip()}

    web = url_or_none(row.get("website"))
    if web:
        props["Website"] = {"url": web}

    loc = row.get("location")
    if isinstance(loc, str) and loc.strip():
        props["Location"] = {"rich_text": [{"text": {"content": trunc(loc)}}]}

    ls = row.get("lead_score")
    if pd.notna(ls) and str(ls).strip():
        try:
            props["Lead score"] = {"number": int(float(ls))}
        except (TypeError, ValueError):
            pass

    fb = row.get("facebook_ads_count")
    fb_n = 0
    if pd.notna(fb) and str(fb).strip():
        try:
            fb_n = int(float(fb))
            props["Active FB ads"] = {"number": fb_n}
        except (TypeError, ValueError):
            pass

    g = row.get("google_ads_count")
    g_n = 0
    if pd.notna(g) and str(g).strip():
        try:
            g_n = int(float(g))
            props["Google Ads"] = {"number": g_n}
        except (TypeError, ValueError):
            pass

    props["Total ad signal"] = {"number": fb_n + g_n}

    dc = row.get("ch_director_count")
    if pd.notna(dc) and str(dc).strip():
        try:
            props["Director count"] = {"number": int(float(dc))}
        except (TypeError, ValueError):
            pass

    fam = row.get("family_business")
    if isinstance(fam, str):
        fam = fam.lower() == "true"
    props["Family business"] = {"checkbox": bool(fam)}

    inc = row.get("ch_incorporated_on")
    if isinstance(inc, str) and inc.strip():
        props["Incorporated"] = {"date": {"start": inc.strip()}}

    addr = row.get("ch_address")
    if isinstance(addr, str) and addr.strip():
        props["Notes"] = {"rich_text": [{"text": {"content": trunc(f"Registered: {addr}")}}]}

    # Extras enrichment fields
    fb_email = row.get("fb_public_email")
    if isinstance(fb_email, str) and "@" in fb_email:
        props["FB public email"] = {"email": fb_email}
    fb_cat = row.get("fb_category")
    if isinstance(fb_cat, str) and fb_cat.strip():
        props["FB category"] = {"rich_text": [{"text": {"content": trunc(fb_cat)}}]}

    li_url = row.get("linkedin_url")
    if isinstance(li_url, str) and li_url.strip().startswith("http"):
        props["LinkedIn URL"] = {"url": li_url.strip()}
    li_emp = row.get("linkedin_employees")
    if pd.notna(li_emp) and str(li_emp).strip() and str(li_emp).strip() != "None":
        try:
            props["LinkedIn employees"] = {"number": int(float(li_emp))}
        except (TypeError, ValueError):
            pass
    li_hq = row.get("linkedin_hq")
    if isinstance(li_hq, str) and li_hq.strip():
        props["LinkedIn HQ"] = {"rich_text": [{"text": {"content": trunc(li_hq)}}]}
    li_ind = row.get("linkedin_industry")
    if isinstance(li_ind, str) and li_ind.strip():
        props["LinkedIn industry"] = {"rich_text": [{"text": {"content": trunc(li_ind)}}]}
    dir_li = row.get("linkedin_director_profile")
    if isinstance(dir_li, str) and dir_li.strip().startswith("http"):
        props["Director LinkedIn"] = {"url": dir_li.strip()}

    last_accts = row.get("ch_last_accounts")
    if isinstance(last_accts, str) and last_accts.strip():
        props["Last accounts filed"] = {"date": {"start": last_accts.strip()}}
    accts_type = row.get("ch_accounts_type")
    if isinstance(accts_type, str) and accts_type.strip():
        # Trim "accounts-with-accounts-type-" prefix for readability
        clean = accts_type.replace("accounts-with-accounts-type-", "").replace("-", " ")
        props["Accounts size band"] = {"rich_text": [{"text": {"content": trunc(clean)}}]}
    appts = row.get("ch_recent_appointments")
    if pd.notna(appts) and str(appts).strip():
        try:
            props["Recent appointments"] = {"number": int(float(appts))}
        except (TypeError, ValueError):
            pass
    resigns = row.get("ch_recent_resignations")
    if pd.notna(resigns) and str(resigns).strip():
        try:
            props["Recent resignations"] = {"number": int(float(resigns))}
        except (TypeError, ValueError):
            pass

    body = {"parent": {"database_id": db_id}, "properties": props}
    last_err = None
    for attempt in range(3):
        try:
            r = client.post(f"{API}/pages", headers=h, json=body)
            if r.status_code >= 400:
                print(f"! row failed: {row.get('company_name')}  {r.status_code} {r.text[:200]}")
            return
        except httpx.HTTPError as e:
            last_err = e
            import time as _t
            _t.sleep(2 ** attempt)
    print(f"! row gave up after retries: {row.get('company_name')}  {last_err}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/outreach_list.csv")
    args = parser.parse_args()

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print("Set NOTION_TOKEN env var")
        return 1

    df = pd.read_csv(args.input, keep_default_na=False)
    print(f"Refreshing Notion with {len(df)} prospects...")

    h = headers(token)
    with httpx.Client(timeout=60.0) as client:
        db_id = find_database(client, h)
        print(f"  database: {db_id}")
        ensure_google_ads_property(client, h, db_id)
        archived = archive_existing(client, h, db_id)
        print(f"  archived {archived} old rows")
        for i, (_, row) in enumerate(df.iterrows(), start=1):
            add_row(client, h, db_id, row.to_dict())
            if i % 10 == 0:
                print(f"  {i}/{len(df)} added")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
