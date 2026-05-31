# 🧪 Test Suite & Benchmarks (`tests/`)

Welcome to the Damru proving grounds. This directory contains our extensive testing framework. 

> **These tests are not just for code correctness—they are active probes against the world's most aggressive anti-bot and fingerprinting services.**

---

## 📊 Test Categories

Our suite is broken down into specific domains of stealth and reliability:

*   🛡️ **`benchmark_auto.py` / `test_benchmark_sites.py`**: Runs Damru through high-tier bot tests like CreepJS, BrowserScan, Sannysoft, and Cloudflare.
*   🎮 **`test_gpu_*.py`**: Specifically verifies that the native binary patches (`native/` folder) are successfully spoofing Vulkan/GLES renderers without leaking *SwiftShader* or *Google Swift* properties.
*   🖥️ **`test_identity.py` / `test_hardware.py`**: Ensures the hardware concurrency (CPU cores), RAM, touch points, and User-Agent are correctly overridden via CDP.
*   🌐 **`test_ip_leak.py` / `test_webrtc_*.py`**: Verifies that the Android `iptables` rules successfully prevent WebRTC from leaking private/local IPs.
*   🔄 **`test_e2e.py`**: End-to-End tests verifying the full flow: `Docker container creation -> Profile Assignment -> Proxy Binding -> Stealth Browsing -> Teardown`.

---

## 🚀 How to Run

Most tests use `pytest` for streamlined execution and reporting.

**Run the full suite:**
```bash
cd ..
pytest tests/
```

**Run a specific stealth module (verbose mode):**
```bash
pytest tests/test_stealth.py -v
```

**Run benchmark tests against real anti-bots:**
```bash
python -m tests.benchmark_auto
```

*Note: These tests are crucial for verifying that the "Zero JS Injection" methodology holds up against evolving browser fingerprinting techniques. Always run the suite before submitting PRs!*