#!/usr/bin/env python3
"""
Data Quality Monitoring System for National Archives Database

Tracks metadata completeness, identifies gaps, and provides quality metrics
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Tuple, Any
from collections import defaultdict
import click

class DataQualityMonitor:
    """Monitor and report on data quality metrics"""
    
    def __init__(self, db_path: str = "./data/discovery.db"):
        self.db_path = db_path
    
    def get_field_completeness(self) -> Dict[str, float]:
        """Calculate completeness percentage for each field"""
        conn = sqlite3.connect(self.db_path)
        
        # Get all field names
        cursor = conn.execute('PRAGMA table_info(records)')
        fields = [col[1] for col in cursor.fetchall()]
        
        # Count NULL/empty values for each field
        field_stats = {}
        total_records = 0
        
        cursor = conn.execute('SELECT COUNT(*) FROM records')
        total_records = cursor.fetchone()[0]
        
        for field in fields:
            cursor = conn.execute(f'SELECT COUNT(*) FROM records WHERE {field} IS NULL OR {field} = ""')
            null_count = cursor.fetchone()[0]
            completeness = ((total_records - null_count) / total_records) * 100
            field_stats[field] = completeness
        
        conn.close()
        return field_stats
    
    def get_critical_gaps(self) -> List[Tuple[str, float]]:
        """Identify fields with critical completeness gaps (< 10%)"""
        field_stats = self.get_field_completeness()
        critical_fields = []
        
        for field, completeness in field_stats.items():
            if completeness < 10:
                critical_fields.append((field, completeness))
        
        # Sort by completeness (worst first)
        critical_fields.sort(key=lambda x: x[1])
        return critical_fields
    
    def get_series_quality_report(self, series_pattern: str = "CO %") -> Dict[str, Any]:
        """Generate quality report for specific series"""
        conn = sqlite3.connect(self.db_path)
        
        # Get records for series
        cursor = conn.execute(
            'SELECT * FROM records WHERE reference LIKE ?', 
            (series_pattern,)
        )
        records = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        if not records:
            conn.close()
            return {"error": "No records found for series pattern"}
        
        # Analyze quality for each field
        field_quality = {}
        total_records = len(records)
        
        for i, column in enumerate(columns):
            if column in ['id', 'created_at', 'updated_at']:  # Skip system fields
                continue
                
            non_empty_count = sum(1 for record in records if record[i] and str(record[i]).strip())
            quality = (non_empty_count / total_records) * 100
            field_quality[column] = {
                'completeness': quality,
                'filled_count': non_empty_count,
                'empty_count': total_records - non_empty_count
            }
        
        conn.close()
        
        return {
            'series_pattern': series_pattern,
            'total_records': total_records,
            'field_quality': field_quality,
            'overall_quality': sum(f['completeness'] for f in field_quality.values()) / len(field_quality)
        }
    
    def get_metadata_enrichment_opportunities(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Identify records that would benefit from metadata enrichment"""
        conn = sqlite3.connect(self.db_path)
        
        # Find records with missing critical metadata
        query = """
            SELECT id, reference, title, scope_content, administrator_background, 
                   catalogue_id, covering_dates, legal_status
            FROM records 
            WHERE (scope_content IS NULL OR scope_content = '') 
               OR (administrator_background IS NULL OR administrator_background = '')
               OR (catalogue_id IS NULL)
               OR (covering_dates IS NULL OR covering_dates = '')
            LIMIT ?
        """
        
        cursor = conn.execute(query, (limit,))
        opportunities = []
        
        for row in cursor.fetchall():
            opportunities.append({
                'id': row[0],
                'reference': row[1],
                'title': row[2],
                'missing_scope_content': not row[3] or row[3] == '',
                'missing_admin_background': not row[4] or row[4] == '',
                'missing_catalogue_id': row[5] is None,
                'missing_covering_dates': not row[6] or row[6] == ''
            })
        
        conn.close()
        return opportunities
    
    def generate_quality_report(self) -> Dict[str, Any]:
        """Generate comprehensive quality report"""
        field_stats = self.get_field_completeness()
        critical_gaps = self.get_critical_gaps()
        
        # Categorize fields
        categories = {
            'Core Metadata': ['id', 'title', 'description', 'reference', 'archive'],
            'Descriptive Content': ['scope_content', 'administrator_background', 'custodial_history'],
            'Hierarchical Structure': ['parent_id', 'level', 'child_count'],
            'Access & Legal': ['access_conditions', 'closure_status', 'legal_status'],
            'Physical Characteristics': ['physical_description', 'dimensions', 'arrangement'],
            'Digital & Online': ['web_links', 'digital_files', 'digitised'],
            'Administrative': ['provenance', 'created_at', 'updated_at']
        }
        
        category_quality = {}
        for category, fields in categories.items():
            category_fields = [f for f in fields if f in field_stats]
            if category_fields:
                avg_quality = sum(field_stats[f] for f in category_fields) / len(category_fields)
                category_quality[category] = {
                    'fields': category_fields,
                    'average_quality': avg_quality,
                    'field_details': {f: field_stats[f] for f in category_fields}
                }
        
        return {
            'timestamp': datetime.now().isoformat(),
            'total_fields': len(field_stats),
            'overall_average_quality': sum(field_stats.values()) / len(field_stats),
            'critical_gaps_count': len(critical_gaps),
            'critical_gaps': critical_gaps,
            'category_quality': category_quality,
            'field_completeness': field_stats
        }
    
    def export_quality_report(self, output_file: str = None):
        """Export quality report to file"""
        report = self.generate_quality_report()
        
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"data_quality_report_{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"✅ Quality report exported to: {output_file}")
        return output_file


@click.group()
def cli():
    """Data Quality Monitoring System"""
    pass


@cli.command()
@click.option('--output', '-o', help='Output file for report')
def generate_report(output):
    """Generate comprehensive data quality report"""
    monitor = DataQualityMonitor()
    
    click.echo("🔍 GENERATING DATA QUALITY REPORT")
    click.echo("=" * 60)
    
    report = monitor.generate_quality_report()
    
    # Display summary
    click.echo(f"📊 OVERALL QUALITY: {report['overall_average_quality']:.1f}%")
    click.echo(f"📋 TOTAL FIELDS: {report['total_fields']}")
    click.echo(f"🚨 CRITICAL GAPS: {report['critical_gaps_count']}")
    
    # Show critical gaps
    if report['critical_gaps']:
        click.echo(f"\n🚨 CRITICAL GAPS (< 10% complete):")
        for field, completeness in report['critical_gaps'][:10]:  # Top 10
            click.echo(f"  ❌ {field}: {completeness:.1f}%")
    
    # Show category quality
    click.echo(f"\n📂 CATEGORY QUALITY:")
    for category, data in report['category_quality'].items():
        status = "✅" if data['average_quality'] >= 80 else "⚠️" if data['average_quality'] >= 50 else "❌"
        click.echo(f"  {status} {category}: {data['average_quality']:.1f}%")
    
    # Export if requested
    if output:
        monitor.export_quality_report(output)
    else:
        monitor.export_quality_report()


@cli.command()
@click.argument('series_pattern', default='CO %')
def series_quality(series_pattern):
    """Analyze quality for specific series"""
    monitor = DataQualityMonitor()
    
    click.echo(f"🔍 SERIES QUALITY ANALYSIS: {series_pattern}")
    click.echo("=" * 60)
    
    report = monitor.get_series_quality_report(series_pattern)
    
    if 'error' in report:
        click.echo(f"❌ {report['error']}")
        return
    
    click.echo(f"📊 Total Records: {report['total_records']}")
    click.echo(f"📊 Overall Quality: {report['overall_quality']:.1f}%")
    
    # Show field quality
    click.echo(f"\n📋 FIELD QUALITY:")
    for field, data in report['field_quality'].items():
        if data['completeness'] < 50:  # Focus on problematic fields
            status = "❌" if data['completeness'] < 10 else "⚠️"
            click.echo(f"  {status} {field}: {data['completeness']:.1f}% "
                      f"({data['filled_count']}/{report['total_records']})")


@cli.command()
@click.option('--limit', '-l', default=50, help='Maximum opportunities to show')
def enrichment_opportunities(limit):
    """Show metadata enrichment opportunities"""
    monitor = DataQualityMonitor()
    
    click.echo("🔍 METADATA ENRICHMENT OPPORTUNITIES")
    click.echo("=" * 60)
    
    opportunities = monitor.get_metadata_enrichment_opportunities(limit)
    
    if not opportunities:
        click.echo("✅ No enrichment opportunities found!")
        return
    
    click.echo(f"📊 Found {len(opportunities)} records with enrichment opportunities")
    
    # Group by series
    series_groups = defaultdict(list)
    for opp in opportunities:
        series = opp['reference'].split('/')[0] if '/' in opp['reference'] else opp['reference']
        series_groups[series].append(opp)
    
    for series, records in series_groups.items():
        click.echo(f"\n📂 {series} ({len(records)} records):")
        for record in records[:3]:  # Show first 3 per series
            missing_fields = []
            if record['missing_scope_content']:
                missing_fields.append('scope_content')
            if record['missing_admin_background']:
                missing_fields.append('admin_background')
            if record['missing_catalogue_id']:
                missing_fields.append('catalogue_id')
            if record['missing_covering_dates']:
                missing_fields.append('covering_dates')
            
            click.echo(f"  • {record['reference']}: {record['title'][:50]}...")
            click.echo(f"    Missing: {', '.join(missing_fields)}")
        
        if len(records) > 3:
            click.echo(f"    ... and {len(records) - 3} more")


if __name__ == '__main__':
    cli()
