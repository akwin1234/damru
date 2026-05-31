"""Debug VPN/osMismatch detection on fingerprint.com/demo.

Extracts FULL VPN methods breakdown to identify exact trigger.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru
from damru.utils import sleep

PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 70)
    print("  VPN/osMismatch Debug Test")
    print("=" * 70)

    async with AsyncDamru(
        device="random",
        proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: Check what IP fingerprint.com sees
        print("\n  [1] Checking exit IP via ipinfo.io...")
        try:
            await page.goto("https://ipinfo.io/json", wait_until="load", timeout=30000)
            await sleep(2)
            ip_text = await page.evaluate("() => document.body.innerText")
            print(f"  Exit IP info: {ip_text[:500]}")
        except Exception as e:
            print(f"  IP check failed: {e}")

        # Step 2: Check TCP fingerprint via scrapfly
        print("\n  [2] Checking TCP/TLS fingerprint...")
        try:
            await page.goto(
                "https://tls.browserleaks.com/json",
                wait_until="load",
                timeout=30000,
            )
            await sleep(2)
            tls_text = await page.evaluate("() => document.body.innerText")
            print(f"  TLS fingerprint: {tls_text[:800]}")
        except Exception as e:
            print(f"  TLS check failed: {e}")

        # Step 3: Navigate to fingerprint.com/demo
        print("\n  [3] Navigating to fingerprint.com/demo...")
        await page.goto(
            "https://fingerprint.com/demo/",
            wait_until="load",
            timeout=60000,
        )

        # Poll for results
        print("  Waiting for FP results (up to 120s)...")
        for attempt in range(24):
            await sleep(5)
            try:
                loading = await page.evaluate("""() => {
                    const text = document.body.innerText;
                    return text.includes('"loading": true') || text.includes('"loading":true');
                }""")
                if not loading:
                    print(f"  Results ready after {(attempt+1)*5}s")
                    break
                if (attempt + 1) % 4 == 0:
                    print(f"  Still loading... {(attempt+1)*5}s")
            except Exception:
                pass
        await sleep(3)

        # Step 4: Extract EVERYTHING from the FP API response
        print("\n  [4] Extracting full API response...")
        try:
            result = await page.evaluate(r"""() => {
                const output = {};

                // Method 1: Find all JSON in pre/code elements
                const codeEls = document.querySelectorAll('pre, code, [class*="json"]');
                for (const el of codeEls) {
                    const text = el.textContent.trim();
                    if (text.length > 50 && text.startsWith('{')) {
                        try {
                            const data = JSON.parse(text);
                            if (data.products) {
                                output.apiData = data;
                            }
                        } catch(e) {}
                    }
                }

                // Method 2: Intercept window.__NEXT_DATA__ or similar React state
                if (window.__NEXT_DATA__) {
                    output.nextData = JSON.stringify(window.__NEXT_DATA__).substring(0, 2000);
                }

                // Method 3: Check for any global fingerprint variables
                for (const key of ['fpResult', 'fingerprintResult', '__FINGERPRINT__', 'fp']) {
                    if (window[key]) {
                        output[key] = JSON.stringify(window[key]).substring(0, 2000);
                    }
                }

                // Method 4: Parse visible text for all signal values
                const body = document.body.innerText;
                const lines = body.split('\n').map(l => l.trim()).filter(l => l);

                // Look for all detection categories and their values
                const categories = [
                    'VPN', 'Proxy', 'Developer Tools', 'Bot', 'Tampering',
                    'Emulator', 'Root Apps', 'Virtual Machine', 'Frida',
                    'Incognito', 'MITM', 'Location Spoofing', 'Suspect Score',
                    'IP Blocklist', 'Remote Control', 'Velocity',
                    'Factory Reset', 'Jailbroken', 'Privacy Settings',
                    'Cloned App', 'High Activity'
                ];

                output.visibleSignals = {};
                for (let i = 0; i < lines.length; i++) {
                    for (const cat of categories) {
                        if (lines[i].toUpperCase().includes(cat.toUpperCase())) {
                            // Grab surrounding context (value is usually nearby)
                            const context = lines.slice(
                                Math.max(0, i-2),
                                Math.min(lines.length, i+6)
                            );
                            output.visibleSignals[cat] = context.join(' | ');
                        }
                    }
                }

                // Method 5: Find VPN sub-methods specifically
                output.vpnMethods = {};
                const vpnTerms = [
                    'osMismatch', 'os_mismatch', 'OS Mismatch',
                    'timezoneMismatch', 'timezone_mismatch', 'Timezone Mismatch',
                    'publicVPN', 'public_vpn', 'Public VPN',
                    'auxiliaryMobile', 'auxiliary_mobile',
                    'relay', 'Relay',
                    'originTimezone', 'origin_timezone',
                    'originCountry', 'origin_country',
                    'confidence'
                ];

                for (const term of vpnTerms) {
                    const regex = new RegExp(term + '[\\s:"]*([^,\\n"}{]+)', 'gi');
                    const matches = body.match(regex);
                    if (matches) {
                        output.vpnMethods[term] = matches.map(m => m.substring(0, 100));
                    }
                }

                // Method 6: Check all data attributes
                const allEls = document.querySelectorAll('[data-result], [data-value], [data-signal]');
                if (allEls.length > 0) {
                    output.dataAttrs = Array.from(allEls).map(el => ({
                        tag: el.tagName,
                        data: el.dataset,
                        text: el.textContent.substring(0, 200)
                    })).slice(0, 20);
                }

                return output;
            }""")

            print("\n" + "=" * 70)
            print("  FULL RESULTS")
            print("=" * 70)

            import json

            # Print API data if found
            if result.get("apiData"):
                products = result["apiData"].get("products", {})
                print("\n  --- API Products ---")
                for sig_name, sig_data in sorted(products.items()):
                    data = sig_data.get("data", sig_data)
                    marker = ""
                    if sig_name in ("vpn", "proxy", "developerTools"):
                        marker = "  <<< FOCUS"
                    print(f"  {sig_name}: {json.dumps(data, indent=4) if isinstance(data, dict) else data}{marker}")

            # Print visible signals
            if result.get("visibleSignals"):
                print("\n  --- Visible Signals ---")
                for cat, context in sorted(result["visibleSignals"].items()):
                    print(f"  {cat}: {context[:200]}")

            # Print VPN methods
            if result.get("vpnMethods"):
                print("\n  --- VPN Method Details ---")
                for term, matches in sorted(result["vpnMethods"].items()):
                    print(f"  {term}: {matches}")

            # Print raw data
            if result.get("nextData"):
                print(f"\n  __NEXT_DATA__ (first 500): {result['nextData'][:500]}")

        except Exception as e:
            print(f"  Extraction error: {e}")
            import traceback
            traceback.print_exc()

        # Step 5: Screenshot
        try:
            ss_path = os.path.join(os.path.dirname(__file__), "vpn_debug.png")
            await page.screenshot(path=ss_path, full_page=True)
            print(f"\n  Screenshot saved: {ss_path}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        print("\n" + "=" * 70)
        print("  Done")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
