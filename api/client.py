"""
Discovery API Client - Respectful and compliant access to National Archives data
"""

import logging
from typing import List, Dict, Optional, Iterator, Any
from datetime import datetime, timedelta
import requests
from ratelimit import limits, sleep_and_retry
import os
import time
import random
from dotenv import load_dotenv

from utils.logging_config import log_api_request

from .models import Record, SearchResult, Collection

# Load environment variables
load_dotenv('config.env')

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when API rate limits are exceeded"""
    pass


class AuthenticationError(Exception):
    """Raised when API authentication fails"""
    pass


class TransientError(Exception):
    """Raised for temporary errors that should be retried"""
    pass


class PermanentError(Exception):
    """Raised for permanent errors that should not be retried"""
    pass


class ParsingError(Exception):
    """Raised when API response cannot be parsed"""
    pass


class DiscoveryClient:
    """
    Client for The National Archives Discovery API
    
    Implements proper rate limiting, authentication, and error handling
    according to TNA's API guidelines.
    """
    
    def __init__(self, 
                 base_url: Optional[str] = None,
                 max_requests_per_5min: int = 3000,
                 requests_per_second: float = 1.0):
        """
        Initialize the Discovery API client
        
        Args:
            base_url: Base URL for API (or set API_BASE_URL env var)
            max_requests_per_5min: 5-minute request limit (default: 3000)
            requests_per_second: Request rate limit (default: 1.0)
        
        Note: Access is IP-based (88.97.249.90), no API key required
        """
        self.base_url = base_url or os.getenv('API_BASE_URL', 'https://discovery.nationalarchives.gov.uk/API')
        self.max_requests_per_5min = max_requests_per_5min
        self.requests_per_second = requests_per_second
        
        # Request tracking for 5-minute AND daily limits (API Bible Section 6.1)
        self.requests_in_5min = 0
        self.last_5min_window = datetime.now()
        
        # Daily limit tracking - CRITICAL per API Bible
        self.daily_request_count = 0
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Session for connection pooling
        self.session = requests.Session()
        # Use CORRECT User-Agent format per API Bible Section 6.3
        self.session.headers.update({
            'User-Agent': 'clio/2.0 (https://github.com/rtw878/clio; contact@example.com)',
            'Accept': 'application/json'
        })
        
        logger.info(f"Initialized Discovery API client (IP-based access) with rate limit: {requests_per_second} req/sec, {max_requests_per_5min} req/5min")
    
    def _exponential_backoff_retry(self, func, *args, max_retries: int = 3, **kwargs):
        """
        Execute function with exponential backoff retry logic (Workflow.md requirement)
        
        Implements the error handling strategy from Table 6.1:
        - Rate Limit (429): Exponential backoff with jitter
        - Server Error (5xx): Fixed retry with 5s delay
        - Network Error: Fixed retry with 5s delay  
        - Parsing Error: No retry
        - Not Found (404): No retry
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
                
            except RateLimitError as e:
                if attempt == max_retries:
                    raise e
                
                # Exponential backoff with jitter for rate limits
                base_delay = 2 ** attempt  # 1s, 2s, 4s, 8s...
                jitter = random.uniform(0.1, 0.5)  # Add randomness
                delay = min(base_delay + jitter, 60)  # Cap at 60 seconds
                
                logger.warning(f"Rate limit hit, backing off for {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})")
                time.sleep(delay)
                last_exception = e
                
            except TransientError as e:
                if attempt == max_retries:
                    raise e
                
                # Fixed delay for transient errors
                logger.warning(f"Transient error, retrying in 5s (attempt {attempt + 1}/{max_retries + 1}): {e}")
                time.sleep(5)
                last_exception = e
                
            except (PermanentError, ParsingError, AuthenticationError) as e:
                # Don't retry permanent errors
                logger.error(f"Permanent error, not retrying: {e}")
                raise e
        
        # If we get here, all retries failed
        if last_exception:
            raise last_exception

    def _check_5min_limit(self):
        """Check and reset 5-minute request counter"""
        now = datetime.now()
        time_diff = (now - self.last_5min_window).total_seconds()
        
        # Reset counter every 5 minutes
        if time_diff >= 300:  # 5 minutes in seconds
            self.requests_in_5min = 0
            self.last_5min_window = now
        
        if self.requests_in_5min >= self.max_requests_per_5min:
            raise RateLimitError(f"5-minute request limit of {self.max_requests_per_5min} exceeded")

    def _check_daily_limit(self):
        """Check and reset daily request counter (API Bible Section 6.1)"""
        now = datetime.now()
        
        # Reset counter at midnight
        if now >= self.daily_reset_time + timedelta(days=1):
            self.daily_request_count = 0
            self.daily_reset_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if self.daily_request_count >= 3000:  # API Bible daily limit
            raise RateLimitError("Daily limit of 3000 requests exceeded")

    def _make_request_internal(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Internal method to make a single API request with enhanced error categorization
        (Workflow.md Table 6.1 implementation)
        """
        self._check_5min_limit()
        self._check_daily_limit()
        
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        start_time = time.time()
        
        try:
            logger.debug(f"Making request to {url} with params {params}")
            response = self.session.get(url, params=params, timeout=30)
            
            # Track successful requests for both 5-min and daily limits
            self.requests_in_5min += 1
            self.daily_request_count += 1
            
            # Calculate response time for structured logging
            response_time = time.time() - start_time
            
            # Enhanced error categorization per API Bible Section 6.2
            error_mapping = {
                204: ("No Content", "Record not found"),
                401: ("Unauthorized", "IP address not allowlisted"),
                403: ("Forbidden", "Access denied"),
                404: ("Not Found", "Resource not found"),
                429: ("Too Many Requests", "Rate limit exceeded"),
                500: ("Internal Server Error", "Server error"),
                503: ("Service Unavailable", "Service temporarily unavailable")
            }
            
            if response.status_code in error_mapping:
                error_name, error_desc = error_mapping[response.status_code]
                log_api_request(logger, 'GET', url, response.status_code, response_time, 
                              error=f"{error_name}: {error_desc}")
                
                if response.status_code == 204:
                    raise PermanentError("Record not found")
                elif response.status_code in [401, 403]:
                    raise AuthenticationError(f"IP not allowlisted: {error_desc}")
                elif response.status_code == 404:
                    raise PermanentError(f"Resource not found: {url}")
                elif response.status_code == 429:
                    raise RateLimitError("Rate limit exceeded - server side throttling")
                elif response.status_code in [500, 503]:
                    raise TransientError(f"{error_name} {response.status_code}: {error_desc}")
            elif 400 <= response.status_code < 500:
                log_api_request(logger, 'GET', url, response.status_code, response_time, 
                              error=f"Client error: {response.text[:100]}")
                raise PermanentError(f"Client error {response.status_code}: {response.text}")
            
            response.raise_for_status()
            
            try:
                json_data = response.json()
                
                # Log successful API request with structured data
                record_count = None
                if isinstance(json_data, dict):
                    # Try to extract record count for logging
                    if 'records' in json_data:
                        record_count = len(json_data['records'])
                    elif 'totalResults' in json_data:
                        record_count = json_data['totalResults']
                
                log_api_request(
                    logger=logger,
                    method='GET',
                    url=url,
                    status_code=response.status_code,
                    response_time=response_time,
                    record_count=record_count
                )
                
                return json_data
                
            except ValueError as e:
                log_api_request(
                    logger=logger,
                    method='GET',
                    url=url,
                    status_code=response.status_code,
                    response_time=response_time,
                    error=f"JSON parsing error: {e}"
                )
                raise ParsingError(f"Failed to parse JSON response: {e}")
            
        except requests.exceptions.Timeout:
            response_time = time.time() - start_time
            log_api_request(logger, 'GET', url, 0, response_time, error="Request timeout")
            raise TransientError("Request timeout")
        except requests.exceptions.ConnectionError:
            response_time = time.time() - start_time
            log_api_request(logger, 'GET', url, 0, response_time, error="Connection error")
            raise TransientError("Connection error")
        except requests.exceptions.RequestException as e:
            response_time = time.time() - start_time
            log_api_request(logger, 'GET', url, 0, response_time, error=f"Network error: {e}")
            raise TransientError(f"Network error: {e}")

    @sleep_and_retry
    @limits(calls=1, period=1)  # 1 request per second
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make a rate-limited request with sophisticated error handling and retry logic
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            
        Returns:
            JSON response data
            
        Raises:
            RateLimitError: If rate limits exceeded after retries
            AuthenticationError: If IP not authorized
            PermanentError: For 4xx errors that shouldn't be retried
            TransientError: For network/server errors after retries
            ParsingError: If response cannot be parsed
        """
        return self._exponential_backoff_retry(
            self._make_request_internal, 
            endpoint, 
            params,
            max_retries=3
        )

    def search(self, 
               query: str,
               page: int = 1,
               per_page: int = 20,
               sort_option: str = "RELEVANCE",
               filters: Optional[Dict] = None) -> SearchResult:
        """
        Search the Discovery catalogue
        
        Args:
            query: Search terms
            page: Page number (1-based)
            per_page: Results per page (max 100)
            filters: Additional search filters
            
        Returns:
            SearchResult containing records and metadata
        """
        # Use CORRECT parameter names per API Bible Section 3.4
        params = {
            'sps.searchQuery': query,
            'sps.page': page - 1,  # Convert to 0-based for API
            'sps.resultsPageSize': min(per_page, 1000),  # API max is 1000
            'sps.sortByOption': sort_option
        }
        
        # Add TNA-compliant filters if provided
        if filters:
            for key, value in filters.items():
                if key.startswith('sps.'):
                    params[key] = value
                else:
                    # Convert common parameter names to TNA format
                    tna_key = self._convert_to_tna_param(key)
                    if tna_key:
                        params[tna_key] = value
        
        try:
            logger.debug(f"Searching with TNA-compliant params: {params}")
            data = self._make_request('search/v1/records', params)
            
            # Use correct field names from API Bible Section 4.1
            records_field = data.get('Records', data.get('records', []))
            records = [Record.from_api_response(record) for record in records_field]
            
            # Use correct field name for total count
            total_results = data.get('Count', data.get('totalResults', len(records)))
            
            return SearchResult(
                records=records,
                total_results=total_results,
                page=page,
                per_page=per_page,
                total_pages=max(1, (total_results + per_page - 1) // per_page),
                query=query,
                facets=data.get('facets', {})
            )
            
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            raise

    def _convert_to_tna_param(self, param_name: str) -> Optional[str]:
        """Convert common parameter names to TNA API format (API Bible Section 3.4)"""
        param_mapping = {
            'date_from': 'sps.dateFrom',
            'date_to': 'sps.dateTo', 
            'departments': 'sps.departments',
            'catalogue_levels': 'sps.catalogueLevels',
            'closure_statuses': 'sps.closureStatuses',
            'held_by_code': 'sps.heldByCode',
            'online_only': 'sps.online',
            'search_restriction_fields': 'sps.searchRestrictionFields'
        }
        return param_mapping.get(param_name)

    def search_record_series(self,
                           series: str,
                           page: int = 0,
                           results_page_size: int = 100) -> Dict:
        """
        Search for records in a specific record series (e.g., 'CO 1')
        
        Uses the search/v1/records endpoint with Discovery API-specific parameters:
        - sps.recordSeries: The record series code
        - sps.page: For pagination (start with 0)
        - sps.resultsPageSize: Number of results per page (max 1000)
        
        Args:
            series: Record series code (e.g., 'CO 1', 'WO 95', etc.)
            page: Page number for pagination (start with 0)
            results_page_size: Number of results per page (max 1000)
            
        Returns:
            Raw API response containing records and count for pagination
        """
        params = {
            'sps.recordSeries': series,
            'sps.page': page,
            'sps.resultsPageSize': min(results_page_size, 1000)
        }
        
        try:
            # Use the search/v1/records endpoint with Discovery API parameters
            return self._make_request('search/v1/records', params)
        except Exception as e:
            logger.error(f"Record series search failed for {series}: {e}")
            raise

    def get_record(self, record_id: str) -> Optional[Record]:
        """
        Get a specific record by ID using the CORRECT TNA API endpoint
        (API Bible Section 3.2: GET /records/v1/details/{id})
        
        Args:
            record_id: The record identifier (e.g., 'C243')
            
        Returns:
            Record object or None if not found
        """
        try:
            data = self._make_request(f'records/v1/details/{record_id}')
            return Record.from_api_response(data)
        except PermanentError as e:
            if "not found" in str(e).lower():
                return None
            raise
        except (TransientError, RateLimitError, AuthenticationError):
            # Re-raise these to be handled by caller
            raise

    def get_record_children(self, parent_id: str) -> List[Record]:
        """
        Get child records using official TNA endpoint
        (API Bible Section 3.2: GET /records/v1/children/{parentId})
        
        Args:
            parent_id: Parent record ID
            
        Returns:
            List of child Record objects
        """
        try:
            data = self._make_request(f'records/v1/children/{parent_id}')
            records_field = data.get('Records', data.get('records', []))
            return [Record.from_api_response(record) for record in records_field]
        except PermanentError as e:
            if "not found" in str(e).lower():
                return []
            raise
        except (TransientError, RateLimitError, AuthenticationError):
            raise

    def get_record_context(self, record_id: str) -> Dict[str, Any]:
        """
        Get full hierarchical context using official TNA endpoint
        (API Bible Section 3.2: GET /records/v1/context/{id})
        
        Args:
            record_id: Record ID
            
        Returns:
            Hierarchical context data
        """
        try:
            return self._make_request(f'records/v1/context/{record_id}')
        except PermanentError as e:
            if "not found" in str(e).lower():
                return {}
            raise
        except (TransientError, RateLimitError, AuthenticationError):
            raise

    def get_record_collection(self, reference: str) -> List[Record]:
        """
        Get collection of records with same citable reference
        (API Bible Section 3.2: GET /records/v1/collection/{reference})
        
        Args:
            reference: Citable reference (e.g., 'WO 32')
            
        Returns:
            List of Record objects with matching reference
        """
        try:
            data = self._make_request(f'records/v1/collection/{reference}')
            records_field = data.get('Records', data.get('records', []))
            return [Record.from_api_response(record) for record in records_field]
        except PermanentError as e:
            if "not found" in str(e).lower():
                return []
            raise
        except (TransientError, RateLimitError, AuthenticationError):
            raise

    def enrich_record_metadata(self, record_id: str) -> Optional[Record]:
        """
        Enrich a record with detailed metadata using the detailed record endpoint
        
        Args:
            record_id: The record identifier (e.g., 'C243')
            
        Returns:
            Enriched Record object or None if not found
        """
        try:
            # Use the detailed record endpoint for rich metadata
            data = self._make_request(f'records/v1/details/{record_id}')
            return Record.from_api_response(data)
        except PermanentError as e:
            if "not found" in str(e).lower():
                return None
            raise
        except (TransientError, RateLimitError, AuthenticationError):
            # Re-raise these to be handled by caller
            raise

    def batch_enrich_metadata(self, record_ids: List[str], 
                             batch_size: int = 10) -> List[Record]:
        """
        Enrich multiple records with detailed metadata in batches
        
        Args:
            record_ids: List of record identifiers
            batch_size: Number of records to process per batch
            
        Returns:
            List of enriched Record objects
        """
        enriched_records = []
        
        for i in range(0, len(record_ids), batch_size):
            batch = record_ids[i:i + batch_size]
            logger.info(f"Enriching metadata for batch {i//batch_size + 1}: {len(batch)} records")
            
            for record_id in batch:
                try:
                    enriched_record = self.enrich_record_metadata(record_id)
                    if enriched_record:
                        enriched_records.append(enriched_record)
                    
                    # Rate limiting
                    time.sleep(1.0 / self.requests_per_second)
                    
                except Exception as e:
                    logger.warning(f"Failed to enrich record {record_id}: {e}")
                    continue
            
            # Batch-level rate limiting
            time.sleep(2)
        
        logger.info(f"Successfully enriched {len(enriched_records)} out of {len(record_ids)} records")
        return enriched_records

    def browse_collection(self, 
                         collection_id: str,
                         page: int = 1,
                         per_page: int = 20) -> SearchResult:
        """
        Browse records within a specific collection
        
        Args:
            collection_id: Collection identifier
            page: Page number
            per_page: Results per page
            
        Returns:
            SearchResult for the collection
        """
        params = {
            'collection': collection_id,
            'page': page,
            'size': min(per_page, 100)
        }
        
        data = self._make_request('browse', params)
        
        records = [Record.from_api_response(record) 
                  for record in data.get('records', [])]
        
        return SearchResult(
            records=records,
            total_results=data.get('totalResults', 0),
            page=page,
            per_page=per_page,
            total_pages=data.get('totalPages', 0),
            query=f"collection:{collection_id}"
        )

    def get_collections(self) -> List[Collection]:
        """
        Get list of available collections
        
        Returns:
            List of Collection objects
        """
        try:
            data = self._make_request('collections')
            return [Collection.from_api_response(coll) 
                   for coll in data.get('collections', [])]
        except Exception as e:
            logger.error(f"Failed to fetch collections: {e}")
            return []

    def search_all_pages(self, 
                        query: str,
                        max_pages: Optional[int] = None,
                        per_page: int = 100) -> Iterator[Record]:
        """
        Search and yield all records across multiple pages
        
        Args:
            query: Search terms
            max_pages: Maximum pages to fetch (None for all)
            per_page: Results per page
            
        Yields:
            Individual Record objects
        """
        page = 1
        
        while True:
            if max_pages and page > max_pages:
                break
                
            try:
                result = self.search(query, page=page, per_page=per_page)
                
                if not result.records:
                    break
                
                for record in result.records:
                    yield record
                
                if page >= result.total_pages:
                    break
                    
                page += 1
                
                # Progress logging
                if page % 10 == 0:
                    logger.info(f"Processed {page} pages for query: {query}")
                    
            except Exception as e:
                logger.error(f"Error on page {page} for query '{query}': {e}")
                break

    def get_record_details(self, record_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed metadata for a specific record using the records API endpoint
        
        Args:
            record_id: The record ID (e.g., 'C332121')
            
        Returns:
            Detailed record data as dictionary, or None if failed
        """
        try:
            # Use the records/v1/details/{id} endpoint for detailed metadata
            endpoint = f"records/v1/details/{record_id}"
            
            # Make the request with proper rate limiting
            response = self._make_request(endpoint)
            
            if response:
                logger.info(f"Successfully fetched detailed metadata for record {record_id}")
                return response
            else:
                logger.warning(f"No detailed metadata returned for record {record_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch detailed metadata for record {record_id}: {e}")
            return None

    def get_popular_searches(self) -> List[str]:
        """Get list of popular search terms from the Discovery homepage"""
        return [
            "World War One army service records",
            "Passenger lists", 
            "Merchant navy service",
            "World War One army war diaries",
            "Poor law",
            "Naturalisation",
            "Muster books",
            "Medals",
            "Wills",
            "Royal Navy service records",
            "RAF combat reports",
            "Royal Marines' service records"
        ]

    def close(self):
        """Close the HTTP session"""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


