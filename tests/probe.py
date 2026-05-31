"""Quick diagnostic probe - tests GPU spoof, WebGL, todetect.net, BrowserScan."""
import sys, os, asyncio, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"

async def probe():
    print("Launching AsyncDamru...")
    async with AsyncDamru(
        device="random",
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to a real page first (chrome://newtab doesn't support WebGL)
        await page.goto("data:text/html,<h1>damru probe</h1>", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1)

        # 0. WebGL Renderer Check (direct JS)
        print("\n" + "="*60)
        print("  WebGL Renderer (JS Check)")
        print("="*60)
        try:
            gl_info = await page.evaluate("""() => {
                try {
                    const c = document.createElement('canvas');
                    const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
                    if (!gl) return {error: 'No WebGL'};
                    const ext = gl.getExtension('WEBGL_debug_renderer_info');
                    const exts = gl.getSupportedExtensions() || [];
                    const result = {
                        version: gl.getParameter(gl.VERSION),
                        shadingVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                        extensionCount: exts.length,
                        extensions: exts.join(', '),
                        hasBPTC: exts.includes('WEBGL_compressed_texture_bptc'),
                    };
                    if (ext) {
                        result.vendor = gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
                        result.renderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
                    } else {
                        result.error = 'No debug renderer info';
                    }
                    return result;
                } catch(e) { return {error: e.message}; }
            }""")
            print(f"  Vendor:     {gl_info.get('vendor', 'N/A')}")
            print(f"  Renderer:   {gl_info.get('renderer', 'N/A')}")
            print(f"  Version:    {gl_info.get('version', 'N/A')}")
            print(f"  GLSL:       {gl_info.get('shadingVersion', 'N/A')}")
            print(f"  Extensions: {gl_info.get('extensionCount', 0)}")
            print(f"  Has BPTC:   {gl_info.get('hasBPTC', 'N/A')}")
            if gl_info.get('error'):
                print(f"  ERROR: {gl_info['error']}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # 0b. Emulator identity check
        print("\n" + "="*60)
        print("  Emulator Identity Check")
        print("="*60)
        try:
            emu_info = await page.evaluate("""() => {
                return {
                    ua: navigator.userAgent,
                    platform: navigator.platform,
                    vendor: navigator.vendor,
                    maxTouch: navigator.maxTouchPoints,
                    deviceMemory: navigator.deviceMemory,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                };
            }""")
            print(f"  UA: {emu_info.get('ua', 'N/A')[:100]}")
            print(f"  Platform: {emu_info.get('platform', 'N/A')}")
            print(f"  MaxTouch: {emu_info.get('maxTouch', 'N/A')}")
            print(f"  DevMem:   {emu_info.get('deviceMemory', 'N/A')}")
            print(f"  Cores:    {emu_info.get('hardwareConcurrency', 'N/A')}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # 1. Scrapfly WebGL fingerprint test
        print("\n" + "="*60)
        print("  Scrapfly WebGL Fingerprint")
        print("="*60)
        try:
            await page.goto(
                "https://scrapfly.io/web-scraping-tools/webgl-fingerprint",
                wait_until="domcontentloaded", timeout=60000
            )
            await asyncio.sleep(12)
            text = await page.evaluate("document.body.innerText")
            # Extract WebGL info from the page
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                low = line.lower()
                if any(kw in low for kw in [
                    "renderer", "vendor", "webgl", "version", "gpu",
                    "unmasked", "shading", "extensions", "max ",
                ]):
                    print(f"    {line[:120]}")
        except Exception as e:
            print(f"  ERROR loading scrapfly: {e}")

        # 2. BrowserScan Score
        print("\n" + "="*60)
        print("  BrowserScan Score")
        print("="*60)
        try:
            await page.goto("https://www.browserscan.net/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(18)
            text = await page.evaluate("document.body.innerText")
            m = re.search(r"(\d+)\s*%", text)
            score = int(m.group(1)) if m else 0
            print(f"  Score: {score}%")
            deductions = re.findall(r"([A-Z][^\n]{5,60})\s*-\d+%", text)
            if deductions:
                print(f"  Deductions: {deductions}")
            else:
                print("  No deductions!")
        except Exception as e:
            print(f"  ERROR: {e}")

        # 3. WebRTC leak check
        print("\n" + "="*60)
        print("  WebRTC Leak Check")
        print("="*60)
        try:
            ips = await page.evaluate("""() => new Promise(resolve => {
                const ips = [];
                try {
                    const pc = new RTCPeerConnection({iceServers: []});
                    pc.createDataChannel('');
                    pc.createOffer().then(o => pc.setLocalDescription(o));
                    pc.onicecandidate = e => {
                        if (!e.candidate) { pc.close(); resolve(ips); return; }
                        const p = e.candidate.candidate.split(' ');
                        if (p.length >= 5) ips.push(p[4]);
                    };
                    setTimeout(() => { pc.close(); resolve(ips); }, 5000);
                } catch(e) { resolve(['ERROR:' + e.message]); }
            })""")
            private = [ip for ip in ips if ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("172.")]
            print(f"  WebRTC IPs: {ips}")
            if not private and not ips:
                print("  PERFECT: No IPs leaked at all")
            elif not private:
                print("  OK: Only public IPs (no private leak)")
            else:
                print(f"  WARNING: Private IP leak detected!")
        except Exception as e:
            print(f"  ERROR: {e}")

        # 4. Key signals
        print("\n" + "="*60)
        print("  Key Signals")
        print("="*60)
        wd = await page.evaluate("navigator.webdriver")
        print(f"  navigator.webdriver: {wd}")
        tz = await page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone")
        print(f"  Timezone: {tz}")
        lang = await page.evaluate("navigator.language")
        print(f"  Language: {lang}")

    print("\nDone!")

asyncio.run(probe())
