"""End-to-end test of damru pipeline with PH proxy.

Tests the full pipeline with ROOT-LEVEL ONLY spoofing (zero JS injection):
  1. ADB connection
  2. Root access + resetprop setup
  3. Device identity spoofing (Samsung Galaxy S22 Ultra - Android 12)
  4. GeoIP-based timezone/locale from proxy
  5. System HTTP proxy (settings put global http_proxy)
  6. Chrome launch + FRE dismissal
  7. CDP connection (via ro.debuggable=1)
  8. WebRTC blocked via iptables (not JS)
  9. Identity verification via Client Hints
"""
import asyncio
import sys

sys.path.insert(0, ".")

from damru.adb import ADB
from damru.root import RootOps
from damru.devices import get_device
from damru.profiles import build_profile
from damru.chrome import ChromeManager
from damru.cdp import CDPConnection
from damru.proxy import build_accept_language, resolve_proxy_geo
from damru.utils import setup_logging, sleep

# SOCKS5 for Python-side GeoIP, HTTP for Android system proxy
PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"
TARGET_DEVICE = "samsung_galaxy_s22_ultra"


async def main():
    setup_logging(debug=True)

    print("=" * 60)
    print("  damru E2E Test - System HTTP Proxy (Zero JS Injection)")
    print("=" * 60)

    # Step 1: ADB
    print("\n[1/10] ADB connection...")
    adb = ADB()
    await adb.ensure_server()
    serial = await adb.detect_device()
    adb.serial = serial
    info = await adb.get_device_info()
    print(f"  Device: {info.get('model')} ({info.get('brand')}) Android {info.get('android_version')}")
    print(f"  Serial: {serial}")

    # Step 2: Root + resetprop
    print("\n[2/10] Root access + resetprop...")
    root = RootOps(adb)
    await root.check_root()
    print("  Root: OK")
    resetprop_cmd = await root._ensure_resetprop()
    print(f"  resetprop: {resetprop_cmd}")

    # Step 3: GeoIP from proxy
    print("\n[3/10] GeoIP resolution from proxy...")
    geo = resolve_proxy_geo(PH_SOCKS5)
    print(f"  Exit IP: {geo.get('ip')}")
    print(f"  Timezone: {geo.get('timezone')}")
    print(f"  Locale: {geo.get('locale')}")
    print(f"  Country: {geo.get('country_code')}")

    # Step 4: Build profile (with http_proxy for Android)
    print("\n[4/10] Building profile...")
    device = get_device(TARGET_DEVICE)
    profile = build_profile(device, proxy=PH_SOCKS5, http_proxy=PH_HTTP)
    print(f"  Target: {profile.description}")
    print(f"  Timezone: {profile.timezone}")
    print(f"  Locale: {profile.locale}")
    print(f"  Android HTTP proxy: {profile.android_http_proxy}")
    print(f"  Chrome flags: {len(profile.chrome_flags)} flags (best-effort, may not be read)")

    # Step 5: Apply system props
    print("\n[5/10] Applying system props...")
    real_android = info.get("android_version", "")
    version_match = real_android == device.android_version
    if version_match:
        print(f"  Android version match ({real_android}) - setting ALL props including version")
    else:
        print(f"  Android version mismatch (real={real_android}, profile={device.android_version}) - skipping version props")
    await root.apply_device_props(device, safe_only=not version_match)
    await root.apply_timezone(profile.timezone)
    await root.apply_locale(profile.locale)

    # Enable debuggable (for DevTools socket)
    debuggable = await adb.get_prop("ro.debuggable")
    if debuggable != "1":
        await root.set_prop("ro.debuggable", "1")
        print("  Set ro.debuggable=1 (DevTools socket)")

    # Verify
    model = await adb.get_prop("ro.product.model")
    brand = await adb.get_prop("ro.product.brand")
    print(f"  Model: {model}")
    print(f"  Brand: {brand}")

    # Step 6: Set system HTTP proxy
    print("\n[6/10] Setting system HTTP proxy...")
    await adb.shell(
        f"settings put global http_proxy {profile.android_http_proxy}",
        allow_failure=True,
    )
    print(f"  System proxy: {profile.android_http_proxy}")

    # Step 7: Chrome setup + launch
    print("\n[7/10] Chrome setup...")
    chrome = ChromeManager(adb)
    await chrome.detect_package()
    version = await chrome.get_version()
    print(f"  Package: {chrome.package}")
    print(f"  Version: {version}")

    # Write flags (best-effort - may not be read on user builds)
    await chrome.write_command_line(profile.chrome_flags)

    # Patch Chrome language (root-level, based on proxy IP)
    accept_lang_val = build_accept_language(profile.locale)
    await chrome.patch_preferences(profile.locale, accept_lang_val)
    print(f"  Language patched: {profile.locale} -> {accept_lang_val}")

    # Launch Chrome
    await chrome.force_stop()
    await chrome.launch()
    print("  Chrome launched")
    await sleep(3)

    # Step 8: Dismiss FRE + WebRTC block
    print("\n[8/10] FRE + WebRTC firewall...")
    await chrome.dismiss_fre()
    await root.apply_webrtc_block()
    print("  FRE check done, WebRTC blocked via iptables")

    # Step 9: Wait for devtools
    print("\n[9/10] Waiting for devtools socket...")
    socket_ok = await chrome.wait_for_devtools_socket(timeout=20.0)
    if socket_ok:
        print("  DevTools socket: READY")
    else:
        print("  DevTools socket: NOT FOUND - retrying...")
        await chrome.force_stop()
        await sleep(1)
        await chrome.launch()
        await sleep(5)
        await chrome.dismiss_fre()
        socket_ok = await chrome.wait_for_devtools_socket(timeout=15.0)
        if not socket_ok:
            print("  FATAL: DevTools socket still not available")
            await cleanup(adb, chrome, root, profile)
            return

    # Step 10: CDP connection + identity check
    print("\n[10/10] CDP connection + identity check...")
    cdp = CDPConnection(adb)
    await cdp.setup_port_forward()
    ctx = await cdp.connect()

    # NO stealth script injection - zero JS tampering!
    print("  Connected (zero JS injection)")

    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    # Navigate to httpbin to check identity + proxy
    print("\n  Navigating to httpbin.org...")
    await page.goto("https://httpbin.org/anything", wait_until="domcontentloaded", timeout=30000)
    await sleep(3)

    # Check identity
    identity = await page.evaluate("""async () => {
        const result = {
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            deviceMemory: navigator.deviceMemory || 'N/A',
            maxTouchPoints: navigator.maxTouchPoints,
            hasUAData: !!navigator.userAgentData,
        };
        if (navigator.userAgentData) {
            try {
                const high = await navigator.userAgentData.getHighEntropyValues([
                    'model', 'platform', 'platformVersion'
                ]);
                result.chModel = high.model;
                result.chPlatform = high.platform;
                result.chPlatformVersion = high.platformVersion;
            } catch(e) {
                result.chError = e.message;
            }
        }
        try {
            const pre = document.querySelector('pre');
            if (pre) {
                const data = JSON.parse(pre.textContent);
                result.httpHeaders = {};
                for (const [k,v] of Object.entries(data.headers || {})) {
                    if (k.toLowerCase().startsWith('sec-ch-ua') ||
                        k.toLowerCase() === 'user-agent' ||
                        k.toLowerCase() === 'accept-language') {
                        result.httpHeaders[k] = v;
                    }
                }
                result.originIp = data.origin;
            }
        } catch(e) {}
        return result;
    }""")

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"\n  User-Agent: {identity.get('userAgent', 'N/A')}")
    print(f"  Platform: {identity.get('platform', 'N/A')}")
    print(f"  DeviceMemory: {identity.get('deviceMemory', 'N/A')}")
    print(f"  MaxTouchPoints: {identity.get('maxTouchPoints', 'N/A')}")

    if identity.get("chModel"):
        print(f"\n  Client Hints Model: {identity['chModel']}")
        print(f"  Client Hints Platform: {identity.get('chPlatform', 'N/A')}")
        print(f"  Client Hints PlatformVer: {identity.get('chPlatformVersion', 'N/A')}")

    if identity.get("httpHeaders"):
        print(f"\n  HTTP Headers:")
        for k, v in identity["httpHeaders"].items():
            print(f"    {k}: {v}")

    if identity.get("originIp"):
        print(f"\n  Exit IP: {identity['originIp']}")

    # Verdict
    print("\n" + "-" * 60)
    checks = []

    # Model check (dynamic based on target device)
    device = get_device(TARGET_DEVICE)
    expected_model = device.model
    ch_model = identity.get("chModel", "")
    if ch_model == expected_model:
        checks.append(("[PASS]", f"Client Hints model = {expected_model}"))
    elif ch_model:
        checks.append(("[FAIL]", f"Client Hints model = {ch_model} (expected {expected_model})"))
    else:
        checks.append(("[SKIP]", "No Client Hints model"))

    # Platform version check (should match device's Android version)
    ch_pv = identity.get("chPlatformVersion", "")
    expected_av = device.android_version
    if ch_pv and ch_pv.startswith(expected_av):
        checks.append(("[PASS]", f"PlatformVersion = {ch_pv} (matches Android {expected_av})"))
    elif ch_pv:
        checks.append(("[WARN]", f"PlatformVersion = {ch_pv} (device profile says {expected_av})"))

    # Proxy check - exit IP should NOT be the proxy server IP or user's Indian IP
    origin = identity.get("originIp", "")
    if origin and "198.20" not in origin and "103.240" not in origin:
        checks.append(("[PASS]", f"Proxy working - exit IP: {origin}"))
    elif origin:
        checks.append(("[FAIL]", f"Proxy NOT working - IP: {origin}"))
    else:
        checks.append(("[SKIP]", "Could not check exit IP"))

    # Accept-Language check
    headers = identity.get("httpHeaders", {})
    accept_lang = headers.get("Accept-Language", "")
    if accept_lang and geo.get("locale", "")[:2] in accept_lang.lower():
        checks.append(("[PASS]", f"Accept-Language matches: {accept_lang}"))
    elif accept_lang:
        checks.append(("[WARN]", f"Accept-Language: {accept_lang} (expected {geo.get('locale')})"))
    else:
        checks.append(("[SKIP]", "No Accept-Language header"))

    for status, msg in checks:
        print(f"  {status} {msg}")

    # Cleanup
    print("\n  Cleaning up...")
    await cdp.disconnect()
    await cleanup(adb, chrome, root, profile)
    print("  Done!")


async def cleanup(adb, chrome, root, profile):
    """Clean up all damru changes."""
    await chrome.force_stop()
    await chrome.clear_command_line()
    # Clear system proxy
    if profile and profile.android_http_proxy:
        await adb.shell("settings put global http_proxy :0", allow_failure=True)
    # Remove WebRTC iptables rules
    try:
        await root.remove_webrtc_block()
    except Exception:
        pass
    # Restore screen/props
    await adb.shell("wm size reset", allow_failure=True)
    await adb.shell("wm density reset", allow_failure=True)
    await root.restore_original_props()


if __name__ == "__main__":
    asyncio.run(main())
