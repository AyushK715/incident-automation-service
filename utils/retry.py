import time
import logging
import functools

logger = logging.getLogger(__name__)

def retry_on_exception(
    max_attempts=3,
    delay_seconds=2.0,
    backoff_factor=2.0,
    exceptions=(Exception,),
):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay  = delay_seconds
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt < max_attempts:
                        logger.warning(
                            "Attempt %s/%s failed for '%s': %s. Retrying in %.1fs...",
                            attempt, max_attempts, func.__name__, str(exc), current_delay,
                            extra={"attempt": attempt, "delay": current_delay}
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(
                            "All %s attempts failed for '%s': %s",
                            max_attempts, func.__name__, str(exc),
                            extra={"attempt": attempt}
                        )
            raise last_exception

        return wrapper
    return decorator
