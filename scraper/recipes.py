"""
Store recipes for regex-based scraping (Layer 0 — no browser needed).

Each recipe tells the universal engine how to find and extract size chart data
from a store's raw HTML source. No code changes needed for new formats.

RECIPE FIELDS:
  name          (str, required)     Store display name
  container     (str or list)       Regex pattern(s) to find the data blob. List = try each in order.
  parse         (str)               "regex" (default) or "json"
  unescape      (bool)             If true, replace \\" with " before JSON parsing (default: false)

  For parse="regex":
    row         (str)               Regex with ONE capture group for each row
    cell        (str)               Regex with ONE capture group for each cell
    first_row   (str)               "headers" (row 0 = column names) or "sizes" (row 0 = size labels)

  For parse="json":
    json_headers (int or list)      Capture group number(s) containing the headers JSON array
    json_rows    (int or list)      Capture group number(s) containing the rows JSON array

  cell_key      (str, optional)     If cells are objects like {"in":"32","cm":"82"}, extract this key
  value_format  (str)               "plain", "slash_cm" (30/76.2 → 76.2), "slash_inches" (76.2/30 → 76.2)
  unit          (str)               Unit label for output (default: "cm")

HOW TO ADD A NEW STORE:
  1. Open a product page in Chrome → Ctrl+U → copy the HTML source
  2. Give the HTML to ChatGPT/Claude and ask it to create a recipe using the fields above
  3. Paste the recipe below OR send it as an inline recipe via the API
  4. Test: curl -X POST http://localhost:8000/scrape -d '{"url": "..."}'
"""

RECIPES = {

    # ── Sheetal Batra ──────────────────────────────────────────────────
    # HTML lists. First list = size labels, rest = measurements.
    # Values: "30/76.2" (inches/cm) → take cm part.
    "sheetalbatra.com": {
        "name": "Sheetal Batra",
        "container": r'<ul class="main-chrt"[^>]*>(.*?)</ul>\s*</li>\s*</ul>',
        "row": r'<ul[^>]*class="main-size[^"]*"[^>]*>(.*?)</ul>',
        "cell": r'<li>(.*?)</li>',
        "value_format": "slash_cm",
        "first_row": "sizes",
    },

    # ── Almost Gods ────────────────────────────────────────────────────
    # Jotly size chart app — JSON embedded in HTML.
    # Two container patterns because the order of rows/headers varies.
    "almostgods.com": {
        "name": "Almost Gods",
        "container": [
            r'"rows":\s*(\[\[.*?\]\])\s*,\s*"headers":\s*(\[[^\]]+\])',
            r'"headers":\s*(\[[^\]]+\])\s*,.*?"rows":\s*(\[\[.*?\]\])',
        ],
        "parse": "json",
        "json_rows": [1, 2],
        "json_headers": [2, 1],
        "value_format": "plain",
    },

    # ── Genes Lecoanet Hemant ────────────────────────────────────────
    # Jotly size chart app — same format as Almost Gods.
    # Values are in inches (plain numbers).
    "geneslecoanethemant.com": {
        "name": "Genes Lecoanet Hemant",
        "container": [
            r'"rows":\s*(\[\[.*?\]\])\s*,\s*"headers":\s*(\[[^\]]+\])',
            r'"headers":\s*(\[[^\]]+\])\s*,.*?"rows":\s*(\[\[.*?\]\])',
        ],
        "parse": "json",
        "json_rows": [1, 2],
        "json_headers": [2, 1],
        "value_format": "plain",
        "unit": "inches",
    },

    # ── Tuck Demo (Shopify) ───────────────────────────────────────────
    # Three heading variants ("Size Chart" / "Lower Body Garment Chart" /
    # "Full Body Chart") followed by a plain <table>. Values are inch ranges.
    "tuckdemo.myshopify.com": {
        "name": "Tuck Demo",
        "container": r'<h2[^>]*class="page-title"[^>]*>[^<]*Chart[^<]*</h2>.*?<table>(.*?)</table>',
        "row": r"<tr>(.*?)</tr>",
        "cell": r"<t[dh][^>]*>(.*?)</t[dh]>",
        "parse": "regex",
        "first_row": "headers",
        "value_format": "plain",
        "unit": "inches",
    },

    # ── FableStreet ───────────────────────────────────────────────────
    # Next.js embedded JSON with escaped quotes. Cells are objects with in/cm keys.
    "fablestreet.com": {
        "name": "FableStreet",
        "container": r'\\"headers\\":\s*(\[[^\]]+\])\s*,\s*\\"rows\\":\s*(\[(?:\{.*?\}(?:,\s*)?)*\])',
        "unescape": True,
        "parse": "json",
        "json_headers": 1,
        "json_rows": 2,
        "cell_key": "cm",
        "value_format": "plain",
        "unit": "cm",
    },

}
