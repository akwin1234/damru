"""Phase 1 fix verification: Audio, Fonts, TTS, MIME types."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"

VERIFY_SCRIPT = """async () => {
    const r = {};

    // Audio sampleRate
    try {
        const ac = new (window.AudioContext || window.webkitAudioContext)();
        r.audioSampleRate = ac.sampleRate;
        r.audioChannels = ac.destination.maxChannelCount;
        ac.close();
    } catch(e) { r.audioError = e.message; }

    // Font detection (test standard fingerprint fonts)
    try {
        const testFonts = [
            'Andale Mono', 'Arial', 'Arial Black', 'Calibri', 'Cambria',
            'Century Gothic', 'Comic Sans MS', 'Consolas', 'Courier', 'Courier New',
            'Georgia', 'Helvetica', 'Impact', 'Lucida Console', 'Lucida Sans',
            'Lucida Sans Typewriter', 'Monaco', 'Book Antiqua', 'Century Schoolbook',
            'Open Sans', 'Lato', 'Montserrat', 'Oswald', 'Poppins',
            'PT Sans', 'Fira Mono', 'Merriweather', 'Inconsolata',
            'Segoe UI', 'Tahoma', 'Times', 'Times New Roman', 'Trebuchet MS',
            'Verdana', 'Palatino', 'Roboto', 'sans-serif', 'serif', 'monospace',
            'cursive', 'fantasy'
        ];

        const canvas = document.createElement('canvas');
        canvas.width = 600; canvas.height = 50;
        const ctx = canvas.getContext('2d');
        const testStr = 'mmmmmmmmmmlli0OQ';

        // Measure default
        ctx.font = '72px monospace';
        const defaultW = ctx.measureText(testStr).width;

        const detected = [];
        for (const font of testFonts) {
            ctx.font = '72px "' + font + '", monospace';
            const w = ctx.measureText(testStr).width;
            if (Math.abs(w - defaultW) > 0.1) {
                detected.push(font);
            }
        }
        r.fontsDetected = detected;
        r.fontCount = detected.length;
        r.fontTotal = testFonts.length;
    } catch(e) { r.fontError = e.message; }

    // Speech voices
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
        r.speechSample = v.slice(0, 10).map(x => x.name + ' (' + x.lang + ')');
    } catch(e) { r.speechError = e.message; }

    // MIME types
    try {
        const mimeTests = [
            'video/mp4', 'video/webm', 'video/ogg',
            'video/mp4; codecs="avc1.42E01E"',
            'video/mp4; codecs="hev1.1.6.L93.B0"',
            'video/mp4; codecs="av01.0.01M.08"',
            'video/webm; codecs="vp8"',
            'video/webm; codecs="vp9"',
            'audio/mp4', 'audio/webm', 'audio/ogg',
            'audio/mpeg', 'audio/wav', 'audio/flac',
        ];

        const v = document.createElement('video');
        const supported = [];
        const unsupported = [];
        for (const mime of mimeTests) {
            const res = v.canPlayType(mime);
            if (res === 'probably' || res === 'maybe') {
                supported.push(mime);
            } else {
                unsupported.push(mime);
            }
        }
        r.mimeSupported = supported;
        r.mimeUnsupported = unsupported;
        r.mimeCount = supported.length + '/' + mimeTests.length;
    } catch(e) { r.mimeError = e.message; }

    return r;
}"""


async def main():
    print("=" * 70)
    print("  Phase 1 Fix Verification")
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

        print("\n  Navigating to about:blank for API checks...")
        await page.goto("about:blank", timeout=10000)
        await asyncio.sleep(2)

        print("  Running verification script...")
        results = await page.evaluate(VERIFY_SCRIPT)

        print("\n" + "=" * 70)
        print("  RESULTS")
        print("=" * 70)

        # Audio
        sr = results.get("audioSampleRate", "")
        print(f"\n  [AUDIO] sampleRate: {sr} {'PASS' if sr == 48000 else 'FAIL (want 48000)'}")

        # Fonts
        fc = results.get("fontCount", 0)
        ft = results.get("fontTotal", 0)
        print(f"\n  [FONTS] Detected: {fc}/{ft}")
        detected = results.get("fontsDetected", [])
        for f in detected:
            print(f"    + {f}")

        # Speech
        sv = results.get("speechVoices", 0)
        print(f"\n  [TTS] Voices: {sv} {'PASS' if sv >= 100 else 'NEEDS MORE'}")
        sample = results.get("speechSample", [])
        for s in sample:
            print(f"    - {s}")

        # MIME
        mc = results.get("mimeCount", "")
        print(f"\n  [MIME] Supported: {mc}")
        unsup = results.get("mimeUnsupported", [])
        if unsup:
            print("    Missing:")
            for m in unsup:
                print(f"      - {m}")

        print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
