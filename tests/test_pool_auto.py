"""Test DamruPool auto mode - redroid container with unique fingerprints."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from damru import DamruPool

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"


async def get_fingerprint(ctx):
    """Navigate to data URL and read fingerprint via JS."""
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    # Navigate to a data URL so init_script runs (about:blank may not trigger it)
    await page.goto("data:text/html,<h1>test</h1>", wait_until="domcontentloaded")
    hw = await page.evaluate("""() => ({
        ua: navigator.userAgent,
        cores: navigator.hardwareConcurrency,
        mem: navigator.deviceMemory,
        platform: navigator.platform,
        screenW: screen.width,
        screenH: screen.height,
    })""")
    return hw


async def main():
    print("=" * 60)
    print("  DamruPool Auto Mode Test - redroid container")
    print("=" * 60)

    async with DamruPool(
        mode="auto",
        max_devices=1,
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as pool:
        print(f"\n  Pool ready: {pool.device_count} device(s)")

        fingerprints = []

        # Session 1
        print("\n--- Session 1 ---")
        async with pool.session() as ctx:
            hw = await get_fingerprint(ctx)
            fingerprints.append(hw)
            print(f"  UA: {hw['ua'][:80]}...")
            print(f"  cores={hw['cores']}, mem={hw['mem']}")
            print(f"  platform={hw['platform']}")
            print(f"  screen={hw['screenW']}x{hw['screenH']}")

        # Session 2 - should get a different random device
        print("\n--- Session 2 ---")
        async with pool.session() as ctx:
            hw = await get_fingerprint(ctx)
            fingerprints.append(hw)
            print(f"  UA: {hw['ua'][:80]}...")
            print(f"  cores={hw['cores']}, mem={hw['mem']}")
            print(f"  platform={hw['platform']}")
            print(f"  screen={hw['screenW']}x{hw['screenH']}")

        # Compare
        print("\n--- Fingerprint Comparison ---")
        if fingerprints[0]['ua'] != fingerprints[1]['ua']:
            print("  PASS: User-Agent is DIFFERENT between sessions")
        else:
            print("  WARN: User-Agent is the SAME (random may pick same device)")

        if fingerprints[0]['screenW'] != fingerprints[1]['screenW']:
            print("  PASS: Screen resolution is DIFFERENT")

        print(f"  Session 1: {fingerprints[0]['ua'][:60]}")
        print(f"  Session 2: {fingerprints[1]['ua'][:60]}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
