# clio

<p align="center">
  <img src=".github/assets/logo.svg" alt="clio - National Archives Research Platform" width="400">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB" alt="Python"></a>
  <a href="https://github.com/rtw878/clio"><img src="https://img.shields.io/badge/GitHub-rtw878%2Fclio-black" alt="Repo"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.104+-009688" alt="FastAPI"></a>
  <a href="https://www.sqlite.org/"><img src="https://img.shields.io/badge/SQLite-3.45+-003B57" alt="SQLite"></a>
</p>

---

## Overview

clio is a research platform for working with The National Archives (TNA) Discovery catalogue locally. It provides fast local search, a web interface, and respects API rate limits while maintaining data integrity through validation and provenance tracking.

---

## Features

- **Local-first storage**: SQLite database with FTS5 full-text search
- **Web interface**: FastAPI + Jinja2 templates for browsing and searching records
- **API integration**: Respectful rate limiting and error handling for TNA Discovery API
- **Semantic search**: Optional AI-powered search using sentence transformers
- **Data integrity**: Comprehensive validation and provenance tracking
- **Bulk operations**: Streaming export, backup, and data processing

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/rtw878/clio.git
cd clio

# Install dependencies
pip install -r requirements.txt

# Configure (optional)
cp config.env.example config.env

# Start web interface
python main.py serve --port 8080
```

Then open http://localhost:8080

### Command Line Usage

```bash
# Search records locally
python main.py search "World War One army service records"

# Fetch from TNA API
python main.py fetch "Passenger lists" --limit 100

# Build semantic search index
python main.py index

# View statistics
python main.py stats
```

---

## Architecture

### Components

- **web/**: FastAPI application with Jinja2 templates
- **api/**: Discovery API client with rate limiting and retries
- **storage/**: SQLite database with FTS5 and schema migrations
- **search/**: Semantic search engine with ChromaDB
- **validation/**: Data validators and quality reporting
- **utils/**: Exporters, streaming, backups, and provenance tracking

### Data Flow

```
TNA Discovery API → API Client → Validation → Database → Search Index
                                 ↓
                          Web Interface ← Cache
                                 ↓
                          User Queries → Results
```

---

## API Integration

The API client implements proper rate limiting and error handling according to TNA's guidelines:

```python
class DiscoveryClient:
    """TNA API client with rate limiting and error handling"""
    
    def __init__(self):
        self.max_requests_per_5min = 3000
        self.requests_per_second = 1.0
        
    def _exponential_backoff_retry(self, func, max_retries=3):
        """Retry logic with exponential backoff and jitter"""
```

**Rate Limits:**
- 1 request per second
- 3000 requests per 5 minutes
- Daily limit of 3000 requests

---

## Search

Two search modes are available:

### Full-Text Search (FTS5)

```sql
CREATE VIRTUAL TABLE records_fts USING fts5(
    id, title, description, reference, subjects, creators, places,
    scope_content, note, content='records', content_rowid='rowid'
);
```

Fast SQLite FTS5 search across record fields with automatic ranking.

### Semantic Search (Optional)

```python
class SemanticSearchEngine:
    """Semantic search using sentence transformers"""
    
    def semantic_search(self, query: str, limit: int = 20):
        # Uses all-MiniLM-L6-v2 for similarity matching
        # ChromaDB vector database for efficient search
```

AI-powered similarity search for finding conceptually similar records.

### Query Processing

```python
class QueryProcessor:
    """Query parsing and optimization"""
    
    def process_query(self, query: str) -> Dict:
        # Historical date pattern recognition
        # Military term expansion (WW1 → World War One)
        # Query optimization for archival terminology
```

Intelligent query processing for better search results.

---

## Data Management

### Database Schema

The SQLite database stores records with hierarchical relationships:

```sql
ALTER TABLE records ADD COLUMN parent_id TEXT;
ALTER TABLE records ADD COLUMN level TEXT;
ALTER TABLE records ADD COLUMN child_count INTEGER;
```

Parent-child relationships support archival hierarchy traversal.

### Provenance Tracking

```python
class ProvenanceTracker:
    """Data lineage tracking"""
    
    def track_extraction(self, record_id: str, source_url: str):
        # Records extraction timestamp, method, and system info
        # Maintains transformation and validation history
```

Complete audit trail of data extraction and processing.

---

## Configuration

### Environment Variables

```bash
# API Configuration
API_BASE_URL=https://discovery.nationalarchives.gov.uk/API

# Database Settings
DB_PATH=./data/discovery.db

# Search Configuration
SEMANTIC_SEARCH_ENABLED=true
EMBEDDING_MODEL=all-MiniLM-L6-v2

# Performance Tuning
MAX_CONCURRENT_REQUESTS=5
CACHE_TTL_MINUTES=60
```

---

## Project Structure

```
clio/
├── api/              # TNA Discovery API client
├── cli/              # Command-line interface
├── search/           # Search engines (FTS5 + semantic)
├── storage/          # Database and cache management
├── utils/            # Exporters, backups, provenance
├── validation/       # Data validation and quality
├── web/              # FastAPI application and templates
└── main.py           # Entry point
```

---

## License

MIT License - see `LICENSE` file for details.
