"""
Error Analysis Engine - Core logic for error analysis
"""

import os
import re
import time
import threading
from concurrent.futures import Future
from typing import Optional
from patrol_types import (
    ErrorLog,
    ErrorLogEvent,
    AnalysisResult,
    ProcessingOptions,
)
from hashing import hash_error_log
from cache import InMemoryCache
from openai_provider import OpenAILLMProvider
from github_provider import GitHubRepositoryCodeProvider


class ErrorAnalysisEngine:
    """Main error analysis engine"""
    
    def __init__(
        self,
        cache: Optional[InMemoryCache] = None,
        llm_provider: Optional[OpenAILLMProvider] = None,
        code_provider: Optional[GitHubRepositoryCodeProvider] = None,
    ):
        """
        Initialize error analysis engine
        
        Args:
            cache: Cache provider (creates default if not provided)
            llm_provider: LLM provider (creates default if not provided)
            code_provider: Code provider (creates default if not provided)
        """
        self.cache = cache or InMemoryCache(max_size=1000, eviction_policy='LRU')
        self.llm_provider = llm_provider or OpenAILLMProvider()
        self.code_provider = code_provider or GitHubRepositoryCodeProvider()
        # In-process "singleflight" to avoid duplicate LLM calls under concurrency.
        self._inflight_lock = threading.Lock()
        self._inflight: dict[str, Future] = {}
    
    def process_error_log(
        self,
        event: ErrorLogEvent,
        options: Optional[ProcessingOptions] = None,
    ) -> Optional[AnalysisResult]:
        """
        Process error log event
        
        Returns cached result on cache hit (unless skip_cache is True).
        """
        options = options or ProcessingOptions()
        
        try:
            # Hash and normalize error
            error_hash, _normalized_error = hash_error_log(event.error_log)
            repo_url = (event.repository_url or os.getenv('DEFAULT_REPOSITORY_URL') or '').strip()
            repo_ref = self._extract_repository_ref(event.error_log.context)
            cache_key = f'analysis:{error_hash}'
            if repo_url:
                cache_key = f'analysis:{repo_url}:{repo_ref or "default"}:{error_hash}'
            
            print(f'[Engine] Processing error: {event.event_id} (hash: {error_hash[:8]}...)')
            
            # Check cache (unless skipped)
            if not options.skip_cache:
                cached_result = self.cache.get(cache_key)
                if cached_result:
                    print(f'[Engine] Cache hit for {error_hash[:8]}...')
                    return cached_result

            inflight_future, is_owner = self._get_or_create_inflight(cache_key)
            if not is_owner:
                print(f'[Engine] Waiting for in-flight analysis for {error_hash[:8]}...')
                return inflight_future.result()
            
            try:
                # Set up target repository context (best-effort).
                repository_context = self._build_repository_context(event)

                # Analyze error using LLM
                print(f'[Engine] Analyzing error with LLM...')
                analysis_result = self.llm_provider.analyze_error(
                    error_hash,
                    event.error_log,
                    repository_context=repository_context,
                )

                # Cache the result (unless skipped)
                if not options.skip_cache:
                    self.cache.set(cache_key, analysis_result, ttl=options.cache_ttl)

                inflight_future.set_result(analysis_result)

                print(f'[Engine] Analysis complete (confidence: {analysis_result.confidence_score}%)')

                return analysis_result
            except Exception as e:
                inflight_future.set_exception(e)
                raise
            finally:
                self._clear_inflight(cache_key, inflight_future)
        
        except Exception as e:
            print(f'[Engine] Error processing log: {e}')
            raise
    
    def process_error_batch(
        self,
        events: list[ErrorLogEvent],
        options: Optional[ProcessingOptions] = None,
    ) -> list[Optional[AnalysisResult]]:
        """Process multiple error logs"""
        results = []
        for event in events:
            try:
                result = self.process_error_log(event, options)
                results.append(result)
            except Exception as e:
                print(f'[Engine] Batch processing error: {e}')
                results.append(None)
        
        return results
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        return self.cache.get_stats()
    
    def clear_cache(self) -> None:
        """Clear cache"""
        self.cache.clear_expired()

    def _get_or_create_inflight(self, key: str) -> tuple[Future, bool]:
        with self._inflight_lock:
            existing = self._inflight.get(key)
            if existing is not None:
                return existing, False
            future: Future = Future()
            self._inflight[key] = future
            return future, True

    def _clear_inflight(self, key: str, future: Future) -> None:
        with self._inflight_lock:
            current = self._inflight.get(key)
            if current is future:
                del self._inflight[key]

    def _build_repository_context(self, event: ErrorLogEvent) -> Optional[str]:
        """
        Best-effort repository setup + codebase context collection.

        This is intentionally resilient: missing repo URL, missing file paths, or GitHub API errors
        should not prevent log-only analysis.
        """
        repo_url = (event.repository_url or os.getenv('DEFAULT_REPOSITORY_URL') or '').strip()
        if not repo_url:
            return None

        repo_ref = self._extract_repository_ref(event.error_log.context)
        code_locations = self._extract_code_locations(event.error_log)
        if not code_locations:
            return f"Repository: {repo_url}\nRef: {repo_ref or 'default'}\n(No code locations found in the log/stack trace.)"

        context_lines = int(os.getenv('CODE_CONTEXT_LINES', '20'))
        max_locations = int(os.getenv('MAX_CODE_LOCATIONS', '4'))
        max_chars = int(os.getenv('MAX_REPOSITORY_CONTEXT_CHARS', '12000'))

        parts: list[str] = [f'Repository: {repo_url}', f"Ref: {repo_ref or 'default'}"]

        for file_path, line_number in code_locations[:max_locations]:
            try:
                file_content = self.code_provider.get_file_content(repo_url, file_path, ref=repo_ref)
                snippet = self._extract_snippet(file_content, line_number, context_lines=context_lines)
                lang = self._guess_language(file_path)
                header = f'[Snippet] {file_path}' + (f':{line_number}' if line_number else '')
                parts.append(f'{header}\n```{lang}\n{snippet}\n```')
            except Exception as e:
                parts.append(f'[Snippet] {file_path}' + (f':{line_number}' if line_number else '') + f'\n(Failed to fetch code: {e})')

            if sum(len(p) for p in parts) >= max_chars:
                parts.append('(Repository context truncated due to size limits.)')
                break

        return '\n\n'.join(parts)

    @staticmethod
    def _extract_repository_ref(context: object) -> Optional[str]:
        if not isinstance(context, dict):
            return None

        candidate_keys = [
            'git.commit.sha',
            'git.commit',
            'git.sha',
            'git.revision',
            'vcs.ref.head.revision',
            'vcs.revision',
            'vcs.revision.id',
            'revision',
            'commit',
        ]

        for key in candidate_keys:
            value = context.get(key)
            if not value:
                continue
            if isinstance(value, str) and re.fullmatch(r'(?i)[0-9a-f]{7,40}', value.strip()):
                return value.strip()

        return None

    @classmethod
    def _extract_code_locations(cls, error_log: ErrorLog) -> list[tuple[str, Optional[int]]]:
        max_locations = int(os.getenv('MAX_CODE_LOCATIONS', '4'))

        raw_locations: list[tuple[str, Optional[int]]] = []

        if error_log.file_path:
            raw_locations.append((error_log.file_path, error_log.line_number))

        if error_log.stack_trace:
            raw_locations.extend(cls._extract_locations_from_stack_trace(error_log.stack_trace))

        seen: set[tuple[str, Optional[int]]] = set()
        locations: list[tuple[str, Optional[int]]] = []

        for raw_path, line_number in raw_locations:
            if not raw_path:
                continue

            normalized_path = cls._normalize_repo_file_path(raw_path)
            if not normalized_path:
                continue

            # Skip internal/non-repo frames.
            if normalized_path.startswith('<') or normalized_path.startswith('node:') or normalized_path.startswith('internal/'):
                continue

            key = (normalized_path, line_number)
            if key in seen:
                continue

            seen.add(key)
            locations.append(key)

            if len(locations) >= max_locations:
                break

        return locations

    @staticmethod
    def _extract_locations_from_stack_trace(stack_trace: str) -> list[tuple[str, Optional[int]]]:
        locations: list[tuple[str, Optional[int]]] = []

        # Node/JS style: "... (path/to/file.ts:45:12)" or "at path/to/file.ts:45:12"
        ext = r'(?:py|js|jsx|ts|tsx|java|go|rb|php|cs|c|cc|cpp|h|hpp|rs)'
        patterns = [
            re.compile(rf'\\((?P<path>[^()]+?\\.(?:{ext})):(?P<line>\\d+):(?P<col>\\d+)\\)'),
            re.compile(rf'(?P<path>[^\\s()]+?\\.(?:{ext})):(?P<line>\\d+):(?P<col>\\d+)'),
            re.compile(rf'(?P<path>[^\\s()]+?\\.(?:{ext})):(?P<line>\\d+)'),
            # Python style: File "path", line 123
            re.compile(r'File ["\\\'](?P<path>[^"\\\']+?\\.py)["\\\'], line (?P<line>\\d+)'),
        ]

        for pattern in patterns:
            for m in pattern.finditer(stack_trace):
                path = (m.group('path') or '').strip()
                if not path:
                    continue

                line_str = m.groupdict().get('line')
                line_number = int(line_str) if line_str and line_str.isdigit() else None
                locations.append((path, line_number))

        return locations

    @staticmethod
    def _normalize_repo_file_path(file_path: str) -> str:
        p = file_path.replace('\\', '/').strip()
        p = re.sub(r'^[A-Za-z]:', '', p)  # Windows drive letter

        # Keep the most likely repo-relative suffix for common monorepo layouts.
        roots = ('src', 'lib', 'app', 'apps', 'packages', 'services', 'modules')
        m = re.search(rf'(?:(?:^|/))(?P<root>{"|".join(roots)})/(?P<rest>.+)$', p)
        if m:
            return f"{m.group('root')}/{m.group('rest')}"

        return p.lstrip('/')

    @staticmethod
    def _extract_snippet(file_content: str, line_number: Optional[int], context_lines: int = 20) -> str:
        lines = file_content.splitlines()
        if not lines:
            return ''

        if line_number and 1 <= line_number <= len(lines):
            start = max(1, line_number - context_lines)
            end = min(len(lines), line_number + context_lines)
        else:
            start = 1
            end = min(len(lines), max(40, context_lines * 2 + 1))

        width = len(str(end))
        snippet_lines = [f'{i:>{width}} | {lines[i - 1]}' for i in range(start, end + 1)]
        return '\n'.join(snippet_lines)

    @staticmethod
    def _guess_language(file_path: str) -> str:
        lower = file_path.lower()
        if lower.endswith('.py'):
            return 'python'
        if lower.endswith('.ts') or lower.endswith('.tsx'):
            return 'typescript'
        if lower.endswith('.js') or lower.endswith('.jsx'):
            return 'javascript'
        if lower.endswith('.go'):
            return 'go'
        if lower.endswith('.java'):
            return 'java'
        if lower.endswith('.rb'):
            return 'ruby'
        if lower.endswith('.rs'):
            return 'rust'
        return 'text'
