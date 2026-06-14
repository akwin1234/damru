"""Profile builder for damru.

Assembles system props and Chrome CLI flags from a device profile
+ user options into a complete DamruProfile. Zero JS injection.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .devices import AndroidDevice, pick_screen_variant
from .proxy import build_accept_language, resolve_locale, resolve_proxy_geo, resolve_system_proxy
from .utils import logger


@dataclass
class DamruProfile:
    """Complete spoofing profile for a damru session."""

    device: AndroidDevice
    system_props: Dict[str, str]
    chrome_flags: List[str]
    screen_width: int
    screen_height: int
    density_dpi: int
    timezone: str
    locale: str
    android_http_proxy: Optional[str] = None  # "host:port" for system proxy
    description: str = ""


def build_profile(
    device: AndroidDevice,
    proxy: Optional[str] = None,
    http_proxy: Optional[str] = None,
    android_proxy: Optional[str] = None,
    timezone: Optional[str] = None,
    locale: Optional[str] = None,
    chrome_version: Optional[str] = None,
    webrtc_block: bool = False,
) -> DamruProfile:
    """Build a complete spoofing profile for the given device.

    Args:
        device: Target device identity.
        proxy: Proxy URL for GeoIP resolution (e.g. "socks5://host:port").
        http_proxy: HTTP proxy for Android system (e.g. "host:port" or
            "http://host:port"). Auto-derived from proxy if None.
        timezone: IANA timezone. Auto-detected from proxy IP if None.
        locale: BCP-47 locale. Auto-detected from timezone if None.
        chrome_version: Installed Chrome/WebView version used for the native
            command-line user-agent. Callers that can inspect the device should
            pass the real installed version before Chrome starts.
    """
    # Resolve Android system HTTP proxy first. When present, use that same
    # path for GeoIP so browser timezone matches the proxy Chrome actually uses.
    android_proxy = android_proxy or resolve_system_proxy(proxy, http_proxy)

    # Auto-detect timezone/locale through an authenticated URL when present.
    # Android settings store only host:port, so using that stripped value for
    # GeoIP can fail against username/password proxies.
    geo_proxy = http_proxy or proxy or android_proxy
    if geo_proxy and (timezone is None or locale is None):
        geo = resolve_proxy_geo(geo_proxy)
        if timezone is None:
            timezone = geo["timezone"]
        if locale is None:
            locale = geo["locale"]

    if timezone is None:
        timezone = "America/New_York"
    if locale is None:
        locale = resolve_locale(timezone)

    system_props = device.system_props()
    chrome_flags = _build_chrome_flags(device, timezone, locale, chrome_version, webrtc_block)

    # Randomize screen resolution for devices with WQHD+/FHD+ modes
    sw, sh, sdpi = pick_screen_variant(device)
    logger.info("Screen: %dx%d @%ddpi (device default: %dx%d @%d)",
                sw, sh, sdpi, device.screen_width, device.screen_height, device.density_dpi)

    description = f"{device.name} ({device.brand} {device.model}, Android {device.android_version})"

    return DamruProfile(
        device=device,
        system_props=system_props,
        chrome_flags=chrome_flags,
        screen_width=sw,
        screen_height=sh,
        density_dpi=sdpi,
        timezone=timezone,
        locale=locale,
        android_http_proxy=android_proxy,
        description=description,
    )


def _build_chrome_flags(
    device: AndroidDevice,
    timezone: str,
    locale: str,
    chrome_version: Optional[str] = None,
    webrtc_block: bool = False,
) -> List[str]:
    """Assemble Chrome command-line flags.

    NOTE: On Android "user" builds (e.g. MuMu), Chrome does NOT read
    /data/local/tmp/chrome-command-line. These flags are still written
    as a best-effort for "userdebug" builds (e.g. AVD with Google APIs).
    The actual proxy is set via Android system settings, not --proxy-server.
    """
    accept_lang = build_accept_language(locale)

    flags: List[str] = [
        # Skip first run dialogs
        "--disable-fre",
        "--no-first-run",
        "--no-default-browser-check",
        # Android CDP attaches through this localabstract socket. Without it,
        # Chrome may visibly launch but Playwright cannot connect.
        "--remote-debugging-socket-name=chrome_devtools_remote",
        # Stealth
        "--disable-blink-features=AutomationControlled",
        "--disable-popup-blocking",
        "--disable-translate",
        "--disable-sync",
        "--metrics-recording-only",
        # Locale
        f"--lang={locale}",
        # navigator.languages must NOT contain q-values - only lang tags.
        # Chrome auto-assigns q-weights in the HTTP Accept-Language header.
        f"--accept-lang={','.join(p.split(';')[0].strip() for p in accept_lang.split(','))}",
        # WebRTC: keep enabled but force routing through proxy if webrtc_block is False (default).
        # When webrtc_block is True, we use default policy (as iptables drops all UDP).
        f"--force-webrtc-ip-handling-policy={'default_public_and_private_interfaces' if webrtc_block else 'disable_non_proxied_udp'}",
        "--enforce-webrtc-ip-permission-check",
        # Rendering
        "--force-color-profile=srgb",
        "--dns-prefetch-disable",
        # Prevent throttling
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        # Network hardening (useful when proxy is active)
        "--disable-background-networking",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-breakpad",
        "--disable-domain-reliability",
        "--no-pings",
        # Reduce V8 heap ceiling on Android to mobile-like range.
        "--js-flags=--max-old-space-size=1024",
        # Expose fake media devices so enumerateDevices includes videoinput.
        "--use-fake-device-for-media-stream",
        # Avoid Redroid BatteryService test-mode instability and 100%-charging tells.
        "--disable-battery-status-api",
        # Keep SpeechSynthesis path enabled on Android builds that gate it.
        "--enable-speech-synthesis-api",
        # Enable Web APIs that real Chrome Android exposes.
        # navigator.credentials, navigator.mediaDevices, navigator.bluetooth,
        # navigator.usb, navigator.serial appear undefined otherwise.
        "--enable-blink-features=WebUSB,WebSerial,Bluetooth,WebBluetooth,CredentialManager,MediaCapture",
        # Remove desktop-only GL extensions that SwiftShader exposes.
        # Only disable extensions that NEVER appear on real mobile GPUs.
        "--disable-gl-extensions=GL_ANGLE_polygon_mode",
    ]

    # -- TLS fingerprint randomization -----------------------------
    # Randomize Chrome's JA3/JA4 TLS fingerprint per session by:
    # 1. Blacklisting random non-essential TLS 1.2 cipher suites
    # 2. Toggling PostQuantumKyber (changes supported_groups extension)
    # This produces ~186 unique JA3 hashes from a single Chrome binary.
    tls_flags, tls_disabled = _randomize_tls_flags()
    flags.extend(tls_flags)

    # Force the full user-agent string at native level so first Chrome
    # page load already has correct platform (Linux armv8l) instead of
    # the Redroid default. CDP overrides apply after page load, which
    # leaves a detectable window where navigator.platform leaks.
    chrome_ver = _effective_chrome_version(chrome_version)
    ua = (
        'Mozilla/5.0 (Linux; Android ' + device.android_version + '; ' + device.model + ') '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/' + chrome_ver + ' Mobile Safari/537.36'
    )
    flags.append('--user-agent=' + ua)

    # Disabled features (collected into ONE flag - Chrome only reads the LAST one)
    # NOTE: DnsOverHttps is NOT disabled - we WANT DoH through the proxy
    # to prevent DNS leak detection by BrowserScan.
    disabled_features = [
        "BatteryStatus",
        "WebRtcHideLocalIpsWithMdns",
        "PaintHolding",
    ]
    disabled_features.extend(tls_disabled)

    flags.append(f"--disable-features={','.join(disabled_features)}")

    return flags


def _effective_chrome_version(chrome_version: Optional[str]) -> str:
    """Return a concrete Chrome version for native command-line flags."""
    value = (chrome_version or "").strip()
    if value and value.lower() != "unknown" and "..." not in value:
        return value
    return "145.0.0.0"


# -- TLS cipher suites safe to blacklist ------------------------
# These are non-essential TLS 1.2 ciphers that Chrome 145 offers.
# Removing 1-3 per session changes the JA3 cipher suite component
# ? different JA3 hash per session.
# All are legacy (RSA key exchange or CBC mode) or optional
# (CHACHA20 where GCM alternatives exist). Removing any subset
# still leaves enough ciphers for all modern sites.
_BLACKLISTABLE_CIPHERS = [
    0x002F,  # TLS_RSA_WITH_AES_128_CBC_SHA (legacy RSA+CBC)
    0x0035,  # TLS_RSA_WITH_AES_256_CBC_SHA (legacy RSA+CBC)
    0x009C,  # TLS_RSA_WITH_AES_128_GCM_SHA256 (RSA, no PFS)
    0x009D,  # TLS_RSA_WITH_AES_256_GCM_SHA384 (RSA, no PFS)
    0xC013,  # TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA (ECDHE+CBC)
    0xC014,  # TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA (ECDHE+CBC)
    0xCCA8,  # TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305 (optional)
    0xCCA9,  # TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305 (optional)
]


def _randomize_tls_flags() -> tuple:
    """Generate random TLS-related Chrome flags to vary JA3 fingerprint.

    Returns:
        (extra_flags, extra_disabled_features) tuple.
    """
    extra_flags: List[str] = []
    extra_disabled: List[str] = []

    # 1. Randomly blacklist 1-3 non-essential cipher suites per session.
    #    C(8,1)+C(8,2)+C(8,3) = 8+28+56 = 92 cipher combos.
    num_to_blacklist = random.randint(1, 3)
    blacklisted = random.sample(_BLACKLISTABLE_CIPHERS, num_to_blacklist)
    hex_list = ",".join(f"0x{c:04x}" for c in blacklisted)
    extra_flags.append(f"--cipher-suite-blacklist={hex_list}")
    logger.info("TLS randomization: blacklisted %d ciphers [%s]",
                num_to_blacklist, hex_list)

    # 2. Randomly toggle PostQuantumKyber (X25519Kyber768 key exchange).
    #    This changes the supported_groups TLS extension ? different JA3.
    #    ~50% chance to disable = doubles the fingerprint space.
    if random.random() < 0.5:
        extra_disabled.append("PostQuantumKyber")
        logger.info("TLS randomization: PostQuantumKyber disabled")

    return extra_flags, extra_disabled
