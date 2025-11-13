"""Structured logging with sensitive data redaction."""

import logging
import json
import re
from typing import Any, Dict
from datetime import datetime
import os

class SensitiveDataFilter(logging.Filter):
    """Filter to redact sensitive information from logs."""
    
    SENSITIVE_PATTERNS = [
        (r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([^"\'}\s]+)', r'\1***REDACTED***'),
        (r'(password["\']?\s*[:=]\s*["\']?)([^"\'}\s]+)', r'\1***REDACTED***'),
        (r'(token["\']?\s*[:=]\s*["\']?)([^"\'}\s]+)', r'\1***REDACTED***'),
        (r'(secret["\']?\s*[:=]\s*["\']?)([^"\'}\s]+)', r'\1***REDACTED***'),
        (r'(authorization:\s*bearer\s+)(\S+)', r'\1***REDACTED***'),
        (r'sk-[a-zA-Z0-9]{20,}', 'sk-***REDACTED***'),  # OpenAI API keys
        (r'(email["\']?\s*[:=]\s*["\']?)([^"\'}\s]+@[^"\'}\s]+)', r'\1***@***.***'),
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive data from log message."""
        if isinstance(record.msg, str):
            for pattern, replacement in self.SENSITIVE_PATTERNS:
                record.msg = re.sub(pattern, replacement, record.msg, flags=re.IGNORECASE)
        
        # Also redact from args if present
        if hasattr(record, 'args') and record.args:
            redacted_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    for pattern, replacement in self.SENSITIVE_PATTERNS:
                        arg = re.sub(pattern, replacement, arg, flags=re.IGNORECASE)
                redacted_args.append(arg)
            record.args = tuple(redacted_args)
        
        return True

class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
        
        # Add custom fields from record
        for key in ['session_id', 'action', 'url', 'selector', 'status', 'duration_ms']:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
        
        return json.dumps(log_data)

def setup_logger(
    name: str = "quash",
    level: str = "INFO",
    log_file: str = None,
    json_format: bool = True
) -> logging.Logger:
    """
    Setup structured logger with sensitive data filtering.
    
    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for logging
        json_format: Whether to use JSON formatting
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    logger.addFilter(SensitiveDataFilter())
    
    # Remove existing handlers to avoid duplicates
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper()))
    
    if json_format:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        # Create logs directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
    
    return logger

# Global logger instance
logger = setup_logger(
    name="quash",
    level=os.getenv("LOG_LEVEL", "INFO"),
    log_file=os.getenv("LOG_FILE", "logs/app.log"),
    json_format=True
)

def log_action(action: str, **kwargs):
    """
    Log a browser action with structured data.
    
    Args:
        action: Action type (navigate, click, type, extract, etc.)
        **kwargs: Additional context (url, selector, status, duration_ms, etc.)
    """
    extra = {'action': action}
    extra.update(kwargs)
    
    status = kwargs.get('status', 'unknown')
    if status == 'success':
        logger.info(f"Action completed: {action}", extra=extra)
    elif status == 'error':
        logger.error(f"Action failed: {action}", extra=extra)
    else:
        logger.debug(f"Action: {action}", extra=extra)

def log_llm_call(provider: str, model: str, tokens: int = None, duration_ms: int = None, **kwargs):
    """
    Log an LLM API call with usage metrics.
    
    Args:
        provider: LLM provider (openai, anthropic, etc.)
        model: Model name
        tokens: Token count if available
        duration_ms: Request duration in milliseconds
        **kwargs: Additional context
    """
    extra = {
        'provider': provider,
        'model': model,
        'tokens': tokens,
        'duration_ms': duration_ms
    }
    extra.update(kwargs)
    
    logger.info(f"LLM call: {provider}/{model}", extra=extra)

