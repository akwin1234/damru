"""Utility helpers for damru."""
from __future__ import annotations

import asyncio
import functools
import logging
import socket
from typing import Any, Callable, TypeVar

logger = logging.getLogger("damru")

T = TypeVar("T")


def find_free_port() -> int:
    """Find a free local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def async_retry(
    retries: int = 3,
    delay: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator that retries an async function on failure."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_err: Exception | None = None
            for attempt in range(retries):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as e:
                    last_err = e
                    if attempt < retries - 1:
                        await asyncio.sleep(delay)
            raise last_err  # type: ignore[misc]
        return wrapper
    return decorator


async def sleep(seconds: float) -> None:
    """Async sleep wrapper."""
    await asyncio.sleep(seconds)


def setup_logging(debug: bool = False) -> None:
    """Configure damru logging."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="[damru] %(levelname)s %(message)s",
    )
    logger.setLevel(level)
