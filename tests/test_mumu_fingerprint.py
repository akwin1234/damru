"""MuMu mode: fingerprint.com/demo test.

Usage:
    python tests/test_mumu_fingerprint.py
    python tests/test_mumu_fingerprint.py --device "Google Pixel 8 Pro"
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

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP   = "proxy.example:50000"
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "mumu_fingerprint")


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
    print("  MuMu - fingerprint.com/demo")
    print("=" * 60)
    print(f"  Device:  {target.name}  (Android {target.android_version})")
    print(f"  GPU:     {target.gpu_family} - {target.webgl_renderer}")
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

        await page.goto("https://fingerprint.com/demo/", wait_until="domcontentloaded", timeout=90000)
        print("  Loaded - waiting 60s for analysis...")
        await sleep(60)

        ss = os.path.join(RESULTS_DIR, "fingerprint.png")
        try:
            await page.screenshot(path=ss, full_page=True, timeout=30000)
            print(f"  Screenshot: {ss}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        try:
            data = await page.evaluate(r"""() => {
                const all = document.body.innerText;
                const lc = all.toLowerCase();
                // Bot detection
                const botDetected = lc.includes('bot detected') || lc.includes('bot: true');
                const notBot = lc.includes('not a bot') || lc.includes('bot: notdetected') || lc.includes('bot: false');
                // Scores and signals
                const suspectMatch = all.match(/suspect\s*score[:\s]*(\d+)/i);
                const emulatorMatch = all.match(/emulator[:\s]*(true|false)/i);
                const rootMatch = all.match(/root\s*apps[:\s]*(true|false)/i);
                const confidenceMatch = all.match(/confidence[:\s]*([\d.]+)/i);
                const visitorIdMatch = all.match(/visitor\s*id[:\s]*([A-Z0-9]{20,})/i);
                // Collect all key: value pairs from the demo sections
                const signals = {};
                for (const el of document.querySelectorAll('[class*="signal"], [class*="Signal"], [class*="result"], [class*="Result"]')) {
                    const label = el.querySelector('[class*="label"], [class*="Label"], [class*="key"], dt');
                    const value = el.querySelector('[class*="value"], [class*="Value"], dd, [class*="signal-value"]');
                    if (label && value) {
                        signals[label.textContent.trim()] = value.textContent.trim();
                    }
                }
                // Raw API response if embedded in page
                let apiData = null;
                try {
                    const pre = Array.from(document.querySelectorAll('pre')).find(p => p.textContent.includes('"visitorId"'));
                    if (pre) apiData = JSON.parse(pre.textContent);
                } catch(e) {}
                return {
                    botStatus: notBot  "notDetected" : (botDetected  "detected" : "N/A"),
                    suspectScore: suspectMatch  suspectMatch[1] : "N/A",
                    emulator: emulatorMatch  emulatorMatch[1] : "N/A",
                    rootApps: rootMatch  rootMatch[1] : "N/A",
                    confidence: confidenceMatch  confidenceMatch[1] : "N/A",
                    visitorId: visitorIdMatch  visitorIdMatch[1] : "N/A",
                    signals: signals,
                    apiData: apiData,
                    pageText: all.substring(0, 5000),
                };
            }""")
        except Exception as e:
            print(f"  Eval failed: {e}")
            data = {"error": str(e)}

        elapsed = round(time.monotonic() - t_start, 1)
        print(f"\n  Bot status:    {data.get('botStatus', '')}")
        print(f"  Suspect score: {data.get('suspectScore', '')}")
        print(f"  Emulator:      {data.get('emulator', '')}")
        print(f"  Root apps:     {data.get('rootApps', '')}")
        print(f"  Confidence:    {data.get('confidence', '')}")
        print(f"  Visitor ID:    {data.get('visitorId', '')}")
        print(f"  Time:          {elapsed}s")
        signals = data.get("signals", {})
        if signals:
            print("\n  Signals:")
            for k, v in list(signals.items())[:20]:
                print(f"    {k}: {v}")
        api = data.get("apiData")
        if api:
            print("\n  API data (key fields):")
            for k in ["visitorId", "confidence", "bot", "emulator", "rootApps", "suspectScore",
                      "developerTools", "tampering", "antiDetectBrowser", "virtualMachine",
                      "proxy", "vpn", "incognito"]:
                if k in api:
                    print(f"    {k}: {api[k]}")
        if data.get("suspectScore") == "N/A" and not signals and not api:
            print("\n  [Page still loading - increase wait time or check screenshot]")
            print(f"\n  Page text (first 500 chars):\n  {data.get('pageText','')[:500]}")

        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": "mumu",
            "device": target.name,
            "gpu_family": target.gpu_family,
            "target_android": target.android_version,
            "total_time_s": elapsed,
            "data": data,
        }
        out = os.path.join(RESULTS_DIR, "report.json")
        with open(out, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n  Report: {out}")


if __name__ == "__main__":
    asyncio.run(main())
