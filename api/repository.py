"""
Repository Client for TNA Discovery API

Implements repository endpoints from API Bible Section 3.3
"""

import logging
from typing import List, Dict, Any, Optional

from .client import DiscoveryClient, PermanentError, TransientError, RateLimitError

logger = logging.getLogger(__name__)


class RepositoryClient:
    """
    Client for TNA Repository endpoints
    
    Implements API Bible Section 3.3 endpoints:
    - GET /repository/v1/details/{id}
    - GET /repository/v1/collection
    """
    
    def __init__(self, api_client: Optional[DiscoveryClient] = None):
        """
        Initialize repository client
        
        Args:
            api_client: DiscoveryClient instance (will create new if None)
        """
        self.api_client = api_client or DiscoveryClient()
        self.logger = logging.getLogger(__name__)
    
    def get_repository_details(self, repo_id: str) -> Optional[Dict[str, Any]]:
        """
        Get archive details by archive record ID
        (API Bible Section 3.3: GET /repository/v1/details/{id})
        
        Args:
            repo_id: Archive record ID (e.g., 'A65')
            
        Returns:
            Repository details dictionary or None if not found
        """
        try:
            data = self.api_client._make_request(f'repository/v1/details/{repo_id}')
            self.logger.info(f"Retrieved repository details for {repo_id}")
            return data
        except PermanentError as e:
            if "not found" in str(e).lower():
                self.logger.warning(f"Repository {repo_id} not found")
                return None
            raise
        except (TransientError, RateLimitError) as e:
            self.logger.error(f"Error retrieving repository {repo_id}: {e}")
            raise
    
    def list_repositories(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Get Archon records collection
        (API Bible Section 3.3: GET /repository/v1/collection)
        
        Args:
            limit: Number of records (1-500, default 30)
            
        Returns:
            List of repository records
        """
        try:
            params = {'limit': min(max(limit, 1), 500)}  # Enforce API limits
            data = self.api_client._make_request('repository/v1/collection', params)
            
            # Extract repositories from response
            repositories = data.get('Repositories', data.get('repositories', []))
            
            self.logger.info(f"Retrieved {len(repositories)} repositories")
            return repositories
            
        except Exception as e:
            self.logger.error(f"Error listing repositories: {e}")
            raise
    
    def search_repositories(self, name_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search repositories with optional name filtering
        
        Args:
            name_filter: Optional name filter for repositories
            
        Returns:
            Filtered list of repositories
        """
        repositories = self.list_repositories(limit=500)  # Get maximum
        
        if name_filter:
            name_filter_lower = name_filter.lower()
            filtered_repos = []
            
            for repo in repositories:
                repo_name = repo.get('Name', repo.get('name', '')).lower()
                if name_filter_lower in repo_name:
                    filtered_repos.append(repo)
            
            self.logger.info(f"Filtered to {len(filtered_repos)} repositories matching '{name_filter}'")
            return filtered_repos
        
        return repositories
    
    def get_repository_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Find repository by exact name match
        
        Args:
            name: Repository name to search for
            
        Returns:
            Repository details or None if not found
        """
        repositories = self.search_repositories(name)
        
        for repo in repositories:
            repo_name = repo.get('Name', repo.get('name', ''))
            if repo_name.lower() == name.lower():
                return repo
        
        self.logger.info(f"Repository '{name}' not found")
        return None
    
    def get_repository_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about available repositories
        
        Returns:
            Statistics dictionary
        """
        try:
            repositories = self.list_repositories(limit=500)
            
            # Analyze repository data
            total_repos = len(repositories)
            tna_repos = 0
            other_repos = 0
            
            for repo in repositories:
                repo_type = repo.get('Type', repo.get('type', '')).lower()
                if 'national archives' in repo_type or repo.get('IsTNA', False):
                    tna_repos += 1
                else:
                    other_repos += 1
            
            stats = {
                'total_repositories': total_repos,
                'tna_repositories': tna_repos,
                'other_repositories': other_repos,
                'data_retrieved_at': self.api_client.session.headers.get('User-Agent', 'Unknown')
            }
            
            self.logger.info(f"Repository statistics: {stats}")
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting repository statistics: {e}")
            return {
                'error': str(e),
                'total_repositories': 0
            }
