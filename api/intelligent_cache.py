"""
Intelligent Caching System for TNA Discovery API

Implements smart caching based on API Bible best practices (Section 6.3)
"""

import logging
import time
import json
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

logger = logging.getLogger(__name__)


class IntelligentCache:
    """
    Smart caching system that respects TNA API Bible best practices
    
    Features:
    - Different TTL for static vs dynamic data
    - Cache invalidation strategies
    - Memory and disk-based caching
    - Cache statistics and monitoring
    """
    
    def __init__(self, cache_dir: str = "data/cache"):
        """
        Initialize intelligent cache
        
        Args:
            cache_dir: Directory for cache storage
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache TTL settings (API Bible Section 6.3)
        self.static_cache_ttl = 86400  # 24 hours for static data (repositories, creators)
        self.dynamic_cache_ttl = 3600  # 1 hour for search results
        self.record_cache_ttl = 7200   # 2 hours for individual records
        
        # Memory cache for frequently accessed items
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.memory_cache_max_size = 1000
        
        # Cache statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'invalidations': 0,
            'memory_hits': 0,
            'disk_hits': 0
        }
        
        # Initialize disk cache database
        self._init_cache_db()
        
        logger.info(f"Initialized IntelligentCache at {cache_dir}")
    
    def _init_cache_db(self):
        """Initialize SQLite database for persistent cache"""
        cache_db_path = self.cache_dir / "cache.db"
        
        with sqlite3.connect(cache_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    ttl INTEGER NOT NULL,
                    cache_type TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed REAL DEFAULT 0
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_created_ttl 
                ON cache_entries(created_at, ttl)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_type 
                ON cache_entries(cache_type)
            """)
            
            conn.commit()
    
    def _generate_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """Generate a unique cache key for endpoint and parameters"""
        # Sort parameters for consistent key generation
        sorted_params = json.dumps(params, sort_keys=True)
        key_data = f"{endpoint}:{sorted_params}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _determine_cache_type(self, endpoint: str, params: Dict[str, Any]) -> str:
        """Determine cache type and TTL based on endpoint"""
        if 'repository' in endpoint:
            return 'static'
        elif 'fileauthorities' in endpoint:
            return 'static'
        elif 'records/v1/details' in endpoint:
            return 'record'
        elif 'search' in endpoint:
            # Complex queries get longer cache time
            query = params.get('sps.searchQuery', '')
            if len(query) > 50:  # Complex query
                return 'complex_search'
            return 'dynamic'
        else:
            return 'dynamic'
    
    def _get_ttl_for_type(self, cache_type: str) -> int:
        """Get TTL based on cache type"""
        ttl_mapping = {
            'static': self.static_cache_ttl,
            'record': self.record_cache_ttl,
            'dynamic': self.dynamic_cache_ttl,
            'complex_search': self.dynamic_cache_ttl * 2  # Cache complex searches longer
        }
        return ttl_mapping.get(cache_type, self.dynamic_cache_ttl)
    
    def should_cache(self, endpoint: str, params: Dict[str, Any]) -> bool:
        """
        Determine if a request should be cached
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            
        Returns:
            True if should be cached
        """
        # Always cache repository and creator info (static data)
        if 'repository' in endpoint or 'fileauthorities' in endpoint:
            return True
        
        # Cache individual record lookups
        if 'records/v1/details' in endpoint:
            return True
        
        # Cache search results with substantial queries
        if 'search' in endpoint:
            query = params.get('sps.searchQuery', '')
            # Cache non-trivial searches
            if len(query) > 10:
                return True
        
        # Cache context and children endpoints
        if 'context' in endpoint or 'children' in endpoint:
            return True
        
        return False
    
    def get(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get cached data if available and valid
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            
        Returns:
            Cached data or None if not found/expired
        """
        if not self.should_cache(endpoint, params):
            return None
        
        cache_key = self._generate_cache_key(endpoint, params)
        current_time = time.time()
        
        # Check memory cache first
        if cache_key in self.memory_cache:
            entry = self.memory_cache[cache_key]
            if current_time - entry['created_at'] < entry['ttl']:
                self.stats['hits'] += 1
                self.stats['memory_hits'] += 1
                entry['last_accessed'] = current_time
                logger.debug(f"Memory cache hit for {endpoint}")
                return entry['data']
            else:
                # Expired, remove from memory
                del self.memory_cache[cache_key]
        
        # Check disk cache
        cache_db_path = self.cache_dir / "cache.db"
        
        try:
            with sqlite3.connect(cache_db_path) as conn:
                cursor = conn.execute(
                    "SELECT data, created_at, ttl FROM cache_entries WHERE cache_key = ?",
                    (cache_key,)
                )
                row = cursor.fetchone()
                
                if row:
                    data_json, created_at, ttl = row
                    
                    # Check if expired
                    if current_time - created_at < ttl:
                        # Valid cache entry
                        data = json.loads(data_json)
                        
                        # Update access statistics
                        conn.execute(
                            "UPDATE cache_entries SET access_count = access_count + 1, last_accessed = ? WHERE cache_key = ?",
                            (current_time, cache_key)
                        )
                        
                        # Add to memory cache if space available
                        if len(self.memory_cache) < self.memory_cache_max_size:
                            self.memory_cache[cache_key] = {
                                'data': data,
                                'created_at': created_at,
                                'ttl': ttl,
                                'last_accessed': current_time
                            }
                        
                        self.stats['hits'] += 1
                        self.stats['disk_hits'] += 1
                        logger.debug(f"Disk cache hit for {endpoint}")
                        return data
                    else:
                        # Expired, delete
                        conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (cache_key,))
                        conn.commit()
        
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
        
        self.stats['misses'] += 1
        return None
    
    def put(self, endpoint: str, params: Dict[str, Any], data: Dict[str, Any]):
        """
        Store data in cache
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            data: Response data to cache
        """
        if not self.should_cache(endpoint, params):
            return
        
        cache_key = self._generate_cache_key(endpoint, params)
        cache_type = self._determine_cache_type(endpoint, params)
        ttl = self._get_ttl_for_type(cache_type)
        current_time = time.time()
        
        try:
            # Store in disk cache
            cache_db_path = self.cache_dir / "cache.db"
            data_json = json.dumps(data)
            
            with sqlite3.connect(cache_db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cache_entries 
                    (cache_key, data, created_at, ttl, cache_type, last_accessed)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (cache_key, data_json, current_time, ttl, cache_type, current_time)
                )
                conn.commit()
            
            # Store in memory cache if space available
            if len(self.memory_cache) < self.memory_cache_max_size:
                self.memory_cache[cache_key] = {
                    'data': data,
                    'created_at': current_time,
                    'ttl': ttl,
                    'last_accessed': current_time
                }
            
            logger.debug(f"Cached {cache_type} data for {endpoint} (TTL: {ttl}s)")
            
        except Exception as e:
            logger.warning(f"Cache write error: {e}")
    
    def invalidate(self, pattern: Optional[str] = None):
        """
        Invalidate cache entries
        
        Args:
            pattern: Optional pattern to match for selective invalidation
        """
        try:
            cache_db_path = self.cache_dir / "cache.db"
            
            with sqlite3.connect(cache_db_path) as conn:
                if pattern:
                    # Selective invalidation based on endpoint pattern
                    cursor = conn.execute(
                        "SELECT cache_key FROM cache_entries WHERE cache_key LIKE ?",
                        (f"%{pattern}%",)
                    )
                    keys_to_delete = [row[0] for row in cursor.fetchall()]
                    
                    for key in keys_to_delete:
                        conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (key,))
                        if key in self.memory_cache:
                            del self.memory_cache[key]
                    
                    conn.commit()
                    self.stats['invalidations'] += len(keys_to_delete)
                    logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
                else:
                    # Clear all cache
                    conn.execute("DELETE FROM cache_entries")
                    conn.commit()
                    self.memory_cache.clear()
                    self.stats['invalidations'] += 1
                    logger.info("Cleared all cache entries")
                    
        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
    
    def cleanup_expired(self):
        """Remove expired cache entries"""
        try:
            current_time = time.time()
            cache_db_path = self.cache_dir / "cache.db"
            
            with sqlite3.connect(cache_db_path) as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM cache_entries WHERE (created_at + ttl) < ?",
                    (current_time,)
                )
                expired_count = cursor.fetchone()[0]
                
                if expired_count > 0:
                    conn.execute(
                        "DELETE FROM cache_entries WHERE (created_at + ttl) < ?",
                        (current_time,)
                    )
                    conn.commit()
                    logger.info(f"Cleaned up {expired_count} expired cache entries")
            
            # Clean memory cache
            expired_keys = []
            for key, entry in self.memory_cache.items():
                if current_time - entry['created_at'] >= entry['ttl']:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.memory_cache[key]
                
        except Exception as e:
            logger.warning(f"Cache cleanup error: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        try:
            cache_db_path = self.cache_dir / "cache.db"
            
            with sqlite3.connect(cache_db_path) as conn:
                # Total entries
                cursor = conn.execute("SELECT COUNT(*) FROM cache_entries")
                total_entries = cursor.fetchone()[0]
                
                # Entries by type
                cursor = conn.execute(
                    "SELECT cache_type, COUNT(*) FROM cache_entries GROUP BY cache_type"
                )
                entries_by_type = dict(cursor.fetchall())
                
                # Cache sizes
                cursor = conn.execute("SELECT SUM(LENGTH(data)) FROM cache_entries")
                disk_size = cursor.fetchone()[0] or 0
                
            memory_size = sum(len(json.dumps(entry['data'])) for entry in self.memory_cache.values())
            
            # Calculate hit rate
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'performance': {
                    'hit_rate_percent': round(hit_rate, 2),
                    'total_requests': total_requests,
                    'cache_hits': self.stats['hits'],
                    'cache_misses': self.stats['misses'],
                    'memory_hits': self.stats['memory_hits'],
                    'disk_hits': self.stats['disk_hits'],
                    'invalidations': self.stats['invalidations']
                },
                'storage': {
                    'total_entries': total_entries,
                    'memory_entries': len(self.memory_cache),
                    'disk_size_bytes': disk_size,
                    'memory_size_bytes': memory_size,
                    'entries_by_type': entries_by_type
                },
                'configuration': {
                    'static_ttl_hours': self.static_cache_ttl / 3600,
                    'dynamic_ttl_hours': self.dynamic_cache_ttl / 3600,
                    'record_ttl_hours': self.record_cache_ttl / 3600,
                    'memory_cache_max_size': self.memory_cache_max_size
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting cache statistics: {e}")
            return {'error': str(e)}


# Global cache instance
_cache_instance: Optional[IntelligentCache] = None


def get_intelligent_cache() -> IntelligentCache:
    """Get or create global cache instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = IntelligentCache()
    return _cache_instance


def cache_enabled_request(client_method, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrapper function to add caching to API client methods
    
    Args:
        client_method: The API client method to call
        endpoint: API endpoint
        params: Request parameters
        
    Returns:
        API response data (from cache or fresh request)
    """
    cache = get_intelligent_cache()
    
    # Try to get from cache first
    cached_data = cache.get(endpoint, params)
    if cached_data is not None:
        return cached_data
    
    # Not in cache, make request
    try:
        response_data = client_method(endpoint, params)
        
        # Cache the response
        cache.put(endpoint, params, response_data)
        
        return response_data
        
    except Exception as e:
        logger.error(f"Request failed for {endpoint}: {e}")
        raise
