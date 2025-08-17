from typing import Dict, Tuple, Optional, List
import math
import keepa  # type: ignore
try:
    from .config import config
    from .logger import logger
    from .resilience import retry_with_backoff, circuit_breakers
    from .cache import keepa_cache
except ImportError:
    from config import config
    from logger import logger
    from resilience import retry_with_backoff, circuit_breakers
    from cache import keepa_cache

DomainMap = {
    "com": 1,
    "co.uk": 2,
    "de": 3,
    "fr": 4,
    "co.jp": 5,
    "ca": 6,
    "it": 8,
    "es": 9,
    "in": 10,
    "com.mx": 11,
}

def get_keepa_domain_id() -> int:
    dom = (getattr(config, "keepa_domain", "com") or "com").lower()
    return DomainMap.get(dom, 1)

def get_keepa_domain_name() -> str:
    """Return Keepa domain name expected by the 'keepa' package (e.g., US, UK, DE, IT)."""
    mapping = {
        "com": "US",
        "co.uk": "UK",
        "de": "DE",
        "fr": "FR",
        "co.jp": "JP",
        "ca": "CA",
        "it": "IT",
        "es": "ES",
        "in": "IN",
        "com.mx": "MX",
    }
    dom = (getattr(config, "keepa_domain", "com") or "com").lower()
    return mapping.get(dom, "US")

@retry_with_backoff(max_retries=3, exceptions=(Exception,))
def fetch_lifetime_min_max_current(asin_list: List[str]) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    """Return {asin: (min, max, current)} lifetime prices (Amazon price) in same currency.
    Uses a 30 minute cache (1800s) to reduce API quota usage while keeping data reasonably fresh.
    On error returns empty mapping or (None, None, None) entries so the caller can fallback.
    """
    key = (getattr(config, "keepa_api_key", "") or "").strip()
    if not key or not asin_list:
        return {}

    # Check cache first (10 min TTL enforced when setting)
    cached = keepa_cache.get_lifetime_minmax_current(asin_list)
    if cached is not None:
        logger.info("Using cached Keepa current/min/max data", asins=len(asin_list))
        return cached

    logger.info("Fetching Keepa data with current prices (cache miss)", asins=len(asin_list))

    try:
        # Primary: keepa package
        result = circuit_breakers['keepa_api'].call(_fetch_from_keepa_package_with_current, key, asin_list)
        if result:
            keepa_cache.set_lifetime_minmax_current(asin_list, result, ttl=1800)  # 30 minutes
            logger.info("Keepa current/min/max data fetched and cached", asins=len(asin_list), results=len(result), ttl_seconds=1800)
        return result
    except ImportError:
        # Fallback: pykeepa
        try:
            result = _fetch_from_pykeepa_with_current(key, asin_list)
            if result:
                keepa_cache.set_lifetime_minmax_current(asin_list, result, ttl=1800)
            return result
        except ImportError:
            # Final fallback: raw HTTP
            try:
                result = circuit_breakers['keepa_api'].call(_fetch_via_http_with_current, asin_list, key)
                if result:
                    keepa_cache.set_lifetime_minmax_current(asin_list, result, ttl=1800)
                return result
            except Exception as e:
                logger.error("All Keepa methods failed", error=str(e))
                return {asin: (None, None, None) for asin in asin_list}
    except Exception as e:
        logger.error("Keepa API failed", error=str(e), asins=len(asin_list))
        return {asin: (None, None, None) for asin in asin_list}

@retry_with_backoff(max_retries=3, exceptions=(Exception,))
def fetch_lifetime_min_max(asin_list: List[str]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Return {asin: (min, max)} lifetime (price type: Amazon price) in same currency.
    Requires KEEPA_API_KEY in config; on error returns {} or missing keys.
    If Keepa doesn't have historical data, returns (None, None) so caller can use DB fallback.
    Uses caching and circuit breaker for resilience.
    """
    key = (getattr(config, "keepa_api_key", "") or "").strip()
    if not key or not asin_list:
        return {}
    
    # Check cache first
    cached_result = keepa_cache.get_lifetime_minmax(asin_list)
    if cached_result is not None:
        logger.info("Using cached Keepa data", asins=len(asin_list))
        return cached_result
    
    try:
        # Try with 'keepa' package first using circuit breaker
        result = circuit_breakers['keepa_api'].call(_fetch_from_keepa_package, key, asin_list)
        
        # Cache successful result
        if result:
            keepa_cache.set_lifetime_minmax(asin_list, result)
            logger.info("Keepa data fetched and cached", asins=len(asin_list), results=len(result))
        
        return result
    
    except ImportError:
        # Fallback: try pykeepa
        try:
            result = _fetch_from_pykeepa(key, asin_list)
            if result:
                keepa_cache.set_lifetime_minmax(asin_list, result)
            return result
        except ImportError:
            # Final fallback: HTTP API
            try:
                result = circuit_breakers['keepa_api'].call(_fetch_via_http, asin_list, key)
                if result:
                    keepa_cache.set_lifetime_minmax(asin_list, result)
                return result
            except Exception as e:
                logger.error("All Keepa methods failed", error=str(e))
                return {asin: (None, None) for asin in asin_list}
    except Exception as e:
        logger.error("Keepa API failed", error=str(e), asins=len(asin_list))
        return {asin: (None, None) for asin in asin_list}

def _fetch_from_keepa_package_with_current(key: str, asin_list: List[str]) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    """Fetch from keepa package with current prices"""
    api = keepa.Keepa(key)
    products_resp = api.query(
        asin_list, 
        domain=get_keepa_domain_name(), 
        stats=1800,
        history=False
    )
    products = _normalize_products(products_resp)
    return _parse_keepa_products_with_current(products)

def _fetch_from_pykeepa_with_current(key: str, asin_list: List[str]) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    """Fetch from pykeepa with current prices"""
    import pykeepa  # type: ignore
    try:
        products_resp = pykeepa.query(
            key,
            asin_list,
            stats=1800,
            domain=get_keepa_domain_id(),
            history=True,
        )
    except Exception:
        products_resp = []
    products = _normalize_products(products_resp)
    return _parse_keepa_products_with_current(products)

def _fetch_from_keepa_package(key: str, asin_list: List[str]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Fetch from keepa package"""
    api = keepa.Keepa(key)
    products_resp = api.query(
        asin_list, 
        domain=get_keepa_domain_name(), 
        stats=1800,
        history=False
    )
    products = _normalize_products(products_resp)
    return _parse_keepa_products(products)

def _fetch_from_pykeepa(key: str, asin_list: List[str]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Fetch from pykeepa"""
    import pykeepa  # type: ignore
    try:
        products_resp = pykeepa.query(
            key,
            asin_list,
            stats=1800,
            domain=get_keepa_domain_id(),
            history=True,
        )
    except Exception:
        products_resp = []
    products = _normalize_products(products_resp)
    return _parse_keepa_products(products)


def _pick_amazon_stat(stats: dict, key: str) -> Optional[float]:
    """Return the Amazon stat value (in cents) from a Keepa stats dict for the given key.
    Handles shapes: scalar, list/tuple (index 0 assumed Amazon), or dict with common labels.
    """
    val = stats.get(key)
    if val is None:
        return None
    # List/tuple form: prefer index 0 (Amazon), then fall back to the first valid entry
    if isinstance(val, (list, tuple)):
        # Some Keepa shapes are list-of-pairs: [[price, when], None, ...].
        # Try likely Amazon index first, then others.
        candidate_indices = (0, 2, 3, 4, 5, 1)
        for idx in candidate_indices:
            if idx < len(val):
                v = val[idx]
                # Pair like [price, when] - take the SECOND element (price)
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    price = v[1]  # Second element is the price in cents
                else:
                    price = v
                if isinstance(price, (int, float)) and math.isfinite(price) and price >= 0:
                    return float(price)
        # As a last resort, scan all entries and return the first valid numeric (pair[1] if needed)
        for v in val:
            price = None
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                price = v[1]  # Take price from [timestamp, price] pair
            elif isinstance(v, (int, float)):
                price = v
            if isinstance(price, (int, float)) and math.isfinite(price) and price >= 0:
                return float(price)
        return None
    # Dict form: try common labels
    if isinstance(val, dict):
        # Try common labels then numeric keys (as int and string)
        for k in ("AMAZON", "amazon", "AMZ", 0, "0", "NEW", "new", 1, "1"):
            v = val.get(k)
            if isinstance(v, (int, float)) and math.isfinite(v) and v >= 0:
                return float(v)
        return None
    # Scalar form
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _normalize_products(products_resp) -> List[dict]:
    """Normalize various keepa/pykeepa response shapes into a list of product dicts."""
    if not products_resp:
        return []
    # Dict shapes
    if isinstance(products_resp, dict):
        if 'products' in products_resp and isinstance(products_resp['products'], list):
            return [p for p in products_resp['products'] if isinstance(p, dict)]
        # Single product dict
        if 'asin' in products_resp or 'stats' in products_resp:
            return [products_resp]
        return []
    # List/tuple shapes
    if isinstance(products_resp, (list, tuple)):
        # Tuple where first element is list of products
        if len(products_resp) > 0 and isinstance(products_resp[0], list):
            first = products_resp[0]
            return [p for p in first if isinstance(p, dict)]
        return [p for p in products_resp if isinstance(p, dict)]
    return []


def _parse_keepa_products_with_current(products: List[dict]) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    """Parse Keepa products to extract min, max, and current prices"""
    out: Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]] = {}
    for p in products or []:
        asin = (p.get('asin') or '').strip()
        if not asin:
            continue
            
        stats = p.get('stats') or {}
        raw_min = None
        raw_max = None
        raw_current = None
        
        # Try to get min/max/current from stats if available
        if stats:
            # Collect valid prices
            min_prices: List[float] = []
            max_prices: List[float] = []

            # Current price: in Keepa stats the first element of 'current' array is Amazon current price (in cents)
            if 'current' in stats:
                cur = stats['current']
                if isinstance(cur, (list, tuple)) and cur:
                    cand = cur[0]
                    if isinstance(cand, (int, float)) and cand > 0:
                        raw_current = float(cand)
                elif isinstance(cur, (int, float)) and cur > 0:
                    raw_current = float(cur)

            # Min array: first element (index 0) is [price, time] pair for Amazon lifetime min
            if 'min' in stats:
                stat_array = stats['min']
                if isinstance(stat_array, (list, tuple)) and stat_array:
                    first = stat_array[0]
                    if isinstance(first, (list, tuple)) and len(first) >= 2 and isinstance(first[1], (int, float)) and first[1] > 0:
                        min_prices.append(float(first[1]))
            # Max array analogous
            if 'max' in stats:
                stat_array = stats['max']
                if isinstance(stat_array, (list, tuple)) and stat_array:
                    first = stat_array[0]
                    if isinstance(first, (list, tuple)) and len(first) >= 2 and isinstance(first[1], (int, float)) and first[1] > 0:
                        max_prices.append(float(first[1]))

            if min_prices:
                raw_min = min(min_prices)
            if max_prices:
                raw_max = max(max_prices)
            # Fallback: if no min/max but we have current, seed them with current
            if (not isinstance(raw_min, (int, float)) or raw_min <= 0) and isinstance(raw_current, (int, float)) and raw_current > 0:
                raw_min = raw_current
            if (not isinstance(raw_max, (int, float)) or raw_max <= 0) and isinstance(raw_current, (int, float)) and raw_current > 0:
                raw_max = raw_current
        
        # If stats don't provide valid data, try history arrays
        if not isinstance(raw_min, (int, float)) or not isinstance(raw_max, (int, float)) or raw_min <= 0 or raw_max <= 0:
            hmin, hmax = _minmax_from_history(p)
            if not isinstance(raw_min, (int, float)) or raw_min <= 0:
                raw_min = hmin
            if not isinstance(raw_max, (int, float)) or raw_max <= 0:
                raw_max = hmax
        
        # Convert from cents to euros and round
        min_price = round(raw_min / 100.0, 2) if isinstance(raw_min, (int, float)) and raw_min > 0 else None
        max_price = round(raw_max / 100.0, 2) if isinstance(raw_max, (int, float)) and raw_max > 0 else None
        current_price = round(raw_current / 100.0, 2) if isinstance(raw_current, (int, float)) and raw_current > 0 else None
        
        out[asin] = (min_price, max_price, current_price)
    return out

def _parse_keepa_products(products: List[dict]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    out: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    for p in products or []:
        asin = (p.get('asin') or '').strip()
        if not asin:
            continue
            
        stats = p.get('stats') or {}
        raw_min = None
        raw_max = None
        
        # Try to get min/max from stats if available
        if stats:
            # Collect all valid prices from min/max stats arrays
            min_prices = []
            max_prices = []
            
            # Extract prices from min stats (use only first slot which is long-term historical)
            if 'min' in stats:
                stat_array = stats['min']
                if isinstance(stat_array, (list, tuple)) and len(stat_array) > 0:
                    item = stat_array[0]  # First slot = long-term historical data
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        price = item[1]  # Second element is price in cents
                        if isinstance(price, (int, float)) and price > 100:  # Filter out prices < €1.00
                            min_prices.append(float(price))
            
            # Extract prices from max stats (use only first slot which is long-term historical)
            if 'max' in stats:
                stat_array = stats['max']
                if isinstance(stat_array, (list, tuple)) and len(stat_array) > 0:
                    item = stat_array[0]  # First slot = long-term historical data
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        price = item[1]  # Second element is price in cents
                        if isinstance(price, (int, float)) and price > 100:  # Filter out prices < €1.00
                            max_prices.append(float(price))
            
            # Calculate actual min/max
            if min_prices:
                raw_min = min(min_prices)
            if max_prices:
                raw_max = max(max_prices)
                        
            # If min/max not found in stats, try current price as fallback
            if (not isinstance(raw_min, (int, float)) or raw_min <= 0) and 'current' in stats:
                current_price = _pick_amazon_stat(stats, 'current')
                if isinstance(current_price, (int, float)) and current_price > 0:
                    raw_min = raw_max = current_price
        
        # If stats don't provide valid data, try history arrays
        if not isinstance(raw_min, (int, float)) or not isinstance(raw_max, (int, float)) or raw_min <= 0 or raw_max <= 0:
            hmin, hmax = _minmax_from_history(p)
            if not isinstance(raw_min, (int, float)) or raw_min <= 0:
                raw_min = hmin
            if not isinstance(raw_max, (int, float)) or raw_max <= 0:
                raw_max = hmax
        
        # Convert from cents to euros and round
        min_price = round(raw_min / 100.0, 2) if isinstance(raw_min, (int, float)) and raw_min > 0 else None
        max_price = round(raw_max / 100.0, 2) if isinstance(raw_max, (int, float)) and raw_max > 0 else None
        
        out[asin] = (min_price, max_price)
    return out

def _minmax_from_history(product: dict) -> Tuple[Optional[float], Optional[float]]:
    """Compute min/max (in cents) from Keepa history arrays when stats are missing.
    Tries 'data' dict with keys like 'AMAZON'/0, then 'csv' list where index 0 is Amazon.
    """
    # Try 'data' mapping first
    data = product.get('data') or {}
    series = None
    if isinstance(data, dict):
        for k in ('AMAZON', 'amazon', 0, '0', 'NEW', 'new', 1, '1'):
            if k in data and isinstance(data[k], (list, tuple)):
                series = data[k]
                break
    if series is None:
        # Fallback to 'csv' array of arrays (0 == Amazon)
        csv = product.get('csv')
        if isinstance(csv, (list, tuple)) and len(csv) > 0 and isinstance(csv[0], (list, tuple)):
            series = csv[0]
    if not isinstance(series, (list, tuple)) or len(series) == 0:
        return None, None
    # Keepa series alternate timestamp, value. Extract values at odd indices.
    values: List[float] = []
    for idx, v in enumerate(series):
        if idx % 2 == 1 and isinstance(v, (int, float)) and math.isfinite(v) and v >= 0:
            values.append(float(v))
    if not values:
        # Some shapes may be simple value lists; try all positions
        for v in series:
            if isinstance(v, (int, float)) and math.isfinite(v) and v >= 0:
                values.append(float(v))
    if not values:
        return None, None
    return (min(values), max(values))


def _fetch_via_http_with_current(asin_list: List[str], api_key: str) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    import httpx  # lazy import
    params = {
        "key": api_key,
        "domain": str(get_keepa_domain_id()),
        "asin": ",".join(asin_list[:100]),  # Keepa has limits; batch up to 100
        "stats": "1800",
        "history": "1",
    }
    url = "https://api.keepa.com/product"
    timeout = getattr(config, "request_timeout_seconds", 20) or 20
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    products = data.get("products") or []
    # Normalize to the same structure parser expects
    norm = []
    for p in products:
        norm.append({
            "asin": p.get("asin"),
            "stats": p.get("stats", {}),
        })
    return _parse_keepa_products_with_current(norm)

def _fetch_via_http(asin_list: List[str], api_key: str) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    import httpx  # lazy import
    params = {
        "key": api_key,
        "domain": str(get_keepa_domain_id()),
        "asin": ",".join(asin_list[:100]),  # Keepa has limits; batch up to 100
        "stats": "1800",
        "history": "1",
    }
    url = "https://api.keepa.com/product"
    timeout = getattr(config, "request_timeout_seconds", 20) or 20
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    products = data.get("products") or []
    # Normalize to the same structure parser expects
    norm = []
    for p in products:
        norm.append({
            "asin": p.get("asin"),
            "stats": p.get("stats", {}),
        })
    return _parse_keepa_products(norm)
