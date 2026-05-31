"""Test fingerprint.com/demo specifically with longer wait + retry."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 70)
    print("  fingerprint.com/demo targeted test")
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
        try:
            await page.goto("https://fingerprint.com/demo/", wait_until="domcontentloaded", timeout=60000)
            print("  Page loaded (domcontentloaded)")

            # Wait for initial load
            await asyncio.sleep(10)

            # Try to wait for visitor ID to appear
            for attempt in range(6):
                text = await page.evaluate("""() => {
                    const els = document.querySelectorAll('[class*="visitor"], [class*="metric"], [data-testid]');
                    let results = [];
                    els.forEach(el => {
                        if (el.textContent && !el.textContent.includes('Loading')) {
                            results.push(el.textContent.trim().substring(0, 200));
                        }
                    });
                    // Also check for any visible result text
                    const body = document.body.innerText;
                    const hasResults = !body.includes('Loading visitor ID');
                    return {results: results.slice(0, 20), hasResults, bodySnippet: body.substring(0, 2000)};
                }""")

                if text.get('hasResults'):
                    print(f"  Results loaded after attempt {attempt + 1}!")
                    break

                print(f"  Still loading... (attempt {attempt + 1}/6)")

                # Try clicking "Analyze my browser again" if visible
                try:
                    btn = page.get_by_text("Analyze my browser again")
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        print("  Clicked 'Analyze my browser again'")
                except Exception:
                    pass

                await asyncio.sleep(10)

            # Final screenshot and text extraction
            await page.screenshot(path="phase2_fingerprint_final.png", full_page=True)
            print("  Screenshot saved: phase2_fingerprint_final.png")

            full_text = await page.evaluate("() => document.body.innerText.substring(0, 10000)")
            print(f"\n  Page text:")
            for line in full_text.split('\n'):
                line = line.strip()
                if line:
                    print(f"    {line}")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 70)
        print("  Test Complete")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
