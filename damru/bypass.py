"""CDN TLS edge-layer bypass for damru.

ROOT CAUSE:
  Certain domains are protected by CDN TLS Bot Manager at the edge layer.
  Chrome's TLS/JA3 fingerprint (BoringSSL) may be blocked.

  UPDATE (Feb 22 2026): CDN TLS also fingerprints urllib3's JA3 as bot.
  Now using curl_cffi with browser TLS impersonation (Chrome/Safari/Edge)
  for requests. Falls back to urllib3 requests if curl_cffi unavailable.

SOLUTION (Persistent bypass — Approach 16 + TLS impersonation):
  Arm a persistent page.route() handler that intercepts ALL document
  requests to a specific domain. Every navigation (GET or POST) is
  replayed through curl_cffi (browser TLS) or Python requests,
  and the response is served back to Chrome via route.fulfill().

Usage (sync):
    from damru.bypass import arm_bypass_sync
    arm_bypass_sync(page, domain="target.com", http_proxy="host:port")
    page.goto(url)

Usage (async):
    await arm_bypass_async(page, domain="target.com", http_proxy="host:port")
    await page.goto(url)
"""
from __future__ import annotations

import random
from typing import Optional

from .utils import logger


# ── TLS impersonation via curl_cffi ────────────────────────────

_CURL_CFI_AVAILABLE = False
try:
    from curl_cffi import requests as cffi_requests
    _CURL_CFI_AVAILABLE = True
except ImportError:
    cffi_requests = None

_BROWSER_PROFILES = [
    "chrome120", "chrome124", "chrome131",
    "safari17_0", "safari18_0",
    "edge101",
]


def _pick_browser_profile() -> str:
    """Select a random browser TLS profile for this session."""
    return random.choice(_BROWSER_PROFILES)


def _create_session(browser_profile: Optional[str] = None):
    """Create an HTTP session with browser TLS impersonation."""
    if _CURL_CFI_AVAILABLE:
        profile = browser_profile or _pick_browser_profile()
        session = cffi_requests.Session(impersonate=profile)
        return session, f"curl_cffi({profile})"
    else:
        import requests as req_lib
        session = req_lib.Session()
        return session, "urllib3"


def _read_page_headers_sync(page) -> dict:
    """Read UA and Accept-Language from a SYNC Playwright page."""
    ua = "Mozilla/5.0 (Linux; Android 14) Chrome/145.0.7632.75 Mobile Safari/537.36"
    accept_lang = "en-US,en;q=0.9"
    try:
        ua = page.evaluate("navigator.userAgent") or ua
    except Exception:
        pass
    try:
        langs = page.evaluate("navigator.languages")
        if langs and len(langs) > 0:
            parts = []
            for i, lang in enumerate(langs):
                if i == 0:
                    parts.append(lang)
                else:
                    q = round(max(0.1, 1.0 - i * 0.1), 1)
                    parts.append(f"{lang};q={q}")
            accept_lang = ",".join(parts)
    except Exception:
        pass
    return {"User-Agent": ua, "Accept-Language": accept_lang}


async def _read_page_headers_async(page) -> dict:
    """Read UA and Accept-Language from an ASYNC Playwright page."""
    ua = "Mozilla/5.0 (Linux; Android 14) Chrome/145.0.7632.75 Mobile Safari/537.36"
    accept_lang = "en-US,en;q=0.9"
    try:
        ua = await page.evaluate("navigator.userAgent") or ua
    except Exception:
        pass
    try:
        langs = await page.evaluate("navigator.languages")
        if langs and len(langs) > 0:
            parts = []
            for i, lang in enumerate(langs):
                if i == 0:
                    parts.append(lang)
                else:
                    q = round(max(0.1, 1.0 - i * 0.1), 1)
                    parts.append(f"{lang};q={q}")
            accept_lang = ",".join(parts)
    except Exception:
        pass
    return {"User-Agent": ua, "Accept-Language": accept_lang}


# ---------------------------------------------------------------------------
# Persistent bypass logic
# ---------------------------------------------------------------------------

def _make_bypass_headers(hdrs: dict, route_request) -> dict:
    """Build request headers for Python replay from Chrome's FULL request headers."""
    chrome_hdrs = dict(route_request.headers)
    chrome_hdrs["User-Agent"] = hdrs["User-Agent"]
    chrome_hdrs["Accept-Language"] = hdrs["Accept-Language"]

    for drop in ("host", "connection", "content-length"):
        chrome_hdrs.pop(drop, None)
    return chrome_hdrs


def _make_proxies(http_proxy: Optional[str]) -> Optional[dict]:
    """Build requests-compatible proxy dict."""
    if not http_proxy:
        return None
    proxy_url = f"http://{http_proxy}" if "://" not in http_proxy else http_proxy
    return {"http": proxy_url, "https": proxy_url}


def arm_bypass_sync(page, domain: str, http_proxy: Optional[str] = None) -> None:
    """Arm persistent CDN TLS TLS bypass for ALL navigations to a domain."""
    hdrs = _read_page_headers_sync(page)
    session, tls_label = _create_session()
    logger.info("CDN TLS bypass TLS backend: %s", tls_label)
    proxies = _make_proxies(http_proxy)

    get_proxy_configs: list[tuple[Optional[dict], str]] = [(None, "direct")]
    if proxies:
        get_proxy_configs.append((proxies, "proxy"))

    def _do_request(method, url, fwd, post_data, px, timeout=12):
        if method == "POST":
            return session.post(url, headers=fwd, data=post_data, proxies=px, timeout=timeout, allow_redirects=True)
        else:
            return session.get(url, headers=fwd, proxies=px, timeout=timeout, allow_redirects=True)

    def _is_sensor_challenge(r) -> bool:
        return r.status_code == 403 and b"bazadebezolkohpepadr" in r.content

    def _fulfill(route, r, method, label, url):
        logger.info("CDN TLS persistent bypass [%s %s]: %s -> %d", method, label, url[:60], r.status_code)
        resp_headers = dict(r.headers)
        for hdr in ("Transfer-Encoding", "Content-Encoding", "Content-Length"):
            resp_headers.pop(hdr, None)
        route.fulfill(status=r.status_code, headers=resp_headers, body=r.content)

    _sensor_served = {}
    pattern = f"https://{domain}/**"

    def _handler(route):
        req = route.request
        if req.resource_type != "document":
            route.continue_()
            return

        url = req.url
        method = req.method.upper()
        post_data = req.post_data
        fwd = _make_bypass_headers(hdrs, req)
        url_path = url.split("")[0]

        if url_path in _sensor_served:
            route.continue_()
            return

        if method == "POST":
            route.continue_()
            return

        for px, label in get_proxy_configs:
            try:
                get_timeout = 12 if px else 20
                r = _do_request(method, url, fwd, post_data, px, get_timeout)
                if _is_sensor_challenge(r) and url_path not in _sensor_served:
                    _sensor_served[url_path] = True
                    _fulfill(route, r, method, f"sensor-challenge({label})", url)
                    return
                _fulfill(route, r, method, label, url)
                return
            except Exception as e:
                logger.warning("CDN TLS bypass [%s %s] failed: %s", method, label, str(e)[:120])

        route.continue_()

    page.route(pattern, _handler)
    page._cdn_bypass_pattern = pattern


async def arm_bypass_async(page, domain: str, http_proxy: Optional[str] = None) -> None:
    """Arm persistent CDN TLS TLS bypass for ALL navigations (ASYNC)."""
    hdrs = await _read_page_headers_async(page)
    session, tls_label = _create_session()
    proxies = _make_proxies(http_proxy)

    get_proxy_configs: list[tuple[Optional[dict], str]] = [(None, "direct")]
    if proxies:
        get_proxy_configs.append((proxies, "proxy"))

    def _do_request_async(method, url, fwd, post_data, px, timeout=12):
        if method == "POST":
            return session.post(url, headers=fwd, data=post_data, proxies=px, timeout=timeout, allow_redirects=True)
        else:
            return session.get(url, headers=fwd, proxies=px, timeout=timeout, allow_redirects=True)

    def _is_sensor_challenge(r) -> bool:
        return r.status_code == 403 and b"bazadebezolkohpepadr" in r.content

    async def _fulfill_async(route, r, method, label, url):
        logger.info("CDN TLS persistent bypass [%s %s]: %s -> %d", method, label, url[:60], r.status_code)
        resp_headers = dict(r.headers)
        for hdr in ("Transfer-Encoding", "Content-Encoding", "Content-Length"):
            resp_headers.pop(hdr, None)
        await route.fulfill(status=r.status_code, headers=resp_headers, body=r.content)

    _sensor_served = {}
    pattern = f"https://{domain}/**"

    async def _handler(route):
        req = route.request
        if req.resource_type != "document":
            await route.continue_()
            return

        url = req.url
        method = req.method.upper()
        post_data = req.post_data
        fwd = _make_bypass_headers(hdrs, req)
        url_path = url.split("")[0]

        if url_path in _sensor_served:
            await route.continue_()
            return

        if method == "POST":
            await route.continue_()
            return

        for px, label in get_proxy_configs:
            try:
                get_timeout = 12 if px else 20
                r = _do_request_async(method, url, fwd, post_data, px, get_timeout)
                if _is_sensor_challenge(r) and url_path not in _sensor_served:
                    _sensor_served[url_path] = True
                    await _fulfill_async(route, r, method, f"sensor-challenge({label})", url)
                    return
                await _fulfill_async(route, r, method, label, url)
                return
            except Exception as e:
                logger.warning("CDN TLS bypass [%s %s] failed: %s", method, label, str(e)[:120])

        await route.continue_()

    await page.route(pattern, _handler)
    page._cdn_bypass_pattern = pattern


async def disarm_bypass_async(page) -> None:
    pat = getattr(page, "_cdn_bypass_pattern", None)
    if pat:
        try:
            await page.unroute(pat)
        except Exception:
            pass


def disarm_bypass_sync(page) -> None:
    pat = getattr(page, "_cdn_bypass_pattern", None)
    if pat:
        try:
            page.unroute(pat)
        except Exception:
            pass


def fetch_html_bypass(url: str, user_agent: str, accept_language: str, http_proxy: Optional[str] = None, timeout: int = 20) -> tuple[int, str]:
    req_headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": accept_language,
        "Upgrade-Insecure-Requests": "1",
    }
    proxy_configs: list[Optional[dict]] = []
    if http_proxy:
        proxy_url = f"http://{http_proxy}" if "://" not in http_proxy else http_proxy
        proxy_configs.append({"http": proxy_url, "https": proxy_url})
    proxy_configs.append(None)

    for proxies in proxy_configs:
        try:
            sess, _ = _create_session()
            r = sess.get(url, headers=req_headers, proxies=proxies, timeout=timeout)
            return r.status_code, r.text
        except Exception:
            pass
    return 0, ""


async def goto_with_bypass(page, url: str, http_proxy: Optional[str] = None, timeout: int = 30000, wait_until: str = "domcontentloaded") -> tuple[int, str]:
    hdrs = await _read_page_headers_async(page)
    status_code, html_body = fetch_html_bypass(url, user_agent=hdrs["User-Agent"], accept_language=hdrs["Accept-Language"], http_proxy=http_proxy)
    if status_code != 200 or not html_body:
        resp = await page.goto(url, timeout=timeout, wait_until=wait_until)
        return (resp.status if resp else 0), await page.title()
    html_bytes = html_body.encode("utf-8")
    route_pattern = url.split("")[0] + "*"
    async def _route_handler(route):
        if route.request.resource_type == "document":
            await route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html_bytes)
        else:
            await route.continue_()
    await page.route(route_pattern, _route_handler)
    try:
        resp = await page.goto(url, timeout=timeout, wait_until=wait_until)
        return (resp.status if resp else 200), await page.title()
    finally:
        await page.unroute(route_pattern)


def goto_with_bypass_sync(page, url: str, http_proxy: Optional[str] = None, timeout: int = 30000, wait_until: str = "domcontentloaded") -> tuple[int, str]:
    hdrs = _read_page_headers_sync(page)
    status_code, html_body = fetch_html_bypass(url, user_agent=hdrs["User-Agent"], accept_language=hdrs["Accept-Language"], http_proxy=http_proxy)
    if status_code != 200 or not html_body:
        resp = page.goto(url, timeout=timeout, wait_until=wait_until)
        return (resp.status if resp else 0), page.title()
    html_bytes = html_body.encode("utf-8")
    route_pattern = url.split("")[0] + "*"
    def _route_handler(route):
        if route.request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html_bytes)
        else:
            route.continue_()
    page.route(route_pattern, _route_handler)
    try:
        resp = page.goto(url, timeout=timeout, wait_until=wait_until)
        return (resp.status if resp else 200), page.title()
    finally:
        page.unroute(route_pattern)
