"""
Error Analysis Engine - Core logic for error analysis
"""

import time
from typing import Optional
from types import (
    ErrorLogEvent,
    AnalysisResult,
    ProcessingOptions,
    NormalizedErrorLog,
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
    
    def process_error_log(
        self,
        event: ErrorLogEvent,
        options: Optional[ProcessingOptions] = None,
    ) -> Optional[AnalysisResult]:
        """
        Process error log event
        
        Returns None if error is duplicate (cached)
        """
        options = options or ProcessingOptions()
        
        try:
            # Hash and normalize error
            error_hash, normalized_error = hash_error_log(event.error_log)
            cache_key = f'analysis:{error_hash}'
            
            print(f'[Engine] Processing error: {event.event_id} (hash: {error_hash[:8]}...)')
            
            # Check cache (unless skipped)
            if not options.skip_cache:
                cached_result = self.cache.get(cache_key)
                if cached_result:
                    print(f'[Engine] Cache hit for {error_hash[:8]}...')
                    return cached_result
            
            # Get repository code if available
            repository_code = None
            if event.repository_url:
                try:
                    # Try to get code from the file mentioned in the error
                    if event.error_log.file_path:
                        repository_code = self.code_provider.get_file_content(
                            event.repository_url,
                            event.error_log.file_path
                        )
                except Exception as e:
                    print(f'[Engine] Failed to get repository code: {e}')
            
            # Analyze error using LLM
            print(f'[Engine] Analyzing error with LLM...')
            analysis_result = self.llm_provider.analyze_error(
                normalized_error,
                repository_code
            )
            
            # Cache the result
            self.cache.set(cache_key, analysis_result, ttl=options.cache_ttl)
            
            print(f'[Engine] Analysis complete (confidence: {analysis_result.confidence_score}%)')
            
            return analysis_result
        
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
