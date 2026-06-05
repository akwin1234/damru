"""AsyncDamru - async context manager for stealth Android browser automation.

Usage:
    async with AsyncDamru(device="pixel_8_pro", proxy="socks5://host:port") as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import sys
from typing import Optional
from urllib.parse import urlparse

# Stealth: tell patched Playwright driver to disable Runtime domain after
# context discovery.  This prevents console.log argument serialization
# which FingerprintJS Pro uses to detect CDP/DevTools.
os.environ.setdefault("PLAYWRIGHT_STEALTH_RUNTIME", "1")

from playwright.async_api import BrowserContext, Page

from .adb import ADB, ADBError
from .apk_assets import find_bundle_apk
from .cdp import CDPConnection
from .chrome import ChromeManager
from .devices import AndroidDevice, get_device, get_random_device, pick_random_android_version, pick_random_chrome_version
from .netfix import wsl_runtime_network_repair_script
from .profiles import DamruProfile, build_profile
from .proxy import build_accept_language, resolve_locale_for_geo
from .root import RootOps
from .utils import logger, setup_logging, sleep


class DamruError(Exception):
    """Damru operation failed."""


class AsyncDamru:
    """Stealth browser automation on Android via ADB + root.

    Spoofing layers (root + CDP ONLY - zero JS injection):
        Layer 1: Android system props (root resetprop) - undetectable
        Layer 2: Chrome CLI flags (best-effort on "user" builds)
        Layer 3: GPU binary patch (.so) or renderer.config - undetectable
        Layer 4: CDP protocol overrides (UA, cores, touch, network) - C++ level
        Layer 5: Chrome Preferences JSON patch (locale, DoH) - undetectable

    GPU renderer + GL extensions are spoofed via renderer.config + opengl-gc
    (MuMu) or binary .so patch (redroid).
    Proxy is set via Android system HTTP proxy (settings put global http_proxy),
    which works on ALL Android builds including "user" (MuMu, BlueStacks, etc).

    Args:
        device: Device name, model, or "random". None = random.
        serial: ADB serial (auto-detect if None).
        proxy: Proxy URL for GeoIP resolution (e.g. "socks5://host:port").
        http_proxy: HTTP proxy for Android system (e.g. "proxy.example:50000"
            or "http://host:port"). Auto-derived from proxy if None.
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
        http_proxy: Optional[str] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
        chrome_package: Optional[str] = None,
        restore_props: bool = True,
        keep_chrome_on_exit: bool = False,
        force_cold_start: bool = False,
        debug: bool = False,
    ):
        self._device_name = device
        self._serial = serial
        self._proxy = proxy
        self._http_proxy = http_proxy
        self._timezone = timezone
        self._locale = locale
        self._chrome_package = chrome_package
        self._restore_props = restore_props
        self._keep_chrome_on_exit = keep_chrome_on_exit
        self._force_cold_start = force_cold_start
        self._debug = debug

        # Initialized during __aenter__
        self._adb: Optional[ADB] = None
        self._root: Optional[RootOps] = None
        self._chrome: Optional[ChromeManager] = None
        self._cdp: Optional[CDPConnection] = None
        self._profile: Optional[DamruProfile] = None
        self._context: Optional[BrowserContext] = None
        self._worker_target_sessions = []
        self._browser_worker_cdp_armed = False
        self._raw_cdp_tasks = []
        self._raw_cdp_ws = None
        # CDP payload snapshots for DamruPoolSync reattach.
        self._sync_ua_payload = None
        self._sync_touch_points = None
        self._sync_timezone = None
        self._touch_points = None
        self._sync_network_params = None
        self._sync_storage_quota_bytes = None

    async def _start_default_redroid_if_needed(self) -> Optional[str]:
        """Start one managed Redroid worker for the simple AsyncDamru API.

        Pool users already go through DamruPool auto mode. This fallback keeps
        `async with AsyncDamru(...)` usable on fresh WSL/Linux installs where no
        manual ADB device is connected yet.
        """
        try:
            from .config import MODE
        except Exception:
            MODE = "manual"
        if MODE != "auto":
            return None

        from .docker import RedroidManager

        docker = RedroidManager()
        await docker.check_docker()
        apk_path = None
        try:
            apk_path = docker.find_chrome_apk(None)
        except DamruError:
            pass
        serial = await docker.ensure_container(0)
        installed = await docker.get_installed_chrome_version(serial)
        if not installed:
            if apk_path is None:
                apk_path = docker.find_chrome_apk(None)
            await docker.install_chrome(serial, apk_path)
        return serial

    async def __aenter__(self) -> BrowserContext:
        setup_logging(self._debug)
        import time as _time
        _t0 = _time.monotonic()

        # #==============================================================#
        # |  PHASE 1: Device detection (sequential - each needs prior) |
        # #==============================================================#

        # Step 1: Detect ADB device
        self._adb = ADB(serial=self._serial)
        await self._adb.ensure_server()
        if not self._serial:
            try:
                self._serial = await self._adb.detect_device()
            except ADBError:
                self._serial = await self._start_default_redroid_if_needed()
                if not self._serial:
                    raise
            self._adb.serial = self._serial

        # Step 2: Device info + root check + GPU detect - all need ADB,
        # but are independent of each other -> run in parallel.
        self._root = RootOps(self._adb)
        info_task = asyncio.ensure_future(self._adb.get_device_info())
        root_task = asyncio.ensure_future(self._root.check_root())
        gpu_task = asyncio.ensure_future(self._query_native_gpu())
        info, _, native_gpu = await asyncio.gather(info_task, root_task, gpu_task)

        logger.info(
            "Device: %s (%s) - Android %s [%s]",
            info.get("model", ""), info.get("brand", ""),
            info.get("android_version", ""), self._serial,
        )
        logger.info("Root access confirmed")
        logger.info("Native GPU: %s", native_gpu or "unknown")

        # Step 3: Pick target device + build profile (CPU-only, instant)
        real_android = info.get("android_version", "")
        if self._device_name and self._device_name != "random":
            target_device = get_device(self._device_name)
        else:
            target_device = get_random_device()
        logger.info("Target device: %s (Android %s, %s, %s)",
                     target_device.name, target_device.android_version,
                     target_device.chipset, target_device.webgl_renderer)

        # MuMu-specific dynamic profile (non-blocking)
        _mumu_chrome_wiped = False
        try:
            from .mumu import MuMuManager
            mm = MuMuManager()
            applied = await asyncio.wait_for(
                mm.apply_dynamic_profile_by_serial(self._serial or "", target_device),
                timeout=90,
            )
            if applied:
                logger.info("MuMu dynamic profile applied from target device: %s", target_device.name)
                # Profile restart wipes the data partition - Chrome must be reinstalled.
                _mumu_chrome_wiped = True
        except asyncio.TimeoutError:
            logger.warning("MuMu dynamic profile apply timed out; continuing with current MuMu settings")
        except Exception as e:
            logger.debug("MuMu dynamic profile apply skipped: %s", e)

        # Step 4: Build profile (includes screen variant randomization).
        # Android can only store host:port as system proxy. Authenticated
        # HTTP/SOCKS proxies are routed through Damru's local no-auth bridge.
        route_text = ""
        try:
            route_text = await self._adb.shell("ip route show default; ip route", timeout=8, allow_failure=True)
        except Exception:
            route_text = ""
        android_proxy = None
        try:
            from .proxy_runtime import resolve_android_proxy

            android_proxy = resolve_android_proxy(self._proxy, self._http_proxy, route_text=route_text)
        except Exception as exc:
            raise DamruError(f"Proxy setup failed: {exc}") from exc
        self._profile = build_profile(
            target_device,
            proxy=self._proxy,
            http_proxy=self._http_proxy,
            android_proxy=android_proxy,
            timezone=self._timezone,
            locale=self._locale,
        )
        logger.info("Profile: %s (tz=%s, locale=%s)",
                     self._profile.description, self._profile.timezone, self._profile.locale)

        # #==============================================================#
        # |  WARM START DETECTION                                       |
        # |  If Chrome was previously set up (Prefs exist), use fast   |
        # |  reuse path: skip pm clear/FRE/TTS setup, overlap GPU.    |
        # #==============================================================#

        self._chrome = ChromeManager(self._adb, package=self._chrome_package)
        warm_start = (not self._force_cold_start) and await self._chrome.has_preferences()
        if warm_start:
            logger.info("WARM START - fast reuse (skip pm clear/FRE/TTS setup)")
        else:
            logger.info("COLD START - full setup")

        # #==============================================================#
        # |  PHASE 2: System-level spoofing - PARALLEL BATCH           |
        # |  All are independent ADB shell commands that don't depend  |
        # |  on each other. Running them concurrently saves ~5-8s.     |
        # #==============================================================#

        # Check real (non-spoofed) SDK from build.prop to guard against a previous
        # session's resetprop having left ro.build.version.release/sdk at a higher
        # value than the actual framework. If the real SDK < target SDK, setting
        # ro.build.version.sdk to the target value will make Chrome call Android APIs
        # that don't exist in the framework -> FATAL EXCEPTION (NoSuchMethodError).
        real_sdk_raw = await self._adb.shell(
            "su -c \"grep '^ro.build.version.sdk=' /system/build.prop 2>/dev/null\" | cut -d= -f2",
            allow_failure=True,
        )
        real_sdk = int(real_sdk_raw.strip()) if real_sdk_raw.strip().isdigit() else 0
        target_sdk = target_device.sdk_version
        if real_sdk > 0 and real_sdk != target_sdk:
            version_match = False
            logger.info(
                "SDK mismatch: real_sdk=%d vs target_sdk=%d - skipping SDK spoof to avoid Chrome crash",
                real_sdk, target_sdk,
            )
        else:
            version_match = real_android == target_device.android_version
            if version_match:
                logger.info("Android version match (%s) - setting ALL props including version", real_android)

        async def _detect_chrome():
            if not self._chrome_package:
                try:
                    await self._chrome.detect_package()
                except Exception:
                    if not _mumu_chrome_wiped:
                        raise
                    # MuMu profile restart wiped Chrome - auto-reinstall.
                    logger.info("Chrome wiped by MuMu profile restart - reinstalling...")
                    try:
                        from .mumu import MuMuManager
                        from .docker import RedroidManager
                        apk_path = RedroidManager().find_chrome_apk(None)
                        _mm = MuMuManager()
                        twv = find_bundle_apk("TrichromeWebView.apk", apk_path)
                        if twv is not None:
                            await self._adb.install_apk(str(twv))
                            logger.info("TrichromeWebView installed")
                        await _mm.install_apk(self._serial or "", apk_path)
                        logger.info("Chrome reinstalled from %s", apk_path)
                        await self._chrome.detect_package()
                    except Exception as reinstall_err:
                        raise type(reinstall_err)(
                            f"Chrome not found and auto-reinstall failed: {reinstall_err}"
                        )
            ver = await self._chrome.get_version()
            logger.info("Chrome: %s v%s", self._chrome.package, ver)
            return ver

        async def _apply_all_props():
            await self._root.apply_device_props(
                target_device, safe_only=not version_match, parallel=warm_start,
            )
            await asyncio.gather(
                self._root.apply_timezone(self._profile.timezone),
                self._root.apply_locale(self._profile.locale),
                self._root.hide_emulator_identity(),
                self._root.apply_version_release(target_device),
            )

        async def _ensure_debuggable():
            debuggable = await self._adb.get_prop("ro.debuggable")
            build_type = await self._adb.get_prop("ro.build.type")
            tasks = []
            if debuggable != "1":
                tasks.append(self._root.set_prop("ro.debuggable", "1"))
                logger.info("Set ro.debuggable=1 (enables DevTools socket)")
            # Chrome checks ro.build.type at Java level - "user" builds block devtools
            # socket creation even when ro.debuggable=1. Must be "userdebug" or "eng".
            if build_type not in ("userdebug", "eng"):
                tasks.append(self._root.set_prop("ro.build.type", "userdebug"))
                logger.info("Set ro.build.type=userdebug (enables DevTools socket on MuMu)")
            if tasks:
                await asyncio.gather(*tasks)

        async def _apply_screen():
            await asyncio.gather(
                self._adb.shell(
                    f"wm size {self._profile.screen_width}x{self._profile.screen_height}",
                    allow_failure=True,
                ),
                self._adb.shell(
                    f"wm density {self._profile.density_dpi}",
                    allow_failure=True,
                ),
                self._adb.shell("settings put system accelerometer_rotation 0", allow_failure=True),
                self._adb.shell("settings put system user_rotation 0", allow_failure=True),
            )

        async def _set_proxy():
            if self._profile.android_http_proxy:
                await self._adb.shell(
                    f"settings put global http_proxy {self._profile.android_http_proxy}",
                    allow_failure=True,
                )
                host, _, port = self._profile.android_http_proxy.rpartition(":")
                if host and port.isdigit():
                    await asyncio.gather(
                        self._adb.shell(f"settings put global global_http_proxy_host {host}", allow_failure=True),
                        self._adb.shell(f"settings put global global_http_proxy_port {port}", allow_failure=True),
                    )
                logger.info("System HTTP proxy: %s", self._profile.android_http_proxy)
            else:
                await asyncio.gather(
                    self._adb.shell("settings put global http_proxy :0", allow_failure=True),
                    self._adb.shell("settings delete global global_http_proxy_host", allow_failure=True),
                    self._adb.shell("settings delete global global_http_proxy_port", allow_failure=True),
                )
                logger.debug("System HTTP proxy cleared")

        async def _fonts_setup():
            """Install extra fonts (one-time) then randomize (per-session)."""
            await self._root.install_extra_fonts()
            await self._root.randomize_fonts()

        # Big parallel batch: all independent system setup + Chrome detect
        # Warm mode only starts eSpeak TTS service (already installed+configured)
        # Cold mode runs full ensure_speech_voices (install + configure)
        chrome_version_fut = asyncio.ensure_future(_detect_chrome())

        async def _start_tts_service():
            """Start eSpeak TTS service (warm start - already installed)."""
            await self._adb.shell(
                "am startservice --user 0 "
                "-n com.reecedunn.espeak/.TtsService",
                allow_failure=True,
            )

        phase2_tasks = [
            _apply_all_props(),
            _ensure_debuggable(),
            self._root.apply_audio_48khz(),
            _fonts_setup(),
            _apply_screen(),
            _set_proxy(),
            chrome_version_fut,
        ]
        if warm_start:
            phase2_tasks.append(_start_tts_service())
        else:
            phase2_tasks.append(self._root.ensure_speech_voices())
        await asyncio.gather(*phase2_tasks)
        version = await chrome_version_fut

        # #==============================================================#
        # |  PHASE 3+4: GPU + Chrome prep (OVERLAPPED for speed)       |
        # |  GPU patch (/vendor/lib64) and Chrome cleanup (/data/data) |
        # |  touch different paths -> run concurrently. Chrome launch   |
        # |  waits for gather (SF restart) to complete.                |
        # #==============================================================#

        has_renderer_config = await self._adb.shell(
            "test -f /system/etc/mumu-configs/renderer.config && echo OK",
            timeout=5, allow_failure=True,
        )
        eff_renderer = RootOps.effective_renderer(target_device)

        async def _gpu_then_battery():
            """GPU spoof (includes SurfaceFlinger restart) then battery."""
            # Warm: skip GPU re-patch if .so already has target renderer
            if warm_start:
                already = await self._root.is_gpu_already_patched(eff_renderer)
                if already:
                    logger.info("GPU already patched for '%s' - skipping (saves ~6s)", eff_renderer)
                    await self._root.apply_battery_spoof()
                    return

            if "OK" in has_renderer_config:
                try:
                    await self._root.apply_gpu_spoof(target_device, self._chrome.package, native_gpu)
                except Exception as e:
                    logger.warning(
                        "renderer.config GPU spoof failed (%s) - trying binary fallback", e,
                    )
                    try:
                        await self._root.apply_gpu_binary_spoof(target_device)
                    except Exception as e2:
                        logger.warning("Binary GPU spoof fallback failed: %s (continuing)", e2)
            else:
                logger.info("No renderer.config - using binary SwiftShader .so patch")
                await self._root.apply_gpu_binary_spoof(target_device)
            # Battery MUST follow GPU spoof - SurfaceFlinger restart resets BatteryService.
            await self._root.apply_battery_spoof()

        async def _chrome_prep():
            """Chrome cleanup + config (runs concurrently with GPU patch)."""
            await self._chrome.force_stop()
            if warm_start:
                await self._chrome.targeted_cleanup()
            else:
                await self._chrome.clear_all_data()
            accept_lang = build_accept_language(self._profile.locale)
            await asyncio.gather(
                self._chrome.write_command_line(self._profile.chrome_flags),
                self._chrome.patch_preferences(self._profile.locale, accept_lang),
            )

        async def _memory_spoof():
            if not await self._root.is_memory_preload_active(self._chrome.package):
                try:
                    await self._root.setup_memory_preload(self._chrome.package)
                except Exception as exc:
                    logger.warning("Memory preload setup failed (deviceMemory will be native): %s", exc)
                    return
            await self._root.apply_memory_spoof(target_device.device_memory)

        # GPU+battery, Chrome prep, CPU cores, memory - ALL in parallel
        await asyncio.gather(
            _gpu_then_battery(),
            _chrome_prep(),
            self._root.apply_cpu_cores_spoof(target_device.hardware_concurrency),
            _memory_spoof(),
        )

        # Chrome launch with retry - SurfaceFlinger restart kills processes
        # and the system needs variable time to re-register activities.
        # If Chrome doesn't start (no devtools socket), retry with longer delay.
        socket_ready = False
        for launch_attempt in range(3):
            startup_delay = 2.0 if warm_start else 4.0
            if launch_attempt > 0:
                # Increasing delay: 5s, 10s for retries
                extra_wait = 5.0 * launch_attempt
                logger.info("Chrome launch retry %d (waiting %.0fs for system)", launch_attempt + 1, extra_wait)
                await sleep(extra_wait)
                await self._chrome.force_stop()

            await self._chrome.launch(startup_delay=startup_delay)

            if not warm_start and launch_attempt == 0:
                await self._chrome.dismiss_fre()

            socket_ready = await self._chrome.wait_for_devtools_socket(
                timeout=10.0 if launch_attempt < 2 else 15.0,
            )
            if socket_ready:
                break

            # Socket not found - on warm start, FRE/sign-in promo may have appeared
            # unexpectedly (e.g. Preferences didn't suppress it). Try dismissing.
            if warm_start:
                logger.debug("Warm start: socket missing, checking for unexpected FRE/sign-in promo...")
                await self._chrome.dismiss_fre(max_attempts=4)
                # Give Chrome much more time after FRE dismissal - browser UI visible but
                # devtools socket may still be initializing. On slow hardware (2-core MuMu),
                # Chrome can take 100+ seconds to expose chrome_devtools_remote socket.
                logger.info("Warm start: Chrome UI confirmed alive, polling socket for up to 90s...")
                socket_ready = await self._chrome.wait_for_devtools_socket(timeout=90.0)
                if socket_ready:
                    break

            logger.warning("Devtools socket not found (attempt %d/3)", launch_attempt + 1)

        if not socket_ready:
            logger.warning("Devtools socket not detected after retries, attempting connection anyway")

        self._cdp = CDPConnection(self._adb)
        await self._cdp.setup_port_forward()
        try:
            self._context = await self._cdp.connect()
        except Exception:
            # __aexit__ is NOT called when __aenter__ raises, so restore GPU spoof here.
            if self._root:
                try:
                    await self._root.remove_gpu_spoof()
                except Exception as e:
                    logger.warning("GPU spoof cleanup on connect failure: %s", e)
            raise

        # Close stale tabs if any
        pages = self._context.pages
        if len(pages) > 1:
            for p in pages[:-1]:
                try:
                    await p.close()
                except Exception:
                    pass
            logger.debug("Closed %d stale tabs", len(pages) - 1)

        await self._sync_geo_from_browser_proxy()

        # #==============================================================#
        # |  PHASE 5: CDP overrides + TTS warmup - PARALLEL BATCH      |
        # |  All are independent CDP commands. TTS uses a separate tab |
        # |  so it doesn't interfere with CDP overrides on main page.  |
        # #==============================================================#

        real_chrome = version if version else None
        await asyncio.gather(
            self._apply_devtools_evasion(),
            self._root.apply_ipv6_block(),
            self._root.apply_webrtc_block(self._chrome.package),
            self._apply_hardware_overrides(target_device),
            self._apply_touch_emulation(target_device),
            self._apply_network_emulation(),
            self._apply_storage_quota_override(target_device),
            self._apply_timezone_override(),
            self._apply_ua_override(
                target_device,
                chrome_version=real_chrome,
                android_version=target_device.android_version,
            ),
            self._warmup_tts_parallel(),  # TTS on separate tab, concurrent
        )

        # Worker core override + verify (depends on UA override being done)
        await self._arm_worker_core_override(target_device.hardware_concurrency)
        await self._verify_worker_cores(target_device.hardware_concurrency)
        await self._settle_initial_page_context()
        await self._apply_timezone_override()
        self._wrap_context_new_page()
        await self._repair_wsl_network_if_needed()

        # Expose override targets for DamruPoolSync reattach
        self._override_cores = target_device.hardware_concurrency
        self._override_memory = target_device.device_memory
        self._cdp_port = self._cdp._local_port

        _elapsed = _time.monotonic() - _t0
        logger.info("Ready in %.1fs! (%s - root + CDP - zero JS injection)",
                     _elapsed, "warm" if warm_start else "cold")

        return self._context

    async def _sync_geo_from_browser_proxy(self) -> None:
        """Refresh timezone/locale from Chrome's actual proxied network path.

        Python-side GeoIP can be wrong for rotating proxies because the browser
        may receive a different exit IP when Chrome opens its own connection.
        If the user did not explicitly set timezone/locale, query GeoIP through
        Chrome after CDP connects and update the profile before final CDP
        language/timezone overrides are applied.
        """
        if not self._context or not self._profile or not self._root:
            return
        if self._timezone is not None and self._locale is not None:
            self._sync_timezone = self._profile.timezone
            return
        if not (self._profile.android_http_proxy or self._proxy):
            self._sync_timezone = self._profile.timezone
            return

        page = None
        try:
            page = await self._context.new_page()
            data = None
            for url in (
                "https://ipapi.co/json/",
                "https://ipinfo.io/json",
                "http://ip-api.com/json/?fields=status,query,timezone,countryCode",
            ):
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    text = (await page.evaluate("document.body.innerText") or "").strip()
                    if not text.startswith("{"):
                        continue
                    parsed = json.loads(text)
                    timezone = parsed.get("timezone")
                    country_code = parsed.get("country_code") or parsed.get("country") or parsed.get("countryCode")
                    if timezone:
                        data = {"timezone": timezone, "country_code": country_code}
                        break
                except Exception:
                    continue
            if not data:
                self._sync_timezone = self._profile.timezone
                logger.debug("Browser proxy GeoIP sync skipped; keeping startup proxy geo")
                return

            timezone = data["timezone"]
            country_code = data.get("country_code")

            changed = []
            if self._timezone is None and timezone != self._profile.timezone:
                self._profile.timezone = timezone
                await self._root.apply_timezone(timezone)
                changed.append(f"tz={timezone}")
            if self._locale is None:
                locale = resolve_locale_for_geo(timezone, country_code)
                if locale != self._profile.locale:
                    self._profile.locale = locale
                    await self._root.apply_locale(locale)
                    if self._chrome:
                        accept_lang = build_accept_language(locale)
                        with contextlib.suppress(Exception):
                            await self._chrome.patch_preferences(locale, accept_lang)
                    changed.append(f"locale={locale}")

            self._sync_timezone = self._profile.timezone
            if changed:
                logger.info(
                    "Browser proxy GeoIP sync: %s (%s)",
                    ", ".join(changed),
                    country_code or "unknown country",
                )
        except Exception as exc:
            self._sync_timezone = self._profile.timezone
            logger.warning("Browser proxy GeoIP sync failed: %s", exc)
        finally:
            if page:
                with contextlib.suppress(Exception):
                    await page.close()

    async def _apply_timezone_override(self) -> None:
        """Apply timezone override to current page targets via CDP."""
        if not self._context or not self._profile:
            return
        timezone = self._sync_timezone or self._profile.timezone

        async def _apply(page: Page) -> None:
            try:
                session = await self._context.new_cdp_session(page)  # type: ignore[union-attr]
                await session.send("Emulation.setTimezoneOverride", {"timezoneId": timezone})
            except Exception:
                pass

        await asyncio.gather(*[_apply(page) for page in self._context.pages], return_exceptions=True)

    async def _settle_initial_page_context(self) -> None:
        """Return a single stable tab after Chrome's startup tab churn."""
        if not self._context:
            return

        for old_page in list(self._context.pages):
            with contextlib.suppress(Exception):
                await old_page.close()

        page = None
        for attempt in range(3):
            try:
                page = await self._context.new_page()
                await page.goto(
                    "data:text/html,<title>damru-ready</title>",
                    wait_until="load",
                    timeout=5000,
                )
                await page.wait_for_load_state("load", timeout=5000)
                await page.evaluate("() => 1")
                await asyncio.sleep(1.0)
                await page.evaluate("() => 1")
                break
            except Exception:
                if page:
                    with contextlib.suppress(Exception):
                        await page.close()
                page = None
                if attempt == 2:
                    return
                await asyncio.sleep(1)

        if page:
            with contextlib.suppress(Exception):
                await page.bring_to_front()

    def _wrap_context_new_page(self) -> None:
        """Normalize Android Chrome tabs before user code navigates them."""
        if not self._context or getattr(self._context, "_damru_new_page_wrapped", False):
            return

        original_new_page = self._context.new_page

        async def _new_page_stable(*args, **kwargs):
            page = await original_new_page(*args, **kwargs)
            try:
                await page.goto("about:blank", wait_until="load", timeout=5000)
                touch_points = getattr(self, "_touch_points", None)
                timezone = getattr(self, "_sync_timezone", None)
                if touch_points or timezone:
                    cdp = await self._context.new_cdp_session(page)  # type: ignore[union-attr]
                    if touch_points:
                        await cdp.send("Emulation.setTouchEmulationEnabled", {
                            "enabled": True,
                            "maxTouchPoints": touch_points,
                        })
                    if timezone:
                        await cdp.send("Emulation.setTimezoneOverride", {"timezoneId": timezone})
                await asyncio.sleep(0.2)
            except Exception:
                pass
            return page

        setattr(self._context, "new_page", _new_page_stable)
        setattr(self._context, "_damru_new_page_wrapped", True)

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        for task in self._raw_cdp_tasks:
            task.cancel()
        for task in self._raw_cdp_tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._raw_cdp_tasks.clear()
        if self._raw_cdp_ws:
            with contextlib.suppress(Exception):
                await self._raw_cdp_ws.close()
            self._raw_cdp_ws = None

        # Disconnect CDP
        if self._cdp:
            await self._cdp.disconnect()

        # Stop Chrome by default. UI/viewer launches can keep Chrome open so
        # the user can inspect the already-navigated page after the CLI exits.
        if self._chrome and not self._keep_chrome_on_exit:
            await self._chrome.force_stop()

        # Restore renderer.config if GPU was spoofed via renderer.config (MuMu mode).
        # For redroid the container is discarded anyway, but for MuMu (manual mode)
        # the Chrome entry in renderer.config persists across test runs and causes
        # Chrome's GPU process to crash (grey screen) on the next launch.
        if self._root:
            try:
                await self._root.remove_gpu_spoof()
            except Exception as e:
                logger.warning("GPU spoof cleanup failed: %s", e)

        await self._repair_wsl_network_if_needed()

        # SKIP wasteful cleanup (same proxy/props next session):
        # - proxy clear (next session sets same proxy again)
        # - screen reset (next session sets new size)
        # - WebRTC rules (next session applies same rules)
        # - system props (next session sets new props)
        # Container stays alive - only Chrome is recycled per session

        logger.info("Cleanup complete (minimal - container reused)")
        if sys.platform == "win32":
            await asyncio.sleep(2.0)

    async def _repair_wsl_network_if_needed(self) -> None:
        """Repair WSL routing after host-network Redroid mutates netns state."""
        if sys.platform != "win32":
            return
        try:
            from .config import WSL_DISTRO
        except Exception:
            WSL_DISTRO = "Ubuntu"
        WSL_DISTRO = os.environ.get("DAMRU_WSL_DISTRO") or WSL_DISTRO
        script = wsl_runtime_network_repair_script()
        encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
        wrapped = f"printf %s {encoded} | base64 -d | bash"
        try:
            proc = await asyncio.create_subprocess_exec(
                "wsl", "-d", WSL_DISTRO, "-u", "root", "--", "bash", "-lc", wrapped,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
        except Exception as exc:
            logger.debug("WSL network repair skipped/failed: %s", exc)

    async def _apply_devtools_evasion(self) -> None:
        """Neutralize debugger timing detection via CDP (no JS injection).

        Debugger.setSkipAllPauses makes `debugger` statements execute as
        instant no-ops, preventing timing-based DevTools detection.
        """
        if not self._context:
            return

        page = self._context.pages[0] if self._context.pages else None
        if not page:
            return

        try:
            cdp = await self._context.new_cdp_session(page)
            await cdp.send("Debugger.enable")
            await cdp.send("Debugger.setSkipAllPauses", {"skip": True})
            logger.info("DevTools evasion: Debugger.setSkipAllPauses (CDP)")
        except Exception as e:
            logger.warning("DevTools evasion setup failed: %s", e)

    async def disconnect_cdp(self) -> None:
        """Disconnect CDP completely so fingerprinting can't detect DevTools.

        Call AFTER navigating to the target page.  All CDP overrides
        (UA, touch, cores) are already baked into the renderer for the
        current page - they persist for in-flight requests even after
        the CDP session closes.

        Use reconnect_cdp() afterwards to regain page.evaluate() access.
        """
        if self._cdp:
            await self._cdp.disconnect()
            self._cdp = None
            self._context = None
            logger.info("CDP disconnected (DevTools invisible)")

    async def reconnect_cdp(self) -> "BrowserContext":
        """Reconnect CDP after fingerprinting completes.

        Returns the new BrowserContext.  Previous page references are
        invalid - get fresh ones from context.pages.
        """
        self._cdp = CDPConnection(self._adb)
        await self._cdp.setup_port_forward()
        self._context = await self._cdp.connect()
        logger.info("CDP reconnected - %d pages", len(self._context.pages))
        return self._context

    async def _apply_hardware_overrides(self, device: AndroidDevice) -> None:
        """Override hardwareConcurrency via CDP protocol (C++ level).

        CDP Emulation.setHardwareConcurrencyOverride modifies the C++ return
        value - completely undetectable by fingerprinting scripts.

        deviceMemory uses native value (no override). Worker scopes also
        use native values. Accepted tradeoff: 0% stealth > correct values.

        CDP override is per-page. Auto-applies to new pages via context.on('page').
        """
        if not self._context:
            return

        target_cores = device.hardware_concurrency

        async def _arm_browser_worker_cores() -> None:
            """Apply hardwareConcurrency to worker targets created after navigation."""
            if self._browser_worker_cdp_armed or not self._context:
                return
            port = getattr(self, "_cdp_port", None) or getattr(self._cdp, "_local_port", None)
            if not port:
                return

            async def _raw_worker_loop() -> None:
                import itertools
                import urllib.request
                import websockets

                version_url = f"http://127.0.0.1:{port}/json/version"
                with urllib.request.urlopen(version_url, timeout=5) as resp:
                    info = json.loads(resp.read().decode("utf-8"))
                ws_url = info.get("webSocketDebuggerUrl")
                if not ws_url:
                    raise RuntimeError("Chrome CDP websocket URL unavailable")

                ws = await websockets.connect(ws_url, max_size=None)
                self._raw_cdp_ws = ws
                counter = itertools.count(1)
                send_lock = asyncio.Lock()
                pending = {}
                armed_pages = set()

                async def _send(
                    method: str,
                    params: Optional[dict] = None,
                    session_id: Optional[str] = None,
                    wait: bool = False,
                ) -> Optional[dict]:
                    msg_id = next(counter)
                    msg = {"id": msg_id, "method": method, "params": params or {}}
                    if session_id:
                        msg["sessionId"] = session_id
                    fut = None
                    if wait:
                        fut = asyncio.get_running_loop().create_future()
                        pending[msg_id] = fut
                    async with send_lock:
                        await ws.send(json.dumps(msg))
                    if fut:
                        return await asyncio.wait_for(fut, timeout=5)
                    return None

                async def _arm_page_target(target_id: str) -> None:
                    if target_id in armed_pages:
                        return
                    armed_pages.add(target_id)
                    response = await _send(
                        "Target.attachToTarget",
                        {"targetId": target_id, "flatten": True},
                        wait=True,
                    )
                    session_id = ((response or {}).get("result") or {}).get("sessionId")
                    if not session_id:
                        return
                    await _send(
                        "Target.setAutoAttach",
                        {
                            "autoAttach": True,
                            "waitForDebuggerOnStart": True,
                            "flatten": True,
                        },
                        session_id,
                    )

                async def _handle_attached(params: dict) -> None:
                    session_id = params.get("sessionId")
                    target_info = params.get("targetInfo", {})
                    target_type = target_info.get("type", "")
                    if not session_id:
                        return
                    try:
                        if target_type in {"worker", "service_worker", "shared_worker"}:
                            await _send(
                                "Emulation.setHardwareConcurrencyOverride",
                                {"hardwareConcurrency": target_cores},
                                session_id,
                            )
                            if self._sync_ua_payload:
                                await _send("Emulation.setUserAgentOverride", self._sync_ua_payload, session_id)
                        await _send("Runtime.runIfWaitingForDebugger", {}, session_id)
                    except Exception as exc:
                        logger.debug("Raw worker override failed: %s", exc)

                async def _reader() -> None:
                    async for raw in ws:
                        event = json.loads(raw)
                        msg_id = event.get("id")
                        if msg_id in pending:
                            fut = pending.pop(msg_id)
                            if not fut.done():
                                fut.set_result(event)
                            continue
                        method = event.get("method")
                        params = event.get("params", {})
                        if method == "Target.attachedToTarget":
                            asyncio.create_task(_handle_attached(params))
                        elif method == "Target.targetCreated":
                            info = params.get("targetInfo", {})
                            if info.get("type") == "page" and info.get("targetId"):
                                asyncio.create_task(_arm_page_target(info["targetId"]))

                reader = asyncio.create_task(_reader())
                try:
                    await _send("Target.setDiscoverTargets", {"discover": True})
                    list_url = f"http://127.0.0.1:{port}/json/list"
                    with urllib.request.urlopen(list_url, timeout=5) as resp:
                        targets = json.loads(resp.read().decode("utf-8"))
                    for target in targets:
                        if target.get("type") == "page" and target.get("id"):
                            await _arm_page_target(target["id"])
                    await reader
                finally:
                    reader.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await reader
                    pending.clear()

            async def _runner() -> None:
                try:
                    await _raw_worker_loop()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("Browser worker cores auto-attach failed: %s", exc)

            self._raw_cdp_tasks.append(asyncio.create_task(_runner()))
            self._browser_worker_cdp_armed = True
            logger.info("Worker cores override armed: %d (raw browser CDP auto-attach)", target_cores)

        # Query actual emulator values
        page = self._context.pages[0] if self._context.pages else None
        if not page:
            logger.warning("No page available for hardware override")
            return

        actual = await page.evaluate(
            "({cores: navigator.hardwareConcurrency, mem: navigator.deviceMemory})"
        )
        actual_cores = actual.get("cores", 0)
        actual_mem = actual.get("mem")

        logger.info(
            "Hardware: emulator cores=%s mem=%s, target cores=%s mem=%s",
            actual_cores, actual_mem, target_cores, device.device_memory,
        )

        # --- CDP override for hardwareConcurrency (C++ level) ---
        needs_cores_override = actual_cores != target_cores

        async def _apply_cdp_cores(p: Page) -> None:
            """Apply cores override to page and worker targets via CDP."""
            try:
                cdp_session = await self._context.new_cdp_session(p)  # type: ignore[union-attr]
                await cdp_session.send(
                    "Emulation.setHardwareConcurrencyOverride",
                    {"hardwareConcurrency": target_cores},
                )

                async def _on_attached(params) -> None:
                    target_info = params.get("targetInfo", {})
                    target_type = target_info.get("type", "")
                    session_id = params.get("sessionId")
                    if target_type not in {"worker", "service_worker", "shared_worker"} or not session_id:
                        return
                    msg = {
                        "id": 1,
                        "method": "Emulation.setHardwareConcurrencyOverride",
                        "params": {"hardwareConcurrency": target_cores},
                    }
                    try:
                        await cdp_session.send(
                            "Target.sendMessageToTarget",
                            {"sessionId": session_id, "message": json.dumps(msg)},
                        )
                        await cdp_session.send(
                            "Target.sendMessageToTarget",
                            {
                                "sessionId": session_id,
                                "message": json.dumps(
                                    {"id": 2, "method": "Runtime.runIfWaitingForDebugger"}
                                ),
                            },
                        )
                    except Exception as exc:
                        logger.debug("Worker cores override failed: %s", exc)

                def _attached_handler(params) -> None:
                    asyncio.ensure_future(_on_attached(params))

                cdp_session.on("Target.attachedToTarget", _attached_handler)
                await cdp_session.send(
                    "Target.setAutoAttach",
                    {
                        "autoAttach": True,
                        # Browser-level raw CDP pauses/resumes workers.  Do not
                        # pause page-session targets here; Android Chrome can
                        # otherwise leave new tabs waiting during pool reuse.
                        "waitForDebuggerOnStart": False,
                        "flatten": False,
                    },
                )
                self._worker_target_sessions.append(cdp_session)
            except Exception as exc:
                logger.debug("CDP cores override failed for page: %s", exc)

        def _bind_cores_reapply_on_navigation(p: Page) -> None:
            if getattr(p, "_damru_cores_nav_bound", False):
                return
            setattr(p, "_damru_cores_nav_bound", True)

            def _on_frame_navigated(frame) -> None:
                if getattr(frame, "parent_frame", None) is None:
                    asyncio.ensure_future(_apply_cdp_cores(p))

            p.on("framenavigated", _on_frame_navigated)

        if needs_cores_override:
            # Do not keep a second raw browser-level CDP websocket open by
            # default. On Android Chrome 145 this can detach/close Playwright's
            # main CDP connection after startup. The page-session auto-attach
            # below is less aggressive; worker mismatches remain a warning.
            if os.environ.get("DAMRU_EXPERIMENTAL_RAW_WORKER_CDP") == "1":
                await _arm_browser_worker_cores()
            await _apply_cdp_cores(page)
            _bind_cores_reapply_on_navigation(page)
            def _on_page(p: Page) -> None:
                _bind_cores_reapply_on_navigation(p)
                asyncio.ensure_future(_apply_cdp_cores(p))
            self._context.on("page", _on_page)
            logger.info(
                "hardwareConcurrency: %d -> %d (CDP override)",
                actual_cores, target_cores,
            )
        else:
            logger.info("hardwareConcurrency already matches target (%d)", target_cores)

        if actual_mem != device.device_memory:
            if actual_mem is None:
                logger.info(
                    "deviceMemory: unavailable on startup probe; target=%s "
                    "(verified on secure pages via memory preload)",
                    device.device_memory,
                )
            else:
                logger.warning(
                    "deviceMemory: %s != target %s (check memory preload)",
                    actual_mem, device.device_memory,
                )
        else:
            logger.info("deviceMemory already matches target (%s)", actual_mem)

    async def _apply_storage_quota_override(self, device: AndroidDevice) -> None:
        """Override storage quota per-origin via CDP Storage domain.

        Chrome on redroid can leak host filesystem quota (hundreds of GB).
        This sets a mobile-like quota for each visited top-level origin.
        """
        if not self._context:
            return

        # Keep quota in common real-phone range close to Samsung reference.
        quota_gb = 64
        quota_bytes = quota_gb * 1024 * 1024 * 1024
        self._sync_storage_quota_bytes = quota_bytes

        async def _apply_for_origin(p: Page, origin: str) -> None:
            try:
                cdp = await self._context.new_cdp_session(p)  # type: ignore[union-attr]
                await cdp.send(
                    "Storage.overrideQuotaForOrigin",
                    {"origin": origin, "quotaSize": quota_bytes},
                )
            except Exception as exc:
                logger.debug("Storage quota override failed for %s: %s", origin, exc)

        def _bind_for_page(p: Page) -> None:
            seen = set()

            def _on_frame_navigated(frame) -> None:
                if getattr(frame, "parent_frame", None) is not None:
                    return
                raw_url = getattr(frame, "url", "") or ""
                parsed = urlparse(raw_url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    return
                origin = f"{parsed.scheme}://{parsed.netloc}"
                if origin in seen:
                    return
                seen.add(origin)
                asyncio.ensure_future(_apply_for_origin(p, origin))

            p.on("framenavigated", _on_frame_navigated)

        page = self._context.pages[0] if self._context.pages else None
        if page:
            _bind_for_page(page)

        self._context.on("page", _bind_for_page)
        logger.info("Storage quota override: %dGB per origin (CDP)", quota_gb)

    async def _apply_ua_override(
        self, device: AndroidDevice, chrome_version: Optional[str] = None,
        android_version: Optional[str] = None,
    ) -> None:
        """Override User-Agent, Chrome version, Client Hints, and locale via CDP.

        Uses the real emulator Android version and real installed Chrome version
        so Workers - which can't be CDP-overridden - see the same values as
        the main page.  Workers inherit the browser-level UA from the Chromium
        binary; CDP Emulation.setUserAgentOverride only affects page targets.
        Any mismatch between page and Worker is a detectable tell.

        Uses CDP Emulation.setUserAgentOverride which overrides:
          - navigator.userAgent (JS property)
          - HTTP User-Agent header
          - navigator.userAgentData (Client Hints API)
          - sec-ch-ua / sec-ch-ua-full-version-list HTTP headers
          - Accept-Language HTTP header (via acceptLanguage param)

        Also calls Emulation.setLocaleOverride to fix:
          - Intl.DateTimeFormat().resolvedOptions().locale
          - Intl.NumberFormat().resolvedOptions().locale

        The grease brand ("Not X Brand") and brand order are computed per
        Chrome major version to match Chromium's actual algorithm.

        This is a C++ level override - completely undetectable by JS.
        """
        if not self._context:
            return

        # Use real emulator Android version to match Workers (can't override
        # Worker UA via CDP - Emulation domain is page-target only).
        if android_version:
            android_ver = int(android_version)
            _VERSION_TO_SDK = {12: 31, 13: 33, 14: 34, 15: 35, 16: 36}
            sdk_ver = _VERSION_TO_SDK.get(android_ver, device.sdk_version)
        else:
            android_ver, sdk_ver = pick_random_android_version(device)
        chrome_ver, brand_info = pick_random_chrome_version(
            force_version=chrome_version,
        )

        ua = (
            f"Mozilla/5.0 (Linux; Android {android_ver}; {device.model}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_ver} Mobile Safari/537.36"
        )

        ua_metadata = {
            "brands": brand_info["brands"],
            "fullVersionList": brand_info["fullVersionList"],
            "fullVersion": chrome_ver,
            "platform": "Android",
            "platformVersion": f"{android_ver}.0.0",
            "architecture": "",
            "model": device.model,
            "mobile": True,
            "bitness": "",
        }

        # Build acceptLanguage from profile locale (bare tags, no q-values).
        # This overrides the HTTP Accept-Language header at C++ level.
        profile_locale = self._profile.locale if self._profile else "en-US"
        accept_lang_header = build_accept_language(profile_locale)
        # Strip q-values for CDP - only bare language tags needed
        accept_lang_tags = ",".join(
            p.split(";")[0].strip() for p in accept_lang_header.split(",")
        )

        ua_payload = {
            "userAgent": ua,
            "platform": "Linux armv8l",
            "acceptLanguage": accept_lang_tags,
            "userAgentMetadata": ua_metadata,
        }
        self._sync_ua_payload = ua_payload

        async def _apply_ua_cdp(p) -> None:
            try:
                s = await self._context.new_cdp_session(p)  # type: ignore[union-attr]
                await s.send("Emulation.setUserAgentOverride", ua_payload)
            except Exception as exc:
                logger.debug("UA override failed for page: %s", exc)

        page = self._context.pages[0] if self._context.pages else None
        if page:
            await _apply_ua_cdp(page)

        self._context.on(
            "page",
            lambda p: asyncio.ensure_future(_apply_ua_cdp(p)),
        )

        # Fix Intl.DateTimeFormat().resolvedOptions().locale via CDP.
        # Without this, AOSP/redroid defaults to en-US regardless of props.
        await self._apply_locale_override(profile_locale)

        logger.info(
            "UA override: Android %s (%s) Chrome/%s lang=%s",
            android_ver, device.model, chrome_ver, accept_lang_tags,
        )

        self._spoofed_android_version = android_ver
        self._spoofed_sdk_version = sdk_ver
        self._spoofed_chrome_version = chrome_ver

    async def _apply_locale_override(self, locale: str) -> None:
        """Override Intl locale via CDP Emulation.setLocaleOverride.

        Fixes Intl.DateTimeFormat().resolvedOptions().locale returning
        the system default (en-US on AOSP/redroid) instead of the target
        locale from the profile.

        This is a C++ level override - completely undetectable by JS.
        """
        if not self._context:
            return

        async def _apply_locale_cdp(p) -> None:
            try:
                s = await self._context.new_cdp_session(p)  # type: ignore[union-attr]
                await s.send("Emulation.setLocaleOverride", {"locale": locale})
            except Exception as exc:
                logger.debug("Locale override failed for page: %s", exc)

        page = self._context.pages[0] if self._context.pages else None
        if page:
            await _apply_locale_cdp(page)

        self._context.on(
            "page",
            lambda p: asyncio.ensure_future(_apply_locale_cdp(p)),
        )

    async def _apply_touch_emulation(self, device: AndroidDevice) -> None:
        """Enable touch emulation via CDP protocol.

        Fixes multiple emulator tells without any JS injection:
          - navigator.maxTouchPoints: 0/1 -> 5 (matching real phone)
          - CSS @media (pointer: coarse) -> matches (touch device)
          - CSS @media (any-pointer: coarse) -> matches
          - CSS @media (hover: none) -> matches (no mouse hover)
          - 'ontouchstart' in window -> true

        CDP Emulation.setTouchEmulationEnabled is a C++ level override -
        completely undetectable by fingerprinting scripts.
        """
        if not self._context:
            return

        touch_points = device.max_touch_points
        self._sync_touch_points = touch_points
        self._touch_points = touch_points

        async def _apply_touch_cdp(p: Page) -> None:
            try:
                cdp = await self._context.new_cdp_session(p)  # type: ignore[union-attr]
                await cdp.send("Emulation.setTouchEmulationEnabled", {
                    "enabled": True,
                    "maxTouchPoints": touch_points,
                })
            except Exception as exc:
                logger.debug("Touch emulation failed for page: %s", exc)

        def _bind_touch_reapply_on_navigation(p: Page) -> None:
            def _on_frame_navigated(frame) -> None:
                # Apply on top-level navigations because some Android builds
                # reset touch state after first real document commit.
                if getattr(frame, "parent_frame", None) is None:
                    asyncio.ensure_future(_apply_touch_cdp(p))
            p.on("framenavigated", _on_frame_navigated)

        page = self._context.pages[0] if self._context.pages else None
        if page:
            await _apply_touch_cdp(page)
            _bind_touch_reapply_on_navigation(page)

        def _on_page(p: Page) -> None:
            async def _setup() -> None:
                await _apply_touch_cdp(p)
                _bind_touch_reapply_on_navigation(p)
            asyncio.ensure_future(_setup())

        self._context.on("page", _on_page)
        logger.info("Touch emulation: maxTouchPoints=%d (CDP)", touch_points)

    async def _apply_network_emulation(self) -> None:
        """Override network connection type via CDP protocol.

        Fixes emulator tell: redroid reports type='ethernet' (no phone
        uses ethernet). Randomizes between wifi and cellular with
        realistic throughput values.

        CDP Network.emulateNetworkConditions overrides:
          - navigator.connection.type -> wifi/cellular
          - navigator.connection.effectiveType -> 4g
          - navigator.connection.rtt -> realistic mobile RTT
          - navigator.connection.downlink -> realistic mobile throughput

        Pure CDP override - no JS injection needed.
        """
        if not self._context:
            return
        logger.info("Network emulation skipped: using native Redroid connectivity for stability")
        return

        # Match the real Samsung reference profile captured for this project.
        conn_type = "wifi"
        latency_ms = 200
        download_bps = 1_700_000   # ~1.7 Mbps
        upload_bps = 1_000_000     # ~1 Mbps

        net_params = {
            "offline": False,
            "latency": latency_ms,
            "downloadThroughput": download_bps / 8,  # CDP wants bytes/sec
            "uploadThroughput": upload_bps / 8,
            "connectionType": conn_type,
        }
        self._sync_network_params = net_params

        async def _apply_net_cdp(p: Page) -> None:
            try:
                cdp = await self._context.new_cdp_session(p)  # type: ignore[union-attr]
                await cdp.send("Network.enable", {})
                # Avoid request throttling here. On Redroid/WSL it can trigger
                # ERR_NETWORK_CHANGED / ERR_INTERNET_DISCONNECTED mid-run.
                # overrideNetworkState is enough for navigator.connection.
                await cdp.send("Network.overrideNetworkState", net_params)
            except Exception as exc:
                logger.debug("Network emulation failed for page: %s", exc)

        def _bind_net_reapply_on_navigation(p: Page) -> None:
            def _on_frame_navigated(frame) -> None:
                if getattr(frame, "parent_frame", None) is None:
                    asyncio.ensure_future(_apply_net_cdp(p))
            p.on("framenavigated", _on_frame_navigated)

        page = self._context.pages[0] if self._context.pages else None
        if page:
            await _apply_net_cdp(page)
            _bind_net_reapply_on_navigation(page)

        def _on_page(p: Page) -> None:
            async def _setup() -> None:
                await _apply_net_cdp(p)
                _bind_net_reapply_on_navigation(p)
            asyncio.ensure_future(_setup())

        self._context.on("page", _on_page)
        logger.info("Network emulation: %s, latency=%dms (CDP)", conn_type, latency_ms)

    async def _query_native_gpu(self) -> str:
        """Query the emulator's native GPU via SurfaceFlinger.

        Returns the GLES line like 'Qualcomm, Adreno (TM) 640, OpenGL ES 3.2'.
        Generic approach - works on any rooted Android device/emulator.
        """
        if not self._adb:
            return ""
        out = await self._adb.shell(
            "dumpsys SurfaceFlinger 2>/dev/null | grep -i 'GLES'",
            timeout=5, allow_failure=True,
        )
        return out.strip()

    async def _arm_worker_core_override(self, target_cores: int) -> None:
        """Arm deterministic worker-core override using CDP target auto-attach.

        This is applied at the end of startup so later CDP setup cannot
        interfere with worker target attachment/routing.
        """
        if self._browser_worker_cdp_armed:
            logger.info("Worker cores override armed: %d (raw browser CDP active)", target_cores)
            return
        if not self._context:
            return

        async def _setup_for_page(p: Page) -> None:
            try:
                cdp = await self._context.new_cdp_session(p)  # type: ignore[union-attr]

                async def _on_attached(params) -> None:
                    info = params.get("targetInfo", {})
                    session_id = params.get("sessionId")
                    if info.get("type") != "worker" or not session_id:
                        return

                    try:
                        await cdp.send(
                            "Target.sendMessageToTarget",
                            {
                                "sessionId": session_id,
                                "message": json.dumps(
                                    {
                                        "id": 1,
                                        "method": "Emulation.setHardwareConcurrencyOverride",
                                        "params": {"hardwareConcurrency": target_cores},
                                    }
                                ),
                            },
                        )
                        # Apply UA override to Worker so userAgentData matches
                        # the main page (prevents Android version mismatch).
                        if self._sync_ua_payload:
                            await cdp.send(
                                "Target.sendMessageToTarget",
                                {
                                    "sessionId": session_id,
                                    "message": json.dumps(
                                        {
                                            "id": 2,
                                            "method": "Emulation.setUserAgentOverride",
                                            "params": self._sync_ua_payload,
                                        }
                                    ),
                                },
                            )
                        await cdp.send(
                            "Target.sendMessageToTarget",
                            {
                                "sessionId": session_id,
                                "message": json.dumps(
                                    {"id": 3, "method": "Runtime.runIfWaitingForDebugger"}
                                ),
                            },
                        )
                    except Exception as exc:
                        logger.debug("Worker target override failed: %s", exc)

                def _on_attach(params) -> None:
                    asyncio.ensure_future(_on_attached(params))

                cdp.on("Target.attachedToTarget", _on_attach)
                await cdp.send(
                    "Target.setAutoAttach",
                    {
                        "autoAttach": True,
                        "waitForDebuggerOnStart": True,
                        "flatten": False,
                    },
                )
                self._worker_target_sessions.append(cdp)
            except Exception as exc:
                logger.debug("Failed to arm worker core override: %s", exc)

        def _bind_rearm_on_navigation(p: Page) -> None:
            if getattr(p, "_damru_worker_rearm_bound", False):
                return
            setattr(p, "_damru_worker_rearm_bound", True)

            def _on_frame_navigated(frame) -> None:
                if getattr(frame, "parent_frame", None) is None:
                    asyncio.ensure_future(_setup_for_page(p))

            p.on("framenavigated", _on_frame_navigated)

        for page in self._context.pages:
            await _setup_for_page(page)
            _bind_rearm_on_navigation(page)

        def _on_page(p: Page) -> None:
            _bind_rearm_on_navigation(p)
            asyncio.ensure_future(_setup_for_page(p))

        self._context.on("page", _on_page)
        logger.info("Worker cores override armed: %d (CDP target auto-attach)", target_cores)

    async def _verify_worker_cores(self, target_cores: int, retries: int = 5) -> None:
        """Verify worker hardwareConcurrency and retry arming if needed.

        Uses JS read-only probing (no mutation) to confirm CDP worker override.
        """
        if not self._context or not self._context.pages:
            return

        page = self._context.pages[0]
        script = (
            "new Promise(r=>{"
            "const w=new Worker(URL.createObjectURL(new Blob(["
            "'setTimeout(()=>postMessage(navigator.hardwareConcurrency),100)'"
            "],{type:'application/javascript'})));"
            "w.onmessage=e=>r(e.data);"
            "})"
        )

        for attempt in range(1, retries + 1):
            try:
                worker_cores = await page.evaluate(script)
            except Exception:
                worker_cores = None

            if worker_cores == target_cores:
                logger.info("Worker cores verified: %s", worker_cores)
                return

            await self._arm_worker_core_override(target_cores)
            await sleep(0.5)

        logger.warning(
            "Worker cores still mismatched after retries (expected %d)",
            target_cores,
        )

    async def _warmup_tts_parallel(self) -> None:
        """TTS warmup on a SEPARATE tab - safe to run concurrently with CDP overrides.

        Creates a new tab, navigates to example.com, triggers speak(), waits
        for voices, then closes the tab. The main page is untouched.
        """
        if not self._context:
            return
        tts_page = None
        try:
            tts_page = await self._context.new_page()
            await tts_page.goto(
                "data:text/html,<title>damru-tts</title>",
                wait_until="domcontentloaded",
                timeout=5000,
            )
            cdp = await self._context.new_cdp_session(tts_page)
            await cdp.send("Runtime.enable")
            await cdp.send("Runtime.evaluate", {
                "expression": (
                    "try{const u=new SpeechSynthesisUtterance('test');"
                    "u.volume=0;speechSynthesis.speak(u);"
                    "setTimeout(()=>speechSynthesis.cancel(),500)"
                    "}catch(e){}"
                ),
                "userGesture": True,
                "awaitPromise": False,
            })
            await sleep(1.0)

            count = 0
            for attempt in range(3):
                result = await cdp.send("Runtime.evaluate", {
                    "expression": (
                        "(async()=>{"
                        "let v=speechSynthesis.getVoices();"
                        "if(v.length>0)return v.length;"
                        "await new Promise(r=>{"
                        "speechSynthesis.onvoiceschanged=()=>r();"
                        "setTimeout(r,8000)});"
                        "return speechSynthesis.getVoices().length})()"
                    ),
                    "awaitPromise": True,
                })
                count = result.get("result", {}).get("value", 0)
                if count > 0:
                    break
                logger.debug("TTS warm-up attempt %d: 0 voices, retrying...", attempt + 1)
                await cdp.send("Runtime.evaluate", {
                    "expression": (
                        "try{const u=new SpeechSynthesisUtterance('hello');"
                        "u.volume=0;speechSynthesis.speak(u);"
                        "setTimeout(()=>speechSynthesis.cancel(),500)"
                        "}catch(e){}"
                    ),
                    "userGesture": True,
                    "awaitPromise": False,
                })
                await sleep(1.5)

            logger.info("TTS warm-up: %d voices available", count)
        except Exception as exc:
            logger.info("TTS warm-up failed: %s", exc)
        finally:
            if tts_page:
                try:
                    await tts_page.close()
                except Exception:
                    pass

    async def _warmup_tts(self) -> None:
        """Trigger TTS engine initialization so getVoices() is populated.

        Android Chrome only loads voices from the system TTS engine after the
        first speechSynthesis.speak() call.  Chrome gates speak() behind
        user-activation (autoplay policy), so we use CDP Runtime.evaluate
        with userGesture=true to bypass the gate.

        We navigate to example.com (real HTTPS origin needed - data: and
        about:blank have opaque origins that don't trigger TTS binding),
        fire speak()+cancel() via CDP with user-gesture flag, then wait
        for onvoiceschanged.
        """
        if not self._context or not self._context.pages:
            return
        page = self._context.pages[0]
        try:
            if (page.url or "") in {"", "about:blank"}:
                await page.goto(
                    "data:text/html,<title>damru-tts</title>",
                    wait_until="domcontentloaded",
                    timeout=5000,
                )
            # Use CDP directly with userGesture: true so Chrome treats the
            # speak() call as if triggered by a tap - bypasses autoplay gate.
            cdp = await self._context.new_cdp_session(page)  # type: ignore[union-attr]

            # Ensure Runtime is enabled on this CDP session (the crPage.js
            # stealth patch only affects Playwright's internal session, but
            # be explicit to avoid any timing issues).
            await cdp.send("Runtime.enable")

            # Step 1: trigger speak() with user gesture flag.
            # Use non-empty text - empty string may be optimized away by Chrome.
            # Add a 500ms delay before cancel() to allow TTS service binding.
            await cdp.send("Runtime.evaluate", {
                "expression": (
                    "try{const u=new SpeechSynthesisUtterance('test');"
                    "u.volume=0;speechSynthesis.speak(u);"
                    "setTimeout(()=>speechSynthesis.cancel(),500)"
                    "}catch(e){}"
                ),
                "userGesture": True,
                "awaitPromise": False,
            })
            # Give Chrome time to bind to TTS service before querying voices.
            await sleep(1.0)

            # Step 2: wait for voices to load (onvoiceschanged or timeout).
            # Retry up to 3 times - TTS service binding is async and may need
            # multiple speak() triggers on some devices.
            count = 0
            for attempt in range(3):
                result = await cdp.send("Runtime.evaluate", {
                    "expression": (
                        "(async()=>{"
                        "let v=speechSynthesis.getVoices();"
                        "if(v.length>0)return v.length;"
                        "await new Promise(r=>{"
                        "speechSynthesis.onvoiceschanged=()=>r();"
                        "setTimeout(r,8000)});"
                        "return speechSynthesis.getVoices().length})()"
                    ),
                    "awaitPromise": True,
                })
                count = result.get("result", {}).get("value", 0)
                if count > 0:
                    break
                # Retry: re-trigger speak to kick TTS service binding.
                logger.debug("TTS warm-up attempt %d: 0 voices, retrying...", attempt + 1)
                await cdp.send("Runtime.evaluate", {
                    "expression": (
                        "try{const u=new SpeechSynthesisUtterance('hello');"
                        "u.volume=0;speechSynthesis.speak(u);"
                        "setTimeout(()=>speechSynthesis.cancel(),500)"
                        "}catch(e){}"
                    ),
                    "userGesture": True,
                    "awaitPromise": False,
                })
                await sleep(1.5)

            logger.info("TTS warm-up: %d voices available", count)
        except Exception as exc:
            logger.info("TTS warm-up failed: %s", exc)
