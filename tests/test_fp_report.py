"""Extract full fingerprint.com/demo report."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"


async def main():
    print("=" * 70)
    print("  fingerprint.com/demo - full report extraction")
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
        print("  Page loaded (domcontentloaded)")

        # Wait for API to complete - needs ~50s through rotating proxy
        for attempt in range(8):
            await asyncio.sleep(10)
            has_results = await page.evaluate("""() => {
                const body = document.body.innerText || '';
                return !body.includes('Loading visitor') && body.includes('Visitor ID');
            }""")
            if has_results:
                print(f"  Results loaded after {(attempt+1)*10}s")
                break
            print(f"  Still loading... ({(attempt+1)*10}s)")

            # Try clicking retry button if visible
            try:
                btn = page.get_by_text("Analyze my browser again")
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    print("  Clicked 'Analyze my browser again'")
            except Exception:
                pass
        else:
            print("  WARNING: Results may not have fully loaded")

        # Extract EVERYTHING from the page
        full_report = await page.evaluate("""() => {
            // Get all text content structured
            const result = {};

            // Method 1: Full body text
            result.bodyText = document.body.innerText;

            // Method 2: Try to find specific data elements
            const allElements = document.querySelectorAll('*');
            const signals = [];
            for (const el of allElements) {
                const text = el.textContent.trim();
                if (text && text.length < 500 && text.length > 2) {
                    const tag = el.tagName;
                    const cls = el.className;
                    if (tag === 'TD' || tag === 'TH' || tag === 'DT' || tag === 'DD' ||
                        (cls && (cls.includes('signal') || cls.includes('metric') ||
                         cls.includes('value') || cls.includes('label') ||
                         cls.includes('result') || cls.includes('detail')))) {
                        signals.push({tag, cls: String(cls).substring(0,80), text: text.substring(0,200)});
                    }
                }
            }
            result.signals = signals.slice(0, 100);

            // Method 3: Check for JSON data in scripts or data attributes
            const jsonScripts = document.querySelectorAll('script[type="application/json"]');
            result.jsonData = [];
            for (const s of jsonScripts) {
                try {
                    result.jsonData.push(JSON.parse(s.textContent));
                } catch(e) {}
            }

            return result;
        }""")

        print("\n" + "=" * 70)
        print("  FULL PAGE TEXT")
        print("=" * 70)
        body = full_report.get("bodyText", "")
        for line in body.split("\n"):
            line = line.strip()
            if line:
                print(f"  {line}")

        if full_report.get("signals"):
            print("\n" + "=" * 70)
            print("  STRUCTURED SIGNALS")
            print("=" * 70)
            for s in full_report["signals"][:50]:
                print(f"  [{s['tag']}] {s['text']}")

        if full_report.get("jsonData"):
            print("\n" + "=" * 70)
            print("  JSON DATA")
            print("=" * 70)
            import json
            for j in full_report["jsonData"]:
                print(json.dumps(j, indent=2)[:5000])

        # Also try to get the API response directly from network
        print("\n" + "=" * 70)
        print("  TRYING FINGERPRINT API RESPONSE")
        print("=" * 70)
        api_data = await page.evaluate("""() => {
            // Check if fingerprint data is stored in window/global
            const keys = ['__NEXT_DATA__', '__fingerprint__', 'fpData', 'visitorData'];
            const found = {};
            for (const k of keys) {
                if (window[k]) found[k] = window[k];
            }

            // Check Next.js data
            const nextData = document.querySelector('#__NEXT_DATA__');
            if (nextData) {
                try { found['nextData'] = JSON.parse(nextData.textContent); } catch(e) {}
            }

            return found;
        }""")

        if api_data:
            import json
            for key, val in api_data.items():
                print(f"\n  --- {key} ---")
                text = json.dumps(val, indent=2)
                # Print first 5000 chars
                print(text[:5000])
                if len(text) > 5000:
                    print(f"  ... ({len(text)} chars total, truncated)")

        print("\n" + "=" * 70)
        print("  Done")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
