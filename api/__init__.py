"""
National Archives Discovery API Client
Respectful and compliant access to the Discovery catalogue
"""

from .client import DiscoveryClient
from .models import Record, SearchResult, Collection

__all__ = ['DiscoveryClient', 'Record', 'SearchResult', 'Collection']
