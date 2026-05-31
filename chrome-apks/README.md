# 📦 Chrome APKs (`chrome-apks/`)

To achieve true undetectability, we cannot rely on whatever default browser version happens to be pre-installed on the emulator. We must match our browser version *exactly* with the User-Agent we are spoofing.

> **This folder contains the actual `.apk` payloads injected into the Android emulator.**

---

## 🗂️ Contents

### 🌐 Chrome Splits (`143.x`, `144.x`, `145.x`)
We maintain different versions of Chrome. When Damru generates a spoofed profile, it automatically detects which Chrome version is needed and installs the corresponding APKs via ADB.

*   `base.apk`: The core browser application.
*   `google_trichrome_library.apk`: The shared Chromium rendering engine required by modern Android Chrome.
*   `split_config.*.apk`: Architecture and language specific splits.

### 🗣️ TTS Engines (`espeak.apk`, `google_tts.apk`, `rhvoice.apk`)
Many anti-bots fingerprint the Text-to-Speech (TTS) voices available on the device. Emulators often have *zero* voices, which is a massive red flag. Damru installs these APKs to populate the Android TTS service with realistic voice arrays, mimicking a real human's smartphone.

---

## 🚀 Deployment Note

*   **Dynamic Push**: If you use the manual base OS image, Damru will dynamically push and install these APKs on cold starts. 
*   **Pre-baked**: If you use the [damru-redroid-latest.tar](https://drive.google.com/file/d/1na6YYHbpvDlaXhicg_nAKiaMFaYRN99U/view?usp=sharing) pre-baked image, all of these APKs (and the TTS configuration) are permanently integrated into the OS image, allowing instant booting without the 30+ second ADB installation penalty.