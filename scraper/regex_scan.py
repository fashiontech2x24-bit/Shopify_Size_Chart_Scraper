"""
Layer 0 — Universal recipe engine. Fetches raw HTML via HTTP and extracts
size charts using store-specific recipes. No browser needed.

Supports two parse modes controlled entirely by recipe config:
  parse="regex" — HTML container → row regex → cell regex → DataFrame
  parse="json"  — container regex captures JSON blobs → json.loads → DataFrame

No code changes needed for new store formats — just add a recipe.
Typical time: ~0.3–0.5 sec (vs 5–15 sec with browser).
"""

import asyncio
import json
import logging
import re
from urllib.parse import urlparse

import aiohttp
import pandas as pd

from .config import HEADERS, MEASUREMENT_KEYWORDS, SIZE_LABELS
from .recipes import RECIPES

log = logging.getLogger(__name__)

# Compiled regex for stripping HTML tags from cell content
_TAG_STRIP = re.compile(r"<[^>]+>")

# HTTP fetch timeout (seconds)
_FETCH_TIMEOUT = 8


def find_recipe(url: str) -> dict | None:
    """Look up a recipe for the given URL's domain."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, recipe in RECIPES.items():
        if domain in host:
            return recipe
    return None


async def try_regex_scan(
    url: str,
    recipe: dict | None = None,
    storefront_password: str | None = None,
) -> tuple[pd.DataFrame, float]:
    """
    Try to extract a size chart using the universal recipe engine (no browser).

    Returns (DataFrame, confidence) or (empty DataFrame, 0.0).
    Works with an inline recipe (passed directly) or a stored recipe from recipes.py.

    If `storefront_password` is given, first POST it to the Shopify /password
    endpoint on the same origin to obtain a session cookie, then fetch with it.
    """
    if recipe is None:
        recipe = find_recipe(url)
    if not recipe:
        return pd.DataFrame(), 0.0

    store_name = recipe.get("name", "unknown")
    log.info("[regex] Recipe found: %s — fetching HTML...", store_name)

    # Step 1: Fetch raw HTML via HTTP (optionally unlocking Shopify password wall)
    html = await _fetch_html(url, storefront_password=storefront_password)
    if not html:
        log.info("[regex] HTTP fetch failed, skipping")
        return pd.DataFrame(), 0.0

    log.info("[regex] Fetched %d chars", len(html))

    # Step 2: Quick check — does this HTML contain measurement keywords?
    html_lower = html.lower()
    has_measurements = any(kw in html_lower for kw in MEASUREMENT_KEYWORDS)
    if not has_measurements:
        log.info("[regex] No measurement keywords in HTML, skipping")
        return pd.DataFrame(), 0.0

    # Step 3: Extract product title
    title = _extract_title(html, url, store_name)
    log.info("[regex] Product: %s", title)

    # Step 4: Apply universal recipe
    df = _apply_universal_recipe(html, recipe, title)
    if df.empty:
        log.info("[regex] Recipe matched no data")
        return pd.DataFrame(), 0.0

    # Step 5: Compute confidence
    confidence = _compute_confidence(df)
    log.info("[regex] Extracted %d sizes, confidence: %.2f", len(df), confidence)

    return df, confidence


async def _fetch_html(url: str, storefront_password: str | None = None) -> str | None:
    """
    Fetch raw HTML via aiohttp. Returns None on failure (with logged reason).

    If `storefront_password` is provided, POST it to `<origin>/password` inside
    the same session first so the `_shopify_essential` cookie is present for
    the subsequent GET. This unlocks password-protected Shopify preview stores.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=_FETCH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if storefront_password:
                parsed = urlparse(url)
                origin = f"{parsed.scheme}://{parsed.netloc}"
                try:
                    async with session.post(
                        f"{origin}/password",
                        data={
                            "form_type": "storefront_password",
                            "utf8": "✓",
                            "password": storefront_password,
                        },
                        headers=HEADERS,
                        allow_redirects=True,
                    ) as auth_resp:
                        log.info("[regex] Storefront auth → HTTP %d", auth_resp.status)
                except Exception as e:
                    log.info("[regex] Storefront auth failed: %s", e)

            async with session.get(url, headers=HEADERS, allow_redirects=True) as resp:
                if resp.status != 200:
                    log.info("[regex] HTTP %d for %s", resp.status, url)
                    return None
                return await resp.text()
    except asyncio.TimeoutError:
        log.info("[regex] HTTP fetch timeout (%ds) for %s", _FETCH_TIMEOUT, url)
        return None
    except aiohttp.ClientError as e:
        log.info("[regex] HTTP fetch client error for %s: %s", url, e)
        return None
    except Exception as e:
        log.warning("[regex] HTTP fetch unexpected error for %s: %s", url, e)
        return None


def _apply_universal_recipe(html: str, recipe: dict, title: str) -> pd.DataFrame:
    """
    Universal recipe engine — one function handles all store formats.

    Pipeline:
      1. Container match (regex, first match wins if list)
      2. Parse: "regex" → row/cell extraction, "json" → json.loads capture groups
      3. Cell-key extraction (for nested objects like {"in":"32","cm":"82"})
      4. Value formatting (plain, slash_cm, slash_inches)
      5. Build DataFrame with Product + Unit columns
    """
    # --- Step 1: Container match ---
    containers = recipe["container"]
    if isinstance(containers, str):
        containers = [containers]

    # Normalize json_rows/json_headers to lists aligned with containers
    json_rows_list = recipe.get("json_rows", [1])
    json_headers_list = recipe.get("json_headers", [2])
    if isinstance(json_rows_list, int):
        json_rows_list = [json_rows_list] * len(containers)
    if isinstance(json_headers_list, int):
        json_headers_list = [json_headers_list] * len(containers)

    match = None
    pattern_idx = 0
    for i, pattern in enumerate(containers):
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            pattern_idx = i
            break

    if not match:
        return pd.DataFrame()

    # --- Step 2: Parse ---
    parse_mode = recipe.get("parse", "regex")
    fmt = recipe.get("value_format", "plain")
    unit = recipe.get("unit", "cm")

    if parse_mode == "json":
        return _parse_json_mode(match, pattern_idx, json_rows_list, json_headers_list, recipe, fmt, unit, title)
    else:
        return _parse_regex_mode(match, recipe, fmt, unit, title)


def _parse_regex_mode(match, recipe: dict, fmt: str, unit: str, title: str) -> pd.DataFrame:
    """Parse using row/cell regex patterns (HTML tables, lists, etc.)."""
    container_html = match.group(0)

    # Find all rows inside the container
    row_matches = re.findall(recipe["row"], container_html, re.DOTALL | re.IGNORECASE)
    if not row_matches:
        return pd.DataFrame()

    # Extract cells from each row
    rows = []
    for row_html in row_matches:
        cells = re.findall(recipe["cell"], row_html, re.DOTALL | re.IGNORECASE)
        cleaned = [_TAG_STRIP.sub("", c).strip() for c in cells]
        if any(cleaned):
            rows.append(cleaned)

    if not rows or len(rows) < 2:
        return pd.DataFrame()

    # Build DataFrame based on layout
    layout = recipe.get("first_row", "headers")

    if layout == "headers":
        headers = rows[0]
        data = []
        for row in rows[1:]:
            d = {}
            for j, h in enumerate(headers):
                val = row[j] if j < len(row) else ""
                d[h] = _parse_value(val, fmt)
            data.append(d)
    elif layout == "sizes":
        size_row = rows[0]
        sizes = size_row[1:]
        data = [{"Size": s} for s in sizes]
        for meas_row in rows[1:]:
            if not meas_row:
                continue
            measure_name = meas_row[0]
            clean_name = re.sub(r"\s*\(.*?\)\s*$", "", measure_name).strip()
            if not clean_name:
                continue
            values = meas_row[1:]
            for i, size_dict in enumerate(data):
                raw = values[i] if i < len(values) else ""
                size_dict[clean_name] = _parse_value(raw, fmt)
    else:
        return pd.DataFrame()

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df.insert(0, "Product", title)
    df.insert(1, "Unit", unit)
    return df


def _unescape_json(s: str) -> str:
    """Unescape common escape sequences found in embedded JSON (Next.js, Shopify)."""
    return (
        s.replace('\\"', '"')
         .replace("\\/", "/")
         .replace("\\n", " ")
         .replace("\\t", " ")
    )


def _parse_json_mode(match, pattern_idx: int, json_rows_list: list, json_headers_list: list,
                     recipe: dict, fmt: str, unit: str, title: str) -> pd.DataFrame:
    """Parse using JSON — extract capture groups, json.loads, build DataFrame."""
    if pattern_idx >= len(json_rows_list) or pattern_idx >= len(json_headers_list):
        log.info("[regex] Recipe misconfigured: json_rows/json_headers shorter than container list")
        return pd.DataFrame()

    rows_group = json_rows_list[pattern_idx]
    headers_group = json_headers_list[pattern_idx]

    try:
        rows_str = match.group(rows_group)
        headers_str = match.group(headers_group)
    except IndexError as e:
        log.info("[regex] Recipe misconfigured: capture group out of range in pattern %d (%s)",
                 pattern_idx, e)
        return pd.DataFrame()

    # Unescape if needed (for Next.js / Shopify escaped JSON)
    if recipe.get("unescape"):
        rows_str = _unescape_json(rows_str)
        headers_str = _unescape_json(headers_str)

    try:
        headers = json.loads(headers_str)
        rows_data = json.loads(rows_str)
    except json.JSONDecodeError as e:
        log.info("[regex] JSON parse error: %s", e)
        return pd.DataFrame()

    if not headers or not rows_data:
        return pd.DataFrame()

    cell_key = recipe.get("cell_key")

    # Normalize: array-of-objects → array-of-arrays
    if rows_data and isinstance(rows_data[0], dict):
        normalized = []
        for row_obj in rows_data:
            row_values = []
            for h in headers:
                val = row_obj.get(h, "")
                if isinstance(val, dict) and cell_key:
                    val = val.get(cell_key, "")
                row_values.append(str(val))
            normalized.append(row_values)
        rows_data = normalized
    else:
        # Array-of-arrays — apply cell_key if cells are somehow objects (unlikely but safe)
        normalized = []
        for row in rows_data:
            row_values = []
            for val in row:
                if isinstance(val, dict) and cell_key:
                    val = val.get(cell_key, "")
                row_values.append(str(val))
            normalized.append(row_values)
        rows_data = normalized

    # Build DataFrame
    data = []
    for row in rows_data:
        d = {}
        for j, h in enumerate(headers):
            val = row[j] if j < len(row) else ""
            d[h] = _parse_value(val, fmt)
        data.append(d)

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df.insert(0, "Product", title)
    df.insert(1, "Unit", unit)
    return df


def _extract_title(html: str, url: str, brand_name: str) -> str:
    """Extract product title from HTML meta tags or <title>."""
    # Try og:title (cleanest)
    og = re.search(r'property="og:title"\s+content="([^"]*)"', html, re.IGNORECASE)
    if og:
        title = og.group(1).strip()
        title = re.sub(
            rf"\s*[|–\-]\s*{re.escape(brand_name)}.*$", "", title, flags=re.IGNORECASE
        )
        if title:
            return title

    # Try <title> tag
    title_tag = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title_tag:
        title = title_tag.group(1).strip()
        title = re.sub(
            rf"\s*[|–\-]\s*{re.escape(brand_name)}.*$", "", title, flags=re.IGNORECASE
        )
        if title:
            return title

    # Fallback: extract from URL
    if "/products/" in url:
        return url.split("/products/")[-1].split("?")[0].replace("-", " ").title()
    return url.rstrip("/").split("/")[-1].replace("-", " ").title()


def _parse_value(raw: str, fmt: str) -> str:
    """
    Parse a cell value according to the recipe's value_format.

    plain:         "96"       → "96"
    slash_cm:      "30/76.2"  → "76.2"   (inches/cm → take cm)
    slash_inches:  "76.2/30"  → "76.2"   (cm/inches → take cm)
    """
    raw = raw.strip()
    if not raw:
        return raw

    if fmt == "slash_cm" and "/" in raw:
        parts = raw.split("/")
        return parts[1].strip() if len(parts) == 2 else raw

    if fmt == "slash_inches" and "/" in raw:
        parts = raw.split("/")
        return parts[0].strip() if len(parts) == 2 else raw

    return raw


def _compute_confidence(df: pd.DataFrame) -> float:
    """Score confidence based on DataFrame quality."""
    if df.empty:
        return 0.0

    score = 0.3  # base score — recipe matched

    # Bonus: recognized measurement columns (substring match so "To Fit Bust" counts).
    cols_lower = [c.lower() for c in df.columns]
    matched_measurements = {
        kw for kw in MEASUREMENT_KEYWORDS if any(kw in col for col in cols_lower)
    }
    if matched_measurements:
        score += min(len(matched_measurements) * 0.1, 0.3)

    # Bonus: recognized size labels
    if "Size" in df.columns:
        known = sum(1 for s in df["Size"] if s.upper() in SIZE_LABELS)
        if known >= 2:
            score += 0.2

    # Bonus: numeric values in measurement columns
    numeric_count = 0
    total_count = 0
    for col in df.columns:
        if col in ("Product", "Unit", "Size"):
            continue
        for val in df[col]:
            total_count += 1
            try:
                float(val)
                numeric_count += 1
            except (ValueError, TypeError):
                pass
    if total_count > 0 and numeric_count / total_count >= 0.7:
        score += 0.2

    return min(score, 1.0)
