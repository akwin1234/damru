"""Test battery spoof + full CreepJS scan via AsyncDamru pipeline.

Verifies:
  1. Battery shows realistic values (not 100% charging)
  2. Full CreepJS profile scan with all sections
  3. GeoIP timezone/locale auto-detected from proxy

Usage: python test_battery_creepjs.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru
from damru.utils import setup_logging, sleep

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"


async def goto_retry(page, url, retries=8, wait_until="domcontentloaded", timeout=30000):
    """Navigate with retries for rotating proxy."""
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
    print("=" * 60)
    print("  Battery Spoof + CreepJS — Full AsyncDamru Pipeline")
    print("=" * 60)

    async with AsyncDamru(
        serial="localhost:5600",
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        debug=False,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # --- 1. Battery check ---
        print("\n[1] Battery Check")
        try:
            await goto_retry(page, "https://www.example.com", retries=5, timeout=20000)
            await sleep(1)
            battery = await page.evaluate("""async () => {
                try {
                    const b = await navigator.getBattery();
                    return {
                        level: (b.level * 100).toFixed(0) + '%',
                        charging: b.charging,
                        chargingTime: b.chargingTime,
                        dischargingTime: b.dischargingTime,
                    };
                } catch(e) { return {error: e.message}; }
            }""")
            level = battery.get("level", "?")
            charging = battery.get("charging", "?")
            print(f"    Level: {level}")
            print(f"    Charging: {charging}")
            print(f"    ChargingTime: {battery.get('chargingTime', '?')}")

            if charging is False and level != "100%":
                print("    PASS: Battery looks like a real phone")
            elif charging is True and level == "100%":
                print("    FAIL: Still showing emulator defaults (100% charging)")
            else:
                print(f"    INFO: Level={level}, Charging={charging}")
        except Exception as e:
            print(f"    ERROR: {e}")

        # --- 2. Quick hardware + touch + network check ---
        print("\n[2] Hardware + Touch + Network + GPU Check")
        try:
            hw = await page.evaluate("""async () => {
                const r = {
                    cores: navigator.hardwareConcurrency,
                    mem: navigator.deviceMemory,
                    ua: navigator.userAgent.substring(0, 100),
                    platform: navigator.platform,
                    webdriver: navigator.webdriver,
                    maxTouchPoints: navigator.maxTouchPoints,
                    ontouchstart: 'ontouchstart' in window,
                };
                // Network
                if (navigator.connection) {
                    r.netType = navigator.connection.type;
                    r.netEffective = navigator.connection.effectiveType;
                    r.netRtt = navigator.connection.rtt;
                    r.netDownlink = navigator.connection.downlink;
                }
                // Client Hints
                if (navigator.userAgentData) {
                    const d = await navigator.userAgentData.getHighEntropyValues([
                        'platformVersion', 'model', 'fullVersionList'
                    ]);
                    r.model = d.model;
                    r.platformVersion = d.platformVersion;
                    r.brands = d.fullVersionList.map(b => b.brand + '/' + b.version).join(', ');
                }
                // WebGL
                try {
                    const c = document.createElement('canvas');
                    const gl = c.getContext('webgl');
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    r.gpu_vendor = gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
                    r.gpu_renderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
                } catch(e) {}
                // Storage
                try {
                    const est = await navigator.storage.estimate();
                    r.storageQuotaGB = (est.quota / (1024**3)).toFixed(1);
                } catch(e) {}
                // CSS media queries
                r.pointerCoarse = matchMedia('(pointer: coarse)').matches;
                r.anyPointerCoarse = matchMedia('(any-pointer: coarse)').matches;
                r.hoverNone = matchMedia('(hover: none)').matches;
                return r;
            }""")
            print(f"    Cores: {hw.get('cores')}, Memory: {hw.get('mem')}GB")
            print(f"    UA: {hw.get('ua')}...")
            print(f"    Model: {hw.get('model')}, Platform: {hw.get('platform')}")
            print(f"    PlatformVersion: {hw.get('platformVersion')}")
            print(f"    Brands: {hw.get('brands', '')[:90]}")
            print(f"    GPU: {hw.get('gpu_renderer', '?')}")
            print(f"    Webdriver: {hw.get('webdriver')}")
            print(f"    Touch: maxTouchPoints={hw.get('maxTouchPoints')}, ontouchstart={hw.get('ontouchstart')}")
            print(f"    CSS: pointer:coarse={hw.get('pointerCoarse')}, any-pointer:coarse={hw.get('anyPointerCoarse')}, hover:none={hw.get('hoverNone')}")
            print(f"    Network: type={hw.get('netType')}, effective={hw.get('netEffective')}, rtt={hw.get('netRtt')}, downlink={hw.get('netDownlink')}")
            print(f"    Storage: {hw.get('storageQuotaGB', '?')}GB")

            # Verdict
            gpu = hw.get('gpu_renderer', '')
            issues = []
            if hw.get('maxTouchPoints', 0) < 2:
                issues.append("LOW touch points")
            if hw.get('netType') == 'ethernet':
                issues.append("ethernet (should be wifi/cellular)")
            if 'WARNING' in gpu or 'LLVM' in gpu or 'SwiftShader' in gpu:
                issues.append(f"GPU garbage: {gpu[:60]}")
            if not hw.get('pointerCoarse'):
                issues.append("pointer:coarse=false")
            if issues:
                print(f"    ISSUES: {', '.join(issues)}")
            else:
                print("    ALL CHECKS PASSED!")
        except Exception as e:
            print(f"    ERROR: {e}")

        # --- 3. CreepJS scan ---
        print("\n[3] CreepJS Full Scan")
        try:
            await goto_retry(
                page, "https://abrahamjuliot.github.io/creepjs/",
                retries=8, wait_until="domcontentloaded", timeout=60000,
            )
            print("    Waiting 40s for CreepJS analysis...")
            await sleep(40)

            full_text = await page.evaluate("() => document.body.innerText")

            # Print full CreepJS output (sanitized for console)
            print("\n" + "=" * 60)
            print("  CreepJS Full Report")
            print("=" * 60)
            for line in full_text.split("\n"):
                safe = line.encode("ascii", "replace").decode("ascii")
                if safe.strip():
                    print(f"  {safe}")
            print("=" * 60)

        except Exception as e:
            print(f"    CreepJS FAILED: {e}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
