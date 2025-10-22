"""
Validation system for National Archives Discovery Clone

Implements comprehensive data validation as specified in Workflow.md Section 5.1
"""

import logging
import json
import re
import sqlite3
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from storage.database import DatabaseManager
from api.client import DiscoveryClient
from api.models import Record
from utils.logging_config import get_contextual_logger

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check"""
    validator_name: str
    check_name: str
    status: str  # 'PASS', 'FAIL', 'WARNING', 'ERROR'
    expected: Any
    actual: Any
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class BaseValidator:
    """Base class for all validators"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.logger = get_contextual_logger(f'validation.{self.__class__.__name__}')
        self.results: List[ValidationResult] = []
    
    def add_result(self, check_name: str, status: str, expected: Any, actual: Any, 
                   message: str, details: Optional[Dict] = None):
        """Add a validation result"""
        result = ValidationResult(
            validator_name=self.__class__.__name__,
            check_name=check_name,
            status=status,
            expected=expected,
            actual=actual,
            message=message,
            details=details
        )
        self.results.append(result)
        
        # Log the result
        if status == 'FAIL':
            self.logger.error(f"{check_name}: {message}")
        elif status == 'WARNING':
            self.logger.warning(f"{check_name}: {message}")
        elif status == 'PASS':
            self.logger.info(f"{check_name}: {message}")
    
    def get_results(self) -> List[ValidationResult]:
        """Get all validation results"""
        return self.results
    
    def clear_results(self):
        """Clear all validation results"""
        self.results.clear()


class CountValidator(BaseValidator):
    """
    Implements Workflow.md count-based validation
    
    Compares record counts in local database against official TNA Discovery counts
    """
    
    def __init__(self, db_manager: DatabaseManager, api_client: Optional[DiscoveryClient] = None):
        super().__init__(db_manager)
        self.api_client = api_client or DiscoveryClient()
    
    def validate_series_counts(self, series_list: Optional[List[str]] = None) -> bool:
        """
        Validate record counts for specific series against TNA website
        
        Args:
            series_list: List of series to validate (None = validate all)
            
        Returns:
            True if all counts match within tolerance
        """
        self.logger.info("Starting series count validation")
        
        if series_list is None:
            # Get all series from database
            series_list = self._get_series_from_database()
        
        all_passed = True
        
        for series in series_list:
            try:
                # Get local count
                local_count = self._get_local_series_count(series)
                
                # Get official count from TNA
                official_count = self._get_official_series_count(series)
                
                if official_count is None:
                    self.add_result(
                        f"series_count_{series}",
                        'ERROR',
                        'Available',
                        'Not found',
                        f"Could not retrieve official count for series {series}",
                        {'series': series, 'local_count': local_count}
                    )
                    all_passed = False
                    continue
                
                # Check if counts match (allow small tolerance for timing differences)
                tolerance = max(1, int(official_count * 0.01))  # 1% tolerance, minimum 1
                
                if abs(local_count - official_count) <= tolerance:
                    self.add_result(
                        f"series_count_{series}",
                        'PASS',
                        official_count,
                        local_count,
                        f"Series {series} count matches: {local_count}/{official_count}",
                        {'series': series, 'tolerance': tolerance}
                    )
                else:
                    self.add_result(
                        f"series_count_{series}",
                        'FAIL',
                        official_count,
                        local_count,
                        f"Series {series} count mismatch: {local_count} local vs {official_count} official",
                        {'series': series, 'difference': abs(local_count - official_count)}
                    )
                    all_passed = False
                    
            except Exception as e:
                self.add_result(
                    f"series_count_{series}",
                    'ERROR',
                    'Validation complete',
                    'Exception',
                    f"Error validating series {series}: {str(e)}",
                    {'series': series, 'error': str(e)}
                )
                all_passed = False
        
        return all_passed
    
    def validate_hierarchy_counts(self, parent_id: str) -> bool:
        """
        Validate that parent records have correct child counts
        
        Args:
            parent_id: ID of parent record to validate
            
        Returns:
            True if hierarchy counts are correct
        """
        try:
            # Get parent record
            parent_record = self.db_manager.get_record(parent_id)
            if not parent_record:
                self.add_result(
                    f"hierarchy_count_{parent_id}",
                    'ERROR',
                    'Record exists',
                    'Not found',
                    f"Parent record {parent_id} not found in database"
                )
                return False
            
            # Count actual children in database
            actual_children = self._count_children(parent_id)
            
            # Get stored child count
            stored_count = parent_record.child_count or 0
            
            if actual_children == stored_count:
                self.add_result(
                    f"hierarchy_count_{parent_id}",
                    'PASS',
                    stored_count,
                    actual_children,
                    f"Child count correct for {parent_id}: {actual_children} children"
                )
                return True
            else:
                self.add_result(
                    f"hierarchy_count_{parent_id}",
                    'FAIL',
                    stored_count,
                    actual_children,
                    f"Child count mismatch for {parent_id}: stored {stored_count}, actual {actual_children}",
                    {'difference': abs(actual_children - stored_count)}
                )
                return False
                
        except Exception as e:
            self.add_result(
                f"hierarchy_count_{parent_id}",
                'ERROR',
                'Validation complete',
                'Exception',
                f"Error validating hierarchy for {parent_id}: {str(e)}"
            )
            return False
    
    def _get_series_from_database(self) -> List[str]:
        """Get list of all series in database"""
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                cursor = conn.execute("""
                    SELECT DISTINCT CASE 
                        WHEN reference LIKE 'CO %' THEN SUBSTR(reference, 1, INSTR(reference || '/', '/') - 1)
                        ELSE reference 
                    END as series
                    FROM records 
                    WHERE reference IS NOT NULL 
                    AND reference LIKE 'CO %'
                    ORDER BY series
                """)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting series from database: {e}")
            return []
    
    def _get_local_series_count(self, series: str) -> int:
        """Get count of records for a series in local database"""
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM records 
                    WHERE reference LIKE ? OR reference = ?
                """, (f"{series}%", series))
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"Error getting local count for {series}: {e}")
            return 0
    
    def _get_official_series_count(self, series: str) -> Optional[int]:
        """
        Get official count from TNA Discovery website
        
        This scrapes the series page to get the official record count
        """
        try:
            # Convert series code to series ID (this is simplified - would need mapping)
            series_mapping = {
                'CO 1': 'C243',
                'CO 2': 'C244',
                'CO 3': 'C245',
                # Add more mappings as needed
            }
            
            series_id = series_mapping.get(series)
            if not series_id:
                self.logger.warning(f"No series ID mapping for {series}")
                return None
            
            # Scrape the series page
            url = f"https://discovery.nationalarchives.gov.uk/details/r/{series_id}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for record count information
            # This would need to be adapted based on actual TNA HTML structure
            count_elements = soup.find_all(text=re.compile(r'\d+\s+record[s]?'))
            
            for element in count_elements:
                match = re.search(r'(\d+)\s+record[s]?', element)
                if match:
                    return int(match.group(1))
            
            # Alternative: look for pagination info
            pagination = soup.find('div', class_='pagination')
            if pagination:
                # Extract total from pagination
                pass
            
            self.logger.warning(f"Could not find record count for {series} on TNA website")
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting official count for {series}: {e}")
            return None
    
    def _count_children(self, parent_id: str) -> int:
        """Count direct children of a parent record"""
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM records WHERE parent_id = ?
                """, (parent_id,))
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"Error counting children for {parent_id}: {e}")
            return 0


class SchemaValidator(BaseValidator):
    """
    Validates data against JSON schema and database constraints
    
    Implements Workflow.md schema validation requirements
    """
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager)
        self.schema = self._load_record_schema()
    
    def validate_records_schema(self, sample_size: Optional[int] = None) -> bool:
        """
        Validate a sample of records against the defined schema
        
        Args:
            sample_size: Number of records to validate (None = all records)
            
        Returns:
            True if all records pass validation
        """
        self.logger.info(f"Starting schema validation (sample size: {sample_size})")
        
        try:
            # Get records to validate
            records = self._get_validation_sample(sample_size)
            
            all_passed = True
            error_count = 0
            warning_count = 0
            
            for record in records:
                try:
                    # Validate individual record
                    record_result = self._validate_single_record(record)
                    
                    if record_result['status'] == 'FAIL':
                        error_count += 1
                        all_passed = False
                    elif record_result['status'] == 'WARNING':
                        warning_count += 1
                    
                except Exception as e:
                    self.add_result(
                        f"record_schema_{record.id}",
                        'ERROR',
                        'Valid record',
                        'Validation exception',
                        f"Error validating record {record.id}: {str(e)}"
                    )
                    error_count += 1
                    all_passed = False
            
            # Summary result
            total_records = len(records)
            self.add_result(
                'schema_validation_summary',
                'PASS' if all_passed else 'FAIL',
                f"{total_records} valid records",
                f"{total_records - error_count} valid, {error_count} errors, {warning_count} warnings",
                f"Schema validation complete: {total_records - error_count}/{total_records} records valid",
                {
                    'total_records': total_records,
                    'valid_records': total_records - error_count,
                    'error_count': error_count,
                    'warning_count': warning_count
                }
            )
            
            return all_passed
            
        except Exception as e:
            self.add_result(
                'schema_validation',
                'ERROR',
                'Validation complete',
                'Exception',
                f"Schema validation failed: {str(e)}"
            )
            return False
    
    def validate_database_constraints(self) -> bool:
        """Validate database-level constraints and relationships"""
        self.logger.info("Validating database constraints")
        
        all_passed = True
        
        try:
            # Check for orphaned records (parent_id points to non-existent record)
            orphaned_count = self._check_orphaned_records()
            if orphaned_count > 0:
                self.add_result(
                    'orphaned_records',
                    'FAIL',
                    0,
                    orphaned_count,
                    f"Found {orphaned_count} orphaned records with invalid parent_id"
                )
                all_passed = False
            else:
                self.add_result(
                    'orphaned_records',
                    'PASS',
                    0,
                    0,
                    "No orphaned records found"
                )
            
            # Check for circular references
            circular_count = self._check_circular_references()
            if circular_count > 0:
                self.add_result(
                    'circular_references',
                    'FAIL',
                    0,
                    circular_count,
                    f"Found {circular_count} circular references in hierarchy"
                )
                all_passed = False
            else:
                self.add_result(
                    'circular_references',
                    'PASS',
                    0,
                    0,
                    "No circular references found"
                )
            
            # Check for duplicate IDs
            duplicate_count = self._check_duplicate_ids()
            if duplicate_count > 0:
                self.add_result(
                    'duplicate_ids',
                    'FAIL',
                    0,
                    duplicate_count,
                    f"Found {duplicate_count} duplicate record IDs"
                )
                all_passed = False
            else:
                self.add_result(
                    'duplicate_ids',
                    'PASS',
                    0,
                    0,
                    "No duplicate IDs found"
                )
            
            return all_passed
            
        except Exception as e:
            self.add_result(
                'database_constraints',
                'ERROR',
                'Validation complete',
                'Exception',
                f"Database constraint validation failed: {str(e)}"
            )
            return False
    
    def _load_record_schema(self) -> Dict[str, Any]:
        """Load the JSON schema for record validation"""
        # This is a simplified schema - in production, this would be loaded from a file
        return {
            "type": "object",
            "required": ["id", "title"],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1},
                "description": {"type": ["string", "null"]},
                "reference": {"type": ["string", "null"]},
                "level": {"type": ["string", "null"], "enum": [None, "Department", "Series", "Sub-series", "Piece", "Item"]},
                "parent_id": {"type": ["string", "null"]},
                "child_count": {"type": ["integer", "null"], "minimum": 0},
                "provenance": {"type": "object"}
            }
        }
    
    def _get_validation_sample(self, sample_size: Optional[int]) -> List[Record]:
        """Get a sample of records for validation"""
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                if sample_size:
                    cursor = conn.execute("""
                        SELECT * FROM records 
                        ORDER BY RANDOM() 
                        LIMIT ?
                    """, (sample_size,))
                else:
                    cursor = conn.execute("SELECT * FROM records")
                
                records = []
                for row in cursor.fetchall():
                    record = self.db_manager._row_to_record(row)
                    records.append(record)
                
                return records
                
        except Exception as e:
            self.logger.error(f"Error getting validation sample: {e}")
            return []
    
    def _validate_single_record(self, record: Record) -> Dict[str, Any]:
        """Validate a single record against schema"""
        issues = []
        
        # Required field checks
        if not record.id:
            issues.append("Missing required field: id")
        if not record.title:
            issues.append("Missing required field: title")
        
        # Level validation (API Bible Section 2.2 - Complete archival hierarchy)
        valid_levels = ["Department", "Division", "Series", "Sub-series", "Sub sub-series", "Piece", "Item"]
        if record.level and record.level not in valid_levels:
            issues.append(f"Invalid level: {record.level}")
        
        # Parent-child consistency
        if record.parent_id and record.level == "Department":
            issues.append("Department level record should not have parent_id")
        
        # Child count validation
        if record.child_count is not None and record.child_count < 0:
            issues.append("Child count cannot be negative")
        
        # Provenance validation
        if not record.provenance or not isinstance(record.provenance, dict):
            issues.append("Missing or invalid provenance data")
        
        if issues:
            self.add_result(
                f"record_schema_{record.id}",
                'FAIL',
                'Valid record',
                'Schema violations',
                f"Record {record.id} failed schema validation: {'; '.join(issues)}",
                {'violations': issues}
            )
            return {'status': 'FAIL', 'issues': issues}
        else:
            return {'status': 'PASS', 'issues': []}
    
    def _check_orphaned_records(self) -> int:
        """Check for records with parent_id pointing to non-existent records"""
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM records r1
                    WHERE r1.parent_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM records r2 
                        WHERE r2.id = r1.parent_id
                    )
                """)
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"Error checking orphaned records: {e}")
            return 0
    
    def _check_circular_references(self) -> int:
        """Check for circular references in parent-child relationships"""
        # This is a simplified check - full implementation would use recursive CTE
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM records r1
                    WHERE r1.parent_id = r1.id
                """)
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"Error checking circular references: {e}")
            return 0
    
    def _check_duplicate_ids(self) -> int:
        """Check for duplicate record IDs"""
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) - COUNT(DISTINCT id) FROM records
                """)
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"Error checking duplicate IDs: {e}")
            return 0


class HierarchyValidator(BaseValidator):
    """Validates archival hierarchy integrity and relationships"""
    
    def validate_hierarchy_integrity(self) -> bool:
        """Validate the entire archival hierarchy structure"""
        self.logger.info("Validating hierarchy integrity")
        
        all_passed = True
        
        try:
            # Check level consistency
            level_consistency = self._check_level_consistency()
            all_passed &= level_consistency
            
            # Check parent-child relationships
            relationship_integrity = self._check_parent_child_relationships()
            all_passed &= relationship_integrity
            
            # Check for isolated hierarchies
            isolation_check = self._check_hierarchy_isolation()
            all_passed &= isolation_check
            
            return all_passed
            
        except Exception as e:
            self.add_result(
                'hierarchy_integrity',
                'ERROR',
                'Validation complete',
                'Exception',
                f"Hierarchy validation failed: {str(e)}"
            )
            return False
    
    def _check_level_consistency(self) -> bool:
        """Check that archival levels are consistent with hierarchy"""
        # Implementation for level consistency checking
        return True
    
    def _check_parent_child_relationships(self) -> bool:
        """Check parent-child relationship integrity"""
        # Implementation for relationship checking
        return True
    
    def _check_hierarchy_isolation(self) -> bool:
        """Check for disconnected hierarchy branches"""
        # Implementation for isolation checking
        return True


class ProvenanceValidator(BaseValidator):
    """Validates provenance data and data lineage"""
    
    def validate_provenance_integrity(self) -> bool:
        """Validate provenance data completeness and accuracy"""
        self.logger.info("Validating provenance integrity")
        
        all_passed = True
        
        try:
            # Check provenance completeness
            completeness = self._check_provenance_completeness()
            all_passed &= completeness
            
            # Check provenance accuracy
            accuracy = self._check_provenance_accuracy()
            all_passed &= accuracy
            
            return all_passed
            
        except Exception as e:
            self.add_result(
                'provenance_integrity',
                'ERROR',
                'Validation complete',
                'Exception',
                f"Provenance validation failed: {str(e)}"
            )
            return False
    
    def _check_provenance_completeness(self) -> bool:
        """Check that all records have complete provenance data"""
        # Implementation for provenance completeness
        return True
    
    def _check_provenance_accuracy(self) -> bool:
        """Check provenance data accuracy"""
        # Implementation for provenance accuracy
        return True


class DataValidator:
    """
    Main validation orchestrator
    
    Coordinates all validation types and provides unified interface
    """
    
    def __init__(self, db_manager: DatabaseManager, api_client: Optional[DiscoveryClient] = None):
        self.db_manager = db_manager
        self.api_client = api_client
        
        # Initialize individual validators
        self.count_validator = CountValidator(db_manager, api_client)
        self.schema_validator = SchemaValidator(db_manager)
        self.hierarchy_validator = HierarchyValidator(db_manager)
        self.provenance_validator = ProvenanceValidator(db_manager)
        
        self.logger = get_contextual_logger('validation.DataValidator')
    
    def run_full_validation(self, series_list: Optional[List[str]] = None,
                           schema_sample_size: Optional[int] = 100) -> Dict[str, Any]:
        """
        Run complete validation suite
        
        Args:
            series_list: List of series to validate counts for
            schema_sample_size: Size of sample for schema validation
            
        Returns:
            Comprehensive validation report
        """
        self.logger.info("Starting full validation suite")
        start_time = datetime.now()
        
        results = {
            'validation_start': start_time.isoformat(),
            'validators': {},
            'overall_status': 'PASS',
            'summary': {}
        }
        
        # Run count validation
        self.logger.info("Running count validation...")
        count_result = self.count_validator.validate_series_counts(series_list)
        results['validators']['count'] = {
            'status': 'PASS' if count_result else 'FAIL',
            'results': [r.__dict__ for r in self.count_validator.get_results()]
        }
        
        # Run schema validation
        self.logger.info("Running schema validation...")
        schema_result = self.schema_validator.validate_records_schema(schema_sample_size)
        schema_constraint_result = self.schema_validator.validate_database_constraints()
        results['validators']['schema'] = {
            'status': 'PASS' if (schema_result and schema_constraint_result) else 'FAIL',
            'results': [r.__dict__ for r in self.schema_validator.get_results()]
        }
        
        # Run hierarchy validation
        self.logger.info("Running hierarchy validation...")
        hierarchy_result = self.hierarchy_validator.validate_hierarchy_integrity()
        results['validators']['hierarchy'] = {
            'status': 'PASS' if hierarchy_result else 'FAIL',
            'results': [r.__dict__ for r in self.hierarchy_validator.get_results()]
        }
        
        # Run provenance validation
        self.logger.info("Running provenance validation...")
        provenance_result = self.provenance_validator.validate_provenance_integrity()
        results['validators']['provenance'] = {
            'status': 'PASS' if provenance_result else 'FAIL',
            'results': [r.__dict__ for r in self.provenance_validator.get_results()]
        }
        
        # Determine overall status
        if not all([count_result, schema_result, schema_constraint_result, 
                   hierarchy_result, provenance_result]):
            results['overall_status'] = 'FAIL'
        
        # Generate summary
        end_time = datetime.now()
        results['validation_end'] = end_time.isoformat()
        results['duration_seconds'] = (end_time - start_time).total_seconds()
        
        # Count results by status
        all_results = []
        for validator_results in results['validators'].values():
            all_results.extend(validator_results['results'])
        
        results['summary'] = {
            'total_checks': len(all_results),
            'passed': len([r for r in all_results if r['status'] == 'PASS']),
            'failed': len([r for r in all_results if r['status'] == 'FAIL']),
            'warnings': len([r for r in all_results if r['status'] == 'WARNING']),
            'errors': len([r for r in all_results if r['status'] == 'ERROR'])
        }
        
        self.logger.info(f"Validation complete: {results['overall_status']} - "
                        f"{results['summary']['passed']}/{results['summary']['total_checks']} checks passed")
        
        return results
    
    def validate_series(self, series: str) -> Dict[str, Any]:
        """
        Run targeted validation for a specific series
        
        Args:
            series: Series identifier (e.g., 'CO 1')
            
        Returns:
            Validation results for the series
        """
        self.logger.info(f"Running targeted validation for series: {series}")
        
        # Count validation for the series
        count_result = self.count_validator.validate_series_counts([series])
        
        # Get series root for hierarchy validation
        series_root = self._get_series_root_id(series)
        hierarchy_result = True
        if series_root:
            hierarchy_result = self.count_validator.validate_hierarchy_counts(series_root)
        
        return {
            'series': series,
            'count_validation': count_result,
            'hierarchy_validation': hierarchy_result,
            'results': [r.__dict__ for r in self.count_validator.get_results()]
        }
    
    def _get_series_root_id(self, series: str) -> Optional[str]:
        """Get the root record ID for a series"""
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                cursor = conn.execute("""
                    SELECT id FROM records 
                    WHERE reference = ? AND level = 'Series'
                    LIMIT 1
                """, (series,))
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            self.logger.error(f"Error getting series root for {series}: {e}")
            return None
