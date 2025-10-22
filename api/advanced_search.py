"""
Advanced Search Builder for TNA Discovery API

Implements full search syntax from API Bible Section 5.1
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AdvancedSearchBuilder:
    """
    Advanced search query builder implementing API Bible Section 5.1 search syntax
    
    Supports:
    - Boolean operators (AND, OR, NOT)
    - Exact phrase matching
    - Wildcard searches
    - Field-specific searching
    - Date range filtering
    - Department filtering
    - Closure status filtering
    """
    
    def __init__(self):
        """Initialize search builder"""
        self.query_parts: List[str] = []
        self.filters: Dict[str, Any] = {}
        self.field_restrictions: List[str] = []
        
        # Valid fields for field-specific search (API Bible Section 5.2)
        self.valid_fields = [
            'title', 'description', 'reference', 
            'people', 'places', 'subjects'
        ]
        
        # Valid sort options (API Bible Section 3.4)
        self.valid_sort_options = [
            'RELEVANCE', 'REFERENCE_ASCENDING', 'DATE_ASCENDING',
            'DATE_DESCENDING', 'TITLE_ASCENDING', 'TITLE_DESCENDING'
        ]
        
        logger.debug("Initialized AdvancedSearchBuilder")
    
    def reset(self) -> 'AdvancedSearchBuilder':
        """Reset the search builder to start fresh"""
        self.query_parts.clear()
        self.filters.clear()
        self.field_restrictions.clear()
        return self
    
    # === QUERY BUILDING METHODS ===
    
    def exact_phrase(self, phrase: str) -> 'AdvancedSearchBuilder':
        """
        Add exact phrase search (API Bible Section 5.1)
        
        Args:
            phrase: Exact phrase to search for
            
        Returns:
            Self for method chaining
            
        Example:
            builder.exact_phrase("Domesday Book")
            # Generates: "Domesday Book"
        """
        self.query_parts.append(f'"{phrase}"')
        logger.debug(f"Added exact phrase: {phrase}")
        return self
    
    def boolean_and(self, term1: str, term2: str) -> 'AdvancedSearchBuilder':
        """
        Add AND boolean operation
        
        Args:
            term1: First search term
            term2: Second search term
            
        Returns:
            Self for method chaining
            
        Example:
            builder.boolean_and("turing", "enigma")
            # Generates: (turing AND enigma)
        """
        self.query_parts.append(f"({term1} AND {term2})")
        logger.debug(f"Added AND query: {term1} AND {term2}")
        return self
    
    def boolean_or(self, term1: str, term2: str) -> 'AdvancedSearchBuilder':
        """
        Add OR boolean operation
        
        Args:
            term1: First search term
            term2: Second search term
            
        Returns:
            Self for method chaining
            
        Example:
            builder.boolean_or("spitfire", "hurricane")
            # Generates: (spitfire OR hurricane)
        """
        self.query_parts.append(f"({term1} OR {term2})")
        logger.debug(f"Added OR query: {term1} OR {term2}")
        return self
    
    def boolean_not(self, include_term: str, exclude_term: str) -> 'AdvancedSearchBuilder':
        """
        Add NOT boolean operation
        
        Args:
            include_term: Term to include
            exclude_term: Term to exclude
            
        Returns:
            Self for method chaining
            
        Example:
            builder.boolean_not("lancaster", "avro")
            # Generates: (lancaster NOT avro)
        """
        self.query_parts.append(f"({include_term} NOT {exclude_term})")
        logger.debug(f"Added NOT query: {include_term} NOT {exclude_term}")
        return self
    
    def wildcard(self, prefix: str) -> 'AdvancedSearchBuilder':
        """
        Add wildcard search (suffix wildcard only per API Bible)
        
        Args:
            prefix: Prefix to search for (will add * suffix)
            
        Returns:
            Self for method chaining
            
        Example:
            builder.wildcard("parliamen")
            # Generates: parliamen*
        """
        self.query_parts.append(f"{prefix}*")
        logger.debug(f"Added wildcard query: {prefix}*")
        return self
    
    def complex_boolean(self, expression: str) -> 'AdvancedSearchBuilder':
        """
        Add complex boolean expression with grouping
        
        Args:
            expression: Complex boolean expression
            
        Returns:
            Self for method chaining
            
        Example:
            builder.complex_boolean("(spitfire OR hurricane) AND dowding")
        """
        self.query_parts.append(f"({expression})")
        logger.debug(f"Added complex boolean: {expression}")
        return self
    
    def add_term(self, term: str) -> 'AdvancedSearchBuilder':
        """
        Add simple search term
        
        Args:
            term: Search term to add
            
        Returns:
            Self for method chaining
        """
        self.query_parts.append(term)
        logger.debug(f"Added term: {term}")
        return self
    
    # === FILTERING METHODS ===
    
    def add_date_range(self, start_year: int, end_year: int) -> 'AdvancedSearchBuilder':
        """
        Add date range filter (API Bible Section 5.3)
        
        Args:
            start_year: Start year (will use Jan 1)
            end_year: End year (will use Dec 31)
            
        Returns:
            Self for method chaining
        """
        self.filters['sps.dateFrom'] = f"{start_year}-01-01T00:00:00"
        self.filters['sps.dateTo'] = f"{end_year}-12-31T23:59:59"
        logger.debug(f"Added date range: {start_year} to {end_year}")
        return self
    
    def add_exact_date_range(self, start_date: str, end_date: str) -> 'AdvancedSearchBuilder':
        """
        Add exact date range with ISO format
        
        Args:
            start_date: Start date in ISO format (e.g., "1939-09-01T00:00:00")
            end_date: End date in ISO format
            
        Returns:
            Self for method chaining
        """
        self.filters['sps.dateFrom'] = start_date
        self.filters['sps.dateTo'] = end_date
        logger.debug(f"Added exact date range: {start_date} to {end_date}")
        return self
    
    def add_departments(self, dept_codes: List[str]) -> 'AdvancedSearchBuilder':
        """
        Add department filter (API Bible Section 5.3)
        
        Args:
            dept_codes: List of department codes (e.g., ["WO", "ADM", "AIR"])
            
        Returns:
            Self for method chaining
        """
        self.filters['sps.departments'] = dept_codes
        logger.debug(f"Added departments filter: {dept_codes}")
        return self
    
    def add_closure_status(self, statuses: List[str]) -> 'AdvancedSearchBuilder':
        """
        Add closure status filter (API Bible Section 5.3)
        
        Args:
            statuses: List of closure codes
                     O=Open, C=Closed, R=Retained, P=Pending
            
        Returns:
            Self for method chaining
        """
        valid_statuses = ['O', 'C', 'R', 'P']
        filtered_statuses = [s for s in statuses if s in valid_statuses]
        
        if filtered_statuses:
            self.filters['sps.closureStatuses'] = filtered_statuses
            logger.debug(f"Added closure status filter: {filtered_statuses}")
        else:
            logger.warning(f"No valid closure statuses in: {statuses}")
        
        return self
    
    def add_repository_filter(self, repo_code: str) -> 'AdvancedSearchBuilder':
        """
        Add repository filter (API Bible Section 5.3)
        
        Args:
            repo_code: Repository code (ALL/TNA/OTH)
            
        Returns:
            Self for method chaining
        """
        valid_codes = ['ALL', 'TNA', 'OTH']
        if repo_code in valid_codes:
            self.filters['sps.heldByCode'] = repo_code
            logger.debug(f"Added repository filter: {repo_code}")
        else:
            logger.warning(f"Invalid repository code: {repo_code}. Must be one of {valid_codes}")
        
        return self
    
    def add_catalogue_levels(self, levels: List[str]) -> 'AdvancedSearchBuilder':
        """
        Add catalogue level filter
        
        Args:
            levels: List of catalogue levels (e.g., ["Level6", "Level7"])
            
        Returns:
            Self for method chaining
        """
        self.filters['sps.catalogueLevels'] = levels
        logger.debug(f"Added catalogue levels filter: {levels}")
        return self
    
    def only_online(self, online_only: bool = True) -> 'AdvancedSearchBuilder':
        """
        Filter for records with downloadable versions only
        
        Args:
            online_only: If True, only returns records with downloadable versions
            
        Returns:
            Self for method chaining
        """
        self.filters['sps.online'] = online_only
        logger.debug(f"Added online filter: {online_only}")
        return self
    
    def restrict_to_fields(self, fields: List[str]) -> 'AdvancedSearchBuilder':
        """
        Restrict search to specific fields (API Bible Section 5.2)
        
        Args:
            fields: List of field names to search in
                   Valid: title, description, reference, people, places, subjects
            
        Returns:
            Self for method chaining
        """
        valid_fields = [f for f in fields if f in self.valid_fields]
        
        if valid_fields:
            self.field_restrictions = valid_fields
            logger.debug(f"Restricted search to fields: {valid_fields}")
        else:
            logger.warning(f"No valid fields in: {fields}. Valid fields: {self.valid_fields}")
        
        return self
    
    # === BUILD METHODS ===
    
    def build_query(self) -> str:
        """
        Build the search query string
        
        Returns:
            Complete search query string
        """
        if not self.query_parts:
            return ""
        
        # Join query parts with AND if multiple parts
        if len(self.query_parts) == 1:
            query = self.query_parts[0]
        else:
            query = " AND ".join(self.query_parts)
        
        logger.debug(f"Built query: {query}")
        return query
    
    def build_params(self, 
                    page: int = 0,
                    per_page: int = 20,
                    sort_option: str = "RELEVANCE") -> Dict[str, Any]:
        """
        Build complete search parameters dictionary
        
        Args:
            page: Page number (0-based)
            per_page: Results per page
            sort_option: Sort option
            
        Returns:
            Complete parameters dictionary for API call
        """
        if sort_option not in self.valid_sort_options:
            logger.warning(f"Invalid sort option: {sort_option}. Using RELEVANCE")
            sort_option = "RELEVANCE"
        
        params = {
            'sps.searchQuery': self.build_query(),
            'sps.page': page,
            'sps.resultsPageSize': min(per_page, 1000),  # API maximum
            'sps.sortByOption': sort_option
        }
        
        # Add filters
        params.update(self.filters)
        
        # Add field restrictions if specified
        if self.field_restrictions:
            params['sps.searchRestrictionFields'] = self.field_restrictions
        
        logger.debug(f"Built parameters: {params}")
        return params
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of current search configuration
        
        Returns:
            Summary dictionary
        """
        return {
            'query_parts': self.query_parts,
            'filters': self.filters,
            'field_restrictions': self.field_restrictions,
            'built_query': self.build_query()
        }


class SmartQueryBuilder(AdvancedSearchBuilder):
    """
    High-level query builder with smart defaults and common patterns
    
    Extends AdvancedSearchBuilder with convenience methods for common search patterns
    """
    
    def search_person(self, name: str, approximate: bool = False) -> 'SmartQueryBuilder':
        """
        Search for a person with smart field restrictions
        
        Args:
            name: Person's name
            approximate: If True, uses wildcard search
            
        Returns:
            Self for method chaining
        """
        self.restrict_to_fields(['people', 'title', 'description'])
        
        if approximate:
            # Split name and create wildcard searches
            name_parts = name.split()
            for part in name_parts:
                if len(part) > 3:  # Only wildcard longer names
                    self.wildcard(part)
                else:
                    self.add_term(part)
        else:
            self.exact_phrase(name)
        
        return self
    
    def search_place(self, place: str, approximate: bool = False) -> 'SmartQueryBuilder':
        """
        Search for a place with appropriate field restrictions
        
        Args:
            place: Place name
            approximate: If True, uses wildcard search
            
        Returns:
            Self for method chaining
        """
        self.restrict_to_fields(['places', 'title', 'description'])
        
        if approximate:
            self.wildcard(place)
        else:
            self.exact_phrase(place)
        
        return self
    
    def search_wwii_records(self) -> 'SmartQueryBuilder':
        """
        Pre-configured search for WWII records
        
        Returns:
            Self for method chaining
        """
        self.add_date_range(1939, 1945)
        self.add_departments(['WO', 'ADM', 'AIR', 'CAB'])
        self.add_closure_status(['O'])  # Open records only
        return self
    
    def search_wwi_records(self) -> 'SmartQueryBuilder':
        """
        Pre-configured search for WWI records
        
        Returns:
            Self for method chaining
        """
        self.add_date_range(1914, 1918)
        self.add_departments(['WO', 'ADM', 'AIR'])
        self.add_closure_status(['O'])  # Open records only
        return self
    
    def search_colonial_office(self, start_year: Optional[int] = None, end_year: Optional[int] = None) -> 'SmartQueryBuilder':
        """
        Pre-configured search for Colonial Office records
        
        Args:
            start_year: Optional start year filter
            end_year: Optional end year filter
            
        Returns:
            Self for method chaining
        """
        self.add_departments(['CO'])
        
        if start_year and end_year:
            self.add_date_range(start_year, end_year)
        
        return self
