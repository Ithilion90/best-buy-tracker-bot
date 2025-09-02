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

def _normalize_keepa_key(dom: Optional[str]) -> str:
    if not dom:
        return (getattr(config, "keepa_domain", "com") or "com").lower()
    # Accept full host like amazon.co.uk or just suffix
    d = dom.lower()
    if d.startswith('amazon.'):
        d = d[len('amazon.') :]
    return d

def get_keepa_domain_id(domain_override: Optional[str] = None) -> int:
    dom = _normalize_keepa_key(domain_override)
    return DomainMap.get(dom, 1)

def get_keepa_domain_name(domain_override: Optional[str] = None) -> str:
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
    dom = _normalize_keepa_key(domain_override)
    return mapping.get(dom, "US")

@retry_with_backoff(max_retries=3, exceptions=(Exception,))
def fetch_lifetime_min_max_current(asin_list: List[str], domain: Optional[str] = None, force: bool = False) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    """Return {asin: (min, max, current)} lifetime prices (Amazon price) in same currency.
    Uses a 30 minute cache (1800s) to reduce API quota usage while keeping data reasonably fresh.
    On error returns empty mapping or (None, None, None) entries so the caller can fallback.
    """
    key = (getattr(config, "keepa_api_key", "") or "").strip()
    if not key or not asin_list:
        return {}

    # Check cache first (10 min TTL enforced when setting)
    if not force:
        cached = keepa_cache.get_lifetime_minmax_current(asin_list, domain=domain)
        if cached is not None:
            logger.info("Using cached Keepa current/min/max data", asins=len(asin_list), domain=domain)
            return cached
    else:
        keepa_cache.invalidate_lifetime_minmax_current(asin_list, domain=domain)

    logger.info("Fetching Keepa data with current prices (cache miss)", asins=len(asin_list), domain=domain or getattr(config, 'keepa_domain', 'com'))

    try:
        # Primary: keepa package
        result = circuit_breakers['keepa_api'].call(_fetch_from_keepa_package_with_current, key, asin_list, domain)
        if result:
            keepa_cache.set_lifetime_minmax_current(asin_list, result, ttl=1800, domain=domain)  # 30 minutes
            logger.info("Keepa current/min/max data fetched and cached", asins=len(asin_list), results=len(result), ttl_seconds=1800, domain=domain)
        return result
    except ImportError:
        # Fallback: pykeepa
        try:
            result = _fetch_from_pykeepa_with_current(key, asin_list, domain)
            if result:
                keepa_cache.set_lifetime_minmax_current(asin_list, result, ttl=1800, domain=domain)
            return result
        except ImportError:
            # Final fallback: raw HTTP
            try:
                result = circuit_breakers['keepa_api'].call(_fetch_via_http_with_current, asin_list, key, domain)
                if result:
                    keepa_cache.set_lifetime_minmax_current(asin_list, result, ttl=1800, domain=domain)
                return result
            except Exception as e:
                logger.error("All Keepa methods failed", error=str(e))
                return {asin: (None, None, None) for asin in asin_list}
    except Exception as e:
        logger.error("Keepa API failed", error=str(e), asins=len(asin_list))
        return {asin: (None, None, None) for asin in asin_list}

@retry_with_backoff(max_retries=3, exceptions=(Exception,))
def fetch_lifetime_min_max(asin_list: List[str], domain: Optional[str] = None, force: bool = False) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Return {asin: (min, max)} lifetime (price type: Amazon price) in same currency.
    Requires KEEPA_API_KEY in config; on error returns {} or missing keys.
    If Keepa doesn't have historical data, returns (None, None) so caller can use DB fallback.
    Uses caching and circuit breaker for resilience.
    """
    key = (getattr(config, "keepa_api_key", "") or "").strip()
    if not key or not asin_list:
        return {}
    
    # Check cache first
    if not force:
        cached_result = keepa_cache.get_lifetime_minmax(asin_list, domain=domain)
        if cached_result is not None:
            logger.info("Using cached Keepa data", asins=len(asin_list), domain=domain)
            return cached_result
    else:
        keepa_cache.invalidate_lifetime_minmax(asin_list, domain=domain)
    
    try:
        # Try with 'keepa' package first using circuit breaker
        result = circuit_breakers['keepa_api'].call(_fetch_from_keepa_package, key, asin_list, domain)
    except ImportError:
        # Fallback: try pykeepa
        try:
            result = _fetch_from_pykeepa(key, asin_list, domain)
        except ImportError:
            # Final fallback: HTTP API
            try:
                result = circuit_breakers['keepa_api'].call(_fetch_via_http, asin_list, key, domain)
            except Exception as e:
                logger.error("All Keepa methods failed", error=str(e))
                return {asin: (None, None) for asin in asin_list}
    except Exception as e:
        logger.error("Keepa API failed", error=str(e), asins=len(asin_list))
        return {asin: (None, None) for asin in asin_list}

    # Cache successful result if any
    if result:
        keepa_cache.set_lifetime_minmax(asin_list, result, domain=domain)
        logger.info("Keepa data fetched and cached", asins=len(asin_list), results=len(result))
    return result

def _fetch_from_keepa_package_with_current(key: str, asin_list: List[str], domain: Optional[str]) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    """Fetch from keepa package with current prices"""
    api = keepa.Keepa(key)
    products_resp = api.query(
        asin_list,
        domain=get_keepa_domain_name(domain),
        stats=1800,
        history=True  # enable history so we can compute proper min/max from csv/data
    )
    products = _normalize_products(products_resp)
    return _parse_keepa_products_with_current(products)

def _fetch_from_pykeepa_with_current(key: str, asin_list: List[str], domain: Optional[str]) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    """Fetch from pykeepa with current prices"""
    import pykeepa  # type: ignore
    try:
        products_resp = pykeepa.query(
            key,
            asin_list,
            stats=1800,
            domain=get_keepa_domain_id(domain),
            history=True,
        )
    except Exception:
        products_resp = []
    products = _normalize_products(products_resp)
    return _parse_keepa_products_with_current(products)

def _fetch_from_keepa_package(key: str, asin_list: List[str], domain: Optional[str]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Fetch from keepa package"""
    api = keepa.Keepa(key)
    products_resp = api.query(
        asin_list,
        domain=get_keepa_domain_name(domain),
        stats=1800,
        history=True  # enable history for pure min/max fetch
    )
    products = _normalize_products(products_resp)
    return _parse_keepa_products(products)

def _fetch_from_pykeepa(key: str, asin_list: List[str], domain: Optional[str]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Fetch from pykeepa"""
    import pykeepa  # type: ignore
    try:
        products_resp = pykeepa.query(
            key,
            asin_list,
            stats=1800,
            domain=get_keepa_domain_id(domain),
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

    # Removed unused helper _extract_prices_from_stat_array (cleanup)

def _parse_keepa_products_with_current(products: List[dict]) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    """Parse Keepa products to extract min, max, and current prices with diagnostics."""
    out: Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]] = {}
    for p in products or []:
        asin = (p.get('asin') or '').strip()
        if not asin:
            continue

        stats = p.get('stats') or {}
        try:
            logger.debug("Keepa diagnostic", asin=asin, stats_keys=list(stats.keys())[:12], has_csv=bool(p.get('csv')), has_data=bool(p.get('data')))
        except Exception:
            pass
        # Prefer explicitly Amazon (index 0) values from stats without mixing other conditions.
        raw_current: Optional[float] = None
        raw_min: Optional[float] = None
        raw_max: Optional[float] = None
        if stats:
            raw_current = _pick_amazon_stat(stats, 'current')
            raw_min = _pick_amazon_stat(stats, 'min')
            raw_max = _pick_amazon_stat(stats, 'max')
            # If min/max absent but current present, initialize (will still allow history improvement)
            if (not isinstance(raw_min, (int, float)) or raw_min <= 0) and isinstance(raw_current, (int, float)) and raw_current > 0:
                raw_min = raw_current
            if (not isinstance(raw_max, (int, float)) or raw_max <= 0) and isinstance(raw_current, (int, float)) and raw_current > 0:
                raw_max = raw_current

        # History fallback if stats missing OR trivial (min==max==current)
        need_history = (
            not isinstance(raw_min, (int, float))
            or not isinstance(raw_max, (int, float))
            or raw_min <= 0
            or raw_max <= 0
            or (isinstance(raw_current, (int, float)) and raw_min == raw_max == raw_current)
        )
        if need_history:
            hmin, hmax = _minmax_from_history(p)
            # Extra diagnostics when history requested
            try:
                csv0 = p.get('csv')[0] if isinstance(p.get('csv'), (list, tuple)) and p.get('csv') else None
                sample_values = []
                if isinstance(csv0, (list, tuple)):
                    # Extract first 20 price entries (odd indices if alternating)
                    extracted = []
                    for idx, v in enumerate(csv0):
                        if len(extracted) >= 20:
                            break
                        if idx % 2 == 1 and isinstance(v, (int, float)) and v > 0:
                            extracted.append(v)
                    sample_values = extracted
                logger.debug("Keepa history diagnostic", asin=asin, history_min=hmin, history_max=hmax, sample_len=len(sample_values), sample=sample_values[:10])
            except Exception:
                pass
            updated = False
            if (not isinstance(raw_min, (int, float)) or raw_min <= 0 or (raw_min == raw_current and hmin and hmin < raw_min)) and hmin:
                raw_min = hmin
                updated = True
            if (not isinstance(raw_max, (int, float)) or raw_max <= 0 or (raw_max == raw_current and hmax and hmax > raw_max)) and hmax:
                raw_max = hmax
                updated = True
            if updated:
                try:
                    logger.info("History fallback considered", asin=asin, hmin=hmin, hmax=hmax, current=raw_current)
                except Exception:
                    pass
            else:
                if isinstance(raw_current, (int, float)) and raw_min == raw_max == raw_current:
                    try:
                        logger.info("History absent or not improving (provisional bounds)", asin=asin, current=raw_current)
                    except Exception:
                        pass

        min_price = round(raw_min / 100.0, 2) if isinstance(raw_min, (int, float)) and raw_min > 0 else None
        max_price = round(raw_max / 100.0, 2) if isinstance(raw_max, (int, float)) and raw_max > 0 else None
        current_price = round(raw_current / 100.0, 2) if isinstance(raw_current, (int, float)) and raw_current > 0 else None
        try:
            logger.debug("Keepa final prices", asin=asin, min=min_price, max=max_price, current=current_price)
        except Exception:
            pass
        out[asin] = (min_price, max_price, current_price)
    return out

def _parse_keepa_products(products: List[dict]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Parse Keepa products (min/max only) with diagnostics."""
    out: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    for p in products or []:
        asin = (p.get('asin') or '').strip()
        if not asin:
            continue
        stats = p.get('stats') or {}
        try:
            logger.debug("Keepa diagnostic (no current)", asin=asin, stats_keys=list(stats.keys())[:12], has_csv=bool(p.get('csv')), has_data=bool(p.get('data')))
        except Exception:
            pass
        raw_min: Optional[float] = None
        raw_max: Optional[float] = None

        if stats:
            raw_min = _pick_amazon_stat(stats, 'min')
            raw_max = _pick_amazon_stat(stats, 'max')
            if (not isinstance(raw_min, (int, float)) or raw_min <= 0) and 'current' in stats:
                c = _pick_amazon_stat(stats, 'current')
                if isinstance(c, (int, float)) and c > 0:
                    raw_min = c
            if (not isinstance(raw_max, (int, float)) or raw_max <= 0) and 'current' in stats:
                c = _pick_amazon_stat(stats, 'current')
                if isinstance(c, (int, float)) and c > 0:
                    raw_max = c

        need_history = (
            not isinstance(raw_min, (int, float))
            or not isinstance(raw_max, (int, float))
            or raw_min <= 0
            or raw_max <= 0
            or (isinstance(raw_min, (int, float)) and isinstance(raw_max, (int, float)) and raw_min == raw_max)
        )
        if need_history:
            hmin, hmax = _minmax_from_history(p)
            updated = False
            if (not isinstance(raw_min, (int, float)) or raw_min <= 0 or (raw_min == raw_max and hmin and hmin < raw_min)) and hmin:
                raw_min = hmin
                updated = True
            if (not isinstance(raw_max, (int, float)) or raw_max <= 0 or (raw_min == raw_max and hmax and hmax > raw_max)) and hmax:
                raw_max = hmax
                updated = True
            if updated:
                try:
                    logger.info("History fallback considered (no current)", asin=asin, hmin=hmin, hmax=hmax)
                except Exception:
                    pass

        min_price = round(raw_min / 100.0, 2) if isinstance(raw_min, (int, float)) and raw_min > 0 else None
        max_price = round(raw_max / 100.0, 2) if isinstance(raw_max, (int, float)) and raw_max > 0 else None
        try:
            logger.debug("Keepa final prices (no current)", asin=asin, min=min_price, max=max_price)
        except Exception:
            pass
        out[asin] = (min_price, max_price)
    return out

def _minmax_from_history(product: dict) -> Tuple[Optional[float], Optional[float]]:
    """Compute min/max (in cents) from Keepa history arrays with robust timestamp filtering.

    Heuristics:
    - Prefer product['data'][AMAZON] style series; fallback to csv[0].
    - Detect alternating timestamp/value pattern by monotonicity of one subset (timestamps grow).
    - If ambiguity remains, treat subset with median >> other OR median > 1e6 as timestamps.
    - Filter unrealistic price cents (> 2,000,000 = 20,000.00) as timestamps/outliers.
    - If after filtering no prices remain, return (None, None).
    """
    data = product.get('data') or {}
    series = None
    if isinstance(data, dict):
        for k in ('AMAZON', 'amazon', 0, '0', 'NEW', 'new', 1, '1'):
            seq = data.get(k)
            if isinstance(seq, (list, tuple)) and len(seq) >= 4:
                series = seq
                break
    if series is None:
        csv = product.get('csv')
        if isinstance(csv, (list, tuple)) and len(csv) > 0 and isinstance(csv[0], (list, tuple)) and len(csv[0]) >= 4:
            series = csv[0]
    if not isinstance(series, (list, tuple)) or len(series) < 4:
        return None, None

    # Split even/odd indices
    even_vals = [v for i, v in enumerate(series) if i % 2 == 0 and isinstance(v, (int, float)) and math.isfinite(v)]
    odd_vals = [v for i, v in enumerate(series) if i % 2 == 1 and isinstance(v, (int, float)) and math.isfinite(v)]

    def monotonic_score(seq: List[float]) -> float:
        if len(seq) < 3:
            return 0.0
        inc = 0
        total = 0
        last = seq[0]
        for v in seq[1:]:
            if v >= last:
                inc += 1
            total += 1
            last = v
        return inc / total if total else 0.0

    m_even = monotonic_score(even_vals)
    m_odd = monotonic_score(odd_vals)
    median_even = sorted(even_vals)[len(even_vals)//2] if even_vals else 0
    median_odd = sorted(odd_vals)[len(odd_vals)//2] if odd_vals else 0

    # Decide which subset are timestamps
    timestamps_are_even = False
    timestamps_are_odd = False
    # Primary decision: strong monotonicity difference
    if m_even >= 0.8 and m_odd < 0.6:
        timestamps_are_even = True
    elif m_odd >= 0.8 and m_even < 0.6:
        timestamps_are_odd = True
    else:
        # Secondary: magnitude heuristic (timestamps often >> prices or >1e6)
        if median_even > 1_000_000 and median_even > median_odd * 2:
            timestamps_are_even = True
        elif median_odd > 1_000_000 and median_odd > median_even * 2:
            timestamps_are_odd = True
        else:
            # Fallback: choose subset with larger monotonic score as timestamps
            if m_even > m_odd:
                timestamps_are_even = True
            else:
                timestamps_are_odd = True

    if timestamps_are_even:
        price_candidates = odd_vals
    elif timestamps_are_odd:
        price_candidates = even_vals
    else:
        price_candidates = odd_vals  # default

    # Filter unrealistic price cents (> 2,000,000) and non-positive
    filtered = [v for v in price_candidates if 0 < v <= 2_000_000]
    # If nothing left, attempt alternate subset
    if not filtered:
        alt = even_vals if price_candidates is odd_vals else odd_vals
        filtered = [v for v in alt if 0 < v <= 2_000_000]
    if not filtered:
        try:
            logger.debug("History filtering produced no prices", m_even=m_even, m_odd=m_odd, median_even=median_even, median_odd=median_odd)
        except Exception:
            pass
        return None, None
    # Remove obvious outliers using IQR
    if len(filtered) >= 5:
        s = sorted(filtered)
        q1 = s[len(s)//4]
        q3 = s[(len(s)*3)//4]
        iqr = max(q3 - q1, 1)
        upper = q3 + 3 * iqr
        lower = max(q1 - 3 * iqr, 0)
        filtered = [v for v in filtered if lower <= v <= upper]
        if not filtered:
            return None, None
    try:
        logger.debug("History price extraction", count=len(filtered), m_even=m_even, m_odd=m_odd, timestamps_even=timestamps_are_even, timestamps_odd=timestamps_are_odd)
    except Exception:
        pass
    return (min(filtered), max(filtered))


def _fetch_via_http_with_current(asin_list: List[str], api_key: str, domain: Optional[str]) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]:
    import httpx  # lazy import
    params = {
        "key": api_key,
    "domain": str(get_keepa_domain_id(domain)),
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
            # Preserve history arrays for fallback parsing
            "csv": p.get("csv"),
            "data": p.get("data"),
        })
    return _parse_keepa_products_with_current(norm)

def _fetch_via_http(asin_list: List[str], api_key: str, domain: Optional[str]) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    import httpx  # lazy import
    params = {
        "key": api_key,
    "domain": str(get_keepa_domain_id(domain)),
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
            "csv": p.get("csv"),
            "data": p.get("data"),
        })
    return _parse_keepa_products(norm)
