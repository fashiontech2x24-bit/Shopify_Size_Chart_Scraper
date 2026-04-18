"""
Size Chart Scraper — Production Microservice.

Run:  uvicorn app:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from scraper import scrape_url, detect_store
from scraper.config import MAX_PARALLEL
from scraper.helpers import launch_browser

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("scraper-service")

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
SCRAPE_TIMEOUT = int(os.environ.get("SCRAPE_TIMEOUT", "60"))
API_KEY = os.environ.get("API_KEY")  # if set, required via X-API-Key header
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

# ---------------------------------------------------------------------------
# Browser pool — single Chromium instance reused across all requests.
# Semaphore is created at module load so it is never None at request time.
# ---------------------------------------------------------------------------
_browser = None
_pw = None
_start_time: float = 0
_semaphore: asyncio.Semaphore = asyncio.Semaphore(MAX_PARALLEL)
_restart_lock: asyncio.Lock = asyncio.Lock()


async def _start_browser():
    global _browser, _pw, _start_time
    _pw, _browser = await launch_browser()
    _start_time = time.time()
    log.info("Browser started (max %d parallel scrapes)", MAX_PARALLEL)


async def _stop_browser():
    global _browser, _pw
    if _browser:
        try:
            await _browser.close()
        except Exception as e:
            log.warning("Error closing browser: %s", e)
        _browser = None
    if _pw:
        try:
            await _pw.stop()
        except Exception as e:
            log.warning("Error stopping playwright: %s", e)
        _pw = None
    log.info("Browser stopped")


async def _get_browser():
    """Return the shared browser, restarting if it crashed.

    Guarded by a lock so concurrent callers don't stampede a restart.
    """
    global _browser
    if _browser is not None and _browser.is_connected():
        return _browser

    async with _restart_lock:
        # Re-check after acquiring the lock — another task may have restarted.
        if _browser is None or not _browser.is_connected():
            log.warning("Browser not connected — restarting...")
            await _stop_browser()
            await _start_browser()
    return _browser


def _is_ready() -> bool:
    return _browser is not None and _browser.is_connected()


# ---------------------------------------------------------------------------
# FastAPI lifespan — start/stop browser with the server
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await _start_browser()
    yield
    await _stop_browser()


app = FastAPI(
    title="Size Chart Scraper",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _require_api_key(x_api_key: str | None) -> None:
    """If API_KEY env var is set, require a matching X-API-Key header."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ScrapeRequest(BaseModel):
    url: str
    recipe: dict | None = None
    skip_browser: bool = False
    store_name: str | None = None
    storefront_password: str | None = None  # Shopify preview-store password

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Invalid URL — must start with http:// or https://")
        return v


class ScrapeResult(BaseModel):
    success: bool
    url: str
    store: str
    product: str | None = None
    unit: str | None = None
    columns: list[str] | None = None
    data: list[dict] | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    browser: str
    uptime_seconds: int
    max_parallel: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    ready = _is_ready()
    return HealthResponse(
        status="ok" if ready else "degraded",
        browser="running" if ready else "down",
        uptime_seconds=int(time.time() - _start_time) if _start_time else 0,
        max_parallel=MAX_PARALLEL,
    )


@app.post("/scrape", response_model=ScrapeResult)
async def scrape(req: ScrapeRequest, x_api_key: str | None = Header(default=None)):
    _require_api_key(x_api_key)

    store = req.store_name or detect_store(req.url)

    # Acquire the concurrency slot FIRST, then get the browser. This ensures
    # browser restarts are serialized under the global limit rather than
    # stampeding when many requests arrive during a crash.
    async with _semaphore:
        try:
            browser = await _get_browser()
        except Exception as e:
            log.exception("Failed to start browser")
            raise HTTPException(status_code=503, detail=f"Browser unavailable: {e}")

        try:
            df = await asyncio.wait_for(
                scrape_url(
                    req.url,
                    browser=browser,
                    recipe=req.recipe,
                    skip_browser=req.skip_browser,
                    storefront_password=req.storefront_password,
                ),
                timeout=SCRAPE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log.error("Scrape timed out after %ds: %s", SCRAPE_TIMEOUT, req.url)
            return ScrapeResult(
                success=False,
                url=req.url,
                store=store,
                error=f"Scrape timed out after {SCRAPE_TIMEOUT}s",
            )
        except Exception as e:
            log.exception("Scrape failed: %s", req.url)
            return ScrapeResult(
                success=False,
                url=req.url,
                store=store,
                error=str(e),
            )

    if df.empty:
        return ScrapeResult(
            success=False,
            url=req.url,
            store=store,
            error="No size chart data found",
        )

    df = df.fillna("")
    records = df.to_dict(orient="records")

    product = records[0].get("Product", "") if records else ""
    if not product or len(product) > 300:
        if product:
            log.warning("Product field looks malformed (len=%d); falling back to URL slug", len(product))
        if "/products/" in req.url:
            product = req.url.split("/products/")[-1].split("?")[0].replace("-", " ").title()
        else:
            product = req.url.rstrip("/").split("/")[-1].replace("-", " ").title()

    unit = records[0].get("Unit", "cm") if records else "cm"

    return ScrapeResult(
        success=True,
        url=req.url,
        store=store,
        product=product,
        unit=unit,
        columns=list(df.columns),
        data=records,
    )
