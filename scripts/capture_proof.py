"""Capture sanitized Damru proof screenshots.

Proxy credentials are never stored in this file. Pass runtime values with
DAMRU_PROXY and, when Android needs an HTTP CONNECT bridge, DAMRU_HTTP_PROXY.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from damru import AsyncDamru


TARGETS = [
    ("example", "Example.com", "https://example.com/", 5),
    ("amazon", "Amazon", "https://www.amazon.com/", 12),
    ("datadome-footlocker", "DataDome target", "https://www.footlocker.com/", 14),
    ("fingerprint-pro", "Fingerprint Pro demo", "https://demo.fingerprint.com/playground", 16),
    ("sannysoft", "Sannysoft", "https://bot.sannysoft.com/", 10),
    ("creepjs", "CreepJS", "https://abrahamjuliot.github.io/creepjs/", 22),
]

TARGET_SCROLL_TEXT = {
    "creepjs": "Headless",
    "fingerprint-pro": "SMART SIGNALS",
}

TARGET_ZOOM = {
    "fingerprint-pro": "0.62",
}


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", value.lower()).strip("-")


async def _snapshot(page, key: str, label: str, url: str, wait_seconds: int, out_dir: Path) -> dict[str, Any]:
    started = time.time()
    result: dict[str, Any] = {
        "key": key,
        "label": label,
        "url": url,
        "ok": False,
        "screenshot": f"{_safe_name(key)}.png",
    }

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(wait_seconds * 1000)
        scroll_text = TARGET_SCROLL_TEXT.get(key)
        if scroll_text:
            zoom = TARGET_ZOOM.get(key)
            if zoom:
                await page.evaluate("value => { document.documentElement.style.zoom = value; }", zoom)
                await page.wait_for_timeout(500)
            await page.evaluate(
                """needle => {
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    let node;
                    while ((node = walker.nextNode())) {
                        if ((node.nodeValue || '').includes(needle)) {
                            const el = node.parentElement;
                            if (el) el.scrollIntoView({ block: 'center', inline: 'nearest' });
                            break;
                        }
                    }
                }""",
                scroll_text,
            )
            await page.wait_for_timeout(1500)
        result["title"] = await page.title()
        result["final_url"] = page.url
        result["signals"] = await page.evaluate(
            """() => ({
                ua: navigator.userAgent,
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                maxTouchPoints: navigator.maxTouchPoints,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                language: navigator.language,
                viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
                bodyText: document.body  document.body.innerText.slice(0, 800) : ""
            })"""
        )
        await page.screenshot(path=str(out_dir / result["screenshot"]), full_page=False, scale="css")
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001 - proof runner must keep moving
        result["error"] = f"{type(exc).__name__}: {exc}"
        try:
            await page.screenshot(path=str(out_dir / result["screenshot"]), full_page=False, scale="css")
        except Exception:
            pass
    finally:
        result["elapsed_seconds"] = round(time.time() - started, 2)

    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Damru proof screenshots")
    parser.add_argument("--out", default="docs/assets/proof/sites", help="output directory")
    parser.add_argument("--targets", default="all", help="comma-separated target keys or 'all'")
    parser.add_argument("--device", default=os.environ.get("DAMRU_DEVICE", "random"))
    parser.add_argument("--timezone", default=os.environ.get("DAMRU_TIMEZONE") or None)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = {x.strip() for x in args.targets.split(",") if x.strip()} if args.targets != "all" else None
    targets = [t for t in TARGETS if wanted is None or t[0] in wanted]

    proxy = os.environ.get("DAMRU_PROXY") or None
    http_proxy = os.environ.get("DAMRU_HTTP_PROXY") or None

    metadata: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "proxy_supplied": bool(proxy or http_proxy),
        "targets": [],
    }
    metadata_path = out_dir / "proof-sites.json"
    if metadata_path.exists():
        try:
            previous = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(previous.get("targets"), list):
                metadata["targets"] = previous["targets"]
        except (OSError, json.JSONDecodeError):
            pass

    async with AsyncDamru(
        device=args.device,
        proxy=proxy,
        http_proxy=http_proxy,
        timezone=args.timezone,
    ) as context:
        page = await context.new_page()
        for key, label, url, wait_seconds in targets:
            result = await _snapshot(page, key, label, url, wait_seconds, out_dir)
            metadata["targets"] = [t for t in metadata["targets"] if t.get("key") != key]
            metadata["targets"].append(result)

    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return 0 if any(t.get("ok") for t in metadata["targets"]) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
