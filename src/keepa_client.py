from typing import Dict, Tuple, Optional, List, Any
import math
import keepa  # type: ignore
try:
    from .config import config
    from .logger import logger
    from .resilience import retry_with_backoff, circuit_breakers
except ImportError:
    from config import config
    from logger import logger
    from resilience import retry_with_backoff, circuit_breakers

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

def fetch_keepa_debug_data(asin: str, domain: Optional[str] = None) -> Dict[str, Any]:  # diagnostic utility
    """Fetch raw Keepa product and expose parsing diagnostics for a single ASIN.
    Returns a dict with keys: asin, domain, stats_min_raw, stats_max_raw, stats_current_raw,
    parsed_min, parsed_max, parsed_current, history_min, history_max, sample_prices.
    Performs a direct HTTP fetch to avoid stale anomalies."""
    key = (getattr(config, "keepa_api_key", "") or "").strip()
    if not key or not asin:
        return {"error": "Missing key or ASIN"}
    try:
        import httpx
        params = {
            "key": key,
            "domain": str(get_keepa_domain_id(domain)),
            "asin": asin,
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
        if not products:
            return {"error": "No product data returned"}
        p = products[0]
        stats = p.get("stats", {}) or {}
        # Raw stats (cents) original entries (could be scalar / list / dict)
        raw_min_entry = stats.get("min")
        raw_max_entry = stats.get("max")
        raw_current_entry = stats.get("current")

        # Helper to introspect how _pick_amazon_stat would interpret a stat
        def _debug_interpret(entry) -> Tuple[Optional[float], Optional[str], Optional[Any]]:
            rationale = None
            sample = None
            if entry is None:
                return None, "missing", None
            if isinstance(entry, (int, float)):
                if 0 < entry < 2_000_000:
                    return float(entry), "scalar", entry
                else:
                    return None, "scalar_out_of_range", entry
            if isinstance(entry, (list, tuple)):
                if len(entry) == 0:
                    return None, "empty_list", None
                primary = entry[0]
                if isinstance(primary, (list, tuple)) and len(primary) >= 2:
                    a, b = primary[0], primary[1]
                    sample = [a, b]
                    # Mirror logic from _pick_amazon_stat.extract_from_pair
                    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                        if a > 2_000_000 and b < 2_000_000:
                            return float(b), "pair_b_is_price", sample
                        if b > 2_000_000 and a < 2_000_000:
                            return float(a), "pair_a_is_price", sample
                        if a < 200_000 and b > 200_000:
                            return float(a), "pair_a_lt_threshold", sample
                        if 0 < a < 2_000_000:
                            return float(a), "pair_first_assumed_price", sample
                # Fallback scan
                for v in entry:
                    if isinstance(v, (list, tuple)) and len(v) >= 2:
                        a, b = v[0], v[1]
                        sample = [a, b]
                        if isinstance(a, (int, float)) and 0 < a < 2_000_000:
                            return float(a), "scan_pair_first", sample
                        if isinstance(b, (int, float)) and 0 < b < 2_000_000:
                            return float(b), "scan_pair_second", sample
                    elif isinstance(v, (int, float)) and 0 < v < 2_000_000:
                        return float(v), "scan_scalar", v
                return None, "list_no_price", None
            if isinstance(entry, dict):
                for k in ("AMAZON", "amazon", "AMZ", 0, "0", "NEW", "new", 1, "1"):
                    v = entry.get(k)
                    if isinstance(v, (int, float)) and 0 < v < 2_000_000:
                        return float(v), f"dict_key:{k}", v
                    if isinstance(v, (list, tuple)) and len(v) >= 2:
                        a, b = v[0], v[1]
                        sample = [a, b]
                        if isinstance(a, (int, float)) and 0 < a < 2_000_000:
                            return float(a), f"dict_pair_first:{k}", sample
                        if isinstance(b, (int, float)) and 0 < b < 2_000_000:
                            return float(b), f"dict_pair_second:{k}", sample
                return None, "dict_no_price", None
            return None, "unhandled_type", str(type(entry))

        raw_min, min_reason, min_sample = _debug_interpret(raw_min_entry)
        raw_max, max_reason, max_sample = _debug_interpret(raw_max_entry)
        raw_current, cur_reason, cur_sample = _debug_interpret(raw_current_entry)
        # Use existing parser for final interpreted values
        parsed = _parse_keepa_products_with_current([p])
        parsed_min, parsed_max, parsed_current = parsed.get(asin, (None, None, None))
        hmin, hmax = _minmax_from_history(p)
        sample_prices: List[float] = []
        csv0 = p.get("csv")[0] if isinstance(p.get("csv"), (list, tuple)) and p.get("csv") else None
        if isinstance(csv0, (list, tuple)):
            for idx, v in enumerate(csv0):
                if len(sample_prices) >= 12:
                    break
                if idx % 2 == 1 and isinstance(v, (int, float)) and v > 0:
                    sample_prices.append(round(v / 100.0, 2))
        return {
            "asin": asin,
            "domain": domain or getattr(config, "keepa_domain", "com"),
            "stats_min_raw": raw_min,
            "stats_max_raw": raw_max,
            "stats_current_raw": raw_current,
            "stats_min_entry": raw_min_entry,
            "stats_max_entry": raw_max_entry,
            "stats_current_entry": raw_current_entry,
            "stats_min_reason": min_reason,
            "stats_max_reason": max_reason,
            "stats_current_reason": cur_reason,
            "stats_min_sample": min_sample,
            "stats_max_sample": max_sample,
            "stats_current_sample": cur_sample,
            "parsed_min": parsed_min,
            "parsed_max": parsed_max,
            "parsed_current": parsed_current,
            "history_min": round(hmin / 100.0, 2) if isinstance(hmin, (int, float)) and hmin > 0 else None,
            "history_max": round(hmax / 100.0, 2) if isinstance(hmax, (int, float)) and hmax > 0 else None,
            "sample_prices": sample_prices,
        }
    except Exception as e:  # pragma: no cover - diagnostic
        try:
            logger.warning("Keepa debug fetch failed", asin=asin, error=str(e))
        except Exception:
            pass
        return {"error": str(e), "asin": asin}

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
    """Return {asin: (min, max, current)} lifetime prices (always fetched fresh)."""
    key = (getattr(config, "keepa_api_key", "") or "").strip()
    if not key or not asin_list:
        return {}
    try:
        # Primary: keepa package
        return circuit_breakers['keepa_api'].call(_fetch_from_keepa_package_with_current, key, asin_list, domain)
    except ImportError:
        try:
            return _fetch_from_pykeepa_with_current(key, asin_list, domain)
        except ImportError:
            try:
                return circuit_breakers['keepa_api'].call(_fetch_via_http_with_current, asin_list, key, domain)
            except Exception as e:
                logger.error("All Keepa methods failed", error=str(e))
                return {asin: (None, None, None) for asin in asin_list}
    except Exception as e:
        logger.error("Keepa API failed", error=str(e), asins=len(asin_list))
        return {asin: (None, None, None) for asin in asin_list}

@retry_with_backoff(max_retries=3, exceptions=(Exception,))
def fetch_lifetime_min_max(asin_list: List[str], domain: Optional[str] = None, force: bool = False) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """Return {asin: (min, max)} lifetime prices (fresh fetch)."""
    key = (getattr(config, "keepa_api_key", "") or "").strip()
    if not key or not asin_list:
        return {}
    try:
        return circuit_breakers['keepa_api'].call(_fetch_from_keepa_package, key, asin_list, domain)
    except ImportError:
        try:
            return _fetch_from_pykeepa(key, asin_list, domain)
        except ImportError:
            try:
                return circuit_breakers['keepa_api'].call(_fetch_via_http, asin_list, key, domain)
            except Exception as e:
                logger.error("All Keepa methods failed", error=str(e))
                return {asin: (None, None) for asin in asin_list}
    except Exception as e:
        logger.error("Keepa API failed", error=str(e), asins=len(asin_list))
        return {asin: (None, None) for asin in asin_list}

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
    """Extract Amazon price (in cents) for the requested stat key.

    Root cause of previous exaggerated max values: we treated list-pair entries
    as [timestamp, price] and picked the second element, but Keepa returns
    pairs as [price, timestamp]. That caused us to sometimes interpret a large
    timestamp (minutes since a reference epoch) as the price producing huge
    max values.

    Heuristics:
    - Prefer index 0 (Amazon) if scalar or pair.
    - For a 2-length pair (a,b) decide which is price:
        * If one element > 2_000_000 and the other < 2_000_000 -> smaller is price.
        * Else if a < 200_000 and b > 200_000 -> a is price.
        * Else assume first element is price (Keepa spec: [price, time]).
    - Skip obvious timestamp-only numbers (> 2_000_000) when alone.
    - Fallback: scan list for first plausible price 1..2_000_000.
    - Dict form: try common labels.
    """
    val = stats.get(key)
    if val is None:
        return None

    def extract_from_pair(a, b):
        # Identify timestamp vs price by magnitude
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if a > 2_000_000 and b < 2_000_000:
                return b
            if b > 2_000_000 and a < 2_000_000:
                return a
            if a < 200_000 and b > 200_000:  # typical price cents (<2000.00) vs timestamp
                return a
            # Default Keepa ordering
            return a
        return None

    if isinstance(val, (list, tuple)):
        # Direct candidates (Amazon condition usually at index 0)
        primary = val[0] if len(val) > 0 else None
        candidates = []
        if isinstance(primary, (list, tuple)) and len(primary) >= 2:
            price = extract_from_pair(primary[0], primary[1])
            if isinstance(price, (int, float)) and 0 < price < 2_000_000:
                return float(price)
        elif isinstance(primary, (int, float)) and 0 < primary < 2_000_000:
            return float(primary)
        # Scan remaining entries
        for v in val:
            price = None
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                price = extract_from_pair(v[0], v[1])
            elif isinstance(v, (int, float)):
                price = v if 0 < v < 2_000_000 else None
            if isinstance(price, (int, float)) and 0 < price < 2_000_000:
                return float(price)
        return None

    if isinstance(val, dict):
        for k in ("AMAZON", "amazon", "AMZ", 0, "0", "NEW", "new", 1, "1"):
            v = val.get(k)
            if isinstance(v, (int, float)) and 0 < v < 2_000_000:
                return float(v)
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                extracted = extract_from_pair(v[0], v[1])
                if isinstance(extracted, (int, float)) and 0 < extracted < 2_000_000:
                    return float(extracted)
        return None

    if isinstance(val, (int, float)) and 0 < val < 2_000_000:
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
