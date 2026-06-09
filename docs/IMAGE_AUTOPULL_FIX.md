# Image and APK Readiness

Status: implemented. Current users should prefer the documented CLI flow instead of manually pulling Redroid images.

## Recommended Flow

```bash
python -m damru install-deps -y
python -m damru install-image
python -m damru check preflight
python -m damru check-env
```

`install-image` loads or downloads the baked `damru-redroid:latest` image. The baked image is the recommended path because Chrome, WebView/TTS assets, fonts, warm preferences, and native assets are already inside the container image.

The published tarball is exported from a clean Redroid base with Damru assets applied once. If you rebake, make sure `bake-image --image damru-redroid:latest` starts from the configured Redroid base image, not an older `damru-redroid:latest`, or the tarball will grow from stale stacked layers.

## Raw/Unbaked Flow

Use this only for baking, debugging, or APK recovery:

```bash
python -m damru install-apks --download
python -m damru bake-image --image damru-redroid:latest
docker save damru-redroid:latest -o damru-redroid-latest.tar
sha256sum damru-redroid-latest.tar > damru-redroid-latest.tar.sha256
python -m damru install-image --tar damru-redroid-latest.tar
python -m damru quick-check --serial 127.0.0.1:5600
```

The APK installer extracts to `/home/damru/chrome-apks` by default and validates:

- Chrome split-APK version folders
- Matching per-version `webview.apk` or `TrichromeWebView.apk` for folders used by Chrome rotation
- `google_tts.apk`
- `espeak.apk`
- `rhvoice.apk`
- Damru's packaged `magisk.apk` when raw Redroid needs a local `resetprop` source

Random profile actions rotate only through Chrome version folders with a matching WebView APK. Folders without a matching WebView asset are skipped so Chrome and Android WebView do not drift apart.

## Readiness Checks

`python -m damru check preflight` is fast and read-only. It does not install packages, pull/load images, mount binderfs, start containers, edit iptables, or change `.wslconfig`. Use `--json` for automation:

```bash
python -m damru check preflight --json --timeout 3
```

`python -m damru check-env` is slower and deeper. It verifies setup details such as Docker, binderfs, image/APK discovery, ADB, Playwright patching, and optional viewer tooling.

## Failure Handling

- Missing baked image: run `python -m damru install-image`.
- Missing raw APKs: run `python -m damru install-apks --download`.
- WSL Docker/binderfs/network issue: run `python -m damru fix-wsl`.
- Worker DNS/internet issue: run `python -m damru fix-internet --all`.
- Unsupported Debian/custom kernel: use Ubuntu 24.04 or a binderfs-enabled kernel.
