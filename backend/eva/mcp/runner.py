from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine to completion whether or not an event loop is already
    running in the current thread (e.g. FastAPI request handlers)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()
