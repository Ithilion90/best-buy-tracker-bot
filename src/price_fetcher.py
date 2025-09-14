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

BASE_LANG_PREF = "en-US,en;q=0.9"
DOMAIN_LANG_MAP = {
    'amazon.it': 'it-IT,it;q=0.9',
    'amazon.fr': 'fr-FR,fr;q=0.9',
    'amazon.de': 'de-DE,de;q=0.9',
    'amazon.es': 'es-ES,es;q=0.9',
    'amazon.co.uk': 'en-GB,en;q=0.9',
    'amazon.com': 'en-US,en;q=0.9',
    'amazon.ca': 'en-CA,en;q=0.9',
    'amazon.com.mx': 'es-MX,es;q=0.9',
    'amazon.co.jp': 'ja-JP,ja;q=0.9',
}

def _build_headers(url: str) -> dict:
    import re as _re
    m = _re.match(r'https?://([^/]+)/', url)
    host = m.group(1).lower() if m else ''
    host = host.replace('www.', '')
    lang = DOMAIN_LANG_MAP.get(host, BASE_LANG_PREF)
    return {
        "User-Agent": config.user_agent,
        "Accept-Language": f"{lang},{BASE_LANG_PREF}",
    }

# Always scrape live (may increase requests, rely on circuit breaker to throttle).

@retry_with_backoff(max_retries=3, exceptions=(httpx.RequestError, httpx.HTTPStatusError))
async def fetch_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        # Check circuit breaker state before making request
        if circuit_breakers['amazon_scraping'].state == 'open':
            logger.warning("Circuit breaker open for Amazon scraping")
            return None
        headers = _build_headers(url)
        resp = await client.get(url, headers=headers, timeout=config.request_timeout_seconds)

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

def extract_title_price_image(html: str):
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
    image_url: Optional[str] = None
    if not price_text:
        # Attempt to build from whole + fraction parts (common in some locales)
        whole = soup.select_one('span.a-price-whole')
        frac = soup.select_one('span.a-price-fraction')
        if whole and whole.get_text(strip=True):
            combined = whole.get_text(strip=True)
            if frac and frac.get_text(strip=True):
                combined += "." + frac.get_text(strip=True)
            price_text = combined
    if price_text:
        price, currency = parse_price_text(price_text)

    # Image selectors (try high-res first, then fallback)
    img_selectors = [
        '#landingImage',
        '#imgTagWrapperId img',
        'img#imgBlkFront',
        'img[data-old-hires]',
        'div#main-image-container img',
    ]
    for sel in img_selectors:
        el = soup.select_one(sel)
        if not el:
            continue
        cand = el.get('data-old-hires') or el.get('data-a-dynamic-image') or el.get('src')
        if not cand:
            continue
        # data-a-dynamic-image is a JSON-like string {"url1":[w,h],...}
        if '"' in cand and '{' in cand:
            import json, re as _re
            try:
                # Normalize quotes if needed
                json_text = cand if cand.strip().startswith('{') else '{' + cand.split('{',1)[1]
                mapping = json.loads(json_text)
                if isinstance(mapping, dict):
                    # pick largest width image
                    best = None
                    best_w = -1
                    for k,v in mapping.items():
                        if isinstance(v, (list, tuple)) and len(v)>=2 and isinstance(v[0], (int,float)):
                            if v[0] > best_w:
                                best = k
                                best_w = v[0]
                    if best:
                        image_url = best
                        break
            except Exception:
                pass
        else:
            image_url = cand
            break

    return title, price, currency, image_url

def extract_availability(html: str) -> Optional[str]:
    """Very simple availability detector across major locales.
    Returns one of: 'in_stock', 'unavailable', 'preorder', 'unknown'.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True).lower()
        # Common OOS strings in various locales
        oos_markers = [
            "currently unavailable",  # en
            "temporarily out of stock",  # en
            "out of stock",  # en
            "non disponibile",  # it
            "momentaneamente non disponibile",  # it
            "attualmente non disponibile",  # it
            "actuellement indisponible",  # fr
            "article indisponible",  # fr
            "derzeit nicht verfügbar",  # de
            "derzeit nicht auf lager",  # de
            "agotado temporalmente",  # es
            "no disponible",  # es
            "在庫切れ",  # jp
        ]
        preorder_markers = [
            "pre-order", "preorder", "pre-ordine", "précommande", "vorbestellen", "preventa"
        ]
        # If "Add to Cart" exists it's likely in stock
        in_stock_markers = [
            "add to cart", "aggiungi al carrello", "ajouter au panier", "in den einkaufswagen", "añadir a la cesta"
        ]
        if any(m in text for m in oos_markers):
            return "unavailable"
        if any(m in text for m in preorder_markers):
            return "preorder"
        if any(m in text for m in in_stock_markers):
            return "in_stock"
        return "unknown"
    except Exception:
        return None

async def fetch_price_title_image(url: str):
    async with httpx.AsyncClient(follow_redirects=True) as client:
        html = await fetch_html(client, url)
        if not html:
            return None, None, None, None
        return extract_title_price_image(html)

async def fetch_price_title_image_and_availability(url: str):
    """Return (title, price, currency, image_url, availability)."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        html = await fetch_html(client, url)
        if not html:
            return None, None, None, None, None
        title, price, currency, image = extract_title_price_image(html)
        availability = extract_availability(html)
        return title, price, currency, image, availability

async def get_scraped_current_price(url: str, asin: str):
    """Return (title, price, currency) scraping live (no cache)."""
    title, price, currency, _img = await fetch_price_title_image(url)
    return title, price, currency
