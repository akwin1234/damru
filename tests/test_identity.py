"""Quick test: verify Chrome reports spoofed device identity via CDP."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=10000)

    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    # Navigate to a real page (Client Hints may not work on about:blank)
    await page.goto("data:text/html,<h1>Identity Test</h1>", timeout=10000)

    # Extract identity from Chrome's JS APIs
    identity = await page.evaluate("""() => {
        return {
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory || 'N/A',
            maxTouchPoints: navigator.maxTouchPoints,
            screenWidth: screen.width,
            screenHeight: screen.height,
            devicePixelRatio: window.devicePixelRatio,
            hasUAData: !!navigator.userAgentData,
            uaDataMobile: navigator.userAgentData  navigator.userAgentData.mobile : 'N/A',
            uaDataPlatform: navigator.userAgentData  navigator.userAgentData.platform : 'N/A',
        };
    }""")

    print("=== Chrome Identity (via CDP) ===")
    for k, v in identity.items():
        print(f"  {k}: {v}")

    # Check Client Hints high entropy values
    if identity["hasUAData"]:
        ua_data = await page.evaluate("""async () => {
            try {
                const d = navigator.userAgentData;
                const high = await d.getHighEntropyValues([
                    'model', 'platform', 'platformVersion', 'fullVersionList',
                    'architecture', 'mobile', 'bitness', 'wow64'
                ]);
                return {
                    brands: d.brands.map(b => b.brand + ' v' + b.version),
                    mobile: high.mobile,
                    platform: high.platform,
                    platformVersion: high.platformVersion,
                    model: high.model,
                    architecture: high.architecture,
                    bitness: high.bitness,
                    fullVersionList: high.fullVersionList  high.fullVersionList.map(b => b.brand + ' ' + b.version) : [],
                };
            } catch(e) {
                return { error: e.message };
            }
        }""")
        print("\n=== Client Hints (High Entropy) ===")
        for k, v in ua_data.items():
            print(f"  {k}: {v}")
    else:
        print("\n=== Client Hints: NOT AVAILABLE ===")

    # Also check via BrowserScan-like detection page
    result = await page.evaluate("""() => {
        // What BrowserScan checks
        return {
            ua_model: navigator.userAgent.match(/; ([^)]+)\\)/).[1] || 'reduced',
            ua_android: navigator.userAgent.match(/Android (\\d+)/).[1] || '',
        };
    }""")
    print("\n=== UA Parsing ===")
    print(f"  UA model field: {result['ua_model']}")
    print(f"  UA Android ver: {result['ua_android']}")

    # Verdict
    print("\n=== VERDICT ===")
    ua = identity["userAgent"]
    if "K)" in ua:
        print("  Chrome uses REDUCED UA (model='K') — identity is in Client Hints only")
    if identity["hasUAData"]:
        model = ua_data.get("model", "")
        if "Pixel" in model:
            print(f"  [PASS] Client Hints model: {model} (SPOOFED!)")
        elif model:
            print(f"  [INFO] Client Hints model: {model}")
        else:
            print("  [INFO] Client Hints model is empty")
    else:
        print("  [WARN] No Client Hints — can't verify model spoofing via JS")
        print("  [INFO] BrowserScan uses HTTP headers (Sec-CH-UA-Model) which Chrome builds from system props")

    await browser.close()
    await pw.stop()

if __name__ == "__main__":
    asyncio.run(main())
