import re
import time
import logging
from threading import Event
from pathlib import Path

logger = logging.getLogger(__name__)


class PipelineCancelledError(Exception):
    """Raised when the pipeline is cancelled."""
    pass


def call_with_retry(
    fn,
    *args,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = (Exception,),
    cancel_event: Event | None = None,
    **kwargs,
):
    """Call fn(*args, **kwargs) with retry + exponential backoff.

    If cancel_event is set during a backoff sleep, raises PipelineCancelledError.
    """
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            if attempt == max_retries:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "[retry] attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt + 1, max_retries, e, delay,
            )
            if cancel_event is not None:
                if cancel_event.wait(timeout=delay):
                    raise PipelineCancelledError("Cancelled during retry wait")
            else:
                time.sleep(delay)
    raise last_exception


def extract_scene_number(tsv_path: Path) -> int:
  m = re.search(r"scene_(\d+)", tsv_path.stem)
  if m:
    return int(m.group(1))
  raise ValueError(f"Cannot extract scene number from {tsv_path.name}")
