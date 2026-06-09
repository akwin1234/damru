"""CDP connection over ADB port forwarding for damru.

Connects to Chrome on Android via Chrome DevTools Protocol by forwarding
the device's chrome_devtools_remote Unix socket to a local TCP port,
then using Playwright's connect_over_cdp().
"""
from __future__ import annotations

import asyncio
from urllib.error import URLError
from urllib.request import urlopen
from typing import Optional

from playwright.async_api import Browser, BrowserContext, async_playwright

from .adb import ADB
from .utils import find_free_port, logger, sleep


class CDPError(Exception):
    """CDP connection failed."""


class CDPConnection:
    """Manage CDP connection to Chrome on Android over ADB port forwarding."""

    def __init__(self, adb: ADB, remote_socket: str = "chrome_devtools_remote"):
        self.adb = adb
        self.remote_socket = remote_socket
        self._local_port: Optional[int] = None
        self._browser: Optional[Browser] = None
        self._pw_instance = None

    async def setup_port_forward(self, local_port: Optional[int] = None) -> int:
        """Forward a local TCP port to the browser DevTools socket.

        Auto-selects a free port if local_port is None.
        """
        # Remove any existing forward on this port
        if self._local_port:
            await self.adb.remove_forward(self._local_port)

        port = local_port or find_free_port()
        await self.adb.remove_forward(port)
        await sleep(0.2)
        await self.adb.forward(port, f"localabstract:{self.remote_socket}")
        self._local_port = port
        logger.debug("Port forward: localhost:%d -> %s", port, self.remote_socket)
        return port

    async def _endpoint_ready(self, port: int) -> bool:
        """Return True when Chrome's DevTools HTTP endpoint responds."""
        def _probe() -> bool:
            try:
                with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
                    return resp.status == 200 and b"webSocketDebuggerUrl" in resp.read(4096)
            except (OSError, URLError):
                return False

        return await asyncio.to_thread(_probe)

    async def _try_connect(self, port: int) -> Browser:
        """Attempt CDP connection with retry.

        Chrome on Android can create chrome_devtools_remote before the HTTP/CDP
        endpoint is fully ready. That shows up as intermittent socket hangups
        during concurrent pool cold starts, so probe the endpoint first and
        cleanly tear down failed Playwright instances before retrying.
        """
        last_err: Exception | None = None
        for attempt in range(8):
            if not await self._endpoint_ready(port):
                await sleep(1.5)
                continue

            pw = await async_playwright().start()
            try:
                browser = await pw.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}",
                    timeout=15000,
                )
                self._pw_instance = pw
                return browser
            except Exception as exc:
                last_err = exc
                try:
                    await pw.stop()
                except Exception:
                    pass
                await sleep(2.0 + attempt)

        if last_err:
            raise last_err
        raise CDPError(f"Chrome DevTools endpoint did not become ready on port {port}")

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
