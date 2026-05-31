"""Test fingerprint.com/demo developerTools detection fix."""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 70)
    print("  fingerprint.com/demo — developerTools fix test")
    print("=" * 70)

    async with AsyncDamru(
        device="Samsung Galaxy S23 Ultra",
        serial="localhost:5600",
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        print("\n  Navigating to fingerprint.com/demo...")
        await page.goto(
            "https://fingerprint.com/demo/",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        print("  Page loaded")

        # Wait for API to complete (~50s through rotating proxy)
        for attempt in range(8):
            await asyncio.sleep(10)
            has_results = await page.evaluate("""() => {
                const body = document.body.innerText || '';
                return body.includes('developerTools');
            }""")
            if has_results:
                print(f"  Results loaded after {(attempt+1)*10}s")
                break
            print(f"  Still loading... ({(attempt+1)*10}s)")
        else:
            print("  WARNING: Results may not have fully loaded")

        # Extract the SERVER API RESPONSE section which has all signals
        report = await page.evaluate("""() => {
            const body = document.body.innerText || '';
            // Find the SERVER API RESPONSE JSON block
            const serverIdx = body.indexOf('"products"');
            if (serverIdx === -1) return {error: 'No products found in page text'};

            // Find the JSON block
            const jsonStart = body.lastIndexOf('{', serverIdx);
            if (jsonStart === -1) return {error: 'No JSON start found'};

            // Try to parse the JSON
            let depth = 0;
            let jsonEnd = -1;
            for (let i = jsonStart; i < body.length; i++) {
                if (body[i] === '{') depth++;
                else if (body[i] === '}') {
                    depth--;
                    if (depth === 0) { jsonEnd = i + 1; break; }
                }
            }
            if (jsonEnd === -1) return {error: 'No JSON end found'};

            const jsonStr = body.substring(jsonStart, jsonEnd);
            try {
                return JSON.parse(jsonStr);
            } catch(e) {
                return {error: 'JSON parse failed: ' + e.message, snippet: jsonStr.substring(0, 500)};
            }
        }""")

        print("\n" + "=" * 70)
        print("  KEY RESULTS")
        print("=" * 70)

        if "error" in report:
            print(f"  ERROR: {report['error']}")
            if "snippet" in report:
                print(f"  Snippet: {report['snippet']}")
            # Fallback: just get full page text
            full = await page.evaluate("() => document.body.innerText.substring(0, 15000)")
            print("\n  Full page text (first 5000 chars):")
            for line in full[:5000].split('\n'):
                line = line.strip()
                if line:
                    print(f"    {line}")
        else:
            products = report.get("products", report)

            # Key signals
            signals = {
                "developerTools": products.get("developerTools", {}).get("data", {}),
                "tampering": products.get("tampering", {}).get("data", {}),
                "botd": products.get("botd", {}).get("data", {}).get("bot", {}),
                "emulator": products.get("emulator", {}).get("data", {}),
                "rootApps": products.get("rootApps", {}).get("data", {}),
                "virtualMachine": products.get("virtualMachine", {}).get("data", {}),
                "frida": products.get("frida", {}).get("data", {}),
                "proxy": products.get("proxy", {}).get("data", {}),
                "vpn": products.get("vpn", {}).get("data", {}),
                "suspectScore": products.get("suspectScore", {}).get("data", {}),
                "incognito": products.get("incognito", {}).get("data", {}),
                "mitmAttack": products.get("mitmAttack", {}).get("data", {}),
                "locationSpoofing": products.get("locationSpoofing", {}).get("data", {}),
            }

            for name, data in signals.items():
                result = data.get("result", data)
                marker = "  <<< TARGET" if name == "developerTools" else ""
                if name == "tampering":
                    print(f"  {name}: result={data.get('result')}, anomalyScore={data.get('anomalyScore')}, antiDetectBrowser={data.get('antiDetectBrowser')}{marker}")
                elif name == "suspectScore":
                    print(f"  {name}: {result}{marker}")
                else:
                    print(f"  {name}: {result}{marker}")

        print("\n" + "=" * 70)
        print("  Done")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
