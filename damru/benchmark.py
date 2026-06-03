"""Built-in benchmark suite for damru.

Tests: CreepJS, BrowserScan, Sannysoft, Cloudflare.
Runs via the full Damru pipeline (ADB + root + CDP) and evaluates
anti-detect effectiveness.

Usage:
    python -m damru benchmark --device pixel_8_pro --proxy socks5://host:port
    python -m damru benchmark --device random --debug
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import Page

from .async_core import AsyncDamru
from .utils import logger, setup_logging, sleep


# ── Test definitions ─────────────────────────────────────────────

@dataclass
class TestResult:
    """Result of a single benchmark test."""
    name: str
    status: str = "PENDING"  # OK, FAIL, ERROR, SKIP
    data: Dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0
    error: str = ""


async def _extract_creepjs(page: Page) -> Dict[str, Any]:
    """Extract CreepJS fingerprint results."""
    try:
        await page.wait_for_selector(".visitor-info", timeout=30000)
    except Exception:
        pass
    await sleep(5)  # Extra time for rendering
    return await page.evaluate("""() => {
        const all = document.body.innerText;
        const likeHeadlessMatch = all.match(/(\\d+)%\\s*like headless/i);
        const headlessMatch = all.match(/(\\d+)%\\s*headless:/i);
        const stealthMatch = all.match(/(\\d+)%\\s*stealth:/i);
        const liesMatch = all.match(/lies[:\\s]*(\\d+)/i);
        return {
            likeHeadless: likeHeadlessMatch  likeHeadlessMatch[1] + "%" : "N/A",
            headless: headlessMatch  headlessMatch[1] + "%" : "N/A",
            stealth: stealthMatch  stealthMatch[1] + "%" : "N/A",
            lies: liesMatch  liesMatch[1] : "N/A",
        };
    }""")


async def _extract_browserscan(page: Page) -> Dict[str, Any]:
    """Extract BrowserScan score."""
    try:
        await page.wait_for_selector(
            "[class*='score'], [class*='Score'], [class*='result']",
            timeout=20000,
        )
    except Exception:
        pass
    return await page.evaluate("""() => {
        const all = document.body.innerText;
        const scoreMatch = all.match(/(\\d+)\\s*%/);
        return {
            score: scoreMatch  scoreMatch[1] + "%" : "N/A",
        };
    }""")


async def _extract_sannysoft(page: Page) -> Dict[str, Any]:
    """Extract Sannysoft bot detection results."""
    return await page.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll("table tr"));
        let passed = 0, failed = 0;
        const failedTests = [];
        for (const row of rows) {
            const cells = row.querySelectorAll("td");
            if (cells.length >= 2) {
                const name = cells[0].textContent.trim();
                const lastCell = cells[cells.length - 1];
                const bg = getComputedStyle(lastCell).backgroundColor;
                const text = lastCell.textContent.trim().toLowerCase();
                const isPass = text.includes("passed") || text.includes("ok") || text === "" ||
                    bg.includes("144, 238") || bg.includes("0, 128") || bg.includes("152, 251");
                const isFail = text.includes("failed") || bg.includes("255, 0") || bg.includes("255, 99");
                if (isPass && name) passed++;
                else if (isFail && name) { failed++; failedTests.push(name); }
            }
        }
        return { passed, failed, total: passed + failed, failedTests };
    }""")


async def _extract_cloudflare(page: Page) -> Dict[str, Any]:
    """Check if Cloudflare challenge was bypassed."""
    title = await page.title()
    blocked = await page.evaluate("""() => {
        return document.body.innerText.includes("Just a moment") ||
               document.body.innerText.includes("Checking") ||
               !!document.querySelector("iframe[src*='challenges']");
    }""")
    return {
        "bypassed": not blocked and "just a moment" not in title.lower(),
        "title": title,
        "url": page.url,
    }


# Test configuration
TESTS = [
    {
        "name": "CreepJS",
        "url": "https://abrahamjuliot.github.io/creepjs/",
        "wait_ms": 25000,
        "extract": _extract_creepjs,
    },
    {
        "name": "BrowserScan",
        "url": "https://www.browserscan.net/",
        "wait_ms": 15000,
        "extract": _extract_browserscan,
    },
    {
        "name": "Sannysoft",
        "url": "https://bot.sannysoft.com/",
        "wait_ms": 8000,
        "extract": _extract_sannysoft,
    },
    {
        "name": "Cloudflare",
        "url": "https://nowsecure.nl/",
        "wait_ms": 15000,
        "extract": _extract_cloudflare,
    },
]


# ── Runner ───────────────────────────────────────────────────────

async def run_benchmark(
    device: Optional[str] = None,
    serial: Optional[str] = None,
    proxy: Optional[str] = None,
    timezone: Optional[str] = None,
    locale: Optional[str] = None,
    tests: Optional[List[str]] = None,
    screenshots_dir: Optional[str] = None,
    debug: bool = False,
) -> List[TestResult]:
    """Run the benchmark suite.

    Args:
        device: Device name or "random".
        serial: ADB serial (auto-detect if None).
        proxy: SOCKS5 proxy URL.
        timezone: IANA timezone.
        locale: BCP-47 locale.
        tests: List of test names to run (None = all).
        screenshots_dir: Directory for screenshots (None = skip).
        debug: Enable debug logging.

    Returns:
        List of TestResult objects.
    """
    # Filter tests
    selected = TESTS
    if tests:
        test_names = {t.lower() for t in tests}
        selected = [t for t in TESTS if t["name"].lower() in test_names]
        if not selected:
            logger.error("No matching tests found. Available: %s",
                         ", ".join(t["name"] for t in TESTS))
            return []

    if screenshots_dir:
        os.makedirs(screenshots_dir, exist_ok=True)

    results: List[TestResult] = []

    async with AsyncDamru(
        device=device,
        serial=serial,
        proxy=proxy,
        timezone=timezone,
        locale=locale,
        debug=debug,
    ) as context:
        # Get or create a page
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = await context.new_page()

        for test_cfg in selected:
            name = test_cfg["name"]
            result = TestResult(name=name)
            t0 = time.monotonic()

            print(f"\n--- {name} ---")
            print(f"  URL: {test_cfg['url']}")

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
                            logger.warning("Navigation retry %d: %s", attempt + 1, nav_err)
                            try:
                                await page.goto("about:blank", timeout=5000)
                            except Exception:
                                pass
                            await sleep(2)
                        else:
                            raise

                # Wait for page to settle
                wait_s = test_cfg["wait_ms"] / 1000
                print(f"  Waiting {wait_s}s...")
                await sleep(wait_s)

                # Screenshot (best effort)
                if screenshots_dir:
                    ss_path = os.path.join(screenshots_dir, f"{name.lower()}.png")
                    try:
                        await page.screenshot(path=ss_path, timeout=5000)
                        print(f"  Screenshot: {ss_path}")
                    except Exception:
                        logger.debug("Screenshot failed for %s", name)

                # Extract results
                data = await test_cfg["extract"](page)
                result.data = data
                result.status = "OK"
                print(f"  Result: {json.dumps(data, indent=4)}")

            except Exception as e:
                result.status = "ERROR"
                result.error = str(e)
                print(f"  ERROR: {e}")

                # Try to recover page for next test
                try:
                    await page.evaluate("window.stop()")
                except Exception:
                    pass
                try:
                    await page.goto("about:blank", timeout=5000)
                except Exception:
                    try:
                        page = await context.new_page()
                    except Exception:
                        pass

            result.duration_s = round(time.monotonic() - t0, 1)
            results.append(result)

    return results


def _format_summary(results: List[TestResult]) -> str:
    """Format a human-readable summary of results."""
    lines = ["\n=== Benchmark Summary ===\n"]

    for r in results:
        status_icon = {
            "OK": "PASS",
            "FAIL": "FAIL",
            "ERROR": "ERR ",
            "SKIP": "SKIP",
            "PENDING": "- ",
        }.get(r.status, "-")

        detail = ""
        if r.status == "OK":
            d = r.data
            if r.name == "CreepJS":
                detail = f"headless={d.get('headless','')}, stealth={d.get('stealth','')}, likeHeadless={d.get('likeHeadless','')}, lies={d.get('lies','')}"
            elif r.name == "BrowserScan":
                detail = f"score={d.get('score','')}"
            elif r.name == "Sannysoft":
                detail = f"{d.get('passed','')}/{d.get('total','')} passed"
                if d.get("failedTests"):
                    detail += f" (failed: {', '.join(d['failedTests'])})"
            elif r.name in ("Cloudflare"):
                bypassed = d.get("bypassed", False)
                detail = "BYPASSED" if bypassed else "BLOCKED"
        elif r.status == "ERROR":
            detail = r.error[:80]

        lines.append(f"  [{status_icon}] {r.name}: {detail}  ({r.duration_s}s)")

    ok_count = sum(1 for r in results if r.status == "OK")
    lines.append(f"\n  Total: {ok_count}/{len(results)} OK")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    """CLI entry point for damru benchmark."""
    parser = argparse.ArgumentParser(
        prog="damru-benchmark",
        description="Damru anti-detect benchmark suite",
    )
    parser.add_argument(
        "--device", "-d",
        default=None,
        help="Device name (e.g. pixel_8_pro, samsung_s24_ultra) or 'random'",
    )
    parser.add_argument(
        "--serial", "-s",
        default=None,
        help="ADB serial (auto-detect if omitted)",
    )
    parser.add_argument(
        "--proxy", "-p",
        default=None,
        help="SOCKS5 proxy URL (e.g. socks5://host:port)",
    )
    parser.add_argument(
        "--timezone",
        default=None,
        help="IANA timezone (auto from proxy if omitted)",
    )
    parser.add_argument(
        "--locale",
        default=None,
        help="BCP-47 locale (auto from timezone if omitted)",
    )
    parser.add_argument(
        "--tests", "-t",
        nargs="*",
        default=None,
        help="Specific tests to run (e.g. creepjs browserscan)",
    )
    parser.add_argument(
        "--screenshots",
        default=None,
        help="Directory for screenshots (skip if omitted)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Path for JSON results file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args(argv)
    setup_logging(args.debug)

    print("=== damru Benchmark Suite ===\n")
    print(f"  Device:   {args.device or 'random'}")
    print(f"  Serial:   {args.serial or 'auto-detect'}")
    print(f"  Proxy:    {args.proxy or 'none'}")
    print(f"  Timezone: {args.timezone or 'auto'}")
    print(f"  Tests:    {', '.join(args.tests) if args.tests else 'all'}")
    print()

    results = asyncio.run(run_benchmark(
        device=args.device,
        serial=args.serial,
        proxy=args.proxy,
        timezone=args.timezone,
        locale=args.locale,
        tests=args.tests,
        screenshots_dir=args.screenshots,
        debug=args.debug,
    ))

    # Print summary
    print(_format_summary(results))

    # Save JSON results
    if args.output:
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "device": args.device,
            "proxy": args.proxy,
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
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2))
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
