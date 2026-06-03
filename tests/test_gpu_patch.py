#!/usr/bin/env python3
"""Test GPU binary patch on redroid 14 ANGLE architecture."""
import sys
import asyncio
from pathlib import Path

# Add damru to path
damru_path = Path(__file__).parent / "damru"
sys.path.insert(0, str(damru_path))

from damru.adb import ADB
from damru.root import RootOps
from damru.devices import get_random_device
from damru.cdp import CDPConnection
from damru.utils import setup_logging

JS_CHECK = """() => {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
    if (!gl) return {error: 'no webgl'};
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    if (!ext) return {error: 'no debug info'};
    return {
        renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
        vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
    };
}"""

async def test():
    setup_logging(True)
    serial = "127.0.0.1:5600"
    adb = ADB(serial=serial)
    await adb._run(["connect", serial], timeout=10, allow_failure=True)

    # Check device
    out = await adb.shell("echo OK", timeout=5, allow_failure=True)
    if "OK" not in out:
        print("FAIL: Device not responding")
        return False

    # Root
    root = RootOps(adb)
    await root.check_root()
    print("Root: OK")

    # Pick target device
    device = get_random_device(android_version="14")
    print(f"Target: {device.name}")
    print(f"  webgl_renderer: {device.webgl_renderer}")
    print(f"  webgl_vendor:   {device.webgl_vendor}")

    # Apply GPU binary spoof
    print("\nApplying GPU binary patch...")
    await root.apply_gpu_binary_spoof(device)
    print("Patch applied!")

    # Stop Chrome, clear data, relaunch
    print("\nLaunching Chrome...")
    await adb.shell("am force-stop com.android.chrome", allow_failure=True)
    await adb.shell("pm clear com.android.chrome", allow_failure=True)
    await asyncio.sleep(1)

    # Write prefs to skip FRE
    await adb.shell(
        "su 0 mkdir -p /data/data/com.android.chrome/shared_prefs",
        allow_failure=True,
    )
    prefs_xml = '<xml version="1.0" encoding="utf-8" standalone="yes" ><map><boolean name="first_run_flow" value="true" /><boolean name="tos_accepted" value="true" /></map>'
    import base64
    b64 = base64.b64encode(prefs_xml.encode()).decode()
    await adb.shell(
        f"su 0 sh -c 'echo {b64} | base64 -d > /data/data/com.android.chrome/shared_prefs/com.android.chrome_preferences.xml'",
        allow_failure=True,
    )
    # Fix ownership
    uid_out = await adb.shell("stat -c %u /data/data/com.android.chrome", allow_failure=True)
    uid = uid_out.strip() if uid_out.strip().isdigit() else "10088"
    await adb.shell(
        f"su 0 chown {uid}:{uid} /data/data/com.android.chrome/shared_prefs/com.android.chrome_preferences.xml",
        allow_failure=True,
    )

    # Launch Chrome
    await adb.shell(
        "am start -n com.android.chrome/com.google.android.apps.chrome.Main "
        "-d 'about:blank' --ez 'no_default_browser_check' true --ez 'no_first_run' true",
        allow_failure=True,
    )
    await asyncio.sleep(8)

    # Check devtools
    sock = await adb.shell("cat /proc/net/unix | grep devtools", allow_failure=True)
    if "devtools" not in sock:
        print("FAIL: No DevTools socket")
        return False

    # CDP connect
    await adb._run(["forward", "tcp:9222", "localabstract:chrome_devtools_remote"], timeout=10)

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = ctx.pages[0]
        await page.goto("about:blank")
        result = await page.evaluate(JS_CHECK)
        await browser.close()

    await adb.shell("am force-stop com.android.chrome", allow_failure=True)
    await adb._run(["forward", "--remove", "tcp:9222"], timeout=5, allow_failure=True)

    print("\n" + "=" * 70)
    print("RESULTS:")
    print("=" * 70)
    if "error" in result:
        print(f"FAIL: {result['error']}")
        return False

    renderer = result.get("renderer", "")
    vendor = result.get("vendor", "")
    print(f"  Renderer: {renderer}")
    print(f"  Vendor:   {vendor}")
    print(f"  Expected renderer to contain: {device.webgl_renderer}")
    print(f"  Expected vendor to contain:   {device.webgl_vendor}")
    print()

    has_swiftshader = "swiftshader" in renderer.lower()
    has_google_vendor = "google inc." in vendor.lower()
    has_target_gpu = device.webgl_renderer[:15].lower() in renderer.lower()

    if has_swiftshader:
        print("FAIL: SwiftShader still visible in renderer")
        return False
    if has_google_vendor:
        print("FAIL: Google Inc. still visible in vendor")
        return False
    if has_target_gpu:
        print("PASS: Target GPU visible in renderer!")
    else:
        print(f"WARN: Target GPU not found in renderer (expected substring: {device.webgl_renderer[:15]})")

    print("PASS: No SwiftShader/Google Inc. leak!")
    return True

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)
