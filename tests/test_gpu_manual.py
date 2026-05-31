#!/usr/bin/env python3
"""Manual GPU spoof test - assumes redroid container already running with Chrome installed."""
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

async def test_gpu_manual():
    """Test GPU binary patch on existing container."""
    print("=" * 70)
    print("MANUAL GPU SPOOF TEST - Binary Patch SwiftShader .so")
    print("=" * 70)

    # Connect to existing container
    serial = "127.0.0.1:5600"
    adb = ADB(serial=serial)

    print(f"\n[1/6] Connecting to ADB {serial}...")
    await adb._run(["connect", serial], timeout=10, allow_failure=True)

    # Check if device is online
    out = await adb.shell("echo OK", timeout=5, allow_failure=True)
    if "OK" not in out:
        print(f"FAIL: Device {serial} not responding")
        print("Make sure redroid container is running:")
        print("  wsl -d Ubuntu docker ps")
        return False
    print(f"PASS: Device online")

    # Check root
    print("\n[2/6] Checking root access...")
    root = RootOps(adb)
    try:
        await root.check_root()
        print("PASS: Root access confirmed")
    except Exception as e:
        print(f"FAIL: No root access: {e}")
        return False

    # Pick random device for GPU spoof
    print("\n[3/6] Selecting target device...")
    device = get_random_device(android_version="14")
    print(f"  Target: {device.name}")
    print(f"  GPU: {device.webgl_renderer}")
    print(f"  Vendor: {device.brand}")

    # Apply GPU binary spoof
    print("\n[4/6] Applying GPU binary patch to SwiftShader .so...")
    print("  (This takes ~5-10s - pulling .so, patching, pushing, restarting SurfaceFlinger)")
    try:
        await root.apply_gpu_binary_spoof(device)
        print("PASS: GPU binary patch applied successfully")
    except Exception as e:
        print(f"FAIL: GPU binary patch failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Launch Chrome and check GPU
    print("\n[5/6] Launching Chrome and querying GPU via CDP...")

    # Force stop + clear Chrome first
    from damru.chrome import ChromeManager
    chrome = ChromeManager(adb)
    await chrome.detect_package()
    await chrome.force_stop()
    await chrome.clear_all_data()

    # Launch Chrome
    await chrome.launch()
    await chrome.dismiss_fre()
    await chrome.wait_for_devtools_socket(timeout=15.0)

    # Connect CDP
    cdp = CDPConnection(adb)
    await cdp.setup_port_forward()
    context = await cdp.connect()
    page = context.pages[0]

    print("\n[6/6] Querying WebGL GPU...")

    await page.goto("about:blank")

    gpu_info = await page.evaluate("""
        () => {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (!gl) return { error: 'WebGL not supported' };

            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (!debugInfo) return { error: 'WEBGL_debug_renderer_info not available' };

            return {
                renderer: gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL),
                vendor: gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL),
            };
        }
    """)

    # Cleanup
    await cdp.disconnect()
    await chrome.force_stop()

    print("\n" + "=" * 70)
    print("RESULTS:")
    print("=" * 70)

    if 'error' in gpu_info:
        print(f"FAIL: {gpu_info['error']}")
        return False

    renderer = gpu_info.get('renderer', 'Unknown')
    vendor = gpu_info.get('vendor', 'Unknown')

    print(f"  Renderer: {renderer}")
    print(f"  Vendor:   {vendor}")
    print(f"  Expected: {device.webgl_renderer} ({device.brand})")
    print()

    # Check for SwiftShader leak
    is_swiftshader = 'swiftshader' in renderer.lower()
    is_google = 'google inc.' in vendor.lower()

    if is_swiftshader:
        print("FAIL: SwiftShader leak detected")
        return False

    if is_google:
        print("FAIL: Google Inc. vendor detected")
        return False

    print("PASS: GPU binary spoof working!")
    print("  - Renderer is NOT SwiftShader")
    print("  - Vendor is NOT Google Inc.")
    return True

async def main_async():
    try:
        success = await test_gpu_manual()
        return 0 if success else 1
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    print("\nManual GPU Spoof Test")
    print("Prerequisites:")
    print("  1. Redroid container running on 127.0.0.1:5600")
    print("  2. Chrome installed in container")
    print("  3. Root access available\n")

    sys.exit(asyncio.run(main_async()))
