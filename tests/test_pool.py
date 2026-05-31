"""Test DamruPool — verify unique fingerprint per session on same device."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from damru import DamruPool

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 60)
    print("  DamruPool Test — 2 sessions, same device, different fingerprints")
    print("=" * 60)

    async with DamruPool(
        max_devices=1,
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=False,
    ) as pool:
        print(f"\n  Pool ready: {pool.device_count} device(s)")

        # Session 1
        print("\n--- Session 1 ---")
        async with pool.session() as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            hw = await page.evaluate("""() => ({
                ua: navigator.userAgent,
                cores: navigator.hardwareConcurrency,
                mem: navigator.deviceMemory,
                platform: navigator.platform,
                screenW: screen.width,
                screenH: screen.height,
            })""")
            print(f"  UA: {hw['ua'][:80]}...")
            print(f"  cores={hw['cores']}, mem={hw['mem']}")
            print(f"  platform={hw['platform']}")
            print(f"  screen={hw['screenW']}x{hw['screenH']}")
            session1 = hw

        # Session 2 — should be different fingerprint
        print("\n--- Session 2 ---")
        async with pool.session() as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            hw = await page.evaluate("""() => ({
                ua: navigator.userAgent,
                cores: navigator.hardwareConcurrency,
                mem: navigator.deviceMemory,
                platform: navigator.platform,
                screenW: screen.width,
                screenH: screen.height,
            })""")
            print(f"  UA: {hw['ua'][:80]}...")
            print(f"  cores={hw['cores']}, mem={hw['mem']}")
            print(f"  platform={hw['platform']}")
            print(f"  screen={hw['screenW']}x{hw['screenH']}")
            session2 = hw

        # Compare
        print("\n--- Comparison ---")
        changed = session1["ua"] != session2["ua"]
        print(f"  UA changed: {'YES' if changed else 'NO (same device picked by random)'}")
        if session1["cores"] != session2["cores"]:
            print(f"  cores: {session1['cores']} -> {session2['cores']}")
        if session1["mem"] != session2["mem"]:
            print(f"  mem: {session1['mem']} -> {session2['mem']}")
        if session1["screenW"] != session2["screenW"]:
            print(f"  screen: {session1['screenW']}x{session1['screenH']} -> {session2['screenW']}x{session2['screenH']}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
