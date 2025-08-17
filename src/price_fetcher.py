from typing import Optional, Tuple, Dict, Any
import httpx
from bs4 import BeautifulSoup
try:
    from .config import config
    from .utils import parse_price_text
    from .logger import logger
    from .resilience import retry_with_backoff, circuit_breakers
except ImportError:  # fallback when run directly
    from config import config
    from utils import parse_price_text
    from logger import logger
    from resilience import retry_with_backoff, circuit_breakers

HEADERS = {
    "User-Agent": config.user_agent,
    "Accept-Language": "en-US,en;q=0.9",
}

# In-memory cache for current prices scraped from Amazon (per ASIN)
_CURRENT_PRICE_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 900  # 15 minutes

def _now_seconds() -> float:
    import time
    return time.time()

def get_cached_current_price(asin: str) -> Optional[float]:
    entry = _CURRENT_PRICE_CACHE.get(asin)
    if not entry:
        return None
    if (_now_seconds() - entry['ts']) > CACHE_TTL_SECONDS:
        return None
    return entry.get('price')

def set_cached_current_price(asin: str, price: Optional[float], title: Optional[str] = None, currency: Optional[str] = None) -> None:
    if price is None:
        return
    _CURRENT_PRICE_CACHE[asin] = {
        'price': price,
        'title': title,
        'currency': currency,
        'ts': _now_seconds()
    }

@retry_with_backoff(max_retries=3, exceptions=(httpx.RequestError, httpx.HTTPStatusError))
async def fetch_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        # Check circuit breaker state before making request
        if circuit_breakers['amazon_scraping'].state == 'open':
            logger.warning("Circuit breaker open for Amazon scraping")
            return None
            
        resp = await client.get(url, headers=HEADERS, timeout=config.request_timeout_seconds)
        
        if resp.status_code == 200:
            # Record success via internal method
            circuit_breakers['amazon_scraping']._on_success()
            logger.info("Successfully fetched page", url=url[:50], status=resp.status_code)
            return resp.text
        else:
            # Record failure via internal method
            circuit_breakers['amazon_scraping']._on_failure()
            logger.warning("Failed to fetch page", url=url[:50], status=resp.status_code)
            return None
    except Exception as e:
        # Record failure via internal method
        circuit_breakers['amazon_scraping']._on_failure()
        logger.error("Error fetching page", url=url[:50], error=str(e))
        return None

def extract_title_and_price(html: str):
    soup = BeautifulSoup(html, "html.parser")

    title = None
    for sel in ["#productTitle", "span#productTitle", "h1#title", "h1 span#productTitle"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(strip=True)
            break

    price_text = None
    for sel in [
        "span.a-offscreen",
        "#corePrice_feature_div span.a-price span.a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#priceblock_saleprice",
    ]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            price_text = el.get_text(strip=True)
            break

    price = None
    currency = None
    if price_text:
        price, currency = parse_price_text(price_text)

    return title, price, currency

async def fetch_price_and_title(url: str):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        html = await fetch_html(client, url)
        if not html:
            return None, None, None
        return extract_title_and_price(html)

async def get_scraped_current_price(url: str, asin: str):
    """Return (title, price, currency) for ASIN using cache; scrape if stale/missing."""
    cached = get_cached_current_price(asin)
    if cached is not None:
        # We don't store title/currency reliably in cache; we may return None for them
        return None, cached, None
    title, price, currency = await fetch_price_and_title(url)
    if price is not None:
        set_cached_current_price(asin, price, title, currency)
    return title, price, currency
