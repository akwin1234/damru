#!/usr/bin/env python3
"""Quick check of WebGL GPU renderer via CDP."""
import asyncio
from playwright.async_api import async_playwright

JS_CHECK = """() => {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
    if (!gl) return {error: 'no webgl'};
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    if (!ext) return {error: 'no debug info'};
    return {
        renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
        vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
        version: gl.getParameter(gl.VERSION),
    };
}"""

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
        ctx = browser.contexts[0]
        page = ctx.pages[0]
        await page.goto('about:blank')
        result = await page.evaluate(JS_CHECK)
        print('WebGL GPU Info:')
        for k, v in result.items():
            print(f'  {k}: {v}')
        await browser.close()

asyncio.run(main())
