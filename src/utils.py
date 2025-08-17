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
    text = text.strip()
    import re as _re
    mcur = _re.match(r'([£$]|USD|EUR|GBP)?\s*(.*)', text)
    currency = None
    number = text
    if mcur:
        currency = mcur.group(1)
        number = mcur.group(2) if mcur.group(2) else number
    clean = _re.sub(r'[^0-9.,]', '', number)
    if clean.count(',') > 0 and clean.count('.') > 0:
        if clean.rfind(',') > clean.rfind('.'):
            clean = clean.replace('.', '')
            clean = clean.replace(',', '.')
        else:
            clean = clean.replace(',', '')
    else:
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

def with_affiliate(url: str) -> str:
    tag = (config.affiliate_tag or "").strip()
    if not tag:
        return url
    try:
        u = urlparse(url)
        qs = dict(parse_qsl(u.query, keep_blank_values=True))
        # Amazon affiliate tag key is usually 'tag'
        qs["tag"] = tag
        new_query = urlencode(qs)
        return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
    except Exception:
        return url

# --- New helpers for Amazon App shared links / short links ---
SHORT_AMAZON_DOMAINS = {"amzn.to", "amzn.eu", "amzn.in", "amzn.asia", "a.co"}

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
    headers = {"User-Agent": config.user_agent, "Accept-Language": "en-US,en;q=0.9"}
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as client:
            # First try HEAD to reduce bandwidth
            try:
                head_resp = await client.head(url)
                if head_resp.is_redirect:
                    return str(head_resp.next_request.url) if head_resp.next_request else str(head_resp.url)
            except Exception:
                pass
            # Fallback to GET
            resp = await client.get(url)
            return str(resp.url)
    except Exception:
        return url

async def resolve_and_normalize_amazon_url(url: str) -> str:
    """Expand short (amzn.*) links then normalize to /dp/ASIN form if possible."""
    expanded = await expand_short_amazon_url(url)
    return normalize_amazon_url(expanded)

