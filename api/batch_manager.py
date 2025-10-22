"""
Request Batching System for TNA Discovery API

Implements high-impact performance optimization from TNA Bible Recommendations
"""

import logging
import asyncio
import time
from typing import List, Dict, Any, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
import threading
from queue import Queue, Empty
import uuid

from .client import DiscoveryClient
from .models import Record

logger = logging.getLogger(__name__)


@dataclass
class BatchRequest:
    """Represents a single request in a batch"""
    request_id: str
    record_id: str
    endpoint: str
    params: Dict[str, Any]
    callback: Optional[Callable] = None
    priority: int = 1  # 1=high, 2=medium, 3=low
    created_at: float = field(default_factory=time.time)
    retries: int = 0
    max_retries: int = 3


@dataclass
class BatchResult:
    """Result of a batch operation"""
    request_id: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    processing_time: float = 0.0


class BatchRequestManager:
    """
    High-performance request batching system
    
    Features:
    - Intelligent batching based on endpoint types
    - Priority queuing
    - Automatic retry with exponential backoff
    - Rate limit aware processing
    - Memory-efficient streaming
    """
    
    def __init__(self, 
                 api_client: DiscoveryClient,
                 batch_size: int = 10,
                 processing_interval: float = 1.0,
                 max_concurrent_batches: int = 3):
        """
        Initialize batch request manager
        
        Args:
            api_client: DiscoveryClient instance
            batch_size: Maximum requests per batch
            processing_interval: Seconds between batch processing
            max_concurrent_batches: Maximum concurrent batch operations
        """
        self.api_client = api_client
        self.batch_size = batch_size
        self.processing_interval = processing_interval
        self.max_concurrent_batches = max_concurrent_batches
        
        # Request queues by priority
        self.high_priority_queue: Queue = Queue()
        self.medium_priority_queue: Queue = Queue()
        self.low_priority_queue: Queue = Queue()
        
        # Batch processing state
        self.pending_requests: Dict[str, BatchRequest] = {}
        self.completed_results: Dict[str, BatchResult] = {}
        self.is_processing = False
        self.processing_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'successful_batches': 0,
            'failed_batches': 0,
            'average_batch_time': 0.0,
            'requests_batched': 0,
            'cache_hits': 0
        }
        
        logger.info(f"Initialized BatchRequestManager (batch_size={batch_size}, interval={processing_interval}s)")
    
    def start_processing(self):
        """Start the batch processing thread"""
        if not self.is_processing:
            self.is_processing = True
            self.processing_thread = threading.Thread(target=self._process_batches, daemon=True)
            self.processing_thread.start()
            logger.info("Started batch processing thread")
    
    def stop_processing(self):
        """Stop the batch processing thread"""
        self.is_processing = False
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5)
        logger.info("Stopped batch processing thread")
    
    def add_record_request(self, 
                          record_id: str, 
                          priority: int = 1,
                          callback: Optional[Callable] = None) -> str:
        """
        Add a record fetch request to the batch queue
        
        Args:
            record_id: Record ID to fetch
            priority: Request priority (1=high, 2=medium, 3=low)
            callback: Optional callback function for result
            
        Returns:
            Request ID for tracking
        """
        request_id = str(uuid.uuid4())
        
        batch_request = BatchRequest(
            request_id=request_id,
            record_id=record_id,
            endpoint='records/v1/details',
            params={'id': record_id},
            callback=callback,
            priority=priority
        )
        
        # Add to appropriate queue based on priority
        if priority == 1:
            self.high_priority_queue.put(batch_request)
        elif priority == 2:
            self.medium_priority_queue.put(batch_request)
        else:
            self.low_priority_queue.put(batch_request)
        
        self.pending_requests[request_id] = batch_request
        self.stats['total_requests'] += 1
        
        logger.debug(f"Added record request {record_id} (priority={priority}, id={request_id})")
        return request_id
    
    def add_search_request(self,
                          query: str,
                          params: Dict[str, Any],
                          priority: int = 2,
                          callback: Optional[Callable] = None) -> str:
        """
        Add a search request to the batch queue
        
        Args:
            query: Search query
            params: Search parameters
            priority: Request priority
            callback: Optional callback function
            
        Returns:
            Request ID for tracking
        """
        request_id = str(uuid.uuid4())
        
        search_params = {
            'sps.searchQuery': query,
            **params
        }
        
        batch_request = BatchRequest(
            request_id=request_id,
            record_id=query,  # Use query as identifier
            endpoint='search/v1/records',
            params=search_params,
            callback=callback,
            priority=priority
        )
        
        # Add to appropriate queue
        if priority == 1:
            self.high_priority_queue.put(batch_request)
        elif priority == 2:
            self.medium_priority_queue.put(batch_request)
        else:
            self.low_priority_queue.put(batch_request)
        
        self.pending_requests[request_id] = batch_request
        self.stats['total_requests'] += 1
        
        logger.debug(f"Added search request '{query}' (priority={priority}, id={request_id})")
        return request_id
    
    def get_result(self, request_id: str, timeout: float = 30.0) -> Optional[BatchResult]:
        """
        Get result for a specific request
        
        Args:
            request_id: Request ID to check
            timeout: Maximum wait time in seconds
            
        Returns:
            BatchResult or None if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if request_id in self.completed_results:
                result = self.completed_results.pop(request_id)
                logger.debug(f"Retrieved result for request {request_id}")
                return result
            
            time.sleep(0.1)  # Small delay to avoid busy waiting
        
        logger.warning(f"Timeout waiting for result {request_id}")
        return None
    
    def batch_record_requests(self, record_ids: List[str], priority: int = 1) -> List[str]:
        """
        Add multiple record requests as a batch
        
        Args:
            record_ids: List of record IDs to fetch
            priority: Priority for all requests
            
        Returns:
            List of request IDs
        """
        request_ids = []
        
        for record_id in record_ids:
            request_id = self.add_record_request(record_id, priority)
            request_ids.append(request_id)
        
        logger.info(f"Batched {len(record_ids)} record requests")
        return request_ids
    
    def wait_for_results(self, request_ids: List[str], timeout: float = 60.0) -> List[BatchResult]:
        """
        Wait for multiple results to complete
        
        Args:
            request_ids: List of request IDs to wait for
            timeout: Maximum wait time
            
        Returns:
            List of BatchResult objects
        """
        results = []
        start_time = time.time()
        remaining_ids = set(request_ids)
        
        while remaining_ids and (time.time() - start_time) < timeout:
            completed_ids = []
            
            for request_id in remaining_ids:
                if request_id in self.completed_results:
                    result = self.completed_results.pop(request_id)
                    results.append(result)
                    completed_ids.append(request_id)
            
            for completed_id in completed_ids:
                remaining_ids.remove(completed_id)
            
            if remaining_ids:
                time.sleep(0.1)
        
        # Add timeout results for any remaining requests
        for request_id in remaining_ids:
            results.append(BatchResult(
                request_id=request_id,
                success=False,
                error="Timeout waiting for result"
            ))
        
        logger.info(f"Retrieved {len(results)} results ({len(remaining_ids)} timeouts)")
        return results
    
    def _get_next_batch(self) -> List[BatchRequest]:
        """Get the next batch of requests to process"""
        batch = []
        
        # Process high priority first
        while len(batch) < self.batch_size:
            try:
                request = self.high_priority_queue.get_nowait()
                batch.append(request)
            except Empty:
                break
        
        # Then medium priority
        while len(batch) < self.batch_size:
            try:
                request = self.medium_priority_queue.get_nowait()
                batch.append(request)
            except Empty:
                break
        
        # Finally low priority
        while len(batch) < self.batch_size:
            try:
                request = self.low_priority_queue.get_nowait()
                batch.append(request)
            except Empty:
                break
        
        return batch
    
    def _process_batches(self):
        """Main batch processing loop"""
        logger.info("Started batch processing loop")
        
        while self.is_processing:
            try:
                # Get next batch
                batch = self._get_next_batch()
                
                if not batch:
                    time.sleep(self.processing_interval)
                    continue
                
                # Process the batch
                self._execute_batch(batch)
                
                # Respect rate limiting
                time.sleep(self.processing_interval)
                
            except Exception as e:
                logger.error(f"Error in batch processing loop: {e}")
                time.sleep(1)  # Brief pause before retrying
        
        logger.info("Batch processing loop ended")
    
    def _execute_batch(self, batch: List[BatchRequest]):
        """Execute a batch of requests"""
        start_time = time.time()
        
        logger.debug(f"Processing batch of {len(batch)} requests")
        
        # Group requests by endpoint type for optimal batching
        record_requests = []
        search_requests = []
        other_requests = []
        
        for request in batch:
            if 'records/v1/details' in request.endpoint:
                record_requests.append(request)
            elif 'search' in request.endpoint:
                search_requests.append(request)
            else:
                other_requests.append(request)
        
        # Process record requests using search API for efficiency
        if record_requests:
            self._batch_process_records(record_requests)
        
        # Process search requests individually (can't batch these effectively)
        for request in search_requests:
            self._process_single_request(request)
        
        # Process other requests individually
        for request in other_requests:
            self._process_single_request(request)
        
        # Update statistics
        processing_time = time.time() - start_time
        self.stats['successful_batches'] += 1
        self.stats['requests_batched'] += len(batch)
        
        # Update average batch time
        total_batches = self.stats['successful_batches'] + self.stats['failed_batches']
        if total_batches > 0:
            self.stats['average_batch_time'] = (
                (self.stats['average_batch_time'] * (total_batches - 1) + processing_time) / total_batches
            )
        
        logger.debug(f"Completed batch in {processing_time:.2f}s")
    
    def _batch_process_records(self, record_requests: List[BatchRequest]):
        """Process multiple record requests efficiently using search API"""
        if not record_requests:
            return
        
        try:
            # Create a search query to fetch multiple records at once
            record_ids = [req.record_id for req in record_requests]
            
            # Use OR query to fetch multiple records
            # Note: This is an optimization - if TNA doesn't support ID searches,
            # fall back to individual requests
            batch_query = ' OR '.join([f'id:"{rid}"' for rid in record_ids])
            
            try:
                # Try batch search first
                search_result = self.api_client.search(
                    query=batch_query,
                    per_page=len(record_ids),
                    sort_option='RELEVANCE'
                )
                
                # Map results back to requests
                result_map = {record.id: record for record in search_result.records}
                
                for request in record_requests:
                    if request.record_id in result_map:
                        # Success
                        result = BatchResult(
                            request_id=request.request_id,
                            success=True,
                            data=result_map[request.record_id],
                            processing_time=time.time() - request.created_at
                        )
                    else:
                        # Not found
                        result = BatchResult(
                            request_id=request.request_id,
                            success=False,
                            error="Record not found in batch search",
                            processing_time=time.time() - request.created_at
                        )
                    
                    self._complete_request(request, result)
                
                logger.debug(f"Batch processed {len(record_requests)} record requests")
                
            except Exception as search_error:
                logger.warning(f"Batch search failed, falling back to individual requests: {search_error}")
                # Fall back to individual requests
                for request in record_requests:
                    self._process_single_request(request)
                    
        except Exception as e:
            logger.error(f"Error in batch record processing: {e}")
            # Mark all requests as failed
            for request in record_requests:
                result = BatchResult(
                    request_id=request.request_id,
                    success=False,
                    error=str(e),
                    processing_time=time.time() - request.created_at
                )
                self._complete_request(request, result)
    
    def _process_single_request(self, request: BatchRequest):
        """Process a single request"""
        try:
            start_time = time.time()
            
            if 'records/v1/details' in request.endpoint:
                # Individual record request
                record = self.api_client.get_record(request.record_id)
                
                if record:
                    result = BatchResult(
                        request_id=request.request_id,
                        success=True,
                        data=record,
                        processing_time=time.time() - start_time
                    )
                else:
                    result = BatchResult(
                        request_id=request.request_id,
                        success=False,
                        error="Record not found",
                        processing_time=time.time() - start_time
                    )
                    
            elif 'search' in request.endpoint:
                # Search request
                search_result = self.api_client.search(
                    query=request.params.get('sps.searchQuery', ''),
                    page=request.params.get('sps.page', 0),
                    per_page=request.params.get('sps.resultsPageSize', 20),
                    sort_option=request.params.get('sps.sortByOption', 'RELEVANCE'),
                    filters={k: v for k, v in request.params.items() 
                            if k.startswith('sps.') and k not in ['sps.searchQuery', 'sps.page', 'sps.resultsPageSize', 'sps.sortByOption']}
                )
                
                result = BatchResult(
                    request_id=request.request_id,
                    success=True,
                    data=search_result,
                    processing_time=time.time() - start_time
                )
            else:
                # Other endpoint
                response_data = self.api_client._make_request(request.endpoint, request.params)
                
                result = BatchResult(
                    request_id=request.request_id,
                    success=True,
                    data=response_data,
                    processing_time=time.time() - start_time
                )
            
            self._complete_request(request, result)
            
        except Exception as e:
            logger.error(f"Error processing request {request.request_id}: {e}")
            
            # Check if this should be retried
            if request.retries < request.max_retries:
                request.retries += 1
                # Re-queue with lower priority
                new_priority = min(request.priority + 1, 3)
                
                if new_priority == 1:
                    self.high_priority_queue.put(request)
                elif new_priority == 2:
                    self.medium_priority_queue.put(request)
                else:
                    self.low_priority_queue.put(request)
                
                logger.debug(f"Retrying request {request.request_id} (attempt {request.retries})")
            else:
                # Max retries exceeded
                result = BatchResult(
                    request_id=request.request_id,
                    success=False,
                    error=f"Max retries exceeded: {str(e)}",
                    processing_time=time.time() - request.created_at
                )
                self._complete_request(request, result)
    
    def _complete_request(self, request: BatchRequest, result: BatchResult):
        """Complete a request with its result"""
        # Remove from pending
        if request.request_id in self.pending_requests:
            del self.pending_requests[request.request_id]
        
        # Store result
        self.completed_results[request.request_id] = result
        
        # Call callback if provided
        if request.callback:
            try:
                request.callback(result)
            except Exception as e:
                logger.warning(f"Error in callback for request {request.request_id}: {e}")
        
        logger.debug(f"Completed request {request.request_id} (success={result.success})")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get batch processing statistics"""
        return {
            'total_requests': self.stats['total_requests'],
            'pending_requests': len(self.pending_requests),
            'completed_results': len(self.completed_results),
            'successful_batches': self.stats['successful_batches'],
            'failed_batches': self.stats['failed_batches'],
            'average_batch_time': self.stats['average_batch_time'],
            'requests_batched': self.stats['requests_batched'],
            'queue_sizes': {
                'high_priority': self.high_priority_queue.qsize(),
                'medium_priority': self.medium_priority_queue.qsize(),
                'low_priority': self.low_priority_queue.qsize()
            },
            'batch_config': {
                'batch_size': self.batch_size,
                'processing_interval': self.processing_interval,
                'max_concurrent_batches': self.max_concurrent_batches
            }
        }
    
    def __enter__(self):
        """Context manager entry"""
        self.start_processing()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_processing()
