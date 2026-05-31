"""MuMu mode: todetect.net test.

Tests stealth quality on MuMu with the new fixes:
  Fix 1: GPU custom mode (Mali/Xclipse/Adreno all work)
  Fix 2: Android version in UA matches target device
  Fix 3: WebRTC fallback uses high-port UDP range
  Fix 4: navigator.deviceMemory spoofed via libfakemem.so (same as redroid)

Usage:
    python tests/test_mumu_todetect.py
    python tests/test_mumu_todetect.py --device "Google Pixel 8 Pro"
"""
import asyncio
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from damru import AsyncDamru
from damru.utils import sleep, setup_logging

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP   = "198.20.189.134:50000"
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "mumu_todetect")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=None, help="Device name (default: random non-Adreno)")
    parser.add_argument("--serial", default=None, help="ADB serial (default: auto-detect)")
    parser.add_argument("--adreno", action="store_true", help="Allow Adreno devices too")
    args = parser.parse_args()

    setup_logging(True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    from damru.devices import DEVICES, get_device
    import random

    if args.device:
        target = get_device(args.device)
    else:
        pool = [d for d in DEVICES if d.gpu_family in ("mali", "xclipse")] if not args.adreno else DEVICES
        target = random.choice(pool or DEVICES)

    print("=" * 60)
    print("  MuMu — todetect.net")
    print("=" * 60)
    print(f"  Device:  {target.name}  (Android {target.android_version})")
    print(f"  GPU:     {target.gpu_family} — {target.webgl_renderer}")
    print(f"  mem:     {target.device_memory} GB   cores: {target.hardware_concurrency}")
    print()

    t_start = time.monotonic()

    async with AsyncDamru(
        device=target.name,
        serial=args.serial,
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        debug=True,
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        await page.goto("https://todetect.net/", wait_until="domcontentloaded", timeout=60000)
        print("  Loaded — waiting 25s for analysis...")
        await sleep(25)

        ss = os.path.join(RESULTS_DIR, "todetect.png")
        try:
            await page.screenshot(path=ss, full_page=True, timeout=30000)
            print(f"  Screenshot: {ss}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        data = await page.evaluate(r"""() => {
            const all = document.body.innerText;
            const pct = (all.match(/(\d+)\s*%/) || [])[1];
            const tables = [];
            for (const t of document.querySelectorAll('table')) {
                const rows = [];
                for (const r of t.querySelectorAll('tr')) {
                    const cells = Array.from(r.querySelectorAll('td,th')).map(c => c.textContent.trim());
                    if (cells.length) rows.push(cells);
                }
                if (rows.length) tables.push(rows);
            }
            return { score: pct ? pct + "%" : "N/A", tables: tables.slice(0, 5), pageText: all.substring(0, 3000) };
        }""")

        elapsed = round(time.monotonic() - t_start, 1)
        print(f"\n  Score: {data.get('score', '?')}   ({elapsed}s)")
        for i, table in enumerate(data.get("tables", [])):
            print(f"\n  Table {i+1}:")
            for row in table[:15]:
                print(f"    {' | '.join(str(c) for c in row)}")

        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": "mumu",
            "device": target.name,
            "gpu_family": target.gpu_family,
            "target_android": target.android_version,
            "total_time_s": elapsed,
            "score": data.get("score"),
            "tables": data.get("tables"),
        }
        out = os.path.join(RESULTS_DIR, "report.json")
        with open(out, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n  Report: {out}")


if __name__ == "__main__":
    asyncio.run(main())
