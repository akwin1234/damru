"""Test Chrome identity on HTTPS page where Client Hints work."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=10000)

    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    # Navigate to a real HTTPS page for secure context
    print("Navigating to httpbin.org for Client Hints test...")
    await page.goto("https://httpbin.org/anything", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    # Extract identity
    identity = await page.evaluate("""() => {
        const result = {
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory || 'N/A',
            maxTouchPoints: navigator.maxTouchPoints,
            hasUAData: !!navigator.userAgentData,
        };
        if (navigator.userAgentData) {
            result.uaDataMobile = navigator.userAgentData.mobile;
            result.uaDataPlatform = navigator.userAgentData.platform;
            result.uaDataBrands = navigator.userAgentData.brands.map(b => b.brand + ' v' + b.version);
        }
        return result;
    }""")

    print("\n=== Chrome Identity ===")
    for k, v in identity.items():
        print(f"  {k}: {v}")

    # Client Hints high entropy
    if identity["hasUAData"]:
        ua_data = await page.evaluate("""async () => {
            try {
                const high = await navigator.userAgentData.getHighEntropyValues([
                    'model', 'platform', 'platformVersion', 'fullVersionList',
                    'architecture', 'mobile', 'bitness'
                ]);
                return {
                    model: high.model,
                    platform: high.platform,
                    platformVersion: high.platformVersion,
                    architecture: high.architecture,
                    bitness: high.bitness,
                    mobile: high.mobile,
                    fullVersionList: high.fullVersionList?.map(b => b.brand + ' ' + b.version) || [],
                };
            } catch(e) {
                return { error: e.message };
            }
        }""")
        print("\n=== Client Hints (High Entropy) ===")
        for k, v in ua_data.items():
            print(f"  {k}: {v}")

        # Check the HTTP headers httpbin echoed back
        http_data = await page.evaluate("""() => {
            try {
                const pre = document.querySelector('pre');
                if (pre) return JSON.parse(pre.textContent);
            } catch(e) {}
            return null;
        }""")
        if http_data and http_data.get("headers"):
            headers = http_data["headers"]
            print("\n=== HTTP Headers (Sec-CH-UA-*) ===")
            for k, v in headers.items():
                if k.lower().startswith("sec-ch-ua") or k.lower() == "user-agent":
                    print(f"  {k}: {v}")
    else:
        print("\n  [WARN] navigator.userAgentData still NOT available on HTTPS!")

    # System props verification
    print("\n=== System Props (from ADB) ===")
    import subprocess
    for prop in ["ro.product.model", "ro.product.brand", "ro.product.manufacturer"]:
        r = subprocess.run(["adb", "-s", "emulator-5556", "shell", f"getprop {prop}"],
                          capture_output=True, text=True)
        print(f"  {prop}: {r.stdout.strip()}")

    # Verdict
    print("\n=== VERDICT ===")
    if identity["hasUAData"]:
        model = ua_data.get("model", "")
        if "Pixel 8 Pro" in model:
            print("  [PASS] resetprop → Chrome Client Hints model = Pixel 8 Pro")
        elif model:
            print(f"  [PARTIAL] Client Hints model = '{model}' (not Pixel 8 Pro)")
        else:
            print("  [INFO] Client Hints model is empty (Chrome reduced UA)")
    else:
        print("  [INFO] Client Hints not available via JS — check HTTP headers on BrowserScan")

    await browser.close()
    await pw.stop()

asyncio.run(main())
