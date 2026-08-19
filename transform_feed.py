#!/usr/bin/env python3
"""
Pulls the Sur La Table culinary feed from ChannelAdvisor, filters to classes
starting 3-30 days from today, maps fields to AppLovin's catalog schema, and
writes the result to OUTPUT_PATH.

Designed to be run daily by GitHub Actions (see .github/workflows/update-feed.yml).
"today" is computed fresh on every run, so the 3-30 day window always rolls forward.

Environment variables:
    CHANNELADVISOR_FEED_URL   (required) - URL ChannelAdvisor serves the raw feed from
    CA_AUTH_USER              (optional) - HTTP basic auth username, if the feed needs it
    CA_AUTH_PASS              (optional) - HTTP basic auth password, if the feed needs it
    CA_API_KEY                (optional) - sent as header "X-Api-Key: <value>" if the feed needs it
    OUTPUT_PATH               (optional) - where to write the CSV. Defaults to
                              feed/applovin_catalog_feed.csv
    WINDOW_START_DAYS         (optional) - defaults to 3
    WINDOW_END_DAYS           (optional) - defaults to 30
"""

import os
import re
import sys
import csv
import io
from datetime import datetime, timedelta

import pandas as pd
import requests

CHANNELADVISOR_FEED_URL = os.environ.get("CHANNELADVISOR_FEED_URL")
CA_AUTH_USER = os.environ.get("CA_AUTH_USER")
CA_AUTH_PASS = os.environ.get("CA_AUTH_PASS")
CA_API_KEY = os.environ.get("CA_API_KEY")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "feed/applovin_catalog_feed.csv")
WINDOW_START_DAYS = int(os.environ.get("WINDOW_START_DAYS", "3"))
WINDOW_END_DAYS = int(os.environ.get("WINDOW_END_DAYS", "30"))

REQUIRED_SOURCE_COLUMNS = [
    "id", "item_group_id", "title", "price", "image_link", "availability",
    "link", "description", "brand", "google_product_category", "sale_price",
    "additional_image_link", "custom_label_0",
]


def fetch_raw_feed() -> pd.DataFrame:
    if not CHANNELADVISOR_FEED_URL:
        sys.exit("ERROR: CHANNELADVISOR_FEED_URL environment variable is not set.")

    auth = None
    headers = {}
    if CA_AUTH_USER and CA_AUTH_PASS:
        auth = (CA_AUTH_USER, CA_AUTH_PASS)
    if CA_API_KEY:
        headers["X-Api-Key"] = CA_API_KEY

    resp = requests.get(CHANNELADVISOR_FEED_URL, auth=auth, headers=headers, timeout=120)
    resp.raise_for_status()

    # ChannelAdvisor feed exports are tab-separated; adjust sep here if yours differs.
    df = pd.read_csv(io.StringIO(resp.text), sep="\t", dtype=str, keep_default_na=False)

    missing = [c for c in REQUIRED_SOURCE_COLUMNS if c not in df.columns]
    if missing:
        sys.exit(f"ERROR: source feed is missing expected columns: {missing}")

    return df


def clean(val, max_len=None) -> str:
    if val is None:
        val = ""
    val = str(val)
    val = val.replace(",", ";")          # AppLovin CSVs can't contain raw commas
    val = val.replace('"', '\\"')        # AppLovin escapes quotes with a backslash
    val = val.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    val = " ".join(val.split())
    if max_len is not None and len(val) > max_len:
        val = val[:max_len]
    return val


def clean_price(val) -> str:
    val = str(val).strip()
    if val.endswith(" USD"):
        val = val[:-4].strip()
    return val


def extract_cfa(link: str):
    m = re.search(r"(CFA-\d+)", link or "")
    return m.group(1) if m else None


def transform(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["parsed_date"] = pd.to_datetime(df["custom_label_0"], format="%m-%d-%Y", errors="coerce")

    today = pd.Timestamp(datetime.now().date())
    start = today + timedelta(days=WINDOW_START_DAYS)
    end = today + timedelta(days=WINDOW_END_DAYS)
    df = df[(df["parsed_date"] >= start) & (df["parsed_date"] <= end)]

    rows = []
    for _, r in df.iterrows():
        cfa = extract_cfa(r["link"])
        rows.append({
            "id": clean(r["id"], 64),
            "itemId": clean(cfa if cfa else r["id"], 64),
            "name": clean(r["title"], 1024),
            "price": clean_price(r["price"]),
            "primaryImageUrl": clean(r["image_link"], 2048),
            "isAvailable": "TRUE" if r["availability"].strip().lower() == "in stock" else "FALSE",
            "webUrl": clean(r["link"], 2048),
            "description": clean(r["description"], 8192),
            "brand": clean(r["brand"], 256),
            "categoryId": clean(r["google_product_category"]),
            "salePrice": clean_price(r["sale_price"]) if r["sale_price"] else "",
            "additionalImageUrls": clean(r["additional_image_link"], 2048) if r["additional_image_link"] else "",
        })

    return pd.DataFrame(rows, columns=[
        "id", "itemId", "name", "price", "primaryImageUrl", "isAvailable", "webUrl",
        "description", "brand", "categoryId", "salePrice", "additionalImageUrls",
    ])


def validate(out_df: pd.DataFrame):
    required = ["id", "itemId", "name", "price", "primaryImageUrl", "isAvailable", "webUrl"]
    problems = []

    if out_df["id"].duplicated().any():
        problems.append(f"{out_df['id'].duplicated().sum()} duplicate id(s)")

    for col in required:
        empty = (out_df[col] == "").sum()
        if empty:
            problems.append(f"{empty} empty value(s) in required column '{col}'")

    bad_prices = out_df[~out_df["price"].str.match(r"^\d+\.\d{2}$")]
    if len(bad_prices):
        problems.append(f"{len(bad_prices)} row(s) with non-numeric price")

    if problems:
        sys.exit("VALIDATION FAILED:\n  - " + "\n  - ".join(problems))

    print(f"Validation passed: {len(out_df)} rows, {out_df['itemId'].nunique()} unique items.")


def main():
    raw_df = fetch_raw_feed()
    out_df = transform(raw_df)

    if len(out_df) == 0:
        sys.exit("ERROR: transform produced 0 rows — refusing to overwrite the live feed with an empty file.")

    validate(out_df)

    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)
    out_df.to_csv(OUTPUT_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Wrote {len(out_df)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
