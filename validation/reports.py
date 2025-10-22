"""
Validation reporting system for National Archives Discovery Clone

Generates comprehensive validation reports in multiple formats
"""

import json
import csv
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationMetrics:
    """Validation metrics for summary reporting"""
    total_checks: int
    passed: int
    failed: int
    warnings: int
    errors: int
    success_rate: float
    validation_duration: float
    
    @classmethod
    def from_results(cls, results: Dict[str, Any]) -> 'ValidationMetrics':
        """Create metrics from validation results"""
        summary = results.get('summary', {})
        return cls(
            total_checks=summary.get('total_checks', 0),
            passed=summary.get('passed', 0),
            failed=summary.get('failed', 0),
            warnings=summary.get('warnings', 0),
            errors=summary.get('errors', 0),
            success_rate=summary.get('passed', 0) / max(summary.get('total_checks', 1), 1) * 100,
            validation_duration=results.get('duration_seconds', 0)
        )


class ValidationReport:
    """
    Comprehensive validation report generator
    
    Produces reports in multiple formats for different audiences
    """
    
    def __init__(self, validation_results: Dict[str, Any]):
        self.results = validation_results
        self.metrics = ValidationMetrics.from_results(validation_results)
        self.timestamp = datetime.now()
    
    def generate_console_report(self) -> str:
        """Generate human-readable console report"""
        lines = []
        
        # Header
        lines.append("=" * 80)
        lines.append("📊 NATIONAL ARCHIVES DISCOVERY CLONE - VALIDATION REPORT")
        lines.append("=" * 80)
        lines.append(f"Generated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Duration: {self.metrics.validation_duration:.1f} seconds")
        lines.append(f"Overall Status: {'✅ PASS' if self.results['overall_status'] == 'PASS' else '❌ FAIL'}")
        lines.append("")
        
        # Summary
        lines.append("📈 SUMMARY METRICS")
        lines.append("-" * 40)
        lines.append(f"Total Checks: {self.metrics.total_checks}")
        lines.append(f"✅ Passed: {self.metrics.passed}")
        lines.append(f"❌ Failed: {self.metrics.failed}")
        lines.append(f"⚠️  Warnings: {self.metrics.warnings}")
        lines.append(f"💥 Errors: {self.metrics.errors}")
        lines.append(f"Success Rate: {self.metrics.success_rate:.1f}%")
        lines.append("")
        
        # Validator Details
        for validator_name, validator_data in self.results.get('validators', {}).items():
            lines.append(f"🔍 {validator_name.upper()} VALIDATION")
            lines.append("-" * 40)
            lines.append(f"Status: {'✅ PASS' if validator_data['status'] == 'PASS' else '❌ FAIL'}")
            
            # Group results by status
            results_by_status = {}
            for result in validator_data['results']:
                status = result['status']
                if status not in results_by_status:
                    results_by_status[status] = []
                results_by_status[status].append(result)
            
            # Show failed checks first
            for status in ['FAIL', 'ERROR', 'WARNING', 'PASS']:
                if status in results_by_status:
                    status_icon = {'PASS': '✅', 'FAIL': '❌', 'WARNING': '⚠️', 'ERROR': '💥'}[status]
                    lines.append(f"\n{status_icon} {status} ({len(results_by_status[status])} checks):")
                    
                    for result in results_by_status[status][:5]:  # Show first 5
                        lines.append(f"  • {result['check_name']}: {result['message']}")
                        if result.get('details'):
                            for key, value in result['details'].items():
                                lines.append(f"    - {key}: {value}")
                    
                    if len(results_by_status[status]) > 5:
                        lines.append(f"    ... and {len(results_by_status[status]) - 5} more")
            
            lines.append("")
        
        # Recommendations
        lines.append("💡 RECOMMENDATIONS")
        lines.append("-" * 40)
        recommendations = self._generate_recommendations()
        for rec in recommendations:
            lines.append(f"• {rec}")
        
        lines.append("")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def generate_json_report(self) -> Dict[str, Any]:
        """Generate machine-readable JSON report"""
        return {
            'report_metadata': {
                'generated_at': self.timestamp.isoformat(),
                'report_version': '1.0',
                'system': 'National Archives Discovery Clone'
            },
            'validation_results': self.results,
            'metrics': self.metrics.__dict__,
            'recommendations': self._generate_recommendations(),
            'summary': {
                'overall_status': self.results['overall_status'],
                'success_rate': self.metrics.success_rate,
                'critical_issues': self._get_critical_issues(),
                'validation_coverage': self._get_validation_coverage()
            }
        }
    
    def generate_csv_report(self) -> str:
        """Generate CSV report for data analysis"""
        output = []
        
        # Header
        output.append([
            'Validator', 'Check_Name', 'Status', 'Expected', 'Actual', 
            'Message', 'Timestamp', 'Details'
        ])
        
        # Data rows
        for validator_name, validator_data in self.results.get('validators', {}).items():
            for result in validator_data['results']:
                output.append([
                    validator_name,
                    result['check_name'],
                    result['status'],
                    str(result['expected']),
                    str(result['actual']),
                    result['message'],
                    result['timestamp'],
                    json.dumps(result.get('details', {}))
                ])
        
        # Convert to CSV string
        import io
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerows(output)
        return csv_buffer.getvalue()
    
    def save_report(self, output_dir: str, formats: Optional[List[str]] = None) -> Dict[str, str]:
        """
        Save validation reports to files
        
        Args:
            output_dir: Directory to save reports
            formats: List of formats to generate ('console', 'json', 'csv')
            
        Returns:
            Dictionary mapping format to saved file path
        """
        if formats is None:
            formats = ['console', 'json', 'csv']
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp_str = self.timestamp.strftime('%Y%m%d_%H%M%S')
        saved_files = {}
        
        for format_name in formats:
            try:
                if format_name == 'console':
                    content = self.generate_console_report()
                    filename = f"validation_report_{timestamp_str}.txt"
                    
                elif format_name == 'json':
                    content = json.dumps(self.generate_json_report(), indent=2, default=str)
                    filename = f"validation_report_{timestamp_str}.json"
                    
                elif format_name == 'csv':
                    content = self.generate_csv_report()
                    filename = f"validation_report_{timestamp_str}.csv"
                    
                else:
                    logger.warning(f"Unknown report format: {format_name}")
                    continue
                
                file_path = output_path / filename
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                saved_files[format_name] = str(file_path)
                logger.info(f"Saved {format_name} report to {file_path}")
                
            except Exception as e:
                logger.error(f"Error saving {format_name} report: {e}")
        
        return saved_files
    
    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on validation results"""
        recommendations = []
        
        # Analyze results for common issues
        all_failures = []
        for validator_data in self.results.get('validators', {}).values():
            for result in validator_data['results']:
                if result['status'] in ['FAIL', 'ERROR']:
                    all_failures.append(result)
        
        # Count-based recommendations
        count_failures = [f for f in all_failures if 'count' in f['check_name'].lower()]
        if count_failures:
            recommendations.append(
                f"Found {len(count_failures)} count mismatches. "
                "Consider re-running traversal for affected series to ensure completeness."
            )
        
        # Schema recommendations
        schema_failures = [f for f in all_failures if 'schema' in f['check_name'].lower()]
        if schema_failures:
            recommendations.append(
                f"Found {len(schema_failures)} schema violations. "
                "Review data parsing logic and update schema validation rules."
            )
        
        # Hierarchy recommendations
        orphaned_failures = [f for f in all_failures if 'orphaned' in f['check_name'].lower()]
        if orphaned_failures:
            recommendations.append(
                "Found orphaned records. Run hierarchy cleanup to fix broken parent-child relationships."
            )
        
        # General recommendations
        if self.metrics.success_rate < 95:
            recommendations.append(
                f"Success rate is {self.metrics.success_rate:.1f}%, below recommended 95%. "
                "Review failed checks and implement data quality improvements."
            )
        
        if not recommendations:
            recommendations.append("All validations passed! Data quality is excellent.")
        
        return recommendations
    
    def _get_critical_issues(self) -> List[Dict[str, Any]]:
        """Get list of critical issues that need immediate attention"""
        critical = []
        
        for validator_name, validator_data in self.results.get('validators', {}).items():
            for result in validator_data['results']:
                if result['status'] == 'ERROR' or (
                    result['status'] == 'FAIL' and 
                    'critical' in result.get('details', {}).get('priority', '').lower()
                ):
                    critical.append({
                        'validator': validator_name,
                        'check': result['check_name'],
                        'message': result['message'],
                        'impact': 'High'
                    })
        
        return critical
    
    def _get_validation_coverage(self) -> Dict[str, Any]:
        """Calculate validation coverage metrics"""
        validators = list(self.results.get('validators', {}).keys())
        
        return {
            'validators_run': len(validators),
            'coverage_areas': validators,
            'comprehensive': len(validators) >= 4,  # Expect at least 4 validator types
            'missing_validators': [
                v for v in ['count', 'schema', 'hierarchy', 'provenance'] 
                if v not in validators
            ]
        }


class ValidationDashboard:
    """
    Interactive validation dashboard for ongoing monitoring
    """
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
    
    def get_validation_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get validation history for the past N days"""
        try:
            # This would query a validation_history table if it existed
            # For now, return empty list
            return []
        except Exception as e:
            self.logger.error(f"Error getting validation history: {e}")
            return []
    
    def get_data_quality_trends(self) -> Dict[str, Any]:
        """Get data quality trends over time"""
        try:
            # Calculate quality metrics trends
            return {
                'success_rate_trend': [],
                'error_count_trend': [],
                'coverage_trend': []
            }
        except Exception as e:
            self.logger.error(f"Error calculating quality trends: {e}")
            return {}
    
    def generate_quality_alerts(self) -> List[Dict[str, Any]]:
        """Generate quality alerts for immediate attention"""
        alerts = []
        
        try:
            # Check for data quality degradation
            # This would analyze recent validation results
            pass
        except Exception as e:
            self.logger.error(f"Error generating quality alerts: {e}")
        
        return alerts
