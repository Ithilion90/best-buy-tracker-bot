import json
import time
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
import hashlib
from dataclasses import dataclass, asdict
from threading import Lock

@dataclass
class CacheEntry:
    data: Any
    timestamp: float
    ttl: float
    
    @property
    def is_expired(self) -> bool:
        return time.time() > (self.timestamp + self.ttl)

class DiskCache:
    """Simple disk-based cache with TTL support"""
    
    def __init__(self, cache_dir: str = "cache", default_ttl: float = 3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)  # Create parent directories too
        self.default_ttl = default_ttl
        self._lock = Lock()
    
    def _get_cache_path(self, key: str) -> Path:
        # Create a safe filename from the key
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.json"
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache"""
        with self._lock:
            cache_path = self._get_cache_path(key)
            
            if not cache_path.exists():
                return None
            
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    entry_data = json.load(f)
                    entry = CacheEntry(**entry_data)
                
                if entry.is_expired:
                    cache_path.unlink(missing_ok=True)
                    return None
                
                return entry.data
            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                cache_path.unlink(missing_ok=True)
                return None
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set item in cache"""
        with self._lock:
            cache_path = self._get_cache_path(key)
            entry = CacheEntry(
                data=value,
                timestamp=time.time(),
                ttl=ttl or self.default_ttl
            )
            
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(asdict(entry), f)
            except Exception:
                # Fail silently on cache write errors
                pass
    
    def delete(self, key: str) -> None:
        """Delete item from cache"""
        with self._lock:
            cache_path = self._get_cache_path(key)
            cache_path.unlink(missing_ok=True)
    
    def clear_expired(self) -> int:
        """Clear all expired entries, return count of cleared items"""
        cleared = 0
        with self._lock:
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        entry_data = json.load(f)
                        entry = CacheEntry(**entry_data)
                    
                    if entry.is_expired:
                        cache_file.unlink()
                        cleared += 1
                except Exception:
                    # Remove corrupted cache files
                    cache_file.unlink(missing_ok=True)
                    cleared += 1
        return cleared

class KeepaCache:
    """Specialized cache for Keepa API responses"""
    
    def __init__(self, cache_dir: str = "cache/keepa"):
        self.cache = DiskCache(cache_dir, default_ttl=1800)  # 30 minutes default
    
    def get_lifetime_minmax(self, asins: List[str]) -> Optional[Dict[str, Tuple[Optional[float], Optional[float]]]]:
        """Get cached lifetime min/max for list of ASINs"""
        cache_key = f"minmax:{':'.join(sorted(asins))}"
        return self.cache.get(cache_key)
    
    def set_lifetime_minmax(self, asins: List[str], data: Dict[str, Tuple[Optional[float], Optional[float]]], ttl: float = 1800) -> None:
        """Cache lifetime min/max for list of ASINs"""
        cache_key = f"minmax:{':'.join(sorted(asins))}"
        self.cache.set(cache_key, data, ttl)
    
    def get_lifetime_minmax_current(self, asins: List[str]) -> Optional[Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]]:
        """Get cached lifetime min/max/current for list of ASINs"""
        cache_key = f"minmax_current:{':'.join(sorted(asins))}"
        return self.cache.get(cache_key)
    
    def set_lifetime_minmax_current(self, asins: List[str], data: Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]], ttl: float = 1800) -> None:
        """Cache lifetime min/max/current for list of ASINs"""
        cache_key = f"minmax_current:{':'.join(sorted(asins))}"
        self.cache.set(cache_key, data, ttl)
    
    def get_product_info(self, asin: str) -> Optional[Dict[str, Any]]:
        """Get cached product info for single ASIN"""
        cache_key = f"product:{asin}"
        return self.cache.get(cache_key)
    
    def set_product_info(self, asin: str, data: Dict[str, Any], ttl: float = 3600) -> None:
        """Cache product info for single ASIN"""
        cache_key = f"product:{asin}"
        self.cache.set(cache_key, data, ttl)

# Global cache instances
keepa_cache = KeepaCache()
general_cache = DiskCache("cache/general")
