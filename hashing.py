"""
Error log hashing and normalization
"""

import hashlib
import re
from typing import Optional
from patrol_types import NormalizedErrorLog, ErrorLog


def normalize_error_log(error_log: ErrorLog) -> NormalizedErrorLog:
    """
    Normalize error log for consistent hashing
    """
    # Normalize file path (remove absolute paths, normalize separators)
    file_path = error_log.file_path
    if file_path:
        file_path = file_path.replace('\\', '/')
        file_path = re.sub(r'^.*/(src|lib|app)/', '', file_path)
    
    # Normalize stack trace (remove line numbers, timestamps)
    stack_trace = error_log.stack_trace
    if stack_trace:
        stack_trace = re.sub(r':\d+:\d+', ':X:X', stack_trace)
        stack_trace = re.sub(r'at \d+ms', 'at Xms', stack_trace)
    
    # Normalize error message (remove variable values)
    message = error_log.message
    message = re.sub(r"'[^']*'", "'X'", message)
    message = re.sub(r'"[^"]*"', '"X"', message)
    message = re.sub(r'\d+', 'N', message)
    
    # Normalize context
    context_str = None
    if error_log.context:
        try:
            import json
            context_str = json.dumps(error_log.context, sort_keys=True)
        except:
            context_str = str(error_log.context)
    
    return NormalizedErrorLog(
        error_hash='',  # Will be set by generate_error_hash
        error_message=message,
        error_code=error_log.code,
        file_path=file_path,
        line_number=error_log.line_number,
        stack_trace=stack_trace,
        context=context_str
    )


def generate_error_hash(normalized_error: NormalizedErrorLog) -> str:
    """
    Generate SHA-256 hash for error fingerprinting
    """
    # Create fingerprint from normalized error components
    fingerprint_parts = [
        normalized_error.error_message,
        normalized_error.error_code or '',
        normalized_error.file_path or '',
        normalized_error.stack_trace or '',
    ]
    
    fingerprint = '|'.join(fingerprint_parts)
    error_hash = hashlib.sha256(fingerprint.encode()).hexdigest()
    
    return error_hash


def hash_error_log(error_log: ErrorLog) -> tuple[str, NormalizedErrorLog]:
    """
    Normalize and hash error log
    Returns: (error_hash, normalized_error)
    """
    normalized = normalize_error_log(error_log)
    error_hash = generate_error_hash(normalized)
    normalized.error_hash = error_hash
    
    return error_hash, normalized


def is_similar_error(hash1: str, hash2: str, threshold: float = 0.9) -> bool:
    """
    Check if two error hashes are similar
    """
    # For exact matching, we use direct hash comparison
    # For similarity, we could implement Levenshtein distance
    return hash1 == hash2
