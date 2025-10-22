"""
Hierarchical Traversal System for National Archives Discovery API

Implements the recursive traversal algorithm described in Workflow.md
for complete Colonial Office (CO) series metadata extraction.
"""

import logging
import time
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
from urllib.parse import urljoin, urlparse
import re

from .client import DiscoveryClient, PermanentError, TransientError, RateLimitError
from .models import Record, CrawlQueueItem
from .scraper import DiscoveryScraper, HybridClient
from storage.database import DatabaseManager
from utils.logging_config import log_traversal_progress, get_contextual_logger

logger = logging.getLogger(__name__)


class HierarchicalTraverser:
    """
    Implements recursive traversal of TNA's archival hierarchy
    
    Based on Workflow.md Section 4: Step-by-Step Data Extraction Workflow
    Supports the complete CO series structure: Department → Series → Sub-series → Pieces → Items
    """
    
    def __init__(self, api_client: DiscoveryClient, db_manager: DatabaseManager, 
                 enable_scraping: bool = True):
        """
        Initialize the hierarchical traverser
        
        Args:
            api_client: Discovery API client with enhanced error handling
            db_manager: Database manager with crawl queue support
            enable_scraping: Whether to enable web scraping fallback
        """
        self.api_client = api_client
        self.db_manager = db_manager
        self.processed_urls: Set[str] = set()
        
        # Initialize hybrid client with scraping fallback
        if enable_scraping:
            try:
                self.scraper = DiscoveryScraper()
                self.hybrid_client = HybridClient(api_client, self.scraper)
                logger.info("Initialized with web scraping fallback enabled")
            except ImportError as e:
                logger.warning(f"Web scraping dependencies not available: {e}")
                self.scraper = None
                self.hybrid_client = None
        else:
            self.scraper = None
            self.hybrid_client = None
        
        # Colonial Office department root (from Workflow.md)
        self.CO_DEPARTMENT_ID = 'C57'
        self.CO_BASE_URL = 'https://discovery.nationalarchives.gov.uk/details/r/'
        
        logger.info("Initialized hierarchical traverser for CO series")
    
    def start_co_traversal(self, max_records: Optional[int] = None) -> Dict[str, Any]:
        """
        Start complete Colonial Office series traversal
        
        Implements Workflow.md "Step 1: Initial Seeding" - begins with C57 (CO department)
        then recursively traverses all series (CO 1, CO 2, etc.)
        
        Args:
            max_records: Maximum records to process (None = unlimited)
            
        Returns:
            Traversal statistics and results
        """
        logger.info("🏛️  Starting complete Colonial Office series traversal")
        logger.info(f"📊 Max records: {max_records if max_records else 'unlimited'}")
        
        start_time = datetime.now()
        
        # Step 1: Seed the crawl queue with CO department root
        co_url = f"{self.CO_BASE_URL}{self.CO_DEPARTMENT_ID}"
        self.db_manager.add_to_crawl_queue(
            url=co_url,
            record_id=self.CO_DEPARTMENT_ID,
            parent_id=None,
            expected_level='Department'
        )
        
        logger.info(f"🌱 Seeded crawl queue with CO department: {co_url}")
        
        # Step 2: Execute recursive traversal
        stats = self._execute_traversal_loop(max_records)
        
        # Calculate final statistics
        end_time = datetime.now()
        duration = end_time - start_time
        
        stats.update({
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration.total_seconds(),
            'traversal_type': 'complete_co_series'
        })
        
        logger.info(f"✅ CO traversal completed in {duration}")
        return stats
    
    def start_specific_series_traversal(self, series_id: str, max_records: Optional[int] = None) -> Dict[str, Any]:
        """
        Start traversal of a specific CO series (e.g., 'CO 1', 'CO 2')
        
        Args:
            series_id: Series identifier (e.g., 'C243' for CO 1)
            max_records: Maximum records to process
            
        Returns:
            Traversal statistics
        """
        logger.info(f"🗂️  Starting specific series traversal: {series_id}")
        
        start_time = datetime.now()
        
        # Seed with specific series
        series_url = f"{self.CO_BASE_URL}{series_id}"
        self.db_manager.add_to_crawl_queue(
            url=series_url,
            record_id=series_id,
            parent_id=self.CO_DEPARTMENT_ID,
            expected_level='Series'
        )
        
        stats = self._execute_traversal_loop(max_records)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        stats.update({
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration.total_seconds(),
            'traversal_type': f'specific_series_{series_id}'
        })
        
        return stats
    
    def _execute_traversal_loop(self, max_records: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute the main traversal loop
        
        Implements Workflow.md "Step 2: Traversal Logic (Recursive Algorithm)"
        """
        processed_count = 0
        failed_count = 0
        skipped_count = 0
        
        logger.info("🔄 Starting traversal loop")
        
        while True:
            # Check if we've hit the record limit
            if max_records and processed_count >= max_records:
                logger.info(f"📊 Reached maximum record limit: {max_records}")
                break
            
            # Get next item from crawl queue
            queue_item = self.db_manager.get_next_crawl_item()
            
            if not queue_item:
                logger.info("📋 No more items in crawl queue - traversal complete")
                break
            
            url = queue_item['url']
            record_id = queue_item['record_id']
            
            # Skip if already processed (idempotency check)
            if url in self.processed_urls:
                skipped_count += 1
                self.db_manager.update_crawl_status(url, 'COMPLETED', 'Already processed')
                continue
            
            logger.debug(f"🔍 Processing: {record_id} ({url})")
            
            try:
                # Mark as processing
                self.db_manager.update_crawl_status(url, 'PROCESSING')
                
                # Process single record
                result = self._process_record(queue_item)
                
                if result['success']:
                    processed_count += 1
                    self.processed_urls.add(url)
                    self.db_manager.update_crawl_status(url, 'COMPLETED')
                    
                    # Log progress every 10 records
                    if processed_count % 10 == 0:
                        queue_stats = self.db_manager.get_crawl_stats()
                        queue_size = sum(queue_stats.values())
                        
                        log_traversal_progress(
                            logger=logger,
                            processed=processed_count,
                            failed=failed_count,
                            queue_size=queue_size,
                            current_record=record_id
                        )
                else:
                    failed_count += 1
                    error_msg = result.get('error', 'Unknown error')
                    self.db_manager.update_crawl_status(url, 'FAILED', error_msg)
                    logger.warning(f"❌ Failed to process {record_id}: {error_msg}")
                
            except Exception as e:
                failed_count += 1
                error_msg = f"Unexpected error: {str(e)}"
                self.db_manager.update_crawl_status(url, 'FAILED', error_msg)
                logger.error(f"💥 Unexpected error processing {record_id}: {e}")
                
                # Add small delay to prevent rapid failures
                time.sleep(1)
        
        # Final statistics
        final_queue_stats = self.db_manager.get_crawl_stats()
        
        return {
            'processed_count': processed_count,
            'failed_count': failed_count,
            'skipped_count': skipped_count,
            'queue_stats': final_queue_stats
        }
    
    def _process_record(self, queue_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single record and discover child records
        
        Implements Workflow.md "function process_record(record_url)"
        
        Args:
            queue_item: Item from crawl queue
            
        Returns:
            Processing result with success status and details
        """
        url = queue_item['url']
        record_id = queue_item['record_id']
        
        try:
            # Step 1: Fetch record metadata via API with scraping fallback
            if self.hybrid_client:
                record = self.hybrid_client.get_record_with_fallback(record_id)
            else:
                record = self.api_client.get_record(record_id)
            
            if not record:
                return {'success': False, 'error': f'Record not found: {record_id}'}
            
            # Step 2: Enhance with hierarchical metadata
            record.parent_id = queue_item.get('parent_id')
            record.level = queue_item.get('expected_level') or record.level
            
            # Step 3: Store record in database
            stored_count = self.db_manager.store_records([record])
            
            if stored_count == 0:
                return {'success': False, 'error': 'Failed to store record in database'}
            
            # Step 4: Discover child records and add to queue
            child_count = self._discover_and_queue_children(record, record_id)
            
            # Update child count in stored record
            if child_count > 0:
                record.child_count = child_count
                self.db_manager.store_records([record])  # Update with child count
            
            logger.debug(f"✅ Processed {record_id}: stored record, found {child_count} children")
            
            return {
                'success': True,
                'record_id': record_id,
                'title': record.title[:50] + '...' if len(record.title) > 50 else record.title,
                'level': record.level,
                'child_count': child_count
            }
            
        except PermanentError as e:
            return {'success': False, 'error': f'Permanent error: {e}'}
        except (TransientError, RateLimitError) as e:
            # These should be retried by the error handling system
            raise e
        except Exception as e:
            return {'success': False, 'error': f'Processing error: {e}'}
    
    def _discover_and_queue_children(self, record: Record, parent_id: str) -> int:
        """
        Discover child records and add them to the crawl queue
        
        For API-based discovery, this uses the series search functionality.
        Future enhancement: Add web scraping fallback as per Workflow.md.
        
        Args:
            record: Parent record
            parent_id: Parent record ID
            
        Returns:
            Number of children discovered and queued
        """
        children_queued = 0
        
        try:
            # Try hybrid approach: API first, then scraping
            if self.hybrid_client:
                # Use scraping-based child discovery (more reliable)
                discovered_children = self.hybrid_client.discover_children_with_fallback(parent_id)
                
                for child_info in discovered_children:
                    child_id = child_info.get('id')
                    child_url = child_info.get('url')
                    
                    if child_id and child_url and child_id != parent_id:
                        # Determine expected level
                        child_level = self._determine_child_level(record.level)
                        
                        success = self.db_manager.add_to_crawl_queue(
                            url=child_url,
                            record_id=child_id,
                            parent_id=parent_id,
                            expected_level=child_level
                        )
                        
                        if success:
                            children_queued += 1
            else:
                # Fallback to API-based discovery for series level
                if record.level in ['Department', 'Series'] and record.reference:
                    # Extract series code (e.g., 'CO 1' from 'CO 1/1/2')
                    series_code = self._extract_series_code(record.reference)
                    
                    if series_code:
                        try:
                            # Search for records in this series
                            api_response = self.api_client.search_record_series(
                                series=series_code,
                                results_page_size=100
                            )
                            
                            raw_records = api_response.get('records', [])
                            
                            for raw_record in raw_records:
                                child_id = raw_record.get('id', '')
                                
                                if child_id and child_id != parent_id:
                                    child_url = f"{self.CO_BASE_URL}{child_id}"
                                    
                                    # Determine expected level
                                    child_level = self._determine_child_level(record.level)
                                    
                                    success = self.db_manager.add_to_crawl_queue(
                                        url=child_url,
                                        record_id=child_id,
                                        parent_id=parent_id,
                                        expected_level=child_level
                                    )
                                    
                                    if success:
                                        children_queued += 1
                        
                        except Exception as e:
                            logger.warning(f"API child discovery failed for {parent_id}: {e}")
            
            return children_queued
            
        except Exception as e:
            logger.error(f"Error discovering children for {parent_id}: {e}")
            return 0
    
    def _extract_series_code(self, reference: str) -> Optional[str]:
        """
        Extract series code from reference (e.g., 'CO 1' from 'CO 1/23/45')
        
        Args:
            reference: Archive reference string
            
        Returns:
            Series code or None
        """
        if not reference:
            return None
        
        # Match patterns like 'CO 1', 'WO 95', 'FO 371'
        match = re.match(r'^([A-Z]+\s+\d+)', reference)
        return match.group(1) if match else None
    
    def _determine_child_level(self, parent_level: str) -> str:
        """
        Determine the expected archival level for children
        
        Args:
            parent_level: Level of parent record
            
        Returns:
            Expected level for children
        """
        level_hierarchy = {
            'Department': 'Series',
            'Series': 'Sub-series',
            'Sub-series': 'Sub sub-series',
            'Sub sub-series': 'Piece',
            'Piece': 'Item'
        }
        
        return level_hierarchy.get(parent_level, 'Item')
    
    def get_traversal_status(self) -> Dict[str, Any]:
        """
        Get current status of the traversal process
        
        Returns:
            Status information including queue statistics
        """
        queue_stats = self.db_manager.get_crawl_stats()
        
        return {
            'queue_statistics': queue_stats,
            'total_processed': len(self.processed_urls),
            'is_active': queue_stats.get('QUEUED', 0) > 0 or queue_stats.get('PROCESSING', 0) > 0
        }
    
    def resume_traversal(self, max_records: Optional[int] = None) -> Dict[str, Any]:
        """
        Resume an interrupted traversal process
        
        Returns:
            Traversal results
        """
        logger.info("🔄 Resuming interrupted traversal")
        
        # Reset any PROCESSING items back to QUEUED (in case of crash)
        with self.db_manager as db:
            db.execute("UPDATE crawl_queue SET status = 'QUEUED' WHERE status = 'PROCESSING'")
        
        return self._execute_traversal_loop(max_records)
