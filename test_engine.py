"""
Unit tests for Patrol error analysis engine
"""

import unittest
import time
from types import ErrorLog, ErrorLogEvent, ProcessingOptions
from hashing import hash_error_log, normalize_error_log
from cache import InMemoryCache
from engine import ErrorAnalysisEngine


class TestHashing(unittest.TestCase):
    """Test error hashing"""
    
    def test_normalize_error_log(self):
        """Test error log normalization"""
        error = ErrorLog(
            message="TypeError: Cannot read property 'foo' of undefined",
            code='ERR_UNDEFINED',
            file_path='/home/user/project/src/handler.ts',
            line_number=45,
        )
        
        normalized = normalize_error_log(error)
        
        self.assertIsNotNone(normalized.error_message)
        self.assertEqual(normalized.error_code, 'ERR_UNDEFINED')
        self.assertIn('handler.ts', normalized.file_path)
    
    def test_hash_consistency(self):
        """Test hash consistency"""
        error = ErrorLog(
            message='TypeError: Cannot read property of undefined',
            file_path='src/handler.ts',
        )
        
        hash1, _ = hash_error_log(error)
        hash2, _ = hash_error_log(error)
        
        self.assertEqual(hash1, hash2, 'Same error should produce same hash')
    
    def test_hash_uniqueness(self):
        """Test hash uniqueness"""
        error1 = ErrorLog(message='Error A', file_path='file1.ts')
        error2 = ErrorLog(message='Error B', file_path='file2.ts')
        
        hash1, _ = hash_error_log(error1)
        hash2, _ = hash_error_log(error2)
        
        self.assertNotEqual(hash1, hash2, 'Different errors should produce different hashes')


class TestCache(unittest.TestCase):
    """Test cache functionality"""
    
    def setUp(self):
        self.cache = InMemoryCache(max_size=3, eviction_policy='LRU')
    
    def test_cache_set_get(self):
        """Test cache set and get"""
        from types import AnalysisResult
        
        result = AnalysisResult(
            error_hash='test-hash',
            analysis='Test analysis',
            confidence_score=85,
        )
        
        self.cache.set('key1', result)
        retrieved = self.cache.get('key1')
        
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.error_hash, 'test-hash')
    
    def test_cache_miss(self):
        """Test cache miss"""
        result = self.cache.get('nonexistent')
        self.assertIsNone(result)
    
    def test_cache_expiration(self):
        """Test cache expiration"""
        from types import AnalysisResult
        
        result = AnalysisResult(
            error_hash='test-hash',
            analysis='Test',
            confidence_score=75,
        )
        
        self.cache.set('key1', result, ttl=1)
        time.sleep(1.1)
        
        retrieved = self.cache.get('key1')
        self.assertIsNone(retrieved, 'Expired entry should return None')
    
    def test_cache_eviction_lru(self):
        """Test LRU eviction"""
        from types import AnalysisResult
        
        for i in range(5):
            result = AnalysisResult(
                error_hash=f'hash-{i}',
                analysis=f'Analysis {i}',
                confidence_score=75,
            )
            self.cache.set(f'key{i}', result)
        
        # Cache should evict oldest entries
        self.assertLessEqual(len(self.cache.cache), self.cache.max_size)
    
    def test_cache_stats(self):
        """Test cache statistics"""
        from types import AnalysisResult
        
        result = AnalysisResult(
            error_hash='test-hash',
            analysis='Test',
            confidence_score=75,
        )
        
        self.cache.set('key1', result)
        self.cache.get('key1')  # Hit
        self.cache.get('key2')  # Miss
        
        stats = self.cache.get_stats()
        
        self.assertEqual(stats['hits'], 1)
        self.assertEqual(stats['misses'], 1)
        self.assertGreater(stats['hit_rate'], 0)


class TestEngine(unittest.TestCase):
    """Test error analysis engine"""
    
    def setUp(self):
        self.cache = InMemoryCache(max_size=10)
        self.engine = ErrorAnalysisEngine(cache=self.cache)
    
    def test_engine_initialization(self):
        """Test engine initialization"""
        self.assertIsNotNone(self.engine.cache)
        self.assertIsNotNone(self.engine.llm_provider)
        self.assertIsNotNone(self.engine.code_provider)
    
    def test_cache_stats(self):
        """Test cache statistics retrieval"""
        stats = self.engine.get_cache_stats()
        
        self.assertIn('hits', stats)
        self.assertIn('misses', stats)
        self.assertIn('size', stats)
        self.assertIn('max_size', stats)


if __name__ == '__main__':
    unittest.main()
