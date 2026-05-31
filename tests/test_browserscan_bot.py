"""BrowserScan bot-detection test with damru on redroid.

Navigates to browserscan.net/bot-detection, waits for results, and extracts
all detection signals with detailed breakdown.
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru
from damru.utils import sleep

PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 70)
    print("  BrowserScan Bot Detection Test (damru + redroid)")
    print("=" * 70)

    async with AsyncDamru(
        device="random",
        proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: Quick IP check
        print("\n  [1] Checking exit IP...")
        try:
            await page.goto("https://ipinfo.io/json", wait_until="load", timeout=20000)
            await sleep(1)
            ip_text = await page.evaluate("() => document.body.innerText")
            ip_data = json.loads(ip_text)
            print(f"  Exit IP: {ip_data.get('ip', '?')} ({ip_data.get('org', '?')}, {ip_data.get('city', '?')}, {ip_data.get('country', '?')})")
        except Exception as e:
            print(f"  IP check failed: {e}")

        # Step 2: Navigate to bot detection page
        print("\n  [2] Navigating to browserscan.net/bot-detection...")
        try:
            await page.goto(
                "https://www.browserscan.net/bot-detection",
                wait_until="load",
                timeout=60000,
            )
            print(f"  Page loaded: {page.url}")
        except Exception as e:
            print(f"  Navigation failed: {e}")
            return

        # Step 3: Wait for results to load
        print("  [3] Waiting for detection results (up to 60s)...")
        for attempt in range(12):
            await sleep(5)
            try:
                # Check if results are loaded by looking for result indicators
                ready = await page.evaluate("""() => {
                    const body = document.body.innerText;
                    // BrowserScan shows results when detection completes
                    return body.includes('Pass') || body.includes('Fail') ||
                           body.includes('pass') || body.includes('fail') ||
                           body.includes('Normal') || body.includes('Abnormal') ||
                           body.includes('Bot') || body.includes('Human');
                }""")
                if ready:
                    print(f"  Results ready after {(attempt + 1) * 5}s")
                    break
                if (attempt + 1) % 3 == 0:
                    print(f"  Still loading... {(attempt + 1) * 5}s")
            except Exception:
                pass
        await sleep(3)

        # Step 4: Extract ALL detection results
        print("\n  [4] Extracting detection results...")
        try:
            result = await page.evaluate(r"""() => {
                const output = {};
                const body = document.body.innerText;
                const lines = body.split('\n').map(l => l.trim()).filter(l => l);

                // Extract all visible text for analysis
                output.allLines = lines.slice(0, 200);

                // Look for specific bot detection categories
                const categories = [
                    'WebDriver', 'webdriver', 'CDP', 'Chrome DevTools',
                    'Selenium', 'Puppeteer', 'Playwright', 'PhantomJS',
                    'Headless', 'headless', 'Automation', 'automation',
                    'Bot', 'bot', 'Human', 'human',
                    'navigator.webdriver', 'window.chrome',
                    'permissions', 'plugins', 'languages',
                    'User Agent', 'user-agent', 'userAgent',
                    'screen', 'Screen', 'canvas', 'Canvas',
                    'WebGL', 'webgl', 'Audio', 'audio',
                    'Font', 'font', 'Battery', 'battery',
                    'Hardware', 'hardware', 'Memory', 'memory',
                    'Touch', 'touch', 'Connection', 'connection',
                    'Pass', 'Fail', 'Normal', 'Abnormal',
                    'Detected', 'detected', 'Not Detected'
                ];

                output.signals = {};
                for (let i = 0; i < lines.length; i++) {
                    for (const cat of categories) {
                        if (lines[i].includes(cat)) {
                            const key = cat.toLowerCase().replace(/\s+/g, '_');
                            if (!output.signals[key]) {
                                output.signals[key] = [];
                            }
                            const context = lines.slice(
                                Math.max(0, i - 1),
                                Math.min(lines.length, i + 3)
                            ).join(' | ');
                            output.signals[key].push(context.substring(0, 300));
                        }
                    }
                }

                // Try to find JSON data in the page
                const pres = document.querySelectorAll('pre, code, [class*="json"]');
                for (const el of pres) {
                    const text = el.textContent.trim();
                    if (text.length > 50 && text.startsWith('{')) {
                        try {
                            output.jsonData = JSON.parse(text);
                        } catch(e) {}
                    }
                }

                // Get all table data (BrowserScan uses tables for results)
                const tables = document.querySelectorAll('table');
                output.tables = [];
                for (const table of tables) {
                    const rows = [];
                    for (const row of table.querySelectorAll('tr')) {
                        const cells = Array.from(row.querySelectorAll('td, th'))
                            .map(c => c.textContent.trim());
                        if (cells.length > 0) {
                            rows.push(cells);
                        }
                    }
                    if (rows.length > 0) {
                        output.tables.push(rows);
                    }
                }

                // Get all elements with pass/fail indicators
                const resultEls = document.querySelectorAll(
                    '[class*="pass"], [class*="fail"], [class*="success"], ' +
                    '[class*="danger"], [class*="warning"], [class*="error"], ' +
                    '[class*="normal"], [class*="abnormal"], [class*="result"]'
                );
                output.resultElements = [];
                for (const el of resultEls) {
                    output.resultElements.push({
                        class: el.className.substring(0, 100),
                        text: el.textContent.trim().substring(0, 200)
                    });
                }

                // Also grab card/section headers with their content
                const cards = document.querySelectorAll(
                    '[class*="card"], [class*="section"], [class*="item"], ' +
                    '[class*="detection"], [class*="check"]'
                );
                output.cards = [];
                for (const card of cards) {
                    const text = card.textContent.trim();
                    if (text.length > 5 && text.length < 500) {
                        output.cards.push(text);
                    }
                }
                // Deduplicate and limit
                output.cards = [...new Set(output.cards)].slice(0, 30);

                return output;
            }""")

            print("\n" + "=" * 70)
            print("  BOT DETECTION RESULTS")
            print("=" * 70)

            # Print tables first (most structured)
            if result.get("tables"):
                for i, table in enumerate(result["tables"]):
                    print(f"\n  --- Table {i + 1} ---")
                    for row in table[:20]:
                        print(f"  {' | '.join(row)}")

            # Print result elements with pass/fail
            if result.get("resultElements"):
                print(f"\n  --- Pass/Fail Elements ({len(result['resultElements'])}) ---")
                seen = set()
                for el in result["resultElements"][:30]:
                    text = el["text"][:150]
                    if text not in seen:
                        seen.add(text)
                        cls = el.get("class", "")
                        indicator = ""
                        if "pass" in cls.lower() or "success" in cls.lower() or "normal" in cls.lower():
                            indicator = " [PASS]"
                        elif "fail" in cls.lower() or "danger" in cls.lower() or "abnormal" in cls.lower():
                            indicator = " [FAIL]"
                        elif "warning" in cls.lower():
                            indicator = " [WARN]"
                        print(f"  {text}{indicator}")

            # Print cards/sections
            if result.get("cards"):
                print(f"\n  --- Detection Cards ({len(result['cards'])}) ---")
                for card in result["cards"][:20]:
                    card_short = card.replace('\n', ' ').strip()[:200]
                    print(f"  {card_short}")

            # Print key signals
            if result.get("signals"):
                print(f"\n  --- Key Signals ---")
                for key, matches in sorted(result["signals"].items()):
                    if key in ("pass", "fail", "normal", "abnormal", "detected", "not_detected"):
                        continue  # Skip generic terms
                    print(f"  {key}:")
                    for m in matches[:3]:
                        print(f"    {m[:200]}")

            # Print JSON data if found
            if result.get("jsonData"):
                print("\n  --- JSON Data ---")
                print(f"  {json.dumps(result['jsonData'], indent=2)[:2000]}")

        except Exception as e:
            print(f"  Extraction error: {e}")
            import traceback
            traceback.print_exc()

        # Step 5: Screenshot
        try:
            ss_path = os.path.join(os.path.dirname(__file__), "browserscan_bot.png")
            await page.screenshot(path=ss_path, full_page=True)
            print(f"\n  Screenshot saved: {ss_path}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        print("\n" + "=" * 70)
        print("  Done")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
