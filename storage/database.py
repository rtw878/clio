"""
Database management for National Archives Discovery data
SQLite-based storage with efficient indexing and search capabilities
"""

import sqlite3
import logging
import os
from typing import List, Dict, Optional, Iterator, Tuple, Any
from datetime import datetime, timedelta
import json
from pathlib import Path

from api.models import Record, SearchResult

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages local SQLite database for storing Discovery records
    
    Provides efficient storage, retrieval, and search capabilities
    while respecting The National Archives' terms of service.
    """
    
    def __init__(self, db_path: str = "./data/discovery.db"):
        """
        Initialize database manager
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        logger.info(f"Database initialized at {db_path}")

    def _migrate_schema(self, conn: sqlite3.Connection):
        """Migrate existing database schema to include new hierarchical fields"""
        try:
            # Check if new columns exist
            cursor = conn.execute("PRAGMA table_info(records)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Add missing columns
            if 'parent_id' not in columns:
                logger.info("Adding parent_id column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN parent_id TEXT")
                
            if 'level' not in columns:
                logger.info("Adding level column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN level TEXT")
                
            if 'child_count' not in columns:
                logger.info("Adding child_count column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN child_count INTEGER")
                
            if 'provenance' not in columns:
                logger.info("Adding provenance column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN provenance TEXT")
            
            # Add API Bible Section 4.1 additional fields
            if 'catalogue_level' not in columns:
                logger.info("Adding catalogue_level column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN catalogue_level INTEGER")
                
            if 'closure_code' not in columns:
                logger.info("Adding closure_code column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN closure_code TEXT")
                
            if 'digitised' not in columns:
                logger.info("Adding digitised column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN digitised BOOLEAN")
                
            if 'hierarchy' not in columns:
                logger.info("Adding hierarchy column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN hierarchy TEXT")
                
            if 'covering_from_date' not in columns:
                logger.info("Adding covering_from_date column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN covering_from_date INTEGER")
                
            if 'covering_to_date' not in columns:
                logger.info("Adding covering_to_date column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN covering_to_date INTEGER")
            
            # Add enhanced TNA API metadata fields
            if 'catalogue_id' not in columns:
                logger.info("Adding catalogue_id column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN catalogue_id INTEGER")
                
            if 'covering_dates' not in columns:
                logger.info("Adding covering_dates column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN covering_dates TEXT")
                
            if 'is_parent' not in columns:
                logger.info("Adding is_parent column to records table")
                conn.execute("ALTER TABLE records ADD COLUMN is_parent BOOLEAN")
                
            conn.commit()
                
        except sqlite3.Error as e:
            logger.warning(f"Schema migration warning: {e}")

    def _init_database(self):
        """Create database tables and indexes"""
        
        with sqlite3.connect(self.db_path) as conn:
            # Migrate existing schema first
            self._migrate_schema(conn)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            
            # Main records table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    date_from TEXT,
                    date_to TEXT,
                    reference TEXT,
                    archive TEXT,
                    collection TEXT,
                    subjects TEXT,
                    creators TEXT,
                    places TEXT,
                    catalogue_source TEXT,
                    access_conditions TEXT,
                    closure_status TEXT,
                    legal_status TEXT,
                    held_by TEXT,
                    former_reference TEXT,
                    note TEXT,
                    arrangement TEXT,
                    dimensions TEXT,
                    administrator_background TEXT,
                    custodial_history TEXT,
                    acquisition_information TEXT,
                    appraisal_information TEXT,
                    accruals TEXT,
                    related_material TEXT,
                    publication_note TEXT,
                    copies_information TEXT,
                    originals_held_elsewhere TEXT,
                    unpublished_finding_aids TEXT,
                    publications TEXT,
                    map_designation TEXT,
                    physical_description TEXT,
                    immediate_source TEXT,
                    scope_content TEXT,
                    language TEXT,
                    script TEXT,
                    web_links TEXT,
                    digital_files TEXT,
                    
                    -- Hierarchical structure fields (Workflow.md requirements)
                    parent_id TEXT,
                    level TEXT,
                    child_count INTEGER,
                    
                    -- Provenance tracking (essential for scholarly integrity)
                    provenance TEXT,
                    
                    -- API Bible Section 4.1 additional fields
                    catalogue_level INTEGER,
                    closure_code TEXT,
                    digitised BOOLEAN,
                    hierarchy TEXT,
                    covering_from_date INTEGER,
                    covering_to_date INTEGER,
                    
                    -- Enhanced TNA API metadata fields
                    catalogue_id INTEGER,
                    covering_dates TEXT,
                    is_parent BOOLEAN,
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Create foreign key relationship for hierarchy
                    FOREIGN KEY (parent_id) REFERENCES records(id)
                )
            """)
            
            # Search queries cache table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    query_hash TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    results_json TEXT NOT NULL,
                    total_results INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            
            # Collections table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    record_count INTEGER,
                    date_range TEXT,
                    archive TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Request log for API compliance tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint TEXT NOT NULL,
                    query TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    response_status INTEGER,
                    records_retrieved INTEGER DEFAULT 0
                )
            """)
            
            # Crawl queue for hierarchical traversal (Workflow.md requirement)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crawl_queue (
                    url TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    status TEXT DEFAULT 'QUEUED',
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    retries INTEGER DEFAULT 0,
                    error_message TEXT,
                    parent_id TEXT,
                    expected_level TEXT,
                    
                    CHECK (status IN ('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED'))
                )
            """)
            
            # Create indexes for efficient searching
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_records_title ON records(title)",
                "CREATE INDEX IF NOT EXISTS idx_records_reference ON records(reference)",
                "CREATE INDEX IF NOT EXISTS idx_records_collection ON records(collection)",
                "CREATE INDEX IF NOT EXISTS idx_records_archive ON records(archive)",
                "CREATE INDEX IF NOT EXISTS idx_records_date_from ON records(date_from)",
                "CREATE INDEX IF NOT EXISTS idx_records_subjects ON records(subjects)",
                "CREATE INDEX IF NOT EXISTS idx_records_creators ON records(creators)",
                "CREATE INDEX IF NOT EXISTS idx_records_places ON records(places)",
                "CREATE INDEX IF NOT EXISTS idx_search_cache_query ON search_cache(query)",
                "CREATE INDEX IF NOT EXISTS idx_api_requests_timestamp ON api_requests(timestamp)",
                
                # Hierarchical structure indexes (critical for traversal performance)
                "CREATE INDEX IF NOT EXISTS idx_records_parent_id ON records(parent_id)",
                "CREATE INDEX IF NOT EXISTS idx_records_level ON records(level)",
                "CREATE INDEX IF NOT EXISTS idx_crawl_queue_status ON crawl_queue(status)",
                "CREATE INDEX IF NOT EXISTS idx_crawl_queue_parent_id ON crawl_queue(parent_id)",
                
                # Full-text search index
                """CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
                    id, title, description, reference, subjects, creators, places, 
                    scope_content, note, content='records', content_rowid='rowid'
                )""",
                
                # Triggers to keep FTS table in sync
                """CREATE TRIGGER IF NOT EXISTS records_fts_insert AFTER INSERT ON records BEGIN
                    INSERT INTO records_fts(rowid, id, title, description, reference, subjects, creators, places, scope_content, note)
                    VALUES (new.rowid, new.id, new.title, new.description, new.reference, new.subjects, new.creators, new.places, new.scope_content, new.note);
                END""",
                
                """CREATE TRIGGER IF NOT EXISTS records_fts_delete AFTER DELETE ON records BEGIN
                    DELETE FROM records_fts WHERE rowid = old.rowid;
                END""",
                
                """CREATE TRIGGER IF NOT EXISTS records_fts_update AFTER UPDATE ON records BEGIN
                    DELETE FROM records_fts WHERE rowid = old.rowid;
                    INSERT INTO records_fts(rowid, id, title, description, reference, subjects, creators, places, scope_content, note)
                    VALUES (new.rowid, new.id, new.title, new.description, new.reference, new.subjects, new.creators, new.places, new.scope_content, new.note);
                END"""
            ]
            
            for index in indexes:
                try:
                    conn.execute(index)
                except sqlite3.Error as e:
                    logger.warning(f"Failed to create index: {e}")
            
            conn.commit()

    def store_record(self, record: Record) -> bool:
        """
        Store a single record in the database
        
        Args:
            record: Record object to store
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                record_dict = record.to_dict()
                record_dict['updated_at'] = datetime.now().isoformat()
                
                # Use INSERT OR REPLACE for upsert behavior
                placeholders = ', '.join(['?' for _ in record_dict])
                columns = ', '.join(record_dict.keys())
                
                conn.execute(f"""
                    INSERT OR REPLACE INTO records ({columns})
                    VALUES ({placeholders})
                """, list(record_dict.values()))
                
                conn.commit()
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Failed to store record {record.id}: {e}")
            return False

    def store_records(self, records: List[Record]) -> int:
        """
        Store multiple records in the database
        
        Args:
            records: List of Record objects to store
            
        Returns:
            Number of records successfully stored
        """
        if not records:
            return 0
            
        stored_count = 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Convert records to dictionaries and ensure SQLite compatibility
                record_data = []
                for record in records:
                    record_dict = record.to_dict()
                    
                    # Ensure all values are SQLite-compatible
                    for key, value in record_dict.items():
                        if isinstance(value, list):
                            # Convert lists to pipe-separated strings
                            record_dict[key] = '|'.join(str(item) for item in value) if value else ''
                        elif isinstance(value, dict):
                            # Convert dictionaries to JSON strings
                            import json
                            record_dict[key] = json.dumps(value, ensure_ascii=False) if value else ''
                        elif value is None:
                            # Convert None to empty string
                            record_dict[key] = ''
                        elif not isinstance(value, (str, int, float, bool)):
                            # Convert any other types to string
                            record_dict[key] = str(value)
                    
                    record_data.append(record_dict)
                
                # Get column names from first record
                columns = list(record_data[0].keys())
                placeholders = ', '.join(['?' for _ in columns])
                columns_str = ', '.join(columns)
                
                # Batch insert
                values_list = [list(rd.values()) for rd in record_data]
                
                conn.executemany(f"""
                    INSERT OR REPLACE INTO records ({columns_str})
                    VALUES ({placeholders})
                """, values_list)
                
                stored_count = len(records)
                conn.commit()
                
                logger.info(f"Stored {stored_count} records in database")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to store records batch: {e}")
        
        return stored_count

    def get_records_with_missing_metadata(self, limit: int = 100) -> List[Record]:
        """
        Get records with missing critical metadata for enrichment
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of Record objects with missing metadata
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Find records with missing critical metadata
                query = """
                    SELECT * FROM records 
                    WHERE (scope_content IS NULL OR scope_content = '') 
                       OR (administrator_background IS NULL OR administrator_background = '')
                       OR (catalogue_id IS NULL)
                       OR (covering_dates IS NULL OR covering_dates = '')
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                
                cursor = conn.execute(query, (limit,))
                rows = cursor.fetchall()
                
                return [self._row_to_record(row) for row in rows]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get records with missing metadata: {e}")
            return []

    def update_record_metadata(self, record: Record) -> bool:
        """
        Update an existing record with enriched metadata
        
        Args:
            record: Record object with enriched metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as db:
                record_dict = record.to_dict()
                record_dict['updated_at'] = datetime.now().isoformat()
                
                # Convert list fields to strings for SQLite compatibility
                for key, value in record_dict.items():
                    if isinstance(value, list):
                        record_dict[key] = '|'.join(str(item) for item in value) if value else ''
                    elif value is None:
                        record_dict[key] = ''
                
                # Build dynamic UPDATE statement
                columns = list(record_dict.keys())
                set_clause = ', '.join([f"{col} = ?" for col in columns])
                
                # Prepare values for UPDATE
                values = list(record_dict.values()) + [record.id]  # Add id for WHERE clause
                
                query = f"""
                    UPDATE records 
                    SET {set_clause}
                    WHERE id = ?
                """
                
                cursor = db.execute(query, values)
                db.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"Updated metadata for record {record.id}")
                    return True
                else:
                    logger.warning(f"No record found to update: {record.id}")
                    return False
                    
        except sqlite3.Error as e:
            logger.error(f"Failed to update record metadata {record.id}: {e}")
            return False

    def batch_update_metadata(self, records: List[Record]) -> int:
        """
        Update multiple records with enriched metadata
        
        Args:
            records: List of Record objects with enriched metadata
            
        Returns:
            Number of records successfully updated
        """
        if not records:
            return 0
        
        updated_count = 0
        
        for record in records:
            if self.update_record_metadata(record):
                updated_count += 1
        
        logger.info(f"Updated metadata for {updated_count} out of {len(records)} records")
        return updated_count

    def get_record(self, record_id: str) -> Optional[Record]:
        """
        Retrieve a record by ID
        
        Args:
            record_id: Record identifier
            
        Returns:
            Record object or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM records WHERE id = ?", (record_id,)
                )
                row = cursor.fetchone()
                
                if row:
                    return self._row_to_record(row)
                
        except sqlite3.Error as e:
            logger.error(f"Failed to retrieve record {record_id}: {e}")
        
        return None

    def search_records(self, 
                      query: str,
                      limit: int = 100,
                      offset: int = 0,
                      filters: Optional[Dict] = None) -> List[Record]:
        """
        Search records using full-text search
        
        Args:
            query: Search query
            limit: Maximum results to return
            offset: Number of results to skip
            filters: Additional filters (collection, archive, etc.)
            
        Returns:
            List of matching Record objects
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Build search query
                if query.strip():
                    # Use full-text search
                    sql = """
                        SELECT r.* FROM records r
                        JOIN records_fts fts ON r.rowid = fts.rowid
                        WHERE records_fts MATCH ?
                    """
                    params = [query]
                else:
                    # No search term, just browse
                    sql = "SELECT * FROM records WHERE 1=1"
                    params = []
                
                # Add filters
                if filters:
                    for field, value in filters.items():
                        if value and field in ['collection', 'archive', 'held_by']:
                            sql += f" AND {field} = ?"
                            params.append(value)
                        elif value and field == 'reference':
                            # Handle reference filtering (starts with pattern)
                            sql += f" AND reference LIKE ?"
                            params.append(f"{value}%")
                
                sql += f" ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                
                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()
                
                return [self._row_to_record(row) for row in rows]
                
        except sqlite3.Error as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return []

    def get_collections(self) -> List[Dict]:
        """
        Get all collections with record counts
        
        Returns:
            List of collection dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT 
                        collection,
                        COUNT(*) as record_count,
                        MIN(date_from) as earliest_date,
                        MAX(date_to) as latest_date
                    FROM records 
                    WHERE collection IS NOT NULL AND collection != ''
                    GROUP BY collection
                    ORDER BY record_count DESC
                """)
                
                return [dict(row) for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get collections: {e}")
            return []

    def get_statistics(self) -> Dict:
        """
        Get database statistics
        
        Returns:
            Dictionary with various statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                stats = {}
                
                # Total records
                cursor = conn.execute("SELECT COUNT(*) FROM records")
                stats['total_records'] = cursor.fetchone()[0]
                
                # Records by archive
                cursor = conn.execute("""
                    SELECT archive, COUNT(*) 
                    FROM records 
                    WHERE archive IS NOT NULL 
                    GROUP BY archive 
                    ORDER BY COUNT(*) DESC
                """)
                stats['archives'] = dict(cursor.fetchall())
                
                # Date range
                cursor = conn.execute("""
                    SELECT MIN(created_at), MAX(created_at)
                    FROM records
                """)
                date_range = cursor.fetchone()
                stats['date_range'] = {
                    'earliest': date_range[0],
                    'latest': date_range[1]
                }
                
                # Database size
                cursor = conn.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                stats['database_size'] = cursor.fetchone()[0]
                
                return stats
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}

    def log_api_request(self, 
                       endpoint: str,
                       query: Optional[str] = None,
                       status: int = 200,
                       records_retrieved: int = 0):
        """
        Log API request for compliance tracking
        
        Args:
            endpoint: API endpoint called
            query: Search query (if applicable)
            status: HTTP status code
            records_retrieved: Number of records returned
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO api_requests (endpoint, query, response_status, records_retrieved)
                    VALUES (?, ?, ?, ?)
                """, (endpoint, query, status, records_retrieved))
                conn.commit()
                
        except sqlite3.Error as e:
            logger.error(f"Failed to log API request: {e}")

    def get_5min_request_count(self, minutes_back: int = 5) -> int:
        """
        Get number of API requests made in the last N minutes
        
        Args:
            minutes_back: Number of minutes to look back
            
        Returns:
            Number of requests made
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes_back)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM api_requests 
                    WHERE timestamp >= ?
                """, (cutoff_time.isoformat(),))
                
                return cursor.fetchone()[0]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get 5-minute request count: {e}")
            return 0

    def get_daily_request_count(self, date: Optional[datetime] = None) -> int:
        """
        Get number of API requests made on a specific date
        
        Args:
            date: Date to check (defaults to today)
            
        Returns:
            Number of requests made
        """
        if date is None:
            date = datetime.now()
        
        date_str = date.strftime('%Y-%m-%d')
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM api_requests 
                    WHERE DATE(timestamp) = ?
                """, (date_str,))
                
                return cursor.fetchone()[0]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get daily request count: {e}")
            return 0

    def cleanup_old_data(self, days: int = 30):
        """
        Clean up old cache data to save space
        
        Args:
            days: Number of days to keep data
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Clean old search cache
                conn.execute("""
                    DELETE FROM search_cache 
                    WHERE created_at < ? OR expires_at < ?
                """, (cutoff_date.isoformat(), datetime.now().isoformat()))
                
                # Clean old API request logs (keep 1 year)
                log_cutoff = datetime.now() - timedelta(days=365)
                conn.execute("""
                    DELETE FROM api_requests 
                    WHERE timestamp < ?
                """, (log_cutoff.isoformat(),))
                
                conn.commit()
                logger.info(f"Cleaned up data older than {days} days")
                
        except sqlite3.Error as e:
            logger.error(f"Failed to cleanup old data: {e}")

    def _row_to_record(self, row: sqlite3.Row) -> Record:
        """Convert database row to Record object"""
        
        # Convert pipe-separated strings back to lists
        subjects = row['subjects'].split('|') if row['subjects'] else []
        creators = row['creators'].split('|') if row['creators'] else []
        places = row['places'].split('|') if row['places'] else []
        web_links = row['web_links'].split('|') if row['web_links'] else []
        digital_files = row['digital_files'].split('|') if row['digital_files'] else []
        
        return Record(
            id=row['id'],
            title=row['title'],
            description=row['description'],
            date_from=row['date_from'],
            date_to=row['date_to'],
            reference=row['reference'],
            archive=row['archive'],
            collection=row['collection'],
            subjects=[s for s in subjects if s],
            creators=[c for c in creators if c],
            places=[p for p in places if p],
            catalogue_source=row['catalogue_source'],
            access_conditions=row['access_conditions'],
            closure_status=row['closure_status'],
            legal_status=row['legal_status'],
            held_by=row['held_by'],
            former_reference=row['former_reference'],
            note=row['note'],
            arrangement=row['arrangement'],
            dimensions=row['dimensions'],
            administrator_background=row['administrator_background'],
            custodial_history=row['custodial_history'],
            acquisition_information=row['acquisition_information'],
            appraisal_information=row['appraisal_information'],
            accruals=row['accruals'],
            related_material=row['related_material'],
            publication_note=row['publication_note'],
            copies_information=row['copies_information'],
            originals_held_elsewhere=row['originals_held_elsewhere'],
            unpublished_finding_aids=row['unpublished_finding_aids'],
            publications=row['publications'],
            map_designation=row['map_designation'],
            physical_description=row['physical_description'],
            immediate_source=row['immediate_source'],
            scope_content=row['scope_content'],
            language=row['language'],
            script=row['script'],
            web_links=[w for w in web_links if w],
            digital_files=[d for d in digital_files if d],
            
            # Hierarchical structure fields
            parent_id=row['parent_id'],
            level=row['level'],
            child_count=row['child_count'],
            
            # Provenance tracking
            provenance=json.loads(row['provenance']) if row['provenance'] else {},
            
            # API Bible Section 4.1 additional fields
            catalogue_level=row['catalogue_level'] if 'catalogue_level' in row.keys() else None,
            closure_code=row['closure_code'] if 'closure_code' in row.keys() else None,
            digitised=row['digitised'] if 'digitised' in row.keys() else None,
            hierarchy=json.loads(row['hierarchy']) if 'hierarchy' in row.keys() and row['hierarchy'] else [],
            covering_from_date=row['covering_from_date'] if 'covering_from_date' in row.keys() else None,
            covering_to_date=row['covering_to_date'] if 'covering_to_date' in row.keys() else None,
            
            # Enhanced TNA API metadata fields
            catalogue_id=row['catalogue_id'] if 'catalogue_id' in row.keys() else None,
            covering_dates=row['covering_dates'] if 'covering_dates' in row.keys() else None,
            is_parent=row['is_parent'] if 'is_parent' in row.keys() else None
        )

    # ===== CRAWL QUEUE MANAGEMENT (Workflow.md Implementation) =====
    
    def add_to_crawl_queue(self, url: str, record_id: str, parent_id: Optional[str] = None, 
                          expected_level: Optional[str] = None) -> bool:
        """Add a URL to the crawl queue for hierarchical traversal"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO crawl_queue 
                    (url, record_id, parent_id, expected_level) 
                    VALUES (?, ?, ?, ?)
                """, (url, record_id, parent_id, expected_level))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to add URL to crawl queue: {e}")
            return False
    
    def get_next_crawl_item(self) -> Optional[Dict[str, Any]]:
        """Get the next QUEUED item from the crawl queue"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM crawl_queue 
                    WHERE status = 'QUEUED' 
                    ORDER BY discovered_at ASC 
                    LIMIT 1
                """)
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get next crawl item: {e}")
            return None
    
    def update_crawl_status(self, url: str, status: str, error_message: Optional[str] = None) -> bool:
        """Update the status of a crawl queue item"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if status == 'COMPLETED':
                    cursor = conn.execute("""
                        UPDATE crawl_queue 
                        SET status = ?, processed_at = CURRENT_TIMESTAMP, error_message = ?
                        WHERE url = ?
                    """, (status, error_message, url))
                elif status == 'FAILED':
                    cursor = conn.execute("""
                        UPDATE crawl_queue 
                        SET status = ?, retries = retries + 1, error_message = ?
                        WHERE url = ?
                    """, (status, error_message, url))
                else:  # PROCESSING
                    cursor = conn.execute("""
                        UPDATE crawl_queue 
                        SET status = ?
                        WHERE url = ?
                    """, (status, url))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to update crawl status: {e}")
            return False
    
    def get_crawl_stats(self) -> Dict[str, int]:
        """Get statistics about the crawl queue"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM crawl_queue 
                    GROUP BY status
                """)
                stats = dict(cursor.fetchall())
                
                # Ensure all statuses are present
                for status in ['QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED']:
                    if status not in stats:
                        stats[status] = 0
                        
                return stats
        except sqlite3.Error as e:
            logger.error(f"Failed to get crawl stats: {e}")
            return {}
    
    def reset_failed_items(self, max_retries: int = 3) -> int:
        """Reset FAILED items back to QUEUED if they haven't exceeded max retries"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    UPDATE crawl_queue 
                    SET status = 'QUEUED', error_message = NULL 
                    WHERE status = 'FAILED' AND retries < ?
                """, (max_retries,))
                return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Failed to reset failed items: {e}")
            return 0

    def close(self):
        """Close database connections"""
        pass  # Using context managers, so no persistent connections

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
