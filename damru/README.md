# 🐍 Damru Core Library (`damru/`)

Welcome to the heart of the Damru framework. This directory contains the main Python source code responsible for orchestrating the entire lifecycle of the spoofing process. 

Our core philosophy here is **"Zero JS Injection"**. Every spoof is executed natively or at the protocol level.

---

## 🏗️ Architecture Overview

The library is modular and highly specialized:

*   🚀 **`async_core.py` & `core.py`**: The main entry points (Async and Sync context managers). These manage the connection flow: `ADB detection -> Rooting -> Applying OS Props -> Patching GPU -> Launching Chrome -> Attaching CDP`.
*   📱 **`devices.py`**: A massive built-in database of 32+ real Android devices. It holds correct hardware specs (CPU cores, RAM, screen resolutions, OS props) to ensure our spoofing is physically accurate.
*   🔑 **`root.py`**: Executes the **Layer 1 (OS)** and **Layer 2 (Binary)** stealth patches via ADB shell using `su`. It modifies `build.prop`, pushes custom GPU `.so` files, and manages `iptables` for WebRTC/IPv6 blocking.
*   🔌 **`cdp.py`**: Handles the connection to the Chrome DevTools Protocol, securely forwarding ports from the Android emulator to `localhost`.
*   🌐 **`chrome.py`**: Manages the Chrome browser lifecycle on the device. It handles clearing app data, dismissing the First Run Experience (FRE), and injecting our **Layer 4** stealth patches directly into Chrome's `Preferences` JSON file.
*   🗺️ **`proxy.py`**: Parses incoming proxy strings and uses them to dynamically map Timezones, Geolocation, and Locales so the browser's identity matches the IP's physical origin.
*   🗄️ **`pool.py`**: Connection pooling managers (`DamruPool`, `DamruPoolSync`) designed for scaling operations concurrently across multiple Docker containers.
*   🩹 **`playwright_patch/`**: Contains `crPage.js` modifications that are dynamically loaded to neutralize Playwright's default behavior, preventing CDP target discovery leaks.

---

> **Note to Developers:** When modifying the core, remember to avoid relying on JavaScript-based evasions. Always look for OS-level or CDP-level solutions first.