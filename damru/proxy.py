"""Proxy configuration and GeoIP resolution for damru.

Resolves timezone and locale from proxy exit IP to ensure Chrome's
timezone matches the proxy location (BrowserScan checks this).

On Android, Chrome on "user" builds ignores command-line flags including
--proxy-server. Instead, we set the system-wide HTTP proxy via
`settings put global http_proxy host:port`. This requires an HTTP proxy.
"""
from __future__ import annotations

import random
import secrets
from typing import Dict, List, Optional
from urllib.parse import quote, unquote, urlparse, urlunparse

from .utils import logger

# GeoIP cache: proxy URL -> {timezone, locale, country_code, ip}. Disabled by
# default for rotating proxies; callers may opt in only for static proxies.
_geo_cache: Dict[str, Dict[str, str]] = {}

_COUNTRY_LOCALE_VARIANTS: Dict[str, List[str]] = {
    # CLDR exceptional reservations / unknown territory fallbacks
    "AC": ["en-AC"], "CP": ["en-US"], "CQ": ["en-CQ"], "DG": ["en-DG"],
    "EA": ["es-EA"], "IC": ["es-IC"], "TA": ["en-TA"], "ZZ": ["en-US"],
    # North America
    "US": ["en-US"], "CA": ["en-CA", "fr-CA"], "MX": ["es-MX"],
    "BM": ["en-BM"], "GL": ["kl-GL", "da-GL"], "PM": ["fr-PM"], "UM": ["en-UM"],
    # Central America / Caribbean
    "BZ": ["en-BZ", "es-BZ"], "CR": ["es-CR"], "SV": ["es-SV"],
    "GT": ["es-GT"], "HN": ["es-HN"], "NI": ["es-NI"], "PA": ["es-PA"],
    "AG": ["en-AG"], "AI": ["en-AI"], "AW": ["nl-AW", "pap-AW"],
    "BB": ["en-BB"], "BL": ["fr-BL"], "BQ": ["nl-BQ"], "BS": ["en-BS"],
    "CU": ["es-CU"], "CW": ["nl-CW", "pap-CW"], "DM": ["en-DM"],
    "DO": ["es-DO"], "GD": ["en-GD"], "GP": ["fr-GP"], "HT": ["ht-HT", "fr-HT"],
    "JM": ["en-JM"], "KN": ["en-KN"], "KY": ["en-KY"], "LC": ["en-LC"],
    "MF": ["fr-MF"], "MQ": ["fr-MQ"], "MS": ["en-MS"], "PR": ["es-PR", "en-PR"],
    "SX": ["nl-SX", "en-SX"], "TC": ["en-TC"], "TT": ["en-TT"], "VC": ["en-VC"],
    "VG": ["en-VG"], "VI": ["en-VI"],
    # South America
    "AR": ["es-AR"], "BO": ["es-BO"], "BR": ["pt-BR"], "CL": ["es-CL"],
    "CO": ["es-CO"], "EC": ["es-EC"], "FK": ["en-FK"], "GF": ["fr-GF"],
    "GY": ["en-GY"], "PE": ["es-PE"], "PY": ["es-PY"], "SR": ["nl-SR"],
    "UY": ["es-UY"], "VE": ["es-VE"],
    # Western / Northern / Southern Europe
    "AD": ["ca-AD", "es-AD"], "AT": ["de-AT"], "AX": ["sv-AX"], "BE": ["nl-BE", "fr-BE"],
    "CH": ["de-CH", "fr-CH", "it-CH"], "DE": ["de-DE"], "DK": ["da-DK"],
    "ES": ["es-ES", "ca-ES"], "FI": ["fi-FI", "sv-FI"], "FO": ["fo-FO", "da-FO"],
    "FR": ["fr-FR"], "GB": ["en-GB"], "GG": ["en-GG"], "GI": ["en-GI"],
    "GR": ["el-GR"], "IE": ["en-IE", "ga-IE"], "IM": ["en-IM"], "IS": ["is-IS"],
    "IT": ["it-IT"], "JE": ["en-JE"], "LI": ["de-LI"], "LU": ["fr-LU", "de-LU", "lb-LU"],
    "MC": ["fr-MC"], "MT": ["mt-MT", "en-MT"], "NL": ["nl-NL", "en-NL"],
    "NO": ["nb-NO", "nn-NO"], "PT": ["pt-PT"], "SE": ["sv-SE"], "SM": ["it-SM"],
    "VA": ["it-VA"],
    # Central / Eastern Europe
    "AL": ["sq-AL"], "BA": ["bs-BA", "hr-BA", "sr-BA"], "BG": ["bg-BG"],
    "BY": ["be-BY", "ru-BY"], "CZ": ["cs-CZ"], "EE": ["et-EE"], "HR": ["hr-HR"],
    "HU": ["hu-HU"], "LT": ["lt-LT"], "LV": ["lv-LV"], "MD": ["ro-MD", "ru-MD"],
    "ME": ["sr-ME"], "MK": ["mk-MK", "sq-MK"], "PL": ["pl-PL"], "RO": ["ro-RO"],
    "RS": ["sr-RS"], "RU": ["ru-RU"], "SI": ["sl-SI"], "SK": ["sk-SK"],
    "UA": ["uk-UA", "ru-UA"], "XK": ["sq-XK", "sr-XK"],
    # Middle East / Central Asia
    "AE": ["ar-AE", "en-AE"], "AF": ["fa-AF", "ps-AF"], "AM": ["hy-AM"],
    "AZ": ["az-AZ"], "BH": ["ar-BH"], "CY": ["el-CY", "tr-CY"], "GE": ["ka-GE"],
    "IL": ["he-IL", "ar-IL", "en-IL"], "IQ": ["ar-IQ", "ku-IQ"], "IR": ["fa-IR"],
    "JO": ["ar-JO"], "KG": ["ky-KG", "ru-KG"], "KW": ["ar-KW"], "KZ": ["kk-KZ", "ru-KZ"],
    "LB": ["ar-LB", "fr-LB"], "OM": ["ar-OM"], "PS": ["ar-PS"], "QA": ["ar-QA"],
    "SA": ["ar-SA"], "SY": ["ar-SY"], "TJ": ["tg-TJ", "ru-TJ"], "TM": ["tk-TM"],
    "TR": ["tr-TR"], "UZ": ["uz-UZ", "ru-UZ"], "YE": ["ar-YE"],
    # South Asia
    "BD": ["bn-BD", "en-BD"], "BT": ["dz-BT", "en-BT"], "IN": ["en-IN", "hi-IN", "ta-IN", "te-IN", "bn-IN", "mr-IN"],
    "LK": ["si-LK", "ta-LK", "en-LK"], "MV": ["dv-MV", "en-MV"], "NP": ["ne-NP"],
    "PK": ["ur-PK", "en-PK"],
    # East / Southeast Asia
    "BN": ["ms-BN", "en-BN"], "CC": ["en-CC"], "CN": ["zh-CN"], "CX": ["en-CX"], "HK": ["zh-HK", "en-HK"],
    "ID": ["id-ID"], "JP": ["ja-JP"], "KH": ["km-KH"], "KP": ["ko-KP"],
    "KR": ["ko-KR"], "LA": ["lo-LA"], "MM": ["my-MM"], "MN": ["mn-MN"],
    "MO": ["zh-MO", "pt-MO"], "MY": ["ms-MY", "en-MY", "zh-MY", "ta-MY"],
    "PH": ["en-PH", "fil-PH"], "SG": ["en-SG", "zh-SG", "ms-SG", "ta-SG"],
    "TH": ["th-TH"], "TL": ["pt-TL", "tet-TL"], "TW": ["zh-TW"], "VN": ["vi-VN"],
    # Oceania
    "AS": ["en-AS", "sm-AS"], "AU": ["en-AU"], "CK": ["en-CK"], "FJ": ["en-FJ"],
    "FM": ["en-FM"], "GU": ["en-GU"], "KI": ["en-KI"], "MH": ["en-MH"],
    "MP": ["en-MP"], "NC": ["fr-NC"], "NF": ["en-NF"], "NR": ["en-NR"],
    "NU": ["en-NU"], "NZ": ["en-NZ"], "PF": ["fr-PF"], "PG": ["en-PG"],
    "PN": ["en-PN"], "PW": ["en-PW"], "SB": ["en-SB"], "TK": ["en-TK"],
    "TO": ["en-TO", "to-TO"], "TV": ["en-TV"], "VU": ["en-VU", "fr-VU"],
    "WF": ["fr-WF"], "WS": ["sm-WS", "en-WS"],
    # Africa
    "AO": ["pt-AO"], "AQ": ["en-AQ"], "BF": ["fr-BF"], "BI": ["rn-BI", "fr-BI"], "BJ": ["fr-BJ"],
    "BV": ["nb-BV"], "BW": ["en-BW"], "CD": ["fr-CD", "ln-CD", "sw-CD"], "CF": ["fr-CF"],
    "CG": ["fr-CG"], "CI": ["fr-CI"], "CM": ["fr-CM", "en-CM"], "CV": ["pt-CV"],
    "DJ": ["fr-DJ", "ar-DJ"], "DZ": ["ar-DZ", "fr-DZ"], "EG": ["ar-EG"],
    "EH": ["ar-EH"], "ER": ["ti-ER", "ar-ER"], "ET": ["am-ET"], "GA": ["fr-GA"], "GS": ["en-GS"],
    "GH": ["en-GH"], "GM": ["en-GM"], "GN": ["fr-GN"], "GQ": ["es-GQ", "fr-GQ"],
    "GW": ["pt-GW"], "HM": ["en-HM"], "IO": ["en-IO"], "KE": ["en-KE", "sw-KE"], "KM": ["ar-KM", "fr-KM"],
    "LR": ["en-LR"], "LS": ["en-LS"], "LY": ["ar-LY"], "MA": ["ar-MA", "fr-MA"],
    "MG": ["mg-MG", "fr-MG"], "ML": ["fr-ML"], "MR": ["ar-MR", "fr-MR"],
    "MU": ["en-MU", "fr-MU"], "MW": ["en-MW"], "MZ": ["pt-MZ"], "NA": ["en-NA"],
    "NE": ["fr-NE"], "NG": ["en-NG"], "RE": ["fr-RE"], "RW": ["rw-RW", "fr-RW", "en-RW"],
    "SC": ["en-SC", "fr-SC"], "SD": ["ar-SD", "en-SD"], "SH": ["en-SH"],
    "SJ": ["nb-SJ"], "SL": ["en-SL"], "SN": ["fr-SN"], "SO": ["so-SO", "ar-SO"], "SS": ["en-SS"],
    "ST": ["pt-ST"], "SZ": ["en-SZ"], "TD": ["fr-TD", "ar-TD"], "TF": ["fr-TF"], "TG": ["fr-TG"],
    "TN": ["ar-TN", "fr-TN"], "TZ": ["sw-TZ", "en-TZ"], "UG": ["en-UG", "sw-UG"],
    "YT": ["fr-YT"], "ZA": ["en-ZA", "af-ZA", "zu-ZA"], "ZM": ["en-ZM"], "ZW": ["en-ZW"],
}

# Timezone -> BCP-47 locale mapping (ported from fingerprint-chromium)
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

def resolve_locale_for_geo(timezone: str, country_code: Optional[str] = None) -> str:
    """Choose a realistic browser locale for a GeoIP country/timezone.

    The timezone must always match the proxy exit. Locale is allowed to vary
    within real phone/browser usage for that country when the user has not set
    one explicitly.
    """
    country = (country_code or "").upper()
    candidates = _COUNTRY_LOCALE_VARIANTS.get(country)
    if not candidates:
        return resolve_locale(timezone)
    return random.choice(candidates)


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
        # Filipino locale: fil as secondary (NOT en-PH - that's artificial and suspicious)
        # Real Android Chrome in PH sends: fil-PH,fil;q=0.9,en-US;q=0.8,en;q=0.7
        return f"{locale},{lang};q=0.9,en-US;q=0.8,en;q=0.7"
    elif locale == "en-PH":
        # English (Philippines): valid PH business format - q appears once at the end.
        # en-PH and en-US share top priority (q=1.0), only en is at q=0.8.
        return "en-PH,en-US,en;q=0.8"
    else:
        return f"{locale},{lang};q=0.9,en-US;q=0.8,en;q=0.7"

def make_sticky_proxy_url(proxy: Optional[str], ttl_minutes: int = 30) -> Optional[str]:
    """Return a provider-sticky proxy URL when a safe automatic form is known.

    DataImpulse rotating gateways can change exit IP on each request, which can
    create timezone/IP mismatches on fingerprinting pages. Their documented
    session parameters are appended to the username: `sessid.<id>` and
    `sessttl.<minutes>`. Unknown providers are left unchanged.
    """
    if not proxy or "://" not in proxy:
        return proxy
    parsed = urlparse(proxy)
    host = (parsed.hostname or "").lower()
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if "dataimpulse.com" not in host or not username:
        return proxy
    if ";sessid." in username or ";sessttl." in username:
        return proxy

    session_id = f"damru{secrets.token_hex(4)}"
    sticky_user = f"{username};sessid.{session_id};sessttl.{ttl_minutes}"

    auth = quote(sticky_user, safe=";._-")
    if password:
        auth = f"{auth}:{quote(password, safe='')}"
    netloc = auth
    if parsed.hostname:
        netloc = f"{netloc}@{parsed.hostname}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"

    sticky = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    logger.info("DataImpulse sticky proxy session enabled (ttl=%dm)", ttl_minutes)
    return sticky


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

    # 2. Check if it's already bare host:port format (e.g. "proxy.example:50000")
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

    # 4. SOCKS5 -> try HTTP on port-1 (common proxy provider pattern)
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


def resolve_proxy_geo(proxy: str, retries: int = 3, use_cache: bool = False) -> Dict[str, str]:
    """Resolve timezone, locale, country from proxy exit IP via GeoIP lookup.

    Connects THROUGH the proxy to GeoIP services. Results are cached per proxy URL.
    Uses HTTPS endpoints (works through HTTP CONNECT proxies) with retries
    for rotating proxies that drop connections.
    """
    proxy = make_sticky_proxy_url(proxy) or proxy

    if use_cache and proxy in _geo_cache:
        return _geo_cache[proxy]

    defaults = {
        "timezone": "America/New_York",
        "locale": "en-US",
        "country_code": "US",
        "ip": "",
    }

    # GeoIP endpoints - HTTPS first (HTTP CONNECT proxy tunnels HTTPS fine,
    # but can't proxy plain HTTP). Fallback to HTTP for SOCKS5 proxies.
    _ENDPOINTS = [
        ("https://ipapi.co/json/", lambda d: (d.get("timezone"), d.get("country_code"), d.get("ip"))),
        ("https://ipinfo.io/json", lambda d: (d.get("timezone"), d.get("country"), d.get("ip"))),
        ("http://ip-api.com/json/fields=query,timezone,countryCode", lambda d: (d.get("timezone"), d.get("countryCode"), d.get("query"))),
    ]

    try:
        import requests
        import time

        # Build proxy dict for requests. Bare host:port values are Android
        # system HTTP proxies, including local CONNECT bridges. Resolve GeoIP
        # through the same path Android Chrome will use to avoid timezone leaks.
        proxy_url = proxy
        if "://" not in proxy_url:
            proxy_url = f"http://{proxy_url}"
        if "socks5://" in proxy_url and "socks5h://" not in proxy_url:
            proxy_url = proxy_url.replace("socks5://", "socks5h://")
        proxies = {"http": proxy_url, "https": proxy_url}

        last_err = None
        for attempt in range(1, retries + 1):
            for url, extractor in _ENDPOINTS:
                try:
                    resp = requests.get(url, proxies=proxies, timeout=10)
                    data = resp.json()
                    tz, cc, ip = extractor(data)

                    if tz:
                        locale = resolve_locale_for_geo(tz, cc)
                        result = {
                            "timezone": tz,
                            "locale": locale,
                            "country_code": cc or "US",
                            "ip": ip or "",
                        }
                        if use_cache:
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
        if use_cache:
            _geo_cache[proxy] = defaults
        return defaults
    except Exception as e:
        logger.warning("GeoIP lookup failed: %s (using defaults)", e)
        if use_cache:
            _geo_cache[proxy] = defaults
        return defaults
