#!/usr/bin/env python3
"""Test full GPU spoof (renderer + vendorID) on redroid container.

Connects to damru-test-0 on port 5600, patches vulkan.pastel.so,
installs Chrome, launches it, queries WebGL via CDP.
"""
import asyncio
import json
import struct
import os
import sys
import tempfile

# Add damru to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "damru"))

ADB_HOST = "localhost"
ADB_PORT = 5600
CONTAINER = "damru-test-0"

# Target device: Galaxy S24 Ultra with Adreno 750
TARGET_RENDERER = "Adreno (TM) 750"
TARGET_VENDOR = "Qualcomm"
TARGET_VENDOR_ID = 0x5143  # Qualcomm Vulkan vendorID
SWIFTSHADER_VENDOR_ID = 0x1AE0  # Google/SwiftShader


async def run_adb(*args, timeout=30):
    """Run an ADB command and return stdout."""
    cmd = ["adb", "-H", ADB_HOST, "-P", "5037", "-s", f"{ADB_HOST}:{ADB_PORT}"] + list(args)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return stdout.decode("utf-8", errors="replace").strip()


async def adb_shell(command, timeout=30):
    """Run a shell command via ADB."""
    return await run_adb("shell", command, timeout=timeout)


async def check_chrome_installed():
    """Check if Chrome is installed."""
    out = await adb_shell("pm path com.android.chrome")
    return "package:" in out


async def install_chrome():
    """Install Chrome APKs via docker cp + pm install sessions."""
    print("  Installing Chrome APKs...")
    apk_dir = "chrome-apks/145.0.7632.75"

    apks = [
        ("google_trichrome_library.apk", "trichrome.apk"),
        ("base.apk", "base.apk"),
        ("split_chrome.apk", "split_chrome.apk"),
        ("split_config.en.apk", "split_config.en.apk"),
        ("split_on_demand.apk", "split_on_demand.apk"),
    ]

    # Copy APKs via docker cp (WSL path)
    wsl_apk_dir = "/mnt/c/path/to/damru/chrome-apks/145.0.7632.75"
    for local_name, remote_name in apks:
        cmd = f'wsl -d Ubuntu -- docker cp "{wsl_apk_dir}/{local_name}" {CONTAINER}:/data/local/tmp/{remote_name}'
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)

    # Install trichrome first
    out = await adb_shell("pm install -r /data/local/tmp/trichrome.apk", timeout=60)
    print(f"    Trichrome: {out}")

    # Install Chrome split APKs via session
    install_cmd = """
TOTAL=$(stat -c%s /data/local/tmp/base.apk)
TOTAL=$((TOTAL + $(stat -c%s /data/local/tmp/split_chrome.apk)))
TOTAL=$((TOTAL + $(stat -c%s /data/local/tmp/split_config.en.apk)))
TOTAL=$((TOTAL + $(stat -c%s /data/local/tmp/split_on_demand.apk)))
SID=$(pm install-create -S $TOTAL 2>&1 | grep -oE '[0-9]+')
pm install-write -S $(stat -c%s /data/local/tmp/base.apk) $SID base /data/local/tmp/base.apk
pm install-write -S $(stat -c%s /data/local/tmp/split_chrome.apk) $SID split_chrome /data/local/tmp/split_chrome.apk
pm install-write -S $(stat -c%s /data/local/tmp/split_config.en.apk) $SID split_config /data/local/tmp/split_config.en.apk
pm install-write -S $(stat -c%s /data/local/tmp/split_on_demand.apk) $SID split_on_demand /data/local/tmp/split_on_demand.apk
pm install-commit $SID
"""
    out = await adb_shell(install_cmd, timeout=120)
    print(f"    Chrome install: {out[-200:]}")


async def get_webgl_via_cdp():
    """Launch Chrome, connect CDP, query WebGL."""
    import aiohttp

    # Force-stop Chrome first
    await adb_shell("am force-stop com.android.chrome")
    await asyncio.sleep(1)

    # Launch Chrome with remote debugging
    await adb_shell(
        "am start -n com.android.chrome/com.google.android.apps.chrome.Main "
        "-d 'about:blank' --activity-clear-task"
    )
    await asyncio.sleep(3)

    # Find Chrome devtools socket
    out = await adb_shell("cat /proc/net/unix | grep devtools")
    if "devtools" not in out:
        print("  WARNING: No devtools socket found")
        return None, None

    # Forward devtools port
    try:
        await run_adb("forward", "tcp:9222", "localabstract:chrome_devtools_remote")
    except Exception:
        pass

    await asyncio.sleep(1)

    # Connect to CDP
    async with aiohttp.ClientSession() as session:
        async with session.get("http://localhost:9222/json") as resp:
            tabs = await resp.json()

        if not tabs:
            print("  No tabs found")
            return None, None

        ws_url = tabs[0].get("webSocketDebuggerUrl")
        if not ws_url:
            print("  No WebSocket URL")
            return None, None

        import aiohttp
        async with session.ws_connect(ws_url) as ws:
            # Query WebGL
            msg = {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """
                    (function() {
                        var c = document.createElement('canvas');
                        var gl = c.getContext('webgl2') || c.getContext('webgl');
                        if (!gl) return JSON.stringify({error: 'no webgl'});
                        var ext = gl.getExtension('WEBGL_debug_renderer_info');
                        return JSON.stringify({
                            vendor: ext  gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : 'N/A',
                            renderer: ext  gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'N/A'
                        });
                    })()
                    """,
                    "returnByValue": True
                }
            }
            await ws.send_json(msg)
            resp = await asyncio.wait_for(ws.receive_json(), timeout=10)
            result = resp.get("result", {}).get("result", {}).get("value", "{}")
            data = json.loads(result)
            return data.get("vendor"), data.get("renderer")


async def patch_vulkan_so():
    """Binary-patch vulkan.pastel.so with renderer strings + vendorID."""
    vulkan_so = "/vendor/lib64/hw/vulkan.pastel.so"
    backup = "/data/local/tmp/damru_vk_pastel_orig.so"

    # Check if file exists
    out = await adb_shell(f"test -f {vulkan_so} && echo OK")
    if "OK" not in out:
        print("  ERROR: vulkan.pastel.so not found!")
        return False

    # Backup original
    out = await adb_shell(f"test -f {backup} && echo EXISTS")
    if "EXISTS" not in out:
        await adb_shell(f"su 0 cp {vulkan_so} {backup}")
        print("  Backed up original vulkan.pastel.so")

    # Pull backup to local
    with tempfile.NamedTemporaryFile(delete=False, suffix=".so") as tmp:
        local_path = tmp.name

    try:
        await run_adb("pull", backup, local_path, timeout=60)

        with open(local_path, "rb") as f:
            data = bytearray(f.read())

        print(f"  File size: {len(data):,} bytes")
        total_patches = 0

        # --- String patches ---
        replacements = [
            (b"SwiftShader Device", TARGET_RENDERER),
            (b"SwiftShader driver", "Adreno driver"),
        ]

        for orig_bytes, target_str in replacements:
            target_encoded = target_str.encode("utf-8")[:len(orig_bytes)]
            if len(target_encoded) < len(orig_bytes):
                target_encoded += b"\x00" * (len(orig_bytes) - len(target_encoded))

            count = 0
            idx = 0
            while True:
                idx = data.find(orig_bytes, idx)
                if idx == -1:
                    break
                data[idx:idx + len(orig_bytes)] = target_encoded
                count += 1
                idx += len(orig_bytes)

            print(f"  String: {orig_bytes.decode()!r} -> {target_str!r}: {count} patches")
            total_patches += count

        # --- VendorID patch ---
        old_vid_bytes = struct.pack("<I", SWIFTSHADER_VENDOR_ID)
        new_vid_bytes = struct.pack("<I", TARGET_VENDOR_ID)
        device_id_bytes = struct.pack("<I", 0xC0DE)

        # Find all deviceID 0xC0DE positions
        device_positions = []
        idx = 0
        while True:
            idx = data.find(device_id_bytes, idx)
            if idx == -1:
                break
            device_positions.append(idx)
            idx += 4
        print(f"  Found {len(device_positions)} deviceID 0xC0DE positions")

        vid_count = 0
        for dpos in device_positions:
            search_start = max(0, dpos - 64)
            search_end = min(len(data), dpos + 64)
            vidx = search_start
            while True:
                vidx = data.find(old_vid_bytes, vidx, search_end)
                if vidx == -1:
                    break
                offset = vidx - dpos
                print(f"    vendorID at 0x{vidx:08X} (offset {offset} from deviceID at 0x{dpos:08X})")
                data[vidx:vidx + 4] = new_vid_bytes
                vid_count += 1
                vidx += 4

        print(f"  VendorID: 0x{SWIFTSHADER_VENDOR_ID:04X} -> 0x{TARGET_VENDOR_ID:04X}: {vid_count} patches")
        total_patches += vid_count

        if total_patches == 0:
            print("  ERROR: No patches applied!")
            return False

        # Write patched file
        with open(local_path, "wb") as f:
            f.write(data)

        # Push back
        await adb_shell("su 0 mount -o remount,rw /vendor 2>/dev/null")
        patched_tmp = "/data/local/tmp/damru_patched_tmp.so"
        await run_adb("push", local_path, patched_tmp, timeout=60)
        await adb_shell(f"su 0 cp {patched_tmp} {vulkan_so}")
        await adb_shell(f"su 0 chmod 644 {vulkan_so}")
        await adb_shell(f"su 0 rm -f {patched_tmp}")
        await adb_shell("su 0 mount -o remount,ro /vendor 2>/dev/null")
        await adb_shell("su 0 sync")

        print(f"  Total: {total_patches} patches applied")
        return True

    finally:
        try:
            os.unlink(local_path)
        except OSError:
            pass


async def main():
    print("=== GPU Full Spoof Test ===")
    print(f"Target: {TARGET_RENDERER} by {TARGET_VENDOR} (vendorID=0x{TARGET_VENDOR_ID:04X})")
    print()

    # Connect ADB
    print("[1] Connecting ADB...")
    out = await run_adb("connect", f"{ADB_HOST}:{ADB_PORT}")
    print(f"  {out}")
    await asyncio.sleep(2)

    # Check Chrome
    print("[2] Checking Chrome...")
    if await check_chrome_installed():
        print("  Chrome already installed")
    else:
        await install_chrome()
        if not await check_chrome_installed():
            print("  FAILED: Chrome not installed!")
            return

    # Get baseline WebGL
    print("[3] Baseline WebGL (before patch)...")
    try:
        vendor, renderer = await get_webgl_via_cdp()
        print(f"  Vendor:   {vendor}")
        print(f"  Renderer: {renderer}")
    except Exception as e:
        print(f"  Baseline check failed: {e}")

    # Force-stop Chrome before patching
    await adb_shell("am force-stop com.android.chrome")
    await asyncio.sleep(1)

    # Patch vulkan.pastel.so
    print("[4] Patching vulkan.pastel.so...")
    success = await patch_vulkan_so()
    if not success:
        print("  FAILED!")
        return

    # Get patched WebGL
    print("[5] Patched WebGL (after patch)...")
    try:
        vendor, renderer = await get_webgl_via_cdp()
        print(f"  Vendor:   {vendor}")
        print(f"  Renderer: {renderer}")

        # Verify
        print()
        print("=== RESULTS ===")
        renderer_ok = TARGET_RENDERER in (renderer or "")
        vendor_ok = TARGET_VENDOR in (vendor or "")
        print(f"  Renderer contains '{TARGET_RENDERER}': {'PASS' if renderer_ok else 'FAIL'}")
        print(f"  Vendor contains '{TARGET_VENDOR}':   {'PASS' if vendor_ok else 'FAIL'}")

        if renderer_ok and vendor_ok:
            print("  >>> FULL GPU SPOOF: SUCCESS <<<")
        else:
            print("  >>> PARTIAL SPOOF — needs investigation <<<")
    except Exception as e:
        print(f"  Patched check failed: {e}")

    # Cleanup
    await adb_shell("am force-stop com.android.chrome")
    try:
        await run_adb("forward", "--remove", "tcp:9222")
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
