"""
Structured JSON Logging Configuration for National Archives Discovery Clone

Implements Workflow.md Section 6.2: Comprehensive Logging requirements
- Machine-readable JSON format for log analysis platforms
- Contextual information for effective debugging
- Standard log levels with detailed messages
"""

import logging
import logging.config
import json
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs structured JSON logs
    
    Implements Workflow.md logging requirements:
    - Machine-readable format for ELK Stack/Datadog compatibility
    - Contextual information for each log entry
    - Detailed human-readable messages
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON"""
        
        # Build base log entry
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'thread': record.thread,
            'process': record.process
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': self.formatException(record.exc_info) if record.exc_info else None
            }
        
        # Add custom context fields
        for key, value in record.__dict__.items():
            if key.startswith('ctx_'):
                # Remove 'ctx_' prefix for cleaner JSON
                clean_key = key[4:]
                log_entry[clean_key] = value
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)


class ContextAdapter(logging.LoggerAdapter):
    """
    Logger adapter that adds contextual information to log records
    
    Allows adding request-specific context like record IDs, URLs, etc.
    """
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Add context to log record"""
        
        # Add context fields to the record
        extra = kwargs.get('extra', {})
        
        # Add our context with 'ctx_' prefix
        for key, value in self.extra.items():
            extra[f'ctx_{key}'] = value
        
        kwargs['extra'] = extra
        return msg, kwargs


def setup_logging(
    log_level: str = 'INFO',
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_json: bool = True
) -> None:
    """
    Setup structured logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (None = no file logging)
        enable_console: Whether to enable console logging
        enable_json: Whether to use JSON formatting
    """
    
    # Create logs directory if needed
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure formatters
    if enable_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Configure specific loggers
    configure_application_loggers()


def configure_application_loggers():
    """Configure application-specific loggers with appropriate levels"""
    
    # Our application loggers
    app_loggers = [
        'api.client',
        'api.traversal', 
        'storage.database',
        'storage.cache',
        'search.semantic_search',
        'cli.main',
        'web.app'
    ]
    
    for logger_name in app_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)  # App loggers at INFO level
    
    # External library loggers (reduce noise)
    external_loggers = {
        'requests': logging.WARNING,
        'urllib3': logging.WARNING,
        'httpx': logging.WARNING,
        'chromadb': logging.WARNING,
        'sentence_transformers': logging.WARNING,
        'transformers': logging.ERROR,
        'torch': logging.ERROR
    }
    
    for logger_name, level in external_loggers.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)


def get_contextual_logger(name: str, **context) -> ContextAdapter:
    """
    Get a logger with contextual information
    
    Args:
        name: Logger name
        **context: Contextual key-value pairs
        
    Returns:
        Logger adapter with context
        
    Example:
        logger = get_contextual_logger('api.client', 
                                      record_id='C243', 
                                      url='https://...')
        logger.info("Processing record", extra={'response_time': 1.2})
    """
    base_logger = logging.getLogger(name)
    return ContextAdapter(base_logger, context)


def log_api_request(
    logger: logging.Logger,
    method: str,
    url: str,
    status_code: int,
    response_time: float,
    record_count: Optional[int] = None,
    error: Optional[str] = None
) -> None:
    """
    Log API request with standardized fields for analysis
    
    Args:
        logger: Logger instance
        method: HTTP method
        url: Request URL
        status_code: HTTP status code
        response_time: Response time in seconds
        record_count: Number of records retrieved
        error: Error message if request failed
    """
    
    log_data = {
        'extra': {
            'ctx_api_method': method,
            'ctx_api_url': url,
            'ctx_api_status': status_code,
            'ctx_api_response_time': response_time,
            'ctx_api_success': 200 <= status_code < 300
        }
    }
    
    if record_count is not None:
        log_data['extra']['ctx_api_record_count'] = record_count
    
    if error:
        log_data['extra']['ctx_api_error'] = error
    
    if 200 <= status_code < 300:
        message = f"API request successful: {method} {url}"
        if record_count:
            message += f" (retrieved {record_count} records)"
        logger.info(message, **log_data)
    else:
        message = f"API request failed: {method} {url} [{status_code}]"
        if error:
            message += f" - {error}"
        logger.error(message, **log_data)


def log_traversal_progress(
    logger: logging.Logger,
    processed: int,
    failed: int,
    queue_size: int,
    current_record: Optional[str] = None
) -> None:
    """
    Log traversal progress with standardized metrics
    
    Args:
        logger: Logger instance
        processed: Number of records processed
        failed: Number of failed records
        queue_size: Current queue size
        current_record: Currently processing record ID
    """
    
    log_data = {
        'extra': {
            'ctx_traversal_processed': processed,
            'ctx_traversal_failed': failed,
            'ctx_traversal_queue_size': queue_size,
            'ctx_traversal_success_rate': processed / (processed + failed) if (processed + failed) > 0 else 1.0
        }
    }
    
    if current_record:
        log_data['extra']['ctx_traversal_current'] = current_record
    
    message = f"Traversal progress: {processed:,} processed, {failed:,} failed, {queue_size:,} queued"
    logger.info(message, **log_data)


def log_database_operation(
    logger: logging.Logger,
    operation: str,
    table: str,
    record_count: int,
    duration: float,
    success: bool = True,
    error: Optional[str] = None
) -> None:
    """
    Log database operations with performance metrics
    
    Args:
        logger: Logger instance
        operation: Database operation (INSERT, UPDATE, SELECT, etc.)
        table: Target table name
        record_count: Number of records affected
        duration: Operation duration in seconds
        success: Whether operation succeeded
        error: Error message if operation failed
    """
    
    log_data = {
        'extra': {
            'ctx_db_operation': operation,
            'ctx_db_table': table,
            'ctx_db_record_count': record_count,
            'ctx_db_duration': duration,
            'ctx_db_success': success
        }
    }
    
    if error:
        log_data['extra']['ctx_db_error'] = error
    
    if success:
        message = f"Database {operation} completed: {record_count} records in {table} ({duration:.3f}s)"
        logger.info(message, **log_data)
    else:
        message = f"Database {operation} failed: {table} - {error}"
        logger.error(message, **log_data)


# Initialize logging from environment variables
def init_from_environment():
    """Initialize logging configuration from environment variables"""
    
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_file = os.getenv('LOG_FILE', './logs/discovery.log')
    enable_json = os.getenv('LOG_FORMAT', 'json').lower() == 'json'
    
    setup_logging(
        log_level=log_level,
        log_file=log_file,
        enable_console=True,
        enable_json=enable_json
    )
