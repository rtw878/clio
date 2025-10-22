"""
FastAPI web application for National Archives Discovery clone
"""

from fastapi import FastAPI, Request, Form, Query, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, List, Dict
import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from storage.database import DatabaseManager
from storage.cache import CacheManager
try:
    from search.semantic_search import SemanticSearchEngine, SEMANTIC_SEARCH_AVAILABLE
except ImportError:
    SEMANTIC_SEARCH_AVAILABLE = False
    SemanticSearchEngine = None
from search.query_processor import QueryProcessor
from api.models import Record

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="National Archives Discovery Clone",
    description="Local interface for searching National Archives Discovery catalogue",
    version="1.0.0"
)

# Initialize components (lazy loading)
db_manager = None
cache_manager = None
search_engine = None
query_processor = None

def get_db_manager():
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager()
    return db_manager

def get_cache_manager():
    global cache_manager
    if cache_manager is None:
        cache_manager = CacheManager()
    return cache_manager

def get_search_engine():
    global search_engine
    if search_engine is None and SEMANTIC_SEARCH_AVAILABLE:
        try:
            search_engine = SemanticSearchEngine()
        except Exception as e:
            logger.warning(f"Semantic search not available: {e}")
            search_engine = None
    return search_engine

def get_query_processor():
    global query_processor
    if query_processor is None:
        query_processor = QueryProcessor()
    return query_processor

# Templates
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Static files (create if needed)
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)

try:
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
except Exception:
    pass  # Static files optional for basic functionality


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with search interface"""
    
    db = get_db_manager()
    
    # Get basic statistics
    stats = db.get_statistics()
    collections = db.get_collections()[:10]  # Top 10 collections
    
    return templates.TemplateResponse("home.html", {
        "request": request,
        "stats": stats,
        "collections": collections
    })


@app.get("/search", response_class=HTMLResponse)
@app.post("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: Optional[str] = Form(None),
    query: Optional[str] = Query(None),
    collection: Optional[str] = Form(None),
    archive: Optional[str] = Form(None),
    semantic: bool = Form(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    """Search results page"""
    
    # Get query from either form or URL parameter
    search_query = q or query
    
    if not search_query:
        return templates.TemplateResponse("search.html", {
            "request": request,
            "query": "",
            "results": [],
            "total_results": 0,
            "page": page,
            "per_page": per_page,
            "total_pages": 0
        })
    
    try:
        db = get_db_manager()
        cache = get_cache_manager()
        
        # Prepare filters
        filters = {}
        if collection:
            filters['collection'] = collection
        if archive:
            filters['archive'] = archive
        
        # Check cache first
        cached_result = cache.get_cached_search(search_query, filters)
        
        if cached_result and not semantic:
            results = [(record, 0.0) for record in cached_result.records]
            total_results = cached_result.total_results
        else:
            if semantic:
                # Use semantic search
                search_eng = get_search_engine()
                if search_eng:
                    results = search_eng.semantic_search(search_query, per_page, filters)
                    total_results = len(results)
                else:
                    # Fallback to traditional search
                    records = db.search_records(
                        search_query, 
                        limit=per_page, 
                        offset=(page-1)*per_page,
                        filters=filters
                    )
                    results = [(record, 0.0) for record in records]
                    total_results = len(records)  # Approximate
            else:
                # Traditional search
                records = db.search_records(
                    search_query,
                    limit=per_page,
                    offset=(page-1)*per_page,
                    filters=filters
                )
                results = [(record, 0.0) for record in records]
                total_results = len(records)  # Approximate
                
                # Cache the results
                from api.models import SearchResult
                search_result = SearchResult(
                    records=records,
                    total_results=total_results,
                    page=page,
                    per_page=per_page,
                    total_pages=(total_results + per_page - 1) // per_page,
                    query=search_query
                )
                cache.cache_search_results(search_query, search_result, filters)
        
        total_pages = (total_results + per_page - 1) // per_page
        
        # Process query for suggestions
        processor = get_query_processor()
        processed_query = processor.process_query(search_query) if processor else {}
        
        return templates.TemplateResponse("search.html", {
            "request": request,
            "query": search_query,
            "results": results,
            "total_results": total_results,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "semantic": semantic,
            "collection": collection,
            "archive": archive,
            "processed_query": processed_query
        })
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e)
        })


@app.get("/record/{record_id}")
async def record_detail(request: Request, record_id: str):
    """Individual record detail page"""
    
    try:
        db = get_db_manager()
        record = db.get_record(record_id)
        
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        
        # Get similar records if semantic search is available
        similar_records = []
        search_eng = get_search_engine()
        if search_eng:
            try:
                similar_results = search_eng.get_similar_records(record_id, limit=5)
                similar_records = [r for r, s in similar_results]
            except Exception as e:
                logger.warning(f"Failed to get similar records: {e}")
        
        return templates.TemplateResponse("record.html", {
            "request": request,
            "record": record,
            "similar_records": similar_records
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Record detail error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e)
        })


@app.get("/collections")
async def collections_page(request: Request):
    """Collections browse page"""
    
    try:
        db = get_db_manager()
        collections = db.get_collections()
        
        return templates.TemplateResponse("collections.html", {
            "request": request,
            "collections": collections
        })
        
    except Exception as e:
        logger.error(f"Collections error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e)
        })


@app.get("/stats")
async def stats_page(request: Request):
    """Statistics and system information page"""
    
    try:
        db = get_db_manager()
        cache = get_cache_manager()
        
        # Get various statistics
        db_stats = db.get_statistics()
        cache_stats = cache.get_cache_stats()
        collections = db.get_collections()
        
        # API usage
        today_requests = db.get_daily_request_count()
        
        # Semantic search stats
        index_stats = {}
        search_eng = get_search_engine()
        if search_eng:
            try:
                index_stats = search_eng.get_index_stats()
            except Exception:
                pass
        
        return templates.TemplateResponse("stats.html", {
            "request": request,
            "db_stats": db_stats,
            "cache_stats": cache_stats,
            "collections": collections,
            "today_requests": today_requests,
            "index_stats": index_stats
        })
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": str(e)
        })


# API Endpoints

@app.get("/api/search")
async def api_search(
    q: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    semantic: bool = Query(False),
    collection: Optional[str] = Query(None),
    archive: Optional[str] = Query(None)
):
    """API endpoint for search"""
    
    try:
        db = get_db_manager()
        
        filters = {}
        if collection:
            filters['collection'] = collection
        if archive:
            filters['archive'] = archive
        
        if semantic:
            search_eng = get_search_engine()
            if search_eng:
                results = search_eng.semantic_search(q, limit, filters)
                records_data = []
                for record, score in results:
                    record_dict = record.to_dict()
                    record_dict['relevance_score'] = score
                    records_data.append(record_dict)
            else:
                return JSONResponse(
                    status_code=503,
                    content={"error": "Semantic search not available"}
                )
        else:
            records = db.search_records(q, limit, offset, filters)
            records_data = [record.to_dict() for record in records]
        
        return {
            "query": q,
            "results": records_data,
            "total_results": len(records_data),
            "semantic": semantic
        }
        
    except Exception as e:
        logger.error(f"API search error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/record/{record_id}")
async def api_record(record_id: str):
    """API endpoint for individual record"""
    
    try:
        db = get_db_manager()
        record = db.get_record(record_id)
        
        if not record:
            return JSONResponse(
                status_code=404,
                content={"error": "Record not found"}
            )
        
        return record.to_dict()
        
    except Exception as e:
        logger.error(f"API record error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/collections")
async def api_collections():
    """API endpoint for collections"""
    
    try:
        db = get_db_manager()
        collections = db.get_collections()
        return {"collections": collections}
        
    except Exception as e:
        logger.error(f"API collections error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/suggest")
async def api_suggest(q: str, limit: int = Query(5, ge=1, le=20)):
    """API endpoint for search suggestions"""
    
    try:
        search_eng = get_search_engine()
        if search_eng:
            suggestions = search_eng.suggest_queries(q, limit)
        else:
            # Fallback: simple database-based suggestions
            db = get_db_manager()
            # Simple implementation: get recent cached queries
            cache = get_cache_manager()
            cached_queries = cache.get_cached_queries()
            suggestions = [cq for cq in cached_queries if q.lower() in cq.lower()][:limit]
        
        return {"suggestions": suggestions}
        
    except Exception as e:
        logger.error(f"API suggest error: {e}")
        return {"suggestions": []}


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    
    try:
        db = get_db_manager()
        stats = db.get_statistics()
        
        return {
            "status": "healthy",
            "total_records": stats.get("total_records", 0),
            "semantic_search": get_search_engine() is not None
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
