#!/usr/bin/env python3
"""Run GPU verification test using damru's own modules.

1. Connect ADB to redroid container
2. Install Chrome if needed (via damru's chrome module)
3. Apply GPU binary spoof
4. Launch Chrome, dismiss FRE, connect CDP
5. Query WebGL GL_RENDERER/GL_VENDOR
"""
import asyncio
import json
import os
import sys

# Add damru to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "damru"))

from damru.adb import ADB
from damru.root import RootOps
from damru.chrome import ChromeManager
from damru.devices import get_device
from damru.utils import setup_logging, logger, find_free_port


async def main():
    setup_logging(debug=True)
    serial = sys.argv[1] if len(sys.argv) > 1 else "localhost:5600"

    print(f"\n{'='*60}")
    print(f"  GPU SPOOF CDP VERIFICATION TEST")
    print(f"  Serial: {serial}")
    print(f"{'='*60}\n")

    adb = ADB(serial=serial)
    await adb.ensure_server()

    # Step 1: Device info
    info = await adb.get_device_info()
    print(f"[1] Device: {info.get('model', '?')} Android {info.get('android_version', '?')}")

    # Step 2: Root
    root = RootOps(adb)
    await root.check_root()
    print(f"[2] Root: {root._root_method}")

    # Step 3: Check Chrome installed
    chrome = ChromeManager(adb)
    await chrome.detect_package()
    version = await chrome.get_version()

    if not version:
        print("[3] Chrome NOT installed — installing from APKs...")
        apk_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "damru", "chrome-apks", "145.0.7632.75")
        # Install trichrome library first
        trichrome = os.path.join(apk_dir, "google_trichrome_library.apk")
        await adb._run(["install", trichrome], timeout=120)
        print("   TrichromeLibrary installed")

        # Install Chrome split APKs
        apks = ["base.apk", "split_chrome.apk", "split_config.en.apk", "split_on_demand.apk"]
        apk_paths = [os.path.join(apk_dir, a) for a in apks]
        total = sum(os.path.getsize(p) for p in apk_paths)

        # Create session
        out = await adb.shell(f"pm install-create -S {total}", timeout=30)
        import re
        m = re.search(r'\[(\d+)\]', out)
        if not m:
            print(f"   FAILED to create install session: {out}")
            return
        session_id = m.group(1)
        print(f"   Install session: {session_id}")

        for apk_path in apk_paths:
            size = os.path.getsize(apk_path)
            name = os.path.basename(apk_path).replace('.apk', '')
            # Push APK to device first
            remote = f"/data/local/tmp/{os.path.basename(apk_path)}"
            await adb._run(["push", apk_path, remote], timeout=60)
            await adb.shell(
                f"pm install-write -S {size} {session_id} {name} {remote}",
                timeout=60,
            )
            print(f"   Wrote {name} ({size} bytes)")

        out = await adb.shell(f"pm install-commit {session_id}", timeout=30)
        if "Success" not in out:
            print(f"   Install commit FAILED: {out}")
            return
        print("   Chrome installed!")
        version = await chrome.get_version()

    print(f"[3] Chrome: {chrome.package} v{version}")

    # Step 4: GPU spoof
    device = get_device("galaxy_s24_ultra")  # Adreno 750 / Qualcomm
    print(f"[4] Applying GPU spoof: {device.webgl_renderer}")
    result = await root.apply_gpu_binary_spoof(device)
    print(f"   Spoof result: {result}")

    # Restart SurfaceFlinger
    await adb.shell_root("setprop ctl.restart surfaceflinger")
    print("   SurfaceFlinger restarted, waiting 5s...")
    await asyncio.sleep(5)

    # Verify SurfaceFlinger
    sf = await adb.shell("dumpsys SurfaceFlinger", timeout=10, allow_failure=True)
    for line in sf.split('\n'):
        if 'GLES' in line:
            print(f"   SF: {line.strip()}")
            break

    # Step 5: Set debuggable
    debuggable = await adb.get_prop("ro.debuggable")
    if debuggable != "1":
        await root.set_prop("ro.debuggable", "1")
    print(f"[5] ro.debuggable={await adb.get_prop('ro.debuggable')}")

    # Step 6: Fresh Chrome launch
    await chrome.force_stop()
    await chrome.clear_all_data()

    # Write preferences to help skip FRE
    from damru.proxy import build_accept_language
    await chrome.patch_preferences("en-US", "en-US,en;q=0.9")

    print("[6] Launching Chrome...")
    await chrome.launch()

    # Step 7: Dismiss FRE
    print("[7] Dismissing FRE...")
    await chrome.dismiss_fre()

    # Step 8: Wait for devtools
    print("[8] Waiting for devtools socket...")
    socket_ready = await chrome.wait_for_devtools_socket(timeout=20.0)
    if not socket_ready:
        print("   WARNING: Socket not detected, trying anyway...")

    # Step 9: CDP WebGL query
    print("[9] CDP WebGL query...")
    port = find_free_port()
    await adb.remove_forward(port)
    await asyncio.sleep(0.3)
    await adb.forward(port, "localabstract:chrome_devtools_remote")
    print(f"   Port forwarded: localhost:{port}")

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://localhost:{port}/json") as resp:
            tabs = await resp.json()

        if not tabs:
            print("   ERROR: No tabs")
            return

        ws_url = tabs[0].get("webSocketDebuggerUrl")
        if not ws_url:
            print("   ERROR: No WebSocket URL")
            return

        async with session.ws_connect(ws_url) as ws:
            # Navigate to a real page
            await ws.send_json({
                "id": 1,
                "method": "Page.navigate",
                "params": {"url": "data:text/html,<h1>GPU Test</h1>"}
            })
            await asyncio.sleep(2)
            # Drain nav response
            try:
                await asyncio.wait_for(ws.receive_json(), timeout=3)
            except asyncio.TimeoutError:
                pass

            # Query WebGL
            await ws.send_json({
                "id": 99,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """
                    (function() {
                        var c = document.createElement('canvas');
                        var gl = c.getContext('webgl2') || c.getContext('webgl');
                        if (!gl) return JSON.stringify({error: 'no webgl'});
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

            # Read until we get id=99
            for _ in range(20):
                try:
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=5)
                except asyncio.TimeoutError:
                    break
                if msg.get("id") == 99:
                    result = msg.get("result", {}).get("result", {})
                    if result.get("type") == "string":
                        data = json.loads(result["value"])
                        print(f"\n{'='*60}")
                        print(f"  GL_VENDOR:   {data.get('vendor')}")
                        print(f"  GL_RENDERER: {data.get('renderer')}")
                        print(f"{'='*60}")

                        renderer = data.get("renderer", "")
                        if "Adreno" in renderer and "SwiftShader" not in renderer:
                            print("\n  GPU SPOOF VERIFIED via Chrome CDP!")
                        elif "SwiftShader" in renderer:
                            print("\n  FAILED: Still showing SwiftShader!")
                        else:
                            print(f"\n  Unexpected: {renderer}")
                    else:
                        print(f"   Error: {result}")
                    break
            else:
                print("   Timeout waiting for WebGL response")

    await adb.remove_forward(port)
    await chrome.force_stop()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
