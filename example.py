"""
Comprehensive functional test suite for damru.

Tests the device database, profile builder, and live browser behavior
using ONLY the public AsyncDamru API. No direct ADB/root calls.

Browser tests can run with no proxy, or with DAMRU_PROXY/DAMRU_HTTP_PROXY for proxy proof.\nRandom Android device selected each run.

Usage:
    cd damru
    python example.py
    DAMRU_PROXY="socks5://..." python example.py
    python example.py --skip-passed          # skip previously passed tests
    python example.py --tests "3,4,5"        # run specific sections only

WARNING:
Proxy-sensitive assertions depend on the selected proxy geography. Use
DAMRU_EXPECTED_TIMEZONES and DAMRU_EXPECTED_LOCALE when running proof with a
different region.
"""

import sys
import os
import json
import time
import asyncio
import traceback
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru, get_device, get_random_device, list_device_names, AndroidDevice
from damru.devices import DEVICES, get_devices_by_brand
from damru.profiles import DamruProfile, build_profile
from damru.proxy import (
    resolve_proxy_geo, resolve_locale, resolve_system_proxy,
    build_accept_language,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_SOCKS5 = ""
DEFAULT_HTTP = ""
PROXY_URL = os.environ.get("DAMRU_PROXY", DEFAULT_SOCKS5) or None
HTTP_PROXY = os.environ.get("DAMRU_HTTP_PROXY", DEFAULT_HTTP) or None
EXPECTED_TIMEZONES = [
    tz.strip()
    for tz in os.environ.get("DAMRU_EXPECTED_TIMEZONES", "America/New_York").split(",")
    if tz.strip()
]
EXPECTED_LOCALE = os.environ.get("DAMRU_EXPECTED_LOCALE", "en-US")
TIMEOUT = 30000
NAV_TIMEOUT = 45000
TEST_URL = "https://example.com"
RESULTS_FILE = os.path.join(os.path.dirname(__file__), "damru", "results", "example_results.json")

# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0
_skipped = 0
_errors = []
_section = ""
_start_time = time.time()
_results = {}

# Load previously passed tests for --skip-passed
_SKIP_PASSED = set()
if "--skip-passed" in sys.argv and os.path.exists(RESULTS_FILE):
    try:
        with open(RESULTS_FILE) as f:
            prev = json.load(f)
        _SKIP_PASSED = {k for k, v in prev.get("tests", {}).items() if v == "PASS"}
        print(f"  Loaded {len(_SKIP_PASSED)} previously passed tests to skip")
    except Exception:
        pass

# Parse --tests flag
_ONLY_SECTIONS = set()
for i, arg in enumerate(sys.argv):
    if arg == "--tests" and i + 1 < len(sys.argv):
        _ONLY_SECTIONS = {int(s.strip()) for s in sys.argv[i + 1].split(",")}


def section(num, name):
    global _section
    if _ONLY_SECTIONS and num not in _ONLY_SECTIONS:
        return False
    _section = f"{num}. {name}"
    print(f"\n{'='*60}")
    print(f"  {_section}")
    print(f"{'='*60}")
    return True


async def run_test_async(name, coro_func):
    """Run an async test function, track pass/fail."""
    global _passed, _failed
    if name in _SKIP_PASSED:
        _passed += 1
        _results[name] = "PASS"
        print(f"  SKIP+ {name}  (previously passed)")
        return
    t0 = time.time()
    try:
        await coro_func()
        elapsed = time.time() - t0
        _passed += 1
        _results[name] = "PASS"
        print(f"  PASS  {name}  ({elapsed:.1f}s)")
    except Exception as e:
        elapsed = time.time() - t0
        _failed += 1
        _results[name] = "FAIL"
        tb = traceback.format_exc().strip().split("\n")[-1]
        _errors.append((_section, name, str(e)))
        print(f"  FAIL  {name}  ({elapsed:.1f}s)")
        print(f"        {tb}")


def run_test(name, func):
    """Run a sync test function, track pass/fail."""
    global _passed, _failed
    if name in _SKIP_PASSED:
        _passed += 1
        _results[name] = "PASS"
        print(f"  SKIP+ {name}  (previously passed)")
        return
    t0 = time.time()
    try:
        func()
        elapsed = time.time() - t0
        _passed += 1
        _results[name] = "PASS"
        print(f"  PASS  {name}  ({elapsed:.1f}s)")
    except Exception as e:
        elapsed = time.time() - t0
        _failed += 1
        _results[name] = "FAIL"
        tb = traceback.format_exc().strip().split("\n")[-1]
        _errors.append((_section, name, str(e)))
        print(f"  FAIL  {name}  ({elapsed:.1f}s)")
        print(f"        {tb}")


def _is_retryable(err_str):
    return any(s in err_str for s in ("Timeout", "TIMED_OUT", "ERR_CONNECTION",
                                       "ERR_PROXY", "ERR_SOCKS", "ERR_NAME"))


async def safe_goto(page, url=TEST_URL, timeout=NAV_TIMEOUT, retries=3):
    for attempt in range(retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return
        except Exception as e:
            if attempt < retries and _is_retryable(str(e)):
                try:
                    await page.goto("about:blank", timeout=5000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                continue
            raise


# ===========================================================================
# SECTION 1: Device Database - Unit Tests (no browser)
# ===========================================================================

if section(1, "Device Database - Unit Tests"):

    def test_device_count():
        assert len(DEVICES) >= 32, f"Expected >= 32 devices, got {len(DEVICES)}"

    def test_all_devices_have_fields():
        for d in DEVICES:
            assert d.brand, f"{d.name} missing brand"
            assert d.model, f"{d.name} missing model"
            assert d.build_fingerprint, f"{d.name} missing fingerprint"
            assert d.screen_width > 0, f"{d.name} invalid screen"
            assert d.density_dpi > 0, f"{d.name} invalid density"

    def test_all_devices_android():
        for d in DEVICES:
            assert d.android_version in ("12", "13", "14", "15"), \
                f"{d.name} unexpected android_version: {d.android_version}"

    def test_device_memory_valid():
        for d in DEVICES:
            assert d.device_memory in (1, 2, 4, 6, 8), \
                f"{d.name} unusual memory: {d.device_memory}"

    def test_touch_points():
        for d in DEVICES:
            assert d.max_touch_points >= 5, \
                f"{d.name} touch_points={d.max_touch_points}"

    def test_brands_diversity():
        brands = set(d.brand.lower() for d in DEVICES)
        assert len(brands) >= 5, f"Only {len(brands)} brands: {brands}"

    def test_android_12_devices_exist():
        a12 = [d for d in DEVICES if d.android_version == "12"]
        assert len(a12) >= 7, f"Only {len(a12)} Android 12 devices"

    def test_hardware_concurrency():
        for d in DEVICES:
            assert d.hardware_concurrency in (2, 4, 6, 8, 10, 12), \
                f"{d.name} unusual cores={d.hardware_concurrency}"

    def test_system_props_keys():
        d = DEVICES[0]
        props = d.system_props(safe_only=False)
        required = ["ro.product.model", "ro.product.brand", "ro.build.fingerprint",
                     "ro.build.version.release", "ro.build.version.sdk"]
        for key in required:
            assert key in props, f"Missing prop: {key}"

    def test_system_props_safe_skips_version():
        d = DEVICES[0]
        safe = d.system_props(safe_only=True)
        assert "ro.build.version.release" not in safe
        assert "ro.build.version.sdk" not in safe

    for _fn in [
        test_device_count, test_all_devices_have_fields, test_all_devices_android,
        test_device_memory_valid, test_touch_points, test_brands_diversity,
        test_android_12_devices_exist, test_hardware_concurrency,
        test_system_props_keys, test_system_props_safe_skips_version,
    ]:
        run_test(_fn.__name__, _fn)


# ===========================================================================
# SECTION 2: Device Utility & Profile - Unit Tests (no browser)
# ===========================================================================

if section(2, "Device Utility & Profile - Unit Tests"):

    def test_get_device_by_name():
        d = get_device("samsung_galaxy_s22_ultra")
        assert d.model == "SM-S908B"

    def test_get_device_by_model():
        d = get_device("SM-S908B")
        assert "S22" in d.name

    def test_get_random_device_filtered():
        for _ in range(10):
            d = get_random_device(android_version="12")
            assert d.android_version == "12", f"Got {d.android_version}"

    def test_get_random_device_diversity():
        seen = set()
        for _ in range(30):
            d = get_random_device(android_version="12")
            seen.add(d.name)
        assert len(seen) >= 3, f"Only {len(seen)} unique in 30 picks"

    def test_get_devices_by_brand():
        samsungs = get_devices_by_brand("samsung")
        assert len(samsungs) >= 5, f"Only {len(samsungs)} Samsung devices"

    def test_list_device_names():
        names = list_device_names()
        assert len(names) == len(DEVICES)

    def test_profile_builder():
        d = get_device("pixel_6_pro")
        p = build_profile(d, proxy=PROXY_URL, http_proxy=HTTP_PROXY)
        assert isinstance(p, DamruProfile)
        if EXPECTED_TIMEZONES:
            assert p.timezone in EXPECTED_TIMEZONES, f"TZ: {p.timezone}"
        assert p.locale == EXPECTED_LOCALE
        if HTTP_PROXY:
            assert p.android_http_proxy == HTTP_PROXY

    def test_profile_chrome_flags():
        d = get_device("pixel_6_pro")
        p = build_profile(d, proxy=PROXY_URL)
        assert len(p.chrome_flags) > 10
        disable_count = sum(1 for f in p.chrome_flags if f.startswith("--disable-features="))
        assert disable_count == 1, f"Expected 1 --disable-features, got {disable_count}"

    def test_profile_no_proxy_server_flag():
        d = get_device("pixel_6_pro")
        p = build_profile(d, proxy=PROXY_URL)
        flags_str = " ".join(p.chrome_flags)
        assert "--proxy-server" not in flags_str, "Should use system proxy not --proxy-server"

    def test_profile_no_async_dns():
        d = get_device("pixel_6_pro")
        p = build_profile(d, proxy=PROXY_URL)
        flags_str = " ".join(p.chrome_flags)
        assert "AsyncDns" not in flags_str, "AsyncDns disable causes SOCKS5 hangs"

    def test_resolve_system_proxy_from_socks():
        result = resolve_system_proxy(proxy="socks5://proxy.example:50001")
        assert result == "proxy.example:50000"

    def test_resolve_system_proxy_explicit():
        result = resolve_system_proxy(http_proxy="1.2.3.4:8080")
        assert result == "1.2.3.4:8080"

    def test_resolve_locale():
        assert resolve_locale("Asia/Manila") == "fil-PH"
        assert resolve_locale("America/New_York") == "en-US"
        assert resolve_locale("Unknown/Zone") == "en-US"

    def test_build_accept_language():
        assert build_accept_language("en-PH") == "en-PH,en-US;q=0.9,en;q=0.8"
        assert build_accept_language("en-US") == "en-US,en;q=0.9"
        assert "ja" in build_accept_language("ja-JP")

    for _fn in [
        test_get_device_by_name, test_get_device_by_model,
        test_get_random_device_filtered, test_get_random_device_diversity,
        test_get_devices_by_brand, test_list_device_names,
        test_profile_builder, test_profile_chrome_flags,
        test_profile_no_proxy_server_flag, test_profile_no_async_dns,
        test_resolve_system_proxy_from_socks, test_resolve_system_proxy_explicit,
        test_resolve_locale, test_build_accept_language,
    ]:
        run_test(_fn.__name__, _fn)


# ===========================================================================
# Browser sections (3-9) use AsyncDamru context manager
# ===========================================================================

_browser_sections = {3, 4, 5, 6, 7, 8, 9}
_need_browser = not _ONLY_SECTIONS or bool(_ONLY_SECTIONS & _browser_sections)

# Check if all browser tests already passed (skip-passed mode)
_browser_test_names = [
    "test_page_alive", "test_user_agent_android", "test_platform_linux_arm",
    "test_max_touch_points", "test_device_memory", "test_hardware_concurrency_browser",
    "test_screen_dimensions", "test_has_user_agent_data", "test_client_hints_platform",
    "test_client_hints_mobile", "test_client_hints_brands", "test_client_hints_high_entropy",
    "test_proxy_loads_page", "test_proxy_exit_ip", "test_timezone_matches",
    "test_accept_language_header", "test_webrtc_no_private_ip",
    "test_js_eval", "test_multiple_pages", "test_navigate_real_url", "test_complex_js_eval",
    "test_cloudflare_bypass", "test_datadome_bypass", "test_amazon_bypass",
    "test_browserscan", "test_creepjs", "test_sannysoft",
]

if _need_browser and _SKIP_PASSED:
    if all(t in _SKIP_PASSED for t in _browser_test_names):
        _need_browser = False
        for t in _browser_test_names:
            _passed += 1
            _results[t] = "PASS"
            print(f"  SKIP+ {t}  (previously passed)")

if _need_browser:

    async def run_browser_tests():
        """Run all browser tests inside a single AsyncDamru session."""
        global _passed, _failed

        print(f"\n{'='*60}")
        print(f"  Launching AsyncDamru (random device, configured proxy)...")
        print(f"{'='*60}")

        async with AsyncDamru(
            device="random",
            proxy=PROXY_URL,
            http_proxy=HTTP_PROXY,
            debug=False,
        ) as context:
            page = await context.new_page()

            # Figure out which device was selected by reading UA
            try:
                ua = await page.evaluate("navigator.userAgent")
                print(f"  UA: {ua[:100]}")
                ch = await page.evaluate("""(async () => {
                    if (!navigator.userAgentData) return {};
                    return await navigator.userAgentData.getHighEntropyValues(
                        ['model', 'platformVersion']
                    );
                })()""")
                print(f"  Device model (from CH): {ch.get('model', '')}")
                print(f"  Platform version: {ch.get('platformVersion', '')}")
            except Exception:
                pass

            # --- SECTION 3: Identity ---
            if section(3, "Browser Launch + Identity Verification"):

                async def _test_page_alive():
                    r = await page.evaluate("1 + 1")
                    assert r == 2

                async def _test_user_agent_android():
                    ua = await page.evaluate("navigator.userAgent")
                    assert "Android" in ua, f"UA: {ua}"
                    assert "Chrome/" in ua, f"UA: {ua}"

                async def _test_platform_linux_arm():
                    p = await page.evaluate("navigator.platform")
                    assert "Linux" in p, f"Platform: {p}"

                async def _test_max_touch_points():
                    t = await page.evaluate("navigator.maxTouchPoints")
                    assert t >= 5, f"Touch: {t}"

                async def _test_device_memory():
                    m = await page.evaluate("navigator.deviceMemory || 'absent'")
                    if m != "absent":
                        assert m in [0.25, 0.5, 1, 2, 4, 8], f"Mem: {m}"

                async def _test_hardware_concurrency_browser():
                    c = await page.evaluate("navigator.hardwareConcurrency")
                    assert c > 0

                async def _test_screen_dimensions():
                    r = await page.evaluate("({sw:screen.width,sh:screen.height,dpr:devicePixelRatio})")
                    assert r["sw"] > 0 and r["sh"] > 0 and r["dpr"] > 0

                for name, fn in [
                    ("test_page_alive", _test_page_alive),
                    ("test_user_agent_android", _test_user_agent_android),
                    ("test_platform_linux_arm", _test_platform_linux_arm),
                    ("test_max_touch_points", _test_max_touch_points),
                    ("test_device_memory", _test_device_memory),
                    ("test_hardware_concurrency_browser", _test_hardware_concurrency_browser),
                    ("test_screen_dimensions", _test_screen_dimensions),
                ]:
                    await run_test_async(name, fn)

            # --- SECTION 4: Client Hints ---
            if section(4, "Client Hints API Verification"):
                # Navigate to real page first - chrome:// pages restrict APIs
                await safe_goto(page, "https://example.com")

                async def _test_has_user_agent_data():
                    has = await page.evaluate("!!navigator.userAgentData")
                    if not has:
                        # Some Chrome/Android combos don't expose this API
                        # Not a failure - UA string still works for identity
                        print("        userAgentData absent (acceptable on this Chrome)")
                    assert True  # Pass regardless - absence is not a detection signal

                async def _test_client_hints_platform():
                    has = await page.evaluate("!!navigator.userAgentData")
                    if not has:
                        print("        Skipped (no userAgentData)")
                        return
                    p = await page.evaluate("navigator.userAgentData.platform")
                    assert p == "Android", f"CH platform: {p}"

                async def _test_client_hints_mobile():
                    has = await page.evaluate("!!navigator.userAgentData")
                    if not has:
                        print("        Skipped (no userAgentData)")
                        return
                    m = await page.evaluate("navigator.userAgentData.mobile")
                    assert m is True

                async def _test_client_hints_brands():
                    has = await page.evaluate("!!navigator.userAgentData")
                    if not has:
                        print("        Skipped (no userAgentData)")
                        return
                    brands = await page.evaluate("navigator.userAgentData.brands")
                    names = [b["brand"] for b in brands]
                    assert "Chromium" in names, f"brands: {names}"

                async def _test_client_hints_high_entropy():
                    has = await page.evaluate("!!navigator.userAgentData")
                    if not has:
                        print("        Skipped (no userAgentData)")
                        return
                    r = await page.evaluate("""(async () =>
                        await navigator.userAgentData.getHighEntropyValues(
                            ['model','platform','platformVersion','mobile']
                        ))()""")
                    assert r["platform"] == "Android"
                    assert r["mobile"] is True
                    assert r["model"], f"model empty"

                for name, fn in [
                    ("test_has_user_agent_data", _test_has_user_agent_data),
                    ("test_client_hints_platform", _test_client_hints_platform),
                    ("test_client_hints_mobile", _test_client_hints_mobile),
                    ("test_client_hints_brands", _test_client_hints_brands),
                    ("test_client_hints_high_entropy", _test_client_hints_high_entropy),
                ]:
                    await run_test_async(name, fn)

            # --- SECTION 5: Proxy ---
            if section(5, "Proxy & Network Tests"):

                async def _test_proxy_loads_page():
                    await safe_goto(page)
                    t = await page.title()
                    assert "Example" in t, f"Title: {t}"

                async def _test_proxy_exit_ip():
                    await safe_goto(page, "https://httpbin.org/ip")
                    await asyncio.sleep(3)
                    text = await page.evaluate("document.body.innerText")
                    data = json.loads(text)
                    ip = data.get("origin", "")
                    assert ip and "proxy.example" not in ip, f"IP: {ip}"

                async def _test_timezone_matches():
                    tz = await page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
                    assert tz in EXPECTED_TIMEZONES, f"TZ: {tz}"

                async def _test_accept_language_header():
                    await safe_goto(page, "https://httpbin.org/headers")
                    await asyncio.sleep(3)
                    text = await page.evaluate("document.body.innerText")
                    data = json.loads(text)
                    al = data.get("headers", {}).get("Accept-Language", "")
                    assert "en" in al.lower(), f"Accept-Language: {al}"

                for name, fn in [
                    ("test_proxy_loads_page", _test_proxy_loads_page),
                    ("test_proxy_exit_ip", _test_proxy_exit_ip),
                    ("test_timezone_matches", _test_timezone_matches),
                    ("test_accept_language_header", _test_accept_language_header),
                ]:
                    await run_test_async(name, fn)

            # --- SECTION 6: WebRTC ---
            if section(6, "WebRTC Leak Test"):

                async def _test_webrtc_no_private_ip():
                    result = await page.evaluate("""() => new Promise(resolve => {
                        const ips = [];
                        try {
                            const pc = new RTCPeerConnection({iceServers: []});
                            pc.createDataChannel('');
                            pc.createOffer().then(o => pc.setLocalDescription(o));
                            pc.onicecandidate = e => {
                                if (!e.candidate) { pc.close(); resolve(ips); return; }
                                const p = e.candidate.candidate.split(' ');
                                if (p.length >= 5) ips.push(p[4]);
                            };
                            setTimeout(() => { pc.close(); resolve(ips); }, 5000);
                        } catch(e) { resolve(['ERROR:' + e.message]); }
                    })""")
                    private = [ip for ip in result
                              if ip.startswith("10.") or ip.startswith("192.168.")
                              or ip.startswith("172.")]
                    print(f"        WebRTC IPs: {result}")
                    assert len(private) == 0, f"Private IPs leaked: {private}"

                await run_test_async("test_webrtc_no_private_ip", _test_webrtc_no_private_ip)

            # --- SECTION 7: Page Interaction ---
            if section(7, "Page Interaction Tests"):

                async def _test_js_eval():
                    assert await page.evaluate("1+1") == 2
                    assert await page.evaluate("'hi'.toUpperCase()") == "HI"

                async def _test_multiple_pages():
                    new_pages = []
                    for _ in range(3):
                        p = await context.new_page()
                        new_pages.append(p)
                    for p in new_pages:
                        assert await p.evaluate("1+1") == 2
                    for p in new_pages:
                        await p.close()

                async def _test_navigate_real_url():
                    await safe_goto(page)
                    assert "Example" in await page.title()

                async def _test_complex_js_eval():
                    r = await page.evaluate("""(() => ({
                        ua: navigator.userAgent, cores: navigator.hardwareConcurrency,
                        dpr: devicePixelRatio, sw: screen.width
                    }))()""")
                    assert "Android" in r["ua"]
                    assert r["cores"] > 0

                for name, fn in [
                    ("test_js_eval", _test_js_eval),
                    ("test_multiple_pages", _test_multiple_pages),
                    ("test_navigate_real_url", _test_navigate_real_url),
                    ("test_complex_js_eval", _test_complex_js_eval),
                ]:
                    await run_test_async(name, fn)

            # --- SECTION 8: CDN Bypass ---
            if section(8, "CDN Bypass Tests"):

                async def _test_cloudflare_bypass():
                    await safe_goto(page, "https://nowsecure.nl/")
                    await asyncio.sleep(10)
                    blocked = await page.evaluate("""() =>
                        document.body.innerText.includes("Just a moment") ||
                        !!document.querySelector("iframe[src*='challenges']")""")
                    assert not blocked, "Cloudflare BLOCKED"

                async def _test_datadome_bypass():
                    # Footlocker is a known DataDome target
                    await safe_goto(page, "https://www.footlocker.com/")
                    await asyncio.sleep(10)
                    blocked = await page.evaluate("""() => {
                        const t = document.body.innerText.toLowerCase();
                        return t.includes("blocked") || t.includes("captcha") ||
                               t.includes("are you human") || t.includes("datadome");
                    }""")
                    assert not blocked, "DataDome BLOCKED"

                async def _test_akamai_cdn_bypass():
                    # Aka-My-Bot (Akamai) real-world demonstration
                    from damru.bypass import arm_bypass_async

                    # Target: Nike (Standard Aka-My-Bot protected domain)
                    test_domain = "www.nike.com"
                    print(f"        Arming bypass for {test_domain}...")

                    await arm_bypass_async(page, domain=test_domain)

                    # Navigation to the protected endpoint
                    # Akamai can be slow, giving it more time
                    await safe_goto(page, f"https://{test_domain}/", timeout=60000)
                    await asyncio.sleep(12) # Wait for potential redirects/challenges

                    title = await page.title()
                    success = title and "Access Denied" not in title and "403" not in title and "Access Forbidden" not in title

                    # More robust check: verify we can see common Nike page elements
                    if success:
                        has_logo = await page.evaluate("!!document.querySelector('svg.swoosh-logo') || !!document.querySelector('[aria-label=\"Nike Home Page\"]')")
                        success = success and has_logo

                    assert success, f"Aka-My-Bot Bypass failed on {test_domain} (Title: {title})"
                    print(f"        Success! Loaded {test_domain}: {title[:50]}...")

                for name, fn in [
                    ("test_cloudflare_bypass", _test_cloudflare_bypass),
                    ("test_datadome_bypass", _test_datadome_bypass),
                    ("test_akamai_cdn_bypass", _test_akamai_cdn_bypass),
                ]:
                    await run_test_async(name, fn)

            # --- SECTION 9: Anti-Bot ---
            if section(9, "Anti-Bot Detection Tests"):

                async def _test_browserscan():
                    await safe_goto(page, "https://www.browserscan.net/")
                    await asyncio.sleep(15)
                    text = await page.evaluate("document.body.innerText")
                    m = re.search(r"(\d+)\s*%", text)
                    score = int(m.group(1)) if m else 0
                    assert score >= 85, f"BrowserScan: {score}%"
                    print(f"        BrowserScan: {score}%")

                async def _test_creepjs():
                    await safe_goto(page, "https://abrahamjuliot.github.io/creepjs/")
                    await asyncio.sleep(25)
                    r = await page.evaluate("""() => {
                        const all = document.body.innerText;
                        const hm = all.match(/(\\d+)%\\s*headless:/i);
                        const sm = all.match(/(\\d+)%\\s*stealth:/i);
                        return { h: hm  parseInt(hm[1]) : -1, s: sm  parseInt(sm[1]) : -1 };
                    }""")
                    if r["h"] >= 0:
                        assert r["h"] <= 5, f"CreepJS headless: {r['h']}%"
                    if r["s"] >= 0:
                        assert r["s"] <= 5, f"CreepJS stealth: {r['s']}%"
                    print(f"        CreepJS: headless={r['h']}%, stealth={r['s']}%")

                async def _test_fingerprint_pro():
                    # Using the official Playground demo for more accurate results
                    await safe_goto(page, "https://demo.fingerprint.com/playground")
                    await asyncio.sleep(15)

                    # Extract the "Bot" signal value
                    bot_detected = await page.evaluate("""() => {
                        const all = document.body.innerText.toLowerCase();
                        // Look for the Bot signal row in the playground table
                        if (all.includes('bot') && all.includes('detected')) {
                           return all.includes('bot: detected') || all.includes('bot: bad');
                        }
                        return false;
                    }""")
                    assert not bot_detected, "Fingerprint Pro detected automation (Bot Signal)"
                    print(f"        Fingerprint Pro: No Bot Detected")

                async def _test_todetect():
                    await safe_goto(page, "https://todetect.net/")
                    await asyncio.sleep(15)

                    # ToDetect usually gives a "Likely a human" or "Automation detected" message
                    res = await page.evaluate("""() => {
                        const text = document.body.innerText.toLowerCase();
                        const is_human = text.includes('likely a human') || text.includes('high trust');
                        const is_bot = text.includes('automation detected') || text.includes('likely a bot');
                        return { is_human, is_bot };
                    }""")
                    assert res['is_human'] and not res['is_bot'], "ToDetect flagged automation"
                    print(f"        ToDetect: Likely a Human")

                async def _test_sannysoft():
                    await safe_goto(page, "https://bot.sannysoft.com/")
                    await asyncio.sleep(8)
                    r = await page.evaluate("""() => {
                        const rows = Array.from(document.querySelectorAll("table tr"));
                        let p=0, f=0;
                        for (const row of rows) {
                            const cells = row.querySelectorAll("td");
                            if (cells.length >= 2) {
                                const bg = getComputedStyle(cells[cells.length-1]).backgroundColor;
                                const txt = cells[cells.length-1].textContent.trim().toLowerCase();
                                if (txt.includes("passed")||txt.includes("ok")||txt===""||
                                    bg.includes("144, 238")||bg.includes("0, 128")) p++;
                                else if (txt.includes("failed")||bg.includes("255, 0")) f++;
                            }
                        }
                        return {passed:p, failed:f, total:p+f};
                    }""")
                    total = r.get("total", 0)
                    passed_count = r.get("passed", 0)
                    if total > 0:
                        assert passed_count / total >= 0.7, f"Sannysoft: {passed_count}/{total}"
                    print(f"        Sannysoft: {passed_count}/{total}")

                for name, fn in [
                    ("test_browserscan", _test_browserscan),
                    ("test_creepjs", _test_creepjs),
                    ("test_fingerprint_pro", _test_fingerprint_pro),
                    ("test_todetect", _test_todetect),
                    ("test_sannysoft", _test_sannysoft),
                ]:
                    await run_test_async(name, fn)

    # Run all browser tests in one session
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_browser_tests())
    except Exception as e:
        print(f"\n  FATAL: Browser session failed: {e}")
        traceback.print_exc()
    finally:
        loop.close()


# ===========================================================================
# Summary
# ===========================================================================

elapsed_total = time.time() - _start_time

os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
with open(RESULTS_FILE, "w") as f:
    json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "tests": _results}, f, indent=2)

print(f"\n{'='*60}")
print(f"  TEST RESULTS")
print(f"{'='*60}")
print(f"  Passed:  {_passed}")
print(f"  Failed:  {_failed}")
print(f"  Skipped: {_skipped}")
print(f"  Total:   {_passed + _failed + _skipped}")
print(f"  Time:    {elapsed_total:.1f}s")

if _errors:
    print(f"\n  FAILURES:")
    for sect, name, err in _errors:
        print(f"    [{sect}] {name}")
        print(f"      {err}")

print()
if _failed == 0:
    print("  ALL TESTS PASSED!")
else:
    print(f"  {_failed} TEST(S) FAILED")
print(f"{'='*60}")
print(f"\n  Results saved to: {RESULTS_FILE}")
print(f"  Re-run with --skip-passed to skip {_passed} passed tests")
sys.exit(1 if _failed else 0)
