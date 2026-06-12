"""DamruPool - multi-device worker pool for concurrent stealth automation.

Two modes:
  Manual: Use existing ADB devices (MuMu instances, phones).
  Auto:   Spin up redroid Docker containers (WSL2 on Windows, native on Linux).
  MuMu:   Auto-manage MuMu instances via MuMuManager.exe on Windows.

Containers/emulators are REUSED - only Chrome is recycled per session
(stop -> clear cache -> change fingerprint via root -> restart Chrome).

Both async (DamruPool) and sync (DamruPoolSync) APIs provided.
DamruPoolSync is thread-safe for use with ThreadPoolExecutor.
"""
from __future__ import annotations

import asyncio
import math
import random
import sys
import threading
from contextlib import asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from .adb import ADB
from .async_core import AsyncDamru, DamruError
from .root import RootOps
from .utils import logger, setup_logging

# Sentinel to distinguish "not provided" from explicit None
_UNSET = object()


@dataclass
class DeviceSlot:
    """One ADB device/container in the pool."""

    serial: str  # "emulator-5556" or "127.0.0.1:5600"
    index: int  # slot index (for proxy round-robin)
    busy: bool = False
    container_index: Optional[int] = None  # for auto mode cleanup
    healthy: bool = True
    consecutive_failures: int = 0
    sessions_served: int = 0
    restart_count: int = 0
    last_error: Optional[str] = None
    chrome_apk_path: Optional[str] = None  # per-slot APK version directory


class DamruPool:
    """Async multi-device pool with unique fingerprint per session.

    Each session() call:
      1. Acquires a free device slot
      2. Creates AsyncDamru with random device profile
      3. Applies fingerprint via root (resetprop, GPU, screen, etc.)
      4. Launches Chrome with fresh data + CDP connection
      5. Yields BrowserContext
      6. On exit: stops Chrome, restores props, releases slot
      7. Container/emulator stays running for next session

    All parameters default to None (sentinel). If None, reads from config.py.
    Constructor args always override config values.

    Args:
        mode: "manual" (existing ADB devices), "auto" (redroid containers),
              or "mumu" (MuMu instances managed automatically).
        max_devices: How many devices to use. 0 = all available (manual only).
        proxy: Single SOCKS5 proxy shared by all workers.
        proxies: Per-worker proxy list (round-robin if fewer than workers).
        http_proxy: Single HTTP proxy for Android system proxy.
        http_proxies: Per-worker HTTP proxy list.
        device: Fixed device name, or None = random per session.
        timezone: IANA timezone (e.g. "Asia/Manila").
        chrome_apk: Path to Chrome APK (auto mode only).
        debug: Enable debug logging.
    """

    def __init__(
        self,
        mode=None,
        max_devices=None,
        proxy=_UNSET,
        proxies=_UNSET,
        http_proxy=_UNSET,
        http_proxies=_UNSET,
        device=_UNSET,
        profile_tier=_UNSET,
        timezone=_UNSET,
        locale=_UNSET,
        chrome_apk=_UNSET,
        wsl_distro=None,
        mumu_manager_path=_UNSET,
        mumu_indices=_UNSET,
        mumu_auto_create=None,
        max_session_retries=None,
        debug=None,
    ):
        from . import config

        self._mode = mode if mode is not None else config.MODE
        self._max_devices = max_devices if max_devices is not None else config.NUM_DEVICES
        self._proxy = proxy if proxy is not _UNSET else config.PROXY
        self._proxies = proxies if proxies is not _UNSET else config.PROXIES
        self._http_proxy = http_proxy if http_proxy is not _UNSET else config.HTTP_PROXY
        self._http_proxies = http_proxies if http_proxies is not _UNSET else config.HTTP_PROXIES
        self._device = device if device is not _UNSET else config.DEVICE
        self._profile_tier = (
            profile_tier
            if profile_tier is not _UNSET
            else getattr(config, "PROFILE_TIER", "premium")
        )
        self._timezone = timezone if timezone is not _UNSET else config.TIMEZONE
        self._locale = locale if locale is not _UNSET else config.LOCALE
        self._chrome_apk = chrome_apk if chrome_apk is not _UNSET else config.CHROME_APK
        self._wsl_distro = wsl_distro  # WSL2 distro name for Windows auto mode
        self._mumu_manager_path = (
            mumu_manager_path
            if mumu_manager_path is not _UNSET
            else config.MUMU_MANAGER_PATH
        )
        self._mumu_indices = (
            mumu_indices
            if mumu_indices is not _UNSET
            else config.MUMU_INSTANCE_INDICES
        )
        self._mumu_auto_create = (
            mumu_auto_create
            if mumu_auto_create is not None
            else config.MUMU_AUTO_CREATE
        )
        self._debug = debug if debug is not None else config.DEBUG

        # Session reliability (from config)
        self._max_retries = (
            int(max_session_retries)
            if max_session_retries is not None
            else config.MAX_SESSION_RETRIES
        )
        self._session_timeout = config.SESSION_SETUP_TIMEOUT
        self._max_failures = config.MAX_SLOT_FAILURES
        self._health_interval = config.HEALTH_CHECK_INTERVAL
        self._task_timeout = config.TASK_TIMEOUT  # None = no limit
        if self._mode in {"auto", "mumu"} and self._session_timeout < 240:
            # Emulator/container first-session setup can be slower than manual devices,
            # especially when multiple Redroid workers cold-start together in WSL.
            self._session_timeout = 240

        # Cleanup timeout: max seconds to wait for __aexit__ before abandoning
        self._cleanup_timeout = 60

        self._slots: List[DeviceSlot] = []
        self._free_event = asyncio.Event()
        self._docker: Any = None  # RedroidManager for auto mode
        self._mumu: Any = None    # MuMuManager for mumu mode
        self._health_task: Optional[asyncio.Task] = None
        self._running = False
        self._chrome_apk_path: Optional[str] = None  # resolved APK path

    async def __aenter__(self) -> "DamruPool":
        setup_logging(self._debug)

        if self._mode == "auto":
            await self._init_auto()
        elif self._mode == "mumu":
            await self._init_mumu()
        else:
            await self._init_manual()

        if not self._slots:
            raise DamruError("No devices available for pool")

        self._running = True

        # Start health monitor if enabled
        if self._health_interval > 0:
            self._health_task = asyncio.create_task(self._health_loop())
            logger.info("Health monitor started (interval=%ds)", self._health_interval)

        logger.info(
            "Pool ready: %d device(s), mode=%s",
            len(self._slots), self._mode,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._running = False

        # Stop health monitor
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        if self._mode == "auto" and self._docker:
            # Don't stop containers - keep them alive for next run
            # Just disconnect ADB connections
            adb = ADB()
            for slot in self._slots:
                try:
                    await adb._run(
                        ["disconnect", slot.serial],
                        timeout=5, allow_failure=True,
                    )
                except Exception:
                    pass
            logger.info("Auto mode: containers left running (reuse on next startup)")
        elif self._mode == "mumu" and self._mumu:
            # Keep MuMu instances running for reuse; only disconnect ADB.
            adb = ADB()
            for slot in self._slots:
                try:
                    await adb._run(
                        ["disconnect", slot.serial],
                        timeout=5, allow_failure=True,
                    )
                except Exception:
                    pass
            logger.info("MuMu mode: instances left running (reuse on next startup)")

        logger.info(
            "Pool closed (served %d sessions total)",
            sum(s.sessions_served for s in self._slots),
        )
        self._slots.clear()
        if sys.platform == "win32":
            await asyncio.sleep(2.0)

    # -- Manual mode init --

    async def _init_manual(self) -> None:
        """Discover existing ADB devices and create slots."""
        adb = ADB()
        await adb.ensure_server()
        devices = await adb.list_devices()
        online = [d for d in devices if d["status"] == "device"]

        if not online:
            raise DamruError(
                "No ADB devices found. Start MuMu instances or connect devices."
            )

        # Limit to max_devices (0 = all)
        if self._max_devices > 0:
            online = online[: self._max_devices]

        for i, dev in enumerate(online):
            self._slots.append(
                DeviceSlot(serial=dev["serial"], index=i)
            )
            logger.info(
                "Slot %d: %s (%s)",
                i, dev["serial"], dev.get("model", "unknown"),
            )

    # -- Auto mode init --

    async def _init_auto(self) -> None:
        """Start redroid containers and create slots.

        Windows: runs docker via WSL2 (redroid needs Linux kernel modules).
        Linux: runs docker natively.

        Each container gets a random Chrome version from chrome-apks/.
        If the container already has that version, skip install.
        If it has a different version, uninstall + install the new one.
        """
        from .docker import RedroidManager

        count = self._max_devices or 10
        self._docker = RedroidManager(wsl_distro=self._wsl_distro)

        await self._docker.check_docker()
        await self._docker.validate_redroid_multi_container_support(count)

        # APKs are only required for raw Redroid images without Chrome. Baked
        # Damru images already contain Chrome, so pip-install users can load the
        # image tarball without also checking APK files into their project.
        try:
            apk_path = self._docker.find_chrome_apk(self._chrome_apk)
            self._chrome_apk_path = apk_path
            logger.info("Chrome APKs available for raw Redroid images")
        except DamruError as exc:
            self._chrome_apk_path = None
            logger.info("Chrome APKs not found; baked image Chrome will be reused if present (%s)", exc)

        # Ensure containers (reuse existing) + cleanup extras
        serials = await self._docker.ensure_all(count)

        _install_sem = asyncio.Semaphore(2)

        async def _setup_container(serial: str, idx: int) -> DeviceSlot:
            # Check what's currently installed
            installed = await self._docker.get_installed_chrome_version(serial)

            if installed:
                # Chrome already present (e.g. baked image) -- keep it as-is.
                # TrichromeLibrary is a system pkg and can't be downgraded,
                # so swapping versions on baked images breaks Chrome.
                slot_apk_path = self._chrome_apk_path
                logger.info(
                    "Slot %d: Chrome %s already installed, keeping",
                    idx, installed,
                )
            else:
                # Not installed at all -> pick a random version & install
                slot_apk_path = self._chrome_apk_path or self._docker.find_chrome_apk(self._chrome_apk)
                from pathlib import Path
                desired_version = Path(slot_apk_path).name
                logger.info(
                    "Slot %d: No Chrome found, installing %s",
                    idx, desired_version,
                )
                async with _install_sem:
                    for attempt in range(3):
                        try:
                            if attempt > 0:
                                await self._docker._run_cmd(
                                    self._docker._adb_cmd("connect", serial),
                                    timeout=10, allow_failure=True,
                                )
                                await asyncio.sleep(5)
                            await self._docker.install_chrome(serial, slot_apk_path)
                            break
                        except Exception as e:
                            if attempt < 2:
                                logger.warning(
                                    "Chrome install on %s attempt %d/3 failed: %s",
                                    serial, attempt + 1, e,
                                )
                                await asyncio.sleep(5)
                            else:
                                raise

            adb = ADB(serial=serial)
            root = RootOps(adb)
            await root.check_root()
            slot = DeviceSlot(
                serial=serial, index=idx, container_index=idx,
                chrome_apk_path=slot_apk_path,
            )
            logger.info(
                "Slot %d: %s (redroid, Chrome %s, root OK)",
                idx, serial, installed or "freshly installed",
            )
            return slot

        slots = await asyncio.gather(
            *[_setup_container(s, i) for i, s in enumerate(serials)]
        )
        self._slots.extend(slots)

    async def _init_mumu(self) -> None:
        """Start/reuse MuMu instances and create slots."""
        from .mumu import MuMuManager
        from .docker import RedroidManager

        count = self._max_devices or 1
        self._mumu = MuMuManager(manager_path=self._mumu_manager_path)
        await self._mumu.check_manager()

        # Reuse existing instances by default. Optional one-time auto-create.
        pairs = await self._mumu.ensure_all(
            count=count,
            indices=self._mumu_indices,
            auto_create=self._mumu_auto_create,
        )

        # Chrome install on MuMu: try auto-discovery (same behavior as redroid).
        apk_path = None
        try:
            apk_path = RedroidManager().find_chrome_apk(self._chrome_apk)
            logger.info("Chrome APK: %s", apk_path)
        except Exception:
            apk_path = None

        _install_sem = asyncio.Semaphore(2)

        async def _setup_pair(pair_idx: int, vm_index: int, serial: str) -> DeviceSlot:
            adb = ADB(serial=serial)

            # Ensure ADB server sees endpoint as online.
            await adb.ensure_server()
            await adb._run(["connect", serial], timeout=10, allow_failure=True)

            if apk_path:
                out = await adb.shell("pm path com.android.chrome", timeout=8, allow_failure=True)
                if "package:" not in out:
                    async with _install_sem:
                        for attempt in range(3):
                            try:
                                if attempt > 0:
                                    await adb._run(["disconnect", serial], timeout=8, allow_failure=True)
                                    await adb._run(["connect", serial], timeout=10, allow_failure=True)
                                    await asyncio.sleep(3)
                                logger.info("Installing Chrome on MuMu %d (%s)", vm_index, serial)
                                await self._mumu.install_apk(serial, apk_path)
                                break
                            except Exception as e:
                                if attempt < 2:
                                    logger.warning(
                                        "Chrome install failed on MuMu %d (%s) attempt %d/3: %s",
                                        vm_index, serial, attempt + 1, e,
                                    )
                                    await asyncio.sleep(3)
                                else:
                                    raise
            else:
                out = await adb.shell("pm path com.android.chrome", timeout=8, allow_failure=True)
                if "package:" not in out:
                    raise DamruError(
                        "Chrome not installed on MuMu and no APK was found. "
                        "Add APKs under damru/chrome-apks/<version>/ or set chrome_apk=."
                    )

            root = RootOps(adb)
            await root.check_root()
            slot = DeviceSlot(serial=serial, index=pair_idx, container_index=vm_index)
            logger.info("Slot %d: %s (mumu idx=%d, root OK)", pair_idx, serial, vm_index)
            return slot

        slots = await asyncio.gather(
            *[_setup_pair(i, vm_idx, serial) for i, (vm_idx, serial) in enumerate(pairs)]
        )
        self._slots.extend(slots)

    # -- Session management --

    @asynccontextmanager
    async def session(
        self,
        device: Optional[str] = None,
        profile_tier: Optional[str] = None,
        proxy: Optional[str] = None,
        task_timeout: Optional[float] = _UNSET,
    ):
        """Acquire a device, apply fresh fingerprint, yield BrowserContext.

        The container/emulator stays running - only Chrome is recycled.
        Each session gets a unique random device fingerprint unless
        a specific device name is provided.

        Args:
            task_timeout: Max seconds for user code. When hit, Chrome is
                killed and the slot freed. None = no limit. Defaults to
                config.TASK_TIMEOUT.
        """
        timeout = task_timeout if task_timeout is not _UNSET else self._task_timeout
        slot = await self._acquire_slot()
        damru = None
        try:
            proxy_url = proxy or self._get_proxy(slot.index)
            http_proxy_url = self._get_http_proxy(slot.index)

            for attempt in range(self._max_retries + 1):
                try:
                    damru = AsyncDamru(
                        device=device or self._device or None,  # None = random
                        serial=slot.serial,
                        proxy=proxy_url,
                        http_proxy=http_proxy_url,
                        profile_tier=profile_tier or self._profile_tier,
                        timezone=self._timezone,
                        locale=self._locale,
                        debug=self._debug,
                    )
                    ctx = await asyncio.wait_for(
                        damru.__aenter__(),
                        timeout=self._session_timeout,
                    )
                    slot.consecutive_failures = 0
                    break  # Setup OK
                except Exception as e:
                    err_text = str(e).strip() or repr(e)
                    logger.warning(
                        "Slot %d setup failed (attempt %d/%d): %s",
                        slot.index, attempt + 1, self._max_retries + 1, err_text,
                    )
                    if damru:
                        try:
                            await asyncio.wait_for(
                                damru.__aexit__(None, None, None),
                                timeout=self._cleanup_timeout,
                            )
                        except Exception:
                            logger.warning("Slot %d: cleanup timed out/failed, abandoning", slot.index)
                        damru = None
                    if (
                        self._mode == "auto"
                        and self._docker
                        and slot.chrome_apk_path
                        and "No Chrome browser found" in err_text
                        and attempt < self._max_retries
                    ):
                        logger.info("Slot %d: Chrome missing after failed setup, reinstalling before retry", slot.index)
                        try:
                            await self._docker.install_chrome(slot.serial, slot.chrome_apk_path)
                        except Exception as install_exc:
                            logger.warning("Slot %d: Chrome reinstall failed: %s", slot.index, install_exc)
                    if attempt == self._max_retries:
                        slot.consecutive_failures += 1
                        slot.last_error = err_text
                        if slot.consecutive_failures >= self._max_failures:
                            slot.healthy = False
                            logger.error(
                                "Slot %d marked unhealthy after %d consecutive failures",
                                slot.index, slot.consecutive_failures,
                            )
                        raise DamruError(
                            f"Session setup failed after {self._max_retries + 1} attempts: {err_text}"
                        )
                    if self._mode == "mumu":
                        try:
                            await self._refresh_mumu_slot(slot)
                        except Exception as recover_err:
                            logger.warning(
                                "Slot %d MuMu refresh before retry failed: %s",
                                slot.index, recover_err,
                            )
                    await asyncio.sleep(2)

            slot.sessions_served += 1
            watchdog = None
            try:
                if timeout:
                    watchdog = asyncio.create_task(
                        self._task_watchdog(damru, slot, timeout)
                    )
                yield ctx
            finally:
                if watchdog and not watchdog.done():
                    watchdog.cancel()
                    try:
                        await watchdog
                    except asyncio.CancelledError:
                        pass
                if damru:
                    try:
                        await asyncio.wait_for(
                            damru.__aexit__(None, None, None),
                            timeout=self._cleanup_timeout,
                        )
                    except Exception as e:
                        logger.warning("Session cleanup timed out/failed: %s", e)
                    damru = None
        finally:
            self._release_slot(slot)

    async def _task_watchdog(self, damru: AsyncDamru, slot: DeviceSlot, timeout: float) -> None:
        """Kill Chrome after task_timeout. User code gets errors -> exits with block."""
        await asyncio.sleep(timeout)
        logger.warning(
            "Task timeout (%ds) on slot %d - killing Chrome",
            timeout, slot.index,
        )
        if damru._chrome:
            try:
                await damru._chrome.force_stop()
            except Exception:
                pass

    async def map(
        self,
        func: Callable,
        items: Sequence,
        concurrency: int = 0,
    ) -> List:
        """Run func(ctx, item) for each item across pool workers.

        Each task gets a unique fingerprint. concurrency=0 means len(slots).
        """
        limit = concurrency or len(self._slots)
        sem = asyncio.Semaphore(limit)

        async def _run(item):
            async with sem:
                async with self.session() as ctx:
                    return await func(ctx, item)

        return await asyncio.gather(*[_run(item) for item in items])

    # -- Slot management --
    async def open_url(self, serial: str, url: str, proxy: str | None = None, mode: str = "playwright", **kwargs) -> str:
        """Open a URL on a device with full stealth fingerprint.
        
        Convenience wrapper around stealth-open-url logic.
        Uses AsyncDamru for a single shot navigation.
        
        Args:
            serial: ADB device serial
            url: http:// or https:// URL
            proxy: SOCKS/HTTP proxy URL
            mode: navigation mode (playwright, cdp, reattach, native)
            **kwargs: passed to AsyncDamru constructor
        """
        from .async_core import AsyncDamru
        async with AsyncDamru(serial=serial, proxy=proxy, **kwargs) as ctx:
            if mode == "playwright":
                page = await ctx.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                return page.title()
            else:
                # Fallback: navigate via CDP
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                return page.title()


    async def _acquire_slot(self) -> DeviceSlot:
        """Wait for and return a free healthy slot."""
        while True:
            for slot in self._slots:
                if not slot.busy and slot.healthy:
                    slot.busy = True
                    return slot
            # Check if any healthy slots exist at all
            healthy = sum(1 for s in self._slots if s.healthy)
            if healthy == 0:
                raise DamruError("All device slots are dead")
            self._free_event.clear()
            await self._free_event.wait()

    def _release_slot(self, slot: DeviceSlot) -> None:
        """Mark slot as free and notify waiters."""
        slot.busy = False
        self._free_event.set()

    # -- Health monitoring --

    async def _health_loop(self) -> None:
        """Background task: periodically check ADB connectivity of idle slots."""
        while self._running:
            await asyncio.sleep(self._health_interval)
            if not self._running:
                break
            for slot in self._slots:
                if slot.busy or not slot.healthy:
                    continue
                try:
                    adb = ADB(serial=slot.serial)
                    out = await adb.shell("echo ok", timeout=5, allow_failure=True)
                    if "ok" not in out:
                        raise Exception("ADB unresponsive")
                except Exception:
                    # Re-check busy - another coroutine may have acquired it during await
                    if slot.busy:
                        continue
                    logger.warning("Slot %d unresponsive, recovering...", slot.index)
                    await self._recover_slot(slot)

    async def _recover_slot(self, slot: DeviceSlot) -> None:
        """Attempt to recover an unresponsive slot."""
        if slot.container_index is None:
            slot.healthy = False
            logger.error("Slot %d (manual mode) unresponsive - marked dead", slot.index)
            return

        slot.restart_count += 1
        if slot.restart_count > self._max_failures:
            slot.healthy = False
            logger.error("Slot %d exceeded restart limit (%d)", slot.index, self._max_failures)
            return

        try:
            if self._mode == "auto":
                serial = await self._docker.restart_container(slot.container_index)
                adb = ADB()
                await adb._run(["connect", serial], timeout=10, allow_failure=True)
                from .config import CONTAINER_BOOT_TIMEOUT, REDROID_CONTAINER_PREFIX
                await self._docker._wait_for_boot(
                    serial,
                    name=f"{REDROID_CONTAINER_PREFIX}{slot.container_index}",
                    timeout=CONTAINER_BOOT_TIMEOUT,
                )
                apk = slot.chrome_apk_path or self._chrome_apk_path
                if apk:
                    await self._docker.install_chrome(serial, apk)
                slot.serial = serial
            elif self._mode == "mumu":
                vm_index = slot.container_index
                await self._mumu.restart_instance(vm_index)
                serial = await self._mumu.ensure_instance(vm_index)
                slot.serial = serial
            else:
                slot.healthy = False
                logger.error("Slot %d (manual mode) unresponsive - marked dead", slot.index)
                return

            slot.healthy = True
            slot.consecutive_failures = 0
            logger.info("Slot %d recovered (restart #%d)", slot.index, slot.restart_count)
        except Exception as e:
            slot.healthy = False
            logger.error("Slot %d recovery failed: %s", slot.index, e)

    async def _refresh_mumu_slot(self, slot: DeviceSlot) -> None:
        """Lightweight MuMu reconnect for session retry.

        Avoids expensive full resource enforcement on every retry.
        Falls back to full ensure_instance only if reconnect path fails.
        """
        if self._mode != "mumu" or not self._mumu or slot.container_index is None:
            return

        serial = slot.serial
        if serial:
            try:
                await self._mumu.connect_adb(serial)
                await self._mumu.wait_for_boot(serial, timeout=45)
                return
            except Exception as reconnect_err:
                logger.warning(
                    "Slot %d MuMu reconnect failed on %s: %s (fallback ensure_instance)",
                    slot.index, serial, reconnect_err,
                )

        ensured = await self._mumu.ensure_instance(slot.container_index)
        if ensured and ensured != slot.serial:
            logger.info(
                "Slot %d MuMu endpoint refreshed: %s -> %s",
                slot.index, slot.serial, ensured,
            )
            slot.serial = ensured

    # -- Proxy routing --

    def _get_proxy(self, index: int) -> Optional[str]:
        if self._proxies:
            return self._proxies[index % len(self._proxies)]
        return self._proxy

    def _get_http_proxy(self, index: int) -> Optional[str]:
        if self._http_proxies:
            return self._http_proxies[index % len(self._http_proxies)]
        return self._http_proxy

    # -- Properties --

    @property
    def slots(self) -> List[DeviceSlot]:
        """Current device slots (read-only view)."""
        return list(self._slots)

    @property
    def device_count(self) -> int:
        """Number of devices in the pool."""
        return len(self._slots)

    @property
    def stats(self) -> Dict[str, int]:
        """Pool health and usage statistics."""
        return {
            "total_slots": len(self._slots),
            "healthy": sum(1 for s in self._slots if s.healthy),
            "busy": sum(1 for s in self._slots if s.busy),
            "idle": sum(1 for s in self._slots if not s.busy and s.healthy),
            "dead": sum(1 for s in self._slots if not s.healthy),
            "sessions_served": sum(s.sessions_served for s in self._slots),
        }


def _apply_sync_overrides(ctx, overrides: Dict[str, Any]):
    """Re-apply async CDP overrides on sync BrowserContext after CDP swap."""
    target_cores = int(overrides.get("cores") or 4)
    ua_payload = overrides.get("ua_payload")
    touch_points = overrides.get("touch_points")
    net_params = overrides.get("network_params")
    quota_bytes = overrides.get("storage_quota_bytes")
    enable_cdp_sensors = os.environ.get("DAMRU_EXPERIMENTAL_CDP_SENSORS", "1") == "1"
    seen_origins = set()

    def _extract_origin(raw_url: str) -> Optional[str]:
        parsed = urlparse(raw_url or "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"

    def _apply_page_overrides(page) -> None:
        try:
            cdp = ctx.new_cdp_session(page)
            phase = random.uniform(0.0, math.tau)
            beta = random.uniform(-8.0, 12.0)
            gamma = random.uniform(-7.0, 7.0)
            alpha = random.uniform(0.0, 360.0)
            gravity = {
                "x": math.sin(math.radians(gamma)) * 9.80665,
                "y": -math.sin(math.radians(beta)) * 9.80665,
                "z": math.cos(math.radians(beta)) * math.cos(math.radians(gamma)) * 9.80665,
            }
            linear = {
                "x": math.sin(phase * 1.7) * 0.025,
                "y": math.cos(phase * 1.3) * 0.020,
                "z": math.sin(phase * 1.1) * 0.014,
            }
            accel = {axis: gravity[axis] + linear[axis] for axis in ("x", "y", "z")}
            z = math.radians(alpha) * 0.5
            x = math.radians(beta) * 0.5
            y = math.radians(gamma) * 0.5
            quat = {
                "x": math.sin(x) * math.cos(y) * math.cos(z) - math.cos(x) * math.sin(y) * math.sin(z),
                "y": math.cos(x) * math.sin(y) * math.cos(z) + math.sin(x) * math.cos(y) * math.sin(z),
                "z": math.cos(x) * math.cos(y) * math.sin(z) - math.sin(x) * math.sin(y) * math.cos(z),
                "w": math.cos(x) * math.cos(y) * math.cos(z) + math.sin(x) * math.sin(y) * math.sin(z),
            }
            cdp.send(
                "Emulation.setHardwareConcurrencyOverride",
                {"hardwareConcurrency": target_cores},
            )
            if ua_payload:
                cdp.send("Emulation.setUserAgentOverride", ua_payload)
            if touch_points:
                cdp.send(
                    "Emulation.setTouchEmulationEnabled",
                    {"enabled": True, "maxTouchPoints": int(touch_points)},
                )
            if net_params:
                cdp.send("Network.enable", {})
                cdp.send("Network.overrideNetworkState", net_params)
            if enable_cdp_sensors:
                for sensor_type, reading in {
                    "accelerometer": {"xyz": accel},
                    "linear-acceleration": {"xyz": linear},
                    "gravity": {"xyz": gravity},
                    "gyroscope": {"xyz": {"x": random.uniform(-0.006, 0.006), "y": random.uniform(-0.006, 0.006), "z": random.uniform(-0.004, 0.004)}},
                    "magnetometer": {"xyz": {"x": random.uniform(22.0, 38.0), "y": random.uniform(-12.0, 12.0), "z": random.uniform(-44.0, -28.0)}},
                    "absolute-orientation": {"quaternion": quat},
                    "relative-orientation": {"quaternion": quat},
                }.items():
                    with suppress(Exception):
                        cdp.send("Emulation.setSensorOverrideEnabled", {
                            "enabled": True,
                            "type": sensor_type,
                            "metadata": {"available": True, "minimumFrequency": 1, "maximumFrequency": 60},
                        })
                        cdp.send("Emulation.setSensorOverrideReadings", {
                            "type": sensor_type,
                            "reading": reading,
                        })
                with suppress(Exception):
                    cdp.send("DeviceOrientation.setDeviceOrientationOverride", {
                        "alpha": alpha,
                        "beta": beta,
                        "gamma": gamma,
                    })
            if quota_bytes:
                origin = _extract_origin(getattr(page, "url", "") or "")
                if origin and origin not in seen_origins:
                    seen_origins.add(origin)
                    cdp.send(
                        "Storage.overrideQuotaForOrigin",
                        {"origin": origin, "quotaSize": int(quota_bytes)},
                    )
        except Exception as e:
            logger.debug("Sync CDP override apply failed: %s", e)

    def _bind_page(page) -> None:
        if getattr(page, "_damru_sync_bound", False):
            return
        setattr(page, "_damru_sync_bound", True)

        def _on_frame_navigated(frame) -> None:
            if getattr(frame, "parent_frame", None) is not None:
                return
            _apply_page_overrides(page)

        page.on("framenavigated", _on_frame_navigated)
        _apply_page_overrides(page)

    for page in list(ctx.pages):
        _bind_page(page)

    def _on_page(new_page) -> None:
        _bind_page(new_page)

    ctx.on("page", _on_page)


class DamruPoolSync:
    """Sync wrapper around DamruPool for ThreadPoolExecutor usage.

    Runs an asyncio event loop in a dedicated background thread.
    Thread-safe: multiple threads can call session() concurrently.

    All parameters default to config.py values (passed through to DamruPool).

    Usage:
        with DamruPoolSync() as pool:                # all from config.py
            with pool.session() as ctx:
                page = ctx.pages[0]
                page.goto("https://example.com")

        with DamruPoolSync(proxy="socks5://host:port") as pool:  # override proxy
            ...
    """

    def __init__(self, **kwargs):
        self._pool = DamruPool(**kwargs)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> "DamruPoolSync":
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="damru-pool-loop"
        )
        self._thread.start()

        future = asyncio.run_coroutine_threadsafe(
            self._pool.__aenter__(), self._loop
        )
        future.result(timeout=300)  # auto mode containers can take time
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._pool.__aexit__(exc_type, exc_val, exc_tb), self._loop
            )
            try:
                future.result(timeout=60)
            except Exception as e:
                logger.warning("Pool cleanup error: %s", e)
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

        if self._loop and not self._loop.is_closed():
            self._loop.close()
            self._loop = None

    @contextmanager
    def session(
        self,
        device: Optional[str] = None,
        profile_tier: Optional[str] = None,
        proxy: Optional[str] = None,
        task_timeout: Optional[float] = _UNSET,
    ):
        """Sync context manager - acquires slot, applies fingerprint, yields SYNC context.

        Thread-safe: can be called from multiple ThreadPoolExecutor workers.

        The async damru setup runs all 17 stealth layers (root props, GPU, proxy,
        Chrome launch, CDP connect, hardware overrides). Then the async Playwright
        CDP client is closed (Chrome + ADB port forward stay alive) and a SYNC
        Playwright CDP client reconnects on the same port. Hardware overrides
        (per-CDP-session) are re-applied on the sync context.

        Args:
            task_timeout: Max seconds for user code. When hit, Chrome is
                killed and the slot freed. None = no limit. Defaults to
                config.TASK_TIMEOUT.
        """
        if not self._loop or not self._loop.is_running():
            raise DamruError("Pool not initialized - use inside 'with' block")

        timeout = task_timeout if task_timeout is not _UNSET else self._pool._task_timeout
        damru_ref: List[Optional[AsyncDamru]] = [None]
        slot_ref: List[Optional[DeviceSlot]] = [None]

        async def _enter():
            slot = await self._pool._acquire_slot()
            slot_ref[0] = slot
            proxy_url = proxy or self._pool._get_proxy(slot.index)
            http_proxy_url = self._pool._get_http_proxy(slot.index)

            damru = None
            for attempt in range(self._pool._max_retries + 1):
                try:
                    damru = AsyncDamru(
                        device=device or self._pool._device or None,
                        serial=slot.serial,
                        proxy=proxy_url,
                        http_proxy=http_proxy_url,
                        profile_tier=profile_tier or self._pool._profile_tier,
                        timezone=self._pool._timezone,
                        locale=self._pool._locale,
                        debug=self._pool._debug,
                    )
                    await asyncio.wait_for(
                        damru.__aenter__(),
                        timeout=self._pool._session_timeout,
                    )
                    damru_ref[0] = damru
                    slot.consecutive_failures = 0
                    break
                except Exception as e:
                    err_text = str(e).strip() or repr(e)
                    logger.warning(
                        "Slot %d setup failed (attempt %d/%d): %s",
                        slot.index, attempt + 1, self._pool._max_retries + 1, err_text,
                    )
                    if damru:
                        try:
                            await asyncio.wait_for(
                                damru.__aexit__(None, None, None),
                                timeout=self._pool._cleanup_timeout,
                            )
                        except Exception:
                            logger.warning("Slot %d: cleanup timed out/failed, abandoning", slot.index)
                        damru = None
                    if attempt == self._pool._max_retries:
                        slot.consecutive_failures += 1
                        slot.last_error = err_text
                        if slot.consecutive_failures >= self._pool._max_failures:
                            slot.healthy = False
                        self._pool._release_slot(slot)
                        slot_ref[0] = None
                        raise DamruError(
                            f"Session setup failed after {self._pool._max_retries + 1} attempts: {err_text}"
                        )
                    if (
                        self._pool._mode == "mumu"
                    ):
                        try:
                            await self._pool._refresh_mumu_slot(slot)
                        except Exception as recover_err:
                            logger.warning(
                                "Slot %d MuMu refresh before retry failed: %s",
                                slot.index, recover_err,
                            )
                    await asyncio.sleep(2)

            slot.sessions_served += 1

        async def _swap_to_sync():
            """Close async Playwright CDP but keep Chrome + ADB port forward alive."""
            damru = damru_ref[0]
            port = getattr(damru, '_cdp_port', None)
            sync_overrides = {
                "cores": getattr(damru, "_override_cores", 4),
                "ua_payload": getattr(damru, "_sync_ua_payload", None),
                "touch_points": getattr(damru, "_sync_touch_points", None),
                "network_params": getattr(damru, "_sync_network_params", None),
                "storage_quota_bytes": getattr(damru, "_sync_storage_quota_bytes", None),
            }
            # Close async Playwright browser (NOT the port forward)
            if damru._cdp and damru._cdp._browser:
                try:
                    await damru._cdp._browser.close()
                except Exception:
                    pass
                damru._cdp._browser = None
            if damru._cdp and damru._cdp._pw_instance:
                try:
                    await damru._cdp._pw_instance.stop()
                except Exception:
                    pass
                damru._cdp._pw_instance = None
            # Also clear async context ref (no longer valid)
            damru._context = None
            return port, sync_overrides

        async def _exit():
            if damru_ref[0]:
                try:
                    await asyncio.wait_for(
                        damru_ref[0].__aexit__(None, None, None),
                        timeout=self._pool._cleanup_timeout,
                    )
                except Exception as e:
                    logger.warning("Session cleanup timed out/failed: %s", e)
            if slot_ref[0]:
                self._pool._release_slot(slot_ref[0])

        async def _kill_chrome():
            if damru_ref[0] and damru_ref[0]._chrome:
                try:
                    await damru_ref[0]._chrome.force_stop()
                except Exception:
                    pass

        def _on_task_timeout():
            logger.warning("Task timeout (%ds) - killing Chrome", timeout)
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(_kill_chrome(), self._loop)

        # -- Phase 1: Async setup (fingerprint, Chrome, CDP, hardware overrides) --
        max_enter_time = (
            (self._pool._max_retries + 1)
            * (self._pool._session_timeout + self._pool._cleanup_timeout + 5)
        )
        fut = asyncio.run_coroutine_threadsafe(_enter(), self._loop)
        fut.result(timeout=max_enter_time)

        # -- Phase 2: Swap async CDP -> sync CDP --
        swap_fut = asyncio.run_coroutine_threadsafe(_swap_to_sync(), self._loop)
        cdp_port, sync_overrides = swap_fut.result(timeout=15)

        if not cdp_port:
            raise DamruError("CDP port not available after async setup")

        # Connect sync Playwright CDP in the calling (worker) thread
        sync_pw = None
        sync_browser = None
        try:
            sync_pw = sync_playwright().start()
            sync_browser = sync_pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{cdp_port}", timeout=15000,
            )
            sync_ctx = (
                sync_browser.contexts[0]
                if sync_browser.contexts
                else sync_browser.new_context()
            )
            # Re-apply hardware overrides on the sync context
            _apply_sync_overrides(sync_ctx, sync_overrides)
        except Exception as e:
            # Sync connect failed - clean up and raise
            if sync_browser:
                try:
                    sync_browser.close()
                except Exception:
                    pass
            if sync_pw:
                try:
                    sync_pw.stop()
                except Exception:
                    pass
            # Still need async cleanup (Chrome stop, restore props)
            exit_fut = asyncio.run_coroutine_threadsafe(_exit(), self._loop)
            try:
                exit_fut.result(timeout=self._pool._cleanup_timeout + 10)
            except Exception:
                pass
            raise DamruError(f"Sync CDP reconnect failed: {e}")

        # -- Phase 3: Yield sync BrowserContext to caller --
        timer = None
        try:
            if timeout:
                timer = threading.Timer(timeout, _on_task_timeout)
                timer.daemon = True
                timer.start()
            yield sync_ctx
        finally:
            if timer:
                timer.cancel()
            # Close sync Playwright
            try:
                sync_browser.close()
            except Exception:
                pass
            try:
                sync_pw.stop()
            except Exception:
                pass
            # Async cleanup (Chrome stop, restore props, release slot)
            exit_fut = asyncio.run_coroutine_threadsafe(_exit(), self._loop)
            try:
                exit_fut.result(timeout=self._pool._cleanup_timeout + 10)
            except Exception as e:
                logger.warning("Session cleanup error: %s", e)
                # CRITICAL: Always release slot even if async cleanup failed/timed out.
                # Without this, a timed-out cleanup leaves the slot busy forever.
                if slot_ref[0]:
                    self._pool._release_slot(slot_ref[0])
                    slot_ref[0] = None

    @property
    def device_count(self) -> int:
        return self._pool.device_count

    @property
    def stats(self) -> Dict[str, int]:
        """Pool health and usage statistics (thread-safe read)."""
        return self._pool.stats
