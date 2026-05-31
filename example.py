"""
Comprehensive functional test suite for damru.

Tests the device database, profile builder, and live browser behavior
using ONLY the public AsyncDamru API. No direct ADB/root calls.

All browser tests run through PH HTTP proxy with zero JS injection.
Random Android 12 device selected each run.

Usage:
    python example.py
    python example.py --skip-passed          # skip previously passed tests
    python example.py --tests "3,4,5"        # run specific sections only
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

# NOTE: Replace with your own SOCKS5/HTTP proxy if needed. 
# If None, Damru will use your local connection.
PH_SOCKS5 = None 
PH_HTTP = None
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
        _failed += 1
        _results[name] = "FAIL"
        _errors.append(f"[{_section}] {name}: {str(e)}")
        print(f"  FAIL  {name}")
        if "--debug" in sys.argv:
            traceback.print_exc()


async def safe_goto(page, url, timeout=NAV_TIMEOUT):
    """Navigate to URL with retry and error handling."""
    for attempt in range(2):
        try:
            return await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        except Exception:
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            raise


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def main():
    # Setup results directory
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)

    if section(1, "Device Database"):
        async def test_device_db():
            assert len(DEVICES) > 30
            d = get_device("pixel_8_pro")
            assert d.brand == "google"
            assert d.model == "Pixel 8 Pro"
            
            random_d = get_random_device()
            assert isinstance(random_d, AndroidDevice)
        
        await run_test_async("test_device_db", test_device_db)

    if section(2, "Profile Builder"):
        async def test_profile_gen():
            d = get_device("samsung_s24_ultra")
            p = build_profile(d, proxy=PH_SOCKS5)
            assert p.device.model == "samsung_s24_ultra"
            assert "Android 14" in p.ua
            assert p.timezone is not None
            assert p.locale is not None
        
        await run_test_async("test_profile_gen", test_profile_gen)

    if section(3, "Network & Proxy Identity"):
        async with AsyncDamru(device="random", proxy=PH_SOCKS5) as browser:
            page = await browser.new_page()

            async def test_ip_leak():
                await safe_goto(page, "https://httpbin.org/ip")
                content = await page.content()
                assert PH_HTTP in content or "198.20.189.134" in content

            async def test_headers():
                await safe_goto(page, "https://httpbin.org/headers")
                content = await page.content()
                # Ensure no Playwright/Automation traces
                assert "Headless" not in content
                assert "Playwright" not in content

            await run_test_async("test_ip_leak", test_ip_leak)
            await run_test_async("test_headers", test_headers)

    if section(4, "Stealth & Bypasses"):
        # Select a stable target device
        async with AsyncDamru(device="pixel_8_pro", proxy=PH_SOCKS5) as browser:
            page = await browser.new_page()

            async def test_cloudflare_bypass():
                await safe_goto(page, "https://nowsecure.nl/")
                await asyncio.sleep(5)
                title = await page.title()
                blocked = "just a moment" in title.lower()
                assert not blocked, "Cloudflare BLOCKED"

            async def test_browserscan():
                await safe_goto(page, "https://www.browserscan.net/")
                await asyncio.sleep(5)
                # Simple check for score
                content = await page.content()
                match = re.search(r"(\d+)\s*%", content)
                score = int(match.group(1)) if match else 0
                assert score >= 85, f"BrowserScan: {score}%"
                print(f"        BrowserScan: {score}%")

            async def test_creepjs():
                await safe_goto(page, "https://abrahamjuliot.github.io/creepjs/")
                await asyncio.sleep(10)
                # Extract score via evaluate
                r = await page.evaluate("""() => {
                    const all = document.body.innerText;
                    const h = all.match(/(\\d+)%\\s*headless:/i);
                    const s = all.match(/(\\d+)%\\s*stealth:/i);
                    return { h: h ? h[1] : 100, s: s ? s[1] : 100 };
                }""")
                if r:
                    assert int(r["h"]) <= 5, f"CreepJS headless: {r['h']}%"
                    assert int(r["s"]) <= 5, f"CreepJS stealth: {r['s']}%"
                print(f"        CreepJS: headless={r['h']}%, stealth={r['s']}%")

            async def test_sannysoft():
                await safe_goto(page, "https://bot.sannysoft.com/")
                await asyncio.sleep(5)
                passed = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll("td")).filter(td => 
                        td.innerText.toLowerCase().includes("passed") || 
                        td.innerText.toLowerCase().includes("ok")
                    ).length;
                }""")
                assert passed > 10, f"Sannysoft passed: {passed}"

            await run_test_async("test_cloudflare_bypass", test_cloudflare_bypass)
            await run_test_async("test_browserscan", test_browserscan)
            await run_test_async("test_creepjs", test_creepjs)
            await run_test_async("test_sannysoft", test_sannysoft)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------

    print(f"\n{'='*60}")
    print(f"  FINAL RESULTS")
    print(f"{'='*60}")
    print(f"  PASSED: {_passed}")
    print(f"  FAILED: {_failed}")
    
    if _errors:
        print("\n  Errors:")
        for err in _errors:
            print(f"    - {err}")

    # Save results for next run
    with open(RESULTS_FILE, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "tests": _results
        }, f, indent=2)

    if _failed == 0:
        print(f"\n  ALL TESTS PASSED!")
    else:
        print(f"  {_failed} TEST(S) FAILED")
    print(f"{'='*60}")
    print(f"\n  Results saved to: {RESULTS_FILE}")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Aborted by user")
        sys.exit(1)
