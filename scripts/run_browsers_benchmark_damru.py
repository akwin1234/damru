"""Run techinz/browsers-benchmark with Damru Redroid.

Usage:
  1. Clone https://github.com/techinz/browsers-benchmark
  2. From that clone, run this script with Damru on PYTHONPATH, or set
     DAMRU_REPO to a local Damru checkout.

Environment:
  DAMRU_REPO           Optional path to the Damru repo.
  DAMRU_BENCH_PROXY    Optional HTTP/SOCKS proxy URL. Do not commit it.
  DAMRU_BENCH_DEVICE   Optional Damru device profile, e.g. Samsung Galaxy S23.
  DAMRU_BENCH_ONLY     Optional comma-separated target names.
  DAMRU_BENCH_SKIP     Optional comma-separated target names.
  DAMRU_BENCH_OUT      Optional output directory.

reCAPTCHA is intentionally skipped by default. It was tested manually through
the Damru UI with a residential proxy; benchmark automation is too sensitive to
proxy reputation and Google-side refresh/rate limits for a stable code result.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

BENCH_DIR = Path.cwd()
DAMRU_DIR = os.environ.get("DAMRU_REPO")
if DAMRU_DIR:
    sys.path.insert(0, str(Path(DAMRU_DIR).resolve()))
sys.path.insert(0, str(BENCH_DIR))

from config.benchmark_targets import benchmark_targets_config  # type: ignore  # noqa: E402
from engines.base import BrowserEngine, NavigationResult  # type: ignore  # noqa: E402
from damru import DamruPool  # noqa: E402


class DamruBenchmarkEngine(BrowserEngine):
    def __init__(self, proxy_url: str | None = None):
        super().__init__(name="damru-redroid", proxy=None)
        self.proxy_url = proxy_url
        self.device = os.environ.get("DAMRU_BENCH_DEVICE") or None
        self.pool = None
        self.session_cm = None
        self.context = None
        self.page = None
        self.last_url = "about:blank"

    @property
    def supported_proxy_protocols(self):
        return ["http", "socks5"]

    async def start(self):
        self._start_time = time.time()
        self.pool = DamruPool(mode="auto", max_devices=1, proxy=self.proxy_url, debug=False)
        await self.pool.__aenter__()
        await self.start_session()

    async def start_session(self):
        self.session_cm = self.pool.session(device=self.device, proxy=self.proxy_url, task_timeout=None)
        self.context = await self.session_cm.__aenter__()
        self.page = await self.context.new_page()
        self.page.set_default_timeout(30000)
        self.page.set_default_navigation_timeout(90000)

    async def stop_session(self):
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
        if self.session_cm:
            try:
                await self.session_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self.session_cm = None
        self.page = None

    async def restart_session(self):
        await self.stop_session()
        await self.start_session()

    async def stop(self):
        await self.stop_session()
        if self.pool:
            try:
                await self.pool.__aexit__(None, None, None)
            except Exception:
                pass

    async def navigate(self, url: str) -> NavigationResult:
        start = time.time()
        response = None
        headers = {}
        success = False
        for attempt in range(4):
            try:
                await self.page.goto("about:blank", wait_until="load", timeout=10000)
                response = await self.page.goto(url, wait_until="domcontentloaded", timeout=90000)
                if self.page.url.startswith("chrome-error://"):
                    raise RuntimeError("chrome-error navigation")
                success = response is None or response.ok
                if response is not None:
                    headers = await response.all_headers()
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                break
            except Exception:
                if attempt == 3:
                    raise
                await asyncio.sleep(2 + attempt * 2)
        self.last_url = self.page.url
        return {"url": self.page.url, "load_time": time.time() - start, "success": success, "headers": headers}

    async def reload_page(self) -> NavigationResult:
        return await self.navigate(self.last_url or self.page.url)

    async def locator(self, css_selector: str):
        loc = self.page.locator(css_selector)
        try:
            count = await loc.count()
            if count <= 0:
                return False, ""
            html = await loc.first.inner_html(timeout=5000)
            return True, html
        except Exception:
            return False, ""

    async def get_page_content(self) -> str:
        return await self.page.content()

    async def execute_js(self, script: str):
        try:
            return await self.page.evaluate(script)
        except Exception as exc:
            if "Illegal return statement" not in str(exc):
                raise
            return await self.page.evaluate(f"(() => {{\n{script}\n}})()")

    async def screenshot(self, path: str) -> None:
        await self.page.screenshot(path=path, full_page=True)


async def main():
    proxy = os.environ.get("DAMRU_BENCH_PROXY") or None
    only = {x.strip() for x in os.environ.get("DAMRU_BENCH_ONLY", "").split(",") if x.strip()}
    skip = {x.strip() for x in os.environ.get("DAMRU_BENCH_SKIP", "").split(",") if x.strip()}
    skip.add("recaptcha_score")

    out_dir = Path(os.environ.get("DAMRU_BENCH_OUT", str(BENCH_DIR / "results" / "damru-redroid-run")))
    shot_dir = out_dir / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)

    engine = DamruBenchmarkEngine(proxy_url=proxy)
    results = {"bypass": [], "browser_data": [], "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        await engine.start()
        for target in benchmark_targets_config.bypass_targets.targets:
            if target.name in skip or (only and target.name not in only):
                continue
            if len(results["bypass"]) and len(results["bypass"]) % 5 == 0:
                await engine.restart_session()
            item = {"target": target.name, "url": target.url, "bypass": False, "error": None}
            for attempt in range(2):
                try:
                    nav = await engine.navigate(target.url)
                    await asyncio.sleep(5)
                    checker = benchmark_targets_config.bypass_targets.checkers[target.check_function]
                    item["bypass"] = bool(await checker(engine))
                    if target.name == "google_search" and not item["bypass"]:
                        html = (await engine.get_page_content()).lower()
                        item["bypass"] = "what is my user agent" in html and "sorry/index" not in engine.page.url.lower()
                    item["final_url"] = nav["url"]
                    item["error"] = None
                    if not item["bypass"] and attempt == 0:
                        await engine.restart_session()
                        continue
                    break
                except Exception as exc:
                    item["error"] = str(exc)
                    if attempt == 0:
                        await engine.restart_session()
                        continue
                    break
            try:
                await engine.screenshot(str(shot_dir / f"{target.name}.png"))
            except Exception:
                pass
            print(json.dumps({"kind": "bypass", **item}), flush=True)
            results["bypass"].append(item)
            await asyncio.sleep(1)

        for target in benchmark_targets_config.browser_data_targets.targets:
            if target.name in skip or (only and target.name not in only):
                continue
            item = {"target": target.name, "url": target.url, "error": None}
            try:
                await engine.navigate(target.url)
                await asyncio.sleep(5)
                checker = benchmark_targets_config.browser_data_targets.checkers[target.check_function]
                item.update(await checker(engine))
            except Exception as exc:
                item["error"] = str(exc)
            try:
                await engine.screenshot(str(shot_dir / f"{target.name}.png"))
            except Exception:
                pass
            print(json.dumps({"kind": "browser_data", **item}), flush=True)
            results["browser_data"].append(item)
            await asyncio.sleep(1)
    finally:
        await engine.stop()

    passed = sum(1 for x in results["bypass"] if x.get("bypass") and not x.get("error"))
    total = len(results["bypass"])
    results["bypass_rate"] = round((passed / total) * 100, 2) if total else 0
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"kind": "summary", "passed": passed, "total": total, "bypass_rate": results["bypass_rate"], "result_json": str(out_dir / "result.json")}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
