"""
Unit tests for Patrol error analysis engine
"""

import unittest
import time
import threading
from patrol_types import ErrorLog, ErrorLogEvent, ProcessingOptions
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
        from patrol_types import AnalysisResult
        
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
        from patrol_types import AnalysisResult
        
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
        from patrol_types import AnalysisResult
        
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
        from patrol_types import AnalysisResult
        
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


class TestInFlightDedupe(unittest.TestCase):
    def test_concurrent_same_error_is_analyzed_once_per_process(self):
        from patrol_types import AnalysisResult

        class DummyLLM:
            def __init__(self):
                self.calls = 0

            def analyze_error(self, error_hash, error_log, repository_context=None):
                self.calls += 1
                time.sleep(0.2)  # ensure overlap for the second thread
                return AnalysisResult(
                    error_hash=error_hash,
                    analysis='{\"rootCause\":\"x\",\"suggestedFix\":\"y\",\"confidenceScore\":75,\"analysis\":\"z\"}',
                    confidence_score=75,
                )

        cache = InMemoryCache(max_size=10)
        llm = DummyLLM()
        engine = ErrorAnalysisEngine(cache=cache, llm_provider=llm)

        event = ErrorLogEvent(
            event_id='e-1',
            timestamp=0,
            error_log=ErrorLog(
                message='TypeError: boom',
                file_path='src/a.ts',
                line_number=10,
                stack_trace='at fn (src/a.ts:10:2)',
            ),
            repository_url=None,
        )

        barrier = threading.Barrier(2)
        results = []
        errors = []

        def worker():
            try:
                barrier.wait()
                results.append(engine.process_error_log(event))
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(llm.calls, 1)
        self.assertEqual(results[0].error_hash, results[1].error_hash)


if __name__ == '__main__':
    unittest.main()
