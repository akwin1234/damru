"""Debug Worker interception - test all Worker creation patterns."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from damru import AsyncDamru

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"

WORKER_TEST_SCRIPT = """() => {
    return new Promise((resolve) => {
        const results = {};

        // Main thread values (baseline)
        results.main_cores = navigator.hardwareConcurrency;
        results.main_mem = navigator.deviceMemory;

        // Check if Blob and Worker are Proxied
        results.blob_type = typeof Blob;
        results.worker_type = typeof Worker;

        // Test 1: Blob Worker (most common pattern)
        try {
            const workerCode = `
                self.onmessage = function() {
                    self.postMessage({
                        cores: navigator.hardwareConcurrency,
                        mem: navigator.deviceMemory,
                        has_WorkerNavigator: typeof WorkerNavigator !== 'undefined',
                    });
                };
            `;
            const blob = new Blob([workerCode], {type: 'application/javascript'});
            const url = URL.createObjectURL(blob);
            const w = new Worker(url);

            w.onmessage = function(e) {
                results.blob_worker = e.data;
                w.terminate();
                URL.revokeObjectURL(url);

                // Test 2: Inline Worker via data: URL
                try {
                    const dataUrl = 'data:application/javascript,' + encodeURIComponent(`
                        self.onmessage = function() {
                            self.postMessage({
                                cores: navigator.hardwareConcurrency,
                                mem: navigator.deviceMemory,
                            });
                        };
                    `);
                    const w2 = new Worker(dataUrl);
                    w2.onmessage = function(e2) {
                        results.data_worker = e2.data;
                        w2.terminate();
                        resolve(results);
                    };
                    w2.onerror = function(err) {
                        results.data_worker_error = err.message || 'error';
                        resolve(results);
                    };
                    w2.postMessage('go');
                } catch(e2) {
                    results.data_worker_error = e2.message;
                    resolve(results);
                }
            };

            w.onerror = function(err) {
                results.blob_worker_error = err.message || 'error';
                resolve(results);
            };

            w.postMessage('go');
        } catch(e) {
            results.blob_worker_error = e.message;
            resolve(results);
        }
    });
}"""


async def main():
    print("=" * 60)
    print("  Worker Interception Debug Test")
    print("=" * 60)

    async with AsyncDamru(
        device="Samsung Galaxy S24 FE",
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=False,
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # Test on data: URL
        print("\n--- data: URL test ---")
        await page.goto(
            "data:text/html,<h1>worker test</h1>",
            wait_until="domcontentloaded",
            timeout=10000,
        )
        await asyncio.sleep(1)

        r = await page.evaluate(WORKER_TEST_SCRIPT)
        _print(r)

        # Test on HTTPS page
        print("\n--- example.com test ---")
        try:
            await page.goto(
                "https://www.example.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await asyncio.sleep(2)
            r2 = await page.evaluate(WORKER_TEST_SCRIPT)
            _print(r2)
        except Exception as e:
            print(f"  Navigation error: {e}")

    print("\nDone!")


def _print(r):
    print(f"  Main thread: cores={r.get('main_cores')}, mem={r.get('main_mem')}")
    print(f"  Blob type: {r.get('blob_type')}, Worker type: {r.get('worker_type')}")

    bw = r.get("blob_worker")
    if bw:
        cores_ok = bw.get("cores") == r.get("main_cores")
        mem_ok = bw.get("mem") == r.get("main_mem")
        print(f"  Blob Worker: cores={bw.get('cores')}, mem={bw.get('mem')}, "
              f"WorkerNavigator={bw.get('has_WorkerNavigator')}")
        print(f"    cores match: {'PASS' if cores_ok else 'FAIL'}")
        print(f"    mem match:   {'PASS' if mem_ok else 'FAIL'}")
    elif r.get("blob_worker_error"):
        print(f"  Blob Worker ERROR: {r.get('blob_worker_error')}")

    dw = r.get("data_worker")
    if dw:
        cores_ok = dw.get("cores") == r.get("main_cores")
        mem_ok = dw.get("mem") == r.get("main_mem")
        print(f"  Data Worker: cores={dw.get('cores')}, mem={dw.get('mem')}")
        print(f"    cores match: {'PASS' if cores_ok else 'FAIL'}")
        print(f"    mem match:   {'PASS' if mem_ok else 'FAIL'}")
    elif r.get("data_worker_error"):
        print(f"  Data Worker ERROR: {r.get('data_worker_error')}")


if __name__ == "__main__":
    asyncio.run(main())
