#!/usr/bin/env python3
"""Test GPU spoof on redroid and verify SwiftShader is not exposed."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from damru import DamruPoolSync


def _check_gpu_spoof() -> bool:
    """Run the live GPU probe. Intended for --run-damru-probes or direct use."""
    print("=" * 70)
    print("GPU SPOOF TEST - Redroid SwiftShader Binary Patch")
    print("=" * 70)

    with DamruPoolSync(mode="auto", max_devices=1, debug=True) as pool:
        print(f"\nPool initialized: {pool.device_count} device(s)")

        with pool.session() as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            print("\n[1/5] Navigating to blank page...")
            page.goto("about:blank")

            print("[2/5] Querying WebGL GPU renderer...")
            gpu_info = page.evaluate(
                """
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
                """
            )

            print("\n[3/5] GPU Information Retrieved:")
            print("-" * 70)
            if "error" in gpu_info:
                print(f"ERROR: {gpu_info['error']}")
                return False

            renderer = gpu_info.get("renderer", "Unknown")
            vendor = gpu_info.get("vendor", "Unknown")
            version = gpu_info.get("version", "Unknown")
            shading = gpu_info.get("shadingLanguage", "Unknown")

            print(f"  Renderer:         {renderer}")
            print(f"  Vendor:           {vendor}")
            print(f"  GL Version:       {version}")
            print(f"  Shading Language: {shading}")
            print("-" * 70)

            print("\n[4/5] Analyzing Results...")
            if "swiftshader" in renderer.lower() or "swiftshader" in vendor.lower():
                print("FAIL: SwiftShader detected - binary patch did not work")
                print("   Expected: target device GPU, e.g. Adreno or Mali")
                print(f"   Got:      {renderer}")
                return False

            print("PASS: GPU binary spoof working")
            print("   Renderer is not SwiftShader")
            print(f"   Vendor string: {vendor}")
            print(f"   Target GPU: {renderer}")

            print("\n[5/5] Testing on BrowserLeaks WebGL...")
            try:
                page.goto("https://browserleaks.com/webgl", timeout=30000)
                page.wait_for_timeout(3000)
                screenshot_path = Path(__file__).parent / "gpu_test_screenshot.png"
                page.screenshot(path=str(screenshot_path))
                print(f"   Screenshot saved: {screenshot_path}")
            except Exception as exc:
                print(f"   Warning: BrowserLeaks test failed: {exc}")

            return True


def test_gpu_spoof() -> None:
    assert _check_gpu_spoof()


def main() -> int:
    print("\nStarting GPU spoof test...")
    print("This will start/reuse a Redroid worker, apply GPU spoofing, and query WebGL.\n")
    try:
        success = _check_gpu_spoof()
    except Exception as exc:
        print("\n" + "=" * 70)
        print("TEST ERROR")
        print("=" * 70)
        print(f"\nException: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    print("\n" + "=" * 70)
    print("GPU SPOOF TEST PASSED" if success else "GPU SPOOF TEST FAILED")
    print("=" * 70)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
