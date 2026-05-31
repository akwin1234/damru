"""Phase 2: Test fingerprint.com/demo and todetect.net with PH proxy."""
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
    print("  Phase 2: Fingerprint Site Testing")
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

        # ---- Test 1: fingerprint.com/demo ----
        print("\n" + "=" * 70)
        print("  [1/2] fingerprint.com/demo")
        print("=" * 70)
        try:
            await page.goto("https://fingerprint.com/demo/", timeout=30000)
            await asyncio.sleep(15)  # wait for fingerprint analysis

            # Take screenshot
            await page.screenshot(path="phase2_fingerprint_demo.png", full_page=True)
            print("  Screenshot saved: phase2_fingerprint_demo.png")

            # Try to extract visible text results
            text = await page.evaluate("""() => {
                // Get all text content from the page
                const body = document.body.innerText;
                return body.substring(0, 5000);
            }""")
            print(f"\n  Page text (first 5000 chars):")
            for line in text.split('\n'):
                line = line.strip()
                if line:
                    print(f"    {line}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ---- Test 2: todetect.net ----
        print("\n" + "=" * 70)
        print("  [2/2] todetect.net")
        print("=" * 70)
        try:
            await page.goto("https://todetect.net/", timeout=30000)
            await asyncio.sleep(20)  # wait for detection analysis

            # Take screenshot
            await page.screenshot(path="phase2_todetect.png", full_page=True)
            print("  Screenshot saved: phase2_todetect.png")

            # Extract results
            text = await page.evaluate("""() => {
                const body = document.body.innerText;
                return body.substring(0, 5000);
            }""")
            print(f"\n  Page text (first 5000 chars):")
            for line in text.split('\n'):
                line = line.strip()
                if line:
                    print(f"    {line}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print("\n" + "=" * 70)
        print("  Phase 2 Complete - Review screenshots for details")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
