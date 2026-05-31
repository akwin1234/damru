"""Test fingerprint.com/demo with CDP disconnect during fingerprinting.

Strategy: Connect CDP → set overrides → navigate → DISCONNECT CDP →
wait for fingerprinting → RECONNECT CDP → extract results.

FingerprintJS can't detect DevTools if CDP isn't connected during
the fingerprinting phase.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru
from damru.utils import logger, sleep

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 70)
    print("  fingerprint.com/demo — CDP disconnect test")
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

        # Step 1: Navigate to fingerprint.com/demo WITH CDP connected
        # (overrides like UA, touch, cores are active for this navigation)
        print("\n  [1] Navigating to fingerprint.com/demo (CDP connected)...")
        await page.goto(
            "https://fingerprint.com/demo/",
            wait_until="commit",  # Return as soon as server responds
            timeout=60000,
        )
        print("  Page committed (HTTP response received with correct UA headers)")

        # Step 2: Brief pause to let critical overrides take effect
        # UA is already in HTTP headers, touch/cores are renderer-level
        await sleep(1)

        # Step 3: DISCONNECT CDP — fingerprinting script runs without DevTools
        print("\n  [2] Disconnecting CDP...")
        damru = context  # This is the BrowserContext, we need the AsyncDamru
        # Actually we need to access the AsyncDamru instance directly
        # The context manager returns BrowserContext, not AsyncDamru
        # Let me use a different approach

    # Can't disconnect from within the context manager easily.
    # Let me use AsyncDamru manually instead.
    print("\n  Restarting with manual control...")

    damru = AsyncDamru(
        device="Samsung Galaxy S23 Ultra",
        serial="localhost:5600",
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    )
    context = await damru.__aenter__()
    page = context.pages[0] if context.pages else await context.new_page()

    try:
        # Step 1: Navigate WITH CDP (overrides active for request headers)
        print("\n  [1] Navigating to fingerprint.com/demo (CDP connected)...")
        await page.goto(
            "https://fingerprint.com/demo/",
            wait_until="commit",
            timeout=60000,
        )
        print("  Page committed")
        await sleep(0.5)

        # Step 2: DISCONNECT CDP
        print("  [2] Disconnecting CDP (DevTools becomes invisible)...")
        await damru.disconnect_cdp()

        # Step 3: Wait for fingerprinting to complete (~60s without CDP)
        print("  [3] Waiting 60s for fingerprinting to complete (no CDP)...")
        for i in range(6):
            await sleep(10)
            print(f"      {(i+1)*10}s...")

        # Step 4: RECONNECT CDP to extract results
        print("  [4] Reconnecting CDP to extract results...")
        context = await damru.reconnect_cdp()
        pages = context.pages
        if not pages:
            print("  ERROR: No pages found after reconnect")
            return
        page = pages[0]
        print(f"  Reconnected — page URL: {page.url}")

        # Step 5: Extract the fingerprint report
        print("  [5] Extracting results...")
        report = await page.evaluate("""() => {
            const body = document.body.innerText || '';
            const serverIdx = body.indexOf('"products"');
            if (serverIdx === -1) return {error: 'No products found', bodySnippet: body.substring(0, 2000)};

            const jsonStart = body.lastIndexOf('{', serverIdx);
            if (jsonStart === -1) return {error: 'No JSON start'};

            let depth = 0, jsonEnd = -1;
            for (let i = jsonStart; i < body.length; i++) {
                if (body[i] === '{') depth++;
                else if (body[i] === '}') { depth--; if (depth === 0) { jsonEnd = i + 1; break; } }
            }
            if (jsonEnd === -1) return {error: 'No JSON end'};

            try {
                return JSON.parse(body.substring(jsonStart, jsonEnd));
            } catch(e) {
                return {error: 'Parse failed: ' + e.message};
            }
        }""")

        print("\n" + "=" * 70)
        print("  KEY RESULTS")
        print("=" * 70)

        if "error" in report:
            print(f"  ERROR: {report['error']}")
            if "bodySnippet" in report:
                for line in report["bodySnippet"].split("\n"):
                    line = line.strip()
                    if line:
                        print(f"    {line}")
        else:
            products = report.get("products", report)
            signals = {
                "developerTools": products.get("developerTools", {}).get("data", {}),
                "tampering": products.get("tampering", {}).get("data", {}),
                "botd": products.get("botd", {}).get("data", {}).get("bot", {}),
                "emulator": products.get("emulator", {}).get("data", {}),
                "rootApps": products.get("rootApps", {}).get("data", {}),
                "virtualMachine": products.get("virtualMachine", {}).get("data", {}),
                "frida": products.get("frida", {}).get("data", {}),
                "proxy": products.get("proxy", {}).get("data", {}),
                "vpn": products.get("vpn", {}).get("data", {}),
                "suspectScore": products.get("suspectScore", {}).get("data", {}),
                "incognito": products.get("incognito", {}).get("data", {}),
            }

            for name, data in signals.items():
                result = data.get("result", data)
                marker = "  <<< TARGET" if name == "developerTools" else ""
                if name == "tampering":
                    print(f"  {name}: result={data.get('result')}, anomalyScore={data.get('anomalyScore')}, antiDetectBrowser={data.get('antiDetectBrowser')}{marker}")
                else:
                    print(f"  {name}: {result}{marker}")

        print("\n" + "=" * 70)
        print("  Done")
        print("=" * 70)

    finally:
        # Clean up manually (disconnect_cdp already called, so __aexit__
        # will skip CDP disconnect)
        try:
            await damru.__aexit__(None, None, None)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
