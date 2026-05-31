#!/usr/bin/env python3
"""GPU spoof verification — runs INSIDE WSL.

Connects directly to redroid container IP via ADB.
Installs Chrome, applies GPU spoof, queries WebGL via CDP.
"""
import asyncio
import json
import os
import re
import subprocess
import sys


SERIAL = "YOUR_ADB_SERIAL_HERE"  # e.g., "127.0.0.1:5555" (Redroid) or "9889d6444b49" (Physical)
CONTAINER = "gpu-test"
APK_DIR = "chrome-apks/145.0.7632.75"
PATCHED_SO = "native/vulkan_pastel_patched.so"


async def run(cmd, timeout=30):
    """Run a shell command and return stdout."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return stdout.decode().strip()


async def adb(cmd, timeout=15):
    """Run an ADB command."""
    return await run(f"adb -s {SERIAL} {cmd}", timeout=timeout)


async def adb_shell(cmd, timeout=15):
    """Run adb shell command."""
    return await run(f"adb -s {SERIAL} shell '{cmd}'", timeout=timeout)


async def docker_exec(cmd, timeout=30):
    """Run command via docker exec."""
    return await run(f"docker exec {CONTAINER} {cmd}", timeout=timeout)


async def main():
    print(f"\n{'='*60}")
    print(f"  GPU SPOOF CDP VERIFICATION TEST (WSL)")
    print(f"  Container: {CONTAINER} ({SERIAL})")
    print(f"{'='*60}\n")

    # Step 1: Verify ADB connection
    boot = await adb_shell("getprop sys.boot_completed")
    assert boot == "1", f"Boot not complete: {boot}"
    model = await adb_shell("getprop ro.product.model")
    android = await adb_shell("getprop ro.build.version.release")
    print(f"[1] Device: {model} Android {android}")

    # Step 2: Check root
    root_out = await adb_shell("su 0 id")
    assert "uid=0" in root_out, f"No root: {root_out}"
    print(f"[2] Root: OK (su 0)")

    # Step 3: Check Chrome
    chrome_path = await adb_shell("pm path com.android.chrome")
    if not chrome_path:
        print("[3] Chrome not installed — installing...")

        # Install TrichromeLibrary
        out = await adb(f'install "{APK_DIR}/google_trichrome_library.apk"', timeout=120)
        assert "Success" in out, f"Trichrome install failed: {out}"
        print("   TrichromeLibrary: OK")

        # Push all split APKs
        splits = ["base.apk", "split_chrome.apk", "split_config.en.apk", "split_on_demand.apk"]
        total = sum(os.path.getsize(os.path.join(APK_DIR, s)) for s in splits)

        for s in splits:
            path = os.path.join(APK_DIR, s)
            await adb(f'push "{path}" /data/local/tmp/{s}', timeout=60)

        # Create install session
        out = await adb_shell(f"pm install-create -S {total}")
        m = re.search(r'\[(\d+)\]', out)
        assert m, f"Failed to create session: {out}"
        session = m.group(1)

        for s in splits:
            size = os.path.getsize(os.path.join(APK_DIR, s))
            name = s.replace('.apk', '')
            await adb_shell(f"pm install-write -S {size} {session} {name} /data/local/tmp/{s}")

        out = await adb_shell(f"pm install-commit {session}")
        assert "Success" in out, f"Install failed: {out}"
        print("   Chrome: installed")

    version = await adb_shell("dumpsys package com.android.chrome | grep versionName | head -1")
    print(f"[3] Chrome: {version.strip()}")

    # Step 4: Apply GPU binary spoof
    print("[4] Applying GPU spoof...")

    # Copy patched .so via docker cp (fast + reliable)
    await run(f"docker cp '{PATCHED_SO}' '{CONTAINER}:/data/local/tmp/vulkan_patched.so'", timeout=30)

    # Backup original + apply patch
    await adb_shell("su 0 sh -c 'test -f /data/local/tmp/vulkan_orig.so || cp /vendor/lib64/hw/vulkan.pastel.so /data/local/tmp/vulkan_orig.so'")
    await adb_shell("su 0 cp /data/local/tmp/vulkan_patched.so /vendor/lib64/hw/vulkan.pastel.so")
    await adb_shell("su 0 chmod 644 /vendor/lib64/hw/vulkan.pastel.so")
    print("   .so patched")

    # Restart SurfaceFlinger
    await adb_shell("su 0 setprop ctl.restart surfaceflinger")
    print("   SurfaceFlinger restarting...")
    await asyncio.sleep(5)

    # Verify via SF dump
    sf = await adb_shell("dumpsys SurfaceFlinger | grep GLES", timeout=10)
    print(f"   SF: {sf.strip()}")
    if "SwiftShader" in sf:
        print("   WARNING: Still showing SwiftShader in SurfaceFlinger")

    # Step 5: Ensure ro.debuggable=1
    dbg = await adb_shell("getprop ro.debuggable")
    print(f"[5] ro.debuggable={dbg}")

    # Step 6: Fresh Chrome launch
    await adb_shell("am force-stop com.android.chrome")
    await adb_shell("pm clear com.android.chrome")
    await asyncio.sleep(1)

    # Write First Run sentinel to skip FRE COMPLETELY
    # Must do this AFTER pm clear and before first launch
    await adb_shell("su 0 sh -c 'mkdir -p /data/data/com.android.chrome/app_chrome/Default'")

    # Write preferences
    prefs = '{"browser":{"has_seen_welcome_page":true},"signin":{"allowed_on_next_startup":false},"first_run_tabs":[]}'
    import base64
    prefs_b64 = base64.b64encode(prefs.encode()).decode()
    await adb_shell(f"su 0 sh -c 'echo {prefs_b64} | base64 -d > /data/data/com.android.chrome/app_chrome/Default/Preferences'")

    # Create First Run sentinel
    await adb_shell("su 0 touch '/data/data/com.android.chrome/app_chrome/First Run'")

    # Fix ownership
    await adb_shell("su 0 sh -c 'CUID=$(stat -c%u /data/data/com.android.chrome) && CGID=$(stat -c%g /data/data/com.android.chrome) && chown -R $CUID:$CGID /data/data/com.android.chrome/app_chrome && chmod -R 770 /data/data/com.android.chrome/app_chrome'")

    print("[6] Preferences + First Run sentinel written")

    # Launch Chrome — use 'cmd activity' as fallback for 'am'
    try:
        out = await adb_shell("am start -n com.android.chrome/com.google.android.apps.chrome.Main -d about:blank")
        if "Error" in out or "not found" in out:
            raise Exception(out)
    except Exception:
        out = await adb_shell("cmd activity start-activity -n com.android.chrome/com.google.android.apps.chrome.Main")
    print(f"   Chrome launch: {out.strip()}")
    await asyncio.sleep(5)

    # Check Chrome alive
    pid = await adb_shell("pidof com.android.chrome")
    print(f"   Chrome PID: {pid or 'DEAD'}")

    if not pid:
        print("   Chrome CRASHED with sentinel. Trying without (FRE dismiss)...")
        await adb_shell("pm clear com.android.chrome")
        await asyncio.sleep(1)
        # Clear logcat for fresh crash info
        try:
            await adb_shell("logcat -c")
        except Exception:
            pass

        try:
            await adb_shell("am start -n com.android.chrome/com.google.android.apps.chrome.Main")
        except Exception:
            await adb_shell("cmd activity start-activity -n com.android.chrome/com.google.android.apps.chrome.Main")
        await asyncio.sleep(8)

        pid = await adb_shell("pidof com.android.chrome")
        print(f"   Chrome PID after retry: {pid or 'DEAD'}")

        if not pid:
            logs = await adb_shell("logcat -d | grep -E 'signal|FATAL|died|Chrome' | tail -5")
            print(f"   Crash logs: {logs[:500]}")
            print("   Chrome keeps crashing. Giving up.")
            return

    # FRE dismiss loop — try multiple times
    for attempt in range(3):
        # Check if devtools socket appeared (means FRE is done)
        sock = await adb_shell("cat /proc/net/unix | grep chrome_devtools")
        if "chrome_devtools" in sock:
            print(f"   Devtools socket found (attempt {attempt})")
            break

        # Try uiautomator dump
        try:
            await adb_shell("uiautomator dump /data/local/tmp/ui.xml")
            ui = await adb_shell("cat /data/local/tmp/ui.xml")
        except Exception:
            ui = ""

        if not ui:
            print(f"   uiautomator dump failed (attempt {attempt})")
            await asyncio.sleep(3)
            continue

        # Check what's showing
        if "fre_pager" in ui or "FirstRun" in ui or "signin_fre" in ui:
            print(f"   FRE detected (attempt {attempt})")
            # Find and tap dismiss/continue button
            tapped = False
            for btn_id in ["signin_fre_dismiss_button", "negative_button",
                           "signin_fre_continue_button", "terms_accept",
                           "tos_and_privacy"]:
                # Flexible regex: resource-id may come before or after bounds
                pattern = f'{btn_id}[^/]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"'
                m = re.search(pattern, ui)
                if not m:
                    # Try reversed attribute order
                    pattern2 = f'bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"[^/]*{btn_id}'
                    m = re.search(pattern2, ui)
                if m:
                    x = (int(m.group(1)) + int(m.group(3))) // 2
                    y = (int(m.group(2)) + int(m.group(4))) // 2
                    print(f"   Tapping {btn_id} at ({x}, {y})")
                    await adb_shell(f"input tap {x} {y}")
                    tapped = True
                    await asyncio.sleep(3)
                    break

            if not tapped:
                # Extract all resource IDs for debugging
                rids = re.findall(r'resource-id="([^"]+)"', ui)
                rids = [r for r in rids if r]
                print(f"   FRE buttons not found. Available IDs: {rids}")
                # Try tapping center-bottom (common FRE button location)
                print("   Trying center-bottom tap (360, 1100)")
                await adb_shell("input tap 360 1100")
                await asyncio.sleep(3)
        else:
            print(f"   No FRE detected in UI (attempt {attempt})")
            await asyncio.sleep(2)

    # Step 7: Wait for devtools socket
    print("[7] Waiting for devtools socket...")
    for i in range(15):
        sock = await adb_shell("cat /proc/net/unix | grep chrome_devtools")
        if "chrome_devtools" in sock:
            print(f"   Socket found after {i+1}s")
            break
        await asyncio.sleep(1)
    else:
        print("   Socket NOT found after 15s, trying anyway...")

    # Step 8: Port forward and CDP query
    print("[8] CDP WebGL query...")
    # Use port 19222 for CDP
    await adb("forward tcp:19222 localabstract:chrome_devtools_remote")
    await asyncio.sleep(0.5)

    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:19222/json", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                tabs = await resp.json()

            if not tabs:
                print("   No tabs!")
                return

            ws_url = tabs[0].get("webSocketDebuggerUrl")
            if not ws_url:
                print("   No WebSocket URL")
                return

            # Fix ws_url to use localhost
            ws_url = ws_url.replace(SERIAL, "localhost:19222")
            print(f"   WS: {ws_url}")

            async with session.ws_connect(ws_url) as ws:
                # Navigate
                await ws.send_json({"id": 1, "method": "Page.navigate",
                                    "params": {"url": "data:text/html,<h1>GPU</h1>"}})
                await asyncio.sleep(2)

                # Drain response
                try:
                    await asyncio.wait_for(ws.receive_json(), timeout=3)
                except:
                    pass

                # WebGL query
                await ws.send_json({
                    "id": 99,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": """(function(){
                            var c=document.createElement('canvas');
                            var gl=c.getContext('webgl2')||c.getContext('webgl');
                            if(!gl)return JSON.stringify({error:'no webgl'});
                            var ext=gl.getExtension('WEBGL_debug_renderer_info');
                            return JSON.stringify({
                                vendor:ext?gl.getParameter(ext.UNMASKED_VENDOR_WEBGL):gl.getParameter(gl.VENDOR),
                                renderer:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER)
                            });
                        })()""",
                        "returnByValue": True,
                    },
                })

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

                            r = data.get("renderer", "")
                            if "Adreno" in r and "SwiftShader" not in r:
                                print("\n  >>> GPU SPOOF VERIFIED via Chrome CDP! <<<")
                            elif "SwiftShader" in r:
                                print("\n  FAILED: Still showing SwiftShader")
                            else:
                                print(f"\n  Renderer: {r}")
                        elif result.get("type") == "object" and "error" in str(result):
                            print(f"   WebGL error: {result}")
                        else:
                            print(f"   Unexpected: {result}")
                        break
                else:
                    print("   Timeout waiting for response")

    except Exception as e:
        print(f"   CDP error: {e}")

    await adb("forward --remove tcp:19222")
    await adb_shell("am force-stop com.android.chrome")
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
