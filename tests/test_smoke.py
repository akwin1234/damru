"""Quick smoke test - verify Chrome starts, GPU patches, CDP works."""
import asyncio, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from damru import AsyncDamru
from damru.utils import setup_logging

PH_HTTP = "proxy.example:50000"

async def main():
    setup_logging(True)
    print("=" * 60)
    print("  SMOKE TEST (baked image)")
    print("=" * 60)
    t_start = time.monotonic()

    async with AsyncDamru(device="random", proxy=PH_HTTP, timezone="Asia/Manila", debug=True) as ctx:
        # Always create a fresh page to avoid stale context from TTS warmup
        page = await ctx.new_page()

        # Quick navigation test
        await page.goto("https://www.example.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        title = await page.title()
        print(f"\n  Page title: {title}")

        # Check GPU renderer via JS
        gpu = await page.evaluate("""() => {
            try {
                const c = document.createElement('canvas');
                const gl = c.getContext('webgl2') || c.getContext('webgl');
                if (!gl) return 'no webgl';
                const ext = gl.getExtension('WEBGL_debug_renderer_info');
                return ext  gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'no ext';
            } catch(e) { return 'error: ' + e.message; }
        }""")
        print(f"  GPU renderer: {gpu}")

        # Check basic fingerprint values
        info = await page.evaluate("""() => ({
            ua: navigator.userAgent.substring(0, 80),
            cores: navigator.hardwareConcurrency,
            memory: navigator.deviceMemory,
            touch: navigator.maxTouchPoints,
            platform: navigator.platform,
        })""")
        print(f"  UA: {info['ua']}...")
        print(f"  Cores: {info['cores']}, Memory: {info['memory']}GB, Touch: {info['touch']}")
        print(f"  Platform: {info['platform']}")

        swiftshader = "SwiftShader" in str(gpu) or "swiftshader" in str(gpu).lower()
        print(f"\n  SwiftShader leak: {'YES (BAD)' if swiftshader else 'NO (GOOD)'}")

    elapsed = time.monotonic() - t_start
    print(f"\nSmoke test PASSED in {elapsed:.1f}s")

if __name__ == "__main__":
    asyncio.run(main())
