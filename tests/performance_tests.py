"""
Comprehensive Performance Testing Suite for National Archives Discovery Clone

Tests system performance under various loads and conditions
"""

import logging
import time
import threading
import asyncio
import statistics
from typing import Dict, Any, List, Callable, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import psutil
import json
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a test"""
    test_name: str
    start_time: float
    end_time: float
    duration: float
    operations_count: int
    operations_per_second: float
    peak_memory_mb: float
    peak_cpu_percent: float
    database_size_before: int
    database_size_after: int
    errors: List[str] = field(default_factory=list)
    custom_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadTestConfig:
    """Configuration for load testing"""
    concurrent_users: int = 10
    operations_per_user: int = 100
    ramp_up_time: float = 5.0
    test_duration: float = 60.0
    think_time: float = 0.1


class PerformanceMonitor:
    """Monitor system performance during tests"""
    
    def __init__(self):
        self.monitoring = False
        self.metrics = []
        self.monitor_thread = None
        
    def start_monitoring(self, interval: float = 1.0):
        """Start performance monitoring"""
        self.monitoring = True
        self.metrics = []
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self.monitor_thread.start()
    
    def stop_monitoring(self) -> Dict[str, Any]:
        """Stop monitoring and return statistics"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        if not self.metrics:
            return {}
        
        cpu_values = [m['cpu_percent'] for m in self.metrics]
        memory_values = [m['memory_mb'] for m in self.metrics]
        
        return {
            'peak_cpu_percent': max(cpu_values),
            'avg_cpu_percent': statistics.mean(cpu_values),
            'peak_memory_mb': max(memory_values),
            'avg_memory_mb': statistics.mean(memory_values),
            'samples': len(self.metrics)
        }
    
    def _monitor_loop(self, interval: float):
        """Performance monitoring loop"""
        process = psutil.Process()
        
        while self.monitoring:
            try:
                cpu_percent = process.cpu_percent()
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                
                self.metrics.append({
                    'timestamp': time.time(),
                    'cpu_percent': cpu_percent,
                    'memory_mb': memory_mb
                })
                
                time.sleep(interval)
            except Exception as e:
                logger.warning(f"Monitoring error: {e}")
                break


class PerformanceTester:
    """
    Comprehensive performance testing framework
    
    Tests:
    - Database operations (CRUD)
    - API client performance
    - Search performance
    - Concurrent access
    - Memory usage
    - Large dataset handling
    """
    
    def __init__(self, database_path: str = "data/discovery.db"):
        self.database_path = database_path
        self.test_results = []
        
    def run_all_tests(self) -> List[PerformanceMetrics]:
        """Run comprehensive performance test suite"""
        logger.info("Starting comprehensive performance tests")
        
        test_methods = [
            self.test_database_operations,
            self.test_search_performance,
            self.test_api_client_performance,
            self.test_concurrent_access,
            self.test_memory_usage,
            self.test_large_dataset_handling,
            self.test_pagination_performance,
            self.test_export_performance,
            self.test_streaming_performance
        ]
        
        results = []
        for test_method in test_methods:
            try:
                result = test_method()
                results.append(result)
                logger.info(f"✅ {result.test_name}: {result.operations_per_second:.1f} ops/sec")
            except Exception as e:
                logger.error(f"❌ Test failed: {test_method.__name__}: {e}")
        
        self.test_results = results
        return results
    
    def test_database_operations(self) -> PerformanceMetrics:
        """Test basic database CRUD operations"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        operations_count = 0
        errors = []
        
        # Get initial database size
        db_size_before = self._get_database_size()
        
        try:
            from storage.database import DatabaseManager
            from api.models import Record
            
            db = DatabaseManager()
            
            # Test record insertion
            for i in range(100):
                record = Record(
                    id=f"test_{i}",
                    title=f"Test Record {i}",
                    description=f"Test description {i}",
                    reference=f"TEST/{i}",
                    archive="TEST",
                    level="Item"
                )
                
                try:
                    db.store_records([record])
                    operations_count += 1
                except Exception as e:
                    errors.append(f"Insert error: {e}")
            
            # Test record retrieval
            for i in range(50):
                try:
                    records = list(db.search_records("test", limit=10))
                    operations_count += 1
                except Exception as e:
                    errors.append(f"Search error: {e}")
            
            # Test record updates
            for i in range(25):
                try:
                    record = Record(
                        id=f"test_{i}",
                        title=f"Updated Test Record {i}",
                        description=f"Updated description {i}",
                        reference=f"TEST/{i}",
                        archive="TEST",
                        level="Item"
                    )
                    db.store_records([record])
                    operations_count += 1
                except Exception as e:
                    errors.append(f"Update error: {e}")
        
        except Exception as e:
            errors.append(f"Database test error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Get final database size
        db_size_after = self._get_database_size()
        
        # Stop monitoring
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="database_operations",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=operations_count,
            operations_per_second=operations_count / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=db_size_before,
            database_size_after=db_size_after,
            errors=errors
        )
    
    def test_search_performance(self) -> PerformanceMetrics:
        """Test search performance with various query types"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        operations_count = 0
        errors = []
        
        try:
            from storage.database import DatabaseManager
            
            db = DatabaseManager()
            
            # Test queries of varying complexity
            test_queries = [
                "test",
                "Churchill",
                "records",
                "England",
                "colonial",
                "correspondence",
                "government",
                "archive",
                "series",
                "department"
            ]
            
            # Run each query multiple times
            for _ in range(10):
                for query in test_queries:
                    try:
                        start_query = time.time()
                        results = list(db.search_records(query, limit=20))
                        query_time = time.time() - start_query
                        
                        operations_count += 1
                        
                        # Log slow queries
                        if query_time > 1.0:
                            logger.warning(f"Slow query: '{query}' took {query_time:.3f}s")
                    
                    except Exception as e:
                        errors.append(f"Search error for '{query}': {e}")
        
        except Exception as e:
            errors.append(f"Search test error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="search_performance",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=operations_count,
            operations_per_second=operations_count / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=self._get_database_size(),
            database_size_after=self._get_database_size(),
            errors=errors
        )
    
    def test_api_client_performance(self) -> PerformanceMetrics:
        """Test API client performance"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        operations_count = 0
        errors = []
        
        try:
            from api.client import DiscoveryClient
            
            client = DiscoveryClient()
            
            # Test various API operations
            test_queries = ["Churchill", "England", "records"]
            
            for query in test_queries:
                try:
                    # Test search
                    result = client.search(query, per_page=5)
                    operations_count += 1
                    
                    # Test record details if we got results
                    if result.records:
                        for record in result.records[:2]:  # Test first 2
                            try:
                                detailed_record = client.get_record(record.id)
                                operations_count += 1
                            except Exception as e:
                                errors.append(f"Record detail error: {e}")
                
                except Exception as e:
                    errors.append(f"API error for '{query}': {e}")
                
                # Rate limiting compliance
                time.sleep(1.1)  # Slightly over 1 second to be safe
        
        except Exception as e:
            errors.append(f"API client test error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="api_client_performance",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=operations_count,
            operations_per_second=operations_count / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=0,
            database_size_after=0,
            errors=errors,
            custom_metrics={'rate_limit_compliant': True}
        )
    
    def test_concurrent_access(self) -> PerformanceMetrics:
        """Test concurrent database access"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        operations_count = 0
        errors = []
        
        def worker_function(worker_id: int, operations: int) -> Tuple[int, List[str]]:
            """Worker function for concurrent testing"""
            local_ops = 0
            local_errors = []
            
            try:
                from storage.database import DatabaseManager
                db = DatabaseManager()
                
                for i in range(operations):
                    try:
                        # Mix of read and write operations
                        if i % 3 == 0:
                            # Write operation
                            from api.models import Record
                            record = Record(
                                id=f"concurrent_{worker_id}_{i}",
                                title=f"Concurrent Record {worker_id}-{i}",
                                description=f"Test concurrent access",
                                reference=f"CONC/{worker_id}/{i}",
                                archive="CONCURRENT",
                                level="Item"
                            )
                            db.store_records([record])
                        else:
                            # Read operation
                            list(db.search_records("concurrent", limit=5))
                        
                        local_ops += 1
                        
                    except Exception as e:
                        local_errors.append(f"Worker {worker_id} operation {i}: {e}")
            
            except Exception as e:
                local_errors.append(f"Worker {worker_id} general error: {e}")
            
            return local_ops, local_errors
        
        # Run concurrent workers
        num_workers = 5
        operations_per_worker = 20
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(worker_function, worker_id, operations_per_worker)
                for worker_id in range(num_workers)
            ]
            
            for future in as_completed(futures):
                try:
                    ops, worker_errors = future.result()
                    operations_count += ops
                    errors.extend(worker_errors)
                except Exception as e:
                    errors.append(f"Worker execution error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="concurrent_access",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=operations_count,
            operations_per_second=operations_count / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=self._get_database_size(),
            database_size_after=self._get_database_size(),
            errors=errors,
            custom_metrics={'concurrent_workers': num_workers}
        )
    
    def test_memory_usage(self) -> PerformanceMetrics:
        """Test memory usage under load"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        operations_count = 0
        errors = []
        
        try:
            from storage.database import DatabaseManager
            from api.models import Record
            
            db = DatabaseManager()
            
            # Create large batches of records to test memory handling
            batch_sizes = [100, 500, 1000]
            
            for batch_size in batch_sizes:
                try:
                    records = []
                    for i in range(batch_size):
                        record = Record(
                            id=f"memory_test_{batch_size}_{i}",
                            title=f"Memory Test Record {i}" * 10,  # Make it longer
                            description="A" * 1000,  # 1KB description
                            reference=f"MEM/{batch_size}/{i}",
                            archive="MEMORY_TEST",
                            level="Item"
                        )
                        records.append(record)
                    
                    # Store the batch
                    db.store_records(records)
                    operations_count += batch_size
                    
                    # Force garbage collection
                    import gc
                    gc.collect()
                    
                except Exception as e:
                    errors.append(f"Memory test batch {batch_size}: {e}")
        
        except Exception as e:
            errors.append(f"Memory test error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="memory_usage",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=operations_count,
            operations_per_second=operations_count / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=self._get_database_size(),
            database_size_after=self._get_database_size(),
            errors=errors
        )
    
    def test_large_dataset_handling(self) -> PerformanceMetrics:
        """Test performance with large datasets"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        operations_count = 0
        errors = []
        
        try:
            from utils.streaming import StreamingRecordProcessor, StreamingConfig
            from storage.database import DatabaseManager
            
            # Test streaming with simulated large dataset
            config = StreamingConfig(chunk_size=50, memory_limit_mb=100)
            processor = StreamingRecordProcessor(config)
            
            db = DatabaseManager()
            
            # Simulate processing large dataset by iterating through existing records
            record_chunks = []
            chunk = []
            
            for record in db.search_records("", limit=1000):  # Get up to 1000 records
                chunk.append(record)
                operations_count += 1
                
                if len(chunk) >= 50:
                    record_chunks.append(chunk)
                    chunk = []
            
            if chunk:
                record_chunks.append(chunk)
            
            # Process chunks
            for i, chunk in enumerate(record_chunks):
                try:
                    # Simulate processing time
                    time.sleep(0.01)  # 10ms per chunk
                    
                    # Memory monitoring
                    memory_info = processor.memory_monitor.check_memory()
                    if memory_info['usage_percent'] > 80:
                        logger.warning(f"High memory usage: {memory_info['usage_percent']:.1f}%")
                
                except Exception as e:
                    errors.append(f"Chunk processing error: {e}")
        
        except Exception as e:
            errors.append(f"Large dataset test error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="large_dataset_handling",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=operations_count,
            operations_per_second=operations_count / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=self._get_database_size(),
            database_size_after=self._get_database_size(),
            errors=errors
        )
    
    def test_pagination_performance(self) -> PerformanceMetrics:
        """Test cursor-based pagination performance"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        operations_count = 0
        errors = []
        
        try:
            from utils.pagination import CursorPaginator
            
            paginator = CursorPaginator()
            
            # Test pagination through multiple pages
            cursor = None
            pages_tested = 0
            max_pages = 10
            
            while pages_tested < max_pages:
                try:
                    result = paginator.paginate_records(
                        page_size=20,
                        cursor=cursor
                    )
                    
                    operations_count += len(result.records)
                    pages_tested += 1
                    
                    if not result.has_next:
                        break
                    
                    cursor = result.next_cursor
                
                except Exception as e:
                    errors.append(f"Pagination error on page {pages_tested}: {e}")
                    break
        
        except Exception as e:
            errors.append(f"Pagination test error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="pagination_performance",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=operations_count,
            operations_per_second=operations_count / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=self._get_database_size(),
            database_size_after=self._get_database_size(),
            errors=errors,
            custom_metrics={'pages_tested': pages_tested}
        )
    
    def test_export_performance(self) -> PerformanceMetrics:
        """Test export system performance"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        operations_count = 0
        errors = []
        
        try:
            from utils.exporters import BulkExportManager, ExportConfig
            
            manager = BulkExportManager()
            
            # Test different export formats
            formats = ['csv', 'json', 'jsonl']
            
            for format_type in formats:
                try:
                    config = ExportConfig(
                        format=format_type,
                        chunk_size=100,
                        filters={'level': 'Item'}  # Limit to reduce test time
                    )
                    
                    output_path = manager.export_records(config)
                    operations_count += 1
                    
                    # Verify file was created
                    if Path(output_path).exists():
                        file_size = Path(output_path).stat().st_size
                        logger.info(f"Export {format_type}: {file_size} bytes")
                        
                        # Clean up test file
                        Path(output_path).unlink()
                    else:
                        errors.append(f"Export file not created for {format_type}")
                
                except Exception as e:
                    errors.append(f"Export error for {format_type}: {e}")
        
        except Exception as e:
            errors.append(f"Export test error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="export_performance",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=operations_count,
            operations_per_second=operations_count / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=self._get_database_size(),
            database_size_after=self._get_database_size(),
            errors=errors
        )
    
    def test_streaming_performance(self) -> PerformanceMetrics:
        """Test streaming system performance"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        operations_count = 0
        errors = []
        
        try:
            from utils.streaming import StreamingRecordProcessor, StreamingConfig
            from storage.database import DatabaseManager
            
            config = StreamingConfig(chunk_size=25, memory_limit_mb=50)
            processor = StreamingRecordProcessor(config)
            
            # Test streaming database records
            def test_processor(records):
                """Test processing function"""
                processed = []
                for record in records:
                    # Simulate processing
                    processed.append({
                        'id': record.id,
                        'title_length': len(record.title or ''),
                        'has_description': bool(record.description)
                    })
                return {'processed': len(processed), 'data': processed}
            
            # Stream records from database
            record_stream = processor.stream_records_from_database(
                query="level = 'Item'",
                batch_size=25
            )
            
            chunk_count = 0
            for chunk in record_stream:
                try:
                    result = test_processor(chunk)
                    operations_count += len(chunk)
                    chunk_count += 1
                    
                    # Limit test to avoid long runtime
                    if chunk_count >= 10:
                        break
                
                except Exception as e:
                    errors.append(f"Streaming chunk error: {e}")
        
        except Exception as e:
            errors.append(f"Streaming test error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="streaming_performance",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=operations_count,
            operations_per_second=operations_count / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=self._get_database_size(),
            database_size_after=self._get_database_size(),
            errors=errors
        )
    
    def load_test(self, config: LoadTestConfig) -> PerformanceMetrics:
        """Run load test with multiple concurrent users"""
        monitor = PerformanceMonitor()
        monitor.start_monitoring()
        
        start_time = time.time()
        total_operations = 0
        all_errors = []
        
        def user_simulation(user_id: int) -> Tuple[int, List[str]]:
            """Simulate a user performing operations"""
            operations = 0
            errors = []
            
            try:
                from storage.database import DatabaseManager
                db = DatabaseManager()
                
                # Ramp up delay
                ramp_delay = (user_id / config.concurrent_users) * config.ramp_up_time
                time.sleep(ramp_delay)
                
                for operation in range(config.operations_per_user):
                    try:
                        # Mix of operations
                        if operation % 4 == 0:
                            # Search operation
                            list(db.search_records("test", limit=5))
                        elif operation % 4 == 1:
                            # Another search
                            list(db.search_records("Churchill", limit=3))
                        elif operation % 4 == 2:
                            # Store operation
                            from api.models import Record
                            record = Record(
                                id=f"load_test_{user_id}_{operation}",
                                title=f"Load Test Record {user_id}-{operation}",
                                description="Load test data",
                                reference=f"LOAD/{user_id}/{operation}",
                                archive="LOAD_TEST",
                                level="Item"
                            )
                            db.store_records([record])
                        else:
                            # Stats operation
                            db.get_statistics()
                        
                        operations += 1
                        
                        # Think time
                        time.sleep(config.think_time)
                    
                    except Exception as e:
                        errors.append(f"User {user_id} operation {operation}: {e}")
            
            except Exception as e:
                errors.append(f"User {user_id} general error: {e}")
            
            return operations, errors
        
        # Run load test
        with ThreadPoolExecutor(max_workers=config.concurrent_users) as executor:
            futures = [
                executor.submit(user_simulation, user_id)
                for user_id in range(config.concurrent_users)
            ]
            
            for future in as_completed(futures):
                try:
                    ops, errors = future.result()
                    total_operations += ops
                    all_errors.extend(errors)
                except Exception as e:
                    all_errors.append(f"User execution error: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        system_metrics = monitor.stop_monitoring()
        
        return PerformanceMetrics(
            test_name="load_test",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            operations_count=total_operations,
            operations_per_second=total_operations / duration if duration > 0 else 0,
            peak_memory_mb=system_metrics.get('peak_memory_mb', 0),
            peak_cpu_percent=system_metrics.get('peak_cpu_percent', 0),
            database_size_before=self._get_database_size(),
            database_size_after=self._get_database_size(),
            errors=all_errors,
            custom_metrics={
                'concurrent_users': config.concurrent_users,
                'operations_per_user': config.operations_per_user,
                'error_rate': len(all_errors) / max(total_operations, 1) * 100
            }
        )
    
    def benchmark_against_baseline(self, baseline_file: Optional[str] = None) -> Dict[str, Any]:
        """Benchmark current performance against baseline"""
        current_results = self.run_all_tests()
        
        if baseline_file and Path(baseline_file).exists():
            with open(baseline_file, 'r') as f:
                baseline_results = json.load(f)
            
            comparison = {}
            for current in current_results:
                test_name = current.test_name
                current_ops = current.operations_per_second
                
                baseline_test = next(
                    (b for b in baseline_results if b['test_name'] == test_name),
                    None
                )
                
                if baseline_test:
                    baseline_ops = baseline_test['operations_per_second']
                    
                    if baseline_ops > 0:
                        performance_ratio = current_ops / baseline_ops
                        comparison[test_name] = {
                            'current_ops_per_sec': current_ops,
                            'baseline_ops_per_sec': baseline_ops,
                            'performance_ratio': performance_ratio,
                            'improvement_percent': (performance_ratio - 1) * 100
                        }
            
            return comparison
        
        # Save current results as new baseline
        baseline_file = baseline_file or "performance_baseline.json"
        self.save_results(current_results, baseline_file)
        
        return {'baseline_created': baseline_file}
    
    def save_results(self, results: List[PerformanceMetrics], filename: str):
        """Save performance test results"""
        results_data = []
        for result in results:
            results_data.append({
                'test_name': result.test_name,
                'duration': result.duration,
                'operations_count': result.operations_count,
                'operations_per_second': result.operations_per_second,
                'peak_memory_mb': result.peak_memory_mb,
                'peak_cpu_percent': result.peak_cpu_percent,
                'error_count': len(result.errors),
                'custom_metrics': result.custom_metrics,
                'timestamp': datetime.fromtimestamp(result.start_time).isoformat()
            })
        
        with open(filename, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        logger.info(f"Performance results saved to {filename}")
    
    def generate_report(self, results: List[PerformanceMetrics]) -> str:
        """Generate human-readable performance report"""
        report = []
        report.append("=" * 80)
        report.append("PERFORMANCE TEST REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append(f"Tests Run: {len(results)}")
        report.append("")
        
        # Summary table
        report.append("TEST SUMMARY")
        report.append("-" * 80)
        report.append(f"{'Test Name':<25} {'Ops/Sec':<10} {'Duration':<10} {'Memory':<10} {'Errors':<8}")
        report.append("-" * 80)
        
        for result in results:
            report.append(
                f"{result.test_name:<25} "
                f"{result.operations_per_second:<10.1f} "
                f"{result.duration:<10.2f} "
                f"{result.peak_memory_mb:<10.1f} "
                f"{len(result.errors):<8}"
            )
        
        report.append("")
        
        # Detailed results
        for result in results:
            report.append(f"=== {result.test_name.upper()} ===")
            report.append(f"Operations: {result.operations_count}")
            report.append(f"Duration: {result.duration:.2f} seconds")
            report.append(f"Throughput: {result.operations_per_second:.1f} operations/second")
            report.append(f"Peak Memory: {result.peak_memory_mb:.1f} MB")
            report.append(f"Peak CPU: {result.peak_cpu_percent:.1f}%")
            
            if result.errors:
                report.append(f"Errors ({len(result.errors)}):")
                for error in result.errors[:5]:  # Show first 5 errors
                    report.append(f"  - {error}")
                if len(result.errors) > 5:
                    report.append(f"  ... and {len(result.errors) - 5} more")
            
            if result.custom_metrics:
                report.append("Custom Metrics:")
                for key, value in result.custom_metrics.items():
                    report.append(f"  {key}: {value}")
            
            report.append("")
        
        return "\n".join(report)
    
    def _get_database_size(self) -> int:
        """Get current database size in bytes"""
        try:
            return Path(self.database_path).stat().st_size
        except FileNotFoundError:
            return 0


# CLI Integration and convenience functions

def run_quick_performance_test() -> List[PerformanceMetrics]:
    """Run a quick performance test"""
    tester = PerformanceTester()
    return [
        tester.test_database_operations(),
        tester.test_search_performance(),
        tester.test_memory_usage()
    ]


def run_comprehensive_performance_test() -> List[PerformanceMetrics]:
    """Run comprehensive performance test suite"""
    tester = PerformanceTester()
    return tester.run_all_tests()


def run_load_test(concurrent_users: int = 10, operations_per_user: int = 50) -> PerformanceMetrics:
    """Run load test with specified parameters"""
    tester = PerformanceTester()
    config = LoadTestConfig(
        concurrent_users=concurrent_users,
        operations_per_user=operations_per_user
    )
    return tester.load_test(config)
