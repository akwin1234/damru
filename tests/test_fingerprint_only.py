"""Test fingerprint.com/demo only with 2GB RAM."""
import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from damru import AsyncDamru
from damru.utils import sleep, setup_logging

PH_HTTP = "proxy.example:50000"
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "fingerprint_only")

async def main():
    setup_logging(True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("=" * 60)
    print("  fingerprint.com/demo Test - 2GB RAM")
    print("=" * 60)
    t_start = time.monotonic()

    async with AsyncDamru(
        device="random",
        proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print("\n" + "=" * 60)
        print("  Navigating to fingerprint.com/demo...")
        print("=" * 60)

        await page.goto(
            "https://fingerprint.com/demo/",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        print("  Page loaded, waiting 60s for fingerprint SDK analysis...")
        await sleep(60)

        # Take screenshot FIRST before page navigates
        ss = os.path.join(RESULTS_DIR, "fingerprint_demo.png")
        try:
            await page.screenshot(path=ss, full_page=True, timeout=30000)
            print(f"  Screenshot: {ss}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        # Extract results quickly before page closes
        try:
            data = await page.evaluate(r"""() => {
                const all = document.body.innerText;
                const lines = all.split('\n').map(l => l.trim()).filter(l => l);

                // Look for visitor ID
                const visitorIdMatch = all.match(/visitor\s*id[:\s]*([a-zA-Z0-9]+)/i);
                const botMatch = all.match(/bot[:\s]*(detected|not detected|yes|no|true|false)/i);

                // Check for bot detection status
                const botDetected = all.toLowerCase().includes('bot detected') ||
                                   all.toLowerCase().includes('bot: yes') ||
                                   all.toLowerCase().includes('bot: true');
                const notBot = all.toLowerCase().includes('not a bot') ||
                              all.toLowerCase().includes('bot: no') ||
                              all.toLowerCase().includes('bot: false') ||
                              all.toLowerCase().includes('bot: not detected');

                // Get all card/section text
                const cards = [];
                for (const el of document.querySelectorAll(
                    '[class*="card"], [class*="result"], [class*="detail"], ' +
                    '[class*="info"], [class*="data"], [class*="value"]'
                )) {
                    const t = el.textContent.trim();
                    if (t.length > 3 && t.length < 300) {
                        cards.push(t);
                    }
                }

                // Get table data
                const tables = [];
                for (const table of document.querySelectorAll('table')) {
                    const rows = [];
                    for (const row of table.querySelectorAll('tr')) {
                        const cells = Array.from(row.querySelectorAll('td, th'))
                            .map(c => c.textContent.trim());
                        if (cells.length > 0) rows.push(cells);
                    }
                    if (rows.length > 0) tables.push(rows);
                }

                // Get headings
                const sections = [];
                for (const el of document.querySelectorAll('h1, h2, h3, h4, h5')) {
                    sections.push(el.textContent.trim());
                }

                return {
                    visitorId: visitorIdMatch  visitorIdMatch[1] : "N/A",
                    botDetected: botDetected && !notBot,
                    botStatus: botMatch  botMatch[1] : (notBot  "not detected" : (botDetected  "detected" : "N/A")),
                    cards: [...new Set(cards)].slice(0, 30),
                    tables: tables.slice(0, 5),
                    sections: sections.slice(0, 15),
                    pageText: all.substring(0, 3000),
                };
            }""")

            print(f"\n  Visitor ID:  {data.get('visitorId', '')}")
            print(f"  Bot Status:  {data.get('botStatus', '')}")
            print(f"  Bot Detected: {data.get('botDetected', '')}")

            if data.get("sections"):
                print(f"\n  Sections:")
                for s in data["sections"]:
                    print(f"    {s}")

            if data.get("tables"):
                for i, table in enumerate(data["tables"]):
                    print(f"\n  Table {i + 1}:")
                    for row in table[:15]:
                        print(f"    {' | '.join(str(c) for c in row)}")

            if data.get("cards"):
                print(f"\n  Detection details ({len(data['cards'])} cards):")
                for c in data["cards"][:15]:
                    short = c.replace('\n', ' ')[:150]
                    print(f"    {short}")

        except Exception as e:
            print(f"  Data extraction failed: {e}")
            data = {"error": str(e)}

        # Save JSON report
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": "auto (redroid, 2GB RAM)",
            "proxy": PH_HTTP,
            "total_time_s": round(time.monotonic() - t_start, 1),
            "fingerprint": data,
        }
        out_path = os.path.join(RESULTS_DIR, "fingerprint_report.json")
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"\n  Report: {out_path}")
        print(f"  Total time: {report['total_time_s']}s")

    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
