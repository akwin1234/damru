# ðŸ“¦ Chrome APKs (`chrome-apks/`)

To achieve true undetectability, we cannot rely on whatever default browser version happens to be pre-installed on the emulator. We must match our browser version *exactly* with the User-Agent we are spoofing.

> **This folder contains the actual `.apk` payloads injected into the Android emulator when running raw/unbaked Redroid.**

The APK payloads are large and are not committed to Git. Install the release bundle when you need raw APKs for baking or unbaked Redroid:

```bash
python -m damru install-apks --download
```

Google Drive bundle: [Chrome/WebView/TTS APK assets](https://drive.google.com/file/d/1xh5Z-LXqUIEjO08KKjhaB_89KS2pBWZq/view?usp=sharing)

Extract/copy it so one bundle root, normally `/home/damru/chrome-apks` on Linux/WSL, contains version directories such as `145.0.7632.75/` with `base.apk`, `google_trichrome_library.apk`, and Chrome split APKs. Keep the top-level WebView/TTS APKs in this same bundle folder too, for example `TrichromeWebView.apk`, `google_tts.apk`, `espeak.apk`, and `rhvoice.apk`.

Manual Linux/WSL example:

```bash
sudo mkdir -p /home/damru
sudo chown "$USER:$USER" /home/damru
unzip damru-chrome-apks-latest.zip -d /home/damru/chrome-apks
find /home/damru/chrome-apks -maxdepth 2 -name '*.apk' | head
```

If the archive already contains a top-level `chrome-apks/` directory, extract it beside the project instead. On Windows, use File Explorer or 7-Zip, then copy the resulting `chrome-apks` folder into the Damru project. WSL sees Windows files under `/mnt/c/...`.

---

## ðŸ—‚ï¸ Contents

### ðŸŒ Chrome Splits (`143.x`, `144.x`, `145.x`)
We maintain different versions of Chrome. When Damru generates a spoofed profile, it automatically detects which Chrome version is needed and installs the corresponding APKs via ADB.

*   `base.apk`: The core browser application.
*   `google_trichrome_library.apk`: The shared Chromium rendering engine required by modern Android Chrome.
*   `split_config.*.apk`: Architecture and language specific splits.

### ðŸ—£ï¸ TTS Engines (`espeak.apk`, `google_tts.apk`, `rhvoice.apk`)
Many anti-bots fingerprint the Text-to-Speech (TTS) voices available on the device. Emulators often have *zero* voices, which is a massive red flag. Damru installs these APKs to populate the Android TTS service with realistic voice arrays, mimicking a real human's smartphone.

---

## ðŸš€ Deployment Note

*   **Dynamic Push**: If you use the manual base OS image, Damru will dynamically push and install these APKs on cold starts.
*   **Pre-baked**: If you use the [damru-redroid-latest.tar](https://drive.google.com/file/d/1AzSTOlGpSfqHB-F-Yty2JqbOEMlgFT5F/view?usp=sharing) pre-baked image, all of these APKs (and the TTS configuration) are permanently integrated into the OS image, allowing instant booting without the 30+ second ADB installation penalty.
