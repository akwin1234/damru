"""Test todetect.net and fingerprint.com/demo only (skip CreepJS)."""
import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from damru import AsyncDamru
from damru.utils import sleep, setup_logging

PH_HTTP = "198.20.189.134:50000"
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "todetect_fingerprint")

async def test_todetect(page):
    print("\n" + "=" * 60)
    print("  TEST 1: todetect.net")
    print("=" * 60)

    await page.goto("https://todetect.net/", wait_until="domcontentloaded", timeout=60000)
    print("  Page loaded, waiting 25s for analysis...")
    await sleep(25)

    ss = os.path.join(RESULTS_DIR, "todetect.png")
    try:
        await page.screenshot(path=ss, full_page=True, timeout=30000)
        print(f"  Screenshot: {ss}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")

    data = await page.evaluate(r"""() => {
        const all = document.body.innerText;
        const scoreMatch = all.match(/(?:overall|total|score|result)[:\s]*(-?\d+)/i);
        const percentMatch = all.match(/(\d+)\s*%/);
        
        const tables = [];
        for (const table of document.querySelectorAll('table')) {
            const rows = [];
            for (const row of table.querySelectorAll('tr')) {
                const cells = Array.from(row.querySelectorAll('td, th')).map(c => c.textContent.trim());
                if (cells.length > 0) rows.push(cells);
            }
            if (rows.length > 0) tables.push(rows);
        }

        return {
            score: scoreMatch ? scoreMatch[1] : percentMatch ? percentMatch[1] + "%" : "N/A",
            tables: tables.slice(0, 5),
            pageText: all.substring(0, 2000),
        };
    }""")

    print(f"\n  Score: {data.get('score', '?')}")
    if data.get("tables"):
        for i, table in enumerate(data["tables"]):
            print(f"\n  Table {i + 1}:")
            for row in table[:15]:
                print(f"    {' | '.join(str(c) for c in row)}")
    
    return data


async def test_fingerprint(page):
    print("\n" + "=" * 60)
    print("  TEST 2: fingerprint.com/demo")
    print("=" * 60)

    await page.goto("https://fingerprint.com/demo/", wait_until="domcontentloaded", timeout=60000)
    print("  Page loaded, waiting 20s for analysis...")
    await sleep(20)

    ss = os.path.join(RESULTS_DIR, "fingerprint_demo.png")
    try:
        await page.screenshot(path=ss, full_page=True, timeout=30000)
        print(f"  Screenshot: {ss}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")

    try:
        data = await page.evaluate(r"""() => {
            const all = document.body.innerText;
            const visitorIdMatch = all.match(/visitor\s*id[:\s]*([a-zA-Z0-9]+)/i);
            const botMatch = all.match(/bot[:\s]*(detected|not detected|yes|no|true|false)/i);
            
            const botDetected = all.toLowerCase().includes('bot detected') || all.toLowerCase().includes('bot: yes');
            const notBot = all.toLowerCase().includes('not a bot') || all.toLowerCase().includes('bot: no');

            const tables = [];
            for (const table of document.querySelectorAll('table')) {
                const rows = [];
                for (const row of table.querySelectorAll('tr')) {
                    const cells = Array.from(row.querySelectorAll('td, th')).map(c => c.textContent.trim());
                    if (cells.length > 0) rows.push(cells);
                }
                if (rows.length > 0) tables.push(rows);
            }

            return {
                visitorId: visitorIdMatch ? visitorIdMatch[1] : "N/A",
                botDetected: botDetected && !notBot,
                botStatus: botMatch ? botMatch[1] : (notBot ? "not detected" : (botDetected ? "detected" : "N/A")),
                tables: tables.slice(0, 5),
                pageText: all.substring(0, 2000),
            };
        }""", timeout=5000)
        
        print(f"\n  Visitor ID: {data.get('visitorId', '?')}")
        print(f"  Bot Status: {data.get('botStatus', '?')}")
        
        if data.get("tables"):
            for i, table in enumerate(data["tables"]):
                print(f"\n  Table {i + 1}:")
                for row in table[:10]:
                    print(f"    {' | '.join(str(c) for c in row)}")
        
        return data
    except Exception as e:
        print(f"  Data extraction failed: {e}")
        return {"error": str(e)}


async def main():
    setup_logging(True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("=" * 60)
    print("  todetect.net + fingerprint.com/demo (2GB RAM)")
    print("=" * 60)
    t_start = time.monotonic()

    async with AsyncDamru(
        device="random",
        proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        results = {}

        try:
            results["todetect"] = await test_todetect(page)
        except Exception as e:
            print(f"  todetect ERROR: {e}")
            results["todetect"] = {"error": str(e)}

        try:
            results["fingerprint"] = await test_fingerprint(page)
        except Exception as e:
            print(f"  fingerprint ERROR: {e}")
            results["fingerprint"] = {"error": str(e)}

        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": "auto (redroid, 2GB RAM)",
            "proxy": PH_HTTP,
            "total_time_s": round(time.monotonic() - t_start, 1),
            "results": results,
        }
        
        out_path = os.path.join(RESULTS_DIR, "report.json")
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print("\n" + "=" * 60)
        print("  SUMMARY")
        print("=" * 60)
        print(f"  Total time: {report['total_time_s']}s")
        print(f"  todetect score: {results.get('todetect', {}).get('score', '?')}")
        print(f"  fingerprint bot: {results.get('fingerprint', {}).get('botStatus', '?')}")
        print(f"\n  Report: {out_path}")

    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
