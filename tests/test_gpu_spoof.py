#!/usr/bin/env python3
"""Test GPU spoof on redroid - verify SwiftShader binary patch works.

This script:
1. Starts a redroid container via DamruPoolSync
2. Launches Chrome with fingerprinted device
3. Checks WebGL renderer via JavaScript
4. Verifies GPU is NOT "Google SwiftShader"
5. Shows target device GPU (e.g. "Adreno (TM) 750")
"""
import sys
from pathlib import Path

# Add damru to path
damru_path = Path(__file__).parent / "damru"
sys.path.insert(0, str(damru_path))

from damru import DamruPoolSync

def test_gpu_spoof():
    """Test GPU binary spoof on redroid container."""
    print("=" * 70)
    print("GPU SPOOF TEST - Redroid SwiftShader Binary Patch")
    print("=" * 70)

    # Auto mode = redroid Docker containers
    with DamruPoolSync(mode="auto", max_devices=1, debug=True) as pool:
        print(f"\nPool initialized: {pool.device_count} device(s)")

        with pool.session() as ctx:
            page = ctx.pages[0]
            print("\n[1/5] Navigating to blank page...")
            page.goto("about:blank")

            print("[2/5] Querying WebGL GPU renderer...")

            # Get GPU info via WebGL
            gpu_info = page.evaluate("""
                () => {
                    const canvas = document.createElement('canvas');
                    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                    if (!gl) return { error: 'WebGL not supported' };

                    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                    if (!debugInfo) return { error: 'WEBGL_debug_renderer_info not available' };

                    return {
                        renderer: gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL),
                        vendor: gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL),
                        version: gl.getParameter(gl.VERSION),
                        shadingLanguage: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                    };
                }
            """)

            print("\n[3/5] GPU Information Retrieved:")
            print("-" * 70)
            if 'error' in gpu_info:
                print(f"❌ ERROR: {gpu_info['error']}")
                return False

            renderer = gpu_info.get('renderer', 'Unknown')
            vendor = gpu_info.get('vendor', 'Unknown')
            version = gpu_info.get('version', 'Unknown')
            shading = gpu_info.get('shadingLanguage', 'Unknown')

            print(f"  Renderer:         {renderer}")
            print(f"  Vendor:           {vendor}")
            print(f"  GL Version:       {version}")
            print(f"  Shading Language: {shading}")
            print("-" * 70)

            print("\n[4/5] Analyzing Results...")

            # Check for SwiftShader leak
            is_swiftshader = 'swiftshader' in renderer.lower() or 'swiftshader' in vendor.lower()
            is_google = 'google' in vendor.lower()

            if is_swiftshader:
                print("❌ FAIL: SwiftShader detected — binary patch DID NOT work")
                print(f"   Expected: Target device GPU (e.g. Adreno, Mali)")
                print(f"   Got:      {renderer}")
                return False

            if is_google and 'google inc.' in vendor.lower():
                print("❌ FAIL: Google Inc. vendor detected — binary patch incomplete")
                print(f"   Expected: Device vendor (e.g. Qualcomm, SAMSUNG)")
                print(f"   Got:      {vendor}")
                return False

            print("✅ PASS: GPU binary spoof working!")
            print(f"   ✓ Renderer is NOT SwiftShader")
            print(f"   ✓ Vendor is NOT Google Inc.")
            print(f"   ✓ Target GPU: {renderer}")
            print(f"   ✓ Target Vendor: {vendor}")

            print("\n[5/5] Testing on BrowserScan (optional - press Ctrl+C to skip)...")
            try:
                print("   Opening BrowserScan WebGL test...")
                page.goto("https://browserleaks.com/webgl", timeout=30000)
                page.wait_for_timeout(3000)

                # Take screenshot for visual verification
                screenshot_path = Path(__file__).parent / "gpu_test_screenshot.png"
                page.screenshot(path=str(screenshot_path))
                print(f"   ✓ Screenshot saved: {screenshot_path}")
                print("   ✓ Check screenshot to verify GPU renderer visually")

            except KeyboardInterrupt:
                print("   Skipped BrowserScan test (Ctrl+C)")
            except Exception as e:
                print(f"   Warning: BrowserScan test failed: {e}")

            return True

def main():
    print("\nStarting GPU spoof test...")
    print("This will:")
    print("  1. Start a redroid container (or reuse existing)")
    print("  2. Apply binary patch to SwiftShader .so")
    print("  3. Launch Chrome with target device fingerprint")
    print("  4. Query WebGL GPU renderer")
    print("  5. Verify it's NOT SwiftShader\n")

    try:
        success = test_gpu_spoof()

        print("\n" + "=" * 70)
        if success:
            print("✅ GPU SPOOF TEST PASSED")
            print("=" * 70)
            print("\nBinary patch working correctly!")
            print("GPU renderer successfully spoofed on redroid.")
            print("\nNext: Test with your bot to verify in production.")
            return 0
        else:
            print("❌ GPU SPOOF TEST FAILED")
            print("=" * 70)
            print("\nBinary patch did not work as expected.")
            print("Check logs above for details.")
            return 1

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ TEST ERROR")
        print("=" * 70)
        print(f"\nException: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
