"""CreepJS full fingerprint capture on redroid auto mode."""
import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"

CREEPJS_SCRAPE = """async () => {
    const r = {};

    // Wait for CreepJS to finish
    let attempts = 0;
    while (attempts < 90) {
        const bodyText = document.body.innerText || '';
        if (bodyText.includes('trust score') || bodyText.includes('headless') ||
            bodyText.includes('stealth') || bodyText.includes('prediction')) break;
        await new Promise(resolve => setTimeout(resolve, 2000));
        attempts++;
    }

    // Grab all summary metrics from CreepJS using simple string ops
    try {
        const body = document.body.innerText || '';
        const lines = body.split('\\n');
        r.creepjsLines = [];
        for (const line of lines) {
            const l = line.trim();
            if (l.includes('headless') || l.includes('stealth') || l.includes('trust') ||
                l.includes('lie') || l.includes('prediction') || l.includes('bot') ||
                l.includes('Fingerprint') || l.includes('grade') || l.includes('%') ||
                l.includes('crowd') || l.includes('score') || l.includes('trash') ||
                l.includes('WebGL') || l.includes('Canvas') || l.includes('Audio') ||
                l.includes('Font') || l.includes('Screen') || l.includes('GPU') ||
                l.includes('Worker') || l.includes('Media') || l.includes('voice') ||
                l.includes('Speech') || l.includes('navigator') || l.includes('window')) {
                if (l.length > 2 && l.length < 300) r.creepjsLines.push(l);
            }
        }
    } catch(e) { r.scrapeError = e.message; }

    // Grab ALL fingerprint data from the page
    try {
        // Get all rows from the fingerprint table
        const rows = document.querySelectorAll('tr');
        const data = {};
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 2) {
                const key = cells[0].textContent.trim();
                const val = cells[1].textContent.trim();
                if (key) data[key] = val;
            }
        });
        r.tableData = data;
    } catch(e) { r.tableError = e.message; }

    // Get the full page text for analysis
    try {
        r.pageText = document.body.innerText.substring(0, 30000);
    } catch(e) {}

    // Specific fingerprint APIs
    try {
        r.userAgent = navigator.userAgent;
        r.platform = navigator.platform;
        r.hardwareConcurrency = navigator.hardwareConcurrency;
        r.deviceMemory = navigator.deviceMemory;
        r.maxTouchPoints = navigator.maxTouchPoints;
        r.languages = JSON.stringify(navigator.languages);
        r.doNotTrack = navigator.doNotTrack;
        r.cookieEnabled = navigator.cookieEnabled;
        r.pdfViewerEnabled = navigator.pdfViewerEnabled;
    } catch(e) {}

    // WebGL
    try {
        const c = document.createElement('canvas');
        const gl = c.getContext('webgl');
        if (gl) {
            const dbg = gl.getExtension('WEBGL_debug_renderer_info');
            r.glVendor = dbg  gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : 'N/A';
            r.glRenderer = dbg  gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'N/A';
            r.webglExts = gl.getSupportedExtensions().length;
        }
        const gl2 = document.createElement('canvas').getContext('webgl2');
        if (gl2) r.webgl2Exts = gl2.getSupportedExtensions().length;
    } catch(e) {}

    // Speech
    try {
        r.speechAvailable = 'speechSynthesis' in window;
        let v = speechSynthesis.getVoices();
        if (v.length === 0) {
            v = await new Promise(resolve => {
                speechSynthesis.onvoiceschanged = () => resolve(speechSynthesis.getVoices());
                setTimeout(() => resolve(speechSynthesis.getVoices()), 3000);
            });
        }
        r.speechVoices = v.length;
        r.speechVoiceNames = v.slice(0, 5).map(x => x.name + ' (' + x.lang + ')');
    } catch(e) {}

    // Screen
    try {
        r.screenW = screen.width;
        r.screenH = screen.height;
        r.innerW = window.innerWidth;
        r.innerH = window.innerHeight;
        r.dpr = window.devicePixelRatio;
        r.colorDepth = screen.colorDepth;
    } catch(e) {}

    // Media devices
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        r.mediaDevices = devices.map(d => d.kind).join(', ');
        r.mediaDeviceCount = devices.length;
    } catch(e) {}

    // Permissions
    try {
        const notif = await navigator.permissions.query({name: 'notifications'});
        r.notifPermission = notif.state;
    } catch(e) {}

    // Storage
    try {
        if (navigator.storage && navigator.storage.estimate) {
            const est = await navigator.storage.estimate();
            r.storageQuota = Math.round(est.quota / 1024 / 1024 / 1024) + 'GB';
        }
    } catch(e) {}

    // Connection
    try {
        if (navigator.connection) {
            r.connectionType = navigator.connection.type;
            r.connectionEffective = navigator.connection.effectiveType;
            r.connectionDownlink = navigator.connection.downlink;
            r.connectionRtt = navigator.connection.rtt;
        }
    } catch(e) {}

    // Client Hints
    try {
        if (navigator.userAgentData) {
            r.uaBrands = JSON.stringify(navigator.userAgentData.brands);
            r.uaMobile = navigator.userAgentData.mobile;
            r.uaPlatform = navigator.userAgentData.platform;
            const hi = await navigator.userAgentData.getHighEntropyValues([
                'architecture', 'model', 'platformVersion', 'fullVersionList'
            ]);
            r.uaModel = hi.model;
            r.uaPlatformVersion = hi.platformVersion;
            r.uaArch = hi.architecture;
            r.uaFullVersionList = JSON.stringify(hi.fullVersionList);
        }
    } catch(e) {}

    // Canvas fingerprint
    try {
        const c = document.createElement('canvas');
        c.width = 200; c.height = 50;
        const ctx = c.getContext('2d');
        ctx.fillStyle = '#f60';
        ctx.fillRect(0,0,200,50);
        ctx.fillStyle = '#069';
        ctx.font = '16px Arial';
        ctx.fillText('fingerprint', 10, 30);
        r.canvasHash = c.toDataURL().substring(0, 60) + '...';
    } catch(e) {}

    // AudioContext
    try {
        const ac = new (window.AudioContext || window.webkitAudioContext)();
        r.audioSampleRate = ac.sampleRate;
        r.audioState = ac.state;
        r.audioChannels = ac.destination.maxChannelCount;
        ac.close();
    } catch(e) {}

    // Intl
    try {
        r.intlLocale = Intl.DateTimeFormat().resolvedOptions().locale;
        r.intlTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch(e) {}

    // WebDriver
    try {
        r.webdriver = navigator.webdriver;
    } catch(e) {}

    return r;
}"""


async def main():
    print("=" * 70)
    print("  CreepJS Full Fingerprint Test")
    print("=" * 70)

    async with AsyncDamru(
        device="Samsung Galaxy S23 Ultra",
        serial="localhost:5600",
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        print("\n  Navigating to CreepJS...")
        for attempt in range(3):
            try:
                await page.goto(
                    "https://abrahamjuliot.github.io/creepjs/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                break
            except Exception as e:
                print(f"  Navigation attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(5)
                    # Navigate to about:blank first to reset state
                    try:
                        await page.goto("about:blank", timeout=5000)
                    except Exception:
                        pass
                else:
                    raise

        # Wait for CreepJS to analyze
        print("  Waiting for CreepJS analysis (up to 120s)...")
        await asyncio.sleep(90)

        print("  Scraping results...")
        results = await page.evaluate(CREEPJS_SCRAPE)

        # Print everything
        print("\n" + "=" * 70)
        print("  RAW FINGERPRINT DATA")
        print("=" * 70)

        # Print non-table data
        for key in sorted(results.keys()):
            if key in ('tableData', 'pageText'):
                continue
            val = results[key]
            print(f"  {key}: {val}")

        # Print page text (CreepJS results) - handle unicode
        if 'pageText' in results:
            print("\n" + "=" * 70)
            print("  CREEPJS PAGE TEXT (first 15000 chars)")
            print("=" * 70)
            text = results['pageText'][:15000]
            # Replace non-ascii chars to avoid encoding errors
            safe_text = text.encode('ascii', 'replace').decode('ascii')
            print(safe_text)

        print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
