"""
Type definitions for Patrol error analysis system
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ErrorLog:
    """Error log information"""
    message: str
    code: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class ErrorLogEvent:
    """Error log event from sink"""
    event_id: str
    timestamp: int
    error_log: ErrorLog
    repository_url: Optional[str] = None
    webhook_config_id: Optional[int] = None


@dataclass
class NormalizedErrorLog:
    """Normalized error log for analysis"""
    error_hash: str
    error_message: str
    error_code: Optional[str]
    file_path: Optional[str]
    line_number: Optional[int]
    stack_trace: Optional[str]
    context: Optional[str]


@dataclass
class AnalysisResult:
    """Error analysis result"""
    error_hash: str
    analysis: str
    root_cause: Optional[str] = None
    suggested_fix: Optional[str] = None
    confidence_score: int = 75
    analyzed_at: int = 0
    ttl: int = 86400
    expires_at: int = 0


@dataclass
class ProcessingOptions:
    """Options for error log processing"""
    cache_ttl: int = 86400
    skip_cache: bool = False
    skip_webhook: bool = False
