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
    return await page.evaluate(r"""() => {
        const all = document.body.innerText;
        const likeHeadlessMatch = all.match(/(\\d+)%\\s*like headless/i);
        const headlessMatch = all.match(/(\\d+)%\\s*headless:/i);
        const stealthMatch = all.match(/(\\d+)%\\s*stealth:/i);
        const liesMatch = all.match(/lies[:\\s]*(\\d+)/i);
        const webrtcMatch = all.match(/WebRTC[\\s\\S]*?(host connection:[\\s\\S]*?)(?:Timezone|Intl|Headless)/i);
        const webrtcText = webrtcMatch ? webrtcMatch[1].trim() : "";
        const webrtcBlocked = /blocked/i.test(webrtcText) && !/(\\d{1,3}\\.){3}\\d{1,3}/.test(webrtcText);
        return {
            likeHeadless: likeHeadlessMatch ? likeHeadlessMatch[1] + "%" : "N/A",
            headless: headlessMatch ? headlessMatch[1] + "%" : "N/A",
            stealth: stealthMatch ? stealthMatch[1] + "%" : "N/A",
            lies: liesMatch ? liesMatch[1] : "N/A",
            webrtcBlocked,
        };
    }""")


async def _extract_browserscan(page: Page) -> Dict[str, Any]:
    """Extract BrowserScan score."""
    last_error = None
    for _ in range(4):
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            try:
                await page.wait_for_selector(
                    "[class*='score'], [class*='Score'], [class*='result']",
                    timeout=8000,
                )
            except Exception:
                pass
            return await page.evaluate(r"""() => {
                const all = document.body.innerText;
                const lines = all.split("\n").map(x => x.trim()).filter(Boolean);
                let score = "N/A";
                const botIndex = lines.findIndex(x => /^Bot Detection:?$/i.test(x));
                if (botIndex >= 0) {
                    for (const line of lines.slice(botIndex + 1, botIndex + 8)) {
                        const m = line.match(/^(\d+)\s*%$/);
                        if (m) { score = m[1] + "%"; break; }
                    }
                }
                if (score === "N/A") {
                    const scoreMatch = all.match(/(\\d+)\\s*%/);
                    score = scoreMatch ? scoreMatch[1] + "%" : "N/A";
                }
                const issues = [];
                for (let i = 0; i < lines.length; i++) {
                    if (/^-\d+\s*%$/.test(lines[i])) {
                        issues.push({name: lines[i - 1] || "", penalty: lines[i], detail: lines[i + 1] || ""});
                    }
                }
                return {
                    score,
                    issues,
                };
            }""")
        except Exception as exc:
            last_error = exc
            await sleep(2)
    raise last_error or RuntimeError("BrowserScan extraction failed")


async def _extract_sannysoft(page: Page) -> Dict[str, Any]:
    """Extract Sannysoft bot detection results."""
    return await page.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll("table tr"));
        let passed = 0, failed = 0;
        const failedTests = [];
        const plugins = navigator.plugins;
        const mimeTypes = navigator.mimeTypes;
        const androidEmptyPluginArray =
            plugins &&
            plugins.length === 0 &&
            Object.prototype.toString.call(plugins) === "[object PluginArray]" &&
            (typeof PluginArray === "undefined" || plugins instanceof PluginArray) &&
            mimeTypes &&
            mimeTypes.length === 0 &&
            Object.prototype.toString.call(mimeTypes) === "[object MimeTypeArray]" &&
            (typeof MimeTypeArray === "undefined" || mimeTypes instanceof MimeTypeArray);
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
                const sannysoftOldPluginFalseFail =
                    name === "Plugins is of type PluginArray" && androidEmptyPluginArray;
                if ((isPass || sannysoftOldPluginFalseFail) && name) passed++;
                else if (isFail && name) { failed++; failedTests.push(name); }
            }
        }
        return {
            passed,
            failed,
            total: passed + failed,
            failedTests,
            pluginCheck: {
                length: plugins ? plugins.length : null,
                type: Object.prototype.toString.call(plugins),
                mimeLength: mimeTypes ? mimeTypes.length : null,
                mimeType: Object.prototype.toString.call(mimeTypes),
                androidEmptyPluginArray,
            },
        };
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

    damru = AsyncDamru(
        device=device,
        serial=serial,
        proxy=proxy,
        timezone=timezone,
        locale=locale,
        debug=debug,
    )
    async with damru as context:
        # Use a fresh tab for proof targets. The startup tab can retain stale
        # network state after Redroid root/GPU/SurfaceFlinger setup.
        page = await context.new_page()
        for stale in list(context.pages):
            if stale is page:
                continue
            try:
                await stale.close()
            except Exception:
                pass

        await damru._repair_wsl_network_if_needed()

        # Android Chrome can report ERR_INTERNET_DISCONNECTED on the first
        # post-setup navigation while connectivity services settle after root,
        # route, and SurfaceFlinger changes. Warm up with a tiny stable page so
        # proof targets measure the browser, not the first network tick.
        for attempt in range(3):
            try:
                await damru._repair_wsl_network_if_needed()
                await page.goto(
                    "https://example.com/",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                await page.goto("about:blank", wait_until="load", timeout=5000)
                break
            except Exception as exc:
                if attempt == 2:
                    logger.debug("Benchmark warm-up navigation skipped: %s", exc)
                await sleep(2)

        try:
            await page.close()
        except Exception:
            pass

        for test_cfg in selected:
            page = await context.new_page()
            name = test_cfg["name"]
            result = TestResult(name=name)
            t0 = time.monotonic()

            print(f"\n--- {name} ---")
            print(f"  URL: {test_cfg['url']}")

            try:
                # Navigation with retry
                for attempt in range(3):
                    try:
                        await damru._repair_wsl_network_if_needed()
                        await page.goto(
                            test_cfg["url"],
                            wait_until="domcontentloaded",
                            timeout=30000,
                        )
                        break
                    except Exception as nav_err:
                        try:
                            await page.evaluate("url => { window.location.href = url; }", test_cfg["url"])
                            await page.wait_for_load_state("domcontentloaded", timeout=30000)
                            break
                        except Exception:
                            pass
                        try:
                            if damru._chrome:
                                await damru._chrome.launch(test_cfg["url"], startup_delay=5.0)
                                await sleep(3)
                                if context.pages:
                                    page = context.pages[-1]
                                if test_cfg["url"].split("/", 3)[2] in page.url:
                                    break
                        except Exception:
                            pass
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
            try:
                await page.close()
            except Exception:
                pass

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

def main(argv: list[str] | None = None) -> int:
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

    return 0 if results and all(r.status == "OK" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
