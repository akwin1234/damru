"""Apply a named Damru device profile to an existing ADB worker."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import asyncio
import hashlib
import random

from .adb import ADB
from .chrome import WEBVIEW_SHELL_PACKAGE, ChromeManager
from .devices import get_device
from .profiles import build_profile
from .proxy import build_accept_language
from .proxy_runtime import resolve_android_proxy
from .root import RootOps


@dataclass(frozen=True)
class AppliedDeviceProfile:
    """Summary of a profile applied to a running Android worker."""

    serial: str
    description: str
    device_name: str
    model: str
    screen_width: int
    screen_height: int
    density_dpi: int
    timezone: str
    locale: str
    android_http_proxy: Optional[str] = None
    chrome_package: Optional[str] = None
    chrome_version: Optional[str] = None
    chrome_note: str = ""


def _normalize_android_proxy(value: str | None) -> str | None:
    proxy = (value or "").strip()
    if proxy in {"", "null", ":0"}:
        return None
    return proxy


async def _current_android_proxy(adb: ADB) -> str | None:
    value = await adb.shell(
        "settings get global http_proxy",
        timeout=8,
        allow_failure=True,
    )
    return _normalize_android_proxy(value)


async def _apply_android_proxy(adb: ADB, proxy: str | None) -> None:
    proxy = _normalize_android_proxy(proxy)
    if not proxy:
        return
    host, _, port = proxy.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError("Android HTTP proxy must resolve to host:port.")
    await asyncio.gather(
        adb.shell(f"settings put global http_proxy {proxy}", allow_failure=True),
        adb.shell(f"settings put global global_http_proxy_host {host}", allow_failure=True),
        adb.shell(f"settings put global global_http_proxy_port {port}", allow_failure=True),
    )


async def _clear_android_proxy(adb: ADB) -> None:
    await asyncio.gather(
        adb.shell("settings put global http_proxy :0", allow_failure=True),
        adb.shell("settings delete global global_http_proxy_host", allow_failure=True),
        adb.shell("settings delete global global_http_proxy_port", allow_failure=True),
    )


async def _maybe_rotate_chrome(serial: str, chrome: ChromeManager, version: str | None = None) -> str:
    from .docker import RedroidManager

    docker = RedroidManager()
    current = await docker.get_installed_chrome_version(serial)
    apk_path = docker.find_chrome_apk(None, version=version)
    if current and version is None:
        for _ in range(8):
            candidate = docker.find_chrome_apk(None)
            if Path(candidate).name != current:
                apk_path = candidate
                break
    from .apk_assets import find_matching_webview_apk

    if Path(apk_path).is_dir() and find_matching_webview_apk(apk_path, apk_path) is None:
        raise RuntimeError(
            f"Matching WebView APK missing for Chrome {Path(apk_path).name}; current Chrome was kept."
        )
    await docker.install_chrome(serial, apk_path)
    await chrome.detect_package(retries=8, delay=1.0)
    installed = await docker.get_installed_chrome_version(serial)
    return installed or Path(apk_path).name

def _build_webview_user_agent(device, chrome_version: str | None) -> str:
    chrome_ver = chrome_version or "145.0.0.0"
    return (
        f"Mozilla/5.0 (Linux; Android {device.android_version}; {device.model} Build/{device.build_id}; wv) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
        f"Chrome/{chrome_ver} Mobile Safari/537.36"
    )

async def _configure_webview_shell(
    adb: ADB,
    root: RootOps,
    chrome: ChromeManager,
    device,
    chrome_flags: list[str],
    chrome_version: str | None,
    locale: str,
    accept_lang: str,
) -> None:
    if not hasattr(chrome, "webview_shell_installed"):
        return
    if not await chrome.webview_shell_installed(WEBVIEW_SHELL_PACKAGE):
        return
    await adb.shell(f"am force-stop {WEBVIEW_SHELL_PACKAGE}", allow_failure=True)
    await root.setup_memory_preload(WEBVIEW_SHELL_PACKAGE)
    await asyncio.gather(
        chrome.write_webview_command_line(
            chrome_flags,
            user_agent=_build_webview_user_agent(device, chrome_version),
        ),
        chrome.patch_webview_preferences(locale, accept_lang, WEBVIEW_SHELL_PACKAGE),
    )


async def force_device_profile(
    serial: str,
    device_name: str,
    *,
    proxy: str | None = None,
    http_proxy: str | None = None,
    timezone: str | None = None,
    locale: str | None = None,
    configure_chrome: bool = True,
    browser_package: str = "com.android.chrome",
    clear_chrome: bool = True,
    rotate_chrome: bool = False,
    chrome_version: str | None = None,
    apply_cpu: bool = True,
    apply_gpu: bool = True,
    apply_memory: bool = True,
    clear_proxy: bool = False,
) -> AppliedDeviceProfile:
    """Force a named Damru profile onto an existing rooted ADB worker.

    This is the deterministic counterpart to the CLI random-profile action.
    It applies Android identity props, release string, timezone, locale,
    display size/density, optional native GPU/memory/CPU spoofing, and optional
    Chromium command-line/preference setup. CDP overrides still belong to the
    runtime harness because they are target/page specific.
    """
    if clear_proxy and (proxy or http_proxy):
        raise ValueError("clear_proxy cannot be combined with proxy or http_proxy.")

    adb = ADB(serial)
    root = RootOps(adb)
    await root.check_root()

    device = get_device(device_name)
    current_http_proxy = None if clear_proxy else http_proxy
    if not clear_proxy and not proxy and not current_http_proxy:
        current_http_proxy = await _current_android_proxy(adb)
    route_text = ""
    if not clear_proxy and (proxy or current_http_proxy):
        route_text = await adb.shell(
            "ip route show default; ip route",
            timeout=8,
            allow_failure=True,
        )
    android_proxy = None
    if not clear_proxy:
        android_proxy = resolve_android_proxy(proxy, current_http_proxy, route_text=route_text)

    profile = build_profile(
        device,
        proxy=proxy,
        http_proxy=current_http_proxy,
        android_proxy=android_proxy,
        timezone=timezone,
        locale=locale,
    )
    sensor_seed = hashlib.sha256(
        f"{device.model}|{profile.timezone}|{profile.locale}|{random.getrandbits(64)}".encode()
    ).hexdigest()[:16]

    await root.apply_device_props(device, safe_only=True, parallel=True)
    await root.set_prop("persist.damru.sensor.seed", sensor_seed)
    await asyncio.gather(
        root.apply_version_release(device),
        root.apply_timezone(profile.timezone),
        root.apply_locale(profile.locale),
        _clear_android_proxy(adb) if clear_proxy else _apply_android_proxy(adb, profile.android_http_proxy),
        adb.shell(f"wm size {profile.screen_width}x{profile.screen_height}", allow_failure=True),
        adb.shell(f"wm density {profile.density_dpi}", allow_failure=True),
        adb.shell("settings put system accelerometer_rotation 0", allow_failure=True),
        adb.shell("settings put system user_rotation 0", allow_failure=True),
        root.apply_cpu_cores_spoof(device.hardware_concurrency) if apply_cpu else _noop(),
    )

    if apply_gpu:
        await root.apply_gpu_binary_spoof(device)

    if rotate_chrome and browser_package != "com.android.chrome":
        raise ValueError("rotate_chrome is only supported for com.android.chrome.")

    chrome_package: str | None = None
    chrome_version: str | None = None
    chrome_note = "chrome=skipped"
    if configure_chrome:
        chrome = ChromeManager(adb, package=browser_package)
        await chrome.detect_package(retries=8, delay=1.0)
        chrome_package = chrome.package
        if apply_memory:
            await root.apply_memory_spoof(device.device_memory)
            await root.setup_memory_preload(chrome.package)
        await chrome.force_stop()
        if rotate_chrome:
            chrome_version = await _maybe_rotate_chrome(serial, chrome, version=chrome_version)
            chrome_note = f"chrome={chrome_version}"
            await chrome.force_stop()
            if clear_chrome:
                await chrome.clear_all_data()
        else:
            chrome_version = await chrome.get_version()
            label = "chrome" if chrome.package == "com.android.chrome" else chrome.package
            chrome_note = f"{label}={chrome_version or 'kept'}"
            if clear_chrome:
                await chrome.clear_all_data()
        accept_lang = build_accept_language(profile.locale)
        await asyncio.gather(
            chrome.write_command_line(profile.chrome_flags),
            chrome.patch_preferences(profile.locale, accept_lang),
        )
        await _configure_webview_shell(
            adb,
            root,
            chrome,
            device,
            profile.chrome_flags,
            chrome_version,
            profile.locale,
            accept_lang,
        )
        if profile.android_http_proxy:
            await asyncio.gather(
                root.apply_webrtc_block(chrome.package),
                root.apply_webrtc_block(WEBVIEW_SHELL_PACKAGE),
            )
        await chrome.force_stop()

    return AppliedDeviceProfile(
        serial=serial,
        description=profile.description,
        device_name=device.name,
        model=device.model,
        screen_width=profile.screen_width,
        screen_height=profile.screen_height,
        density_dpi=profile.density_dpi,
        timezone=profile.timezone,
        locale=profile.locale,
        android_http_proxy=profile.android_http_proxy,
        chrome_package=chrome_package,
        chrome_version=chrome_version,
        chrome_note=chrome_note,
    )


async def _noop() -> None:
    return None
