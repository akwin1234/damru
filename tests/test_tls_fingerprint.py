"""Test TLS fingerprint randomization via tls.peet.ws/api/all.

Launches 2 redroid sessions (auto mode) and captures JA3/JA4/HTTP2
fingerprints from Chrome to verify they're actually changing.
"""
import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from damru import DamruPool
from damru.utils import setup_logging

PH_SOCKS5 = "socks5://proxy.example:50001"
PH_HTTP = "proxy.example:50000"

TLS_URL = "https://tls.peet.ws/api/all"


async def capture_tls(ctx, session_num: int) -> dict:
    """Navigate to tls.peet.ws/api/all and capture fingerprint JSON."""
    print(f"\n  Session {session_num}: Navigating to {TLS_URL}...")
    page = await ctx.new_page()

    try:
        await page.goto(TLS_URL, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(3)

        body_text = await page.evaluate("""
            () => {
                const pre = document.querySelector('pre');
                return pre  pre.textContent : document.body.innerText;
            }
        """)

        try:
            tls_data = json.loads(body_text)
        except json.JSONDecodeError:
            print(f"  ERROR: Could not parse JSON. Body: {body_text[:300]}")
            return {"error": body_text[:300]}

        # Data is nested under tls.* and http2.*
        tls = tls_data.get("tls", {})
        h2 = tls_data.get("http2", {})

        result = {
            "ja3": tls.get("ja3", ""),
            "ja3_hash": tls.get("ja3_hash", ""),
            "ja4": tls.get("ja4", ""),
            "peetprint_hash": tls.get("peetprint_hash", ""),
            "ciphers": tls.get("ciphers", []),
            "h2_cdn": h2.get("cdn_fingerprint", ""),
            "h2_cdn_hash": h2.get("cdn_fingerprint_hash", ""),
        }

        # Extract supported_groups from extensions
        for ext in tls.get("extensions", []):
            if ext.get("name", "").startswith("supported_groups"):
                result["supported_groups"] = ext.get("supported_groups", [])

        print(f"\n  Session {session_num} TLS fingerprint:")
        print(f"    JA3 hash:      {result['ja3_hash']}")
        print(f"    JA4:           {result['ja4']}")
        print(f"    Cipher count:  {len(result['ciphers'])}")
        print(f"    H2 CDN TLS:     {result['h2_cdn']}")
        print(f"    H2 CDN TLS hash:{result['h2_cdn_hash']}")
        print(f"    Groups:        {result.get('supported_groups', 'N/A')}")

        outfile = os.path.join(os.path.dirname(__file__), f"tls_session_{session_num}.json")
        with open(outfile, "w") as f:
            json.dump(tls_data, f, indent=2)
        print(f"    Full data: {outfile}")

        return result

    finally:
        await page.close()


async def main():
    setup_logging(True)
    print("=" * 60)
    print("  TLS FINGERPRINT RANDOMIZATION TEST")
    print("  Chrome on redroid via tls.peet.ws/api/all")
    print("=" * 60)

    results = []

    async with DamruPool(
        mode="auto",
        max_devices=1,
        proxy=PH_SOCKS5,
        http_proxy=PH_HTTP,
        timezone="Asia/Manila",
        debug=True,
    ) as pool:
        print(f"\n  Pool ready: {pool.device_count} device(s)")

        for session_num in range(1, 3):
            print(f"\n{'='*60}")
            print(f"  SESSION {session_num}")
            print(f"{'='*60}")
            t0 = time.monotonic()

            async with pool.session() as ctx:
                r = await capture_tls(ctx, session_num)
                r["elapsed"] = time.monotonic() - t0
                results.append(r)

    if any("error" in r for r in results):
        print("\nERROR: Could not capture TLS fingerprints. Check logs above.")
        return

    r1, r2 = results
    print("\n" + "=" * 60)
    print("  COMPARISON: Session 1 vs Session 2")
    print("=" * 60)

    def compare(field, label):
        v1, v2 = r1.get(field, ""), r2.get(field, "")
        if not v1 and not v2:
            print(f"  -- {label}: N/A")
            return None
        match = v1 == v2
        status = "SAME" if match else "DIFFERENT"
        icon = "FAIL" if match else "PASS"
        print(f"  [{icon}] {label}: {status}")
        if not match:
            print(f"         S1: {str(v1)[:80]}")
            print(f"         S2: {str(v2)[:80]}")
        else:
            print(f"         Both: {str(v1)[:80]}")
        return not match

    ja3_diff = compare("ja3_hash", "JA3 hash")
    ja4_diff = compare("ja4", "JA4")
    h2_diff = compare("h2_cdn_hash", "HTTP/2 CDN TLS hash")
    compare("supported_groups", "Supported groups")

    cs1 = len(r1.get("ciphers", []))
    cs2 = len(r2.get("ciphers", []))
    cs_diff = cs1 != cs2
    print(f"  [{'PASS' if cs_diff else 'FAIL'}] Cipher suite count: {cs1} vs {cs2}")

    print(f"\n  VERDICT:")
    print(f"    JA3 randomized:    {'YES' if ja3_diff else 'NO (NEEDS FIX)'}")
    print(f"    JA4 randomized:    {'YES' if ja4_diff else 'NO (NEEDS FIX)'}")
    print(f"    HTTP/2 randomized: {'YES' if h2_diff else 'NO (expected - Chrome H2 is static, curl_cffi bypass handles this)'}")
    print(f"    Cipher count diff: {'YES' if cs_diff else 'NO'}")

    # Also test curl_cffi H2 diversity (bypass layer)
    print(f"\n{'='*60}")
    print("  BYPASS LAYER: curl_cffi H2 fingerprint diversity")
    print("=" * 60)
    try:
        from curl_cffi import requests as cffi_requests
        h2_hashes = set()
        for profile in ["chrome120", "safari17_0", "edge101"]:
            sess = cffi_requests.Session(impersonate=profile)
            r = sess.get("https://tls.peet.ws/api/all", timeout=15)
            d = json.loads(r.text)
            h2h = d.get("http2", {}).get("cdn_fingerprint_hash", "")
            h2fp = d.get("http2", {}).get("cdn_fingerprint", "")
            h2_hashes.add(h2h)
            print(f"    {profile:12s} -> H2={h2h} ({h2fp[:40]}...)")
        print(f"\n    Unique H2 fingerprints in bypass: {len(h2_hashes)}")
        print(f"    H2 diversity: {'YES' if len(h2_hashes) > 1 else 'NO'}")
    except ImportError:
        print("    curl_cffi not available - bypass uses urllib3 only")


if __name__ == "__main__":
    asyncio.run(main())
