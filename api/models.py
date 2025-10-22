"""
Data models for National Archives Discovery API responses
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import json
from datetime import datetime


@dataclass
class Record:
    """Represents a single archive record from the Discovery catalogue"""
    
    id: str
    title: str
    description: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    reference: Optional[str] = None
    archive: Optional[str] = None
    collection: Optional[str] = None
    subjects: List[str] = None
    creators: List[str] = None
    places: List[str] = None
    catalogue_source: Optional[str] = None
    access_conditions: Optional[str] = None
    closure_status: Optional[str] = None
    legal_status: Optional[str] = None
    held_by: Optional[str] = None
    former_reference: Optional[str] = None
    note: Optional[str] = None
    arrangement: Optional[str] = None
    dimensions: Optional[str] = None
    administrator_background: Optional[str] = None
    custodial_history: Optional[str] = None
    acquisition_information: Optional[str] = None
    appraisal_information: Optional[str] = None
    accruals: Optional[str] = None
    related_material: Optional[str] = None
    publication_note: Optional[str] = None
    copies_information: Optional[str] = None
    originals_held_elsewhere: Optional[str] = None
    unpublished_finding_aids: Optional[str] = None
    publications: Optional[str] = None
    map_designation: Optional[str] = None
    physical_description: Optional[str] = None
    immediate_source: Optional[str] = None
    scope_content: Optional[str] = None
    language: Optional[str] = None
    script: Optional[str] = None
    web_links: List[str] = None
    digital_files: List[str] = None
    
    # Hierarchical structure fields (from Workflow.md)
    parent_id: Optional[str] = None
    level: Optional[str] = None  # e.g., 'Series', 'Piece', 'Item', 'Department'
    child_count: Optional[int] = None
    
    # Provenance tracking (essential for scholarly integrity)
    provenance: Dict[str, Any] = field(default_factory=dict)
    
    # Additional fields from API Bible Section 4.1
    catalogue_level: Optional[int] = None  # Numeric level (6, 7, etc.)
    closure_code: Optional[str] = None
    digitised: Optional[bool] = None
    hierarchy: List[Dict[str, Any]] = field(default_factory=list)  # Parent context array
    covering_from_date: Optional[int] = None  # Numeric date
    covering_to_date: Optional[int] = None  # Numeric date
    
    # Enhanced TNA API metadata fields
    catalogue_id: Optional[int] = None  # Internal TNA catalogue identifier
    covering_dates: Optional[str] = None  # Human-readable date ranges
    is_parent: Optional[bool] = None  # Whether record has children
    
    def __post_init__(self):
        """Initialize empty lists for None values"""
        if self.subjects is None:
            self.subjects = []
        if self.creators is None:
            self.creators = []
        if self.places is None:
            self.places = []
        if self.web_links is None:
            self.web_links = []
        if self.digital_files is None:
            self.digital_files = []
        if self.hierarchy is None:
            self.hierarchy = []

    @classmethod
    def _parse_level(cls, level_value: Any) -> Optional[str]:
        """
        Parse level value from API response and convert to archival level name
        (API Bible Section 2.2 - Archival Hierarchy)
        """
        if not level_value:
            return None
            
        # Handle numeric levels (convert to standard archival level names)
        level_mapping = {
            0: "Department",
            1: "Division", 
            2: "Series",
            3: "Sub-series",
            4: "Sub sub-series", 
            5: "Piece",
            6: "Item"
        }
        
        # If it's already a string level name, return as-is
        if isinstance(level_value, str):
            # Check if it's a numeric string
            try:
                numeric_level = int(level_value)
                return level_mapping.get(numeric_level, level_value)
            except ValueError:
                # It's already a descriptive name
                if level_value in ["Department", "Division", "Series", "Sub-series", "Sub sub-series", "Piece", "Item"]:
                    return level_value
                else:
                    # Unknown string level, return as-is
                    return level_value
        
        # If it's a number, map it
        if isinstance(level_value, (int, float)):
            return level_mapping.get(int(level_value), f"Level{int(level_value)}")
        
        return str(level_value) if level_value else None

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> 'Record':
        """Create a Record instance from API response data"""
        
        # Handle heldBy field - can be list or string
        held_by_value = data.get('heldBy', '')
        if isinstance(held_by_value, list):
            # Handle list of dictionaries or strings
            held_by_items = []
            for item in held_by_value:
                if isinstance(item, dict):
                    # Extract name from dictionary
                    name = item.get('xReferenceName', '')
                    if name:
                        held_by_items.append(name)
                else:
                    # Handle string items
                    held_by_items.append(str(item))
            held_by_str = ', '.join(held_by_items) if held_by_items else ''
        else:
            held_by_str = str(held_by_value) if held_by_value else ''
        
        # Handle places - ensure it's a list
        places_value = data.get('places', [])
        if not isinstance(places_value, list):
            places_value = [str(places_value)] if places_value else []
        
        # Handle taxonomies as subjects
        subjects_value = data.get('taxonomies', [])
        if not isinstance(subjects_value, list):
            subjects_value = [str(subjects_value)] if subjects_value else []
        
        # Handle corpBodies as creators
        creators_value = data.get('corpBodies', [])
        if not isinstance(creators_value, list):
            creators_value = [str(creators_value)] if creators_value else []
        
        # Generate enhanced provenance metadata automatically
        from utils.provenance import enhanced_record_provenance
        
        record_id = data.get('id', '')
        source_url = f"https://discovery.nationalarchives.gov.uk/details/r/{record_id}"
        
        provenance_data = enhanced_record_provenance(
            record_id=record_id,
            source_method='API',
            source_url=source_url,
            raw_data_size=len(str(data)),
            additional_metadata={
                'api_endpoint': 'informationasset',
                'response_fields_count': len(data.keys()),
                'has_hierarchical_data': bool(data.get('parentId') or data.get('ParentIAID'))
            }
        )
        
        # Enhanced metadata extraction from TNA API
        scope_content_obj = data.get('scopeContent', {})
        scope_content_desc = scope_content_obj.get('description', '') if isinstance(scope_content_obj, dict) else ''
        
        # Enhanced held by information parsing
        held_by_enhanced = ''
        if isinstance(held_by_value, list) and held_by_value:
            held_by_details = []
            for held_by_item in held_by_value:
                if isinstance(held_by_item, dict):
                    name = held_by_item.get('xReferenceName', '')
                    if name:
                        held_by_details.append(name)
            held_by_enhanced = ', '.join(held_by_details) if held_by_details else held_by_str
        else:
            held_by_enhanced = held_by_str
        
        return cls(
            # Enhanced core metadata with TNA API fields
            id=data.get('Id', data.get('id', '')),
            title=data.get('Title', data.get('title', '')),
            description=data.get('Description', data.get('description', '')),
            date_from=data.get('CoveringFromDate', data.get('startDate', '')),
            date_to=data.get('CoveringToDate', data.get('endDate', '')),
            reference=data.get('CitableReference', data.get('reference', '')),
            archive=data.get('Source', data.get('source', '')),
            collection=data.get('collection', ''),
            subjects=subjects_value,
            creators=creators_value,
            places=places_value,
            catalogue_source=data.get('source', ''),
            
            # Enhanced access and legal information
            access_conditions=data.get('accessConditions', ''),
            closure_status=data.get('ClosureStatus', data.get('closureStatus', '')),
            legal_status=data.get('legalStatus', ''),
            held_by=held_by_enhanced,
            
            # Enhanced reference information
            former_reference=f"{data.get('formerReferenceDep', '')} {data.get('formerReferencePro', '')}".strip(),
            note=data.get('note', ''),
            
            # Enhanced descriptive content
            arrangement=data.get('arrangement', ''),
            dimensions=data.get('dimensions', ''),
            administrator_background=data.get('adminHistory', ''),
            custodial_history=data.get('custodialHistory', ''),
            acquisition_information=data.get('acquisitionInformation', ''),
            appraisal_information=data.get('appraisalInformation', ''),
            accruals=data.get('accruals', ''),
            related_material=data.get('relatedMaterial', ''),
            publication_note=data.get('publicationNote', ''),
            copies_information=data.get('copiesInformation', ''),
            originals_held_elsewhere=data.get('originalsHeldElsewhere', ''),
            unpublished_finding_aids=data.get('unpublishedFindingAids', ''),
            publications=data.get('publications', ''),
            
            # Enhanced physical and map information
            map_designation=data.get('mapDesignation', ''),
            physical_description=data.get('physicalCondition', ''),
            immediate_source=data.get('immediateSource', ''),
            
            # Enhanced scope content from TNA API
            scope_content=scope_content_desc,
            
            # Enhanced language and script information
            language=data.get('language', ''),
            script=data.get('script', ''),
            
            # Enhanced digital and web information
            web_links=data.get('webLinks', []),
            digital_files=data.get('digitalFiles', []),
            
            # Enhanced hierarchical fields
            parent_id=data.get('parentId') or data.get('ParentIAID'),
            level=cls._parse_level(data.get('level') or data.get('catalogueLevel')),
            child_count=data.get('childCount'),
            
            # Enhanced TNA API specific fields
            catalogue_level=data.get('CatalogueLevel', data.get('catalogueLevel')),
            closure_code=data.get('ClosureCode', data.get('closureCode')),
            digitised=data.get('Digitised', data.get('digitised')),
            hierarchy=data.get('hierarchy', []),
            covering_from_date=data.get('CoveringFromDate', data.get('coveringFromDate')),
            covering_to_date=data.get('CoveringToDate', data.get('coveringToDate')),
            
            # Enhanced additional metadata
            catalogue_id=data.get('catalogueId'),
            covering_dates=data.get('coveringDates'),
            is_parent=data.get('isParent'),
            
            # Provenance tracking
            provenance=provenance_data
        )

    @classmethod
    def from_detailed_api_response(cls, data: Dict[str, Any]) -> 'Record':
        """
        Create a Record instance from detailed API response data (records/v1/details endpoint)
        This method captures ALL available metadata fields for maximum completeness
        """
        
        # Handle heldBy field - can be list or string
        held_by_value = data.get('heldBy', '')
        if isinstance(held_by_value, list):
            # Handle list of dictionaries or strings
            held_by_items = []
            for item in held_by_value:
                if isinstance(item, dict):
                    # Extract name from dictionary
                    name = item.get('xReferenceName', '')
                    if name:
                        held_by_items.append(name)
                else:
                    # Handle string items
                    held_by_items.append(str(item))
            held_by_str = ', '.join(held_by_items) if held_by_items else ''
        else:
            held_by_str = str(held_by_value) if held_by_value else ''
        
        # Handle places - ensure it's a list
        places_value = data.get('places', [])
        if not isinstance(places_value, list):
            places_value = [str(places_value)] if places_value else []
        
        # Handle taxonomies as subjects
        subjects_value = data.get('taxonomies', [])
        if not isinstance(subjects_value, list):
            subjects_value = [str(subjects_value)] if subjects_value else []
        
        # Handle corpBodies as creators
        creators_value = data.get('corpBodies', [])
        if not isinstance(creators_value, list):
            creators_value = [str(creators_value)] if creators_value else []
        
        # Generate enhanced provenance metadata automatically
        from utils.provenance import enhanced_record_provenance
        
        record_id = data.get('id', '')
        source_url = f"https://discovery.nationalarchives.gov.uk/details/r/{record_id}"
        
        provenance_data = enhanced_record_provenance(
            record_id=record_id,
            source_method='API_DETAILED',
            source_url=source_url,
            raw_data_size=len(str(data)),
            additional_metadata={
                'api_endpoint': 'records/v1/details',
                'response_fields_count': len(data.keys()),
                'has_hierarchical_data': bool(data.get('parentId') or data.get('ParentIAID')),
                'metadata_completeness': 'FULL'
            }
        )
        
        # Enhanced metadata extraction from detailed TNA API response
        scope_content_obj = data.get('scopeContent', {})
        scope_content_desc = scope_content_obj.get('description', '') if isinstance(scope_content_obj, dict) else ''
        
        # Clean HTML tags from scope content for title/description
        import re
        clean_scope_desc = re.sub(r'<[^>]+>', '', scope_content_desc) if scope_content_desc else ''
        
        # Enhanced held by information parsing
        held_by_enhanced = ''
        if isinstance(held_by_value, list) and held_by_value:
            held_by_details = []
            for held_by_item in held_by_value:
                if isinstance(held_by_item, dict):
                    name = held_by_item.get('xReferenceName', '')
                    if name:
                        held_by_details.append(name)
            held_by_enhanced = ', '.join(held_by_details) if held_by_details else held_by_str
        else:
            held_by_enhanced = held_by_str
        
        return cls(
            # Enhanced core metadata with detailed TNA API fields
            id=data.get('id', ''),
            title=clean_scope_desc or data.get('title', ''),  # Use scope content as primary title
            description=clean_scope_desc or data.get('description', ''),  # Use scope content as primary description
            date_from=data.get('coveringFromDate', data.get('startDate', '')),
            date_to=data.get('coveringToDate', data.get('endDate', '')),
            reference=data.get('citableReference', data.get('reference', '')),  # Use citableReference for accuracy
            archive=data.get('source', ''),
            collection=data.get('collection', ''),
            subjects=subjects_value,
            creators=creators_value,
            places=places_value,
            catalogue_source=data.get('source', ''),
            
            # Enhanced access and legal information
            access_conditions=data.get('accessConditions', ''),
            closure_status=data.get('closureStatus', ''),
            legal_status=data.get('legalStatus', ''),
            held_by=held_by_enhanced,
            
            # Enhanced reference information
            former_reference=f"{data.get('formerReferenceDep', '')} {data.get('formerReferencePro', '')}".strip(),
            note=data.get('note', ''),
            
            # Enhanced descriptive content
            arrangement=data.get('arrangement', ''),
            dimensions=data.get('physicalDescriptionExtent', ''),  # Use correct field name
            administrator_background=data.get('administrativeBackground', ''),
            custodial_history=data.get('custodialHistory', ''),
            acquisition_information=data.get('immediateSourceOfAcquisition', ''),
            appraisal_information=data.get('appraisalInformation', ''),
            accruals=data.get('accruals', ''),
            related_material=data.get('detailedRelatedMaterial', ''),
            publication_note=data.get('publicationNote', ''),
            copies_information=data.get('copiesInformation', ''),
            originals_held_elsewhere=data.get('locationOfOriginals', ''),
            unpublished_finding_aids=data.get('unpublishedFindingAids', ''),
            publications=data.get('publicationNote', ''),
            
            # Enhanced physical and map information
            map_designation=data.get('mapDesignation', ''),
            physical_description=data.get('physicalDescriptionForm', ''),
            immediate_source=data.get('immediateSourceOfAcquisition', ''),
            
            # Enhanced scope content from detailed TNA API
            scope_content=scope_content_desc,
            
            # Enhanced language and script information
            language=data.get('language', ''),
            script=data.get('script', ''),
            
            # Enhanced digital and web information
            web_links=data.get('links', []),
            digital_files=data.get('scannedLists', []),
            
            # Enhanced hierarchical fields
            parent_id=data.get('parentId'),
            level=cls._parse_level(data.get('catalogueLevel')),
            child_count=data.get('childCount'),
            
            # Enhanced TNA API specific fields
            catalogue_level=data.get('catalogueLevel'),
            closure_code=data.get('closureCode'),
            digitised=data.get('digitised'),
            hierarchy=data.get('sortKey', []),  # Use sortKey for hierarchy
            covering_from_date=data.get('coveringFromDate'),
            covering_to_date=data.get('coveringToDate'),
            
            # Enhanced additional metadata
            catalogue_id=data.get('catalogueId'),
            covering_dates=data.get('coveringDates'),
            is_parent=data.get('isParent'),
            
            # Provenance tracking
            provenance=provenance_data
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for storage"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'reference': self.reference,
            'archive': self.archive,
            'collection': self.collection,
            'subjects': '|'.join(self.subjects) if self.subjects else '',
            'creators': '|'.join(self.creators) if self.creators else '',
            'places': '|'.join(self.places) if self.places else '',
            'catalogue_source': self.catalogue_source,
            'access_conditions': self.access_conditions,
            'closure_status': self.closure_status,
            'legal_status': self.legal_status,
            'held_by': self.held_by,
            'former_reference': self.former_reference,
            'note': self.note,
            'arrangement': self.arrangement,
            'dimensions': self.dimensions,
            'administrator_background': self.administrator_background,
            'custodial_history': self.custodial_history,
            'acquisition_information': self.acquisition_information,
            'appraisal_information': self.appraisal_information,
            'accruals': self.accruals,
            'related_material': self.related_material,
            'publication_note': self.publication_note,
            'copies_information': self.copies_information,
            'originals_held_elsewhere': self.originals_held_elsewhere,
            'unpublished_finding_aids': self.unpublished_finding_aids,
            'publications': self.publications,
            'map_designation': self.map_designation,
            'physical_description': self.physical_description,
            'immediate_source': self.immediate_source,
            'scope_content': self.scope_content,
            'language': self.language,
            'script': self.script,
            'web_links': '|'.join(self.web_links) if self.web_links else '',
            'digital_files': '|'.join(self.digital_files) if self.digital_files else '',
            
            # Hierarchical fields
            'parent_id': self.parent_id,
            'level': self.level,
            'child_count': self.child_count,
            
            # Provenance tracking (stored as JSON string)
            'provenance': json.dumps(self.provenance) if self.provenance else '{}',
            
            # API Bible Section 4.1 additional fields
            'catalogue_level': self.catalogue_level,
            'closure_code': self.closure_code,
            'digitised': self.digitised,
            'hierarchy': json.dumps(self.hierarchy) if self.hierarchy else '[]',
            'covering_from_date': self.covering_from_date,
            'covering_to_date': self.covering_to_date,
            
            # Enhanced TNA API metadata fields
            'catalogue_id': self.catalogue_id,
            'covering_dates': self.covering_dates,
            'is_parent': self.is_parent
        }


@dataclass
class SearchResult:
    """Container for search results with metadata"""
    
    records: List[Record]
    total_results: int
    page: int
    per_page: int
    total_pages: int
    query: str
    facets: Dict[str, List[str]] = None
    
    def __post_init__(self):
        if self.facets is None:
            self.facets = {}


@dataclass
class Collection:
    """Represents a collection or series in the archive"""
    
    id: str
    title: str
    description: Optional[str] = None
    record_count: Optional[int] = None
    date_range: Optional[str] = None
    archive: Optional[str] = None


@dataclass
class CrawlQueueItem:
    """Represents an item in the crawl queue for hierarchical traversal"""
    
    url: str
    record_id: str
    status: str = 'QUEUED'  # QUEUED, PROCESSING, COMPLETED, FAILED
    discovered_at: Optional[str] = None
    processed_at: Optional[str] = None
    retries: int = 0
    error_message: Optional[str] = None
    parent_id: Optional[str] = None
    expected_level: Optional[str] = None  # Expected archival level
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert queue item to dictionary for storage"""
        return {
            'url': self.url,
            'record_id': self.record_id,
            'status': self.status,
            'discovered_at': self.discovered_at,
            'processed_at': self.processed_at,
            'retries': self.retries,
            'error_message': self.error_message,
            'parent_id': self.parent_id,
            'expected_level': self.expected_level
        }
