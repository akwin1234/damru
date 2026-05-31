"""Phase 2 v5: Test todetect.net, ipleak.net, fingerprint.com/demo with IPv6+STUN block."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 70)
    print("  Phase 2 v5: todetect + ipleak + fingerprint.com (IPv6 blocked)")
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

        # ---- Test 1: todetect.net ----
        print("\n" + "=" * 70)
        print("  [1/3] todetect.net")
        print("=" * 70)
        try:
            await page.goto("https://todetect.net/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(40)  # wait for full analysis

            await page.screenshot(path="phase2v5_todetect.png", full_page=True)
            print("  Screenshot saved: phase2v5_todetect.png")

            text = await page.evaluate("""() => {
                const body = document.body.innerText;
                return body.substring(0, 10000);
            }""")
            print(f"\n  Page text:")
            for line in text.split('\n'):
                line = line.strip()
                if line:
                    print(f"    {line}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ---- Test 2: ipleak.net ----
        print("\n" + "=" * 70)
        print("  [2/3] ipleak.net")
        print("=" * 70)
        try:
            await page.goto("https://ipleak.net/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(25)  # wait for leak detection

            await page.screenshot(path="phase2v5_ipleak.png", full_page=True)
            print("  Screenshot saved: phase2v5_ipleak.png")

            text = await page.evaluate("""() => {
                const body = document.body.innerText;
                return body.substring(0, 10000);
            }""")
            print(f"\n  Page text:")
            for line in text.split('\n'):
                line = line.strip()
                if line:
                    print(f"    {line}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ---- Test 3: fingerprint.com/demo ----
        print("\n" + "=" * 70)
        print("  [3/3] fingerprint.com/demo")
        print("=" * 70)
        try:
            await page.goto("https://fingerprint.com/demo/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(20)  # wait for analysis

            await page.screenshot(path="phase2v5_fingerprint.png", full_page=True)
            print("  Screenshot saved: phase2v5_fingerprint.png")

            text = await page.evaluate("""() => {
                const body = document.body.innerText;
                return body.substring(0, 10000);
            }""")
            print(f"\n  Page text:")
            for line in text.split('\n'):
                line = line.strip()
                if line:
                    print(f"    {line}")
        except Exception as e:
            print(f"  ERROR: {e}")

        print("\n" + "=" * 70)
        print("  Phase 2 v5 Complete")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
