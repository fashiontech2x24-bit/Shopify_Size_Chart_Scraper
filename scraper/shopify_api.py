"""
Shopify API fallback — try to extract size chart from product JSON endpoint.

Many Shopify stores expose /products/<handle>.json which may contain
size chart data embedded in the product body HTML. Uses plain HTTP
(aiohttp) — no browser needed.
"""

import json
import logging
import re

import aiohttp
import pandas as pd

from .config import HEADERS

log = logging.getLogger(__name__)

_FETCH_TIMEOUT = 8


async def try_shopify_api(product_url: str, browser=None) -> tuple:
    """
    Try to fetch size chart from Shopify's product JSON API via HTTP.

    The `browser` kwarg is accepted for backwards compatibility but unused.
    Returns (pd.DataFrame, float confidence) or (empty DataFrame, 0.0).
    """
    if "/products/" not in product_url:
        return pd.DataFrame(), 0.0

    json_url = product_url.split("?")[0]
    if not json_url.endswith(".json"):
        json_url += ".json"

    text = await _fetch(json_url)
    if not text:
        return pd.DataFrame(), 0.0

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        log.info("[shopify] JSON parse error for %s: %s", json_url, e)
        return pd.DataFrame(), 0.0

    product = data.get("product", {})
    body_html = product.get("body_html", "")
    title = product.get("title", "")

    if not body_html:
        return pd.DataFrame(), 0.0

    df = _parse_html_tables(body_html, title)
    if not df.empty:
        return df, 0.4  # Low confidence — embedded tables may not be size charts

    return pd.DataFrame(), 0.0


async def _fetch(url: str) -> str | None:
    try:
        timeout = aiohttp.ClientTimeout(total=_FETCH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=HEADERS, allow_redirects=True) as resp:
                if resp.status != 200:
                    log.info("[shopify] HTTP %d for %s", resp.status, url)
                    return None
                return await resp.text()
    except Exception as e:
        log.info("[shopify] Fetch failed for %s: %s", url, e)
        return None


def _parse_html_tables(html: str, title: str) -> pd.DataFrame:
    """Parse HTML tables from product body_html."""
    table_pattern = re.compile(r'<table[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
    row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    cell_pattern = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.DOTALL | re.IGNORECASE)
    tag_strip = re.compile(r'<[^>]+>')

    tables = table_pattern.findall(html)
    if not tables:
        return pd.DataFrame()

    best_df = pd.DataFrame()
    for table_html in tables:
        rows_html = row_pattern.findall(table_html)
        if len(rows_html) < 2:
            continue

        parsed_rows = []
        for row_html in rows_html:
            cells = cell_pattern.findall(row_html)
            cleaned = [tag_strip.sub("", c).strip() for c in cells]
            parsed_rows.append(cleaned)

        if not parsed_rows:
            continue

        all_text = " ".join(" ".join(row) for row in parsed_rows).lower()
        if "size" in all_text and any(kw in all_text for kw in
                ("chest", "waist", "hip", "bust", "shoulder", "length", "inseam")):
            headers = parsed_rows[0]
            data_rows = []
            for row in parsed_rows[1:]:
                if not any(c.strip() for c in row):
                    continue
                d = {}
                for j, h in enumerate(headers):
                    if j < len(row):
                        d[h] = row[j]
                data_rows.append(d)

            if data_rows:
                df = pd.DataFrame(data_rows)
                df.insert(0, "Product", title)
                df.insert(1, "Unit", "cm")
                if len(df) > len(best_df):
                    best_df = df

    return best_df
