"""CDP connection over ADB port forwarding for damru.

Connects to Chrome on Android via Chrome DevTools Protocol by forwarding
the device's chrome_devtools_remote Unix socket to a local TCP port,
then using Playwright's connect_over_cdp().
"""
from __future__ import annotations

from typing import Optional

from playwright.async_api import Browser, BrowserContext, async_playwright

from .adb import ADB
from .utils import async_retry, find_free_port, logger, sleep


class CDPError(Exception):
    """CDP connection failed."""


class CDPConnection:
    """Manage CDP connection to Chrome on Android over ADB port forwarding."""

    def __init__(self, adb: ADB):
        self.adb = adb
        self._local_port: Optional[int] = None
        self._browser: Optional[Browser] = None
        self._pw_instance = None

    async def setup_port_forward(self, local_port: Optional[int] = None) -> int:
        """Forward a local TCP port to chrome_devtools_remote.

        Auto-selects a free port if local_port is None.
        """
        # Remove any existing forward on this port
        if self._local_port:
            await self.adb.remove_forward(self._local_port)

        port = local_port or find_free_port()
        await self.adb.remove_forward(port)
        await sleep(0.2)
        await self.adb.forward(port, "localabstract:chrome_devtools_remote")
        self._local_port = port
        logger.debug("Port forward: localhost:%d -> chrome_devtools_remote", port)
        return port

    @async_retry(retries=3, delay=2.0)
    async def _try_connect(self, port: int) -> Browser:
        """Attempt CDP connection with retry."""
        pw = await async_playwright().start()
        self._pw_instance = pw
        browser = await pw.chromium.connect_over_cdp(
            f"http://127.0.0.1:{port}",
            timeout=10000,
        )
        return browser

    async def connect(self) -> BrowserContext:
        """Connect to Chrome via CDP and return the browser context.

        Returns the existing browser context (Chrome on Android always has one).
        """
        if not self._local_port:
            raise CDPError("Port forward not set up. Call setup_port_forward() first.")

        logger.info("Connecting via CDP on port %d...", self._local_port)
        self._browser = await self._try_connect(self._local_port)

        contexts = self._browser.contexts
        if contexts:
            ctx = contexts[0]
        else:
            ctx = await self._browser.new_context()

        logger.info("CDP connected! Context has %d pages.", len(ctx.pages))
        return ctx

    async def disconnect(self) -> None:
        """Close browser connection and remove port forward."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._pw_instance:
            try:
                await self._pw_instance.stop()
            except Exception:
                pass
            self._pw_instance = None

        if self._local_port:
            await self.adb.remove_forward(self._local_port)
            self._local_port = None
