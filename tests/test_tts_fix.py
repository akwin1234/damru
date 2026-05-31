"""Quick TTS voices diagnostic and fix verification.

Tests that speechSynthesis.getVoices() returns voices after damru warmup.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from damru import AsyncDamru
from damru.utils import sleep

PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 70)
    print("  TTS Voices Fix Test")
    print("=" * 70)

    async with AsyncDamru(
        device="random",
        proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: Check TTS state via ADB (using the internal ADB instance)
        print("\n  [1] Checking Android TTS configuration...")

        # Step 2: Check voices via JS on current page
        print("\n  [2] Checking speechSynthesis.getVoices()...")
        try:
            result = await page.evaluate("""() => {
                const voices = speechSynthesis.getVoices();
                return {
                    count: voices.length,
                    samples: voices.slice(0, 10).map(v => ({
                        name: v.name,
                        lang: v.lang,
                        local: v.localService,
                        default: v.default
                    }))
                };
            }""")
            print(f"  Voices on current page: {result['count']}")
            if result['samples']:
                for v in result['samples']:
                    tag = " [DEFAULT]" if v['default'] else ""
                    local = "local" if v['local'] else "network"
                    print(f"    - {v['name']} ({v['lang']}, {local}){tag}")
        except Exception as e:
            print(f"  Error checking voices: {e}")

        # Step 3: Navigate to HTTPS page and try again
        print("\n  [3] Navigating to example.com and re-checking...")
        try:
            await page.goto("https://www.example.com/", wait_until="domcontentloaded", timeout=15000)
            await sleep(2)
            result = await page.evaluate("""() => {
                const voices = speechSynthesis.getVoices();
                return {
                    count: voices.length,
                    samples: voices.slice(0, 10).map(v => ({
                        name: v.name,
                        lang: v.lang,
                        local: v.localService,
                        default: v.default
                    }))
                };
            }""")
            print(f"  Voices after navigation: {result['count']}")
            if result['samples']:
                for v in result['samples']:
                    tag = " [DEFAULT]" if v['default'] else ""
                    local = "local" if v['local'] else "network"
                    print(f"    - {v['name']} ({v['lang']}, {local}){tag}")
        except Exception as e:
            print(f"  Error: {e}")

        # Step 4: Manual speak trigger and recheck
        print("\n  [4] Manual speak() trigger + recheck...")
        try:
            await page.evaluate("""() => {
                const u = new SpeechSynthesisUtterance('test');
                u.volume = 0;
                speechSynthesis.speak(u);
                setTimeout(() => speechSynthesis.cancel(), 500);
            }""")
            await sleep(3)
            result = await page.evaluate("""() => {
                const voices = speechSynthesis.getVoices();
                return {
                    count: voices.length,
                    engines: [...new Set(voices.map(v => v.name.split(' ')[0]))]
                };
            }""")
            print(f"  Voices after manual speak: {result['count']}")
            if result.get('engines'):
                print(f"  Engines: {result['engines'][:10]}")
        except Exception as e:
            print(f"  Error: {e}")

        # Step 5: Wait for onvoiceschanged
        print("\n  [5] Waiting for onvoiceschanged (up to 10s)...")
        try:
            result = await page.evaluate("""() => {
                return new Promise((resolve) => {
                    const voices = speechSynthesis.getVoices();
                    if (voices.length > 0) {
                        resolve({count: voices.length, waited: false});
                        return;
                    }
                    speechSynthesis.onvoiceschanged = () => {
                        const v = speechSynthesis.getVoices();
                        resolve({count: v.length, waited: true});
                    };
                    setTimeout(() => {
                        const v = speechSynthesis.getVoices();
                        resolve({count: v.length, waited: true, timedOut: true});
                    }, 10000);
                });
            }""")
            print(f"  Final voice count: {result['count']}")
            if result.get('waited'):
                print(f"  Waited for event: {'timed out' if result.get('timedOut') else 'received'}")
        except Exception as e:
            print(f"  Error: {e}")

        print("\n" + "=" * 70)
        print("  Done")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
