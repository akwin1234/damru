"""Debug CreepJS Worker creation pattern."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from damru import AsyncDamru

PH_SOCKS5 = "socks5://198.20.189.134:50001"
PH_HTTP = "198.20.189.134:50000"


async def main():
    print("=" * 60)
    print("  CreepJS Worker Debug")
    print("=" * 60)

    async with AsyncDamru(
        device="Samsung Galaxy S24 FE",
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=False,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        print("\n  Navigating to CreepJS...")
        try:
            await page.goto(
                "https://abrahamjuliot.github.io/creepjs/",
                wait_until="domcontentloaded",
                timeout=45000,
            )
        except Exception as e:
            print(f"  Nav error (continuing): {e}")

        # Check if our Blob/Worker proxies survived navigation
        proxy_check = await page.evaluate("""() => {
            const results = {};
            // Check if Blob and Worker are native or Proxy
            results.blob_toString = Blob.toString().substring(0, 100);
            results.worker_toString = Worker.toString().substring(0, 100);
            results.blob_name = Blob.name;
            results.worker_name = Worker.name;

            // Check if our init_script ran (hardwareConcurrency should be overridden)
            results.main_cores = navigator.hardwareConcurrency;
            results.main_mem = navigator.deviceMemory;

            // Check if Worker prototype is Proxy
            results.blob_is_function = typeof Blob === 'function';
            results.worker_is_function = typeof Worker === 'function';

            return results;
        }""")
        print(f"\n  Blob toString: {proxy_check.get('blob_toString', '?')}")
        print(f"  Worker toString: {proxy_check.get('worker_toString', '?')}")
        print(f"  Blob.name: {proxy_check.get('blob_name')}")
        print(f"  Worker.name: {proxy_check.get('worker_name')}")
        print(f"  Main cores: {proxy_check.get('main_cores')}")
        print(f"  Main mem: {proxy_check.get('main_mem')}")

        # Now create a worker from CreepJS page context to test
        worker_test = await page.evaluate("""() => {
            return new Promise((resolve) => {
                try {
                    const code = `
                        self.onmessage = function() {
                            self.postMessage({
                                cores: navigator.hardwareConcurrency,
                                mem: navigator.deviceMemory,
                                hasWN: typeof WorkerNavigator !== 'undefined',
                            });
                        };
                    `;
                    const blob = new Blob([code], {type: 'application/javascript'});
                    const url = URL.createObjectURL(blob);
                    const w = new Worker(url);
                    w.onmessage = function(e) {
                        w.terminate();
                        URL.revokeObjectURL(url);
                        resolve({worker: e.data});
                    };
                    w.onerror = function(err) {
                        resolve({error: err.message || 'worker error'});
                    };
                    w.postMessage('go');
                    setTimeout(() => resolve({error: 'timeout'}), 10000);
                } catch(e) {
                    resolve({error: e.message});
                }
            });
        }""")
        print(f"\n  Worker from CreepJS page: {worker_test}")

        # Wait for CreepJS to finish
        print("\n  Waiting 30s for CreepJS analysis...")
        await asyncio.sleep(30)

        # Check page source for worker script URLs
        scripts = await page.evaluate("""() => {
            const scripts = [];
            document.querySelectorAll('script').forEach(s => {
                if (s.src) scripts.push(s.src);
            });
            return scripts;
        }""")
        print(f"\n  Page scripts: {len(scripts)}")
        for s in scripts[:5]:
            print(f"    {s}")

        # Check CreepJS hardware output
        text = await page.evaluate("document.body.innerText")
        print("\n  === CreepJS hardware lines ===")
        for line in text.split("\n"):
            low = line.lower().strip()
            if any(kw in low for kw in ["cores", "ram", "hardware", "memory", "lies", "headless", "stealth"]):
                if len(line.strip()) < 120:
                    print(f"    {line.strip()}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
