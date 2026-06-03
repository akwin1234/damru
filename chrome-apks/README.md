# Chrome APK Bundle

Damru uses pinned Android Chrome/WebView/TTS assets so the browser binary, user agent, client hints, voices, and profile metadata stay coherent.

The APK payloads are large and are not committed to Git. Normal users should let setup download and place them automatically:

```bash
python -m damru install-apks --download
```

Manual bundle link:

https://drive.google.com/file/d/1xh5Z-LXqUIEjO08KKjhaB_89KS2pBWZq/view?usp=sharing

## Expected Layout

The default Linux/WSL location is `/home/damru/chrome-apks`.

```text
/home/damru/chrome-apks/
  TrichromeWebView.apk
  google_tts.apk
  espeak.apk
  rhvoice.apk
  143.x/
    base.apk
    google_trichrome_library.apk
    split_config.*.apk
  144.x/
    base.apk
    google_trichrome_library.apk
    split_config.*.apk
```

Damru ships `magisk.apk` as a package asset and copies it into the local bundle when raw/unbaked Redroid needs a local source for standalone `resetprop`. Damru does not download Magisk, eSpeak, Google TTS, or RHVoice from third-party APK sites at runtime.

## Why This Matters

Emulators often have mismatched browser versions and no TTS voices. That is easy to fingerprint. Damru installs known-good Chrome/WebView/TTS combinations so browser version, voices, profile language, and Android identity remain believable.

## Baked Image Path

The fastest path is the baked Redroid image, where Chrome, WebView, TTS, fonts, native hooks, and warm preferences are already installed:

https://drive.google.com/file/d/1AzSTOlGpSfqHB-F-Yty2JqbOEMlgFT5F/view?usp=sharing
