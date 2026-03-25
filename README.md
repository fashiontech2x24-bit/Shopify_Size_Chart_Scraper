# Size Chart Scraper

Scrapes size chart data from any product URL. Returns structured measurements in CM.

## Quick Start

```bash
docker compose down && docker compose up --build
```

Runs on `http://localhost:8000`

## API

### Health Check

```
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "browser": "running",
  "uptime_seconds": 120,
  "max_parallel": 4
}
```

---

### Scrape Size Chart

```
POST /scrape
Content-Type: application/json
```

**Request fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | Product page URL (must start with http:// or https://) |
| `recipe` | object | No | Inline recipe for Layer 0 regex extraction. If omitted, falls back to `recipes.py` then browser layers |
| `skip_browser` | boolean | No | If `true`, skip browser layers (1/2/3) when recipe fails. Default: `false` |
| `store_name` | string | No | Store name for logging and response. If omitted, auto-detected from URL |

**Recipe object fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Store display name (used in logs and title cleanup) |
| `format` | string | No | `"jotly_json"` for Shopify Jotly stores. Omit for HTML regex |
| `container` | string | For regex | Regex to match the entire size chart section |
| `row` | string | For regex | Regex with ONE capture group for each row |
| `cell` | string | For regex | Regex with ONE capture group for each cell |
| `value_format` | string | Yes | `"plain"`, `"slash_cm"` (30/76.2 → 76.2), or `"slash_inches"` (76.2/30 → 76.2) |
| `first_row` | string | For regex | `"headers"` (first row = column names) or `"sizes"` (first row = size labels, transposed) |

---

#### Example 1: Basic request (no recipe, uses existing workflow)

**Request:**
```json
{
  "url": "https://www.snitch.co.in/products/some-product"
}
```

**Response (success):**
```json
{
  "success": true,
  "url": "https://www.snitch.co.in/products/some-product",
  "store": "snitch",
  "product": "Product Name",
  "unit": "cm",
  "columns": ["Product", "Unit", "Size", "Chest", "Waist", "Hip"],
  "data": [
    {
      "Product": "Product Name",
      "Unit": "cm",
      "Size": "S",
      "Chest": "96",
      "Waist": "76",
      "Hip": "96"
    }
  ],
  "error": null
}
```

---

#### Example 2: Inline recipe (Jotly JSON format)

**Request:**
```json
{
  "url": "https://almostgods.com/products/zodiac-polo",
  "store_name": "Almost Gods",
  "recipe": {
    "name": "Almost Gods",
    "format": "jotly_json",
    "value_format": "plain"
  }
}
```

**Response:**
```json
{
  "success": true,
  "url": "https://almostgods.com/products/zodiac-polo",
  "store": "Almost Gods",
  "product": "Zodiac Relaxed Polo",
  "unit": "cm",
  "columns": ["Product", "Unit", "Size", "Shoulder", "Chest", "Sleeve length", "Length"],
  "data": [
    {
      "Product": "Zodiac Relaxed Polo",
      "Unit": "cm",
      "Size": "XS",
      "Shoulder": "17.5",
      "Chest": "40",
      "Sleeve length": "9",
      "Length": "26"
    },
    {
      "Product": "Zodiac Relaxed Polo",
      "Unit": "cm",
      "Size": "S",
      "Shoulder": "18",
      "Chest": "42",
      "Sleeve length": "9.5",
      "Length": "26.5"
    },
    {
      "Product": "Zodiac Relaxed Polo",
      "Unit": "cm",
      "Size": "M",
      "Shoulder": "18.5",
      "Chest": "44",
      "Sleeve length": "10",
      "Length": "27"
    },
    {
      "Product": "Zodiac Relaxed Polo",
      "Unit": "cm",
      "Size": "L",
      "Shoulder": "19",
      "Chest": "46",
      "Sleeve length": "10.5",
      "Length": "27.5"
    },
    {
      "Product": "Zodiac Relaxed Polo",
      "Unit": "cm",
      "Size": "XL",
      "Shoulder": "19.5",
      "Chest": "48",
      "Sleeve length": "11",
      "Length": "28"
    },
    {
      "Product": "Zodiac Relaxed Polo",
      "Unit": "cm",
      "Size": "XXL",
      "Shoulder": "20",
      "Chest": "50",
      "Sleeve length": "11.5",
      "Length": "28.5"
    },
    {
      "Product": "Zodiac Relaxed Polo",
      "Unit": "cm",
      "Size": "XXXL",
      "Shoulder": "20.5",
      "Chest": "52",
      "Sleeve length": "12",
      "Length": "29"
    }
  ],
  "error": null
}
```

---

#### Example 3: Inline recipe (HTML regex format)

**Request:**
```json
{
  "url": "https://www.sheetalbatra.com/products/kaina",
  "store_name": "Sheetal Batra",
  "recipe": {
    "name": "Sheetal Batra",
    "container": "<ul class=\"main-chrt\"[^>]*>(.*?)</ul>\\s*</li>\\s*</ul>",
    "row": "<ul[^>]*class=\"main-size[^\"]*\"[^>]*>(.*?)</ul>",
    "cell": "<li>(.*?)</li>",
    "value_format": "slash_cm",
    "first_row": "sizes"
  }
}
```

**Response:**
```json
{
  "success": true,
  "url": "https://www.sheetalbatra.com/products/kaina",
  "store": "Sheetal Batra",
  "product": "Kaina- Soft Blue Pure chanderi silk Parsi-gara Embroidered Ensemble",
  "unit": "cm",
  "columns": ["Product", "Unit", "Size", "Bust", "Waist", "Hip"],
  "data": [
    {
      "Product": "Kaina- Soft Blue Pure chanderi silk Parsi-gara Embroidered Ensemble",
      "Unit": "cm",
      "Size": "XXS",
      "Bust": "76.2",
      "Waist": "61",
      "Hip": "86.4"
    },
    {
      "Product": "Kaina- Soft Blue Pure chanderi silk Parsi-gara Embroidered Ensemble",
      "Unit": "cm",
      "Size": "XS",
      "Bust": "81.3",
      "Waist": "66",
      "Hip": "91.4"
    }
  ],
  "error": null
}
```

---

#### Example 4: skip_browser (recipe-only mode)

When testing a new recipe, use `skip_browser: true` to get instant failure instead of waiting 15+ seconds for browser fallback.

**Request:**
```json
{
  "url": "https://random-store.com/products/test",
  "store_name": "Test Store",
  "skip_browser": true,
  "recipe": {
    "name": "Test Store",
    "container": "<table class=\"size-chart\">(.*?)</table>",
    "row": "<tr>(.*?)</tr>",
    "cell": "<td>(.*?)</td>",
    "value_format": "plain",
    "first_row": "headers"
  }
}
```

**Response (recipe didn't match):**
```json
{
  "success": false,
  "url": "https://random-store.com/products/test",
  "store": "Test Store",
  "product": null,
  "unit": null,
  "columns": null,
  "data": null,
  "error": "No size chart data found"
}
```

---

#### Response (failure)

```json
{
  "success": false,
  "url": "https://example.com/products/something",
  "store": "unknown",
  "product": null,
  "unit": null,
  "columns": null,
  "data": null,
  "error": "No size chart data found"
}
```

#### Response (timeout)

```json
{
  "success": false,
  "url": "https://example.com/products/something",
  "store": "unknown",
  "product": null,
  "unit": null,
  "columns": null,
  "data": null,
  "error": "Scrape timed out after 60s"
}
```

## Scraping Layers

Requests flow through 4 layers in order. The first layer that returns data wins.

| Layer | Method | Speed | When it runs |
|-------|--------|-------|-------------|
| 0 — Regex | HTTP fetch + regex | ~0.3 sec | Inline recipe provided OR domain matches `scraper/recipes.py` |
| 1 — Known Store | Browser + custom scraper | ~5-15 sec | Store has a scraper in `scraper/stores/` |
| 2 — Universal | Browser + auto-detection | ~5-15 sec | Any unknown store |
| 3 — Shopify API | API call | ~1 sec | URL contains `/products/` |

If `skip_browser: true` is set, layers 1/2/3 are skipped entirely.

## Adding a New Store

### Option A: Via API (inline recipe — no rebuild needed)

Send the recipe in the request body. Your admin app stores recipes in its own DB and sends them per-request.

```bash
curl -s -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://newstore.com/products/something",
    "store_name": "New Store",
    "recipe": {
      "name": "New Store",
      "format": "jotly_json",
      "value_format": "plain"
    }
  }' | python3 -m json.tool
```

### Option B: Via recipes.py (hardcoded — requires rebuild)

1. Open the product page in Chrome → `Ctrl+U` → copy the HTML source
2. Give the HTML to ChatGPT/Claude with this prompt:

   > I need a regex recipe to extract the size chart from this HTML. Give me these 5 fields as Python strings:
   > 1. container — regex that captures the entire size chart section
   > 2. row — regex with ONE capture group for each row inside the container
   > 3. cell — regex with ONE capture group for each cell inside a row
   > 4. value_format — one of: plain, slash_cm, slash_inches
   > 5. first_row — "headers" or "sizes"

3. Add the recipe to `scraper/recipes.py`:

   ```python
   "newstore.com": {
       "name": "New Store",
       "container": r'...',
       "row": r'...',
       "cell": r'...',
       "value_format": "plain",
       "first_row": "headers",
   },
   ```

   For Shopify stores using the **Jotly size chart app**, use:

   ```python
   "newstore.com": {
       "name": "New Store",
       "format": "jotly_json",
       "value_format": "plain",
   },
   ```

4. Rebuild and test:
   ```bash
   docker compose down && docker compose up --build -d
   curl -s -X POST http://localhost:8000/scrape \
     -H "Content-Type: application/json" \
     -d '{"url": "https://newstore.com/products/something"}' | python3 -m json.tool
   ```

## Current Recipes

| Store | Domain | Format |
|-------|--------|--------|
| Sheetal Batra | `sheetalbatra.com` | HTML regex |
| Almost Gods | `almostgods.com` | Jotly JSON |

## Known Store Scrapers (Layer 1)

Snitch, Fashion Nova, Libas, Rare Rabbit, Gymshark, Bombay Shirts, The Loom, Outdoor Voices, Good American
