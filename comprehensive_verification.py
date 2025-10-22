#!/usr/bin/env python3
"""
Comprehensive Data Verification Script
Compares locally stored records with live TNA API data to ensure:
1. All information was captured accurately
2. All API fields were captured
3. Data integrity is maintained
"""

import sqlite3
import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import asdict
import requests
from datetime import datetime

class ComprehensiveVerifier:
    def __init__(self, db_path: str = './data/discovery.db'):
        self.db_path = db_path
        self.api_base_url = "https://discovery.nationalarchives.gov.uk/API"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NationalArchivesClone/1.0 (Data Verification)'
        })
        
    def get_local_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Get a record from local database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('SELECT * FROM records WHERE id = ?', (record_id,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            print(f"❌ Error getting local record {record_id}: {e}")
            return None
    
    def get_live_api_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Get a record from live TNA API"""
        try:
            url = f"{self.api_base_url}/records/v1/details/{record_id}"
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"⚠️  API returned {response.status_code} for {record_id}")
                return None
                
        except Exception as e:
            print(f"❌ Error getting live record {record_id}: {e}")
            return None
    
    def compare_records(self, local_record: Dict[str, Any], api_record: Dict[str, Any]) -> Dict[str, Any]:
        """Compare local record with live API record"""
        comparison = {
            'record_id': local_record.get('id'),
            'reference': local_record.get('reference'),
            'fields_compared': 0,
            'fields_match': 0,
            'fields_mismatch': 0,
            'missing_fields': [],
            'extra_fields': [],
            'field_comparisons': {}
        }
        
        # Get all fields from API record
        api_fields = set()
        def extract_fields(obj, prefix=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    field_name = f"{prefix}.{key}" if prefix else key
                    api_fields.add(field_name)
                    if isinstance(value, (dict, list)):
                        extract_fields(value, field_name)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    field_name = f"{prefix}[{i}]"
                    extract_fields(item, field_name)
        
        extract_fields(api_record)
        
        # Compare key fields
        key_fields = [
            'title', 'description', 'date_from', 'date_to', 'reference',
            'archive', 'collection', 'subjects', 'creators', 'places',
            'catalogue_source', 'access_conditions', 'closure_status',
            'legal_status', 'held_by', 'former_reference', 'note',
            'arrangement', 'dimensions', 'administrator_background',
            'custodial_history', 'acquisition_information', 'appraisal_information',
            'accruals', 'related_material', 'publication_note', 'copies_information',
            'originals_held_elsewhere', 'unpublished_finding_aids', 'publications',
            'map_designation', 'physical_description', 'immediate_source',
            'scope_content', 'language', 'script', 'web_links', 'digital_files',
            'parent_id', 'level', 'child_count', 'provenance', 'catalogue_level',
            'closure_code', 'digitised', 'hierarchy', 'covering_from_date',
            'covering_to_date', 'catalogue_id', 'covering_dates', 'is_parent'
        ]
        
        for field in key_fields:
            comparison['fields_compared'] += 1
            
            local_value = local_record.get(field)
            api_value = self._extract_api_value(api_record, field)
            
            if local_value == api_value:
                comparison['fields_match'] += 1
                comparison['field_comparisons'][field] = {
                    'status': 'match',
                    'local': local_value,
                    'api': api_value
                }
            else:
                comparison['fields_mismatch'] += 1
                comparison['field_comparisons'][field] = {
                    'status': 'mismatch',
                    'local': local_value,
                    'api': api_value
                }
        
        # Check for missing fields in local record
        for field in api_fields:
            if field not in key_fields and field not in comparison['missing_fields']:
                comparison['missing_fields'].append(field)
        
        return comparison
    
    def _extract_api_value(self, api_record: Dict[str, Any], field: str) -> Any:
        """Extract value from nested API record structure"""
        try:
            # Handle nested fields
            if '.' in field:
                parts = field.split('.')
                value = api_record
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        return None
                return value
            
            # Handle array fields
            if '[' in field:
                base_field = field.split('[')[0]
                if base_field in api_record:
                    return api_record[base_field]
                return None
            
            # Direct field access
            return api_record.get(field)
            
        except Exception:
            return None
    
    def verify_series(self, series_name: str, sample_size: int = 10) -> Dict[str, Any]:
        """Verify a specific series by sampling records"""
        print(f"\n🔍 Verifying series: {series_name}")
        
        # Get sample records from local database
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    'SELECT id, reference FROM records WHERE reference LIKE ? ORDER BY RANDOM() LIMIT ?',
                    (f"{series_name}%", sample_size)
                )
                sample_records = cursor.fetchall()
        except Exception as e:
            print(f"❌ Error getting sample records for {series_name}: {e}")
            return {}
        
        if not sample_records:
            print(f"⚠️  No records found for {series_name}")
            return {}
        
        print(f"📊 Sampling {len(sample_records)} records for verification...")
        
        verification_results = {
            'series': series_name,
            'sample_size': len(sample_records),
            'records_verified': 0,
            'records_failed': 0,
            'total_fields_compared': 0,
            'total_fields_match': 0,
            'total_fields_mismatch': 0,
            'record_details': []
        }
        
        for i, record in enumerate(sample_records, 1):
            record_id = record['id']
            reference = record['reference']
            
            print(f"  📝 Verifying {i}/{len(sample_records)}: {reference} ({record_id})")
            
            # Get local record
            local_record = self.get_local_record(record_id)
            if not local_record:
                verification_results['records_failed'] += 1
                continue
            
            # Get live API record
            api_record = self.get_live_api_record(record_id)
            if not api_record:
                verification_results['records_failed'] += 1
                continue
            
            # Compare records
            comparison = self.compare_records(local_record, api_record)
            
            verification_results['records_verified'] += 1
            verification_results['total_fields_compared'] += comparison['fields_compared']
            verification_results['total_fields_match'] += comparison['fields_match']
            verification_results['total_fields_mismatch'] += comparison['fields_mismatch']
            
            verification_results['record_details'].append({
                'record_id': record_id,
                'reference': reference,
                'comparison': comparison
            })
            
            # Rate limiting
            time.sleep(0.5)
        
        # Calculate accuracy percentages
        if verification_results['total_fields_compared'] > 0:
            accuracy = (verification_results['total_fields_match'] / verification_results['total_fields_compared']) * 100
            verification_results['accuracy_percentage'] = round(accuracy, 2)
        else:
            verification_results['accuracy_percentage'] = 0
        
        print(f"✅ {series_name}: {verification_results['records_verified']}/{verification_results['sample_size']} records verified")
        print(f"📊 Accuracy: {verification_results['accuracy_percentage']}% ({verification_results['total_fields_match']}/{verification_results['total_fields_compared']} fields match)")
        
        return verification_results
    
    def generate_verification_report(self, results: List[Dict[str, Any]]) -> str:
        """Generate a comprehensive verification report"""
        report = []
        report.append("# COMPREHENSIVE DATA VERIFICATION REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Summary
        total_records = sum(r['sample_size'] for r in results)
        total_verified = sum(r['records_verified'] for r in results)
        total_fields = sum(r['total_fields_compared'] for r in results)
        total_matches = sum(r['total_fields_match'] for r in results)
        
        overall_accuracy = (total_matches / total_fields * 100) if total_fields > 0 else 0
        
        report.append("## EXECUTIVE SUMMARY")
        report.append(f"- **Total Records Sampled**: {total_records}")
        report.append(f"- **Total Records Verified**: {total_verified}")
        report.append(f"- **Total Fields Compared**: {total_fields}")
        report.append(f"- **Overall Accuracy**: {overall_accuracy:.2f}%")
        report.append("")
        
        # Series breakdown
        report.append("## SERIES BREAKDOWN")
        for result in results:
            report.append(f"### {result['series']}")
            report.append(f"- **Sample Size**: {result['sample_size']}")
            report.append(f"- **Records Verified**: {result['records_verified']}")
            report.append(f"- **Accuracy**: {result['accuracy_percentage']}%")
            report.append(f"- **Fields Compared**: {result['total_fields_compared']}")
            report.append(f"- **Fields Match**: {result['total_fields_match']}")
            report.append(f"- **Fields Mismatch**: {result['total_fields_mismatch']}")
            report.append("")
        
        # Detailed findings
        report.append("## DETAILED FINDINGS")
        for result in results:
            report.append(f"### {result['series']} - Detailed Analysis")
            
            for record_detail in result['record_details']:
                report.append(f"#### {record_detail['reference']} ({record_detail['record_id']})")
                
                comparison = record_detail['comparison']
                report.append(f"- **Fields Compared**: {comparison['fields_compared']}")
                report.append(f"- **Fields Match**: {comparison['fields_match']}")
                report.append(f"- **Fields Mismatch**: {comparison['fields_mismatch']}")
                
                # Show mismatches
                mismatches = [f for f, c in comparison['field_comparisons'].items() if c['status'] == 'mismatch']
                if mismatches:
                    report.append("- **Mismatched Fields**:")
                    for field in mismatches[:5]:  # Limit to first 5
                        comp = comparison['field_comparisons'][field]
                        report.append(f"  - `{field}`: Local='{comp['local']}' vs API='{comp['api']}'")
                    if len(mismatches) > 5:
                        report.append(f"  - ... and {len(mismatches) - 5} more")
                
                # Show missing fields
                if comparison['missing_fields']:
                    report.append(f"- **Missing Fields in Local DB**: {', '.join(comparison['missing_fields'][:10])}")
                    if len(comparison['missing_fields']) > 10:
                        report.append(f"  - ... and {len(comparison['missing_fields']) - 10} more")
                
                report.append("")
        
        return "\n".join(report)

def main():
    """Main verification process"""
    print("🔍 COMPREHENSIVE DATA VERIFICATION")
    print("=" * 50)
    
    verifier = ComprehensiveVerifier()
    
    # Verify each CO series
    series_to_verify = [f"CO {i}" for i in range(1, 11)]
    
    all_results = []
    
    for series in series_to_verify:
        try:
            result = verifier.verify_series(series, sample_size=5)  # Sample 5 records per series
            if result:
                all_results.append(result)
        except Exception as e:
            print(f"❌ Error verifying {series}: {e}")
            continue
    
    # Generate and save report
    if all_results:
        report = verifier.generate_verification_report(all_results)
        
        report_filename = f"verification_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n📄 Verification report saved: {report_filename}")
        
        # Print summary
        total_accuracy = sum(r['accuracy_percentage'] for r in all_results) / len(all_results)
        print(f"\n📊 OVERALL VERIFICATION SUMMARY")
        print(f"Average Accuracy: {total_accuracy:.2f}%")
        print(f"Series Verified: {len(all_results)}")
        
    else:
        print("❌ No verification results to report")

if __name__ == "__main__":
    main()
