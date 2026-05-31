"""Test fingerprint.com/demo with crPage.js Runtime enable/disable patch."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru
from damru.utils import sleep

PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 70)
    print("  fingerprint.com/demo - Runtime patch test")
    print(f"  PLAYWRIGHT_STEALTH_RUNTIME = {os.environ.get('PLAYWRIGHT_STEALTH_RUNTIME', 'NOT SET')}")
    print("=" * 70)

    async with AsyncDamru(
        device="random",
        proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to fingerprint.com/demo
        print("\n  [1] Navigating to fingerprint.com/demo...")
        await page.goto(
            "https://fingerprint.com/demo/",
            wait_until="load",
            timeout=60000,
        )
        print(f"  Page loaded: {page.url}")

        # Wait for FP results - poll every 5s for up to 90s
        print("  [2] Waiting for fingerprint results (up to 90s)...")
        for attempt in range(18):
            await sleep(5)
            try:
                loading = await page.evaluate("""() => {
                    const text = document.body.innerText;
                    return text.includes('"loading": true') || text.includes('"loading":true');
                }""")
                if not loading:
                    print(f"  Results ready after {(attempt+1)*5}s!")
                    break
                print(f"  Still loading... {(attempt+1)*5}s")
            except Exception:
                print(f"  Context issue at {(attempt+1)*5}s, continuing...")

        # Get full page text for analysis
        print("  [3] Extracting results...")
        await sleep(2)

        ss_dir = os.path.dirname(__file__)
        try:
            await page.screenshot(path=os.path.join(ss_dir, "fp_result.png"), full_page=True)
            print(f"  Full page screenshot saved")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        # Extract the DEVELOPER TOOLS value from the visible page
        try:
            result = await page.evaluate(r"""() => {
                const body = document.body.innerText;
                const lines = body.split('\n').map(l => l.trim()).filter(l => l);
                const result = {};

                // Find DEVELOPER TOOLS section and its value
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i].toUpperCase().includes('DEVELOPER TOOLS')) {
                        // Value should be in nearby lines
                        for (let j = i-2; j < i+5 && j < lines.length; j++) {
                            const v = lines[j].trim().toLowerCase();
                            if (v === 'true' || v === 'false' || v === 'not detected' || v === 'detected') {
                                result.developerTools = lines[j].trim();
                            }
                        }
                        result.context = lines.slice(Math.max(0,i-2), Math.min(lines.length,i+5)).join(' | ');
                    }
                    if (lines[i].toUpperCase().includes('SUSPECT SCORE')) {
                        for (let j = i-2; j < i+5 && j < lines.length; j++) {
                            const num = parseInt(lines[j]);
                            if (!isNaN(num) && num >= 0 && num <= 100) {
                                result.suspectScore = num;
                            }
                        }
                    }
                }

                // Also grab any JSON data from pre/code elements
                const pres = document.querySelectorAll('pre, code');
                for (const el of pres) {
                    const text = el.textContent.trim();
                    if (text.length > 20 && text.startsWith('{')) {
                        try {
                            const data = JSON.parse(text);
                            if (data.products || data.developerTools) {
                                result.apiData = data;
                            }
                        } catch(e) {}
                    }
                }

                // Search for signal values in the full text
                const signalPatterns = {
                    'botDetection': /bot\s*(?:detection|detected)[:\s]*([^\n]+)/i,
                    'tampering': /tampering[:\s]*([^\n]+)/i,
                    'emulator': /emulator[:\s]*([^\n]+)/i,
                    'vpn': /vpn[:\s]*([^\n]+)/i,
                    'proxy': /proxy[:\s]*([^\n]+)/i,
                    'incognito': /incognito[:\s]*([^\n]+)/i,
                };

                for (const [key, pattern] of Object.entries(signalPatterns)) {
                    const m = body.match(pattern);
                    if (m) result[key] = m[1].trim().substring(0, 100);
                }

                // Check if still loading
                result.isLoading = body.includes('"loading": true') || body.includes('"loading":true');

                return result;
            }""")

            print("\n" + "=" * 70)
            print("  RESULTS")
            print("=" * 70)

            if result.get("isLoading"):
                print("  WARNING: FP results still loading - API may be slow/blocked")

            for key, value in result.items():
                if key == "apiData":
                    # Pretty print API data
                    import json
                    products = value.get("products", value)
                    for sig in ["developerTools", "tampering", "botd", "suspectScore",
                                "emulator", "rootApps", "virtualMachine", "frida",
                                "proxy", "vpn", "incognito"]:
                        if sig in products:
                            d = products[sig].get("data", products[sig])
                            marker = "  <<< TARGET" if sig == "developerTools" else ""
                            print(f"  API.{sig}: {d}{marker}")
                elif key == "context":
                    print(f"  devtools context: {value}")
                elif key == "developerTools":
                    print(f"  >>> DEVELOPER TOOLS: {value} <<<")
                elif key == "suspectScore":
                    print(f"  SUSPECT SCORE: {value}")
                elif key != "isLoading":
                    print(f"  {key}: {value}")

        except Exception as e:
            print(f"  Extraction error: {e}")

        print("\n" + "=" * 70)
        print("  Done")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
