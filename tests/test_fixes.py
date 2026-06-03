"""Quick test for GPU driverInfo fix and WebGL extension count."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"

FINGERPRINT_SCRIPT = """async () => {
    const r = {};

    // GPU
    try {
        const c = document.createElement('canvas');
        const gl = c.getContext('webgl');
        if (gl) {
            const dbg = gl.getExtension('WEBGL_debug_renderer_info');
            r.gpuVendor = dbg  gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : 'no dbg ext';
            r.gpuRenderer = dbg  gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'no dbg ext';
            r.webglExts = gl.getSupportedExtensions().length;
            r.webglExtList = gl.getSupportedExtensions().join(', ');
        }
    } catch(e) { r.gpuError = e.message; }

    // WebGL2 extensions
    try {
        const c2 = document.createElement('canvas');
        const gl2 = c2.getContext('webgl2');
        if (gl2) {
            r.webgl2Exts = gl2.getSupportedExtensions().length;
        }
    } catch(e) {}

    // Speech (voices load asynchronously - wait for onvoiceschanged)
    try {
        r.speechAvailable = 'speechSynthesis' in window;
        if (window.speechSynthesis) {
            let v = speechSynthesis.getVoices();
            if (v.length === 0) {
                v = await new Promise(resolve => {
                    speechSynthesis.onvoiceschanged = () =>
                        resolve(speechSynthesis.getVoices());
                    setTimeout(() => resolve(speechSynthesis.getVoices()), 5000);
                });
            }
            r.speechVoices = v.length;
        } else {
            r.speechVoices = -1;
        }
    } catch(e) { r.speechError = e.message; }

    // Other hardware
    r.cores = navigator.hardwareConcurrency;
    r.mem = navigator.deviceMemory;
    r.touch = navigator.maxTouchPoints;

    return r;
}"""


async def main():
    print("=" * 70)
    print("  Fix Verification Test")
    print("  Checking: GPU renderer, WebGL extensions, speech")
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

        # Navigate to HTTPS (needed for deviceMemory, storage, etc.)
        print("\n  Navigating to example.com...")
        await page.goto(
            "https://www.example.com/",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(3)

        results = await page.evaluate(FINGERPRINT_SCRIPT)

        print("\n" + "=" * 70)
        print("  RESULTS")
        print("=" * 70)

        renderer = results.get("gpuRenderer", "N/A")
        vendor = results.get("gpuVendor", "N/A")
        webgl_exts = results.get("webglExts", "N/A")
        webgl2_exts = results.get("webgl2Exts", "N/A")
        speech_voices = results.get("speechVoices", "N/A")

        # GPU renderer analysis
        has_driver_info = "LLVM" in renderer or "VULK" in renderer
        has_swiftshader = "SwiftShader" in renderer
        print(f"\n  GPU Vendor:     {vendor}")
        print(f"  GPU Renderer:   {renderer}")
        print(f"  Has driverInfo: {'YES (TELL!)' if has_driver_info else 'NO (clean)'}")
        print(f"  Has SwiftShader: {'YES (TELL!)' if has_swiftshader else 'NO (clean)'}")

        # WebGL extensions
        print(f"\n  WebGL1 exts:    {webgl_exts} (real phone: 43)")
        print(f"  WebGL2 exts:    {webgl2_exts}")
        if results.get("webglExtList"):
            exts = results["webglExtList"].split(", ")
            desktop_only = [e for e in exts if "polygon_mode" in e or "translated_shader" in e]
            if desktop_only:
                print(f"  Desktop-only:   {desktop_only} (TELLS!)")
            else:
                print(f"  Desktop-only:   None found (clean)")

        # Speech
        print(f"\n  Speech avail:   {results.get('speechAvailable', 'N/A')}")
        print(f"  Speech voices:  {speech_voices}")

        # Other
        print(f"\n  Cores:          {results.get('cores', 'N/A')}")
        print(f"  Memory:         {results.get('mem', 'N/A')}")
        print(f"  Touch:          {results.get('touch', 'N/A')}")

        print("\n" + "=" * 70)
        # Summary
        checks = [
            ("GPU: no driverInfo tell", not has_driver_info),
            ("GPU: no SwiftShader", not has_swiftshader),
            ("WebGL1 exts closer to 43", isinstance(webgl_exts, int) and webgl_exts > 28),
            ("Speech available", results.get("speechAvailable", False)),
        ]
        passed = sum(1 for _, ok in checks if ok)
        for name, ok in checks:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        print(f"\n  {passed}/{len(checks)} checks passed")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
