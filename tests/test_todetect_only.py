"""Test todetect.net only with 2GB RAM."""
import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from damru import AsyncDamru
from damru.utils import sleep, setup_logging

PH_HTTP = "proxy.example:50000"
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "todetect_only")

async def main():
    setup_logging(True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("=" * 60)
    print("  todetect.net Test - 2GB RAM")
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
        print("  Navigating to todetect.net...")
        print("=" * 60)

        await page.goto(
            "https://todetect.net/",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        print("  Page loaded, waiting 25s for analysis...")
        await sleep(25)

        # Take screenshot
        ss = os.path.join(RESULTS_DIR, "todetect.png")
        try:
            await page.screenshot(path=ss, full_page=True, timeout=30000)
            print(f"  Screenshot: {ss}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        # Extract results
        data = await page.evaluate(r"""() => {
            const all = document.body.innerText;
            const lines = all.split('\n').map(l => l.trim()).filter(l => l);

            // Look for overall score
            const scoreMatch = all.match(/(:overall|total|score|result)[:\s]*(-\d+)/i);
            const percentMatch = all.match(/(\d+)\s*%/);

            // Get all table data
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

            // Get visible sections
            const sections = [];
            for (const el of document.querySelectorAll('h1, h2, h3, h4, [class*="score"], [class*="result"]')) {
                const t = el.textContent.trim();
                if (t.length > 0 && t.length < 200) sections.push(t);
            }

            return {
                score: scoreMatch  scoreMatch[1] : percentMatch  percentMatch[1] + "%" : "N/A",
                tables: tables.slice(0, 5),
                sections: sections.slice(0, 20),
                pageText: all.substring(0, 3000),
            };
        }""")

        print(f"\n  Overall Score: {data.get('score', '')}")

        if data.get("tables"):
            for i, table in enumerate(data["tables"]):
                print(f"\n  Table {i + 1}:")
                for row in table[:20]:
                    print(f"    {' | '.join(str(c) for c in row)}")

        if data.get("sections"):
            print(f"\n  Sections:")
            for s in data["sections"]:
                print(f"    {s}")

        # Save JSON report
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": "auto (redroid, 2GB RAM)",
            "proxy": PH_HTTP,
            "total_time_s": round(time.monotonic() - t_start, 1),
            "todetect": data,
        }
        out_path = os.path.join(RESULTS_DIR, "todetect_report.json")
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"\n  Report: {out_path}")
        print(f"  Total time: {report['total_time_s']}s")

    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
