"""Verify faked screen resolution on real fingerprinting sites."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from damru import AsyncDamru
from damru.devices import get_device

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"

# Pixel 8 Pro has distinctive resolution: 1344x2992 @560dpi
DEVICE = "Google Pixel 8 Pro"


async def main():
    dev = get_device(DEVICE)
    print("=" * 60)
    print(f"  Screen Resolution Verification on Real Sites")
    print(f"  Device: {DEVICE}")
    print(f"  Device default: {dev.screen_width}x{dev.screen_height} @{dev.density_dpi}dpi")
    print("=" * 60)

    async with AsyncDamru(
        device=DEVICE,
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=False,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # -- Test 0: Direct JS check --
        print("\n--- [0] Direct JS Check ---")
        await page.goto("data:text/html,<h1>screen</h1>", wait_until="domcontentloaded", timeout=10000)
        await asyncio.sleep(1)
        sc = await page.evaluate("""() => ({
            screenW: screen.width,
            screenH: screen.height,
            availW: screen.availWidth,
            availH: screen.availHeight,
            innerW: window.innerWidth,
            innerH: window.innerHeight,
            outerW: window.outerWidth,
            outerH: window.outerHeight,
            dpr: window.devicePixelRatio,
            colorDepth: screen.colorDepth,
            orientation: screen.orientation  screen.orientation.type : 'N/A',
        })""")
        print(f"  screen: {sc['screenW']}x{sc['screenH']}")
        print(f"  avail:  {sc['availW']}x{sc['availH']}")
        print(f"  inner:  {sc['innerW']}x{sc['innerH']}")
        print(f"  outer:  {sc['outerW']}x{sc['outerH']}")
        print(f"  DPR:    {sc['dpr']}")
        print(f"  color:  {sc['colorDepth']}")
        print(f"  orient: {sc['orientation']}")

        # -- Test 1: BrowserLeaks --
        print("\n--- [1] BrowserLeaks ---")
        try:
            await page.goto("https://browserleaks.com/javascript", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(8)
            bl = await page.evaluate("""() => {
                const result = {};
                const rows = document.querySelectorAll('tr');
                for (const row of rows) {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 2) {
                        const key = cells[0].textContent.trim().toLowerCase();
                        const val = cells[1].textContent.trim();
                        if (key.includes('screen') || key.includes('window') || key.includes('pixel ratio') ||
                            key.includes('avail') || key.includes('color') || key.includes('orientation') ||
                            key.includes('inner') || key.includes('outer'))
                            result[key] = val;
                    }
                }
                return result;
            }""")
            for k, v in sorted(bl.items()):
                print(f"    {k}: {v}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # -- Test 2: BrowserScan --
        print("\n--- [2] BrowserScan ---")
        try:
            await page.goto("https://www.browserscan.net/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(20)
            text = await page.evaluate("document.body.innerText")
            for line in text.split("\n"):
                low = line.lower().strip()
                if any(kw in low for kw in ["screen", "resolution", "viewport", "pixel", "dpr", "window"]):
                    if len(line.strip()) < 120:
                        print(f"    {line.strip()}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # -- Test 3: whatismyresolution.com (simple) --
        print("\n--- [3] whatismyresolution.com ---")
        try:
            await page.goto("https://whatismyscreenresolution.net/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            text = await page.evaluate("document.body.innerText")
            for line in text.split("\n"):
                low = line.lower().strip()
                if any(kw in low for kw in ["screen", "resolution", "viewport", "pixel", "window", "browser"]):
                    if len(line.strip()) < 120 and len(line.strip()) > 3:
                        print(f"    {line.strip()}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # -- Test 4: deviceinfo.me --
        print("\n--- [4] deviceinfo.me ---")
        try:
            await page.goto("https://www.deviceinfo.me/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(10)
            di = await page.evaluate("""() => {
                const result = {};
                const rows = document.querySelectorAll('tr');
                for (const row of rows) {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 2) {
                        const key = cells[0].textContent.trim().toLowerCase();
                        const val = cells[1].textContent.trim();
                        if (key.includes('screen') || key.includes('window') || key.includes('pixel') ||
                            key.includes('viewport') || key.includes('resolution') || key.includes('dpr') ||
                            key.includes('avail') || key.includes('inner') || key.includes('outer') ||
                            key.includes('color depth'))
                            result[key] = val;
                    }
                }
                return result;
            }""")
            for k, v in sorted(di.items()):
                print(f"    {k}: {v}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
