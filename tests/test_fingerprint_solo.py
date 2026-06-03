"""Test fingerprint.com/demo only."""
import asyncio, json, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from damru import AsyncDamru
from damru.utils import sleep, setup_logging

PH_HTTP = "proxy.example:50000"
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "fingerprint_solo")

async def main():
    setup_logging(True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print("=" * 60)
    print("  fingerprint.com/demo TEST (2GB RAM)")
    print("=" * 60)
    t_start = time.monotonic()

    # Use container 1 (port 5601) explicitly
    async with AsyncDamru(device="random", serial="127.0.0.1:5601", proxy=PH_HTTP, timezone="Asia/Manila", debug=True) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        await page.goto("https://fingerprint.com/demo/", wait_until="domcontentloaded", timeout=60000)
        print("  Page loaded, waiting 20s...")
        await sleep(20)

        ss = os.path.join(RESULTS_DIR, "fingerprint.png")
        try:
            await page.screenshot(path=ss, full_page=True, timeout=30000)
            print(f"  Screenshot: {ss}")
        except Exception as e:
            print(f"  Screenshot failed: {e}")

        try:
            data = await page.evaluate(r"""() => {
                const all = document.body.innerText;
                const visitorIdMatch = all.match(/visitor\s*id[:\s]*([a-zA-Z0-9]+)/i);
                const botDetected = all.toLowerCase().includes('bot detected');
                const notBot = all.toLowerCase().includes('not a bot');
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
                    visitorId: visitorIdMatch  visitorIdMatch[1] : "N/A",
                    botStatus: notBot  "not detected" : (botDetected  "detected" : "N/A"),
                    tables: tables.slice(0, 5),
                    pageText: all.substring(0, 2000)
                };
            }""", timeout=5000)
            
            print(f"\n  Visitor ID: {data.get('visitorId', '')}")
            print(f"  Bot Status: {data.get('botStatus', '')}")
            
            if data.get("tables"):
                for i, table in enumerate(data["tables"]):
                    print(f"\n  Table {i + 1}:")
                    for row in table[:10]:
                        print(f"    {' | '.join(str(c) for c in row)}")
        except Exception as e:
            print(f"  Data extraction failed: {e}")
            data = {"error": str(e)}

        with open(os.path.join(RESULTS_DIR, "report.json"), "w") as f:
            json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "total_time_s": round(time.monotonic() - t_start, 1), "data": data}, f, indent=2, default=str)

    print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
