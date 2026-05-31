#!/usr/bin/env python3
"""Quick GPU spoof verification via CDP.

Connects to a running redroid container, applies GPU binary spoof,
launches Chrome, dismisses FRE, connects CDP, queries WebGL.

Usage:
    python test_gpu_cdp.py [adb_serial]
    # Default serial: localhost:5600
"""
import asyncio
import json
import sys
import os

# Add damru to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "damru"))

from damru.adb import ADB
from damru.root import RootOps
from damru.chrome import ChromeManager
from damru.devices import get_device
from damru.utils import setup_logging, logger


async def main():
    setup_logging(debug=True)

    serial = sys.argv[1] if len(sys.argv) > 1 else "localhost:5600"
    print(f"\n=== GPU CDP Verification Test ===")
    print(f"ADB serial: {serial}\n")

    adb = ADB(serial=serial)

    # Step 1: Ensure ADB connected
    print("[1/8] Connecting ADB...")
    await adb.ensure_server()
    info = await adb.get_device_info()
    print(f"  Device: {info.get('model', '?')} Android {info.get('android_version', '?')}")

    # Step 2: Check root
    print("[2/8] Checking root...")
    root = RootOps(adb)
    await root.check_root()
    print(f"  Root method: {root._root_method}")

    # Step 3: Apply GPU binary spoof (Adreno 750 / Qualcomm)
    print("[3/8] Applying GPU binary spoof...")
    device = get_device("galaxy_s24_ultra")  # Adreno 750
    result = await root.apply_gpu_binary_spoof(device)
    print(f"  GPU spoof applied: {result}")

    # Step 4: Restart SurfaceFlinger to reload patched .so
    print("[4/8] Restarting SurfaceFlinger...")
    await adb.shell_root("setprop ctl.restart surfaceflinger")
    await asyncio.sleep(3)

    # Verify via SurfaceFlinger dump
    sf_dump = await adb.shell("dumpsys SurfaceFlinger | grep GLES", timeout=10, allow_failure=True)
    print(f"  SurfaceFlinger: {sf_dump.strip()}")

    # Step 5: Set debuggable + launch Chrome
    print("[5/8] Preparing Chrome...")
    await root.set_prop("ro.debuggable", "1")

    chrome = ChromeManager(adb)
    await chrome.detect_package()
    print(f"  Package: {chrome.package}")

    # Check if Chrome is installed
    version = await chrome.get_version()
    if not version:
        print("  Chrome not installed! Install it first.")
        return

    print(f"  Version: {version}")

    # Force stop + clear data for clean FRE
    await chrome.force_stop()
    await chrome.clear_all_data()

    # Write minimal preferences (skip first-run stuff)
    await chrome.patch_preferences("en-US", "en-US,en;q=0.9")

    # Step 6: Launch Chrome
    print("[6/8] Launching Chrome...")
    await chrome.launch()

    # Step 7: Dismiss FRE
    print("[7/8] Dismissing FRE...")
    await chrome.dismiss_fre()

    # Wait for devtools socket
    print("  Waiting for devtools socket...")
    socket_ready = await chrome.wait_for_devtools_socket(timeout=15.0)
    print(f"  Socket ready: {socket_ready}")

    # Step 8: CDP WebGL query
    print("[8/8] Querying WebGL via CDP...")

    # Port forward
    from damru.utils import find_free_port
    port = find_free_port()
    await adb.remove_forward(port)
    await asyncio.sleep(0.2)
    await adb.forward(port, "localabstract:chrome_devtools_remote")
    print(f"  Port forwarded: localhost:{port}")

    # Query WebGL via raw CDP (no Playwright needed)
    import aiohttp
    async with aiohttp.ClientSession() as session:
        # Get tab list
        async with session.get(f"http://localhost:{port}/json") as resp:
            tabs = await resp.json()

        if not tabs:
            print("  ERROR: No tabs found")
            return

        ws_url = tabs[0].get("webSocketDebuggerUrl")
        if not ws_url:
            print("  ERROR: No WebSocket URL")
            return

        print(f"  Connecting WebSocket: {ws_url}")
        async with session.ws_connect(ws_url) as ws:
            # First navigate to a page (WebGL needs a real page context)
            await ws.send_json({
                "id": 1,
                "method": "Page.navigate",
                "params": {"url": "data:text/html,<h1>GPU Test</h1>"}
            })
            resp_nav = await asyncio.wait_for(ws.receive_json(), timeout=10)
            await asyncio.sleep(1)

            # Query WebGL
            await ws.send_json({
                "id": 2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """
                    (function() {
                        var c = document.createElement('canvas');
                        var gl = c.getContext('webgl2') || c.getContext('webgl');
                        if (!gl) return JSON.stringify({error: 'no webgl context'});
                        var ext = gl.getExtension('WEBGL_debug_renderer_info');
                        return JSON.stringify({
                            vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
                            renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)
                        });
                    })()
                    """,
                    "returnByValue": True,
                },
            })

            # Read responses until we get id=2
            for _ in range(10):
                resp_data = await asyncio.wait_for(ws.receive_json(), timeout=10)
                if resp_data.get("id") == 2:
                    break
            else:
                print("  ERROR: Didn't get WebGL response")
                return

            result = resp_data.get("result", {}).get("result", {})
            if result.get("type") == "string":
                data = json.loads(result["value"])
                print(f"\n{'='*50}")
                print(f"  GL_VENDOR:   {data.get('vendor')}")
                print(f"  GL_RENDERER: {data.get('renderer')}")
                print(f"{'='*50}")

                # Verify spoof
                renderer = data.get("renderer", "")
                if "Adreno" in renderer and "SwiftShader" not in renderer:
                    print("\n  GPU SPOOF VERIFIED via Chrome CDP!")
                elif "SwiftShader" in renderer:
                    print("\n  FAILED: Still showing SwiftShader")
                else:
                    print(f"\n  UNEXPECTED renderer: {renderer}")
            else:
                print(f"  ERROR: Unexpected result: {result}")

    # Cleanup port forward
    await adb.remove_forward(port)
    await chrome.force_stop()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
