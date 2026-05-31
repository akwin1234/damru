"""Benchmark damru auto mode (redroid container) against anti-detect sites.

Tests: BrowserScan, CreepJS, Sannysoft, Cloudflare.
"""
import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from damru import DamruPool
from damru.benchmark import TESTS, TestResult, _format_summary
from damru.utils import logger, setup_logging, sleep

# Replace with your proxy to test geo-stealth, else use None
PH_SOCKS5 = None
PH_HTTP = None
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "results", "redroid_screenshots")


async def main():
    setup_logging(True)

    print("=" * 60)
    print("  damru Benchmark — redroid auto mode")
    print("=" * 60)

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    async with DamruPool(
        mode="auto",
        max_devices=1,
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as pool:
        print(f"\n  Pool ready: {pool.device_count} device(s)")

        async with pool.session() as ctx:
            pages = ctx.pages
            page = pages[0] if pages else await ctx.new_page()

            results = []

            for test_cfg in TESTS:
                name = test_cfg["name"]
                result = TestResult(name=name)
                t0 = time.monotonic()

                print(f"\n{'='*40}")
                print(f"  TEST: {name}")
                print(f"  URL:  {test_cfg['url']}")
                print(f"{'='*40}")

                try:
                    # Navigation with retry
                    for attempt in range(3):
                        try:
                            await page.goto(
                                test_cfg["url"],
                                wait_until="domcontentloaded",
                                timeout=30000,
                            )
                            break
                        except Exception as nav_err:
                            if attempt < 2:
                                logger.warning("  Retry %d: %s", attempt + 1, str(nav_err)[:100])
                                try:
                                    await page.goto("about:blank", timeout=5000)
                                except Exception:
                                    pass
                                await sleep(3)
                            else:
                                raise

                    # Wait for page to settle
                    wait_s = test_cfg["wait_ms"] / 1000
                    print(f"  Waiting {wait_s}s for results...")
                    await sleep(wait_s)

                    # Screenshot
                    ss_path = os.path.join(SCREENSHOTS_DIR, f"{name.lower()}.png")
                    try:
                        await page.screenshot(path=ss_path, timeout=10000)
                        print(f"  Screenshot: {ss_path}")
                    except Exception as e:
                        logger.debug("Screenshot failed: %s", e)

                    # Extract results
                    data = await test_cfg["extract"](page)
                    result.data = data
                    result.status = "OK"
                    print(f"  Result: {json.dumps(data, indent=4)}")

                except Exception as e:
                    result.status = "ERROR"
                    result.error = str(e)
                    print(f"  ERROR: {e}")

                    # Recover page
                    try:
                        await page.evaluate("window.stop()")
                    except Exception:
                        pass
                    try:
                        await page.goto("about:blank", timeout=5000)
                    except Exception:
                        try:
                            page = await ctx.new_page()
                        except Exception:
                            pass

                result.duration_s = round(time.monotonic() - t0, 1)
                results.append(result)

            # Print summary
            print(_format_summary(results))

            # Save JSON
            report = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "mode": "auto (redroid)",
                "proxy": PH_SOCKS5,
                "results": [
                    {
                        "name": r.name,
                        "status": r.status,
                        "data": r.data,
                        "duration_s": r.duration_s,
                        "error": r.error,
                    }
                    for r in results
                ],
            }
            out_path = os.path.join(os.path.dirname(__file__), "results", "benchmark_redroid.json")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\nResults saved to: {out_path}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
