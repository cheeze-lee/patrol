"""
GitHub Repository Code Provider
"""

import os
import re
import time
import base64
from typing import Optional, Dict, List
from urllib.parse import quote
try:
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore


class GitHubRepositoryCodeProvider:
    """GitHub repository code provider"""
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize GitHub provider
        
        Args:
            token: GitHub Personal Access Token (defaults to GITHUB_TOKEN env var)
        """
        self.token = token or os.getenv('GITHUB_TOKEN')
        
        self.base_url = 'https://api.github.com'
        self.max_retries = 3
        self.retry_delay_ms = 1000
        self.code_cache: Dict[str, tuple[str, int]] = {}
        self.cache_ttl_ms = 3600000  # 1 hour
    
    def get_file_content(self, repo_url: str, file_path: str, ref: Optional[str] = None) -> str:
        """Get file content from repository"""
        try:
            owner, repo = self._parse_repository_url(repo_url)
            if not owner or not repo:
                raise ValueError(f'Invalid repository URL: {repo_url}')
            
            return self._fetch_file_content(owner, repo, file_path, ref=ref)
        except Exception as e:
            print(f'[GitHub] Failed to get file content: {e}')
            raise
    
    def get_files_by_pattern(self, repo_url: str, pattern: str) -> List[str]:
        """Get files matching pattern"""
        try:
            owner, repo = self._parse_repository_url(repo_url)
            if not owner or not repo:
                raise ValueError(f'Invalid repository URL: {repo_url}')
            
            return self._search_relevant_files(owner, repo, pattern)
        except Exception as e:
            print(f'[GitHub] Failed to search files: {e}')
            return []
    
    def get_repo_metadata(self, repo_url: str) -> Dict:
        """Get repository metadata"""
        try:
            owner, repo = self._parse_repository_url(repo_url)
            if not owner or not repo:
                raise ValueError(f'Invalid repository URL: {repo_url}')
            
            url = f'{self.base_url}/repos/{owner}/{repo}'
            response = self._make_request(url)
            
            return {
                'name': response.get('name'),
                'description': response.get('description'),
                'url': response.get('html_url'),
                'language': response.get('language'),
                'stars': response.get('stargazers_count'),
                'forks': response.get('forks_count'),
            }
        except Exception as e:
            print(f'[GitHub] Failed to get repo metadata: {e}')
            return {}
    
    def _fetch_file_content(self, owner: str, repo: str, file_path: str, ref: Optional[str] = None) -> str:
        """Fetch file content from GitHub"""
        cache_key = f'{owner}/{repo}/{ref or "default"}/{file_path}'
        
        # Check cache
        if cache_key in self.code_cache:
            content, timestamp = self.code_cache[cache_key]
            if time.time() * 1000 - timestamp < self.cache_ttl_ms:
                print(f'[GitHub] Cache hit for {cache_key}')
                return content
        
        url = f'{self.base_url}/repos/{owner}/{repo}/contents/{file_path}'
        if ref:
            url = f'{url}?ref={quote(ref, safe="")}'
        response = self._make_request(url)
        
        if response and response.get('type') == 'file' and response.get('content'):
            content = base64.b64decode(response['content']).decode('utf-8')
            self.code_cache[cache_key] = (content, time.time() * 1000)
            return content
        
        raise ValueError(f'File not found: {file_path}')
    
    def _search_relevant_files(self, owner: str, repo: str, pattern: str) -> List[str]:
        """Search for relevant files in repository"""
        try:
            keywords = self._extract_keywords(pattern)
            results = []
            
            for keyword in keywords[:3]:
                try:
                    # Keep the query broad; callers can post-filter and/or request specific paths.
                    url = f'{self.base_url}/search/code?q=repo:{owner}/{repo}+{keyword}'
                    response = self._make_request(url)
                    
                    if response and response.get('items'):
                        for item in response['items'][:2]:
                            try:
                                file_content = self._fetch_file_content(owner, repo, item['path'])
                                if file_content:
                                    results.append(file_content)
                            except:
                                pass
                except Exception as e:
                    print(f'[GitHub] Search failed for keyword "{keyword}": {e}')
            
            return results
        except Exception as e:
            print(f'[GitHub] Search failed: {e}')
            return []
    
    def _parse_repository_url(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """Parse repository URL"""
        try:
            # Support formats: https://github.com/owner/repo, git@github.com:owner/repo.git
            match = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
            if match:
                return match.group(1), match.group(2)
            return None, None
        except Exception as e:
            print(f'[GitHub] Failed to parse repository URL: {e}')
            return None, None
    
    def _make_request(self, url: str, retry_count: int = 0) -> Optional[Dict]:
        """Make authenticated request to GitHub API"""
        try:
            if requests is None:
                raise ModuleNotFoundError('requests package is not installed (pip install -r requirements.txt)')

            headers = {
                'Accept': 'application/vnd.github.v3.raw+json',
                'User-Agent': 'Patrol-Error-Analyzer',
            }
            if self.token:
                headers['Authorization'] = f'token {self.token}'
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 404:
                return None
            
            if response.status_code == 403:
                print('[GitHub] Rate limit or permission issue (403)')
                raise Exception('GitHub API rate limit or permission denied')
            
            if not response.ok:
                raise Exception(f'GitHub API error: {response.status_code} {response.reason}')
            
            return response.json()
        except Exception as e:
            if retry_count < self.max_retries:
                delay_ms = self.retry_delay_ms * (2 ** retry_count)
                print(f'[GitHub] Retrying after {delay_ms}ms...')
                time.sleep(delay_ms / 1000)
                return self._make_request(url, retry_count + 1)
            raise
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        }
        
        keywords = [
            word for word in re.split(r'[\s\W]+', text.lower())
            if len(word) > 3 and word not in stop_words
        ]
        
        return keywords[:5]
    
    def clear_cache(self) -> None:
        """Clear code cache"""
        self.code_cache.clear()
        print('[GitHub] Code cache cleared')
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            'size': len(self.code_cache),
            'entries': len(self.code_cache),
        }
