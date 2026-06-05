"""Test todetect.net and fingerprint.com in parallel using 2 separate containers."""
import asyncio, json, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from damru import AsyncDamru
from damru.utils import sleep, setup_logging

PH_HTTP = os.environ.get("DAMRU_TEST_PROXY")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "parallel_sites")

async def _probe_todetect():
    """Test todetect.net on container 0."""
    print("\n[TODETECT] Starting...")
    t_start = time.monotonic()
    todetect_dir = os.path.join(RESULTS_DIR, "todetect")
    os.makedirs(todetect_dir, exist_ok=True)

    async with AsyncDamru(device="random", proxy=PH_HTTP, timezone="Asia/Manila", debug=True) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        await page.goto("https://todetect.net/", wait_until="domcontentloaded", timeout=60000)
        print("[TODETECT] Page loaded, waiting 25s...")
        await sleep(25)

        ss = os.path.join(todetect_dir, "todetect.png")
        try:
            await page.screenshot(path=ss, full_page=True, timeout=30000)
            print(f"[TODETECT] Screenshot: {ss}")
        except Exception as e:
            print(f"[TODETECT] Screenshot failed: {e}")

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
                print(f"\n[TODETECT] Table {i + 1}:")
                for row in table[:15]:
                    print(f"  {' | '.join(str(c) for c in row)}")

        with open(os.path.join(todetect_dir, "report.json"), "w") as f:
            json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "total_time_s": round(time.monotonic() - t_start, 1), "data": data}, f, indent=2, default=str)

    print(f"[TODETECT] Done in {time.monotonic() - t_start:.1f}s")
    return {"site": "todetect", "success": True, "time": time.monotonic() - t_start}

async def _probe_fingerprint():
    """Test fingerprint.com on container 1."""
    print("\n[FINGERPRINT] Starting...")
    t_start = time.monotonic()
    fp_dir = os.path.join(RESULTS_DIR, "fingerprint")
    os.makedirs(fp_dir, exist_ok=True)

    async with AsyncDamru(device="random", proxy=PH_HTTP, timezone="Asia/Manila", debug=True) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        await page.goto("https://fingerprint.com/demo/", wait_until="domcontentloaded", timeout=60000)
        print("[FINGERPRINT] Page loaded, waiting 20s...")
        await sleep(20)

        ss = os.path.join(fp_dir, "fingerprint.png")
        try:
            await page.screenshot(path=ss, full_page=True, timeout=30000)
            print(f"[FINGERPRINT] Screenshot: {ss}")
        except Exception as e:
            print(f"[FINGERPRINT] Screenshot failed: {e}")

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

            print(f"\n[FINGERPRINT] Visitor ID: {data.get('visitorId', '')}")
            print(f"[FINGERPRINT] Bot Status: {data.get('botStatus', '')}")

            if data.get("tables"):
                for i, table in enumerate(data["tables"]):
                    print(f"\n[FINGERPRINT] Table {i + 1}:")
                    for row in table[:10]:
                        print(f"  {' | '.join(str(c) for c in row)}")
        except Exception as e:
            print(f"[FINGERPRINT] Data extraction failed: {e}")
            data = {"error": str(e)}

        with open(os.path.join(fp_dir, "report.json"), "w") as f:
            json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "total_time_s": round(time.monotonic() - t_start, 1), "data": data}, f, indent=2, default=str)

    print(f"[FINGERPRINT] Done in {time.monotonic() - t_start:.1f}s")
    return {"site": "fingerprint", "success": True, "time": time.monotonic() - t_start}

async def main():
    setup_logging(True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print("=" * 60)
    print("  PARALLEL TEST: todetect.net + fingerprint.com (2GB RAM)")
    print("=" * 60)

    # Run both tests in parallel
    results = await asyncio.gather(
        _probe_todetect(),
        _probe_fingerprint(),
        return_exceptions=True
    )

    print("\n" + "=" * 60)
    print("RESULTS:")
    for r in results:
        if isinstance(r, Exception):
            print(f"  [FAIL] Error: {r}")
        else:
            print(f"  [OK] {r['site']}: {r['time']:.1f}s")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
