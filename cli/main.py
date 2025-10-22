"""
Command-line interface for National Archives Discovery clone
"""

import click
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from tqdm import tqdm
import json
import statistics
from datetime import datetime
import time

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.client import DiscoveryClient
from storage.database import DatabaseManager
from storage.cache import CacheManager
try:
    from search.semantic_search import SemanticSearchEngine, SEMANTIC_SEARCH_AVAILABLE
except ImportError:
    SEMANTIC_SEARCH_AVAILABLE = False
    SemanticSearchEngine = None
from search.query_processor import QueryProcessor

# Load environment variables
load_dotenv('config.env')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/discovery.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


@click.group()
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.option('--config', help='Path to configuration file')
@click.pass_context
def cli(ctx, debug, config):
    """National Archives Discovery Catalogue Clone - Respectful archival research tool"""
    
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Ensure required directories exist
    Path('./data').mkdir(exist_ok=True)
    Path('./logs').mkdir(exist_ok=True)
    
    # Initialize context
    ctx.ensure_object(dict)
    ctx.obj['debug'] = debug
    ctx.obj['config'] = config


@cli.command()
@click.argument('query')
@click.option('--limit', '-l', default=20, help='Maximum results to display')
@click.option('--collection', '-c', help='Filter by collection')
@click.option('--archive', '-a', help='Filter by archive')
@click.option('--semantic', '-s', is_flag=True, help='Use semantic search')
@click.option('--export', '-e', help='Export results to file (JSON/CSV)')
@click.pass_context
def search(ctx, query, limit, collection, archive, semantic, export):
    """Search the Discovery catalogue"""
    
    try:
        # Initialize components
        db_manager = DatabaseManager()
        
        # Prepare filters
        filters = {}
        if collection:
            filters['collection'] = collection
        if archive:
            filters['archive'] = archive
        
        if semantic:
            # Use semantic search
            if not SEMANTIC_SEARCH_AVAILABLE:
                click.echo("❌ Semantic search not available. Install dependencies: pip install sentence-transformers chromadb", err=True)
                return
            
            search_engine = SemanticSearchEngine()
            
            with click.progressbar(length=1, label='Performing semantic search') as bar:
                results = search_engine.semantic_search(query, limit, filters)
                bar.update(1)
            
            click.echo(f"\n🔍 Semantic search results for: '{query}'")
            click.echo(f"Found {len(results)} results\n")
            
            for i, (record, score) in enumerate(results, 1):
                click.echo(f"{i}. {record.title}")
                click.echo(f"   📊 Relevance: {score:.3f}")
                if record.reference:
                    click.echo(f"   📋 Reference: {record.reference}")
                if record.collection:
                    click.echo(f"   📚 Collection: {record.collection}")
                if record.date_from or record.date_to:
                    date_range = f"{record.date_from or ''} - {record.date_to or ''}".strip(' -')
                    click.echo(f"   📅 Date: {date_range}")
                if record.description:
                    desc = record.description[:200] + "..." if len(record.description) > 200 else record.description
                    click.echo(f"   📝 {desc}")
                click.echo()
        
        else:
            # Use traditional search
            with click.progressbar(length=1, label='Searching database') as bar:
                records = db_manager.search_records(query, limit, filters=filters)
                bar.update(1)
            
            click.echo(f"\n🔍 Search results for: '{query}'")
            click.echo(f"Found {len(records)} results\n")
            
            for i, record in enumerate(records, 1):
                click.echo(f"{i}. {record.title}")
                if record.reference:
                    click.echo(f"   📋 Reference: {record.reference}")
                if record.collection:
                    click.echo(f"   📚 Collection: {record.collection}")
                if record.date_from or record.date_to:
                    date_range = f"{record.date_from or ''} - {record.date_to or ''}".strip(' -')
                    click.echo(f"   📅 Date: {date_range}")
                if record.description:
                    desc = record.description[:200] + "..." if len(record.description) > 200 else record.description
                    click.echo(f"   📝 {desc}")
                click.echo()
        
        # Export results if requested
        if export:
            export_results(results if semantic else [(r, 0.0) for r in records], export, query)
    
    except Exception as e:
        click.echo(f"❌ Search failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command()
@click.argument('query')
# No page limits - will fetch ALL available records
@click.option('--per-page', default=100, help='Records per page')
@click.option('--collection', '-c', help='Filter by collection')
@click.pass_context
def fetch(ctx, query, per_page, collection):
    """Fetch records from Discovery API and store locally"""
    
    try:
        # Initialize components - IP-based access, no API key needed
        client = DiscoveryClient()
        db_manager = DatabaseManager()
        cache_manager = CacheManager()
        
        click.echo(f"🔍 Fetching records for: '{query}'")
        click.echo(f"📊 Per page: {per_page} (NO PAGE LIMITS - will fetch ALL records)")
        
        # Check 5-minute rate limit
        # Note: We rely on the API client's built-in rate limiting
        
        # Prepare filters
        filters = {}
        if collection:
            filters['collection'] = collection
        
        total_records = 0
        
        with click.progressbar(
            client.search_all_pages(query, 1000, per_page),  # Use very high limit, API will stop when done
            label='Fetching records'
        ) as records:
            
            batch = []
            for record in records:
                batch.append(record)
                total_records += 1
                
                # Store in batches of 100
                if len(batch) >= 100:
                    stored = db_manager.store_records(batch)
                    batch = []
                
                # The API client handles rate limiting automatically
            
            # Store remaining records
            if batch:
                db_manager.store_records(batch)
        
        click.echo(f"\n✅ Successfully fetched and stored {total_records} records")
        
        # Log the API usage
        db_manager.log_api_request('search', query, 200, total_records)
        
    except Exception as e:
        click.echo(f"❌ Fetch failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command()
@click.argument('series')
@click.option('--per-page', '-p', default=100, help='Records per page (max 100)')
@click.pass_context
def fetch_series(ctx, series, per_page):
    """Fetch all records from a specific record series (e.g., 'CO 1', 'WO 95') with automatic metadata enrichment"""
    
    try:
        client = DiscoveryClient()
        db_manager = DatabaseManager()
        
        click.echo(f"🗂️  Fetching records from series: {series}")
        click.echo(f"📊 Per page: {per_page} (NO PAGE LIMITS - will fetch ALL records)")
        click.echo(f"🔍 Automatic metadata enrichment: ENABLED (will fetch detailed metadata for each record)")
        
        total_records = 0
        current_page = 0  # Start from page 0
        
        with tqdm(desc="Fetching series records", unit="page") as pbar:
            while True:  # Continue until no more records
                # Use the new record series search method with Discovery API parameters
                api_response = client.search_record_series(
                    series=series,
                    page=current_page,
                    results_page_size=per_page
                )
                
                # Parse records from the response
                raw_records = api_response.get('records', [])
                if not raw_records:
                    click.echo(f"📝 No more records found at page {current_page}")
                    break
                
                # Convert to Record objects with basic metadata
                from api.models import Record
                records = [Record.from_api_response(record) for record in raw_records]
                
                # ENHANCED: Automatically enrich each record with detailed metadata
                enriched_records = []
                click.echo(f"🔍 Enriching {len(records)} records with detailed metadata...")
                
                for i, record in enumerate(records, 1):
                    try:
                        # Fetch detailed metadata for each record
                        detailed_data = client.get_record_details(record.id)
                        if detailed_data:
                            # Create enriched record with detailed metadata
                            enriched_record = Record.from_detailed_api_response(detailed_data)
                            enriched_records.append(enriched_record)
                            click.echo(f"  ✅ Enriched {i}/{len(records)}: {enriched_record.reference or enriched_record.id}")
                        else:
                            # Fallback to basic record if detailed fetch fails
                            enriched_records.append(record)
                            click.echo(f"  ⚠️  Basic metadata only for {i}/{len(records)}: {record.reference or record.id}")
                        
                        # Rate limiting to be respectful to the API
                        import time
                        time.sleep(0.5)
                        
                    except Exception as e:
                        click.echo(f"  ❌ Failed to enrich record {i}: {e}")
                        # Fallback to basic record
                        enriched_records.append(record)
                
                # Ensure we have the right number of records
                if len(enriched_records) != len(records):
                    click.echo(f"⚠️  Warning: Expected {len(records)} records, got {len(enriched_records)}")
                    # Use basic records if enrichment failed
                    enriched_records = records
                
                # Store enriched records in database
                try:
                    stored_count = db_manager.store_records(enriched_records)
                    total_records += stored_count
                except Exception as e:
                    click.echo(f"❌ Failed to store enriched records: {e}")
                    # Fallback to storing basic records
                    stored_count = db_manager.store_records(records)
                    total_records += stored_count
                
                # Check if we've reached the end (no more records)
                if len(raw_records) < per_page:
                    click.echo(f"📝 Reached end of series at page {current_page} (only {len(raw_records)} records)")
                    # Update progress bar for the current page before breaking
                    pbar.update(1)
                    pbar.set_postfix({"total": f"{total_records:,}", "page": current_page + 1})
                    break
                
                current_page += 1
                pbar.update(1)
                pbar.set_postfix({"total": f"{total_records:,}", "page": current_page})
        
        click.echo(f"\n✅ Successfully fetched and stored {total_records:,} records from {series} series")
        click.echo(f"🎯 All records automatically enriched with detailed metadata!")
        
        # Log the API usage
        db_manager.log_api_request('fetch_series_enriched', series, 200, total_records)
        
    except Exception as e:
        click.echo(f"❌ Series fetch failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command()
@click.option('--limit', '-l', default=50, help='Number of popular searches to process')
# No page limits - will fetch ALL available records
@click.pass_context
def bootstrap(ctx, limit):
    """Bootstrap the database with popular searches"""
    
    try:
        client = DiscoveryClient()
        db_manager = DatabaseManager()
        
        # Get popular search terms
        popular_searches = client.get_popular_searches()
        
        click.echo(f"🚀 Bootstrapping database with {len(popular_searches)} popular searches")
        
        total_records = 0
        
        for i, query in enumerate(popular_searches, 1):
            click.echo(f"\n[{i}/{len(popular_searches)}] Fetching: {query}")
            
            try:
                # The API client handles rate limiting automatically
                
                records_count = 0
                batch = []
                
                for record in client.search_all_pages(query, 1000, 100):  # Use very high limit, API will stop when done
                    batch.append(record)
                    records_count += 1
                    
                    if len(batch) >= 100:
                        db_manager.store_records(batch)
                        batch = []
                
                if batch:
                    db_manager.store_records(batch)
                
                total_records += records_count
                click.echo(f"   📊 Stored {records_count} records")
                
                # Log API usage
                db_manager.log_api_request('search', query, 200, records_count)
                
            except Exception as e:
                click.echo(f"   ❌ Failed to fetch '{query}': {e}")
                continue
        
        click.echo(f"\n✅ Bootstrap completed. Total records stored: {total_records}")
        
    except Exception as e:
        click.echo(f"❌ Bootstrap failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command()
@click.option('--batch-size', '-b', default=100, help='Batch size for indexing')
@click.option('--reset', is_flag=True, help='Reset index before rebuilding')
@click.pass_context
def index(ctx, batch_size, reset):
    """Build semantic search index from stored records"""
    
    if not SEMANTIC_SEARCH_AVAILABLE:
        click.echo("❌ Semantic search not available. Install dependencies: pip install sentence-transformers chromadb", err=True)
        return
    
    try:
        db_manager = DatabaseManager()
        search_engine = SemanticSearchEngine()
        
        if reset:
            click.echo("🔄 Resetting semantic search index...")
            search_engine.reset_index()
        
        # Get all records for indexing
        click.echo("📊 Getting records from database...")
        
        # Use a simple query to get all records
        all_records = db_manager.search_records("", limit=100000)  # Large limit to get all
        
        if not all_records:
            click.echo("❌ No records found in database. Run 'fetch' or 'bootstrap' first.")
            return
        
        click.echo(f"🔍 Indexing {len(all_records)} records...")
        
        # Index in batches with progress bar
        indexed_count = 0
        
        with click.progressbar(
            range(0, len(all_records), batch_size),
            label='Building index'
        ) as batch_starts:
            
            for start in batch_starts:
                end = min(start + batch_size, len(all_records))
                batch = all_records[start:end]
                
                batch_indexed = search_engine.index_records_batch(batch, len(batch))
                indexed_count += batch_indexed
        
        click.echo(f"\n✅ Successfully indexed {indexed_count} records")
        
        # Show index statistics
        stats = search_engine.get_index_stats()
        click.echo(f"📈 Index statistics:")
        click.echo(f"   Total indexed: {stats.get('total_records_indexed', 0)}")
        click.echo(f"   Model: {stats.get('model_name', 'unknown')}")
        
    except Exception as e:
        click.echo(f"❌ Indexing failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command('traverse-co')
@click.option('--max-records', '-m', type=int, help='Maximum records to process')
@click.option('--resume', '-r', is_flag=True, help='Resume interrupted traversal')
@click.pass_context
def traverse_co(ctx, max_records, resume):
    """Start complete Colonial Office series hierarchical traversal (Workflow.md implementation)"""
    
    try:
        from api.client import DiscoveryClient
        from api.traversal import HierarchicalTraverser
        from storage.database import DatabaseManager
        
        client = DiscoveryClient()
        db_manager = DatabaseManager()
        traverser = HierarchicalTraverser(client, db_manager)
        
        if resume:
            click.echo("🔄 Resuming interrupted CO traversal...")
            results = traverser.resume_traversal(max_records)
        else:
            click.echo("🏛️  Starting complete Colonial Office series traversal")
            click.echo("📋 This will systematically traverse from C57 (CO Department) → all series → sub-series → pieces → items")
            
            if max_records:
                click.echo(f"📊 Limited to {max_records:,} records")
            else:
                click.echo("⚠️  No limit set - this will process ALL CO records (potentially millions)")
                if not click.confirm("Continue with unlimited traversal?"):
                    return
            
            results = traverser.start_co_traversal(max_records)
        
        # Display results
        click.echo(f"\n✅ Traversal completed!")
        click.echo(f"📊 Processed: {results['processed_count']:,} records")
        click.echo(f"❌ Failed: {results['failed_count']:,} records")
        click.echo(f"⏭️  Skipped: {results['skipped_count']:,} records")
        click.echo(f"⏱️  Duration: {results['duration_seconds']:.1f} seconds")
        
        # Queue statistics
        queue_stats = results.get('queue_stats', {})
        click.echo(f"\n📋 Final Queue Status:")
        for status, count in queue_stats.items():
            click.echo(f"   {status}: {count:,}")
        
    except Exception as e:
        click.echo(f"❌ Traversal failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command('traverse-series')
@click.argument('series_id')
@click.option('--max-records', '-m', type=int, help='Maximum records to process')
@click.pass_context
def traverse_series(ctx, series_id, max_records):
    """Start traversal of specific CO series (e.g., C243 for CO 1)"""
    
    try:
        from api.client import DiscoveryClient
        from api.traversal import HierarchicalTraverser
        from storage.database import DatabaseManager
        
        client = DiscoveryClient()
        db_manager = DatabaseManager()
        traverser = HierarchicalTraverser(client, db_manager)
        
        click.echo(f"🗂️  Starting traversal of series: {series_id}")
        
        results = traverser.start_specific_series_traversal(series_id, max_records)
        
        # Display results
        click.echo(f"\n✅ Series traversal completed!")
        click.echo(f"📊 Processed: {results['processed_count']:,} records")
        click.echo(f"❌ Failed: {results['failed_count']:,} records")
        click.echo(f"⏱️  Duration: {results['duration_seconds']:.1f} seconds")
        
    except Exception as e:
        click.echo(f"❌ Series traversal failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command('traversal-status')
@click.pass_context
def traversal_status(ctx):
    """Show current traversal status and queue statistics"""
    
    try:
        from api.client import DiscoveryClient
        from api.traversal import HierarchicalTraverser
        from storage.database import DatabaseManager
        
        client = DiscoveryClient()
        db_manager = DatabaseManager()
        traverser = HierarchicalTraverser(client, db_manager)
        
        status = traverser.get_traversal_status()
        
        click.echo("📊 Traversal Status:")
        click.echo(f"   Active: {'Yes' if status['is_active'] else 'No'}")
        click.echo(f"   Total processed: {status['total_processed']:,}")
        
        click.echo("\n📋 Crawl Queue Statistics:")
        for queue_status, count in status['queue_statistics'].items():
            icon = {"QUEUED": "⏳", "PROCESSING": "🔄", "COMPLETED": "✅", "FAILED": "❌"}.get(queue_status, "📄")
            click.echo(f"   {icon} {queue_status}: {count:,}")
        
    except Exception as e:
        click.echo(f"❌ Failed to get traversal status: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command('validate')
@click.option('--type', '-t', 'validation_type', 
              type=click.Choice(['full', 'count', 'schema', 'hierarchy', 'provenance']),
              default='full', help='Type of validation to run')
@click.option('--series', '-s', help='Specific series to validate (e.g., "CO 1")')
@click.option('--sample-size', '-n', type=int, default=100, 
              help='Sample size for schema validation')
@click.option('--report-format', '-f', 
              type=click.Choice(['console', 'json', 'csv']),
              multiple=True, default=['console'],
              help='Report output format(s)')
@click.option('--save-report', '-o', help='Directory to save validation reports')
@click.pass_context
def validate(ctx, validation_type, series, sample_size, report_format, save_report):
    """Run comprehensive data validation checks"""
    
    try:
        from validation.validators import DataValidator
        from validation.reports import ValidationReport
        from storage.database import DatabaseManager
        from api.client import DiscoveryClient
        
        click.echo(f"🔍 Starting {validation_type} validation...")
        
        # Initialize components
        db_manager = DatabaseManager()
        api_client = DiscoveryClient()
        validator = DataValidator(db_manager, api_client)
        
        # Run validation based on type
        if validation_type == 'full':
            click.echo("📊 Running complete validation suite...")
            results = validator.run_full_validation(
                series_list=[series] if series else None,
                schema_sample_size=sample_size
            )
        elif validation_type == 'count':
            click.echo("🔢 Running count validation...")
            if series:
                results = validator.validate_series(series)
            else:
                results = validator.count_validator.validate_series_counts()
                results = {'count_validation': results, 'results': [r.__dict__ for r in validator.count_validator.get_results()]}
        elif validation_type == 'schema':
            click.echo("📋 Running schema validation...")
            schema_result = validator.schema_validator.validate_records_schema(sample_size)
            constraint_result = validator.schema_validator.validate_database_constraints()
            results = {
                'schema_validation': schema_result and constraint_result,
                'results': [r.__dict__ for r in validator.schema_validator.get_results()]
            }
        elif validation_type == 'hierarchy':
            click.echo("🌳 Running hierarchy validation...")
            hierarchy_result = validator.hierarchy_validator.validate_hierarchy_integrity()
            results = {
                'hierarchy_validation': hierarchy_result,
                'results': [r.__dict__ for r in validator.hierarchy_validator.get_results()]
            }
        elif validation_type == 'provenance':
            click.echo("📜 Running provenance validation...")
            provenance_result = validator.provenance_validator.validate_provenance_integrity()
            results = {
                'provenance_validation': provenance_result,
                'results': [r.__dict__ for r in validator.provenance_validator.get_results()]
            }
        
        # Generate and display report
        if validation_type == 'full':
            report = ValidationReport(results)
            
            # Display console report
            if 'console' in report_format:
                click.echo("\n" + report.generate_console_report())
            
            # Save reports if requested
            if save_report:
                saved_files = report.save_report(save_report, list(report_format))
                click.echo(f"\n📁 Reports saved:")
                for format_name, file_path in saved_files.items():
                    click.echo(f"  • {format_name}: {file_path}")
        else:
            # Simple validation result display
            overall_status = "✅ PASS" if results.get(f'{validation_type}_validation', False) else "❌ FAIL"
            click.echo(f"\n{overall_status} {validation_type.title()} validation completed")
            
            # Show key results
            for result in results.get('results', [])[:10]:
                status_icon = {'PASS': '✅', 'FAIL': '❌', 'WARNING': '⚠️', 'ERROR': '💥'}.get(result['status'], '📄')
                click.echo(f"  {status_icon} {result['check_name']}: {result['message']}")
        
    except Exception as e:
        click.echo(f"❌ Validation failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command('validate-series')
@click.argument('series')
@click.option('--check-counts', '-c', is_flag=True, help='Check record counts against TNA')
@click.option('--check-hierarchy', '-h', is_flag=True, help='Check hierarchy integrity')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed results')
@click.pass_context
def validate_series(ctx, series, check_counts, check_hierarchy, verbose):
    """Quick validation for a specific series"""
    
    try:
        from validation.validators import DataValidator
        from storage.database import DatabaseManager
        from api.client import DiscoveryClient
        
        click.echo(f"🗂️  Validating series: {series}")
        
        db_manager = DatabaseManager()
        api_client = DiscoveryClient()
        validator = DataValidator(db_manager, api_client)
        
        results = validator.validate_series(series)
        
        # Display results
        count_status = "✅ PASS" if results['count_validation'] else "❌ FAIL"
        hierarchy_status = "✅ PASS" if results['hierarchy_validation'] else "❌ FAIL"
        
        click.echo(f"  📊 Count validation: {count_status}")
        click.echo(f"  🌳 Hierarchy validation: {hierarchy_status}")
        
        if verbose:
            click.echo("\n📋 Detailed Results:")
            for result in results['results']:
                status_icon = {'PASS': '✅', 'FAIL': '❌', 'WARNING': '⚠️', 'ERROR': '💥'}.get(result['status'], '📄')
                click.echo(f"  {status_icon} {result['check_name']}: {result['message']}")
        
    except Exception as e:
        click.echo(f"❌ Series validation failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command('data-quality')
@click.option('--summary', '-s', is_flag=True, help='Show data quality summary')
@click.option('--trends', '-t', is_flag=True, help='Show quality trends')
@click.option('--alerts', '-a', is_flag=True, help='Show quality alerts')
@click.pass_context
def data_quality(ctx, summary, trends, alerts):
    """Show data quality dashboard"""
    
    try:
        from validation.reports import ValidationDashboard
        from storage.database import DatabaseManager
        
        db_manager = DatabaseManager()
        dashboard = ValidationDashboard(db_manager)
        
        if summary or not any([trends, alerts]):
            click.echo("📊 DATA QUALITY SUMMARY")
            click.echo("-" * 40)
            
            # Get basic database stats
            stats = db_manager.get_statistics()
            click.echo(f"Total records: {stats.get('total_records', 0):,}")
            
            # Would show validation history summary
            click.echo("Last validation: Not available")
            click.echo("Overall quality score: Not available")
        
        if trends:
            click.echo("\n📈 QUALITY TRENDS")
            click.echo("-" * 40)
            trends_data = dashboard.get_data_quality_trends()
            click.echo("Trend data not available yet")
        
        if alerts:
            click.echo("\n🚨 QUALITY ALERTS")
            click.echo("-" * 40)
            alerts_data = dashboard.generate_quality_alerts()
            if not alerts_data:
                click.echo("No quality alerts")
            else:
                for alert in alerts_data:
                    click.echo(f"⚠️  {alert['message']}")
        
    except Exception as e:
        click.echo(f"❌ Data quality dashboard failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command('provenance')
@click.option('--record-id', '-r', help='Show provenance for specific record')
@click.option('--lineage', '-l', is_flag=True, help='Show full data lineage')
@click.option('--report', '-R', is_flag=True, help='Generate comprehensive report')
@click.option('--start-date', help='Start date for report (YYYY-MM-DD)')
@click.option('--end-date', help='End date for report (YYYY-MM-DD)')
@click.option('--save-to', '-o', help='Save report to file')
@click.pass_context
def provenance(ctx, record_id, lineage, report, start_date, end_date, save_to):
    """Show provenance and data lineage information"""
    
    try:
        from utils.provenance import get_provenance_tracker
        from storage.database import DatabaseManager
        
        db_manager = DatabaseManager()
        tracker = get_provenance_tracker(db_manager)
        
        if record_id:
            # Show provenance for specific record
            click.echo(f"📜 Provenance for record: {record_id}")
            
            if lineage:
                # Show full data lineage
                lineage_obj = tracker.create_data_lineage(record_id)
                if lineage_obj:
                    click.echo("\n🔗 DATA LINEAGE:")
                    click.echo(f"  Source: {lineage_obj.source_system}")
                    click.echo(f"  URL: {lineage_obj.source_url}")
                    click.echo(f"  Extracted: {lineage_obj.extraction_timestamp}")
                    click.echo(f"  Parser: {lineage_obj.parser_version}")
                    click.echo(f"  Quality: {lineage_obj.quality_score or 'Not calculated'}")
                    click.echo(f"  Confidence: {lineage_obj.confidence_level or 'Not calculated'}")
                    
                    if lineage_obj.transformation_history:
                        click.echo(f"\n🔄 TRANSFORMATIONS ({len(lineage_obj.transformation_history)}):")
                        for i, transform in enumerate(lineage_obj.transformation_history[:5]):
                            click.echo(f"  {i+1}. {transform.get('type', 'Unknown')}: {transform.get('description', 'No description')}")
                    
                    if lineage_obj.validation_history:
                        click.echo(f"\n✅ VALIDATIONS ({len(lineage_obj.validation_history)}):")
                        for i, validation in enumerate(lineage_obj.validation_history[:5]):
                            status_icon = {'PASS': '✅', 'FAIL': '❌', 'WARNING': '⚠️', 'ERROR': '💥'}.get(validation.get('status'), '📄')
                            click.echo(f"  {status_icon} {validation.get('validation_type', 'Unknown')}: {validation.get('status', 'Unknown')}")
                else:
                    click.echo("❌ No lineage data found for this record")
            else:
                # Show basic provenance
                # This would query the database for basic provenance info
                click.echo("Basic provenance display not yet implemented")
        
        elif report:
            # Generate comprehensive provenance report
            click.echo("📊 Generating comprehensive provenance report...")
            
            report_data = tracker.generate_provenance_report(
                start_date=start_date,
                end_date=end_date
            )
            
            # Display summary
            summary = report_data.get('summary', {})
            click.echo(f"\n📈 PROVENANCE REPORT SUMMARY:")
            click.echo(f"  Total records: {summary.get('total_records', 0):,}")
            click.echo(f"  Records with lineage: {summary.get('records_with_lineage', 0):,}")
            click.echo(f"  Average quality score: {summary.get('average_quality_score', 0):.3f}")
            
            # Show statistics
            stats = report_data.get('statistics', {})
            if stats.get('source_methods'):
                click.echo(f"\n📊 SOURCE METHODS:")
                for method, count in stats['source_methods'].items():
                    click.echo(f"  • {method}: {count:,} records")
            
            # Show recommendations
            recommendations = report_data.get('recommendations', [])
            if recommendations:
                click.echo(f"\n💡 RECOMMENDATIONS:")
                for rec in recommendations[:5]:
                    click.echo(f"  • {rec}")
            
            # Save report if requested
            if save_to:
                import json
                with open(save_to, 'w') as f:
                    json.dump(report_data, f, indent=2, default=str)
                click.echo(f"\n📁 Report saved to: {save_to}")
        
        else:
            # Show general provenance statistics
            click.echo("📊 PROVENANCE SYSTEM STATUS")
            click.echo("-" * 40)
            click.echo(f"Session ID: {tracker.session_id}")
            click.echo(f"System: {tracker.system_info.get('platform', 'Unknown')}")
            click.echo(f"Python: {tracker.system_info.get('python_version', 'Unknown').split()[0]}")
            click.echo("\nUse --help for more options")
        
    except Exception as e:
        click.echo(f"❌ Provenance operation failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command()
@click.pass_context
def stats(ctx):
    """Show database and system statistics"""
    
    try:
        db_manager = DatabaseManager()
        cache_manager = CacheManager()
        
        click.echo("📊 National Archives Discovery Clone Statistics\n")
        
        # Database statistics
        db_stats = db_manager.get_statistics()
        click.echo("🗄️  Database:")
        click.echo(f"   Total records: {db_stats.get('total_records', 0):,}")
        click.echo(f"   Database size: {db_stats.get('database_size', 0) / (1024*1024):.1f} MB")
        
        if db_stats.get('archives'):
            click.echo(f"   Top archives:")
            for archive, count in list(db_stats['archives'].items())[:5]:
                click.echo(f"     • {archive}: {count:,} records")
        
        # Collections
        collections = db_manager.get_collections()
        if collections:
            click.echo(f"\n📚 Collections ({len(collections)} total):")
            for coll in collections[:10]:
                click.echo(f"   • {coll['collection']}: {coll['record_count']:,} records")
        
        # Cache statistics
        cache_stats = cache_manager.get_cache_stats()
        click.echo(f"\n💾 Cache:")
        click.echo(f"   Active entries: {cache_stats.get('active_entries', 0)}")
        click.echo(f"   Cache size: {cache_stats.get('size_mb', 0)} MB")
        
        # API usage
        today_requests = db_manager.get_daily_request_count()
        click.echo(f"\n🌐 API Usage (today):")
        click.echo(f"   Requests made: {today_requests}/3000")
        click.echo(f"   Remaining: {3000 - today_requests}")
        
        # Semantic search index
        if SEMANTIC_SEARCH_AVAILABLE:
            try:
                search_engine = SemanticSearchEngine()
                index_stats = search_engine.get_index_stats()
                
                click.echo(f"\n🧠 Semantic Search:")
                click.echo(f"   Indexed records: {index_stats.get('total_records_indexed', 0):,}")
                click.echo(f"   Model: {index_stats.get('model_name', 'Not loaded')}")
            except Exception:
                click.echo(f"\n🧠 Semantic Search: Index not built")
        else:
            click.echo(f"\n🧠 Semantic Search: Not available (install dependencies)")
        
    except Exception as e:
        click.echo(f"❌ Failed to get statistics: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command()
@click.option('--limit', '-l', default=10, help='Number of records to display')
@click.option('--reference', '-r', help='Filter by reference (e.g., CO, WO, FO)')
@click.pass_context
def list_records(ctx, limit, reference):
    """List records in the database"""
    
    try:
        db_manager = DatabaseManager()
        
        # Build query
        query = "SELECT id, reference, title, date_from, date_to FROM records"
        params = []
        
        if reference:
            # Fix: Use proper archival reference matching
            # For series like "CO 1", we want to match:
            # - "CO 1" (exact series)
            # - "CO 1/" (series with sub-items)
            # - "CO 1/1", "CO 1/2", etc. (sub-items)
            # But NOT "CO 10", "CO 11", etc. (different series)
            
            # Split the reference to get series prefix
            if '/' in reference:
                # If reference contains "/", match the exact prefix
                series_prefix = reference.split('/')[0]
                query += " WHERE reference LIKE ? AND reference NOT LIKE ?"
                params.append(f"{reference}%")
                params.append(f"{series_prefix}%/%")  # Exclude other series
            else:
                # If reference is just a series (e.g., "CO 1"), match exactly
                query += " WHERE (reference = ? OR reference LIKE ?) AND reference NOT LIKE ?"
                params.append(reference)
                params.append(f"{reference}/%")
                params.append(f"{reference}%/%")  # Exclude other series like "CO 10"
        
        query += " ORDER BY reference, id LIMIT ?"
        params.append(limit)
        
        click.echo(f"📋 Records in Database (showing {limit} records):\n")
        
        import sqlite3
        with sqlite3.connect(db_manager.db_path) as conn:
            cursor = conn.execute(query, params)
            
            count = 0
            for row in cursor.fetchall():
                count += 1
                record_id, ref, title, date_from, date_to = row
                
                # Format dates
                date_str = ""
                if date_from and date_to:
                    date_str = f" ({date_from} - {date_to})"
                elif date_from:
                    date_str = f" ({date_from})"
                
                click.echo(f"{count:3d}. {ref or 'No Ref':<12} | {record_id:<12} | {title[:60]}...{date_str}")
        
        if count == 0:
            click.echo("   No records found!")
            click.echo("   Use 'python main.py fetch <query>' to add records.")
        
    except Exception as e:
        click.echo(f"❌ Failed to list records: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command()
@click.option('--host', default='localhost', help='Host to bind to')
@click.option('--port', default=8000, help='Port to bind to')
@click.option('--reload', is_flag=True, help='Enable auto-reload for development')
@click.pass_context
def serve(ctx, host, port, reload):
    """Start the web interface"""
    
    try:
        import uvicorn
        from web.app import app
        
        click.echo(f"🌐 Starting web interface at http://{host}:{port}")
        click.echo("   Press Ctrl+C to stop")
        
        uvicorn.run(
            "web.app:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info"
        )
        
    except ImportError:
        click.echo("❌ Web dependencies not installed. Run: pip install fastapi uvicorn", err=True)
    except Exception as e:
        click.echo(f"❌ Failed to start web server: {e}", err=True)
        if ctx.obj['debug']:
            raise


@cli.command()
@click.option('--days', default=30, help='Days of data to keep')
@click.pass_context
def cleanup(ctx, days):
    """Clean up old cache and log data"""
    
    try:
        db_manager = DatabaseManager()
        cache_manager = CacheManager()
        
        click.echo(f"🧹 Cleaning up data older than {days} days...")
        
        # Clean database
        db_manager.cleanup_old_data(days)
        
        # Clean cache
        cache_manager.cleanup_expired_cache()
        
        click.echo("✅ Cleanup completed")
        
    except Exception as e:
        click.echo(f"❌ Cleanup failed: {e}", err=True)
        if ctx.obj['debug']:
            raise


def export_results(results, filename, query):
    """Export search results to file"""
    
    try:
        if filename.endswith('.json'):
            # Export as JSON
            export_data = {
                'query': query,
                'timestamp': str(datetime.now()),
                'results': []
            }
            
            for record, score in results:
                result_data = record.to_dict()
                result_data['relevance_score'] = score
                export_data['results'].append(result_data)
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        elif filename.endswith('.csv'):
            # Export as CSV
            import csv
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow([
                    'Title', 'Reference', 'Collection', 'Archive', 
                    'Date From', 'Date To', 'Description', 'Relevance Score'
                ])
                
                # Data
                for record, score in results:
                    writer.writerow([
                        record.title,
                        record.reference or '',
                        record.collection or '',
                        record.archive or '',
                        record.date_from or '',
                        record.date_to or '',
                        record.description or '',
                        f"{score:.3f}"
                    ])
        
        click.echo(f"📄 Results exported to {filename}")
        
    except Exception as e:
        click.echo(f"❌ Export failed: {e}", err=True)


def main():
    """Main entry point"""
    cli()


@cli.command('advanced-search')
@click.option('--exact-phrase', '-e', help='Exact phrase to search for')
@click.option('--person', '-p', help='Search for a person')
@click.option('--place', '-pl', help='Search for a place')
@click.option('--departments', '-d', help='Comma-separated department codes (e.g., WO,ADM,AIR)')
@click.option('--start-year', '-sy', type=int, help='Start year for date filter')
@click.option('--end-year', '-ey', type=int, help='End year for date filter')
@click.option('--closure-status', '-cs', help='Closure status (O=Open, C=Closed, R=Retained, P=Pending)')
@click.option('--repository', '-repo', type=click.Choice(['ALL', 'TNA', 'OTH']), help='Repository filter')
@click.option('--online-only', '-online', is_flag=True, help='Only records with digital versions')
@click.option('--wildcard', '-w', help='Wildcard search (adds * suffix)')
@click.option('--and-terms', '-and', help='Two terms with AND (format: term1,term2)')
@click.option('--or-terms', '-or', help='Two terms with OR (format: term1,term2)')
@click.option('--not-terms', '-not', help='Include/exclude terms (format: include,exclude)')
@click.option('--fields', '-f', help='Restrict to fields (comma-separated: title,description,reference,people,places,subjects)')
@click.option('--sort', '-s', type=click.Choice(['RELEVANCE', 'REFERENCE_ASCENDING', 'DATE_ASCENDING', 'DATE_DESCENDING', 'TITLE_ASCENDING', 'TITLE_DESCENDING']), default='RELEVANCE', help='Sort option')
@click.option('--limit', '-l', type=int, default=20, help='Number of results to return')
@click.option('--preset', type=click.Choice(['wwi', 'wwii', 'colonial']), help='Use preset search configuration')
@click.pass_context
def advanced_search(ctx, exact_phrase, person, place, departments, start_year, end_year, 
                   closure_status, repository, online_only, wildcard, and_terms, or_terms, 
                   not_terms, fields, sort, limit, preset):
    """Advanced search with boolean operators, wildcards, and field restrictions (API Bible Section 5.1)"""
    try:
        from api.advanced_search import SmartQueryBuilder
        from api.client import DiscoveryClient
        
        # Initialize search builder
        if preset:
            builder = SmartQueryBuilder()
            if preset == 'wwi':
                builder.search_wwi_records()
            elif preset == 'wwii':
                builder.search_wwii_records()
            elif preset == 'colonial':
                builder.search_colonial_office()
        else:
            builder = SmartQueryBuilder()
        
        # Add search terms
        if exact_phrase:
            builder.exact_phrase(exact_phrase)
        
        if person:
            builder.search_person(person, approximate=True)
        
        if place:
            builder.search_place(place, approximate=True)
        
        if wildcard:
            builder.wildcard(wildcard)
        
        if and_terms:
            terms = and_terms.split(',')
            if len(terms) == 2:
                builder.boolean_and(terms[0].strip(), terms[1].strip())
            else:
                click.echo("Error: --and-terms requires exactly 2 terms separated by comma")
                return
        
        if or_terms:
            terms = or_terms.split(',')
            if len(terms) == 2:
                builder.boolean_or(terms[0].strip(), terms[1].strip())
            else:
                click.echo("Error: --or-terms requires exactly 2 terms separated by comma")
                return
        
        if not_terms:
            terms = not_terms.split(',')
            if len(terms) == 2:
                builder.boolean_not(terms[0].strip(), terms[1].strip())
            else:
                click.echo("Error: --not-terms requires exactly 2 terms separated by comma")
                return
        
        # Add filters
        if departments:
            dept_list = [d.strip().upper() for d in departments.split(',')]
            builder.add_departments(dept_list)
        
        if start_year and end_year:
            builder.add_date_range(start_year, end_year)
        
        if closure_status:
            builder.add_closure_status([closure_status.upper()])
        
        if repository:
            builder.add_repository_filter(repository)
        
        if online_only:
            builder.only_online(True)
        
        if fields:
            field_list = [f.strip() for f in fields.split(',')]
            builder.restrict_to_fields(field_list)
        
        # Build and execute search
        client = DiscoveryClient()
        params = builder.build_params(page=0, per_page=limit, sort_option=sort)
        
        click.echo(f"\n=== Advanced Search Query ===")
        click.echo(f"Query: {params.get('sps.searchQuery', 'No query terms')}")
        click.echo(f"Filters: {len([k for k in params.keys() if k.startswith('sps.') and k != 'sps.searchQuery'])}")
        
        if params.get('sps.searchQuery'):
            result = client.search(
                query=params['sps.searchQuery'],
                page=0,
                per_page=limit,
                sort_option=sort,
                filters={k: v for k, v in params.items() if k.startswith('sps.') and k not in ['sps.searchQuery', 'sps.page', 'sps.resultsPageSize', 'sps.sortByOption']}
            )
            
            click.echo(f"\n=== Search Results ===")
            click.echo(f"Found {result.total_results} total results")
            click.echo(f"Showing first {len(result.records)} results:")
            
            for i, record in enumerate(result.records, 1):
                click.echo(f"\n{i}. [{record.reference}] {record.title}")
                if record.date_from or record.date_to:
                    click.echo(f"   Dates: {record.date_from} - {record.date_to}")
                if record.description:
                    click.echo(f"   Description: {record.description[:100]}...")
        else:
            click.echo("Error: No search query generated. Please provide search terms.")
            
    except ImportError:
        click.echo("Error: Advanced search features not available. Missing dependencies.")
    except Exception as e:
        click.echo(f"Error performing advanced search: {e}")


@cli.command('browse-repositories')
@click.option('--name-filter', '-n', help='Filter repositories by name')
@click.option('--limit', '-l', type=int, default=30, help='Number of repositories to show')
@click.option('--stats', '-s', is_flag=True, help='Show repository statistics')
@click.pass_context
def browse_repositories(ctx, name_filter, limit, stats):
    """Browse and search repositories/archives (API Bible Section 3.3)"""
    try:
        from api.repository import RepositoryClient
        
        repo_client = RepositoryClient()
        
        if stats:
            statistics = repo_client.get_repository_statistics()
            click.echo(f"\n=== Repository Statistics ===")
            click.echo(f"Total repositories: {statistics.get('total_repositories', 0)}")
            click.echo(f"TNA repositories: {statistics.get('tna_repositories', 0)}")
            click.echo(f"Other repositories: {statistics.get('other_repositories', 0)}")
            return
        
        if name_filter:
            repositories = repo_client.search_repositories(name_filter)
            click.echo(f"\n=== Repositories matching '{name_filter}' ===")
        else:
            repositories = repo_client.list_repositories(limit)
            click.echo(f"\n=== First {limit} Repositories ===")
        
        for i, repo in enumerate(repositories[:limit], 1):
            name = repo.get('Name', repo.get('name', 'Unknown'))
            repo_type = repo.get('Type', repo.get('type', 'Unknown'))
            click.echo(f"{i}. {name} ({repo_type})")
            
            # Show additional info if available
            if 'Description' in repo or 'description' in repo:
                desc = repo.get('Description', repo.get('description', ''))[:100]
                if desc:
                    click.echo(f"   Description: {desc}...")
        
        if not repositories:
            click.echo("No repositories found.")
            
    except Exception as e:
        click.echo(f"Error browsing repositories: {e}")


@cli.command('browse-creators')
@click.argument('creator_type', type=click.Choice(['Person', 'Business', 'Family', 'Manor', 'Organisation']))
@click.option('--name-search', '-n', help='Search for creators by name')
@click.option('--limit', '-l', type=int, default=20, help='Number of creators to show')
@click.option('--stats', '-s', is_flag=True, help='Show creator statistics')
@click.pass_context
def browse_creators(ctx, creator_type, name_search, limit, stats):
    """Browse creators/file authorities by type (API Bible Section 3.1)"""
    try:
        from api.creator import CreatorClient
        
        creator_client = CreatorClient()
        
        if stats:
            statistics = creator_client.get_creator_statistics()
            click.echo(f"\n=== Creator Statistics ===")
            for ctype, count in statistics.get('by_type', {}).items():
                click.echo(f"{ctype}: {count}")
            click.echo(f"Total: {statistics.get('total_creators', 0)}")
            return
        
        if name_search:
            creators = creator_client.search_creators_by_name(name_search, creator_type)
            click.echo(f"\n=== {creator_type} creators matching '{name_search}' ===")
        else:
            response = creator_client.search_creators(creator_type, limit)
            creators = response.get('Creators', response.get('creators', []))
            click.echo(f"\n=== First {limit} {creator_type} creators ===")
        
        for i, creator in enumerate(creators[:limit], 1):
            name = creator.get('AuthorityName', creator.get('Name', 'Unknown'))
            epithet = creator.get('Epithet', '')
            
            click.echo(f"{i}. {name}")
            if epithet:
                click.echo(f"   {epithet}")
            
            # Show biography snippet if available
            bio = creator.get('BiographyHistory', '')
            if bio and len(bio) > 50:
                click.echo(f"   Bio: {bio[:100]}...")
        
        if not creators:
            click.echo(f"No {creator_type} creators found.")
            
    except Exception as e:
        click.echo(f"Error browsing creators: {e}")


@cli.command('cache')
@click.option('--stats', '-s', is_flag=True, help='Show cache statistics')
@click.option('--cleanup', '-c', is_flag=True, help='Clean up expired cache entries')
@click.option('--invalidate', '-i', help='Invalidate cache entries (optional pattern)')
@click.option('--clear', is_flag=True, help='Clear all cache entries')
@click.pass_context
def cache_management(ctx, stats, cleanup, invalidate, clear):
    """Manage and monitor intelligent cache system"""
    try:
        from api.intelligent_cache import get_intelligent_cache
        
        cache = get_intelligent_cache()
        
        if stats:
            statistics = cache.get_statistics()
            
            click.echo(f"\n=== Cache Performance Statistics ===")
            perf = statistics.get('performance', {})
            click.echo(f"Hit Rate: {perf.get('hit_rate_percent', 0):.1f}%")
            click.echo(f"Total Requests: {perf.get('total_requests', 0)}")
            click.echo(f"Cache Hits: {perf.get('cache_hits', 0)} (Memory: {perf.get('memory_hits', 0)}, Disk: {perf.get('disk_hits', 0)})")
            click.echo(f"Cache Misses: {perf.get('cache_misses', 0)}")
            click.echo(f"Invalidations: {perf.get('invalidations', 0)}")
            
            click.echo(f"\n=== Cache Storage ===")
            storage = statistics.get('storage', {})
            click.echo(f"Total Entries: {storage.get('total_entries', 0)}")
            click.echo(f"Memory Entries: {storage.get('memory_entries', 0)}")
            click.echo(f"Disk Size: {storage.get('disk_size_bytes', 0):,} bytes")
            click.echo(f"Memory Size: {storage.get('memory_size_bytes', 0):,} bytes")
            
            entries_by_type = storage.get('entries_by_type', {})
            if entries_by_type:
                click.echo(f"\nEntries by Type:")
                for cache_type, count in entries_by_type.items():
                    click.echo(f"  {cache_type}: {count}")
            
            click.echo(f"\n=== Configuration ===")
            config = statistics.get('configuration', {})
            click.echo(f"Static Data TTL: {config.get('static_ttl_hours', 0):.1f} hours")
            click.echo(f"Dynamic Data TTL: {config.get('dynamic_ttl_hours', 0):.1f} hours")
            click.echo(f"Record Data TTL: {config.get('record_ttl_hours', 0):.1f} hours")
            
        if cleanup:
            click.echo("Cleaning up expired cache entries...")
            cache.cleanup_expired()
            click.echo("Cache cleanup completed.")
            
        if invalidate:
            click.echo(f"Invalidating cache entries matching '{invalidate}'...")
            cache.invalidate(invalidate)
            click.echo("Cache invalidation completed.")
            
        if clear:
            click.confirm("Are you sure you want to clear ALL cache entries?", abort=True)
            cache.invalidate()  # Clear all
            click.echo("All cache entries cleared.")
            
        if not any([stats, cleanup, invalidate, clear]):
            click.echo("Use --help to see available cache management options.")
            
    except Exception as e:
        click.echo(f"Error managing cache: {e}")


@cli.command('batch-fetch')
@click.argument('record_ids', nargs=-1, required=True)
@click.option('--batch-size', '-b', type=int, default=10, help='Batch size for processing')
@click.option('--priority', '-p', type=click.Choice(['1', '2', '3']), default='1', help='Request priority (1=high, 2=medium, 3=low)')
@click.option('--timeout', '-t', type=float, default=30.0, help='Timeout for results in seconds')
@click.option('--stats', '-s', is_flag=True, help='Show batch processing statistics')
@click.pass_context
def batch_fetch(ctx, record_ids, batch_size, priority, timeout, stats):
    """Efficiently fetch multiple records using request batching"""
    try:
        from api.batch_manager import BatchRequestManager
        from api.client import DiscoveryClient
        
        client = DiscoveryClient()
        
        with BatchRequestManager(client, batch_size=batch_size) as batch_manager:
            if stats:
                # Show initial statistics
                initial_stats = batch_manager.get_statistics()
                click.echo(f"\n=== Batch Manager Statistics ===")
                click.echo(f"Batch Size: {initial_stats['batch_config']['batch_size']}")
                click.echo(f"Processing Interval: {initial_stats['batch_config']['processing_interval']}s")
                click.echo(f"Total Requests: {initial_stats['total_requests']}")
                
            if record_ids:
                click.echo(f"\n=== Batch Fetching {len(record_ids)} Records ===")
                click.echo(f"Batch Size: {batch_size}, Priority: {priority}, Timeout: {timeout}s")
                
                # Submit batch requests
                request_ids = batch_manager.batch_record_requests(
                    list(record_ids), 
                    priority=int(priority)
                )
                
                click.echo(f"Submitted {len(request_ids)} requests...")
                
                # Wait for results
                results = batch_manager.wait_for_results(request_ids, timeout=timeout)
                
                # Display results
                successful = sum(1 for r in results if r.success)
                failed = len(results) - successful
                
                click.echo(f"\n=== Batch Results ===")
                click.echo(f"Successful: {successful}")
                click.echo(f"Failed: {failed}")
                
                for i, result in enumerate(results, 1):
                    if result.success and result.data:
                        record = result.data
                        click.echo(f"\n{i}. ✅ [{record.reference}] {record.title}")
                        if record.date_from or record.date_to:
                            click.echo(f"   Dates: {record.date_from} - {record.date_to}")
                        click.echo(f"   Processing Time: {result.processing_time:.3f}s")
                    else:
                        click.echo(f"\n{i}. ❌ Error: {result.error}")
                
                # Show final statistics
                if stats:
                    final_stats = batch_manager.get_statistics()
                    click.echo(f"\n=== Final Statistics ===")
                    click.echo(f"Total Requests Processed: {final_stats['total_requests']}")
                    click.echo(f"Successful Batches: {final_stats['successful_batches']}")
                    click.echo(f"Average Batch Time: {final_stats['average_batch_time']:.3f}s")
                    click.echo(f"Requests Batched: {final_stats['requests_batched']}")
                    
                    if final_stats['requests_batched'] > 0:
                        efficiency = (final_stats['requests_batched'] / final_stats['total_requests']) * 100
                        click.echo(f"Batching Efficiency: {efficiency:.1f}%")
            
    except Exception as e:
        click.echo(f"Error in batch fetch: {e}")


@cli.command('batch-search')
@click.argument('queries', nargs=-1, required=True)
@click.option('--batch-size', '-b', type=int, default=5, help='Batch size for processing')
@click.option('--priority', '-p', type=click.Choice(['1', '2', '3']), default='2', help='Request priority')
@click.option('--limit', '-l', type=int, default=10, help='Results per search')
@click.option('--timeout', '-t', type=float, default=60.0, help='Timeout for all results')
@click.pass_context
def batch_search(ctx, queries, batch_size, priority, limit, timeout):
    """Efficiently execute multiple searches using request batching"""
    try:
        from api.batch_manager import BatchRequestManager
        from api.client import DiscoveryClient
        
        client = DiscoveryClient()
        
        with BatchRequestManager(client, batch_size=batch_size) as batch_manager:
            click.echo(f"\n=== Batch Searching {len(queries)} Queries ===")
            
            request_ids = []
            
            # Submit search requests
            for query in queries:
                request_id = batch_manager.add_search_request(
                    query=query,
                    params={'sps.resultsPageSize': limit},
                    priority=int(priority)
                )
                request_ids.append(request_id)
            
            click.echo(f"Submitted {len(request_ids)} search requests...")
            
            # Wait for results
            results = batch_manager.wait_for_results(request_ids, timeout=timeout)
            
            # Display results
            click.echo(f"\n=== Search Results ===")
            
            for i, (query, result) in enumerate(zip(queries, results), 1):
                click.echo(f"\n{i}. Query: '{query}'")
                
                if result.success and result.data:
                    search_result = result.data
                    click.echo(f"   Results: {search_result.total_results} total, showing {len(search_result.records)}")
                    click.echo(f"   Processing Time: {result.processing_time:.3f}s")
                    
                    for j, record in enumerate(search_result.records[:3], 1):  # Show first 3
                        click.echo(f"   {j}. [{record.reference}] {record.title}")
                    
                    if len(search_result.records) > 3:
                        click.echo(f"   ... and {len(search_result.records) - 3} more")
                else:
                    click.echo(f"   ❌ Error: {result.error}")
            
            # Show statistics
            stats = batch_manager.get_statistics()
            click.echo(f"\n=== Batch Statistics ===")
            click.echo(f"Successful Batches: {stats['successful_batches']}")
            click.echo(f"Average Batch Time: {stats['average_batch_time']:.3f}s")
            
    except Exception as e:
        click.echo(f"Error in batch search: {e}")


@cli.command('health')
@click.option('--monitor', '-m', is_flag=True, help='Start health monitoring')
@click.option('--status', '-s', is_flag=True, help='Show current health status')
@click.option('--history', '-h', help='Show endpoint history (format: endpoint:hours)')
@click.option('--errors', '-e', type=int, help='Show error analysis for last N hours')
@click.option('--check', '-c', help='Perform single health check on endpoint')
@click.option('--interval', '-i', type=int, default=60, help='Monitoring interval in seconds')
@click.pass_context
def health_monitoring(ctx, monitor, status, history, errors, check, interval):
    """API health monitoring and diagnostics"""
    try:
        from api.health_monitor import APIHealthMonitor, setup_console_alerts
        from api.client import DiscoveryClient
        
        client = DiscoveryClient()
        
        if monitor:
            click.echo(f"🏥 Starting API Health Monitor (interval={interval}s)")
            click.echo("Press Ctrl+C to stop monitoring\n")
            
            # Setup console alerts
            alert_handler = setup_console_alerts()
            
            with APIHealthMonitor(client, check_interval=interval) as monitor:
                monitor.add_alert_callback(alert_handler)
                
                try:
                    while True:
                        time.sleep(5)  # Check every 5 seconds for display updates
                        
                        # Show current status
                        summary = monitor.get_health_summary()
                        click.clear()
                        click.echo(f"🏥 API Health Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                        click.echo(f"Overall Status: {summary['overall_status']} | Success Rate: {summary['overall_success_rate']:.1f}%")
                        click.echo(f"Avg Response Time: {summary['average_response_time']:.3f}s | Checks/Hour: {summary['total_checks_last_hour']}")
                        click.echo()
                        
                        for endpoint, stats in summary['endpoints'].items():
                            status_icon = "✅" if stats['status'] == "HEALTHY" else "⚠️" if stats['status'] == "WARNING" else "❌"
                            click.echo(f"{status_icon} {endpoint}")
                            click.echo(f"   Status: {stats['status']} | Success: {stats['success_rate']:.1f}% | Response: {stats['average_response_time']:.3f}s")
                            if stats['consecutive_failures'] > 0:
                                click.echo(f"   ⚠️ Consecutive Failures: {stats['consecutive_failures']}")
                        
                        click.echo("\nPress Ctrl+C to stop monitoring...")
                        
                except KeyboardInterrupt:
                    click.echo("\n\n✅ Health monitoring stopped.")
        
        elif status:
            monitor = APIHealthMonitor(client)
            
            # Perform quick health checks
            click.echo("🏥 Performing Health Checks...\n")
            
            endpoints_to_check = [
                ('search/v1/records', {'sps.searchQuery': 'test', 'sps.resultsPageSize': 1}),
                ('records/v1/details/C9134', {}),
                ('repository/v1/collection', {'limit': 1})
            ]
            
            for endpoint, params in endpoints_to_check:
                click.echo(f"Checking {endpoint}...", nl=False)
                health_check = monitor.perform_health_check(endpoint, params)
                
                if health_check.success:
                    click.echo(f" ✅ OK ({health_check.response_time:.3f}s)")
                else:
                    click.echo(f" ❌ FAILED ({health_check.error_type}: {health_check.error_message})")
            
            # Show summary
            summary = monitor.get_health_summary()
            click.echo(f"\n=== Health Summary ===")
            click.echo(f"Overall Status: {summary['overall_status']}")
            click.echo(f"Success Rate: {summary['overall_success_rate']:.1f}%")
            click.echo(f"Average Response Time: {summary['average_response_time']:.3f}s")
        
        elif history:
            try:
                endpoint, hours_str = history.split(':')
                hours = int(hours_str)
            except ValueError:
                click.echo("Error: History format should be 'endpoint:hours' (e.g., 'search/v1/records:24')")
                return
            
            monitor = APIHealthMonitor(client)
            history_data = monitor.get_endpoint_history(endpoint, hours)
            
            if not history_data:
                click.echo(f"No history data found for {endpoint} in the last {hours} hours")
                return
            
            click.echo(f"\n=== {endpoint} History (Last {hours} hours) ===")
            click.echo(f"Total Checks: {len(history_data)}")
            
            successful = sum(1 for check in history_data if check['success'])
            click.echo(f"Success Rate: {(successful/len(history_data)*100):.1f}%")
            
            response_times = [check['response_time'] for check in history_data if check['success']]
            if response_times:
                click.echo(f"Avg Response Time: {statistics.mean(response_times):.3f}s")
            
            # Show recent failures
            failures = [check for check in history_data if not check['success']]
            if failures:
                click.echo(f"\nRecent Failures ({len(failures)}):")
                for failure in failures[-5:]:  # Last 5 failures
                    timestamp = datetime.fromtimestamp(failure['timestamp']).strftime('%H:%M:%S')
                    click.echo(f"  {timestamp}: {failure['error_type']} - {failure['error_message']}")
        
        elif errors is not None:
            monitor = APIHealthMonitor(client)
            error_analysis = monitor.get_error_analysis(errors)
            
            click.echo(f"\n=== Error Analysis (Last {errors} hours) ===")
            click.echo(f"Total Errors: {error_analysis['total_errors']}")
            click.echo(f"Error Rate: {error_analysis['error_rate']:.1f}%")
            
            if error_analysis['error_types']:
                click.echo("\nError Types:")
                for error_type, count in error_analysis['error_types'].items():
                    click.echo(f"  {error_type}: {count}")
            
            if error_analysis['error_endpoints']:
                click.echo("\nErrors by Endpoint:")
                for endpoint, count in error_analysis['error_endpoints'].items():
                    click.echo(f"  {endpoint}: {count}")
            
            if error_analysis['most_common_error']:
                click.echo(f"\nMost Common Error: {error_analysis['most_common_error']}")
        
        elif check:
            monitor = APIHealthMonitor(client)
            click.echo(f"Performing health check on {check}...")
            
            health_check = monitor.perform_health_check(check, {})
            
            if health_check.success:
                click.echo(f"✅ SUCCESS")
                click.echo(f"Response Time: {health_check.response_time:.3f}s")
                click.echo(f"Status Code: {health_check.status_code}")
            else:
                click.echo(f"❌ FAILED")
                click.echo(f"Error Type: {health_check.error_type}")
                click.echo(f"Error Message: {health_check.error_message}")
                click.echo(f"Response Time: {health_check.response_time:.3f}s")
        
        else:
            click.echo("Use --help to see available health monitoring options.")
            
    except Exception as e:
        click.echo(f"Error in health monitoring: {e}")


@cli.command('stream-fetch')
@click.argument('query')
@click.option('--max-records', '-m', type=int, default=10000, help='Maximum records to fetch')
@click.option('--chunk-size', '-c', type=int, default=100, help='Records per chunk')
@click.option('--memory-limit', type=int, default=500, help='Memory limit in MB')
@click.option('--output', '-o', help='Output file path (optional)')
@click.pass_context
def stream_fetch(ctx, query, max_records, chunk_size, memory_limit, output):
    """Fetch large datasets using memory-efficient streaming"""
    try:
        from utils.streaming import StreamingRecordProcessor, StreamingConfig
        from api.client import DiscoveryClient
        
        click.echo(f"🔄 Starting streaming fetch for '{query}'")
        click.echo(f"📊 Max records: {max_records}, Chunk size: {chunk_size}, Memory limit: {memory_limit}MB")
        
        # Initialize components
        api_client = DiscoveryClient()
        config = StreamingConfig(
            chunk_size=chunk_size,
            memory_limit_mb=memory_limit,
            progress_callback=lambda current, total: click.echo(f"Progress: {current}/{total} records")
        )
        processor = StreamingRecordProcessor(config)
        
        # Store records in database
        from storage.database import DatabaseManager
        db = DatabaseManager()
        
        total_stored = 0
        
        for chunk in processor.stream_records_from_api(api_client, query, max_records):
            stored_count = db.store_records(chunk)
            total_stored += stored_count
            
            click.echo(f"Stored chunk: {stored_count} records (total: {total_stored})")
            
            # Memory info
            memory_info = processor.memory_monitor.check_memory()
            if memory_info['usage_percent'] > 70:
                click.echo(f"⚠️  Memory usage: {memory_info['usage_percent']:.1f}%")
        
        # Final statistics
        stats = processor.get_statistics()
        click.echo(f"\n✅ Streaming fetch complete!")
        click.echo(f"Total records: {total_stored}")
        click.echo(f"Processing time: {stats['total_time']:.1f}s")
        click.echo(f"Peak memory: {stats['peak_memory_mb']:.1f}MB")
        click.echo(f"GC runs: {stats['gc_runs']}")
        
    except Exception as e:
        click.echo(f"Error in streaming fetch: {e}")


@cli.command('stream-export')
@click.option('--query', '-q', help='SQL WHERE clause to filter records')
@click.option('--format', '-f', type=click.Choice(['jsonl', 'csv', 'xml']), default='jsonl', help='Export format')
@click.option('--chunk-size', '-c', type=int, default=1000, help='Records per chunk')
@click.option('--memory-limit', type=int, default=500, help='Memory limit in MB')
@click.pass_context
def stream_export(ctx, query, format, chunk_size, memory_limit):
    """Export large datasets using memory-efficient streaming"""
    try:
        from utils.streaming import export_records_streaming
        
        click.echo(f"📤 Starting streaming export")
        if query:
            click.echo(f"Filter: {query}")
        click.echo(f"Format: {format}, Chunk size: {chunk_size}")
        
        output_path = export_records_streaming(
            query=query,
            output_format=format,
            chunk_size=chunk_size
        )
        
        click.echo(f"✅ Export complete: {output_path}")
        
        # Show file size
        from pathlib import Path
        if Path(output_path).exists():
            size_mb = Path(output_path).stat().st_size / 1024 / 1024
            click.echo(f"File size: {size_mb:.2f} MB")
        
    except Exception as e:
        click.echo(f"Error in streaming export: {e}")


@cli.command('stream-analyze')
@click.option('--analysis', '-a', type=click.Choice(['word_frequency', 'date_distribution', 'archive_stats']), 
              default='archive_stats', help='Type of analysis to perform')
@click.option('--query', '-q', help='SQL WHERE clause to filter records')
@click.option('--chunk-size', '-c', type=int, default=500, help='Records per chunk')
@click.pass_context
def stream_analyze(ctx, analysis, query, chunk_size):
    """Perform analysis on large datasets using streaming"""
    try:
        from utils.streaming import analyze_records_streaming
        from collections import defaultdict
        import json
        
        click.echo(f"📊 Starting streaming analysis: {analysis}")
        if query:
            click.echo(f"Filter: {query}")
        
        # Define analysis functions
        def archive_stats_analysis(records):
            """Analyze archive distribution"""
            stats = defaultdict(int)
            for record in records:
                if record.archive:
                    stats[record.archive] += 1
            return dict(stats)
        
        def date_distribution_analysis(records):
            """Analyze date distribution by decade"""
            decades = defaultdict(int)
            for record in records:
                if record.date_from:
                    try:
                        year = int(record.date_from.split('/')[2]) if '/' in record.date_from else int(record.date_from[:4])
                        decade = (year // 10) * 10
                        decades[f"{decade}s"] += 1
                    except (ValueError, IndexError):
                        continue
            return dict(decades)
        
        def word_frequency_analysis(records):
            """Analyze word frequency in titles"""
            words = defaultdict(int)
            for record in records:
                if record.title:
                    # Simple word extraction
                    title_words = record.title.lower().split()
                    for word in title_words:
                        if len(word) > 3:  # Skip short words
                            words[word] += 1
            # Return top 50 words
            return dict(sorted(words.items(), key=lambda x: x[1], reverse=True)[:50])
        
        analysis_funcs = {
            'archive_stats': archive_stats_analysis,
            'date_distribution': date_distribution_analysis,
            'word_frequency': word_frequency_analysis
        }
        
        results = analyze_records_streaming(
            analysis_funcs[analysis],
            query=query,
            chunk_size=chunk_size
        )
        
        click.echo(f"\n📈 Analysis Results ({analysis}):")
        click.echo(json.dumps(results, indent=2))
        
    except Exception as e:
        click.echo(f"Error in streaming analysis: {e}")


@cli.command('performance')
@click.option('--test-type', '-t', type=click.Choice(['quick', 'comprehensive', 'load']), 
              default='quick', help='Type of performance test')
@click.option('--concurrent-users', '-u', type=int, default=10, help='Concurrent users for load test')
@click.option('--operations', '-o', type=int, default=50, help='Operations per user for load test')
@click.option('--save-report', '-s', help='Save detailed report to file')
@click.option('--baseline', '-b', help='Compare against baseline file')
@click.pass_context
def performance_test(ctx, test_type, concurrent_users, operations, save_report, baseline):
    """Run performance tests and benchmarking"""
    try:
        from tests.performance_tests import PerformanceTester, LoadTestConfig, run_quick_performance_test, run_load_test
        
        click.echo(f"⚡ Starting {test_type} performance test...")
        
        if test_type == 'quick':
            results = run_quick_performance_test()
        elif test_type == 'comprehensive':
            tester = PerformanceTester()
            results = tester.run_all_tests()
        elif test_type == 'load':
            click.echo(f"Load test: {concurrent_users} users, {operations} operations each")
            result = run_load_test(concurrent_users, operations)
            results = [result]
        
        # Display results
        click.echo(f"\n📊 Performance Test Results ({test_type})")
        click.echo("=" * 80)
        
        for result in results:
            status = "✅" if len(result.errors) == 0 else "⚠️"
            click.echo(f"{status} {result.test_name}:")
            click.echo(f"   Throughput: {result.operations_per_second:.1f} ops/sec")
            click.echo(f"   Duration: {result.duration:.2f}s")
            click.echo(f"   Peak Memory: {result.peak_memory_mb:.1f} MB")
            
            if result.errors:
                click.echo(f"   ❌ Errors: {len(result.errors)}")
                for error in result.errors[:2]:  # Show first 2 errors
                    click.echo(f"      - {error}")
            
            if result.custom_metrics:
                for key, value in result.custom_metrics.items():
                    click.echo(f"   {key}: {value}")
            click.echo()
        
        # Save detailed report
        if save_report:
            tester = PerformanceTester()
            report = tester.generate_report(results)
            with open(save_report, 'w') as f:
                f.write(report)
            click.echo(f"📄 Detailed report saved to: {save_report}")
        
        # Baseline comparison
        if baseline:
            tester = PerformanceTester()
            tester.test_results = results
            comparison = tester.benchmark_against_baseline(baseline)
            
            if 'baseline_created' in comparison:
                click.echo(f"📊 New baseline created: {comparison['baseline_created']}")
            else:
                click.echo("\n📈 Performance Comparison vs Baseline:")
                for test_name, metrics in comparison.items():
                    improvement = metrics['improvement_percent']
                    status = "📈" if improvement > 5 else "📉" if improvement < -5 else "➡️"
                    click.echo(f"{status} {test_name}: {improvement:+.1f}% "
                             f"({metrics['current_ops_per_sec']:.1f} vs {metrics['baseline_ops_per_sec']:.1f} ops/sec)")
        
        # Overall summary
        total_ops = sum(r.operations_count for r in results)
        total_time = sum(r.duration for r in results)
        total_errors = sum(len(r.errors) for r in results)
        
        click.echo(f"\n🎯 Overall Summary:")
        click.echo(f"Total Operations: {total_ops}")
        click.echo(f"Total Time: {total_time:.1f}s")
        click.echo(f"Total Errors: {total_errors}")
        click.echo(f"Success Rate: {((total_ops - total_errors) / max(total_ops, 1) * 100):.1f}%")
        
    except Exception as e:
        click.echo(f"Error in performance testing: {e}")


@cli.command('backup')
@click.option('--action', '-a', type=click.Choice(['create', 'list', 'restore', 'cleanup', 'schedule']), 
              required=True, help='Backup action to perform')
@click.option('--backup-id', '-i', help='Backup ID for restore action')
@click.option('--backup-type', '-t', type=click.Choice(['full', 'incremental']), 
              default='full', help='Type of backup to create')
@click.option('--restore-path', '-p', default='data_restored', help='Path to restore backup to')
@click.option('--schedule', '-s', type=click.Choice(['hourly', 'daily', 'weekly']), 
              default='daily', help='Backup schedule interval')
@click.pass_context
def backup_system(ctx, action, backup_id, backup_type, restore_path, schedule):
    """Automated backup and recovery system"""
    try:
        from utils.backup_recovery import BackupManager, BackupConfig
        
        config = BackupConfig(
            retention_days=30,
            compression=True,
            verify_backup=True,
            schedule_interval=schedule
        )
        manager = BackupManager(config)
        
        if action == 'create':
            click.echo(f"💾 Creating {backup_type} backup...")
            
            if backup_type == 'full':
                backup_id = manager.create_full_backup(f"Manual backup {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            else:
                backup_id = manager.create_incremental_backup()
            
            click.echo(f"✅ Backup created: {backup_id}")
            
            # Show backup info
            metadata = manager.metadata[backup_id]
            click.echo(f"File: {metadata['file_path']}")
            click.echo(f"Size: {metadata['file_size'] / 1024 / 1024:.1f} MB")
            click.echo(f"Records: {metadata['record_count']}")
            click.echo(f"Verified: {'✅' if metadata['verified'] else '❌'}")
        
        elif action == 'list':
            backups = manager.list_backups()
            
            if not backups:
                click.echo("No backups found.")
                return
            
            click.echo("📋 Available Backups:")
            click.echo("-" * 80)
            click.echo(f"{'Backup ID':<25} {'Type':<12} {'Size (MB)':<10} {'Age (days)':<12} {'Records':<10}")
            click.echo("-" * 80)
            
            for backup in backups:
                click.echo(
                    f"{backup['backup_id']:<25} "
                    f"{backup['backup_type']:<12} "
                    f"{backup['file_size'] / 1024 / 1024:<10.1f} "
                    f"{backup['age_days']:<12} "
                    f"{backup['record_count']:<10}"
                )
        
        elif action == 'restore':
            if not backup_id:
                click.echo("❌ Backup ID required for restore action")
                return
            
            click.echo(f"🔄 Restoring backup: {backup_id}")
            click.echo(f"Restore path: {restore_path}")
            
            click.confirm("This will overwrite existing data. Continue?", abort=True)
            
            success = manager.restore_backup(backup_id, restore_path)
            
            if success:
                click.echo(f"✅ Backup restored successfully to {restore_path}")
            else:
                click.echo("❌ Backup restore failed")
        
        elif action == 'cleanup':
            click.echo("🧹 Cleaning up old backups...")
            cleaned = manager.cleanup_old_backups()
            click.echo(f"✅ Cleaned up {cleaned} old backups")
        
        elif action == 'schedule':
            click.echo(f"⏰ Setting up automated backups ({schedule})")
            manager.start_scheduled_backups()
            click.echo("✅ Automated backup scheduling started")
            click.echo("Use Ctrl+C to stop the scheduler")
            
            try:
                # Keep the process running
                import time
                while True:
                    time.sleep(60)
                    
                    # Show statistics periodically
                    stats = manager.get_backup_statistics()
                    click.echo(f"📊 Total backups: {stats['total_backups']}, "
                             f"Total size: {stats['total_size_mb']:.1f} MB")
            
            except KeyboardInterrupt:
                manager.stop_scheduled_backups()
                click.echo("\n✅ Backup scheduling stopped")
        
        # Show backup statistics
        if action in ['create', 'list', 'cleanup']:
            stats = manager.get_backup_statistics()
            click.echo(f"\n📊 Backup Statistics:")
            click.echo(f"Total Backups: {stats['total_backups']}")
            click.echo(f"Full Backups: {stats['full_backups']}")
            click.echo(f"Incremental Backups: {stats['incremental_backups']}")
            click.echo(f"Total Size: {stats['total_size_mb']:.1f} MB")
            if stats['newest_backup']:
                click.echo(f"Latest Backup: {stats['newest_backup']}")
    
    except Exception as e:
        click.echo(f"Error in backup system: {e}")


@cli.command()
@click.option('--series', '-s', help='Enrich specific series (e.g., "CO 1")')
@click.option('--batch-size', '-b', default=10, help='Number of records to process per batch')
@click.option('--limit', '-l', default=100, help='Maximum number of records to enrich')
@click.option('--dry-run', is_flag=True, help='Show what would be enriched without making changes')
@click.pass_context
def enrich_metadata(ctx, series, batch_size, limit, dry_run):
    """Enrich existing records with detailed metadata from TNA API"""
    
    try:
        click.echo("🔍 METADATA ENRICHMENT SYSTEM")
        click.echo("=" * 60)
        
        # Initialize components
        client = DiscoveryClient()
        db_manager = DatabaseManager()
        
        # Get records to enrich
        if series:
            click.echo(f"📋 Enriching records from series: {series}")
            # Get records from specific series
            with click.progressbar(length=1, label='Querying database') as bar:
                records = db_manager.search_records(f'reference:"{series}"', limit=limit)
                bar.update(1)
        else:
            click.echo("📋 Enriching all records (limited by --limit)")
            # Get records with missing metadata using direct SQL query
            with click.progressbar(length=1, label='Querying database') as bar:
                records = db_manager.get_records_with_missing_metadata(limit)
                bar.update(1)
        
        if not records:
            click.echo("❌ No records found to enrich")
            return
        
        click.echo(f"📊 Found {len(records)} records to enrich")
        
        if dry_run:
            click.echo("🔍 DRY RUN - No changes will be made")
            click.echo("Records that would be enriched:")
            for record in records[:5]:  # Show first 5
                click.echo(f"  • {record.reference}: {record.title}")
            if len(records) > 5:
                click.echo(f"  ... and {len(records) - 5} more")
            return
        
        # Confirm action
        click.confirm(f"Enrich {len(records)} records with detailed metadata?", abort=True)
        
        # Extract record IDs
        record_ids = [record.id for record in records]
        
        # Enrich metadata in batches
        click.echo(f"🚀 Starting metadata enrichment (batch size: {batch_size})")
        
        with click.progressbar(length=len(record_ids), label='Enriching metadata') as bar:
            enriched_records = client.batch_enrich_metadata(record_ids, batch_size)
            bar.update(len(record_ids))
        
        if enriched_records:
            # Update database with enriched records
            click.echo(f"💾 Updating database with enriched metadata...")
            
            with click.progressbar(length=len(enriched_records), label='Updating database') as bar:
                updated_count = db_manager.batch_update_metadata(enriched_records)
                bar.update(len(enriched_records))
            
            click.echo(f"✅ Successfully enriched {updated_count} records!")
            
            # Show sample of enriched data
            if enriched_records:
                sample = enriched_records[0]
                click.echo(f"\n📋 Sample enriched record:")
                click.echo(f"  Reference: {sample.reference}")
                click.echo(f"  Scope Content: {sample.scope_content[:100] if sample.scope_content else 'None'}...")
                click.echo(f"  Catalogue ID: {sample.catalogue_id}")
                click.echo(f"  Covering Dates: {sample.covering_dates}")
                click.echo(f"  Legal Status: {sample.legal_status}")
        else:
            click.echo("❌ No records were successfully enriched")
    
    except Exception as e:
        click.echo(f"❌ Error during metadata enrichment: {e}")
        if ctx.obj.get('debug'):
            raise


if __name__ == '__main__':
    main()
