"""Capture full CreepJS report from a real phone via ADB + CDP."""
import asyncio
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright


SERIAL = "RZCX92121CK"
LOCAL_PORT = 9223
SOCKET_NAME = "chrome_devtools_remote_32426"


async def goto_retry(page, url, retries=8, timeout=60000):
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return True
        except Exception as e:
            err = str(e).split("\n")[0][:80]
            if attempt < retries:
                print(f"  Retry {attempt}/{retries}: {err}")
                await asyncio.sleep(3)
            else:
                raise


async def main():
    # ADB forward
    subprocess.run(["adb", "-s", SERIAL, "forward", f"tcp:{LOCAL_PORT}",
                     f"localabstract:{SOCKET_NAME}"], check=True)
    print(f"Forwarded port {LOCAL_PORT} to Chrome devtools")

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{LOCAL_PORT}")
        context = browser.contexts[0]

        # Find the CreepJS page or use first available
        page = None
        for p in context.pages:
            if "creepjs" in (p.url or ""):
                page = p
                break
        if not page:
            page = context.pages[0] if context.pages else await context.new_page()
            print("Navigating to CreepJS...")
            await goto_retry(page, "https://abrahamjuliot.github.io/creepjs/")

        print(f"On page: {page.url}")
        # If already on CreepJS, it may have finished — short wait
        if "creepjs" in (page.url or ""):
            print("Already on CreepJS, waiting 15s for completion...")
            await asyncio.sleep(15)
        else:
            print("Waiting 45s for CreepJS analysis...")
            await asyncio.sleep(45)

        # Capture main page
        main_text = await page.evaluate("() => document.body.innerText")

        # Find sub-page links at bottom of CreepJS
        sub_links = await page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href;
                const text = a.textContent.trim();
                if (href.includes('creepjs') && href !== window.location.href && text.length > 0) {
                    links.push({href, text});
                }
            });
            return links;
        }""")
        print(f"Found {len(sub_links)} sub-page links")

        # Capture each sub-page
        sub_pages = {}
        for link in sub_links:
            href = link["href"]
            text = link["text"]
            try:
                print(f"  Capturing: {text} ({href.split('/')[-1]})...")
                await goto_retry(page, href, retries=3, timeout=30000)
                await asyncio.sleep(8)
                content = await page.evaluate("() => document.body.innerText")
                sub_pages[text] = content
            except Exception as e:
                sub_pages[text] = f"ERROR: {e}"

        # Build markdown
        md = []
        md.append("# CreepJS Report — Real Samsung Galaxy S23 FE (SM-S711B)")
        md.append(f"- **Device**: Samsung SM-S711B (Galaxy S23 FE)")
        md.append(f"- **Android**: 16")
        md.append(f"- **Chrome**: 144.0.7559.132")
        md.append(f"- **Date**: 2026-02-16")
        md.append(f"- **Connection**: USB (no proxy)")
        md.append("")
        md.append("## Main Page")
        md.append("```")
        md.append(main_text)
        md.append("```")

        for title, content in sub_pages.items():
            md.append("")
            md.append(f"## {title}")
            md.append("```")
            md.append(content)
            md.append("```")

        # Save
        out_path = os.path.join(os.path.dirname(__file__), "results", "real_samsung_creepjs.md")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))

        print(f"\nSaved to {out_path}")

        # Cleanup
        await browser.close()
        subprocess.run(["adb", "-s", SERIAL, "forward", "--remove",
                         f"tcp:{LOCAL_PORT}"], check=False)

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
