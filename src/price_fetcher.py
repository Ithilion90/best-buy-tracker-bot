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
    # Priority order: prefer actual Amazon price over coupon/deal prices
    # 1. Try main price block (excludes coupon badges)
    for sel in [
        "#corePrice_feature_div .a-price[data-a-color='price'] span.a-offscreen",
        "#corePrice_feature_div .a-price.a-text-price span.a-offscreen",
        "#apex_desktop .a-price[data-a-color='price'] span.a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#priceblock_saleprice",
    ]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            price_text = el.get_text(strip=True)
            break
    
    # 2. Fallback: any offscreen price (may include coupons)
    if not price_text:
        offscreen_prices = soup.select("span.a-offscreen")
        for el in offscreen_prices:
            text = el.get_text(strip=True)
            # Skip if parent has coupon/badge indicators
            parent = el.parent
            if parent:
                parent_class = ' '.join(parent.get('class', []))
                # Skip coupon badges and promotional elements
                if any(x in parent_class.lower() for x in ['coupon', 'badge', 'promotion', 'promo']):
                    continue
            if text:
                price_text = text
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

def extract_all_prices_debug(html: str) -> dict:
    """Extract all prices found on page for debugging purposes.
    Returns dict with all prices and which one was selected."""
    soup = BeautifulSoup(html, "html.parser")
    
    debug_info = {
        'all_offscreen': [],
        'primary_selectors': {},
        'selected_price': None,
        'selected_source': None
    }
    
    # Collect all offscreen prices
    for el in soup.select("span.a-offscreen"):
        text = el.get_text(strip=True)
        parent = el.parent
        parent_class = ' '.join(parent.get('class', [])) if parent else ''
        is_coupon = any(x in parent_class.lower() for x in ['coupon', 'badge', 'promotion', 'promo'])
        debug_info['all_offscreen'].append({
            'text': text,
            'parent_class': parent_class,
            'is_coupon': is_coupon
        })
    
    # Try primary selectors
    primary_sels = [
        ("#corePrice_feature_div .a-price[data-a-color='price'] span.a-offscreen", "corePrice main"),
        ("#corePrice_feature_div .a-price.a-text-price span.a-offscreen", "corePrice text"),
        ("#apex_desktop .a-price[data-a-color='price'] span.a-offscreen", "apex desktop"),
        ("#priceblock_ourprice", "priceblock_ourprice"),
        ("#priceblock_dealprice", "priceblock_dealprice"),
        ("#priceblock_saleprice", "priceblock_saleprice"),
    ]
    
    for sel, name in primary_sels:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            debug_info['primary_selectors'][name] = text
            if not debug_info['selected_price']:
                debug_info['selected_price'] = text
                debug_info['selected_source'] = name
    
    # If no primary selector worked, use fallback
    if not debug_info['selected_price']:
        for item in debug_info['all_offscreen']:
            if not item['is_coupon'] and item['text']:
                debug_info['selected_price'] = item['text']
                debug_info['selected_source'] = 'fallback_offscreen'
                break
    
    return debug_info

def extract_availability(html: str) -> Optional[str]:
    """Availability detection prioritizing Amazon DOM over page-wide text.
    Returns: 'in_stock' | 'unavailable' | 'preorder' | 'unknown'.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        # Check availability block first
        avail_el = soup.select_one('#availability, span#availability, div#availability span')
        if avail_el:
            ab_text = avail_el.get_text(" ", strip=True).lower()
            if any(x in ab_text for x in [
                "currently unavailable", "temporarily out of stock", "out of stock",
                "non disponibile", "momentaneamente non disponibile", "attualmente non disponibile",
                "actuellement indisponible", "article indisponible",
                "derzeit nicht verfügbar", "derzeit nicht auf lager",
                "agotado", "no disponible", "在庫切れ"
            ]):
                return "unavailable"
            if any(x in ab_text for x in [
                "pre-order", "preorder", "pre-ordine", "précommande", "vorbestellen", "preventa"
            ]):
                return "preorder"
            if any(x in ab_text for x in [
                "in stock", "disponibile", "en stock", "auf lager", "disponible"
            ]):
                return "in_stock"

        # Check buttons presence and disabled state
        add_btn = soup.select_one('#add-to-cart-button, input#add-to-cart-button')
        buy_btn = soup.select_one('#buy-now-button, input#buy-now-button')
        def _is_enabled(btn):
            if not btn:
                return False
            if btn.has_attr('disabled'):
                return False
            parent = btn.parent
            # disabled style on wrapper
            if parent and 'a-button-disabled' in (parent.get('class') or []):
                return False
            return True
        if _is_enabled(add_btn) or _is_enabled(buy_btn):
            return "in_stock"

        # Fallback: page text explicit OOS
        text = soup.get_text(" ", strip=True).lower()
        if any(x in text for x in [
            "currently unavailable", "temporarily out of stock", "out of stock",
            "non disponibile", "momentaneamente non disponibile", "attualmente non disponibile",
            "actuellement indisponible", "article indisponible",
            "derzeit nicht verfügbar", "derzeit nicht auf lager",
            "agotado", "no disponible", "在庫切れ"
        ]):
            return "unavailable"
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

async def fetch_price_debug(url: str):
    """Return debug info about all prices found on the page."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        html = await fetch_html(client, url)
        if not html:
            return None
        return extract_all_prices_debug(html)

async def get_scraped_current_price(url: str, asin: str):
    """Return (title, price, currency) scraping live (no cache)."""
    title, price, currency, _img = await fetch_price_title_image(url)
    return title, price, currency
