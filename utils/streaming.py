"""
Memory-Efficient Streaming Processing for National Archives Discovery API

Implements streaming data processing to handle large datasets without memory overflow
"""

import logging
import time
from typing import Iterator, Dict, Any, List, Optional, Callable, Generator
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from contextlib import contextmanager
import gc

from api.models import Record
from api.client import DiscoveryClient

logger = logging.getLogger(__name__)


@dataclass
class StreamingConfig:
    """Configuration for streaming operations"""
    chunk_size: int = 100  # Records per chunk
    memory_limit_mb: int = 500  # Max memory usage in MB
    gc_frequency: int = 10  # Garbage collection every N chunks
    flush_frequency: int = 50  # Database flush every N chunks
    progress_callback: Optional[Callable[[int, int], None]] = None


class MemoryMonitor:
    """Monitor and manage memory usage during streaming operations"""
    
    def __init__(self, limit_mb: int = 500):
        self.limit_bytes = limit_mb * 1024 * 1024
        self.peak_usage = 0
        
    def check_memory(self) -> Dict[str, Any]:
        """Check current memory usage"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        current_usage = memory_info.rss
        self.peak_usage = max(self.peak_usage, current_usage)
        
        return {
            'current_mb': current_usage / 1024 / 1024,
            'peak_mb': self.peak_usage / 1024 / 1024,
            'limit_mb': self.limit_bytes / 1024 / 1024,
            'usage_percent': (current_usage / self.limit_bytes) * 100,
            'at_limit': current_usage > self.limit_bytes
        }
    
    def force_gc_if_needed(self, threshold_percent: float = 80.0) -> bool:
        """Force garbage collection if memory usage is high"""
        memory_info = self.check_memory()
        
        if memory_info['usage_percent'] > threshold_percent:
            logger.info(f"Memory usage at {memory_info['usage_percent']:.1f}%, forcing garbage collection")
            gc.collect()
            return True
        return False


class StreamingRecordProcessor:
    """
    Process large numbers of records with memory-efficient streaming
    
    Features:
    - Chunked processing to prevent memory overflow
    - Automatic garbage collection
    - Progress tracking and callbacks
    - Database transaction management
    - Error recovery and resumption
    """
    
    def __init__(self, 
                 config: StreamingConfig = None,
                 database_path: str = "data/discovery.db"):
        """
        Initialize streaming processor
        
        Args:
            config: Streaming configuration
            database_path: Path to SQLite database
        """
        self.config = config or StreamingConfig()
        self.database_path = database_path
        self.memory_monitor = MemoryMonitor(self.config.memory_limit_mb)
        
        # Processing statistics
        self.stats = {
            'total_processed': 0,
            'successful_chunks': 0,
            'failed_chunks': 0,
            'total_time': 0.0,
            'peak_memory_mb': 0.0,
            'gc_runs': 0
        }
        
        logger.info(f"Initialized streaming processor (chunk_size={self.config.chunk_size}, "
                   f"memory_limit={self.config.memory_limit_mb}MB)")
    
    @contextmanager
    def database_transaction(self, timeout: int = 30):
        """Context manager for database transactions with timeout"""
        conn = sqlite3.connect(self.database_path, timeout=timeout)
        conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode for better concurrency
        conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety and performance
        
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction failed: {e}")
            raise
        finally:
            conn.close()
    
    def stream_records_from_api(self, 
                               api_client: DiscoveryClient,
                               query: str,
                               max_records: Optional[int] = None) -> Generator[List[Record], None, None]:
        """
        Stream records from API in chunks
        
        Args:
            api_client: Discovery API client
            query: Search query
            max_records: Maximum records to fetch (None for unlimited)
            
        Yields:
            Lists of Record objects (chunks)
        """
        page = 0
        total_fetched = 0
        
        while True:
            if max_records and total_fetched >= max_records:
                break
            
            # Calculate how many records to fetch this page
            per_page = min(self.config.chunk_size, 
                          (max_records - total_fetched) if max_records else self.config.chunk_size)
            
            try:
                # Fetch a page of results
                search_result = api_client.search(
                    query=query,
                    page=page,
                    per_page=per_page
                )
                
                if not search_result.records:
                    logger.info("No more records available, ending stream")
                    break
                
                yield search_result.records
                
                total_fetched += len(search_result.records)
                page += 1
                
                # Check if we've reached the end
                if len(search_result.records) < per_page:
                    logger.info(f"Reached end of results (fetched {total_fetched} records)")
                    break
                
                # Memory management
                if page % self.config.gc_frequency == 0:
                    if self.memory_monitor.force_gc_if_needed():
                        self.stats['gc_runs'] += 1
                
                # Rate limiting compliance
                time.sleep(1.0)  # 1 request per second
                
            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                raise
    
    def stream_records_from_database(self, 
                                   query: Optional[str] = None,
                                   batch_size: int = None) -> Generator[List[Record], None, None]:
        """
        Stream records from database in chunks
        
        Args:
            query: SQL WHERE clause (optional)
            batch_size: Override default chunk size
            
        Yields:
            Lists of Record objects (chunks)
        """
        chunk_size = batch_size or self.config.chunk_size
        offset = 0
        
        with self.database_transaction() as conn:
            # Get total count for progress tracking
            count_sql = "SELECT COUNT(*) FROM records"
            if query:
                count_sql += f" WHERE {query}"
            
            total_records = conn.execute(count_sql).fetchone()[0]
            logger.info(f"Streaming {total_records} records from database")
            
            while offset < total_records:
                # Fetch chunk
                sql = """
                    SELECT * FROM records 
                    {} 
                    ORDER BY created_at 
                    LIMIT ? OFFSET ?
                """.format(f"WHERE {query}" if query else "")
                
                cursor = conn.execute(sql, (chunk_size, offset))
                rows = cursor.fetchall()
                
                if not rows:
                    break
                
                # Convert rows to Record objects
                records = []
                for row in rows:
                    try:
                        # Convert sqlite3.Row to dict for Record creation
                        row_dict = dict(row)
                        record = self._row_to_record(row_dict)
                        records.append(record)
                    except Exception as e:
                        logger.warning(f"Failed to parse record at offset {offset}: {e}")
                        continue
                
                yield records
                
                offset += len(rows)
                
                # Progress callback
                if self.config.progress_callback:
                    self.config.progress_callback(offset, total_records)
                
                # Memory management
                if (offset // chunk_size) % self.config.gc_frequency == 0:
                    if self.memory_monitor.force_gc_if_needed():
                        self.stats['gc_runs'] += 1
    
    def _row_to_record(self, row_dict: Dict[str, Any]) -> Record:
        """Convert database row to Record object"""
        # Import here to avoid circular imports
        from storage.database import DatabaseManager
        
        # Use the existing method from DatabaseManager
        db_manager = DatabaseManager()
        return db_manager._row_to_record(row_dict)
    
    def process_stream(self, 
                      record_stream: Generator[List[Record], None, None],
                      processor_func: Callable[[List[Record]], Dict[str, Any]],
                      output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a stream of record chunks with a custom processor function
        
        Args:
            record_stream: Generator yielding record chunks
            processor_func: Function to process each chunk
            output_path: Optional output file path
            
        Returns:
            Processing statistics
        """
        start_time = time.time()
        chunk_count = 0
        
        output_file = None
        if output_path:
            output_file = open(output_path, 'w', encoding='utf-8')
            
        try:
            for chunk in record_stream:
                chunk_count += 1
                
                try:
                    # Process the chunk
                    result = processor_func(chunk)
                    
                    # Write to output file if provided
                    if output_file and result:
                        json.dump(result, output_file)
                        output_file.write('\n')
                        output_file.flush()
                    
                    self.stats['successful_chunks'] += 1
                    self.stats['total_processed'] += len(chunk)
                    
                    # Memory monitoring
                    memory_info = self.memory_monitor.check_memory()
                    self.stats['peak_memory_mb'] = max(
                        self.stats['peak_memory_mb'], 
                        memory_info['current_mb']
                    )
                    
                    # Progress logging
                    if chunk_count % 10 == 0:
                        logger.info(f"Processed {chunk_count} chunks, "
                                  f"{self.stats['total_processed']} total records, "
                                  f"memory: {memory_info['current_mb']:.1f}MB")
                    
                    # Force garbage collection if needed
                    if chunk_count % self.config.gc_frequency == 0:
                        if self.memory_monitor.force_gc_if_needed():
                            self.stats['gc_runs'] += 1
                
                except Exception as e:
                    logger.error(f"Error processing chunk {chunk_count}: {e}")
                    self.stats['failed_chunks'] += 1
                    continue
        
        finally:
            if output_file:
                output_file.close()
        
        self.stats['total_time'] = time.time() - start_time
        
        logger.info(f"Streaming processing complete: "
                   f"{self.stats['total_processed']} records in {self.stats['total_time']:.1f}s, "
                   f"peak memory: {self.stats['peak_memory_mb']:.1f}MB")
        
        return self.stats.copy()
    
    def bulk_transform_records(self, 
                             transform_func: Callable[[Record], Dict[str, Any]],
                             query: Optional[str] = None,
                             output_format: str = "jsonl") -> str:
        """
        Apply a transformation to all records in streaming fashion
        
        Args:
            transform_func: Function to transform each record
            query: Optional SQL WHERE clause to filter records
            output_format: Output format (jsonl, csv, xml)
            
        Returns:
            Path to output file
        """
        timestamp = int(time.time())
        output_path = f"data/exports/bulk_transform_{timestamp}.{output_format}"
        Path(output_path).parent.mkdir(exist_ok=True)
        
        def chunk_processor(records: List[Record]) -> Dict[str, Any]:
            """Process a chunk of records"""
            transformed = []
            for record in records:
                try:
                    result = transform_func(record)
                    if result:
                        transformed.append(result)
                except Exception as e:
                    logger.warning(f"Failed to transform record {record.id}: {e}")
            
            return {'transformed_count': len(transformed), 'data': transformed}
        
        # Create record stream from database
        record_stream = self.stream_records_from_database(query)
        
        # Process the stream
        stats = self.process_stream(record_stream, chunk_processor, output_path)
        
        logger.info(f"Bulk transformation complete: {output_path}")
        return output_path
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics"""
        memory_info = self.memory_monitor.check_memory()
        
        return {
            **self.stats,
            'current_memory_mb': memory_info['current_mb'],
            'memory_limit_mb': self.config.memory_limit_mb,
            'config': {
                'chunk_size': self.config.chunk_size,
                'memory_limit_mb': self.config.memory_limit_mb,
                'gc_frequency': self.config.gc_frequency,
                'flush_frequency': self.config.flush_frequency
            }
        }


# Convenience functions for common streaming operations

def stream_large_search(api_client: DiscoveryClient, 
                       query: str, 
                       max_records: int = 10000,
                       chunk_size: int = 100) -> Generator[List[Record], None, None]:
    """
    Convenience function for streaming large search results
    
    Args:
        api_client: Discovery API client
        query: Search query
        max_records: Maximum records to fetch
        chunk_size: Records per chunk
        
    Yields:
        Record chunks
    """
    config = StreamingConfig(chunk_size=chunk_size)
    processor = StreamingRecordProcessor(config)
    
    yield from processor.stream_records_from_api(api_client, query, max_records)


def export_records_streaming(query: Optional[str] = None,
                           output_format: str = "jsonl",
                           chunk_size: int = 1000) -> str:
    """
    Export records in streaming fashion to prevent memory issues
    
    Args:
        query: SQL WHERE clause (optional)
        output_format: Export format
        chunk_size: Records per chunk
        
    Returns:
        Path to exported file
    """
    config = StreamingConfig(chunk_size=chunk_size)
    processor = StreamingRecordProcessor(config)
    
    def record_to_dict(record: Record) -> Dict[str, Any]:
        """Convert record to dictionary for export"""
        return record.to_dict()
    
    return processor.bulk_transform_records(record_to_dict, query, output_format)


def analyze_records_streaming(analysis_func: Callable[[List[Record]], Dict[str, Any]],
                            query: Optional[str] = None,
                            chunk_size: int = 500) -> Dict[str, Any]:
    """
    Perform analysis on large datasets using streaming
    
    Args:
        analysis_func: Function to analyze record chunks
        query: SQL WHERE clause (optional)
        chunk_size: Records per chunk
        
    Returns:
        Aggregated analysis results
    """
    config = StreamingConfig(chunk_size=chunk_size)
    processor = StreamingRecordProcessor(config)
    
    record_stream = processor.stream_records_from_database(query, chunk_size)
    return processor.process_stream(record_stream, analysis_func)
