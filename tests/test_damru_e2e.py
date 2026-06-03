#!/usr/bin/env python3
"""Quick E2E test of damru core flow on a running redroid container.

Tests: ADB connect, root, GPU binary spoof, Chrome launch, FRE dismiss,
CDP connect, WebGL query. WebRTC is disabled.

Usage: python test_damru_e2e.py [serial]
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "damru"))

from damru.adb import ADB
from damru.root import RootOps
from damru.chrome import ChromeManager
from damru.cdp import CDPConnection
from damru.devices import get_device, get_random_device, pick_random_android_version, pick_random_chrome_version
from damru.profiles import build_profile
from damru.proxy import build_accept_language
from damru.utils import setup_logging, logger


async def main():
    setup_logging(debug=True)
    serial = sys.argv[1] if len(sys.argv) > 1 else "localhost:5600"

    print(f"\n=== damru E2E Test (serial={serial}) ===\n")

    # 1. ADB
    adb = ADB(serial=serial)
    await adb.ensure_server()
    info = await adb.get_device_info()
    print(f"[1] Device: {info.get('model')} Android {info.get('android_version')}")

    # 2. Root
    root = RootOps(adb)
    await root.check_root()
    print(f"[2] Root: OK")

    # 3. Pick device
    real_android = info.get("android_version", "")
    device = get_random_device(android_version=real_android or None)
    print(f"[3] Target: {device.name} ({device.webgl_renderer}, {device.webgl_vendor})")

    # 4. GPU binary spoof
    print(f"[4] GPU spoof...")
    await root.apply_gpu_binary_spoof(device)

    # Verify via SurfaceFlinger (if SF restart needed)
    sf = await adb.shell("dumpsys SurfaceFlinger", timeout=10, allow_failure=True)
    for line in sf.split('\n'):
        if 'GLES' in line:
            print(f"    SF: {line.strip()[:120]}")
            break

    # 5. Props
    version_match = real_android == device.android_version
    await root.apply_device_props(device, safe_only=not version_match)
    await root.hide_emulator_identity()
    print(f"[5] Props applied (version_match={version_match})")

    # 6. Chrome
    chrome = ChromeManager(adb)
    await chrome.detect_package()
    version = await chrome.get_version()
    print(f"[6] Chrome: {chrome.package} v{version}")

    if not version:
        print("    Chrome not installed - skipping launch test")
        return

    # 6b. Set system HTTP proxy BEFORE Chrome launch (so all traffic routes through it)
    proxy = sys.argv[2] if len(sys.argv) > 2 else None
    if proxy:
        await adb.shell(f"settings put global http_proxy {proxy}", allow_failure=True)
        print(f"[6b] System proxy set: {proxy}")

    # 7. Fresh Chrome
    await chrome.force_stop()
    await chrome.clear_all_data()
    await chrome.patch_preferences("en-US", "en-US,en;q=0.9")
    await chrome.launch()
    print("[7] Chrome launched")

    # 8. FRE dismiss
    await chrome.dismiss_fre()
    print("[8] FRE dismissed")

    # 9. Devtools
    socket_ok = await chrome.wait_for_devtools_socket(timeout=15.0)
    print(f"[9] Devtools socket: {socket_ok}")

    if not socket_ok:
        print("    No devtools socket - cannot connect CDP")
        await chrome.force_stop()
        return

    # 10. CDP
    cdp = CDPConnection(adb)
    await cdp.setup_port_forward()
    ctx = await cdp.connect()
    print(f"[10] CDP connected, pages={len(ctx.pages)}")

    # 10b. UA override with random OS + Chrome version
    android_ver, sdk_ver = pick_random_android_version(device)
    chrome_ver, brand_info = pick_random_chrome_version()
    ua = (
        f"Mozilla/5.0 (Linux; Android {android_ver}; {device.model}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_ver} Mobile Safari/537.36"
    )
    ua_metadata = {
        "brands": brand_info["brands"],
        "fullVersionList": brand_info["fullVersionList"],
        "fullVersion": chrome_ver,
        "platform": "Android",
        "platformVersion": f"{android_ver}.0.0",
        "architecture": "",
        "model": device.model,
        "mobile": True,
        "bitness": "",
    }
    page0 = ctx.pages[0] if ctx.pages else None
    if page0:
        try:
            cdp_session = await ctx.new_cdp_session(page0)
            await cdp_session.send("Emulation.setUserAgentOverride", {
                "userAgent": ua,
                "platform": "Linux armv8l",
                "userAgentMetadata": ua_metadata,
            })
            grease = [b for b in brand_info["brands"] if "Not" in b["brand"]][0]
            print(f"[10b] UA override: Android {android_ver} ({device.model}) Chrome/{chrome_ver}")
            print(f"      Grease: {grease['brand']};v={grease['version']}")
            print(f"      OS versions: {device.supported_android_versions} -> picked {android_ver}")
        except Exception as e:
            print(f"[10b] UA override failed: {e}")

    # 11. WebGL query
    page = ctx.pages[0] if ctx.pages else None
    if page:
        await page.goto("data:text/html,<h1>E2E GPU Test</h1>", wait_until="domcontentloaded")
        result = await page.evaluate("""() => {
            const c = document.createElement('canvas');
            const gl = c.getContext('webgl2') || c.getContext('webgl');
            if (!gl) return {error: 'no webgl'};
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            return {
                vendor: ext  gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
                renderer: ext  gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)
            };
        }""")
        print(f"\n{'='*60}")
        print(f"  GL_VENDOR:   {result.get('vendor')}")
        print(f"  GL_RENDERER: {result.get('renderer')}")
        print(f"{'='*60}")

        renderer = result.get("renderer", "")
        if "SwiftShader" not in renderer and device.webgl_renderer.split("(")[0].strip() in renderer:
            print(f"\n  GPU SPOOF MATCH for {device.name}!")
        elif "SwiftShader" in renderer:
            print(f"\n  FAILED: Still SwiftShader")
        else:
            print(f"\n  Renderer: {renderer} (expected contains: {device.webgl_renderer})")

    # 11b. UA / Client Hints / OS version check
    if page:
        ua_info = await page.evaluate("""() => {
            const r = {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
            };
            if (navigator.userAgentData) {
                r.mobile = navigator.userAgentData.mobile;
                r.platform_ch = navigator.userAgentData.platform;
                // getHighEntropyValues is async
            }
            // Extract Android version from UA string
            const m = navigator.userAgent.match(/Android (\\d+)/);
            r.android_ver = m  m[1] : 'unknown';
            return r;
        }""")
        print(f"\n[11b] UA Check:")
        print(f"    Android version (from UA): {ua_info.get('android_ver')}")
        print(f"    Platform: {ua_info.get('platform')}")
        print(f"    Mobile: {ua_info.get('mobile')}")
        print(f"    UA: {ua_info.get('userAgent', '')[:100]}...")

        # High-entropy Client Hints (async)
        try:
            ch = await page.evaluate("""async () => {
                if (!navigator.userAgentData) return {error: 'no userAgentData'};
                const d = await navigator.userAgentData.getHighEntropyValues([
                    'platformVersion', 'model', 'fullVersionList', 'architecture'
                ]);
                return {
                    platformVersion: d.platformVersion,
                    model: d.model,
                    arch: d.architecture,
                    brands: d.fullVersionList.map(b => b.brand + '/' + b.version).join(', ')
                };
            }""")
            print(f"    CH platformVersion: {ch.get('platformVersion')}")
            print(f"    CH model: {ch.get('model')}")
            print(f"    CH brands: {ch.get('brands', '')[:80]}")
        except Exception as e:
            print(f"    Client Hints: {e}")

    # 12. IP / WebRTC leak tests (requires proxy - already set at step 6b)
    if proxy and page:
        print(f"\n[12] IP Leak Tests (proxy={proxy})")

        # ipleak.net - check visible IP + WebRTC
        try:
            await page.goto("https://ipleak.net/", wait_until="load", timeout=30000)
            await asyncio.sleep(8)  # Wait for JS-rendered content
            ip_info = await page.evaluate("""() => {
                // Try multiple selectors for IP
                const selectors = ['.your_ip', '#ipv4', '.ip-value', 'h1', '.ip_address'];
                let ip = null;
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && /\\d+\\.\\d+\\.\\d+/.test(el.textContent)) {
                        ip = el.textContent.trim();
                        break;
                    }
                }
                // Fallback: find any element with an IP pattern
                if (!ip) {
                    const all = document.body.innerText;
                    const m = all.match(/(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})/);
                    if (m) ip = m[1];
                }
                // WebRTC detection
                const webrtcEls = document.querySelectorAll('[id*="webrtc"] td, [class*="webrtc"] td');
                const webrtcIps = [];
                webrtcEls.forEach(el => {
                    const m = el.textContent.match(/(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})/);
                    if (m) webrtcIps.push(m[1]);
                });
                return { ip: ip || 'not found', webrtc: webrtcIps, title: document.title };
            }""")
            print(f"    ipleak.net: IP={ip_info.get('ip', '')}")
            webrtc = ip_info.get('webrtc', [])
            if webrtc:
                print(f"    ipleak.net WebRTC LEAK: {webrtc}")
            else:
                print(f"    ipleak.net WebRTC: NO LEAKS")
        except Exception as e:
            print(f"    ipleak.net: error - {e}")

        # whoer.net - overall anonymity score
        try:
            await page.goto("https://whoer.net/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(15)  # whoer.net is heavy JS, needs time
            whoer = await page.evaluate("""() => {
                // Extract IP from page
                const body = document.body.innerText;
                const ipMatch = body.match(/(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})/);
                // Extract anonymity percentage
                const pctMatch = body.match(/(\\d+)\\s*%/);
                return {
                    ip: ipMatch  ipMatch[1] : 'N/A',
                    score: pctMatch  pctMatch[1] + '%' : 'N/A',
                    title: document.title
                };
            }""")
            print(f"    whoer.net: score={whoer.get('score', '')}, IP={whoer.get('ip', '')}")
        except Exception as e:
            print(f"    whoer.net: error - {e}")

        # Clear proxy
        await adb.shell("settings put global http_proxy :0", allow_failure=True)
    elif not proxy:
        print("\n[12] Skipping IP leak tests (pass proxy as 2nd arg, e.g. proxy.example:50000)")

    # Cleanup
    await cdp.disconnect()
    await chrome.force_stop()
    print("\nE2E test complete!")


if __name__ == "__main__":
    asyncio.run(main())
