"""Benchmark damru against CreepJS, todetect.net, and fingerprint.com/demo.

Uses existing running container (warm start) for speed.
Takes screenshots and extracts detection results.
"""
import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from damru import AsyncDamru
from damru.utils import sleep, setup_logging

PH_HTTP = "198.20.189.134:50000"
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "benchmark_sites")


async def test_creepjs(page):
    """Navigate to CreepJS and extract scores."""
    print("\n" + "=" * 60)
    print("  TEST 1: CreepJS")
    print("=" * 60)

    await page.goto(
        "https://abrahamjuliot.github.io/creepjs/",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    print("  Page loaded, waiting 30s for fingerprint analysis...")
    await sleep(30)

    # Take screenshot
    ss = os.path.join(RESULTS_DIR, "creepjs.png")
    try:
        await page.screenshot(path=ss, full_page=True, timeout=15000)
        print(f"  Screenshot: {ss}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")

    # Extract scores
    data = await page.evaluate("""() => {
        const all = document.body.innerText;
        const likeHeadlessMatch = all.match(/(\\d+)%\\s*like headless/i);
        const headlessMatch = all.match(/(\\d+)%\\s*headless:/i);
        const stealthMatch = all.match(/(\\d+)%\\s*stealth:/i);
        const liesMatch = all.match(/lies[:\\s]*(\\d+)/i);

        // Also get trust score and fingerprint ID
        const trustMatch = all.match(/trust\\s*score[:\\s]*(\\d+)/i);
        const fpMatch = all.match(/([a-f0-9]{16,})/i);

        return {
            likeHeadless: likeHeadlessMatch ? likeHeadlessMatch[1] + "%" : "N/A",
            headless: headlessMatch ? headlessMatch[1] + "%" : "N/A",
            stealth: stealthMatch ? stealthMatch[1] + "%" : "N/A",
            lies: liesMatch ? liesMatch[1] : "N/A",
            trustScore: trustMatch ? trustMatch[1] : "N/A",
        };
    }""")

    print(f"\n  Results:")
    print(f"    Headless:     {data.get('headless', '?')}")
    print(f"    Stealth:      {data.get('stealth', '?')}")
    print(f"    Like Headless: {data.get('likeHeadless', '?')}")
    print(f"    Lies:         {data.get('lies', '?')}")
    print(f"    Trust Score:  {data.get('trustScore', '?')}")
    return data


async def test_todetect(page):
    """Navigate to todetect.net and extract detection results."""
    print("\n" + "=" * 60)
    print("  TEST 2: todetect.net")
    print("=" * 60)

    await page.goto(
        "https://todetect.net/",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    print("  Page loaded, waiting 20s for analysis...")
    await sleep(20)

    # Take screenshot
    ss = os.path.join(RESULTS_DIR, "todetect.png")
    try:
        await page.screenshot(path=ss, full_page=True, timeout=15000)
        print(f"  Screenshot: {ss}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")

    # Extract results
    data = await page.evaluate(r"""() => {
        const all = document.body.innerText;
        const lines = all.split('\n').map(l => l.trim()).filter(l => l);

        // Look for overall score
        const scoreMatch = all.match(/(?:overall|total|score|result)[:\s]*(-?\d+)/i);
        const percentMatch = all.match(/(\d+)\s*%/);

        // Extract individual test results
        const tests = {};
        const testPatterns = [
            /timezone[:\s]*(.+)/i,
            /language[:\s]*(.+)/i,
            /webrtc[:\s]*(.+)/i,
            /dns[:\s]*(.+)/i,
            /ip[:\s]*(.+)/i,
            /canvas[:\s]*(.+)/i,
            /webgl[:\s]*(.+)/i,
            /audio[:\s]*(.+)/i,
            /font[:\s]*(.+)/i,
            /screen[:\s]*(.+)/i,
        ];

        for (const line of lines) {
            for (const pat of testPatterns) {
                const m = line.match(pat);
                if (m) {
                    const key = pat.source.split('[')[0].replace(/\\/g, '');
                    tests[key] = m[1].trim().substring(0, 100);
                }
            }
        }

        // Get all elements with status indicators
        const statusEls = document.querySelectorAll(
            '[class*="pass"], [class*="fail"], [class*="ok"], [class*="error"], ' +
            '[class*="good"], [class*="bad"], [class*="warn"], [class*="success"], ' +
            '[class*="danger"], [class*="positive"], [class*="negative"]'
        );
        const statuses = [];
        for (const el of statusEls) {
            const text = el.textContent.trim();
            if (text.length > 0 && text.length < 200) {
                statuses.push({
                    class: el.className.substring(0, 80),
                    text: text.substring(0, 150)
                });
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

        // Get visible score/result sections
        const sections = [];
        for (const el of document.querySelectorAll('h1, h2, h3, h4, [class*="score"], [class*="result"]')) {
            const t = el.textContent.trim();
            if (t.length > 0 && t.length < 200) sections.push(t);
        }

        return {
            score: scoreMatch ? scoreMatch[1] : percentMatch ? percentMatch[1] + "%" : "N/A",
            tests: tests,
            statuses: statuses.slice(0, 30),
            tables: tables.slice(0, 5),
            sections: sections.slice(0, 20),
            pageText: all.substring(0, 3000),
        };
    }""")

    print(f"\n  Overall Score: {data.get('score', '?')}")

    if data.get("tables"):
        for i, table in enumerate(data["tables"]):
            print(f"\n  Table {i + 1}:")
            for row in table[:15]:
                print(f"    {' | '.join(str(c) for c in row)}")

    if data.get("statuses"):
        print(f"\n  Status indicators ({len(data['statuses'])}):")
        seen = set()
        for s in data["statuses"][:20]:
            text = s["text"][:120]
            if text not in seen:
                seen.add(text)
                cls = s.get("class", "").lower()
                indicator = ""
                if any(x in cls for x in ("pass", "good", "success", "ok", "positive")):
                    indicator = " [OK]"
                elif any(x in cls for x in ("fail", "bad", "danger", "error", "negative")):
                    indicator = " [FAIL]"
                elif "warn" in cls:
                    indicator = " [WARN]"
                print(f"    {text}{indicator}")

    if data.get("sections"):
        print(f"\n  Sections:")
        for s in data["sections"]:
            print(f"    {s}")

    return data


async def test_fingerprint(page):
    """Navigate to fingerprint.com/demo and extract results."""
    print("\n" + "=" * 60)
    print("  TEST 3: fingerprint.com/demo")
    print("=" * 60)

    await page.goto(
        "https://fingerprint.com/demo/",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    print("  Page loaded, waiting 15s for fingerprint analysis...")
    await sleep(15)

    # Take screenshot
    ss = os.path.join(RESULTS_DIR, "fingerprint_demo.png")
    try:
        await page.screenshot(path=ss, full_page=True, timeout=15000)
        print(f"  Screenshot: {ss}")
    except Exception as e:
        print(f"  Screenshot failed: {e}")

    # Extract results
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

        // Get headings and sections
        const sections = [];
        for (const el of document.querySelectorAll('h1, h2, h3, h4, h5')) {
            sections.push(el.textContent.trim());
        }

        return {
            visitorId: visitorIdMatch ? visitorIdMatch[1] : "N/A",
            botDetected: botDetected && !notBot,
            botStatus: botMatch ? botMatch[1] : (notBot ? "not detected" : (botDetected ? "detected" : "N/A")),
            cards: [...new Set(cards)].slice(0, 30),
            tables: tables.slice(0, 5),
            sections: sections.slice(0, 15),
            pageText: all.substring(0, 3000),
        };
    }""")

    print(f"\n  Visitor ID:  {data.get('visitorId', '?')}")
    print(f"  Bot Status:  {data.get('botStatus', '?')}")
    print(f"  Bot Detected: {data.get('botDetected', '?')}")

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

    return data


async def main():
    setup_logging(True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("=" * 60)
    print("  damru Benchmark — CreepJS + todetect.net + fingerprint.com")
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

        # Test 1: CreepJS
        try:
            results["creepjs"] = await test_creepjs(page)
        except Exception as e:
            print(f"  CreepJS ERROR: {e}")
            results["creepjs"] = {"error": str(e)}
            try:
                await page.goto("about:blank", timeout=5000)
            except Exception:
                page = await ctx.new_page()

        # Test 2: todetect.net
        try:
            results["todetect"] = await test_todetect(page)
        except Exception as e:
            print(f"  todetect.net ERROR: {e}")
            results["todetect"] = {"error": str(e)}
            try:
                await page.goto("about:blank", timeout=5000)
            except Exception:
                page = await ctx.new_page()

        # Test 3: fingerprint.com/demo
        try:
            results["fingerprint"] = await test_fingerprint(page)
        except Exception as e:
            print(f"  fingerprint.com ERROR: {e}")
            results["fingerprint"] = {"error": str(e)}

        # Save JSON report
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": "auto (redroid, baked image)",
            "proxy": PH_HTTP,
            "total_time_s": round(time.monotonic() - t_start, 1),
            "results": results,
        }
        out_path = os.path.join(RESULTS_DIR, "benchmark_report.json")
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        # Print summary
        print("\n" + "=" * 60)
        print("  BENCHMARK SUMMARY")
        print("=" * 60)
        print(f"  Total time: {report['total_time_s']}s")
        print()

        cr = results.get("creepjs", {})
        print(f"  CreepJS:")
        print(f"    Headless:      {cr.get('headless', '?')}")
        print(f"    Stealth:       {cr.get('stealth', '?')}")
        print(f"    Like Headless: {cr.get('likeHeadless', '?')}")
        print(f"    Lies:          {cr.get('lies', '?')}")

        td = results.get("todetect", {})
        print(f"\n  todetect.net:")
        print(f"    Score: {td.get('score', '?')}")

        fp = results.get("fingerprint", {})
        print(f"\n  fingerprint.com:")
        print(f"    Bot Status:  {fp.get('botStatus', '?')}")
        print(f"    Visitor ID:  {fp.get('visitorId', '?')}")

        print(f"\n  Screenshots: {RESULTS_DIR}")
        print(f"  Report: {out_path}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
