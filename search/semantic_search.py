"""
Semantic search engine using sentence transformers and vector databases
Provides AI-powered search capabilities over National Archives data
"""

import logging
import os
from typing import List, Dict, Tuple, Optional
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    import chromadb
    from chromadb.config import Settings
    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Semantic search dependencies not available: {e}")
    logging.info("To enable semantic search, install: pip install sentence-transformers chromadb")
    SEMANTIC_SEARCH_AVAILABLE = False
    
    # Create dummy classes for graceful degradation
    class SentenceTransformer:
        def __init__(self, *args, **kwargs):
            raise ImportError("sentence-transformers not installed")
    
    class chromadb:
        @staticmethod
        def PersistentClient(*args, **kwargs):
            raise ImportError("chromadb not installed")
    
    class Settings:
        def __init__(self, *args, **kwargs):
            raise ImportError("chromadb not installed")

from api.models import Record
from storage.database import DatabaseManager

logger = logging.getLogger(__name__)


class SemanticSearchEngine:
    """
    AI-powered semantic search engine for National Archives records
    
    Uses sentence transformers to create embeddings and ChromaDB for 
    efficient vector similarity search.
    """
    
    def __init__(self, 
                 model_name: str = "all-MiniLM-L6-v2",
                 vector_db_path: str = "./data/vectors",
                 db_path: str = "./data/discovery.db"):
        """
        Initialize semantic search engine
        
        Args:
            model_name: Sentence transformer model to use
            vector_db_path: Path to vector database
            db_path: Path to SQLite database
        """
        if not SEMANTIC_SEARCH_AVAILABLE:
            raise ImportError(
                "Semantic search dependencies not available. "
                "Install with: pip install sentence-transformers chromadb"
            )
        
        self.model_name = model_name
        self.vector_db_path = vector_db_path
        self.db_path = db_path
        
        # Ensure vector database directory exists
        Path(vector_db_path).mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.model = None
        self.chroma_client = None
        self.collection = None
        self.db_manager = DatabaseManager(db_path)
        
        # Lazy load model and database
        self._model_loaded = False
        self._db_initialized = False
        
        logger.info(f"Semantic search engine initialized with model: {model_name}")

    def _load_model(self):
        """Lazy load the sentence transformer model"""
        if not self._model_loaded:
            logger.info(f"Loading sentence transformer model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            self._model_loaded = True

    def _init_vector_db(self):
        """Initialize ChromaDB vector database"""
        if not self._db_initialized:
            logger.info("Initializing vector database")
            
            self.chroma_client = chromadb.PersistentClient(
                path=self.vector_db_path,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Get or create collection
            try:
                self.collection = self.chroma_client.get_collection(
                    name="national_archives_records"
                )
                logger.info("Found existing vector collection")
            except Exception:
                # Collection doesn't exist, create it
                self.collection = self.chroma_client.create_collection(
                    name="national_archives_records",
                    metadata={"description": "National Archives Discovery records"}
                )
                logger.info("Created new vector collection")
            
            self._db_initialized = True

    def index_record(self, record: Record) -> bool:
        """
        Index a single record for semantic search
        
        Args:
            record: Record to index
            
        Returns:
            True if successful, False otherwise
        """
        self._load_model()
        self._init_vector_db()
        
        try:
            # Create searchable text from record
            searchable_text = self._create_searchable_text(record)
            
            # Generate embedding
            embedding = self.model.encode(searchable_text).tolist()
            
            # Store in vector database
            self.collection.upsert(
                ids=[record.id],
                embeddings=[embedding],
                documents=[searchable_text],
                metadatas=[{
                    'title': record.title,
                    'reference': record.reference or '',
                    'collection': record.collection or '',
                    'archive': record.archive or '',
                    'date_from': record.date_from or '',
                    'date_to': record.date_to or '',
                    'subjects': '|'.join(record.subjects) if record.subjects else '',
                    'creators': '|'.join(record.creators) if record.creators else '',
                    'places': '|'.join(record.places) if record.places else ''
                }]
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to index record {record.id}: {e}")
            return False

    def index_records_batch(self, records: List[Record], batch_size: int = 100) -> int:
        """
        Index multiple records efficiently
        
        Args:
            records: List of records to index
            batch_size: Number of records to process at once
            
        Returns:
            Number of records successfully indexed
        """
        if not records:
            return 0
        
        self._load_model()
        self._init_vector_db()
        
        indexed_count = 0
        
        # Process in batches to manage memory
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            try:
                # Prepare batch data
                ids = []
                embeddings = []
                documents = []
                metadatas = []
                
                for record in batch:
                    searchable_text = self._create_searchable_text(record)
                    
                    ids.append(record.id)
                    documents.append(searchable_text)
                    metadatas.append({
                        'title': record.title,
                        'reference': record.reference or '',
                        'collection': record.collection or '',
                        'archive': record.archive or '',
                        'date_from': record.date_from or '',
                        'date_to': record.date_to or '',
                        'subjects': '|'.join(record.subjects) if record.subjects else '',
                        'creators': '|'.join(record.creators) if record.creators else '',
                        'places': '|'.join(record.places) if record.places else ''
                    })
                
                # Generate embeddings for batch
                batch_texts = [self._create_searchable_text(r) for r in batch]
                batch_embeddings = self.model.encode(batch_texts).tolist()
                
                # Store batch in vector database
                self.collection.upsert(
                    ids=ids,
                    embeddings=batch_embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                
                indexed_count += len(batch)
                
                if indexed_count % 1000 == 0:
                    logger.info(f"Indexed {indexed_count} records")
                
            except Exception as e:
                logger.error(f"Failed to index batch starting at {i}: {e}")
        
        logger.info(f"Successfully indexed {indexed_count} records")
        return indexed_count

    def semantic_search(self, 
                       query: str,
                       limit: int = 20,
                       filters: Optional[Dict] = None) -> List[Tuple[Record, float]]:
        """
        Perform semantic search on indexed records
        
        Args:
            query: Search query in natural language
            limit: Maximum number of results
            filters: Metadata filters (collection, archive, etc.)
            
        Returns:
            List of (Record, similarity_score) tuples sorted by relevance
        """
        self._load_model()
        self._init_vector_db()
        
        try:
            # Generate query embedding
            query_embedding = self.model.encode(query).tolist()
            
            # Prepare ChromaDB filters
            where_clause = {}
            if filters:
                for key, value in filters.items():
                    if value and key in ['collection', 'archive']:
                        where_clause[key] = value
            
            # Search vector database
            search_kwargs = {
                'query_embeddings': [query_embedding],
                'n_results': limit
            }
            
            if where_clause:
                search_kwargs['where'] = where_clause
            
            results = self.collection.query(**search_kwargs)
            
            # Retrieve full records from SQLite
            record_results = []
            
            if results['ids'] and results['ids'][0]:
                for i, record_id in enumerate(results['ids'][0]):
                    record = self.db_manager.get_record(record_id)
                    if record:
                        # ChromaDB returns distances, convert to similarity scores
                        distance = results['distances'][0][i]
                        similarity = 1.0 - distance  # Convert distance to similarity
                        record_results.append((record, similarity))
            
            return record_results
            
        except Exception as e:
            logger.error(f"Semantic search failed for query '{query}': {e}")
            return []

    def hybrid_search(self, 
                     query: str,
                     limit: int = 20,
                     semantic_weight: float = 0.7,
                     filters: Optional[Dict] = None) -> List[Tuple[Record, float]]:
        """
        Combine semantic search with traditional full-text search
        
        Args:
            query: Search query
            limit: Maximum results
            semantic_weight: Weight for semantic vs text search (0.0-1.0)
            filters: Search filters
            
        Returns:
            Combined and re-ranked search results
        """
        # Get semantic search results
        semantic_results = self.semantic_search(query, limit * 2, filters)
        
        # Get traditional search results
        text_results = self.db_manager.search_records(query, limit * 2, filters=filters)
        
        # Combine and score results
        combined_scores = {}
        
        # Add semantic scores
        for record, score in semantic_results:
            combined_scores[record.id] = {
                'record': record,
                'semantic_score': score,
                'text_score': 0.0
            }
        
        # Add text scores (simple relevance based on position)
        for i, record in enumerate(text_results):
            text_score = 1.0 - (i / len(text_results))  # Higher score for earlier results
            
            if record.id in combined_scores:
                combined_scores[record.id]['text_score'] = text_score
            else:
                combined_scores[record.id] = {
                    'record': record,
                    'semantic_score': 0.0,
                    'text_score': text_score
                }
        
        # Calculate final scores
        final_results = []
        for entry in combined_scores.values():
            final_score = (
                semantic_weight * entry['semantic_score'] + 
                (1 - semantic_weight) * entry['text_score']
            )
            final_results.append((entry['record'], final_score))
        
        # Sort by final score and return top results
        final_results.sort(key=lambda x: x[1], reverse=True)
        return final_results[:limit]

    def get_similar_records(self, record_id: str, limit: int = 10) -> List[Tuple[Record, float]]:
        """
        Find records similar to a given record
        
        Args:
            record_id: ID of the source record
            limit: Maximum similar records to return
            
        Returns:
            List of similar records with similarity scores
        """
        # Get the source record
        source_record = self.db_manager.get_record(record_id)
        if not source_record:
            return []
        
        # Use the record's searchable text as query
        query_text = self._create_searchable_text(source_record)
        
        # Perform semantic search
        results = self.semantic_search(query_text, limit + 1)  # +1 to exclude self
        
        # Filter out the source record itself
        return [(record, score) for record, score in results if record.id != record_id]

    def suggest_queries(self, partial_query: str, limit: int = 5) -> List[str]:
        """
        Suggest query completions based on indexed content
        
        Args:
            partial_query: Partial search query
            limit: Maximum suggestions
            
        Returns:
            List of suggested query completions
        """
        try:
            # Simple implementation: search for similar records and extract keywords
            if len(partial_query) < 3:
                return []
            
            # Search for records matching partial query
            results = self.semantic_search(partial_query, limit * 2)
            
            # Extract keywords from titles and subjects
            suggestions = set()
            
            for record, _ in results:
                # Add title words
                title_words = record.title.lower().split()
                for word in title_words:
                    if word.startswith(partial_query.lower()) and len(word) > len(partial_query):
                        suggestions.add(word)
                
                # Add subject terms
                for subject in record.subjects:
                    if subject.lower().startswith(partial_query.lower()):
                        suggestions.add(subject)
            
            return list(suggestions)[:limit]
            
        except Exception as e:
            logger.error(f"Failed to generate query suggestions: {e}")
            return []

    def _create_searchable_text(self, record: Record) -> str:
        """
        Create comprehensive searchable text from a record
        
        Args:
            record: Record to process
            
        Returns:
            Combined searchable text
        """
        text_parts = []
        
        # Core fields
        if record.title:
            text_parts.append(record.title)
        
        if record.description:
            text_parts.append(record.description)
        
        if record.reference:
            text_parts.append(f"Reference: {record.reference}")
        
        # Subjects, creators, places
        if record.subjects:
            text_parts.append("Subjects: " + ", ".join(record.subjects))
        
        if record.creators:
            text_parts.append("Creators: " + ", ".join(record.creators))
        
        if record.places:
            text_parts.append("Places: " + ", ".join(record.places))
        
        # Archive and collection info
        if record.archive:
            text_parts.append(f"Archive: {record.archive}")
        
        if record.collection:
            text_parts.append(f"Collection: {record.collection}")
        
        # Scope and content
        if record.scope_content:
            text_parts.append(record.scope_content)
        
        if record.note:
            text_parts.append(record.note)
        
        # Administrative info
        if record.administrator_background:
            text_parts.append(record.administrator_background)
        
        if record.custodial_history:
            text_parts.append(record.custodial_history)
        
        # Date information
        if record.date_from or record.date_to:
            date_info = f"Date: {record.date_from or ''} - {record.date_to or ''}".strip(' -')
            text_parts.append(date_info)
        
        return " ".join(text_parts)

    def get_index_stats(self) -> Dict:
        """
        Get statistics about the vector index
        
        Returns:
            Dictionary with index statistics
        """
        try:
            self._init_vector_db()
            
            if self.collection:
                count_result = self.collection.count()
                
                return {
                    'total_records_indexed': count_result,
                    'model_name': self.model_name,
                    'vector_db_path': self.vector_db_path,
                    'collection_name': self.collection.name
                }
            else:
                return {
                    'total_records_indexed': 0,
                    'model_name': self.model_name,
                    'vector_db_path': self.vector_db_path,
                    'collection_name': None
                }
            
        except Exception as e:
            logger.warning(f"Index statistics not available: {e}")
            return {
                'total_records_indexed': 0,
                'model_name': self.model_name,
                'vector_db_path': self.vector_db_path,
                'collection_name': None
            }

    def reset_index(self):
        """Reset the vector index (delete all embeddings)"""
        try:
            self._init_vector_db()
            
            # Delete the collection and recreate it
            self.chroma_client.delete_collection("national_archives_records")
            
            self.collection = self.chroma_client.create_collection(
                name="national_archives_records",
                metadata={"description": "National Archives Discovery records"}
            )
            
            logger.info("Vector index reset successfully")
            
        except Exception as e:
            logger.error(f"Failed to reset vector index: {e}")

    def close(self):
        """Clean up resources"""
        # ChromaDB handles cleanup automatically
        pass
