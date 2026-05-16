#!/usr/bin/env python3
"""Push the outreach list into a fresh Notion page + inline database.

Reads the token from NOTION_TOKEN env var (one-shot, never written to disk).
Creates a top-level page in the workspace, with a header, callout instructions,
and an inline database holding all PLATINUM + GOLD prospects.
"""

import argparse
import os
import sys
from typing import Any

import httpx
import pandas as pd

API = "https://api.notion.com/v1"
ROOT_PAGE_QUERY = os.getenv("NOTION_PARENT_PAGE_QUERY", "Outreach")
SECTION_TITLE = os.getenv("NOTION_SECTION_TITLE", "Prospect Intelligence Review")
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


def create_section_page(client: httpx.Client, h: dict) -> str:
    body = {
        "parent": {"type": "page_id", "page_id": find_or_create_root(client, h)},
        "icon": {"type": "emoji", "emoji": "🔥"},
        "properties": {
            "title": {"title": [{"text": {"content": SECTION_TITLE}}]}
        },
        "children": [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": (
                                    "PLATINUM = BUS-registered + active FB ads. GOLD = BUS-registered. "
                                    "Sorted by tier then lead_score. Update Status as you work the list."
                                )
                            },
                        }
                    ],
                    "icon": {"type": "emoji", "emoji": "🎯"},
                    "color": "orange_background",
                },
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Prospect Pipeline"}}]
                },
            },
            {"object": "block", "type": "divider", "divider": {}},
        ],
    }
    r = client.post(f"{API}/pages", headers=h, json=body)
    r.raise_for_status()
    return r.json()["id"]


def find_or_create_root(client: httpx.Client, h: dict) -> str:
    """Find a page we can write under. Prefer a workspace-level page named
    something neutral."""
    r = client.post(
        f"{API}/search",
        headers=h,
        json={"query": ROOT_PAGE_QUERY, "filter": {"property": "object", "value": "page"}},
    )
    for p in r.json().get("results", []):
        title = ""
        for v in p.get("properties", {}).values():
            if v.get("type") == "title" and v.get("title"):
                title = "".join(t.get("plain_text", "") for t in v["title"])
        if title.strip().lower() == ROOT_PAGE_QUERY.strip().lower():
            return p["id"]

    # Notion API requires a parent — workspace-root pages can only be created via
    # users.me + parent.type=workspace in newer versions, but most integrations
    # don't have that scope. We pick the first workspace-parent page we can see.
    r = client.post(
        f"{API}/search",
        headers=h,
        json={"page_size": 50, "filter": {"property": "object", "value": "page"}},
    )
    candidates = []
    for p in r.json().get("results", []):
        if p.get("parent", {}).get("type") == "workspace":
            candidates.append(p)
    # Prefer a page literally called "Home" if present.
    for p in candidates:
        title = ""
        for v in p.get("properties", {}).values():
            if v.get("type") == "title" and v.get("title"):
                title = "".join(t.get("plain_text", "") for t in v["title"])
        if title.strip().lower() == "home":
            return p["id"]
    if candidates:
        return candidates[0]["id"]
    raise RuntimeError("No accessible parent page found for Notion integration")


def create_database(client: httpx.Client, h: dict, parent_page_id: str) -> str:
    body = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "📋"},
        "is_inline": True,
        "title": [{"type": "text", "text": {"content": DATABASE_TITLE}}],
        "properties": {
            "Company": {"title": {}},
            "Tier": {
                "select": {
                    "options": [
                        {"name": "PLATINUM", "color": "orange"},
                        {"name": "GOLD", "color": "yellow"},
                    ]
                }
            },
            "Status": {
                "select": {
                    "options": [
                        {"name": "Not contacted", "color": "default"},
                        {"name": "Researching", "color": "blue"},
                        {"name": "Email sent", "color": "purple"},
                        {"name": "Follow-up sent", "color": "purple"},
                        {"name": "Replied — interested", "color": "green"},
                        {"name": "Replied — not now", "color": "yellow"},
                        {"name": "Replied — no", "color": "red"},
                        {"name": "Bounced", "color": "red"},
                        {"name": "Booked call", "color": "green"},
                        {"name": "Closed won", "color": "green"},
                        {"name": "Closed lost", "color": "gray"},
                    ]
                }
            },
            "Director": {"rich_text": {}},
            "Email": {"email": {}},
            "Email confidence": {"number": {"format": "number"}},
            "Position": {"rich_text": {}},
            "Phone": {"phone_number": {}},
            "Website": {"url": {}},
            "Location": {"rich_text": {}},
            "Lead score": {"number": {"format": "number"}},
            "Active FB ads": {"number": {"format": "number"}},
            "Director count": {"number": {"format": "number"}},
            "Family business": {"checkbox": {}},
            "Incorporated": {"date": {}},
            "Notes": {"rich_text": {}},
        },
    }
    r = client.post(f"{API}/databases", headers=h, json=body)
    r.raise_for_status()
    return r.json()["id"]


def url_or_none(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def date_or_none(value: Any) -> dict | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return {"start": value.strip()}


def add_row(client: httpx.Client, h: dict, db_id: str, row: dict) -> None:
    props: dict[str, Any] = {
        "Company": {"title": [{"text": {"content": trunc(row.get("company_name") or "Unknown", 1900)}}]},
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
    if pd.notna(fb) and str(fb).strip():
        try:
            props["Active FB ads"] = {"number": int(float(fb))}
        except (TypeError, ValueError):
            pass
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
    inc = date_or_none(row.get("ch_incorporated_on"))
    if inc:
        props["Incorporated"] = {"date": inc}
    addr = row.get("ch_address")
    if isinstance(addr, str) and addr.strip():
        props["Notes"] = {"rich_text": [{"text": {"content": trunc(f"Registered: {addr}")}}]}

    body = {"parent": {"database_id": db_id}, "properties": props}
    r = client.post(f"{API}/pages", headers=h, json=body)
    if r.status_code >= 400:
        print(f"! row failed: {row.get('company_name')}  {r.status_code} {r.text[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/outreach_list.csv")
    args = parser.parse_args()

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print("Set NOTION_TOKEN env var (one-shot, will not be saved)")
        return 1

    df = pd.read_csv(args.input, keep_default_na=False)
    print(f"Pushing {len(df)} prospects to Notion...")

    h = headers(token)
    with httpx.Client(timeout=60.0) as client:
        section_id = create_section_page(client, h)
        print(f"  page: https://www.notion.so/{section_id.replace('-', '')}")
        db_id = create_database(client, h, section_id)
        print(f"  database created: {db_id}")
        for i, (_, row) in enumerate(df.iterrows(), start=1):
            add_row(client, h, db_id, row.to_dict())
            if i % 10 == 0:
                print(f"  {i}/{len(df)} added")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
