"""Retry utilities with exponential backoff for handling transient failures."""

import asyncio
import time
from typing import Callable, Any, TypeVar, Optional
from functools import wraps
from app.core.logger import logger

T = TypeVar('T')

class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number with exponential backoff."""
        import random
        
        delay = min(
            self.initial_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        if self.jitter:
            # Add random jitter (±25% of delay)
            delay = delay * (0.75 + random.random() * 0.5)
        
        return delay

def retry_async(
    config: Optional[RetryConfig] = None,
    retryable_exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Decorator for async functions to add retry logic with exponential backoff.
    
    Args:
        config: Retry configuration (defaults to RetryConfig())
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Optional callback function called on each retry attempt
    
    Example:
        @retry_async(RetryConfig(max_retries=5))
        async def fetch_data():
            # Your code here
            pass
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(config.max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    
                    # Log success if this wasn't the first attempt
                    if attempt > 0:
                        logger.info(
                            f"Retry successful for {func.__name__} on attempt {attempt + 1}",
                            extra={'function': func.__name__, 'attempt': attempt + 1}
                        )
                    
                    return result
                    
                except retryable_exceptions as e:
                    last_exception = e
                    
                    # Don't retry if we've exhausted attempts
                    if attempt >= config.max_retries:
                        logger.error(
                            f"All retry attempts exhausted for {func.__name__}",
                            extra={
                                'function': func.__name__,
                                'attempts': attempt + 1,
                                'error': str(e)
                            }
                        )
                        break
                    
                    delay = config.calculate_delay(attempt)
                    
                    logger.warning(
                        f"Retry attempt {attempt + 1}/{config.max_retries} for {func.__name__} after {delay:.2f}s",
                        extra={
                            'function': func.__name__,
                            'attempt': attempt + 1,
                            'delay_seconds': delay,
                            'error': str(e)
                        }
                    )
                    
                    # Call retry callback if provided
                    if on_retry:
                        try:
                            await on_retry(attempt, e)
                        except Exception as callback_error:
                            logger.error(f"Error in retry callback: {callback_error}")
                    
                    # Wait before retrying
                    await asyncio.sleep(delay)
            
            # If we get here, all retries failed
            raise last_exception
        
        return wrapper
    return decorator

async def retry_with_timeout(
    func: Callable,
    timeout: float,
    retry_config: Optional[RetryConfig] = None,
    *args,
    **kwargs
) -> Any:
    """
    Execute an async function with both timeout and retry logic.
    
    Args:
        func: Async function to execute
        timeout: Timeout in seconds
        retry_config: Retry configuration
        *args, **kwargs: Arguments to pass to func
    
    Returns:
        Result from successful execution
    
    Raises:
        TimeoutError: If execution exceeds timeout
        Exception: If all retries fail
    """
    if retry_config is None:
        retry_config = RetryConfig()
    
    @retry_async(config=retry_config)
    async def _execute_with_timeout():
        try:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout ({timeout}s) exceeded for {func.__name__}")
            raise TimeoutError(f"Operation timed out after {timeout}s")
    
    return await _execute_with_timeout()

class CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail immediately
    - HALF_OPEN: Testing if service recovered
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable) -> Callable:
        """Decorator to protect a function with circuit breaker."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info(f"Circuit breaker for {func.__name__} entering HALF_OPEN state")
                else:
                    raise Exception(f"Circuit breaker OPEN for {func.__name__}")
            
            try:
                result = await func(*args, **kwargs)
                
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                    logger.info(f"Circuit breaker for {func.__name__} CLOSED (recovered)")
                
                return result
                
            except self.expected_exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.error(
                        f"Circuit breaker OPEN for {func.__name__} after {self.failure_count} failures",
                        extra={'failures': self.failure_count}
                    )
                
                raise e
        
        return wrapper

