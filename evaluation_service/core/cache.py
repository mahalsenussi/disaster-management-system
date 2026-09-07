"""
Caching layer for evaluation service
Supports in-memory cache (default) and Redis (production)
"""
import time
import json
from typing import Any, Optional
import threading

class InMemoryCache:
    """Simple in-memory cache with TTL support"""
    
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if expiry is None or time.time() < expiry:
                    return value
                else:
                    # Expired, remove it
                    del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: int = 600):
        """Set value in cache with TTL (default 10 minutes)"""
        expiry = time.time() + ttl if ttl > 0 else None
        with self._lock:
            self._cache[key] = (value, expiry)
    
    def delete(self, key: str):
        """Delete key from cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self):
        """Clear all cache"""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self):
        """Get cache statistics"""
        with self._lock:
            return {
                'size': len(self._cache),
                'keys': list(self._cache.keys())
            }

class RedisCache:
    """Redis-based cache (for production)"""
    
    def __init__(self, host='localhost', port=6379, db=0):
        try:
            import redis
            self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            self.redis.ping()
        except ImportError:
            raise ImportError("redis package not installed. Install with: pip install redis")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Redis: {e}")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache"""
        try:
            value = self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception:
            return None
    
    def set(self, key: str, value: Any, ttl: int = 600):
        """Set value in Redis cache with TTL"""
        try:
            self.redis.setex(key, ttl, json.dumps(value))
        except Exception:
            pass
    
    def delete(self, key: str):
        """Delete key from Redis cache"""
        try:
            self.redis.delete(key)
        except Exception:
            pass
    
    def clear(self):
        """Clear all cache (use with caution)"""
        try:
            self.redis.flushdb()
        except Exception:
            pass
    
    def get_stats(self):
        """Get cache statistics"""
        try:
            info = self.redis.info()
            return {
                'size': info.get('db0', {}).get('keys', 0),
                'memory_used': info.get('used_memory_human', 'N/A')
            }
        except Exception:
            return {'size': 0, 'memory_used': 'N/A'}

class Cache:
    """Cache facade - switches between in-memory and Redis"""
    
    def __init__(self, use_redis=False, redis_config=None):
        if use_redis and redis_config:
            self.cache = RedisCache(**redis_config)
        else:
            self.cache = InMemoryCache()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        return self.cache.get(key)
    
    def set(self, key: str, value: Any, ttl: int = 600):
        """Set value in cache with TTL"""
        return self.cache.set(key, value, ttl)
    
    def delete(self, key: str):
        """Delete key from cache"""
        return self.cache.delete(key)
    
    def clear(self):
        """Clear all cache"""
        return self.cache.clear()
    
    def get_stats(self):
        """Get cache statistics"""
        return self.cache.get_stats()

# Global cache instance
_cache = None

def get_cache(use_redis=False, redis_config=None):
    """Get global cache instance"""
    global _cache
    if _cache is None:
        _cache = Cache(use_redis=use_redis, redis_config=redis_config)
    return _cache
