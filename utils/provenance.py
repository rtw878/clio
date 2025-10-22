"""
Enhanced Provenance Tracking System

Implements comprehensive data lineage and metadata tracking
for scholarly integrity and auditing purposes.
"""

import hashlib
import logging
import platform
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import json

from storage.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class DataLineage:
    """Represents the lineage of a data record"""
    record_id: str
    source_system: str  # 'API', 'Scraper', 'Manual'
    source_url: str
    extraction_timestamp: str
    extraction_method: str
    parser_version: str
    system_info: Dict[str, str]
    transformation_history: List[Dict[str, Any]]
    validation_history: List[Dict[str, Any]]
    quality_score: Optional[float] = None
    confidence_level: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DataLineage':
        """Create from dictionary"""
        return cls(**data)


class ProvenanceTracker:
    """
    Comprehensive provenance tracking system
    
    Tracks:
    - Data source and extraction method
    - System environment details
    - Transformation and processing history
    - Validation results
    - Quality metrics
    - Data dependencies
    """
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize provenance tracker
        
        Args:
            db_manager: Database manager for storing provenance data
        """
        self.db_manager = db_manager
        self.system_info = self._collect_system_info()
        self.session_id = self._generate_session_id()
        
        logger.info(f"Initialized provenance tracker with session ID: {self.session_id}")
    
    def create_record_provenance(self, 
                                record_id: str,
                                source_method: str,
                                source_url: str,
                                parser_version: str,
                                raw_data_size: Optional[int] = None,
                                response_time: Optional[float] = None,
                                additional_metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Create comprehensive provenance metadata for a record
        
        Args:
            record_id: Unique record identifier
            source_method: 'API', 'Scraper', 'Manual'
            source_url: Source URL where data was obtained
            parser_version: Version of parser used
            raw_data_size: Size of raw response data
            response_time: Time taken to fetch data
            additional_metadata: Additional metadata to include
            
        Returns:
            Comprehensive provenance dictionary
        """
        provenance = {
            # Core identification
            'record_id': record_id,
            'session_id': self.session_id,
            
            # Source information
            'source_system': source_method,
            'source_url': source_url,
            'source_method_details': self._get_method_details(source_method),
            
            # Temporal information
            'extraction_timestamp': datetime.now().isoformat(),
            'extraction_date': datetime.now().strftime('%Y-%m-%d'),
            'extraction_time_utc': datetime.utcnow().isoformat() + 'Z',
            
            # Processing information
            'parser_version': parser_version,
            'processing_pipeline': 'national_archives_clone_v2',
            
            # System environment
            'system_info': self.system_info,
            
            # Performance metrics
            'performance': {
                'raw_data_size_bytes': raw_data_size,
                'response_time_seconds': response_time,
                'extraction_duration': None  # To be filled by caller
            },
            
            # Quality and validation
            'quality_metrics': {
                'completeness_score': None,  # To be calculated
                'accuracy_score': None,
                'consistency_score': None
            },
            
            # Data transformations
            'transformations': [],
            
            # Validation history
            'validations': [],
            
            # Dependencies
            'dependencies': {
                'parent_records': [],
                'child_records': [],
                'related_records': []
            },
            
            # Checksums for integrity
            'checksums': {
                'raw_data_hash': None,  # To be calculated from raw data
                'processed_data_hash': None  # To be calculated from processed data
            },
            
            # Additional metadata
            'additional_metadata': additional_metadata or {}
        }
        
        return provenance
    
    def add_transformation(self, 
                          record_id: str,
                          transformation_type: str,
                          description: str,
                          input_fields: List[str],
                          output_fields: List[str],
                          parameters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Record a data transformation
        
        Args:
            record_id: Record being transformed
            transformation_type: Type of transformation
            description: Human-readable description
            input_fields: Fields used as input
            output_fields: Fields produced as output
            parameters: Transformation parameters
            
        Returns:
            Transformation record
        """
        transformation = {
            'timestamp': datetime.now().isoformat(),
            'type': transformation_type,
            'description': description,
            'input_fields': input_fields,
            'output_fields': output_fields,
            'parameters': parameters or {},
            'processor_version': self.system_info.get('processor_version', 'unknown')
        }
        
        # Store transformation if database available
        if self.db_manager:
            self._store_transformation(record_id, transformation)
        
        logger.info(f"Recorded transformation for {record_id}: {transformation_type}")
        return transformation
    
    def add_validation_result(self,
                             record_id: str,
                             validation_type: str,
                             status: str,
                             score: Optional[float] = None,
                             details: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Record a validation result
        
        Args:
            record_id: Record being validated
            validation_type: Type of validation
            status: 'PASS', 'FAIL', 'WARNING', 'ERROR'
            score: Numerical validation score (0-1)
            details: Additional validation details
            
        Returns:
            Validation record
        """
        validation = {
            'timestamp': datetime.now().isoformat(),
            'validation_type': validation_type,
            'status': status,
            'score': score,
            'details': details or {},
            'validator_version': self.system_info.get('processor_version', 'unknown')
        }
        
        # Store validation if database available
        if self.db_manager:
            self._store_validation(record_id, validation)
        
        logger.info(f"Recorded validation for {record_id}: {validation_type} = {status}")
        return validation
    
    def calculate_quality_score(self, 
                               record_id: str,
                               completeness: float,
                               accuracy: float,
                               consistency: float) -> Dict[str, float]:
        """
        Calculate comprehensive quality score
        
        Args:
            record_id: Record being scored
            completeness: Completeness score (0-1)
            accuracy: Accuracy score (0-1)
            consistency: Consistency score (0-1)
            
        Returns:
            Quality metrics dictionary
        """
        # Weighted quality score
        weights = {'completeness': 0.4, 'accuracy': 0.4, 'consistency': 0.2}
        
        overall_score = (
            completeness * weights['completeness'] +
            accuracy * weights['accuracy'] +
            consistency * weights['consistency']
        )
        
        quality_metrics = {
            'completeness_score': completeness,
            'accuracy_score': accuracy,
            'consistency_score': consistency,
            'overall_quality_score': overall_score,
            'quality_grade': self._score_to_grade(overall_score),
            'calculation_timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"Calculated quality score for {record_id}: {overall_score:.3f}")
        return quality_metrics
    
    def create_data_lineage(self, record_id: str) -> Optional[DataLineage]:
        """
        Create comprehensive data lineage for a record
        
        Args:
            record_id: Record to trace lineage for
            
        Returns:
            DataLineage object or None if not found
        """
        if not self.db_manager:
            logger.warning("No database manager available for lineage creation")
            return None
        
        try:
            # Get record provenance data
            provenance_data = self._get_record_provenance(record_id)
            if not provenance_data:
                return None
            
            # Get transformation history
            transformations = self._get_record_transformations(record_id)
            
            # Get validation history
            validations = self._get_record_validations(record_id)
            
            # Create lineage object
            lineage = DataLineage(
                record_id=record_id,
                source_system=provenance_data.get('source_system', 'unknown'),
                source_url=provenance_data.get('source_url', ''),
                extraction_timestamp=provenance_data.get('extraction_timestamp', ''),
                extraction_method=provenance_data.get('source_method', ''),
                parser_version=provenance_data.get('parser_version', ''),
                system_info=provenance_data.get('system_info', {}),
                transformation_history=transformations,
                validation_history=validations,
                quality_score=provenance_data.get('quality_metrics', {}).get('overall_quality_score'),
                confidence_level=self._calculate_confidence_level(provenance_data, transformations, validations)
            )
            
            return lineage
            
        except Exception as e:
            logger.error(f"Error creating data lineage for {record_id}: {e}")
            return None
    
    def generate_provenance_report(self, 
                                  record_ids: Optional[List[str]] = None,
                                  start_date: Optional[str] = None,
                                  end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate comprehensive provenance report
        
        Args:
            record_ids: Specific records to include (None = all)
            start_date: Start date filter (ISO format)
            end_date: End date filter (ISO format)
            
        Returns:
            Comprehensive provenance report
        """
        report = {
            'report_metadata': {
                'generated_at': datetime.now().isoformat(),
                'generator': 'ProvenanceTracker',
                'version': '2.0.0',
                'session_id': self.session_id
            },
            'summary': {},
            'records': [],
            'statistics': {},
            'quality_analysis': {},
            'recommendations': []
        }
        
        try:
            if not self.db_manager:
                report['error'] = 'No database manager available'
                return report
            
            # Get records matching criteria
            records_data = self._get_records_for_report(record_ids, start_date, end_date)
            
            # Process each record
            for record_data in records_data:
                record_id = record_data.get('id')
                lineage = self.create_data_lineage(record_id)
                
                if lineage:
                    report['records'].append(lineage.to_dict())
            
            # Generate statistics
            report['statistics'] = self._calculate_provenance_statistics(records_data)
            
            # Generate quality analysis
            report['quality_analysis'] = self._analyze_data_quality(records_data)
            
            # Generate recommendations
            report['recommendations'] = self._generate_provenance_recommendations(records_data)
            
            # Summary
            report['summary'] = {
                'total_records': len(records_data),
                'records_with_lineage': len(report['records']),
                'average_quality_score': report['quality_analysis'].get('average_quality_score', 0),
                'date_range': {
                    'start': start_date,
                    'end': end_date
                }
            }
            
            logger.info(f"Generated provenance report for {len(records_data)} records")
            return report
            
        except Exception as e:
            logger.error(f"Error generating provenance report: {e}")
            report['error'] = str(e)
            return report
    
    def _collect_system_info(self) -> Dict[str, str]:
        """Collect system environment information"""
        return {
            'platform': platform.platform(),
            'python_version': sys.version,
            'processor_version': '2.0.0',  # Our processor version
            'hostname': platform.node(),
            'architecture': platform.architecture()[0],
            'system': platform.system(),
            'release': platform.release(),
            'collection_timestamp': datetime.now().isoformat()
        }
    
    def _generate_session_id(self) -> str:
        """Generate unique session identifier"""
        timestamp = datetime.now().isoformat()
        hostname = platform.node()
        combined = f"{timestamp}_{hostname}"
        return hashlib.md5(combined.encode()).hexdigest()[:16]
    
    def _get_method_details(self, source_method: str) -> Dict[str, Any]:
        """Get detailed information about extraction method"""
        method_details = {
            'API': {
                'description': 'Official TNA Discovery API',
                'reliability': 'high',
                'structured_data': True,
                'real_time': True
            },
            'Scraper': {
                'description': 'Web scraping fallback',
                'reliability': 'medium',
                'structured_data': False,
                'real_time': True
            },
            'Manual': {
                'description': 'Manual data entry',
                'reliability': 'variable',
                'structured_data': True,
                'real_time': False
            }
        }
        
        return method_details.get(source_method, {'description': 'Unknown method'})
    
    def _score_to_grade(self, score: float) -> str:
        """Convert numerical score to letter grade"""
        if score >= 0.95:
            return 'A+'
        elif score >= 0.90:
            return 'A'
        elif score >= 0.85:
            return 'B+'
        elif score >= 0.80:
            return 'B'
        elif score >= 0.75:
            return 'C+'
        elif score >= 0.70:
            return 'C'
        elif score >= 0.60:
            return 'D'
        else:
            return 'F'
    
    def _calculate_confidence_level(self, 
                                  provenance_data: Dict,
                                  transformations: List[Dict],
                                  validations: List[Dict]) -> str:
        """Calculate confidence level based on provenance data"""
        # Simple confidence calculation
        confidence_score = 0.5  # Base score
        
        # Boost for API source
        if provenance_data.get('source_system') == 'API':
            confidence_score += 0.2
        
        # Boost for recent data
        extraction_time = provenance_data.get('extraction_timestamp', '')
        if extraction_time:
            try:
                extraction_dt = datetime.fromisoformat(extraction_time.replace('Z', '+00:00'))
                age_days = (datetime.now() - extraction_dt.replace(tzinfo=None)).days
                if age_days < 30:
                    confidence_score += 0.2
            except:
                pass
        
        # Boost for validations
        passing_validations = len([v for v in validations if v.get('status') == 'PASS'])
        if passing_validations > 0:
            confidence_score += min(0.2, passing_validations * 0.05)
        
        # Convert to confidence level
        if confidence_score >= 0.9:
            return 'Very High'
        elif confidence_score >= 0.8:
            return 'High'
        elif confidence_score >= 0.6:
            return 'Medium'
        elif confidence_score >= 0.4:
            return 'Low'
        else:
            return 'Very Low'
    
    def _store_transformation(self, record_id: str, transformation: Dict):
        """Store transformation record in database"""
        # This would store in a transformations table
        pass
    
    def _store_validation(self, record_id: str, validation: Dict):
        """Store validation record in database"""
        # This would store in a validations table
        pass
    
    def _get_record_provenance(self, record_id: str) -> Optional[Dict]:
        """Get provenance data for a record"""
        # This would query the records table for provenance data
        return {}
    
    def _get_record_transformations(self, record_id: str) -> List[Dict]:
        """Get transformation history for a record"""
        # This would query transformations table
        return []
    
    def _get_record_validations(self, record_id: str) -> List[Dict]:
        """Get validation history for a record"""
        # This would query validations table
        return []
    
    def _get_records_for_report(self, 
                               record_ids: Optional[List[str]], 
                               start_date: Optional[str], 
                               end_date: Optional[str]) -> List[Dict]:
        """Get records matching report criteria"""
        # This would query the database with filters
        return []
    
    def _calculate_provenance_statistics(self, records_data: List[Dict]) -> Dict[str, Any]:
        """Calculate statistics for provenance report"""
        return {
            'source_methods': {},
            'parser_versions': {},
            'extraction_timeline': {},
            'quality_distribution': {}
        }
    
    def _analyze_data_quality(self, records_data: List[Dict]) -> Dict[str, Any]:
        """Analyze data quality across records"""
        return {
            'average_quality_score': 0.0,
            'quality_trends': [],
            'quality_by_source': {},
            'quality_issues': []
        }
    
    def _generate_provenance_recommendations(self, records_data: List[Dict]) -> List[str]:
        """Generate recommendations based on provenance analysis"""
        return [
            "Consider re-validating records with low quality scores",
            "Update parser version for improved data extraction",
            "Implement additional validation checks for data consistency"
        ]


# Global provenance tracker instance
_global_tracker: Optional[ProvenanceTracker] = None


def get_provenance_tracker(db_manager: Optional[DatabaseManager] = None) -> ProvenanceTracker:
    """Get global provenance tracker instance"""
    global _global_tracker
    
    if _global_tracker is None:
        _global_tracker = ProvenanceTracker(db_manager)
    
    return _global_tracker


def enhanced_record_provenance(record_id: str, 
                              source_method: str,
                              source_url: str,
                              **kwargs) -> Dict[str, Any]:
    """
    Convenience function for creating enhanced record provenance
    
    Args:
        record_id: Record identifier
        source_method: Extraction method
        source_url: Source URL
        **kwargs: Additional metadata
        
    Returns:
        Enhanced provenance dictionary
    """
    tracker = get_provenance_tracker()
    return tracker.create_record_provenance(
        record_id=record_id,
        source_method=source_method,
        source_url=source_url,
        parser_version="2.0.0",
        **kwargs
    )
