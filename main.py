#!/usr/bin/env python3
"""
National Archives Discovery Catalogue Clone
Main entry point for the application

Usage:
    python main.py --help           # Show help
    python main.py search "query"   # Search records
    python main.py fetch "query"    # Fetch from API
    python main.py bootstrap        # Bootstrap with popular searches
    python main.py index            # Build semantic search index
    python main.py serve            # Start web interface
    python main.py stats            # Show statistics
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Initialize structured logging from environment
from utils.logging_config import init_from_environment
init_from_environment()

# Import and run CLI
from cli.main import main

if __name__ == '__main__':
    main()
