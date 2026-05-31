"""Verify faked CPU cores + RAM on real fingerprinting sites."""
import asyncio
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from damru import AsyncDamru

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"

# Use S24 FE (10 cores, 8GB) — easy to spot if faked correctly
DEVICE = "Samsung Galaxy S24 FE"
EXPECTED_CORES = 10
EXPECTED_MEM = 8


async def main():
    print("=" * 60)
    print(f"  Hardware Spoof Verification on Real Sites")
    print(f"  Device: {DEVICE}")
    print(f"  Expected: cores={EXPECTED_CORES}, mem={EXPECTED_MEM}")
    print("=" * 60)

    async with AsyncDamru(
        device=DEVICE,
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=False,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # ── Test 0: Direct JS check (baseline) ──
        print("\n--- [0] Direct JS Check ---")
        await page.goto("data:text/html,<h1>hw</h1>", wait_until="domcontentloaded", timeout=10000)
        await asyncio.sleep(1)
        hw = await page.evaluate("({cores: navigator.hardwareConcurrency, mem: navigator.deviceMemory})")
        print(f"  cores={hw['cores']} mem={hw['mem']}")
        print(f"  {'PASS' if hw['cores'] == EXPECTED_CORES and hw['mem'] == EXPECTED_MEM else 'FAIL'}")

        # ── Test 1: BrowserLeaks ──
        print("\n--- [1] BrowserLeaks (browserleaks.com/javascript) ---")
        try:
            await page.goto("https://browserleaks.com/javascript", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(8)
            text = await page.evaluate("document.body.innerText")
            # Look for hardwareConcurrency and deviceMemory in the page
            for line in text.split("\n"):
                low = line.lower().strip()
                if "hardwareconcurrency" in low or "devicememory" in low or "device memory" in low:
                    print(f"    {line.strip()[:100]}")
            # Also extract directly from their JS results
            bl_hw = await page.evaluate("""() => {
                const rows = document.querySelectorAll('tr');
                const result = {};
                for (const row of rows) {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 2) {
                        const key = cells[0].textContent.trim().toLowerCase();
                        const val = cells[1].textContent.trim();
                        if (key.includes('hardwareconcurrency')) result.cores = val;
                        if (key.includes('devicememory')) result.mem = val;
                    }
                }
                return result;
            }""")
            if bl_hw.get("cores") or bl_hw.get("mem"):
                print(f"  Extracted: cores={bl_hw.get('cores', '?')}, mem={bl_hw.get('mem', '?')}")
                cores_ok = str(EXPECTED_CORES) in str(bl_hw.get("cores", ""))
                mem_ok = str(EXPECTED_MEM) in str(bl_hw.get("mem", ""))
                print(f"  cores: {'PASS' if cores_ok else 'FAIL'}, mem: {'PASS' if mem_ok else 'FAIL'}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ── Test 2: BrowserScan ──
        print("\n--- [2] BrowserScan (browserscan.net) ---")
        try:
            await page.goto("https://www.browserscan.net/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(20)
            text = await page.evaluate("document.body.innerText")
            # BrowserScan shows hardware info
            for line in text.split("\n"):
                low = line.lower().strip()
                if any(kw in low for kw in ["hardware", "memory", "core", "cpu", "device mem", "concurrency"]):
                    print(f"    {line.strip()[:100]}")
            # Check score
            m = re.search(r"(\d+)\s*%", text)
            if m:
                print(f"  Score: {m.group(1)}%")
            # Try to get specific values from the page
            bs_hw = await page.evaluate("""() => {
                const text = document.body.innerText;
                const result = {};
                // Look for patterns like "Hardware Concurrency 10" or "Device Memory 8"
                const hcMatch = text.match(/(?:hardware\\s*concurrency|cpu\\s*cores?)[\\s:]*?(\\d+)/i);
                const dmMatch = text.match(/(?:device\\s*memory)[\\s:]*?(\\d+)/i);
                if (hcMatch) result.cores = hcMatch[1];
                if (dmMatch) result.mem = dmMatch[1];
                return result;
            }""")
            if bs_hw.get("cores") or bs_hw.get("mem"):
                print(f"  Extracted: cores={bs_hw.get('cores', '?')}, mem={bs_hw.get('mem', '?')}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ── Test 3: CreepJS ──
        print("\n--- [3] CreepJS ---")
        try:
            await page.goto("https://abrahamjuliot.github.io/creepjs/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(30)
            text = await page.evaluate("document.body.innerText")
            # Look for hardware values and lies
            for line in text.split("\n"):
                low = line.lower().strip()
                if any(kw in low for kw in ["hardware", "memory", "core", "device mem", "concurrency", "lies", "headless", "stealth"]):
                    if len(line.strip()) < 120:
                        print(f"    {line.strip()}")
            # Extract specific values
            cjs = await page.evaluate("""() => {
                const text = document.body.innerText;
                const result = {};
                const hcMatch = text.match(/hardwareConcurrency[:\\s]*?(\\d+)/i);
                const dmMatch = text.match(/deviceMemory[:\\s]*?(\\d+\\.?\\d*)/i);
                const liesMatch = text.match(/lies[:\\s]*(\\d+)/i);
                if (hcMatch) result.cores = hcMatch[1];
                if (dmMatch) result.mem = dmMatch[1];
                if (liesMatch) result.lies = liesMatch[1];
                return result;
            }""")
            print(f"  Extracted: cores={cjs.get('cores', '?')}, mem={cjs.get('mem', '?')}, lies={cjs.get('lies', '?')}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # ── Test 4: deviceinfo.me ──
        print("\n--- [4] deviceinfo.me ---")
        try:
            await page.goto("https://www.deviceinfo.me/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(10)
            di_hw = await page.evaluate("""() => {
                const result = {};
                const rows = document.querySelectorAll('tr');
                for (const row of rows) {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 2) {
                        const key = cells[0].textContent.trim().toLowerCase();
                        const val = cells[1].textContent.trim();
                        if (key.includes('hardware concurrency') || key.includes('logical processors'))
                            result.cores = val;
                        if (key.includes('device memory'))
                            result.mem = val;
                    }
                }
                return result;
            }""")
            if di_hw.get("cores") or di_hw.get("mem"):
                print(f"  cores={di_hw.get('cores', '?')}, mem={di_hw.get('mem', '?')}")
                cores_ok = str(EXPECTED_CORES) in str(di_hw.get("cores", ""))
                mem_ok = str(EXPECTED_MEM) in str(di_hw.get("mem", ""))
                print(f"  cores: {'PASS' if cores_ok else 'FAIL'}, mem: {'PASS' if mem_ok else 'FAIL'}")
            else:
                # Fallback: search page text
                text = await page.evaluate("document.body.innerText")
                for line in text.split("\n"):
                    low = line.lower().strip()
                    if "hardware" in low or "device memory" in low or "logical" in low:
                        print(f"    {line.strip()[:100]}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
