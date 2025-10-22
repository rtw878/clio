"""
Intelligent caching layer that respects National Archives API policies
"""

import hashlib
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import sqlite3

from api.models import SearchResult

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages caching of API responses while respecting TNA policies
    
    Note: The National Archives advises against long-term caching of API content
    as the service is under development. This cache is designed for short-term
    efficiency within a session while still respecting their guidelines.
    """
    
    def __init__(self, db_path: str = "./data/discovery.db", cache_ttl_hours: int = 1):
        """
        Initialize cache manager
        
        Args:
            db_path: Path to SQLite database
            cache_ttl_hours: Time-to-live for cache entries in hours (default: 1)
        """
        self.db_path = db_path
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        
        logger.info(f"Cache manager initialized with {cache_ttl_hours}h TTL")

    def _generate_cache_key(self, query: str, filters: Optional[Dict] = None) -> str:
        """
        Generate a unique cache key for a query
        
        Args:
            query: Search query string
            filters: Additional search filters
            
        Returns:
            MD5 hash as cache key
        """
        cache_data = {
            'query': query.strip().lower(),
            'filters': filters or {}
        }
        
        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_string.encode()).hexdigest()

    def get_cached_search(self, 
                         query: str, 
                         filters: Optional[Dict] = None) -> Optional[SearchResult]:
        """
        Retrieve cached search results if available and not expired
        
        Args:
            query: Search query
            filters: Search filters
            
        Returns:
            SearchResult if found and valid, None otherwise
        """
        cache_key = self._generate_cache_key(query, filters)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                cursor = conn.execute("""
                    SELECT results_json, created_at, expires_at 
                    FROM search_cache 
                    WHERE query_hash = ?
                """, (cache_key,))
                
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                # Check if cache entry has expired
                expires_at = datetime.fromisoformat(row['expires_at'])
                if datetime.now() > expires_at:
                    # Clean up expired entry
                    conn.execute("DELETE FROM search_cache WHERE query_hash = ?", (cache_key,))
                    conn.commit()
                    return None
                
                # Deserialize cached results
                results_data = json.loads(row['results_json'])
                
                # Reconstruct SearchResult object
                from api.models import Record
                
                records = [Record.from_api_response(r) for r in results_data['records']]
                
                search_result = SearchResult(
                    records=records,
                    total_results=results_data['total_results'],
                    page=results_data['page'],
                    per_page=results_data['per_page'],
                    total_pages=results_data['total_pages'],
                    query=results_data['query'],
                    facets=results_data.get('facets', {})
                )
                
                logger.debug(f"Cache hit for query: {query}")
                return search_result
                
        except (sqlite3.Error, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to retrieve cached search for '{query}': {e}")
            return None

    def cache_search_results(self, 
                           query: str,
                           search_result: SearchResult,
                           filters: Optional[Dict] = None):
        """
        Cache search results for future use
        
        Args:
            query: Search query
            search_result: SearchResult to cache
            filters: Search filters used
        """
        cache_key = self._generate_cache_key(query, filters)
        
        try:
            # Serialize search results
            results_data = {
                'records': [record.to_dict() for record in search_result.records],
                'total_results': search_result.total_results,
                'page': search_result.page,
                'per_page': search_result.per_page,
                'total_pages': search_result.total_pages,
                'query': search_result.query,
                'facets': search_result.facets
            }
            
            results_json = json.dumps(results_data)
            
            # Calculate expiry time
            expires_at = datetime.now() + self.cache_ttl
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO search_cache 
                    (query_hash, query, results_json, total_results, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    cache_key,
                    query,
                    results_json,
                    search_result.total_results,
                    expires_at.isoformat()
                ))
                
                conn.commit()
                
                logger.debug(f"Cached search results for query: {query}")
                
        except (sqlite3.Error, json.JSONEncodeError) as e:
            logger.warning(f"Failed to cache search results for '{query}': {e}")

    def invalidate_cache(self, query: Optional[str] = None):
        """
        Invalidate cache entries
        
        Args:
            query: Specific query to invalidate (None to clear all)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                if query:
                    cache_key = self._generate_cache_key(query)
                    conn.execute("DELETE FROM search_cache WHERE query_hash = ?", (cache_key,))
                    logger.info(f"Invalidated cache for query: {query}")
                else:
                    conn.execute("DELETE FROM search_cache")
                    logger.info("Cleared all cache entries")
                
                conn.commit()
                
        except sqlite3.Error as e:
            logger.error(f"Failed to invalidate cache: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                stats = {}
                
                # Total cached queries
                cursor = conn.execute("SELECT COUNT(*) FROM search_cache")
                stats['total_entries'] = cursor.fetchone()[0]
                
                # Active (non-expired) entries
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM search_cache 
                    WHERE expires_at > ?
                """, (datetime.now().isoformat(),))
                stats['active_entries'] = cursor.fetchone()[0]
                
                # Cache size
                cursor = conn.execute("""
                    SELECT SUM(LENGTH(results_json)) FROM search_cache
                """)
                size_bytes = cursor.fetchone()[0] or 0
                stats['size_mb'] = round(size_bytes / (1024 * 1024), 2)
                
                # Most cached queries
                cursor = conn.execute("""
                    SELECT query, COUNT(*) as cache_count
                    FROM search_cache
                    GROUP BY query
                    ORDER BY cache_count DESC
                    LIMIT 10
                """)
                stats['popular_queries'] = [
                    {'query': row[0], 'count': row[1]} 
                    for row in cursor.fetchall()
                ]
                
                return stats
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return {}

    def cleanup_expired_cache(self):
        """Remove expired cache entries"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM search_cache 
                    WHERE expires_at < ?
                """, (datetime.now().isoformat(),))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired cache entries")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to cleanup expired cache: {e}")

    def get_cached_queries(self) -> List[str]:
        """
        Get list of currently cached queries
        
        Returns:
            List of cached query strings
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT DISTINCT query FROM search_cache 
                    WHERE expires_at > ?
                    ORDER BY created_at DESC
                """, (datetime.now().isoformat(),))
                
                return [row[0] for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get cached queries: {e}")
            return []
