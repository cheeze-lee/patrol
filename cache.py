"""
In-memory cache management with MaxQueue support
"""

import time
from typing import Optional, Dict, Tuple
from patrol_types import AnalysisResult


class InMemoryCache:
    """
    In-memory cache with MaxQueue configuration and LRU/FIFO eviction
    """
    
    def __init__(self, max_size: int = 1000, eviction_policy: str = 'LRU'):
        """
        Initialize cache
        
        Args:
            max_size: Maximum number of cache entries
            eviction_policy: 'LRU' (Least Recently Used) or 'FIFO' (First In First Out)
        """
        self.cache: Dict[str, Tuple[AnalysisResult, int]] = {}  # key -> (value, timestamp)
        self.max_size = max(1, max_size)
        self.eviction_policy = eviction_policy
        self.access_order: Dict[str, int] = {}  # key -> last_access_time
        self.hits = 0
        self.misses = 0
        self.writes = 0
    
    def get(self, key: str) -> Optional[AnalysisResult]:
        """
        Get value from cache
        
        Returns None if not found or expired
        """
        if key not in self.cache:
            self.misses += 1
            return None
        
        result, expires_at = self.cache[key]
        
        # Check if expired
        if time.time() > expires_at:
            del self.cache[key]
            if key in self.access_order:
                del self.access_order[key]
            self.misses += 1
            return None
        
        # Update access time for LRU
        self.access_order[key] = time.time()
        self.hits += 1
        
        return result
    
    def set(self, key: str, value: AnalysisResult, ttl: int = 86400) -> None:
        """
        Set value in cache with TTL
        
        Args:
            key: Cache key
            value: Analysis result to cache
            ttl: Time to live in seconds (default: 24 hours)
        """
        expires_at = time.time() + ttl
        self.cache[key] = (value, expires_at)
        self.access_order[key] = time.time()
        self.writes += 1
        
        # Check if eviction is needed
        self._evict_if_needed()
    
    def delete(self, key: str) -> None:
        """Delete value from cache"""
        if key in self.cache:
            del self.cache[key]
        if key in self.access_order:
            del self.access_order[key]
    
    def _evict_if_needed(self) -> None:
        """Evict entries if cache exceeds max size"""
        if len(self.cache) <= self.max_size:
            return
        
        to_evict = len(self.cache) - self.max_size
        evicted = 0
        
        if self.eviction_policy == 'LRU':
            # Sort by access time and evict least recently used
            sorted_keys = sorted(
                self.cache.keys(),
                key=lambda k: self.access_order.get(k, 0)
            )
            for key in sorted_keys[:to_evict]:
                del self.cache[key]
                if key in self.access_order:
                    del self.access_order[key]
                evicted += 1
        else:  # FIFO
            # Evict oldest entries (first keys added)
            keys = list(self.cache.keys())
            for key in keys[:to_evict]:
                del self.cache[key]
                if key in self.access_order:
                    del self.access_order[key]
                evicted += 1
        
        print(f"[Cache] Evicted {evicted} entries (policy: {self.eviction_policy}, size: {len(self.cache)}/{self.max_size})")
    
    def clear_expired(self) -> None:
        """Clear all expired entries"""
        now = time.time()
        expired_keys = []
        
        for key, (_, expires_at) in self.cache.items():
            if now > expires_at:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
            if key in self.access_order:
                del self.access_order[key]
        
        print(f"[Cache] Cleared {len(expired_keys)} expired entries")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        
        return {
            'hits': self.hits,
            'misses': self.misses,
            'writes': self.writes,
            'hit_rate': hit_rate,
            'size': len(self.cache),
            'max_size': self.max_size,
            'eviction_policy': self.eviction_policy,
            'utilization_percent': (len(self.cache) / self.max_size) * 100,
        }
    
    def set_max_size(self, size: int) -> None:
        """Set max cache size"""
        self.max_size = max(1, size)
        self._evict_if_needed()
    
    def get_max_size(self) -> int:
        """Get max cache size"""
        return self.max_size
