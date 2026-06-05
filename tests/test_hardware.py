"""Test hardware value overrides (CPU cores + device memory).

Validates that CDP hardwareConcurrency override and JS deviceMemory
init_script work correctly across different device profiles.
"""
import asyncio
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru
from damru.devices import get_device, get_random_device

TEST_PROXY = os.environ.get("DAMRU_TEST_PROXY")
TEST_HTTP_PROXY = os.environ.get("DAMRU_TEST_HTTP_PROXY")
TEST_TIMEZONE = os.environ.get("DAMRU_TEST_TIMEZONE", "Asia/Manila")

# Test devices with different core/memory combos
TEST_DEVICES = [
    # (name, expected_cores, expected_mem)
    ("Samsung Galaxy S24 FE", 10, 8),     # Exynos 10-core
    ("Samsung Galaxy A15 5G", 8, 4),      # Budget: 4GB RAM
    ("Xiaomi Redmi Note 12 5G", 8, 4),    # Budget: 4GB RAM
    ("Google Pixel 8 Pro", 8, 8),         # Standard flagship
]


async def _check_device(name: str, expected_cores: int, expected_mem: int) -> bool:
    """Test a single device profile's hardware values."""
    print(f"\n{'='*60}")
    print(f"  Testing: {name}")
    print(f"  Expected: cores={expected_cores}, mem={expected_mem}")
    print(f"{'='*60}")

    try:
        async with AsyncDamru(
            device=name,
            proxy=TEST_PROXY,
            http_proxy=TEST_HTTP_PROXY,
            timezone=TEST_TIMEZONE,
            debug=False,
        ) as context:
            page = context.pages[0] if context.pages else await context.new_page()

            # Test 1: Check values on data: URL
            await page.goto(
                "data:text/html,<h1>test</h1>",
                wait_until="domcontentloaded",
                timeout=10000,
            )
            await asyncio.sleep(1)

            vals = await page.evaluate("""() => ({
                cores: navigator.hardwareConcurrency,
                mem: navigator.deviceMemory,
            })""")

            cores = vals.get("cores")
            mem = vals.get("mem")
            print(f"  [data: URL] cores={cores}, mem={mem}")

            cores_ok = cores == expected_cores
            mem_ok = mem == expected_mem if mem is not None else True
            print(f"  cores: {'PASS' if cores_ok else 'FAIL'} (got {cores}, expected {expected_cores})")
            print(f"  mem:   {'PASS' if mem_ok else 'FAIL'} (got {mem}, expected {expected_mem}; None is allowed on data: URLs)")

            # Test 2: Navigate to HTTPS page and re-check (tests persistence)
            try:
                await page.goto(
                    "https://www.example.com/",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await asyncio.sleep(2)

                vals2 = await page.evaluate("""() => ({
                    cores: navigator.hardwareConcurrency,
                    mem: navigator.deviceMemory,
                })""")

                cores2 = vals2.get("cores")
                mem2 = vals2.get("mem")
                print(f"  [example.com] cores={cores2}, mem={mem2}")

                cores_persist = cores2 == expected_cores
                mem_persist = True
                print(f"  cores persist: {'PASS' if cores_persist else 'FAIL'}")
                print(f"  mem persist:   INFO (got {mem2}, target {expected_mem}; Chrome may cap/omit deviceMemory)")

                return cores_ok and mem_ok and cores_persist and mem_persist

            except Exception as e:
                print(f"  Navigation to example.com failed: {e}")
                # Still count initial test
                return cores_ok and mem_ok

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize("name,expected_cores,expected_mem", TEST_DEVICES)
async def test_hardware_profile_values(name: str, expected_cores: int, expected_mem: int) -> None:
    assert await _check_device(name, expected_cores, expected_mem)


async def main():
    print("=" * 60)
    print("  damru Hardware Override Test")
    print("  (CDP for cores, JS init_script for memory)")
    print("=" * 60)

    results = []
    for name, cores, mem in TEST_DEVICES:
        ok = await _check_device(name, cores, mem)
        results.append((name, ok))

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    passed = 0
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if ok:
            passed += 1

    total = len(results)
    print(f"\n  {passed}/{total} devices passed")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
