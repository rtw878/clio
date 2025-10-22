"""
Web Scraping Fallback System for National Archives Discovery Clone

Implements Workflow.md Section 2.3: Contingency Web Scraping Strategy
Provides robust fallback when API is unavailable or incomplete
"""

import logging
import time
import re
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urljoin, urlparse
from datetime import datetime
import json

import requests
from bs4 import BeautifulSoup, Tag

from .models import Record
from .client import PermanentError, TransientError, RateLimitError
from utils.logging_config import get_contextual_logger

logger = logging.getLogger(__name__)


class ScrapingError(Exception):
    """Base exception for scraping errors"""
    pass


class ParseError(ScrapingError):
    """Raised when HTML parsing fails"""
    pass


class NavigationError(ScrapingError):
    """Raised when navigation through site structure fails"""
    pass


class DiscoveryScraper:
    """
    Web scraper for TNA Discovery website
    
    Implements Workflow.md scraping strategy:
    - Hierarchical navigation through archival structure
    - Metadata extraction from HTML pages
    - Child record discovery
    - Fallback for API failures
    """
    
    def __init__(self, delay_between_requests: float = 2.0):
        """
        Initialize the Discovery scraper
        
        Args:
            delay_between_requests: Delay between requests to be respectful
        """
        self.base_url = 'https://discovery.nationalarchives.gov.uk'
        self.delay = delay_between_requests
        self.session = requests.Session()
        
        # Set respectful headers
        self.session.headers.update({
            'User-Agent': 'NationalArchivesClone/2.0 WebScraper (Educational Research - ryan.walmsley@example.com)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # CSS selectors for metadata extraction (would need to be refined based on actual TNA HTML)
        self.selectors = self._init_selectors()
        
        self.logger = get_contextual_logger('api.scraper')
        
        logger.info("Initialized Discovery web scraper with respectful delays")
    
    def _init_selectors(self) -> Dict[str, str]:
        """
        Initialize CSS selectors for metadata extraction
        
        Note: These are example selectors and would need to be updated
        based on actual TNA Discovery website HTML structure
        """
        return {
            'title': '.record-title, h1.title, .title',
            'reference': '.reference-code, .ref-code, .reference',
            'description': '.description, .scope-content, .summary',
            'dates': '.covering-dates, .dates, .date-range',
            'level': '.level, .archival-level, .record-level',
            'held_by': '.held-by, .repository, .archive',
            'subjects': '.subjects li, .subject-tags .tag',
            'creators': '.creators li, .creator-tags .tag',
            'places': '.places li, .place-tags .tag',
            'child_links': '.child-records a, .children a, .browse-children a',
            'record_count': '.record-count, .total-records, .result-count',
            'pagination': '.pagination, .pager',
            'closure_status': '.closure-status, .access-status',
            'former_reference': '.former-reference, .previous-ref',
            'arrangement': '.arrangement, .organization',
            'admin_history': '.admin-history, .administrative-background'
        }
    
    def get_record_by_id(self, record_id: str) -> Optional[Record]:
        """
        Scrape a single record by its Discovery ID
        
        Args:
            record_id: TNA Discovery record ID (e.g., 'C243')
            
        Returns:
            Record object or None if not found/error
        """
        url = f"{self.base_url}/details/r/{record_id}"
        
        try:
            self.logger.info(f"Scraping record: {record_id}")
            html = self._fetch_page(url)
            
            if not html:
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            record_data = self._extract_record_metadata(soup, record_id, url)
            
            if not record_data:
                return None
            
            # Create Record object with scraping provenance
            record = Record.from_api_response(record_data)
            record.provenance.update({
                'source_method': 'Scraper',
                'source_url': url,
                'retrieved_at': datetime.now().isoformat(),
                'parser_version': '2.0.0-scraper',
                'html_title': soup.title.string if soup.title else None
            })
            
            return record
            
        except Exception as e:
            self.logger.error(f"Error scraping record {record_id}: {e}")
            return None
    
    def discover_child_records(self, parent_record_id: str) -> List[Dict[str, str]]:
        """
        Discover child records by scraping the parent record's page
        
        Implements Workflow.md "Step 4: Discover and Queue Children"
        
        Args:
            parent_record_id: ID of parent record
            
        Returns:
            List of child record info dicts with 'id' and 'url' keys
        """
        url = f"{self.base_url}/details/r/{parent_record_id}"
        children = []
        
        try:
            self.logger.info(f"Discovering children for: {parent_record_id}")
            html = self._fetch_page(url)
            
            if not html:
                return children
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for child record links using multiple strategies
            child_links = self._find_child_links(soup)
            
            for link in child_links:
                child_info = self._extract_child_info(link)
                if child_info:
                    children.append(child_info)
            
            self.logger.info(f"Found {len(children)} children for {parent_record_id}")
            return children
            
        except Exception as e:
            self.logger.error(f"Error discovering children for {parent_record_id}: {e}")
            return children
    
    def get_series_record_count(self, series_id: str) -> Optional[int]:
        """
        Get the official record count for a series from TNA website
        
        Used for validation against local database counts
        
        Args:
            series_id: Series ID (e.g., 'C243' for CO 1)
            
        Returns:
            Record count or None if not found
        """
        url = f"{self.base_url}/details/r/{series_id}"
        
        try:
            html = self._fetch_page(url)
            if not html:
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try multiple methods to find record count
            count = self._extract_record_count(soup)
            
            if count:
                self.logger.info(f"Found record count for {series_id}: {count}")
            
            return count
            
        except Exception as e:
            self.logger.error(f"Error getting record count for {series_id}: {e}")
            return None
    
    def search_records(self, query: str, max_pages: int = 5) -> List[Dict[str, Any]]:
        """
        Search for records using the Discovery website search
        
        Fallback for API search functionality
        
        Args:
            query: Search query string
            max_pages: Maximum pages to scrape
            
        Returns:
            List of record metadata dicts
        """
        search_url = f"{self.base_url}/search/records"
        records = []
        
        try:
            for page in range(1, max_pages + 1):
                params = {
                    'query': query,
                    'page': page
                }
                
                html = self._fetch_page(search_url, params)
                if not html:
                    break
                
                soup = BeautifulSoup(html, 'html.parser')
                page_records = self._extract_search_results(soup)
                
                if not page_records:
                    break
                
                records.extend(page_records)
                
                # Check if there are more pages
                if not self._has_next_page(soup):
                    break
                
                self._respectful_delay()
            
            self.logger.info(f"Scraped {len(records)} records for query: {query}")
            return records
            
        except Exception as e:
            self.logger.error(f"Error searching records: {e}")
            return records
    
    def _fetch_page(self, url: str, params: Optional[Dict] = None) -> Optional[str]:
        """
        Fetch a single page with error handling and respectful delays
        
        Args:
            url: URL to fetch
            params: Query parameters
            
        Returns:
            HTML content or None on error
        """
        try:
            self._respectful_delay()
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.text
            elif response.status_code == 404:
                self.logger.warning(f"Page not found: {url}")
                return None
            elif response.status_code == 429:
                self.logger.warning(f"Rate limited, backing off: {url}")
                time.sleep(60)  # Back off for 1 minute
                return None
            else:
                self.logger.error(f"HTTP {response.status_code} for {url}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for {url}: {e}")
            return None
    
    def _extract_record_metadata(self, soup: BeautifulSoup, record_id: str, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract metadata from a record page
        
        Args:
            soup: BeautifulSoup object of the page
            record_id: Record ID
            url: Source URL
            
        Returns:
            Dictionary of extracted metadata
        """
        try:
            metadata = {
                'id': record_id,
                'source_url': url
            }
            
            # Extract title
            title_elem = soup.select_one(self.selectors['title'])
            if title_elem:
                metadata['title'] = self._clean_text(title_elem.get_text())
            
            # Extract reference
            ref_elem = soup.select_one(self.selectors['reference'])
            if ref_elem:
                metadata['reference'] = self._clean_text(ref_elem.get_text())
            
            # Extract description
            desc_elem = soup.select_one(self.selectors['description'])
            if desc_elem:
                metadata['description'] = self._clean_text(desc_elem.get_text())
            
            # Extract dates
            dates_elem = soup.select_one(self.selectors['dates'])
            if dates_elem:
                dates_text = self._clean_text(dates_elem.get_text())
                start_date, end_date = self._parse_date_range(dates_text)
                if start_date:
                    metadata['startDate'] = start_date
                if end_date:
                    metadata['endDate'] = end_date
            
            # Extract level
            level_elem = soup.select_one(self.selectors['level'])
            if level_elem:
                metadata['level'] = self._clean_text(level_elem.get_text())
            
            # Extract held by
            held_by_elem = soup.select_one(self.selectors['held_by'])
            if held_by_elem:
                metadata['heldBy'] = self._clean_text(held_by_elem.get_text())
            
            # Extract subjects (list)
            subject_elems = soup.select(self.selectors['subjects'])
            if subject_elems:
                metadata['taxonomies'] = [self._clean_text(elem.get_text()) for elem in subject_elems]
            
            # Extract creators (list)
            creator_elems = soup.select(self.selectors['creators'])
            if creator_elems:
                metadata['corpBodies'] = [self._clean_text(elem.get_text()) for elem in creator_elems]
            
            # Extract places (list)
            place_elems = soup.select(self.selectors['places'])
            if place_elems:
                metadata['places'] = [self._clean_text(elem.get_text()) for elem in place_elems]
            
            # Extract closure status
            closure_elem = soup.select_one(self.selectors['closure_status'])
            if closure_elem:
                metadata['closureStatus'] = self._clean_text(closure_elem.get_text())
            
            # Extract arrangement
            arrangement_elem = soup.select_one(self.selectors['arrangement'])
            if arrangement_elem:
                metadata['arrangement'] = self._clean_text(arrangement_elem.get_text())
            
            # Extract admin history
            admin_elem = soup.select_one(self.selectors['admin_history'])
            if admin_elem:
                metadata['adminHistory'] = self._clean_text(admin_elem.get_text())
            
            return metadata if metadata.get('title') else None
            
        except Exception as e:
            self.logger.error(f"Error extracting metadata: {e}")
            return None
    
    def _find_child_links(self, soup: BeautifulSoup) -> List[Tag]:
        """Find links to child records on a page"""
        child_links = []
        
        # Try multiple selectors for child links
        for selector in [
            self.selectors['child_links'],
            'a[href*="/details/r/"]',  # Generic record links
            '.browse-section a',       # Browse section links
            '.record-list a'           # Record list links
        ]:
            links = soup.select(selector)
            child_links.extend(links)
        
        # Filter for actual record detail links
        filtered_links = []
        for link in child_links:
            href = link.get('href', '')
            if '/details/r/' in href and href not in [l.get('href', '') for l in filtered_links]:
                filtered_links.append(link)
        
        return filtered_links
    
    def _extract_child_info(self, link: Tag) -> Optional[Dict[str, str]]:
        """Extract child record information from a link"""
        try:
            href = link.get('href', '')
            if not href:
                return None
            
            # Extract record ID from URL
            match = re.search(r'/details/r/([^/?]+)', href)
            if not match:
                return None
            
            record_id = match.group(1)
            full_url = urljoin(self.base_url, href)
            
            return {
                'id': record_id,
                'url': full_url,
                'title': self._clean_text(link.get_text())
            }
            
        except Exception as e:
            self.logger.error(f"Error extracting child info: {e}")
            return None
    
    def _extract_record_count(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract record count from a series page"""
        try:
            # Try multiple methods to find record count
            count_selectors = [
                self.selectors['record_count'],
                '.total-results',
                '.count',
                'text-containing-number'
            ]
            
            for selector in count_selectors:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text()
                    match = re.search(r'(\d+).*record', text, re.IGNORECASE)
                    if match:
                        return int(match.group(1))
            
            # Look for count in text content
            page_text = soup.get_text()
            patterns = [
                r'(\d+)\s+records?',
                r'(\d+)\s+items?',
                r'(\d+)\s+documents?',
                r'Contains\s+(\d+)',
                r'Total\s+(\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return int(match.group(1))
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting record count: {e}")
            return None
    
    def _extract_search_results(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract search results from search page"""
        results = []
        
        try:
            # Look for search result items
            result_items = soup.select('.search-result, .result-item, .record-item')
            
            for item in result_items:
                result_data = {}
                
                # Extract title and link
                title_link = item.select_one('a[href*="/details/r/"]')
                if title_link:
                    result_data['title'] = self._clean_text(title_link.get_text())
                    href = title_link.get('href', '')
                    
                    # Extract ID from URL
                    match = re.search(r'/details/r/([^/?]+)', href)
                    if match:
                        result_data['id'] = match.group(1)
                
                # Extract other metadata visible in search results
                ref_elem = item.select_one('.reference, .ref')
                if ref_elem:
                    result_data['reference'] = self._clean_text(ref_elem.get_text())
                
                desc_elem = item.select_one('.description, .summary')
                if desc_elem:
                    result_data['description'] = self._clean_text(desc_elem.get_text())
                
                if result_data.get('id'):
                    results.append(result_data)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error extracting search results: {e}")
            return []
    
    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        """Check if there's a next page in pagination"""
        try:
            next_link = soup.select_one('.pagination .next, .pager .next, a[title*="Next"]')
            return next_link is not None
        except Exception:
            return False
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text"""
        if not text:
            return ''
        
        # Remove extra whitespace and normalize
        cleaned = re.sub(r'\s+', ' ', text.strip())
        return cleaned
    
    def _parse_date_range(self, date_text: str) -> tuple[Optional[str], Optional[str]]:
        """Parse date range text into start and end dates"""
        if not date_text:
            return None, None
        
        try:
            # Try to parse various date formats
            # This is simplified - would need more robust date parsing
            
            # Look for year ranges like "1574-1757"
            year_range_match = re.search(r'(\d{4})\s*[-–]\s*(\d{4})', date_text)
            if year_range_match:
                return year_range_match.group(1), year_range_match.group(2)
            
            # Look for single year
            year_match = re.search(r'(\d{4})', date_text)
            if year_match:
                return year_match.group(1), year_match.group(1)
            
            return None, None
            
        except Exception as e:
            self.logger.error(f"Error parsing date range '{date_text}': {e}")
            return None, None
    
    def _respectful_delay(self):
        """Add respectful delay between requests"""
        time.sleep(self.delay)


class HybridClient:
    """
    Hybrid client that tries API first, falls back to scraping
    
    Implements the complete Workflow.md strategy for robust data collection
    """
    
    def __init__(self, api_client, scraper: Optional[DiscoveryScraper] = None):
        """
        Initialize hybrid client
        
        Args:
            api_client: DiscoveryClient instance
            scraper: DiscoveryScraper instance (optional)
        """
        self.api_client = api_client
        self.scraper = scraper or DiscoveryScraper()
        self.logger = get_contextual_logger('api.hybrid_client')
    
    def get_record_with_fallback(self, record_id: str) -> Optional[Record]:
        """
        Get record using API first, scraper as fallback
        
        Args:
            record_id: Record ID to fetch
            
        Returns:
            Record object or None
        """
        # Try API first
        try:
            self.logger.debug(f"Trying API for record {record_id}")
            record = self.api_client.get_record(record_id)
            if record:
                self.logger.info(f"✅ API success for {record_id}")
                return record
            else:
                self.logger.info(f"📝 API returned no record for {record_id}")
        except (PermanentError, RateLimitError, TransientError) as e:
            self.logger.warning(f"API failed for {record_id}: {e}")
        
        # Fall back to scraping
        try:
            self.logger.info(f"🌐 Falling back to scraping for {record_id}")
            record = self.scraper.get_record_by_id(record_id)
            if record:
                self.logger.info(f"✅ Scraping success for {record_id}")
                return record
            else:
                self.logger.warning(f"❌ Scraping failed for {record_id}")
        except Exception as e:
            self.logger.error(f"Scraping error for {record_id}: {e}")
        
        return None
    
    def discover_children_with_fallback(self, parent_id: str) -> List[Dict[str, str]]:
        """
        Discover child records with API/scraping fallback
        
        Args:
            parent_id: Parent record ID
            
        Returns:
            List of child record info
        """
        children = []
        
        # Try API series search first (if applicable)
        try:
            # This would use API series search if available
            # For now, go straight to scraping as it's more reliable for discovery
            pass
        except Exception as e:
            self.logger.warning(f"API child discovery failed for {parent_id}: {e}")
        
        # Use scraping for child discovery
        try:
            children = self.scraper.discover_child_records(parent_id)
            self.logger.info(f"Discovered {len(children)} children via scraping for {parent_id}")
        except Exception as e:
            self.logger.error(f"Scraping child discovery failed for {parent_id}: {e}")
        
        return children
