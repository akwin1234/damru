"""Proxy configuration and GeoIP resolution for damru.

Resolves timezone and locale from proxy exit IP to ensure Chrome's
timezone matches the proxy location (BrowserScan checks this).

On Android, Chrome on "user" builds ignores command-line flags including
--proxy-server. Instead, we set the system-wide HTTP proxy via
`settings put global http_proxy host:port`. This requires an HTTP proxy.
"""
from __future__ import annotations

from typing import Dict, Optional
from urllib.parse import urlparse

from .utils import logger

# GeoIP cache: proxy URL → {timezone, locale, country_code, ip}
_geo_cache: Dict[str, Dict[str, str]] = {}

# Timezone → BCP-47 locale mapping (ported from fingerprint-chromium)
_TIMEZONE_LOCALE_MAP: Dict[str, str] = {
    # Asia Pacific
    "Asia/Manila": "fil-PH",
    "Asia/Tokyo": "ja-JP",
    "Asia/Seoul": "ko-KR",
    "Asia/Shanghai": "zh-CN",
    "Asia/Hong_Kong": "zh-HK",
    "Asia/Taipei": "zh-TW",
    "Asia/Singapore": "en-SG",
    "Asia/Kolkata": "en-IN",
    "Asia/Calcutta": "en-IN",
    "Asia/Jakarta": "id-ID",
    "Asia/Bangkok": "th-TH",
    "Asia/Ho_Chi_Minh": "vi-VN",
    "Asia/Kuala_Lumpur": "ms-MY",
    "Asia/Dhaka": "bn-BD",
    "Asia/Karachi": "ur-PK",
    "Asia/Dubai": "ar-AE",
    "Asia/Riyadh": "ar-SA",
    "Asia/Jerusalem": "he-IL",
    "Asia/Tehran": "fa-IR",
    # Americas
    "America/New_York": "en-US",
    "America/Chicago": "en-US",
    "America/Denver": "en-US",
    "America/Los_Angeles": "en-US",
    "America/Anchorage": "en-US",
    "Pacific/Honolulu": "en-US",
    "America/Toronto": "en-CA",
    "America/Vancouver": "en-CA",
    "America/Mexico_City": "es-MX",
    "America/Sao_Paulo": "pt-BR",
    "America/Buenos_Aires": "es-AR",
    "America/Bogota": "es-CO",
    "America/Lima": "es-PE",
    "America/Santiago": "es-CL",
    # Europe
    "Europe/London": "en-GB",
    "Europe/Paris": "fr-FR",
    "Europe/Berlin": "de-DE",
    "Europe/Madrid": "es-ES",
    "Europe/Rome": "it-IT",
    "Europe/Amsterdam": "nl-NL",
    "Europe/Brussels": "nl-BE",
    "Europe/Zurich": "de-CH",
    "Europe/Vienna": "de-AT",
    "Europe/Stockholm": "sv-SE",
    "Europe/Oslo": "nb-NO",
    "Europe/Copenhagen": "da-DK",
    "Europe/Helsinki": "fi-FI",
    "Europe/Warsaw": "pl-PL",
    "Europe/Prague": "cs-CZ",
    "Europe/Budapest": "hu-HU",
    "Europe/Bucharest": "ro-RO",
    "Europe/Athens": "el-GR",
    "Europe/Istanbul": "tr-TR",
    "Europe/Moscow": "ru-RU",
    "Europe/Kiev": "uk-UA",
    "Europe/Lisbon": "pt-PT",
    "Europe/Dublin": "en-IE",
    # Africa / Middle East
    "Africa/Cairo": "ar-EG",
    "Africa/Lagos": "en-NG",
    "Africa/Johannesburg": "en-ZA",
    "Africa/Nairobi": "en-KE",
    "Africa/Casablanca": "fr-MA",
    # Oceania
    "Australia/Sydney": "en-AU",
    "Australia/Melbourne": "en-AU",
    "Australia/Perth": "en-AU",
    "Pacific/Auckland": "en-NZ",
}


def resolve_locale(timezone: str) -> str:
    """Map IANA timezone to BCP-47 locale. Falls back to 'en-US'."""
    return _TIMEZONE_LOCALE_MAP.get(timezone, "en-US")


def build_accept_language(locale: str) -> str:
    """Build a realistic Accept-Language header from a locale.

    For non-English locales in bilingual countries (Philippines, etc.),
    includes English as a high-priority secondary language since many
    users in these countries browse in English.
    """
    lang = locale.split("-")[0]

    if locale == "en-US":
        return "en-US,en;q=0.9"
    elif lang == "en":
        return f"{locale},en-US;q=0.9,en;q=0.8"
    elif lang == "fil":
        # Filipino locale: fil as secondary (NOT en-PH — that's artificial and suspicious)
        # Real Android Chrome in PH sends: fil-PH,fil;q=0.9,en-US;q=0.8,en;q=0.7
        return f"{locale},{lang};q=0.9,en-US;q=0.8,en;q=0.7"
    elif locale == "en-PH":
        # English (Philippines): valid PH business format — q appears once at the end
        # en-PH and en-US share top priority (q=1.0), only en is at q=0.8
        return "en-PH,en-US,en;q=0.8"
    else:
        return f"{locale},{lang};q=0.9,en-US;q=0.8,en;q=0.7"


def resolve_system_proxy(
    proxy: Optional[str] = None,
    http_proxy: Optional[str] = None,
) -> Optional[str]:
    """Resolve the HTTP proxy string for Android system settings.

    Android's `settings put global http_proxy` only supports HTTP CONNECT
    proxies in `host:port` format. This function resolves the right value.

    Priority:
        1. Explicit http_proxy parameter (host:port or http://host:port)
        2. If proxy is http://, extract host:port from it
        3. If proxy is bare host:port, use it directly
        4. If proxy is socks5://, try port-1 as HTTP (common pattern)
        5. None if nothing available

    Returns:
        "host:port" string suitable for `settings put global http_proxy`,
        or None if no HTTP proxy is available.
    """
    # 1. Explicit HTTP proxy
    if http_proxy:
        return _extract_host_port(http_proxy)

    if not proxy:
        return None

    # 2. Check if it's already bare host:port format (e.g. "198.20.189.134:50000")
    if "://" not in proxy and ":" in proxy:
        # Validate it's actually host:port
        parts = proxy.split(":")
        if len(parts) == 2 and parts[1].isdigit():
            return proxy  # Already in correct format

    parsed = urlparse(proxy)
    scheme = (parsed.scheme or "").lower()
    host = parsed.hostname or ""
    port = parsed.port

    if not host or not port:
        return None

    # 3. HTTP proxy URL
    if scheme in ("http", "https"):
        return f"{host}:{port}"

    # 4. SOCKS5 → try HTTP on port-1 (common proxy provider pattern)
    if scheme in ("socks5", "socks5h"):
        http_port = port - 1
        logger.info(
            "SOCKS5 proxy detected. Using HTTP proxy on port %d "
            "(common pattern: HTTP=SOCKS-1). Pass http_proxy= to override.",
            http_port,
        )
        return f"{host}:{http_port}"

    return None


def _extract_host_port(url: str) -> str:
    """Extract host:port from a URL or bare host:port string."""
    if "://" in url:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or 80
        return f"{host}:{port}"
    # Already in host:port format
    return url


def resolve_proxy_geo(proxy: str, retries: int = 3) -> Dict[str, str]:
    """Resolve timezone, locale, country from proxy exit IP via GeoIP lookup.

    Connects THROUGH the proxy to GeoIP services. Results are cached per proxy URL.
    Uses HTTPS endpoints (works through HTTP CONNECT proxies) with retries
    for rotating proxies that drop connections.
    """
    if proxy in _geo_cache:
        return _geo_cache[proxy]

    defaults = {
        "timezone": "America/New_York",
        "locale": "en-US",
        "country_code": "US",
        "ip": "",
    }

    # GeoIP endpoints — HTTPS first (HTTP CONNECT proxy tunnels HTTPS fine,
    # but can't proxy plain HTTP). Fallback to HTTP for SOCKS5 proxies.
    _ENDPOINTS = [
        ("https://ipapi.co/json/", lambda d: (d.get("timezone"), d.get("country_code"), d.get("ip"))),
        ("https://ipinfo.io/json", lambda d: (d.get("timezone"), d.get("country"), d.get("ip"))),
        ("http://ip-api.com/json/?fields=query,timezone,countryCode", lambda d: (d.get("timezone"), d.get("countryCode"), d.get("query"))),
    ]

    try:
        import requests
        import time

        # Build proxy dict for requests
        proxy_url = proxy
        if "socks5://" in proxy and "socks5h://" not in proxy:
            proxy_url = proxy.replace("socks5://", "socks5h://")
        proxies = {"http": proxy_url, "https": proxy_url}

        last_err = None
        for attempt in range(1, retries + 1):
            for url, extractor in _ENDPOINTS:
                try:
                    resp = requests.get(url, proxies=proxies, timeout=10)
                    data = resp.json()
                    tz, cc, ip = extractor(data)

                    if tz:
                        locale = resolve_locale(tz)
                        result = {
                            "timezone": tz,
                            "locale": locale,
                            "country_code": cc or "US",
                            "ip": ip or "",
                        }
                        _geo_cache[proxy] = result
                        logger.info("Proxy GeoIP: %s -> %s (%s) via %s",
                                    proxy.split("@")[-1][:30], tz, locale,
                                    url.split("/")[2])
                        return result
                except Exception as e:
                    last_err = e
                    continue

            if attempt < retries:
                time.sleep(2)
                logger.debug("GeoIP retry %d/%d...", attempt, retries)

        logger.warning("GeoIP lookup failed after %d retries: %s (using defaults)", retries, last_err)
        _geo_cache[proxy] = defaults
        return defaults
    except Exception as e:
        logger.warning("GeoIP lookup failed: %s (using defaults)", e)
        _geo_cache[proxy] = defaults
        return defaults
