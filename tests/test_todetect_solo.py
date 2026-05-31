"""Test todetect.net only."""
import asyncio, json, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from damru import AsyncDamru
from damru.utils import sleep, setup_logging

PH_HTTP = "198.20.189.134:50000"
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "todetect_solo")

async def main():
    setup_logging(True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print("=" * 60)
    print("  todetect.net TEST (2GB RAM)")
    print("=" * 60)
    t_start = time.monotonic()

    # Use container 0 (port 5600) explicitly
    async with AsyncDamru(device="random", serial="127.0.0.1:5600", proxy=PH_HTTP, timezone="Asia/Manila", debug=True) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        await page.goto("https://todetect.net/", wait_until="domcontentloaded", timeout=60000)
        print("  Page loaded, waiting 25s...")
        await sleep(25)

        ss = os.path.join(RESULTS_DIR, "todetect.png")
        try:
            await page.screenshot(path=ss, full_page=True, timeout=30000)
            print(f"  Screenshot: {ss}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        data = await page.evaluate(r"""() => {
            const all = document.body.innerText;
            const tables = [];
            for (const table of document.querySelectorAll('table')) {
                const rows = [];
                for (const row of table.querySelectorAll('tr')) {
                    const cells = Array.from(row.querySelectorAll('td, th')).map(c => c.textContent.trim());
                    if (cells.length > 0) rows.push(cells);
                }
                if (rows.length > 0) tables.push(rows);
            }
            return {tables: tables.slice(0, 5), pageText: all.substring(0, 2000)};
        }""")

        if data.get("tables"):
            for i, table in enumerate(data["tables"]):
                print(f"\n  Table {i + 1}:")
                for row in table[:15]:
                    print(f"    {' | '.join(str(c) for c in row)}")

        with open(os.path.join(RESULTS_DIR, "report.json"), "w") as f:
            json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "total_time_s": round(time.monotonic() - t_start, 1), "data": data}, f, indent=2, default=str)

    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
