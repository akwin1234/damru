#!/usr/bin/env python3
"""Test: Random OS version + IP leak check (ipleak.net + whoer.net).

Verifies:
  1. Random OS version from supported_android_versions
  2. Client Hints on HTTPS match override
  3. No WebRTC IP leak (real Indian IP hidden)
  4. Proxy IP showing as Philippines

Usage: python test_ip_leak.py [serial] [proxy]
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "damru"))

from damru.adb import ADB
from damru.root import RootOps
from damru.cdp import CDPConnection
from damru.chrome import ChromeManager
from damru.devices import get_random_device, pick_random_android_version, pick_random_chrome_version
from damru.utils import setup_logging, sleep


async def goto_retry(page, url, retries=8, wait_until="domcontentloaded", timeout=30000):
    """Navigate with retries for rotating proxy that drops connections."""
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout)
            return True
        except Exception as e:
            err = str(e).split("\n")[0][:80]
            if attempt < retries:
                print(f"    Retry {attempt}/{retries}: {err}")
                await sleep(3)
            else:
                raise
    return False


async def main():
    setup_logging(debug=False)
    serial = sys.argv[1] if len(sys.argv) > 1 else "localhost:5600"
    proxy = sys.argv[2] if len(sys.argv) > 2 else "proxy.example:50000"

    adb = ADB(serial=serial)
    await adb.ensure_server()
    info = await adb.get_device_info()
    print(f"\n=== IP Leak + OS Version Test ===")
    print(f"Emulator: {info.get('model')} Android {info.get('android_version')}")

    # Pick device + random OS
    device = get_random_device(android_version=info.get("android_version"))
    android_ver, sdk_ver = pick_random_android_version(device)
    print(f"\nTarget: {device.name} ({device.model})")
    print(f"  OS versions available: {device.supported_android_versions}")
    print(f"  Randomly picked: Android {android_ver} (SDK {sdk_ver})")

    # Root + GPU
    root = RootOps(adb)
    await root.check_root()
    await root.apply_gpu_binary_spoof(device)
    await root.apply_device_props(device, safe_only=False)
    await root.hide_emulator_identity()

    # WebRTC block
    await root.apply_webrtc_block()
    print("  WebRTC iptables: applied")

    # Set proxy BEFORE Chrome
    await adb.shell(f"settings put global http_proxy {proxy}", allow_failure=True)
    print(f"  Proxy: {proxy}")

    # Chrome fresh
    chrome = ChromeManager(adb)
    await chrome.detect_package()
    version = await chrome.get_version()
    await chrome.force_stop()
    await chrome.clear_all_data()
    await chrome.patch_preferences("en-US", "en-US,en;q=0.9")
    await chrome.launch()
    await chrome.dismiss_fre()
    await chrome.wait_for_devtools_socket(timeout=15.0)

    # CDP
    cdp = CDPConnection(adb)
    await cdp.setup_port_forward()
    ctx = await cdp.connect()
    page = ctx.pages[0]

    # UA override with random OS + Chrome version
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
    s = await ctx.new_cdp_session(page)
    await s.send("Emulation.setUserAgentOverride", {
        "userAgent": ua,
        "platform": "Linux armv8l",
        "userAgentMetadata": ua_metadata,
    })
    grease = next((b for b in brand_info["brands"] if "Not" in b["brand"]), {})
    brand_order = ", ".join(b["brand"] for b in brand_info["brands"])
    print(f"  Chrome: {chrome_ver} (grease: {grease.get('brand','')};v={grease.get('version','')})")
    print(f"  Brand order: [{brand_order}]")
    print(f"  UA: Android {android_ver}, {device.model}, Chrome/{chrome_ver}")

    # ===== 1. Client Hints on HTTPS =====
    print("\n[1] Client Hints (HTTPS)")
    try:
        await goto_retry(page, "https://www.example.com", retries=5, timeout=20000)
        ch = await page.evaluate("""async () => {
            const r = {};
            if (navigator.userAgentData) {
                const d = await navigator.userAgentData.getHighEntropyValues([
                    'platformVersion', 'model', 'fullVersionList'
                ]);
                r.platformVersion = d.platformVersion;
                r.model = d.model;
                r.mobile = navigator.userAgentData.mobile;
                r.brands = d.fullVersionList.map(b => b.brand + '/' + b.version).join(', ');
            }
            const m = navigator.userAgent.match(/Android (\\d+)/);
            r.uaVer = m  m[1] : '';
            return r;
        }""")
        print(f"    UA Android: {ch.get('uaVer')}")
        print(f"    CH platformVersion: {ch.get('platformVersion')}")
        print(f"    CH model: {ch.get('model')}")
        print(f"    CH mobile: {ch.get('mobile')}")
        print(f"    CH brands: {ch.get('brands', '')[:100]}")
    except Exception as e:
        print(f"    FAILED: {e}")

    # ===== 2. ipleak.net =====
    print("\n[2] ipleak.net")
    try:
        await goto_retry(page, "https://ipleak.net/", retries=5, wait_until="load", timeout=45000)
        await sleep(10)
        ip_info = await page.evaluate("""() => {
            const body = document.body.innerText;
            // Find all IPs on page
            const allIPs = [...body.matchAll(/(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})/g)].map(m => m[1]);
            // Unique IPs
            const unique = [...new Set(allIPs)];

            // WebRTC detection
            let webrtcText = '';
            document.querySelectorAll('*').forEach(el => {
                if (el.textContent && el.textContent.toLowerCase().includes('webrtc') && el.innerText.length < 500) {
                    webrtcText += el.innerText + '\\n';
                }
            });
            const webrtcIPs = [...webrtcText.matchAll(/(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})/g)].map(m => m[1]);

            return {
                uniqueIPs: unique.slice(0, 15),
                webrtcIPs: [...new Set(webrtcIPs)],
                webrtcText: webrtcText.trim().substring(0, 400),
                title: document.title
            };
        }""")
        unique_ips = ip_info.get("uniqueIPs", [])
        webrtc_ips = ip_info.get("webrtcIPs", [])
        print(f"    IPs found: {unique_ips}")
        if webrtc_ips:
            print(f"    *** WebRTC LEAK: {webrtc_ips} ***")
        else:
            print(f"    WebRTC: NO LEAKS")
        if ip_info.get("webrtcText"):
            for line in ip_info["webrtcText"].split("\n")[:5]:
                if line.strip():
                    print(f"    WebRTC section: {line.strip()[:120]}")
    except Exception as e:
        print(f"    FAILED: {e}")

    # ===== 3. whoer.net =====
    print("\n[3] whoer.net")
    try:
        await goto_retry(page, "https://whoer.net/", retries=5, timeout=60000)
        await sleep(20)  # Very heavy JS
        whoer = await page.evaluate("""() => {
            const body = document.body.innerText;
            const ipMatch = body.match(/(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})/);
            const pctMatch = body.match(/(\\d+)\\s*%/);

            // Find specific data fields
            const data = {};
            const lines = body.split('\\n');
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim().toLowerCase();
                if (line.includes('webrtc')) data.webrtc = lines[i].trim() + (lines[i+1]  ' ' + lines[i+1].trim() : '');
                if (line.includes('dns')) data.dns = lines[i].trim() + (lines[i+1]  ' ' + lines[i+1].trim() : '');
                if (line.includes('your ip') || line.includes('ip address')) data.ip_row = lines[i].trim();
                if (line.includes('country')) data.country = lines[i].trim() + (lines[i+1]  ' ' + lines[i+1].trim() : '');
                if (line.includes('anonymity')) data.anonymity = lines[i].trim() + (lines[i+1]  ' ' + lines[i+1].trim() : '');
            }

            return {
                ip: ipMatch  ipMatch[1] : 'N/A',
                score: pctMatch  pctMatch[1] + '%' : 'N/A',
                data: data,
                snippet: body.substring(0, 600)
            };
        }""")
        print(f"    IP: {whoer.get('ip', '')}")
        print(f"    Anonymity: {whoer.get('score', '')}")
        data = whoer.get("data", {})
        for key in ["country", "webrtc", "dns", "anonymity"]:
            if key in data:
                print(f"    {key}: {data[key][:120]}")
    except Exception as e:
        print(f"    FAILED: {e}")

    # Cleanup
    await adb.shell("settings put global http_proxy :0", allow_failure=True)
    await cdp.disconnect()
    await chrome.force_stop()
    print("\n=== DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
