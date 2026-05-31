"""Test hardened JS injection — verifies both values AND anti-detection stealth.

Tests:
  1. Values correct (cores + memory match target device)
  2. getter.toString() returns "[native code]" (Proxy interception)
  3. getter.name matches native ("get deviceMemory")
  4. Function.prototype.toString integrity (toString.toString() = native)
  5. Property descriptor shape matches native
  6. Survives navigation to HTTPS page
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"

DETECTION_SCRIPT = """() => {
    const results = {};
    const N = Navigator.prototype;

    // 1. Values
    results.cores = navigator.hardwareConcurrency;
    results.mem = navigator.deviceMemory;

    // 2. Getter toString — should show "[native code]"
    try {
        const dmDesc = Object.getOwnPropertyDescriptor(N, 'deviceMemory');
        const hcDesc = Object.getOwnPropertyDescriptor(N, 'hardwareConcurrency');
        if (dmDesc && dmDesc.get) {
            results.dm_toString = dmDesc.get.toString();
            results.dm_hasNative = dmDesc.get.toString().includes('[native code]');
        }
        if (hcDesc && hcDesc.get) {
            results.hc_toString = hcDesc.get.toString();
            results.hc_hasNative = hcDesc.get.toString().includes('[native code]');
        }
    } catch(e) { results.toString_error = e.message; }

    // 3. Getter .name — should be "get deviceMemory"
    try {
        const dmDesc = Object.getOwnPropertyDescriptor(N, 'deviceMemory');
        const hcDesc = Object.getOwnPropertyDescriptor(N, 'hardwareConcurrency');
        results.dm_name = dmDesc && dmDesc.get ? dmDesc.get.name : 'N/A';
        results.hc_name = hcDesc && hcDesc.get ? hcDesc.get.name : 'N/A';
    } catch(e) { results.name_error = e.message; }

    // 4. Function.prototype.toString integrity
    try {
        const tsStr = Function.prototype.toString.toString();
        results.ts_toString = tsStr;
        results.ts_hasNative = tsStr.includes('[native code]');
    } catch(e) { results.ts_error = e.message; }

    // 5. Function.prototype.toString.call(getter) — advanced check
    try {
        const dmDesc = Object.getOwnPropertyDescriptor(N, 'deviceMemory');
        if (dmDesc && dmDesc.get) {
            results.dm_fpts = Function.prototype.toString.call(dmDesc.get);
            results.dm_fpts_native = results.dm_fpts.includes('[native code]');
        }
    } catch(e) { results.fpts_error = e.message; }

    // 6. Property descriptor shape
    try {
        const dmDesc = Object.getOwnPropertyDescriptor(N, 'deviceMemory');
        if (dmDesc) {
            results.dm_configurable = dmDesc.configurable;
            results.dm_enumerable = dmDesc.enumerable;
            results.dm_hasSet = 'set' in dmDesc;
            results.dm_hasValue = 'value' in dmDesc;
        }
    } catch(e) { results.desc_error = e.message; }

    // 7. Type checks
    results.mem_type = typeof navigator.deviceMemory;
    results.cores_type = typeof navigator.hardwareConcurrency;

    // 8. Prototype chain
    results.dm_in_navigator = 'deviceMemory' in navigator;
    results.dm_own = navigator.hasOwnProperty('deviceMemory');
    results.dm_in_proto = 'deviceMemory' in N;

    // 9. Other functions' toString still work (no collateral damage)
    try {
        results.array_push_ts = Array.prototype.push.toString().includes('[native code]');
        results.math_max_ts = Math.max.toString().includes('[native code]');
    } catch(e) { results.collateral_error = e.message; }

    return results;
}"""


async def main():
    print("=" * 60)
    print("  Hardened JS Injection — Stealth Detection Test")
    print("=" * 60)

    async with AsyncDamru(
        device="Samsung Galaxy S24 FE",  # 10 cores, 8GB — good edge case
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=False,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # Test on data: URL first
        await page.goto("data:text/html,<h1>stealth test</h1>", wait_until="domcontentloaded", timeout=10000)
        await asyncio.sleep(1)

        results = await page.evaluate(DETECTION_SCRIPT)

        print(f"\n  --- data: URL ---")
        _print_results(results, expected_cores=10, expected_mem=8)

        # Test after navigation to HTTPS (persistence check)
        try:
            await page.goto("https://www.example.com/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            results2 = await page.evaluate(DETECTION_SCRIPT)
            print(f"\n  --- example.com (persistence) ---")
            _print_results(results2, expected_cores=10, expected_mem=8)
        except Exception as e:
            print(f"\n  Navigation failed: {e}")

    print("\n  Done!")


def _print_results(r: dict, expected_cores: int, expected_mem: int):
    checks = []

    # Values
    cores_ok = r.get("cores") == expected_cores
    mem_ok = r.get("mem") == expected_mem
    checks.append(("cores value", cores_ok, f"{r.get('cores')} (expected {expected_cores})"))
    checks.append(("mem value", mem_ok, f"{r.get('mem')} (expected {expected_mem})"))

    # toString returns [native code]
    dm_native = r.get("dm_hasNative", False)
    hc_native = r.get("hc_hasNative", False)
    checks.append(("dm getter.toString() native", dm_native, r.get("dm_toString", "N/A")[:60]))
    checks.append(("hc getter.toString() native", hc_native, r.get("hc_toString", "N/A")[:60]))

    # Getter .name
    dm_name_ok = r.get("dm_name") == "get deviceMemory"
    hc_name_ok = r.get("hc_name") == "get hardwareConcurrency"
    checks.append(("dm getter.name", dm_name_ok, r.get("dm_name", "N/A")))
    checks.append(("hc getter.name", hc_name_ok, r.get("hc_name", "N/A")))

    # Function.prototype.toString integrity
    ts_ok = r.get("ts_hasNative", False)
    checks.append(("toString.toString() native", ts_ok, r.get("ts_toString", "N/A")[:60]))

    # Function.prototype.toString.call(getter)
    fpts_ok = r.get("dm_fpts_native", False)
    checks.append(("FP.toString.call(getter) native", fpts_ok, r.get("dm_fpts", "N/A")[:60]))

    # Descriptor shape
    cfg_ok = r.get("dm_configurable") is True
    enum_ok = r.get("dm_enumerable") is True
    no_val = r.get("dm_hasValue") is False  # accessor, not data descriptor
    checks.append(("descriptor configurable", cfg_ok, str(r.get("dm_configurable"))))
    checks.append(("descriptor enumerable", enum_ok, str(r.get("dm_enumerable"))))
    checks.append(("descriptor no value (accessor)", no_val, f"hasValue={r.get('dm_hasValue')}"))

    # Types
    mem_type_ok = r.get("mem_type") == "number"
    cores_type_ok = r.get("cores_type") == "number"
    checks.append(("mem type=number", mem_type_ok, r.get("mem_type", "N/A")))
    checks.append(("cores type=number", cores_type_ok, r.get("cores_type", "N/A")))

    # Prototype chain
    in_nav = r.get("dm_in_navigator") is True
    not_own = r.get("dm_own") is False
    in_proto = r.get("dm_in_proto") is True
    checks.append(("'deviceMemory' in navigator", in_nav, str(r.get("dm_in_navigator"))))
    checks.append(("not own property", not_own, f"hasOwn={r.get('dm_own')}"))
    checks.append(("in Navigator.prototype", in_proto, str(r.get("dm_in_proto"))))

    # Collateral damage
    arr_ok = r.get("array_push_ts") is True
    math_ok = r.get("math_max_ts") is True
    checks.append(("Array.push.toString native", arr_ok, str(r.get("array_push_ts"))))
    checks.append(("Math.max.toString native", math_ok, str(r.get("math_max_ts"))))

    passed = 0
    total = len(checks)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"    [{status}] {name}: {detail}")
        if ok:
            passed += 1

    print(f"\n    {passed}/{total} checks passed")


if __name__ == "__main__":
    asyncio.run(main())
