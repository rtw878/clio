"""
Intelligent query processing for National Archives searches
Handles query parsing, expansion, and optimization
"""

import re
import logging
from typing import List, Dict, Tuple, Optional, Set
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class QueryProcessor:
    """
    Processes and enhances search queries for better results
    
    Provides query parsing, expansion, date extraction, and
    intelligent query suggestions for National Archives searches.
    """
    
    def __init__(self):
        """Initialize query processor with historical terms and patterns"""
        
        # Historical date patterns
        self.date_patterns = [
            r'\b(\d{4})\b',  # Year
            r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',  # MM/DD/YYYY
            r'\b(\d{1,2})-(\d{1,2})-(\d{4})\b',  # MM-DD-YYYY
            r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b',  # YYYY-MM-DD
            r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s+(\d{4})\b',
            r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b',
            r'\b(early|mid|late)\s+(\d{4})\b',
            r'\bc\.?\s*(\d{4})\b',  # circa
            r'\b(\d{4})s\b'  # 1940s
        ]
        
        # Military and historical term expansions
        self.term_expansions = {
            'ww1': ['World War 1', 'World War One', 'First World War', 'Great War'],
            'ww2': ['World War 2', 'World War Two', 'Second World War'],
            'wwi': ['World War 1', 'World War One', 'First World War'],
            'wwii': ['World War 2', 'World War Two', 'Second World War'],
            'navy': ['Royal Navy', 'naval', 'maritime', 'ship', 'vessel'],
            'army': ['British Army', 'military', 'regiment', 'battalion', 'infantry'],
            'raf': ['Royal Air Force', 'RAF', 'air force', 'aviation', 'aircraft'],
            'service': ['service record', 'military service', 'war service'],
            'medal': ['decoration', 'honour', 'award', 'military medal'],
            'parish': ['church', 'religious', 'ecclesiastical', 'parochial'],
            'census': ['population', 'household', 'enumeration'],
            'will': ['testament', 'probate', 'inheritance', 'legacy'],
            'birth': ['baptism', 'christening', 'nativity'],
            'death': ['burial', 'funeral', 'mortality', 'deceased'],
            'marriage': ['wedding', 'matrimony', 'spouse', 'union']
        }
        
        # Common archival subjects
        self.archival_subjects = {
            'genealogy': ['family history', 'ancestry', 'lineage', 'pedigree'],
            'immigration': ['passenger list', 'emigration', 'migration', 'naturalisation'],
            'legal': ['court', 'legal proceeding', 'lawsuit', 'trial'],
            'property': ['land', 'estate', 'property deed', 'conveyance'],
            'trade': ['merchant', 'commerce', 'business', 'occupation'],
            'colonial': ['empire', 'colony', 'dominion', 'overseas'],
            'education': ['school', 'university', 'academic', 'learning'],
            'medical': ['hospital', 'health', 'medicine', 'doctor']
        }
        
        # Reference number patterns
        self.reference_patterns = [
            r'\b[A-Z]{1,4}\s*\d+/\d+\b',  # ADM 1/123
            r'\b[A-Z]{1,4}\s*\d+\b',      # WO 95
            r'\b[A-Z]+\s*\d+/[A-Z]\d+\b', # PREM 1/A123
            r'\bC\s*\d+/\d+\b',           # C 54/1234
            r'\bE\s*\d+/\d+\b'            # E 179/123
        ]

    def process_query(self, query: str) -> Dict:
        """
        Process and analyze a search query
        
        Args:
            query: Raw search query
            
        Returns:
            Dictionary with processed query components
        """
        processed = {
            'original_query': query,
            'cleaned_query': self._clean_query(query),
            'expanded_terms': [],
            'extracted_dates': [],
            'extracted_references': [],
            'suggested_filters': {},
            'query_type': self._classify_query(query),
            'enhanced_query': ''
        }
        
        # Extract dates
        processed['extracted_dates'] = self._extract_dates(query)
        
        # Extract reference numbers
        processed['extracted_references'] = self._extract_references(query)
        
        # Expand terms
        processed['expanded_terms'] = self._expand_terms(query)
        
        # Suggest filters
        processed['suggested_filters'] = self._suggest_filters(query)
        
        # Create enhanced query
        processed['enhanced_query'] = self._create_enhanced_query(processed)
        
        return processed

    def _clean_query(self, query: str) -> str:
        """Clean and normalize query text"""
        
        # Convert to lowercase
        cleaned = query.lower().strip()
        
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Handle common abbreviations
        abbreviations = {
            'st.': 'saint',
            'st ': 'saint ',
            'ltd.': 'limited',
            'co.': 'company',
            'inc.': 'incorporated',
            '&': 'and'
        }
        
        for abbrev, full in abbreviations.items():
            cleaned = cleaned.replace(abbrev, full)
        
        return cleaned.strip()

    def _classify_query(self, query: str) -> str:
        """
        Classify the type of search query
        
        Args:
            query: Search query
            
        Returns:
            Query type classification
        """
        query_lower = query.lower()
        
        # Check for reference number search
        if any(re.search(pattern, query, re.IGNORECASE) for pattern in self.reference_patterns):
            return 'reference_search'
        
        # Check for name search
        if re.search(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', query):
            return 'name_search'
        
        # Check for date range search
        if len(self._extract_dates(query)) > 0:
            return 'date_search'
        
        # Check for military service search
        military_terms = ['service', 'army', 'navy', 'air force', 'raf', 'regiment', 'battalion']
        if any(term in query_lower for term in military_terms):
            return 'military_search'
        
        # Check for genealogy search
        genealogy_terms = ['birth', 'death', 'marriage', 'baptism', 'burial', 'will', 'census']
        if any(term in query_lower for term in genealogy_terms):
            return 'genealogy_search'
        
        # Check for place search
        if 'london' in query_lower or 'england' in query_lower or re.search(r'\b[A-Z][a-z]+shire\b', query):
            return 'place_search'
        
        return 'general_search'

    def _extract_dates(self, query: str) -> List[Dict]:
        """
        Extract date information from query
        
        Args:
            query: Search query
            
        Returns:
            List of extracted date dictionaries
        """
        dates = []
        
        for pattern in self.date_patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE)
            
            for match in matches:
                date_info = {
                    'raw_text': match.group(0),
                    'start_pos': match.start(),
                    'end_pos': match.end(),
                    'type': 'unknown'
                }
                
                # Try to parse the date
                try:
                    if len(match.groups()) == 1:  # Simple year
                        year = int(match.group(1))
                        date_info['year'] = year
                        date_info['type'] = 'year'
                    elif len(match.groups()) == 3:  # Full date
                        date_info['type'] = 'full_date'
                        # Additional parsing logic would go here
                    
                    dates.append(date_info)
                    
                except ValueError:
                    continue
        
        return dates

    def _extract_references(self, query: str) -> List[str]:
        """Extract archive reference numbers from query"""
        
        references = []
        
        for pattern in self.reference_patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE)
            
            for match in matches:
                ref = match.group(0).upper().replace(' ', '')
                references.append(ref)
        
        return references

    def _expand_terms(self, query: str) -> List[str]:
        """
        Expand query terms with synonyms and related terms
        
        Args:
            query: Search query
            
        Returns:
            List of expanded terms
        """
        expanded = []
        query_lower = query.lower()
        
        # Check for term expansions
        for term, expansions in self.term_expansions.items():
            if term in query_lower:
                expanded.extend(expansions)
        
        # Check for archival subjects
        for subject, related_terms in self.archival_subjects.items():
            if subject in query_lower:
                expanded.extend(related_terms)
        
        return list(set(expanded))  # Remove duplicates

    def _suggest_filters(self, query: str) -> Dict:
        """
        Suggest appropriate filters based on query content
        
        Args:
            query: Search query
            
        Returns:
            Dictionary of suggested filters
        """
        filters = {}
        query_lower = query.lower()
        
        # Archive suggestions
        if 'war office' in query_lower or 'wo ' in query_lower:
            filters['archive'] = 'The National Archives'
            filters['collection_hint'] = 'War Office records'
        
        elif 'admiralty' in query_lower or 'adm ' in query_lower:
            filters['archive'] = 'The National Archives'
            filters['collection_hint'] = 'Admiralty records'
        
        elif 'air ministry' in query_lower or 'air ' in query_lower:
            filters['archive'] = 'The National Archives'
            filters['collection_hint'] = 'Air Ministry records'
        
        # Date range suggestions
        dates = self._extract_dates(query)
        if dates:
            # Use first extracted date
            date = dates[0]
            if 'year' in date:
                filters['date_from'] = str(date['year'])
                filters['date_to'] = str(date['year'])
        
        # Military service suggestions
        if any(term in query_lower for term in ['service record', 'military service']):
            filters['subjects_hint'] = 'Military service records'
        
        return filters

    def _create_enhanced_query(self, processed: Dict) -> str:
        """
        Create an enhanced search query with expanded terms
        
        Args:
            processed: Processed query dictionary
            
        Returns:
            Enhanced query string
        """
        enhanced_parts = [processed['cleaned_query']]
        
        # Add expanded terms
        if processed['expanded_terms']:
            # Add most relevant expanded terms (limit to avoid over-expansion)
            relevant_expansions = processed['expanded_terms'][:5]
            enhanced_parts.extend(relevant_expansions)
        
        # Create final enhanced query
        enhanced = ' '.join(enhanced_parts)
        
        # Remove duplicates while preserving order
        words = enhanced.split()
        seen = set()
        unique_words = []
        
        for word in words:
            if word.lower() not in seen:
                unique_words.append(word)
                seen.add(word.lower())
        
        return ' '.join(unique_words)

    def suggest_related_queries(self, query: str, query_type: str = None) -> List[str]:
        """
        Suggest related queries based on the original query
        
        Args:
            query: Original search query
            query_type: Classified query type
            
        Returns:
            List of suggested related queries
        """
        if query_type is None:
            query_type = self._classify_query(query)
        
        suggestions = []
        query_lower = query.lower()
        
        if query_type == 'military_search':
            if 'army' in query_lower:
                suggestions.extend([
                    query.replace('army', 'navy'),
                    query.replace('army', 'air force'),
                    query + ' medal',
                    query + ' war diary'
                ])
            
            if 'service' in query_lower:
                suggestions.extend([
                    query + ' record',
                    query.replace('service', 'pension'),
                    query.replace('service', 'medal')
                ])
        
        elif query_type == 'genealogy_search':
            base_terms = ['birth', 'marriage', 'death', 'will', 'census']
            for term in base_terms:
                if term not in query_lower:
                    suggestions.append(query + ' ' + term)
        
        elif query_type == 'name_search':
            suggestions.extend([
                query + ' birth',
                query + ' death',
                query + ' marriage',
                query + ' service record',
                query + ' will'
            ])
        
        # Generic suggestions
        suggestions.extend([
            query + ' records',
            query + ' documents',
            'early ' + query,
            'late ' + query
        ])
        
        # Remove duplicates and limit
        unique_suggestions = list(set(suggestions))
        return unique_suggestions[:8]

    def extract_entities(self, query: str) -> Dict:
        """
        Extract named entities from the query
        
        Args:
            query: Search query
            
        Returns:
            Dictionary of extracted entities
        """
        entities = {
            'people': [],
            'places': [],
            'organizations': [],
            'dates': [],
            'references': []
        }
        
        # Extract people (simple pattern matching)
        person_pattern = r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'
        people = re.findall(person_pattern, query)
        entities['people'] = people
        
        # Extract places (basic UK place recognition)
        place_patterns = [
            r'\b[A-Z][a-z]+shire\b',  # Counties
            r'\bLondon\b',
            r'\bEngland\b',
            r'\bScotland\b',
            r'\bWales\b',
            r'\bIreland\b'
        ]
        
        for pattern in place_patterns:
            places = re.findall(pattern, query, re.IGNORECASE)
            entities['places'].extend(places)
        
        # Extract organizations
        org_patterns = [
            r'\b\w+ Regiment\b',
            r'\b\w+ Battalion\b',
            r'\bRoyal \w+\b',
            r'\b\w+ Company\b'
        ]
        
        for pattern in org_patterns:
            orgs = re.findall(pattern, query, re.IGNORECASE)
            entities['organizations'].extend(orgs)
        
        # Use already implemented date and reference extraction
        entities['dates'] = self._extract_dates(query)
        entities['references'] = self._extract_references(query)
        
        return entities

    def optimize_for_archive_search(self, query: str) -> str:
        """
        Optimize query specifically for archive searches
        
        Args:
            query: Original query
            
        Returns:
            Optimized query for archive search systems
        """
        # Process the query
        processed = self.process_query(query)
        
        # Start with enhanced query
        optimized = processed['enhanced_query']
        
        # Add archival context terms
        archival_boost_terms = []
        
        if processed['query_type'] == 'military_search':
            archival_boost_terms.extend(['record', 'service', 'military'])
        
        elif processed['query_type'] == 'genealogy_search':
            archival_boost_terms.extend(['register', 'record', 'certificate'])
        
        # Add reference numbers if found
        if processed['extracted_references']:
            optimized = ' '.join(processed['extracted_references']) + ' ' + optimized
        
        # Add boost terms
        if archival_boost_terms:
            optimized += ' ' + ' '.join(archival_boost_terms)
        
        return optimized.strip()
