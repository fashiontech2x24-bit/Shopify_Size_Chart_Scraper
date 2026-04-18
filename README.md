# Size Chart Scraper

Scrapes size chart data from any product URL. Returns structured measurements in CM.

## Quick Start

```bash
docker compose down && docker compose up --build
```

Runs on `http://localhost:8000`. Logs stream to terminal. Press `Ctrl+C` to stop.

Background mode:
```bash
docker compose down && docker compose up --build -d
docker compose logs -f
```

---

## API

### GET /health

```bash
curl http://localhost:8000/health
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

### POST /scrape

```bash
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/products/shirt"}'
```

#### Request Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | Yes | — | Product page URL (http:// or https://) |
| `recipe` | object | No | `null` | Inline recipe for Layer 0 extraction. If omitted, falls back to stored recipes then browser layers |
| `skip_browser` | boolean | No | `false` | If `true`, skip browser layers (1/2/3) when recipe fails — returns instantly |
| `store_name` | string | No | auto-detected | Store name for logging and response `store` field |
| `storefront_password` | string | No | `null` | Shopify storefront password — when set, the service POSTs it to `<origin>/password` before fetching, enabling password-protected preview stores at Layer 0 |

#### Recipe Object Fields

The recipe tells the engine how to find and parse size chart data from raw HTML. Two parse modes: `regex` (for HTML) and `json` (for embedded JSON).

**Common fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | — | Store display name (used in logs) |
| `container` | string or array | Yes | — | Regex pattern(s) to find the data blob. Array = try each in order until one matches |
| `parse` | string | No | `"regex"` | Parse mode: `"regex"` or `"json"` |
| `unescape` | boolean | No | `false` | If `true`, replace `\"` with `"` before JSON parsing (for Next.js escaped data) |
| `cell_key` | string | No | `null` | If cells are objects like `{"in":"32","cm":"82"}`, extract this key |
| `value_format` | string | Yes | — | `"plain"`, `"slash_cm"` (30/76.2 → 76.2), or `"slash_inches"` (76.2/30 → 76.2) |
| `unit` | string | No | `"cm"` | Unit label for the output Unit column |

**Additional fields for `parse: "regex"`:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `row` | string | Yes | Regex with ONE capture group for each row inside the container |
| `cell` | string | Yes | Regex with ONE capture group for each cell inside a row |
| `first_row` | string | Yes | `"headers"` (row 0 = column names) or `"sizes"` (row 0 = size labels, transposed layout) |

**Additional fields for `parse: "json"`:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `json_headers` | int or array | Yes | Capture group number(s) from `container` regex that contains the headers JSON array |
| `json_rows` | int or array | Yes | Capture group number(s) from `container` regex that contains the rows JSON array |

When `container` is a list, `json_headers` and `json_rows` must also be lists of the same length — each entry maps to the corresponding container pattern.

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | `true` if size chart data was found |
| `url` | string | The requested URL |
| `store` | string | Store name (from `store_name`, auto-detected, or `"unknown"`) |
| `product` | string or null | Product name extracted from the page |
| `unit` | string or null | `"cm"` (always CM) |
| `columns` | array or null | Column names: `["Product", "Unit", "Size", "Chest", ...]` |
| `data` | array or null | Array of row objects, one per size |
| `error` | string or null | Error message if `success` is `false` |

---

## Examples

### 1. Basic request (no recipe — uses browser)

```json
{
  "url": "https://www.snitch.co.in/products/some-product"
}
```

Response:
```json
{
  "success": true,
  "url": "https://www.snitch.co.in/products/some-product",
  "store": "snitch",
  "product": "Product Name",
  "unit": "cm",
  "columns": ["Product", "Unit", "Size", "Chest", "Waist", "Hip"],
  "data": [
    {"Product": "Product Name", "Unit": "cm", "Size": "S", "Chest": "96", "Waist": "76", "Hip": "96"}
  ],
  "error": null
}
```

---

### 2. Inline recipe — HTML regex (parse: "regex")

For stores where the size chart is in HTML elements (tables, lists, divs).

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

Response:
```json
{
  "success": true,
  "url": "https://www.sheetalbatra.com/products/kaina",
  "store": "Sheetal Batra",
  "product": "Kaina- Soft Blue Pure chanderi silk Parsi-gara Embroidered Ensemble",
  "unit": "cm",
  "columns": ["Product", "Unit", "Size", "Bust", "Waist", "Hip"],
  "data": [
    {"Product": "Kaina-...", "Unit": "cm", "Size": "XXS", "Bust": "76.2", "Waist": "61", "Hip": "86.4"},
    {"Product": "Kaina-...", "Unit": "cm", "Size": "XS", "Bust": "81.3", "Waist": "66", "Hip": "91.4"},
    {"Product": "Kaina-...", "Unit": "cm", "Size": "S", "Bust": "86.4", "Waist": "71.1", "Hip": "96.5"},
    {"Product": "Kaina-...", "Unit": "cm", "Size": "M", "Bust": "91.4", "Waist": "76.2", "Hip": "102"},
    {"Product": "Kaina-...", "Unit": "cm", "Size": "L", "Bust": "96.5", "Waist": "81.3", "Hip": "107"},
    {"Product": "Kaina-...", "Unit": "cm", "Size": "XL", "Bust": "102", "Waist": "86.4", "Hip": "112"}
  ],
  "error": null
}
```

---

### 3. Inline recipe — JSON with array-of-arrays (parse: "json")

For stores with embedded JSON like Jotly/Shopify where rows are `[["XS","17.5","40"],...]`.

```json
{
  "url": "https://almostgods.com/products/zodiac-polo",
  "store_name": "Almost Gods",
  "recipe": {
    "name": "Almost Gods",
    "container": "\"rows\":\\s*(\\[\\[.*?\\]\\])\\s*,\\s*\"headers\":\\s*(\\[[^\\]]+\\])",
    "parse": "json",
    "json_rows": 1,
    "json_headers": 2,
    "value_format": "plain"
  }
}
```

Response:
```json
{
  "success": true,
  "url": "https://almostgods.com/products/zodiac-polo",
  "store": "Almost Gods",
  "product": "Zodiac Relaxed Polo",
  "unit": "cm",
  "columns": ["Product", "Unit", "Size", "Shoulder", "Chest", "Sleeve length", "Length"],
  "data": [
    {"Product": "Zodiac Relaxed Polo", "Unit": "cm", "Size": "XS", "Shoulder": "17.5", "Chest": "40", "Sleeve length": "9", "Length": "26"},
    {"Product": "Zodiac Relaxed Polo", "Unit": "cm", "Size": "S", "Shoulder": "18", "Chest": "42", "Sleeve length": "9.5", "Length": "26.5"},
    {"Product": "Zodiac Relaxed Polo", "Unit": "cm", "Size": "M", "Shoulder": "18.5", "Chest": "44", "Sleeve length": "10", "Length": "27"},
    {"Product": "Zodiac Relaxed Polo", "Unit": "cm", "Size": "L", "Shoulder": "19", "Chest": "46", "Sleeve length": "10.5", "Length": "27.5"},
    {"Product": "Zodiac Relaxed Polo", "Unit": "cm", "Size": "XL", "Shoulder": "19.5", "Chest": "48", "Sleeve length": "11", "Length": "28"},
    {"Product": "Zodiac Relaxed Polo", "Unit": "cm", "Size": "XXL", "Shoulder": "20", "Chest": "50", "Sleeve length": "11.5", "Length": "28.5"},
    {"Product": "Zodiac Relaxed Polo", "Unit": "cm", "Size": "XXXL", "Shoulder": "20.5", "Chest": "52", "Sleeve length": "12", "Length": "29"}
  ],
  "error": null
}
```

---

### 4. Inline recipe — JSON with nested cell objects (parse: "json" + cell_key)

For stores with escaped Next.js JSON where each cell is an object like `{"in":"32","cm":"82"}`.

```json
{
  "url": "https://www.fablestreet.com/products/cotton-fit-flare-gingham-dress-brown",
  "store_name": "FableStreet",
  "recipe": {
    "name": "FableStreet",
    "container": "\\\\\"headers\\\\\":\\s*(\\[[^\\]]+\\])\\s*,\\s*\\\\\"rows\\\\\":\\s*(\\[(?:\\{.*?\\}(?:,\\s*)?)*\\])",
    "unescape": true,
    "parse": "json",
    "json_headers": 1,
    "json_rows": 2,
    "cell_key": "cm",
    "value_format": "plain",
    "unit": "cm"
  }
}
```

Response:
```json
{
  "success": true,
  "url": "https://www.fablestreet.com/products/cotton-fit-flare-gingham-dress-brown",
  "store": "FableStreet",
  "product": "Buy Brown Cotton Fit & Flare Gingham Dress Online",
  "unit": "cm",
  "columns": ["Product", "Unit", "Size", "To Fit Bust", "To Fit Waist", "To Fit Hip"],
  "data": [
    {"Product": "...", "Unit": "cm", "Size": "XS", "To Fit Bust": "82-84", "To Fit Waist": "69-71", "To Fit Hip": "89-91"},
    {"Product": "...", "Unit": "cm", "Size": "S", "To Fit Bust": "86-89", "To Fit Waist": "74-76", "To Fit Hip": "94-97"},
    {"Product": "...", "Unit": "cm", "Size": "M", "To Fit Bust": "91-94", "To Fit Waist": "79-82", "To Fit Hip": "99-102"},
    {"Product": "...", "Unit": "cm", "Size": "L", "To Fit Bust": "97-99", "To Fit Waist": "84-86", "To Fit Hip": "104-107"},
    {"Product": "...", "Unit": "cm", "Size": "XL", "To Fit Bust": "102-104", "To Fit Waist": "89-91", "To Fit Hip": "109-112"},
    {"Product": "...", "Unit": "cm", "Size": "XXL", "To Fit Bust": "107-109", "To Fit Waist": "94-97", "To Fit Hip": "114-117"}
  ],
  "error": null
}
```

---

### 5. Multiple container patterns (fallback ordering)

When the JSON field order varies between pages, use a list of patterns. The engine tries each in order.

```json
{
  "url": "https://almostgods.com/products/zodiac-polo",
  "store_name": "Almost Gods",
  "recipe": {
    "name": "Almost Gods",
    "container": [
      "\"rows\":\\s*(\\[\\[.*?\\]\\])\\s*,\\s*\"headers\":\\s*(\\[[^\\]]+\\])",
      "\"headers\":\\s*(\\[[^\\]]+\\])\\s*,.*?\"rows\":\\s*(\\[\\[.*?\\]\\])"
    ],
    "parse": "json",
    "json_rows": [1, 2],
    "json_headers": [2, 1],
    "value_format": "plain"
  }
}
```

`json_rows: [1, 2]` means: for pattern 0, rows are in capture group 1; for pattern 1, rows are in capture group 2.

---

### 6. skip_browser (recipe testing mode)

Use `skip_browser: true` when testing a recipe. If it fails, you get an instant error instead of waiting 15+ seconds for browser fallback.

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

Response:
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

### Error Responses

**No data found:**
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

**Timeout (configurable via `SCRAPE_TIMEOUT`, default 60s):**
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

---

## Scraping Layers

Requests flow through 4 layers in order. The first layer that returns data wins.

| Layer | Method | Speed | When it runs |
|-------|--------|-------|-------------|
| 0 — Recipe | HTTP fetch + recipe engine | ~0.3 sec | Inline recipe provided OR domain matches `scraper/recipes.py` |
| 1 — Known Store | Browser + custom scraper | ~5-15 sec | Store has a scraper in `scraper/stores/` |
| 2 — Universal | Browser + auto-detection | ~5-15 sec | Any unknown store |
| 3 — Shopify API | HTTP (no browser) | ~0.5 sec | URL contains `/products/` |

If `skip_browser: true` is set, layers 1/2/3 are skipped entirely.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRAPE_TIMEOUT` | `60` | Per-request scrape timeout (seconds) |
| `API_KEY` | _(unset)_ | If set, `POST /scrape` requires header `X-API-Key: <value>` |
| `ALLOWED_ORIGINS` | `*` | Comma-separated list of CORS origins (e.g. `https://admin.example.com`) |

---

## Adding a New Store

### Option A: Via API (inline recipe — no rebuild needed)

Your admin app stores recipes in its own DB and sends them per-request:

```bash
curl -s -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://newstore.com/products/something",
    "store_name": "New Store",
    "skip_browser": true,
    "recipe": {
      "name": "New Store",
      "container": "<table class=\"size-chart\">(.*?)</table>",
      "row": "<tr>(.*?)</tr>",
      "cell": "<td>(.*?)</td>",
      "value_format": "plain",
      "first_row": "headers"
    }
  }' | python3 -m json.tool
```

### Option B: Via recipes.py (hardcoded — requires rebuild)

1. Open the product page in Chrome, press `Ctrl+U`, copy the HTML source
2. Give the HTML to ChatGPT/Claude with the recipe fields reference above
3. Add the recipe to `scraper/recipes.py`
4. Rebuild: `docker compose down && docker compose up --build -d`

### How to create a recipe

Give the HTML source to ChatGPT/Claude with this prompt:

> I need a recipe to extract the size chart from this HTML. The recipe has these fields:
>
> **If the chart is in HTML elements** (tables, lists, divs):
> - `container` — regex to match the whole chart section
> - `row` — regex with ONE capture group for each row
> - `cell` — regex with ONE capture group for each cell
> - `first_row` — "headers" (row 0 = column names) or "sizes" (row 0 = size labels)
> - `value_format` — "plain", "slash_cm" (30/76.2 → take 76.2), or "slash_inches"
>
> **If the chart is in embedded JSON** (Jotly, Next.js, etc.):
> - `container` — regex with capture groups for the headers and rows JSON arrays
> - `parse` — "json"
> - `json_headers` — which capture group has the headers array
> - `json_rows` — which capture group has the rows array
> - `unescape` — true if the JSON has escaped quotes (\")
> - `cell_key` — if cells are objects like {"in":"32","cm":"82"}, which key to extract
> - `value_format` — "plain", "slash_cm", or "slash_inches"

---

## Current Stored Recipes

| Store | Domain | Parse Mode | Notes |
|-------|--------|-----------|-------|
| Sheetal Batra | `sheetalbatra.com` | regex | HTML lists, values in inches/cm format |
| Almost Gods | `almostgods.com` | json | Jotly app, array-of-arrays |
| FableStreet | `fablestreet.com` | json | Next.js escaped JSON, nested cell objects |

## Known Store Scrapers (Layer 1)

Snitch, Fashion Nova, Libas, Rare Rabbit, Gymshark, Bombay Shirts, The Loom, Outdoor Voices, Good American
