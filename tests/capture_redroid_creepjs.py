"""Capture full CreepJS report from redroid via AsyncDamru pipeline (same as real phone capture)."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru
from damru.utils import setup_logging, sleep

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"


async def goto_retry(page, url, retries=8, timeout=60000):
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return True
        except Exception as e:
            err = str(e).split("\n")[0][:80]
            if attempt < retries:
                print(f"  Retry {attempt}/{retries}: {err}")
                await sleep(3)
            else:
                raise


async def main():
    setup_logging(debug=False)
    print("=" * 60)
    print("  CreepJS Full Capture - Redroid (AsyncDamru Pipeline)")
    print("=" * 60)

    async with AsyncDamru(
        device="Samsung Galaxy S23 FE",
        serial="localhost:5600",
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        debug=False,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to CreepJS
        print("Navigating to CreepJS...")
        await goto_retry(page, "https://abrahamjuliot.github.io/creepjs/",
                         retries=8, timeout=60000)
        print("Waiting 45s for CreepJS analysis...")
        await sleep(45)

        # Capture main page
        main_text = await page.evaluate("() => document.body.innerText")

        # Find sub-page links
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
                await goto_retry(page, href, retries=5, timeout=30000)
                await sleep(10)
                content = await page.evaluate("() => document.body.innerText")
                sub_pages[text] = content
            except Exception as e:
                sub_pages[text] = f"ERROR: {e}"

        # Build markdown
        md = []
        md.append("# CreepJS Report - Redroid (AsyncDamru Pipeline)")
        md.append(f"- **Platform**: Redroid 14, x86_64, Docker/WSL2")
        md.append(f"- **Proxy**: PH HTTP (proxy.example:50000)")
        md.append(f"- **Date**: 2026-02-16")
        md.append(f"- **Pipeline**: Full AsyncDamru (root + CDP + JS)")
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
        out_path = os.path.join(os.path.dirname(__file__), "results", "redroid_creepjs.md")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))

        print(f"\nSaved to {out_path}")

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
