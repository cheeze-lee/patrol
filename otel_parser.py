"""
OpenTelemetry Log Parser
Parses OTEL logs from Vector Sink and converts to Patrol format
"""

from typing import Optional, Dict, Any, List
from patrol_types import ErrorLog, ErrorLogEvent
import json
import time


class OTELLogParser:
    """Parse OpenTelemetry logs from Vector"""
    
    @staticmethod
    def parse_otel_log(otel_log: Dict[str, Any]) -> Optional[ErrorLogEvent]:
        """
        Parse OTEL log record to ErrorLogEvent
        
        OTEL Log Record structure:
        {
          "resourceLogs": [
            {
              "resource": {
                "attributes": {
                  "service.name": "my-service",
                  "service.version": "1.0.0"
                }
              },
              "scopeLogs": [
                {
                  "scope": {
                    "name": "my-logger",
                    "version": "1.0.0"
                  },
                  "logRecords": [
                    {
                      "timeUnixNano": "1707817200000000000",
                      "severityNumber": 17,
                      "severityText": "ERROR",
                      "body": {
                        "stringValue": "TypeError: Cannot read property of undefined"
                      },
                      "attributes": {
                        "exception.type": "TypeError",
                        "exception.message": "Cannot read property of undefined",
                        "exception.stacktrace": "at getUserById (src/handlers/user.ts:45:15)",
                        "code.filepath": "src/handlers/user.ts",
                        "code.lineno": 45
                      },
                      "traceId": "abc123...",
                      "spanId": "def456..."
                    }
                  ]
                }
              ]
            }
          ]
        }
        """
        try:
            # Extract resource logs
            resource_logs = otel_log.get('resourceLogs', [])
            if not resource_logs:
                return None
            
            resource = resource_logs[0].get('resource', {})
            resource_attrs = resource.get('attributes', {})
            
            # Extract scope logs
            scope_logs = resource_logs[0].get('scopeLogs', [])
            if not scope_logs:
                return None
            
            log_records = scope_logs[0].get('logRecords', [])
            if not log_records:
                return None
            
            # Parse first log record
            log_record = log_records[0]
            
            # Extract error information
            error_log = OTELLogParser._extract_error_log(log_record, resource_attrs)
            
            # Generate event ID
            trace_id = log_record.get('traceId', '')
            span_id = log_record.get('spanId', '')
            event_id = f"{trace_id}-{span_id}" if trace_id and span_id else f"otel-{int(time.time() * 1000)}"
            
            # Extract timestamp
            time_unix_nano_raw = log_record.get('timeUnixNano', 0)
            try:
                time_unix_nano = int(time_unix_nano_raw)
                timestamp = int(time_unix_nano / 1000000)  # Convert nanoseconds to milliseconds
            except (TypeError, ValueError):
                timestamp = int(time.time() * 1000)
            
            # Extract repository URL from resource attributes
            repository_url = (
                resource_attrs.get('git.repository.url')
                or resource_attrs.get('vcs.repository.url')
                or resource_attrs.get('repository.url')
            )
            
            return ErrorLogEvent(
                event_id=event_id,
                timestamp=timestamp,
                error_log=error_log,
                repository_url=repository_url,
            )
        
        except Exception as e:
            print(f'[OTEL Parser] Failed to parse OTEL log: {e}')
            return None
    
    @staticmethod
    def _extract_error_log(log_record: Dict[str, Any], resource_attrs: Dict[str, Any]) -> ErrorLog:
        """Extract error log from OTEL log record"""
        
        # Extract message from body
        body = log_record.get('body', {})
        message = ''
        
        if isinstance(body, dict):
            message = body.get('stringValue', '')
        elif isinstance(body, str):
            message = body
        
        # Extract attributes
        attributes = log_record.get('attributes', {})
        
        # Extract exception information
        exception_type = attributes.get('exception.type')
        exception_message = attributes.get('exception.message')
        exception_stacktrace = attributes.get('exception.stacktrace')
        
        # Combine message
        if exception_type and exception_message:
            message = f"{exception_type}: {exception_message}"
        elif exception_message:
            message = exception_message
        
        # Extract code location
        file_path = attributes.get('code.filepath')
        line_number_raw = attributes.get('code.lineno')
        try:
            line_number = int(line_number_raw) if line_number_raw is not None else None
        except (TypeError, ValueError):
            line_number = None
        
        # Extract context (all other attributes)
        context = {
            k: v for k, v in attributes.items()
            if not k.startswith('exception.') and not k.startswith('code.')
        }
        
        # Add resource attributes to context
        context['service.name'] = resource_attrs.get('service.name')
        context['service.version'] = resource_attrs.get('service.version')
        # Include repo/revision hints if present (useful for fetching correct code revision).
        for k in (
            'git.repository.url',
            'git.commit.sha',
            'git.sha',
            'vcs.repository.url',
            'vcs.ref.head.name',
            'vcs.ref.head.revision',
        ):
            if resource_attrs.get(k) is not None:
                context[k] = resource_attrs.get(k)
        
        return ErrorLog(
            message=message or 'Unknown error',
            code=exception_type,
            file_path=file_path,
            line_number=line_number,
            stack_trace=exception_stacktrace,
            context=context if context else None,
        )
    
    @staticmethod
    def parse_otel_batch(otel_logs: List[Dict[str, Any]]) -> List[Optional[ErrorLogEvent]]:
        """Parse batch of OTEL logs"""
        events = []
        for otel_log in otel_logs:
            event = OTELLogParser.parse_otel_log(otel_log)
            if event:
                events.append(event)
        return events


class VectorOTELSinkHandler:
    """Handler for Vector OTEL Sink"""
    
    @staticmethod
    def parse_vector_payload(payload: Dict[str, Any]) -> List[Optional[ErrorLogEvent]]:
        """
        Parse Vector OTEL Sink payload
        
        Vector sends OTEL logs in batch format:
        {
          "logs": [
            { OTEL log record },
            { OTEL log record },
            ...
          ]
        }
        """
        logs = payload.get('logs', [])
        
        if not logs:
            return []
        
        # If single OTEL log
        if isinstance(logs, dict):
            event = OTELLogParser.parse_otel_log(logs)
            return [event] if event else []
        
        # If batch of OTEL logs
        if isinstance(logs, list):
            return OTELLogParser.parse_otel_batch(logs)
        
        return []
    
    @staticmethod
    def parse_vector_json_array(json_str: str) -> List[Optional[ErrorLogEvent]]:
        """Parse Vector JSON array payload"""
        try:
            data = json.loads(json_str)
            return VectorOTELSinkHandler.parse_vector_payload(data)
        except Exception as e:
            print(f'[Vector Handler] Failed to parse JSON: {e}')
            return []
