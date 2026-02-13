"""
AWS Lambda Handler for Patrol Error Analysis System
Supports OTEL logs from Vector Sink
"""

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Import core modules
from types import ErrorLogEvent, ErrorLog, ProcessingOptions
from engine import ErrorAnalysisEngine
from cache import InMemoryCache
from openai_provider import OpenAILLMProvider
from github_provider import GitHubRepositoryCodeProvider
from otel_parser import OTELLogParser, VectorOTELSinkHandler


# Initialize engine (reused across Lambda invocations)
_engine: Optional[ErrorAnalysisEngine] = None


def get_engine() -> ErrorAnalysisEngine:
    """Get or create error analysis engine"""
    global _engine
    
    if _engine is None:
        try:
            cache_max_size = int(os.getenv('CACHE_MAX_SIZE', '1000'))
            cache_policy = os.getenv('CACHE_EVICTION_POLICY', 'LRU')
            
            cache = InMemoryCache(max_size=cache_max_size, eviction_policy=cache_policy)
            llm = OpenAILLMProvider()
            code_provider = GitHubRepositoryCodeProvider()
            
            _engine = ErrorAnalysisEngine(cache, llm, code_provider)
            print(f'[Lambda] Engine initialized (cache: {cache_max_size}, policy: {cache_policy})')
        except Exception as e:
            print(f'[Lambda] Failed to initialize engine: {e}')
            raise
    
    return _engine


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for error analysis
    
    Supports:
    - OTEL logs from Vector Sink (HTTP POST)
    - SQS events
    - SNS events
    - EventBridge events
    - Direct API calls
    """
    try:
        print(f'[Lambda] Received event: {json.dumps(event, default=str)[:500]}...')
        
        engine = get_engine()
        
        # Parse event based on source
        error_events = _parse_event(event)
        
        if not error_events:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No valid error events found'}),
            }
        
        # Process error events
        results = []
        failed = 0
        
        for error_event in error_events:
            try:
                options = ProcessingOptions(
                    cache_ttl=int(os.getenv('CACHE_TTL', '86400')),
                    skip_cache=False,
                    skip_webhook=False,
                )
                
                result = engine.process_error_log(error_event, options)
                
                if result:
                    results.append({
                        'eventId': error_event.event_id,
                        'errorHash': result.error_hash,
                        'analysis': result.analysis,
                        'rootCause': result.root_cause,
                        'suggestedFix': result.suggested_fix,
                        'confidenceScore': result.confidence_score,
                        'analyzedAt': result.analyzed_at,
                    })
            except Exception as e:
                print(f'[Lambda] Error processing event: {e}')
                failed += 1
        
        # Get cache stats
        cache_stats = engine.get_cache_stats()
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'processed': len(error_events) - failed,
                'failed': failed,
                'results': results,
                'cacheStats': {
                    'hits': cache_stats['hits'],
                    'misses': cache_stats['misses'],
                    'hitRate': cache_stats['hit_rate'],
                    'size': cache_stats['size'],
                    'maxSize': cache_stats['max_size'],
                    'utilizationPercent': cache_stats['utilization_percent'],
                },
            }),
        }
    
    except Exception as e:
        print(f'[Lambda] Handler error: {e}')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
        }


def _parse_event(event: Dict[str, Any]) -> List[ErrorLogEvent]:
    """Parse event from different sources"""
    error_events = []
    
    # OTEL event from Vector Sink (HTTP POST)
    if 'resourceLogs' in event:
        try:
            otel_event = OTELLogParser.parse_otel_log(event)
            if otel_event:
                error_events.append(otel_event)
        except Exception as e:
            print(f'[Lambda] Failed to parse OTEL event: {e}')
        return error_events
    
    # Batch OTEL events
    if 'logs' in event and isinstance(event.get('logs'), (list, dict)):
        try:
            batch_events = VectorOTELSinkHandler.parse_vector_payload(event)
            error_events.extend([e for e in batch_events if e])
        except Exception as e:
            print(f'[Lambda] Failed to parse OTEL batch: {e}')
        return error_events
    
    # SQS event
    if 'Records' in event and event['Records']:
        for record in event['Records']:
            if 'body' in record:
                try:
                    body = json.loads(record['body'])
                    
                    # Check if body contains OTEL log
                    if 'resourceLogs' in body:
                        otel_event = OTELLogParser.parse_otel_log(body)
                        if otel_event:
                            error_events.append(otel_event)
                    else:
                        error_event = _parse_error_event(body)
                        if error_event:
                            error_events.append(error_event)
                except Exception as e:
                    print(f'[Lambda] Failed to parse SQS record: {e}')
    
    # SNS event
    elif 'Records' in event and any('Sns' in r for r in event['Records']):
        for record in event['Records']:
            if 'Sns' in record:
                try:
                    message = json.loads(record['Sns']['Message'])
                    
                    # Check if message contains OTEL log
                    if 'resourceLogs' in message:
                        otel_event = OTELLogParser.parse_otel_log(message)
                        if otel_event:
                            error_events.append(otel_event)
                    else:
                        error_event = _parse_error_event(message)
                        if error_event:
                            error_events.append(error_event)
                except Exception as e:
                    print(f'[Lambda] Failed to parse SNS record: {e}')
    
    # EventBridge event
    elif 'detail' in event:
        try:
            # Check if detail contains OTEL log
            if 'resourceLogs' in event['detail']:
                otel_event = OTELLogParser.parse_otel_log(event['detail'])
                if otel_event:
                    error_events.append(otel_event)
            else:
                error_event = _parse_error_event(event['detail'])
                if error_event:
                    error_events.append(error_event)
        except Exception as e:
            print(f'[Lambda] Failed to parse EventBridge event: {e}')
    
    # Direct API call
    elif 'eventId' in event:
        try:
            error_event = _parse_error_event(event)
            if error_event:
                error_events.append(error_event)
        except Exception as e:
            print(f'[Lambda] Failed to parse direct event: {e}')
    
    return error_events


def _parse_error_event(data: Dict[str, Any]) -> Optional[ErrorLogEvent]:
    """Parse error event from data"""
    try:
        error_log_data = data.get('errorLog', {})
        
        error_log = ErrorLog(
            message=error_log_data.get('message', ''),
            code=error_log_data.get('code'),
            file_path=error_log_data.get('filePath'),
            line_number=error_log_data.get('lineNumber'),
            stack_trace=error_log_data.get('stackTrace'),
            context=error_log_data.get('context'),
        )
        
        return ErrorLogEvent(
            event_id=data.get('eventId', ''),
            timestamp=data.get('timestamp', 0),
            error_log=error_log,
            repository_url=data.get('repositoryUrl'),
            webhook_config_id=data.get('webhookConfigId'),
        )
    except Exception as e:
        print(f'[Lambda] Failed to parse error event: {e}')
        return None


# For local testing
if __name__ == '__main__':
    # Test OTEL event
    otel_event = {
        'resourceLogs': [
            {
                'resource': {
                    'attributes': {
                        'service.name': 'my-service',
                        'service.version': '1.0.0',
                        'git.repository.url': 'https://github.com/your-org/your-repo',
                    }
                },
                'scopeLogs': [
                    {
                        'scope': {
                            'name': 'my-logger',
                            'version': '1.0.0'
                        },
                        'logRecords': [
                            {
                                'timeUnixNano': str(int(time.time() * 1e9)),
                                'severityNumber': 17,
                                'severityText': 'ERROR',
                                'body': {
                                    'stringValue': 'TypeError: Cannot read property of undefined'
                                },
                                'attributes': {
                                    'exception.type': 'TypeError',
                                    'exception.message': 'Cannot read property of undefined',
                                    'exception.stacktrace': 'at getUserById (src/handlers/user.ts:45:15)',
                                    'code.filepath': 'src/handlers/user.ts',
                                    'code.lineno': 45,
                                },
                                'traceId': 'abc123def456',
                                'spanId': 'def456ghi789',
                            }
                        ]
                    }
                ]
            }
        ]
    }
    
    result = handler(otel_event, None)
    print(json.dumps(result, indent=2))
