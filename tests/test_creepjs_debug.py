"""Debug CreepJS stealth detection on redroid - capture full page details."""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from damru import DamruPool
from damru.utils import setup_logging, sleep

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"


async def main():
    setup_logging(True)

    async with DamruPool(
        mode="auto",
        max_devices=1,
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as pool:
        async with pool.session() as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            print("\n--- Navigating to CreepJS ---")
            await page.goto(
                "https://abrahamjuliot.github.io/creepjs/",
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print("Waiting 35s for CreepJS to finish analysis...")
            await sleep(35)

            # Take full-page screenshot
            ss_dir = os.path.join(os.path.dirname(__file__), "results", "redroid_debug")
            os.makedirs(ss_dir, exist_ok=True)
            await page.screenshot(
                path=os.path.join(ss_dir, "creepjs_full.png"),
                full_page=True,
                timeout=15000,
            )
            print(f"Full-page screenshot saved")

            # Extract the FULL page text to find stealth indicators
            full_text = await page.evaluate("""() => {
                return document.body.innerText;
            }""")

            with open(os.path.join(ss_dir, "creepjs_text.txt"), "w", encoding="utf-8") as f:
                f.write(full_text)
            print(f"Full text saved to creepjs_text.txt")

            # Extract specific sections related to stealth/headless/lies
            details = await page.evaluate("""() => {
                const text = document.body.innerText;
                const result = {};

                // Find headless/stealth/lies section
                const headlessMatch = text.match(/(\\d+)%\\s*headless/i);
                const stealthMatch = text.match(/(\\d+)%\\s*stealth/i);
                const likeHeadlessMatch = text.match(/(\\d+)%\\s*like headless/i);
                const liesMatch = text.match(/lies[:\\s]*(\\d+)/i);
                const trashMatch = text.match(/trash[:\\s]*(\\d+)/i);

                result.headless = headlessMatch  headlessMatch[0] : 'N/A';
                result.stealth = stealthMatch  stealthMatch[0] : 'N/A';
                result.likeHeadless = likeHeadlessMatch  likeHeadlessMatch[0] : 'N/A';
                result.lies = liesMatch  liesMatch[0] : 'N/A';
                result.trash = trashMatch  trashMatch[0] : 'N/A';

                // Get all red/warning elements
                const allElements = document.querySelectorAll('*');
                const warnings = [];
                for (const el of allElements) {
                    const style = getComputedStyle(el);
                    const text = el.textContent.trim();
                    if ((style.color === 'rgb(255, 0, 0)' || style.color === 'red' ||
                         style.backgroundColor === 'rgb(255, 0, 0)') && text.length < 200) {
                        warnings.push(text.substring(0, 150));
                    }
                }
                result.redElements = [...new Set(warnings)].slice(0, 30);

                // Find "bot" related text
                const botSection = text.match(/bot.*(=\\n\\n)/gis);
                result.botSections = botSection  botSection.map(s => s.substring(0, 200)) : [];

                // Find "stealth" related text with context
                const stealthSections = [];
                const lines = text.split('\\n');
                for (let i = 0; i < lines.length; i++) {
                    if (lines[i].toLowerCase().includes('stealth') ||
                        lines[i].toLowerCase().includes('resist') ||
                        lines[i].toLowerCase().includes('privacy')) {
                        const context = lines.slice(Math.max(0, i-2), i+3).join(' | ');
                        stealthSections.push(context.substring(0, 300));
                    }
                }
                result.stealthContext = stealthSections.slice(0, 20);

                return result;
            }""")

            print("\n=== CreepJS Debug Output ===")
            print(json.dumps(details, indent=2))

            # Also check specific things CreepJS might flag
            browser_checks = await page.evaluate("""() => {
                return {
                    webdriver: navigator.webdriver,
                    plugins_length: navigator.plugins.length,
                    plugins_type: Object.prototype.toString.call(navigator.plugins),
                    languages: navigator.languages,
                    platform: navigator.platform,
                    deviceMemory: navigator.deviceMemory,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    maxTouchPoints: navigator.maxTouchPoints,
                    connection: navigator.connection  {
                        effectiveType: navigator.connection.effectiveType,
                        rtt: navigator.connection.rtt,
                        downlink: navigator.connection.downlink,
                    } : null,
                    mediaDevices: await navigator.mediaDevices.enumerateDevices()
                        .then(d => d.map(dev => ({kind: dev.kind, label: dev.label})))
                        .catch(() => 'error'),
                    permissions_notification: await navigator.permissions.query({name: 'notifications'})
                        .then(p => p.state).catch(() => 'error'),
                    screen: {
                        width: screen.width,
                        height: screen.height,
                        colorDepth: screen.colorDepth,
                        pixelDepth: screen.pixelDepth,
                        availWidth: screen.availWidth,
                        availHeight: screen.availHeight,
                    },
                    webgl_renderer: (() => {
                        try {
                            const c = document.createElement('canvas');
                            const gl = c.getContext('webgl');
                            const ext = gl.getExtension('WEBGL_debug_renderer_info');
                            return {
                                vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
                                renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
                            };
                        } catch(e) { return 'error: ' + e.message; }
                    })(),
                };
            }""")

            print("\n=== Browser Checks ===")
            print(json.dumps(browser_checks, indent=2, default=str))

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
