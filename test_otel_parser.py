"""
Unit tests for OTEL parser
"""

import unittest
import time
from otel_parser import OTELLogParser, VectorOTELSinkHandler


class TestOTELParser(unittest.TestCase):
    """Test OTEL log parsing"""
    
    def setUp(self):
        """Setup test OTEL log"""
        self.otel_log = {
            'resourceLogs': [
                {
                    'resource': {
                        'attributes': {
                            'service.name': 'test-service',
                            'service.version': '1.0.0',
                            'git.repository.url': 'https://github.com/test/repo',
                        }
                    },
                    'scopeLogs': [
                        {
                            'scope': {
                                'name': 'test-logger',
                                'version': '1.0.0'
                            },
                            'logRecords': [
                                {
                                    'timeUnixNano': str(int(time.time() * 1e9)),
                                    'severityNumber': 17,
                                    'severityText': 'ERROR',
                                    'body': {
                                        'stringValue': 'Test error message'
                                    },
                                    'attributes': {
                                        'exception.type': 'TypeError',
                                        'exception.message': 'Cannot read property',
                                        'exception.stacktrace': 'at test.ts:10:5',
                                        'code.filepath': 'src/test.ts',
                                        'code.lineno': 10,
                                    },
                                    'traceId': 'abc123',
                                    'spanId': 'def456',
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    
    def test_parse_otel_log(self):
        """Test parsing OTEL log"""
        event = OTELLogParser.parse_otel_log(self.otel_log)
        
        self.assertIsNotNone(event)
        self.assertEqual(event.event_id, 'abc123-def456')
        self.assertEqual(event.error_log.message, 'TypeError: Cannot read property')
        self.assertEqual(event.error_log.code, 'TypeError')
        self.assertEqual(event.error_log.file_path, 'src/test.ts')
        self.assertEqual(event.error_log.line_number, 10)
        self.assertEqual(event.repository_url, 'https://github.com/test/repo')
    
    def test_parse_otel_batch(self):
        """Test parsing batch of OTEL logs"""
        logs = [self.otel_log, self.otel_log]
        events = OTELLogParser.parse_otel_batch(logs)
        
        self.assertEqual(len(events), 2)
        for event in events:
            self.assertIsNotNone(event)
    
    def test_parse_vector_payload(self):
        """Test parsing Vector payload"""
        payload = {
            'logs': [self.otel_log]
        }
        
        events = VectorOTELSinkHandler.parse_vector_payload(payload)
        
        self.assertEqual(len(events), 1)
        self.assertIsNotNone(events[0])
    
    def test_parse_empty_logs(self):
        """Test parsing empty logs"""
        payload = {'logs': []}
        events = VectorOTELSinkHandler.parse_vector_payload(payload)
        
        self.assertEqual(len(events), 0)
    
    def test_parse_invalid_otel_log(self):
        """Test parsing invalid OTEL log"""
        invalid_log = {'invalid': 'data'}
        event = OTELLogParser.parse_otel_log(invalid_log)
        
        self.assertIsNone(event)


if __name__ == '__main__':
    unittest.main()
