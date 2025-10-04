import re
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
import asyncio
import httpx
try:
    from .config import config
except ImportError:  # fallback when run directly
    from config import config

ASIN_RE = re.compile(r'/([A-Z0-9]{10})(?:[/?]|$)')

def extract_asin(url: str) -> Optional[str]:
    m = ASIN_RE.search(url)
    return m.group(1) if m else None

def normalize_amazon_url(url: str) -> str:
    asin = extract_asin(url)
    if not asin:
        return url
    import re as _re
    m = _re.match(r'(https?://[^/]+)/', url)
    if not m:
        return url
    domain = m.group(1)
    return f"{domain}/dp/{asin}"

def parse_price_text(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Parse a localized Amazon price string into (float, currency).
    Handles formats like:
      12,34 €  |  €12,34  |  1.234,56 €  |  1 234,56 €  |  $12.34  |  12,34 EUR
    """
    raw = text.strip()
    import re as _re
    # Normalize non‑breaking spaces
    raw = raw.replace('\u202f', ' ').replace('\xa0', ' ')
    # Extract currency symbol (leading or trailing)
    currency = None
    cur_match = _re.search(r'(USD|EUR|GBP|CHF|CAD|AUD|£|€|\$)', raw)
    if cur_match:
        sym = cur_match.group(1)
        # Map symbols to ISO if possible
        symbol_map = {'£': 'GBP', '€': 'EUR', '$': 'USD'}
        currency = symbol_map.get(sym, sym)
    # Remove currency words/symbols to isolate number
    number_part = _re.sub(r'(USD|EUR|GBP|CHF|CAD|AUD|£|€|\$)', '', raw, flags=_re.IGNORECASE)
    # Remove words like TTC, IVA, taxes, etc.
    number_part = _re.sub(r'(?i)(ttc|iva|tax(es)?|incl\.?|compr\.?|sped\.?|gratuit)', '', number_part)
    # Remove spaces (thousand separators) but keep separators . or ,
    number_part = _re.sub(r'\s+', '', number_part)
    # Keep only digits and separators
    clean = _re.sub(r'[^0-9.,]', '', number_part)
    # Heuristic: if both separators present decide decimal
    if clean.count(',') > 0 and clean.count('.') > 0:
        # Last occurring separator is decimal
        if clean.rfind(',') > clean.rfind('.'):
            # comma decimal => remove dots (thousands) then replace comma with dot
            clean = clean.replace('.', '').replace(',', '.')
        else:
            # dot decimal => remove commas
            clean = clean.replace(',', '')
    else:
        # Only one type or none
        if clean.count(',') == 1 and len(clean.split(',')[-1]) in (2, 3):
            clean = clean.replace(',', '.')
        else:
            clean = clean.replace(',', '')
    try:
        return float(clean), currency
    except Exception:
        return None, currency

def truncate(text: str, max_len: int = 60) -> str:
    return text if len(text) <= max_len else (text[: max_len - 1] + "…")

def with_affiliate(url: str, use_offer_listing: bool = False) -> str:
    """Add affiliate tag to URL.
    
    Args:
        url: Amazon product URL
        use_offer_listing: Deprecated (Amazon redirects these anyway)
    """
    tag = (config.affiliate_tag or "").strip()
    
    try:
        u = urlparse(url)
        
        # Add affiliate tag and helpful parameters
        if tag:
            qs = dict(parse_qsl(u.query, keep_blank_values=True))
            qs["tag"] = tag
            new_query = urlencode(qs)
            return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
        else:
            return url
    except Exception:
        return url

def build_product_url(domain: str, asin: str, title: str | None = None) -> str:
    """Build Amazon product URL with affiliate tag.
    
    Args:
        domain: Amazon domain (e.g., 'amazon.it', 'amazon.com')
        asin: Product ASIN
        title: Optional product title for SEO-friendly URL (helps Amazon routing)
    
    Returns:
        URL to product page with affiliate tag and ref parameter
    """
    # Build URL with optional title in path (Amazon's preferred format)
    if title:
        # Create URL-safe slug from title
        import re
        slug = re.sub(r'[^\w\s-]', '', title.lower())  # Remove special chars
        slug = re.sub(r'[\s_]+', '-', slug)  # Replace spaces with hyphens
        slug = slug[:80]  # Limit length
        base_url = f"https://{domain}/{slug}/dp/{asin}"
    else:
        base_url = f"https://{domain}/dp/{asin}"
    
    # Add affiliate tag via with_affiliate
    url_with_tag = with_affiliate(base_url)
    
    # Add ref parameter to help Amazon identify the source (reduces routing issues)
    try:
        u = urlparse(url_with_tag)
        qs = dict(parse_qsl(u.query, keep_blank_values=True))
        # Add ref parameter if not already present
        if 'ref' not in qs:
            qs['ref'] = 'nosim'  # "no similar items" - cleaner product page
        new_query = urlencode(qs)
        return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
    except Exception:
        return url_with_tag

# --- New helpers for Amazon App shared links / short links ---
SHORT_AMAZON_DOMAINS = {"amzn.to", "amzn.eu", "amzn.in", "amzn.asia", "a.co"}

# ---------------- Currency helpers -----------------

_CURRENCY_SYMBOLS = {
    'EUR': '€',
    'USD': '$',
    'GBP': '£',
    'JPY': '¥',
    'CAD': 'CA$',
    'AUD': 'A$',
    'MXN': 'MX$',
    'INR': '₹',
}

_DOMAIN_CURRENCY = {
    'amazon.it': 'EUR', 'amazon.de': 'EUR', 'amazon.fr': 'EUR', 'amazon.es': 'EUR', 'amazon.co.uk': 'GBP',
    'amazon.com': 'USD', 'amazon.ca': 'CAD', 'amazon.com.mx': 'MXN', 'amazon.co.jp': 'JPY', 'amazon.in': 'INR'
}

def domain_to_currency(domain: str | None) -> str:
    if not domain:
        return 'EUR'
    d = domain.lower()
    return _DOMAIN_CURRENCY.get(d, 'EUR')

def currency_symbol(code: str | None) -> str:
    if not code:
        return '€'
    return _CURRENCY_SYMBOLS.get(code.upper(), code.upper())

def format_price(amount: float | None, currency: str | None) -> str:
    if amount is None:
        return 'N/A'
    code = (currency or 'EUR').upper()
    sym = currency_symbol(code)
    # If symbol already contains code (like CA$) just prepend, else typical symbol before.
    if sym.endswith('$') and len(sym) > 1 and not sym.startswith('$'):
        # e.g., CA$ 12.34
        return f"{sym}{amount:.2f}"
    if sym in ('$','€','£','¥','₹'):
        return f"{sym}{amount:.2f}"
    # Fallback: amount + space + code
    return f"{amount:.2f} {code}"

def is_short_amazon(url: str) -> bool:
    try:
        netloc = urlparse(url).netloc.lower()
        # Strip leading www.
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc in SHORT_AMAZON_DOMAINS
    except Exception:
        return False

async def expand_short_amazon_url(url: str, timeout: int = 10) -> str:
    """Follow redirects for amzn.* short links to reach canonical /dp/ URL.
    Returns original url on failure.
    """
    if not is_short_amazon(url):
        return url
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers={"User-Agent": config.user_agent}) as client:
            resp = await client.get(url)
            return str(resp.url)
    except Exception:
        return url

async def resolve_and_normalize_amazon_url(url: str) -> str:
    """Expand short (amzn.*) links then normalize to /dp/ASIN form if possible."""
    expanded = await expand_short_amazon_url(url)
    return normalize_amazon_url(expanded)

