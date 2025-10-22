"""
Cursor-Based Pagination for National Archives Discovery API

Implements efficient pagination for large datasets using cursor-based approach
instead of offset-based pagination to avoid performance degradation
"""

import logging
import time
from typing import List, Dict, Any, Optional, Tuple, Iterator, NamedTuple
from dataclasses import dataclass
import json
import sqlite3
from datetime import datetime
import base64

from api.models import Record

logger = logging.getLogger(__name__)


class PaginationCursor(NamedTuple):
    """
    Cursor for pagination state
    
    Contains the last seen values for ordering columns
    """
    timestamp: str  # ISO timestamp of last record
    record_id: str  # ID of last record for tie-breaking
    direction: str = "forward"  # forward or backward
    
    def encode(self) -> str:
        """Encode cursor to base64 string for URL safety"""
        cursor_data = {
            "timestamp": self.timestamp,
            "record_id": self.record_id,
            "direction": self.direction
        }
        json_str = json.dumps(cursor_data, separators=(',', ':'))
        return base64.urlsafe_b64encode(json_str.encode()).decode()
    
    @classmethod
    def decode(cls, cursor_string: str) -> 'PaginationCursor':
        """Decode cursor from base64 string"""
        try:
            json_str = base64.urlsafe_b64decode(cursor_string.encode()).decode()
            cursor_data = json.loads(json_str)
            return cls(**cursor_data)
        except Exception as e:
            logger.error(f"Failed to decode cursor: {e}")
            raise ValueError(f"Invalid cursor: {cursor_string}")


@dataclass
class PaginationResult:
    """Result of a paginated query"""
    records: List[Record]
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    has_next: bool = False
    has_prev: bool = False
    total_count: Optional[int] = None
    page_info: Dict[str, Any] = None


class CursorPaginator:
    """
    High-performance cursor-based paginator for large datasets
    
    Advantages over offset-based pagination:
    - Consistent performance regardless of page depth
    - No duplicate/missing records during concurrent insertions
    - Stable pagination for real-time data
    - Efficient database queries with indexed columns
    """
    
    def __init__(self, database_path: str = "data/discovery.db"):
        """
        Initialize cursor paginator
        
        Args:
            database_path: Path to SQLite database
        """
        self.database_path = database_path
        self.default_page_size = 50
        self.max_page_size = 1000
        
        logger.info("Initialized cursor-based paginator")
    
    def paginate_records(self, 
                        page_size: int = None,
                        cursor: Optional[str] = None,
                        filters: Optional[Dict[str, Any]] = None,
                        order_by: str = "created_at",
                        order_direction: str = "DESC") -> PaginationResult:
        """
        Paginate records using cursor-based approach
        
        Args:
            page_size: Number of records per page
            cursor: Pagination cursor from previous request
            filters: Optional filters to apply
            order_by: Column to order by (must be indexed)
            order_direction: ASC or DESC
            
        Returns:
            PaginationResult with records and navigation info
        """
        page_size = min(page_size or self.default_page_size, self.max_page_size)
        
        # Parse cursor if provided
        cursor_obj = None
        if cursor:
            try:
                cursor_obj = PaginationCursor.decode(cursor)
            except ValueError as e:
                logger.warning(f"Invalid cursor provided: {e}")
                cursor_obj = None
        
        # Build query
        query_parts = self._build_cursor_query(
            cursor_obj, filters, order_by, order_direction, page_size
        )
        
        # Execute query
        with sqlite3.connect(self.database_path) as conn:
            conn.row_factory = sqlite3.Row
            
            cursor_db = conn.execute(query_parts['sql'], query_parts['params'])
            rows = cursor_db.fetchall()
            
            # Convert to Record objects
            records = []
            for row in rows:
                try:
                    record = self._row_to_record(dict(row))
                    records.append(record)
                except Exception as e:
                    logger.warning(f"Failed to parse record: {e}")
                    continue
            
            # Determine navigation state
            has_next = len(records) == page_size
            has_prev = cursor_obj is not None
            
            # Generate next/prev cursors
            next_cursor = None
            prev_cursor = None
            
            if records:
                if has_next:
                    last_record = records[-1]
                    next_cursor = PaginationCursor(
                        timestamp=last_record.created_at or datetime.now().isoformat(),
                        record_id=last_record.id,
                        direction="forward"
                    ).encode()
                
                if has_prev:
                    first_record = records[0]
                    prev_cursor = PaginationCursor(
                        timestamp=first_record.created_at or datetime.now().isoformat(),
                        record_id=first_record.id,
                        direction="backward"
                    ).encode()
            
            # Get total count (expensive operation - cache this)
            total_count = self._get_total_count(conn, filters)
            
            return PaginationResult(
                records=records,
                next_cursor=next_cursor,
                prev_cursor=prev_cursor,
                has_next=has_next,
                has_prev=has_prev,
                total_count=total_count,
                page_info={
                    'page_size': page_size,
                    'actual_count': len(records),
                    'order_by': order_by,
                    'order_direction': order_direction
                }
            )
    
    def _build_cursor_query(self, 
                           cursor: Optional[PaginationCursor],
                           filters: Optional[Dict[str, Any]],
                           order_by: str,
                           order_direction: str,
                           page_size: int) -> Dict[str, Any]:
        """Build SQL query with cursor-based pagination"""
        
        # Base query
        sql_parts = ["SELECT * FROM records"]
        params = []
        where_conditions = []
        
        # Apply filters
        if filters:
            for key, value in filters.items():
                if key in ['archive', 'collection', 'level']:
                    where_conditions.append(f"{key} = ?")
                    params.append(value)
                elif key == 'date_from_after':
                    where_conditions.append("date_from >= ?")
                    params.append(value)
                elif key == 'date_to_before':
                    where_conditions.append("date_to <= ?")
                    params.append(value)
                elif key == 'title_contains':
                    where_conditions.append("title LIKE ?")
                    params.append(f"%{value}%")
        
        # Apply cursor-based pagination
        if cursor:
            if cursor.direction == "forward":
                if order_direction == "DESC":
                    # For DESC ordering, we want records with timestamp < cursor_timestamp
                    # or (timestamp = cursor_timestamp AND id < cursor_id)
                    cursor_condition = f"""
                        ({order_by} < ? OR ({order_by} = ? AND id < ?))
                    """
                    params.extend([cursor.timestamp, cursor.timestamp, cursor.record_id])
                else:
                    # For ASC ordering, we want records with timestamp > cursor_timestamp
                    cursor_condition = f"""
                        ({order_by} > ? OR ({order_by} = ? AND id > ?))
                    """
                    params.extend([cursor.timestamp, cursor.timestamp, cursor.record_id])
                
                where_conditions.append(cursor_condition)
            
            elif cursor.direction == "backward":
                # Reverse the logic for backward pagination
                if order_direction == "DESC":
                    cursor_condition = f"""
                        ({order_by} > ? OR ({order_by} = ? AND id > ?))
                    """
                    params.extend([cursor.timestamp, cursor.timestamp, cursor.record_id])
                else:
                    cursor_condition = f"""
                        ({order_by} < ? OR ({order_by} = ? AND id < ?))
                    """
                    params.extend([cursor.timestamp, cursor.timestamp, cursor.record_id])
                
                where_conditions.append(cursor_condition)
                # Reverse order direction for backward pagination
                order_direction = "ASC" if order_direction == "DESC" else "DESC"
        
        # Add WHERE clause
        if where_conditions:
            sql_parts.append("WHERE " + " AND ".join(where_conditions))
        
        # Add ORDER BY
        sql_parts.append(f"ORDER BY {order_by} {order_direction}, id {order_direction}")
        
        # Add LIMIT
        sql_parts.append("LIMIT ?")
        params.append(page_size)
        
        sql = " ".join(sql_parts)
        
        return {
            'sql': sql,
            'params': params
        }
    
    def _get_total_count(self, conn: sqlite3.Connection, filters: Optional[Dict[str, Any]]) -> int:
        """Get total count with filters applied"""
        count_sql = "SELECT COUNT(*) FROM records"
        count_params = []
        where_conditions = []
        
        if filters:
            for key, value in filters.items():
                if key in ['archive', 'collection', 'level']:
                    where_conditions.append(f"{key} = ?")
                    count_params.append(value)
                elif key == 'date_from_after':
                    where_conditions.append("date_from >= ?")
                    count_params.append(value)
                elif key == 'date_to_before':
                    where_conditions.append("date_to <= ?")
                    count_params.append(value)
                elif key == 'title_contains':
                    where_conditions.append("title LIKE ?")
                    count_params.append(f"%{value}%")
        
        if where_conditions:
            count_sql += " WHERE " + " AND ".join(where_conditions)
        
        return conn.execute(count_sql, count_params).fetchone()[0]
    
    def _row_to_record(self, row_dict: Dict[str, Any]) -> Record:
        """Convert database row to Record object"""
        # Import here to avoid circular imports
        from storage.database import DatabaseManager
        
        # Use the existing method from DatabaseManager
        db_manager = DatabaseManager()
        return db_manager._row_to_record(row_dict)
    
    def paginate_search_results(self,
                               query: str,
                               page_size: int = None,
                               cursor: Optional[str] = None) -> PaginationResult:
        """
        Paginate full-text search results
        
        Args:
            query: Search query
            page_size: Number of records per page
            cursor: Pagination cursor
            
        Returns:
            PaginationResult with search results
        """
        page_size = min(page_size or self.default_page_size, self.max_page_size)
        
        # Parse cursor
        cursor_obj = None
        if cursor:
            try:
                cursor_obj = PaginationCursor.decode(cursor)
            except ValueError:
                cursor_obj = None
        
        # Build FTS query with cursor
        sql_parts = ["""
            SELECT r.* FROM records r
            JOIN records_fts fts ON r.rowid = fts.rowid
            WHERE records_fts MATCH ?
        """]
        params = [query]
        
        # Apply cursor pagination
        if cursor_obj:
            if cursor_obj.direction == "forward":
                cursor_condition = "(r.created_at < ? OR (r.created_at = ? AND r.id < ?))"
                params.extend([cursor_obj.timestamp, cursor_obj.timestamp, cursor_obj.record_id])
            else:
                cursor_condition = "(r.created_at > ? OR (r.created_at = ? AND r.id > ?))"
                params.extend([cursor_obj.timestamp, cursor_obj.timestamp, cursor_obj.record_id])
            
            sql_parts.append(f"AND {cursor_condition}")
        
        # Order and limit
        sql_parts.extend([
            "ORDER BY r.created_at DESC, r.id DESC",
            "LIMIT ?"
        ])
        params.append(page_size)
        
        sql = " ".join(sql_parts)
        
        # Execute query
        with sqlite3.connect(self.database_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor_db = conn.execute(sql, params)
            rows = cursor_db.fetchall()
            
            # Convert to records
            records = []
            for row in rows:
                try:
                    record = self._row_to_record(dict(row))
                    records.append(record)
                except Exception as e:
                    logger.warning(f"Failed to parse search result: {e}")
                    continue
            
            # Navigation state
            has_next = len(records) == page_size
            has_prev = cursor_obj is not None
            
            # Generate cursors
            next_cursor = None
            prev_cursor = None
            
            if records:
                if has_next:
                    last_record = records[-1]
                    next_cursor = PaginationCursor(
                        timestamp=last_record.created_at or datetime.now().isoformat(),
                        record_id=last_record.id,
                        direction="forward"
                    ).encode()
                
                if has_prev:
                    first_record = records[0]
                    prev_cursor = PaginationCursor(
                        timestamp=first_record.created_at or datetime.now().isoformat(),
                        record_id=first_record.id,
                        direction="backward"
                    ).encode()
            
            return PaginationResult(
                records=records,
                next_cursor=next_cursor,
                prev_cursor=prev_cursor,
                has_next=has_next,
                has_prev=has_prev,
                page_info={
                    'page_size': page_size,
                    'actual_count': len(records),
                    'query': query,
                    'type': 'search'
                }
            )


class PaginationCache:
    """Cache for pagination metadata to improve performance"""
    
    def __init__(self, cache_ttl: int = 300):  # 5 minutes
        self.cache = {}
        self.cache_ttl = cache_ttl
    
    def get_cached_count(self, cache_key: str) -> Optional[int]:
        """Get cached total count"""
        if cache_key in self.cache:
            count, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return count
            else:
                del self.cache[cache_key]
        return None
    
    def cache_count(self, cache_key: str, count: int):
        """Cache total count"""
        self.cache[cache_key] = (count, time.time())
    
    def clear_cache(self):
        """Clear all cached counts"""
        self.cache.clear()


# Convenience functions

def paginate_all_records(page_size: int = 50, 
                        cursor: Optional[str] = None,
                        filters: Optional[Dict[str, Any]] = None) -> PaginationResult:
    """
    Convenience function to paginate all records
    
    Args:
        page_size: Records per page
        cursor: Pagination cursor
        filters: Optional filters
        
    Returns:
        PaginationResult
    """
    paginator = CursorPaginator()
    return paginator.paginate_records(page_size, cursor, filters)


def paginate_search(query: str,
                   page_size: int = 50,
                   cursor: Optional[str] = None) -> PaginationResult:
    """
    Convenience function to paginate search results
    
    Args:
        query: Search query
        page_size: Records per page
        cursor: Pagination cursor
        
    Returns:
        PaginationResult
    """
    paginator = CursorPaginator()
    return paginator.paginate_search_results(query, page_size, cursor)


def iterate_all_records(filters: Optional[Dict[str, Any]] = None,
                       page_size: int = 100) -> Iterator[Record]:
    """
    Iterator to process all records efficiently
    
    Args:
        filters: Optional filters
        page_size: Records per page
        
    Yields:
        Individual Record objects
    """
    paginator = CursorPaginator()
    cursor = None
    
    while True:
        result = paginator.paginate_records(page_size, cursor, filters)
        
        for record in result.records:
            yield record
        
        if not result.has_next:
            break
        
        cursor = result.next_cursor


def get_page_navigation(current_cursor: Optional[str],
                       total_pages: Optional[int] = None) -> Dict[str, Any]:
    """
    Generate navigation information for UI
    
    Args:
        current_cursor: Current page cursor
        total_pages: Total number of pages (if known)
        
    Returns:
        Navigation information
    """
    nav_info = {
        'current_cursor': current_cursor,
        'has_cursor': current_cursor is not None,
        'total_pages': total_pages
    }
    
    if current_cursor:
        try:
            cursor_obj = PaginationCursor.decode(current_cursor)
            nav_info['cursor_info'] = {
                'timestamp': cursor_obj.timestamp,
                'record_id': cursor_obj.record_id,
                'direction': cursor_obj.direction
            }
        except ValueError:
            nav_info['cursor_info'] = None
    
    return nav_info
