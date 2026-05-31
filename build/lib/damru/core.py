"""Damru - sync context manager for stealth Android browser automation.

Usage:
    from damru import Damru

    with Damru(device="pixel_8_pro", proxy="socks5://host:port") as browser:
        page = browser.new_page()
        page.goto("https://example.com")
        print(page.title())
"""
from __future__ import annotations

import asyncio
from typing import Optional

from playwright.sync_api import BrowserContext

from .async_core import AsyncDamru


class Damru:
    """Sync wrapper around AsyncDamru.

    Provides a synchronous context manager that runs the async pipeline
    in an event loop.

    Args:
        device: Device name, model, or "random". None = random.
        serial: ADB serial (auto-detect if None).
        proxy: SOCKS5 proxy URL (e.g. "socks5://host:port").
        timezone: IANA timezone (auto from proxy if None).
        locale: BCP-47 locale (auto from timezone if None).
        chrome_package: Chrome APK package name (auto-detect if None).
        restore_props: Whether to restore original system props on exit.
        debug: Enable debug logging.
    """

    def __init__(
        self,
        device: Optional[str] = None,
        serial: Optional[str] = None,
        proxy: Optional[str] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
        chrome_package: Optional[str] = None,
        restore_props: bool = True,
        debug: bool = False,
    ):
        self._async_damru = AsyncDamru(
            device=device,
            serial=serial,
            proxy=proxy,
            timezone=timezone,
            locale=locale,
            chrome_package=chrome_package,
            restore_props=restore_props,
            debug=debug,
        )
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._context: Optional[BrowserContext] = None

    def __enter__(self) -> BrowserContext:
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        if self._loop and self._loop.is_running():
            # We're inside an existing event loop (e.g., Jupyter)
            # Use nest_asyncio or create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                self._context = pool.submit(
                    lambda: asyncio.run(self._async_damru.__aenter__())
                ).result()
        else:
            self._context = asyncio.run(self._async_damru.__aenter__())

        return self._context  # type: ignore[return-value]

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(
                    lambda: asyncio.run(
                        self._async_damru.__aexit__(exc_type, exc_val, exc_tb)
                    )
                ).result()
        else:
            asyncio.run(self._async_damru.__aexit__(exc_type, exc_val, exc_tb))
