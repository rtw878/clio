"""
Creator/File Authority Client for TNA Discovery API

Implements file authority endpoints from API Bible Section 3.1
"""

import logging
from typing import List, Dict, Any, Optional

from .client import DiscoveryClient, PermanentError, TransientError, RateLimitError

logger = logging.getLogger(__name__)


class CreatorClient:
    """
    Client for TNA File Authority/Creator endpoints
    
    Implements API Bible Section 3.1 endpoints:
    - GET /fileauthorities/v1/details/{id}
    - GET /fileauthorities/v1/collection/{type}
    """
    
    def __init__(self, api_client: Optional[DiscoveryClient] = None):
        """
        Initialize creator client
        
        Args:
            api_client: DiscoveryClient instance (will create new if None)
        """
        self.api_client = api_client or DiscoveryClient()
        self.logger = logging.getLogger(__name__)
        
        # Valid creator types from API Bible
        self.valid_types = ['Person', 'Business', 'Family', 'Manor', 'Organisation']
    
    def get_creator_details(self, creator_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information for a specific File Authority/Creator
        (API Bible Section 3.1: GET /fileauthorities/v1/details/{id})
        
        Args:
            creator_id: Creator identifier (e.g., 'C193', 'A12345')
            
        Returns:
            Creator details dictionary or None if not found
        """
        try:
            data = self.api_client._make_request(f'fileauthorities/v1/details/{creator_id}')
            self.logger.info(f"Retrieved creator details for {creator_id}")
            return data
        except PermanentError as e:
            if "not found" in str(e).lower():
                self.logger.warning(f"Creator {creator_id} not found")
                return None
            raise
        except (TransientError, RateLimitError) as e:
            self.logger.error(f"Error retrieving creator {creator_id}: {e}")
            raise
    
    def search_creators(self, 
                       creator_type: str, 
                       limit: int = 30,
                       direction: str = "NEXT",
                       batch_start_mark: Optional[str] = None) -> Dict[str, Any]:
        """
        Get file authority records collection by type
        (API Bible Section 3.1: GET /fileauthorities/v1/collection/{type})
        
        Args:
            creator_type: Type (Person/Business/Family/Manor/Organisation)
            limit: Number of records (1-500, default 30)
            direction: Paging direction (NEXT/PREV)
            batch_start_mark: For pagination
            
        Returns:
            Collection response with creators and pagination info
        """
        if creator_type not in self.valid_types:
            raise ValueError(f"Invalid creator type '{creator_type}'. Must be one of: {self.valid_types}")
        
        try:
            params = {
                'limit': min(max(limit, 1), 500),  # Enforce API limits (1-500)
                'direction': direction,
                'includeCursor': True
            }
            
            if batch_start_mark:
                params['batchStartMark'] = batch_start_mark
            
            data = self.api_client._make_request(f'fileauthorities/v1/collection/{creator_type}', params)
            
            creators = data.get('Creators', data.get('creators', []))
            self.logger.info(f"Retrieved {len(creators)} {creator_type} creators")
            
            return data
            
        except Exception as e:
            self.logger.error(f"Error searching {creator_type} creators: {e}")
            raise
    
    def get_all_creators_by_type(self, creator_type: str, max_pages: int = 10) -> List[Dict[str, Any]]:
        """
        Get all creators of a specific type across multiple pages
        
        Args:
            creator_type: Type of creator to retrieve
            max_pages: Maximum pages to fetch
            
        Returns:
            List of all creators retrieved
        """
        all_creators = []
        next_batch_mark = None
        page = 0
        
        while page < max_pages:
            try:
                response = self.search_creators(
                    creator_type=creator_type,
                    limit=500,  # Maximum per page
                    batch_start_mark=next_batch_mark
                )
                
                page_creators = response.get('Creators', response.get('creators', []))
                if not page_creators:
                    break
                
                all_creators.extend(page_creators)
                
                # Check for next page
                next_batch_mark = response.get('NextBatchMark')
                if not next_batch_mark:
                    break
                
                page += 1
                self.logger.info(f"Retrieved page {page}, total creators so far: {len(all_creators)}")
                
            except Exception as e:
                self.logger.error(f"Error on page {page}: {e}")
                break
        
        self.logger.info(f"Retrieved total of {len(all_creators)} {creator_type} creators")
        return all_creators
    
    def search_creators_by_name(self, name: str, creator_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for creators by name across types
        
        Args:
            name: Name to search for
            creator_type: Optional type filter
            
        Returns:
            List of matching creators
        """
        matching_creators = []
        name_lower = name.lower()
        
        types_to_search = [creator_type] if creator_type else self.valid_types
        
        for ctype in types_to_search:
            try:
                creators = self.get_all_creators_by_type(ctype, max_pages=5)  # Limit search scope
                
                for creator in creators:
                    creator_name = creator.get('AuthorityName', creator.get('Name', ''))
                    if name_lower in creator_name.lower():
                        creator['_search_type'] = ctype  # Add type for reference
                        matching_creators.append(creator)
                
            except Exception as e:
                self.logger.warning(f"Error searching {ctype} creators for name '{name}': {e}")
                continue
        
        self.logger.info(f"Found {len(matching_creators)} creators matching '{name}'")
        return matching_creators
    
    def get_creator_by_exact_name(self, name: str, creator_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Find creator by exact name match
        
        Args:
            name: Exact name to match
            creator_type: Optional type filter
            
        Returns:
            Creator details or None if not found
        """
        matches = self.search_creators_by_name(name, creator_type)
        
        for creator in matches:
            creator_name = creator.get('AuthorityName', creator.get('Name', ''))
            if creator_name == name:
                return creator
        
        return None
    
    def get_creator_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about creators by type
        
        Returns:
            Statistics dictionary
        """
        stats = {
            'by_type': {},
            'total_creators': 0,
            'types_available': self.valid_types
        }
        
        for creator_type in self.valid_types:
            try:
                # Get first page to estimate totals
                response = self.search_creators(creator_type, limit=1)
                type_total = response.get('TotalCount', len(response.get('Creators', [])))
                
                stats['by_type'][creator_type] = type_total
                stats['total_creators'] += type_total
                
            except Exception as e:
                self.logger.warning(f"Error getting stats for {creator_type}: {e}")
                stats['by_type'][creator_type] = 0
        
        self.logger.info(f"Creator statistics: {stats}")
        return stats
    
    def validate_creator_type(self, creator_type: str) -> bool:
        """
        Validate if creator type is supported
        
        Args:
            creator_type: Type to validate
            
        Returns:
            True if valid, False otherwise
        """
        return creator_type in self.valid_types
