# Damru Viewer, Screenshots, and Video

Damru normally runs headless. Visual tooling is optional and must be launched explicitly so normal stealth automation does not open windows or send manual input events.

## Local UI Viewer

The easiest viewer path is the experimental local dashboard:

```bash
python -m damru ui
```

Open **Work Lab**, select an ADB worker, then click **Open viewer**. The browser viewer streams Android screenshots and sends click, drag, text, Back, Home, and Recent actions over ADB. It is useful for quick inspection, but it is browser-based and can feel slower than native screen mirroring.

Use **Copy native command** in Work Lab to copy the right terminal command for the current OS and selected worker. On Windows, Damru still manages workers through WSL, but the native viewer command passes the plain TCP serial such as `127.0.0.1:5600` to `scrcpy`.

The UI also exposes URL navigation, quick checks, screenshots, gallery cleanup, internet repair, random profile actions, and inline logs for the selected worker. These actions are convenience wrappers around allowlisted Damru commands; they do not run arbitrary shell input.

## Commands

```bash
python -m damru devices
python -m damru screenshot --serial wsl:127.0.0.1:5600 --output screen.png
python -m damru record --serial wsl:127.0.0.1:5600 --time-limit 30 --output clip.mp4
python -m damru view --serial wsl:127.0.0.1:5600
python -m damru view --serial wsl:127.0.0.1:5600 --no-control
```

If `--serial` is omitted, Damru uses virtual-device auto-detection: TCP endpoints first, then `emulator-*` serials. Windows/WSL Redroid workers appear as `wsl:127.0.0.1:5600`, `wsl:127.0.0.1:5601`, and so on. Physical-looking USB serials are refused by default; `DAMRU_ALLOW_PHYSICAL=1` is only for disposable test devices.

## Live Viewer

`python -m damru view` starts `scrcpy` for a live device window. This is intended for debugging, visual inspection, and manual browser operation.

Use `--no-control` when you only want to watch the device without sending keyboard, mouse, or touch events:

```bash
python -m damru view --no-control
```

Manual control can change the browser profile state, click pages, type text, or alter Android settings. Keep it separate from benchmark runs when you need clean automation results.

## Installing scrcpy

```bash
python -m damru install-viewer
python -m damru check-env --viewer
```

On native Linux, `install-viewer` installs `scrcpy` with apt. On Windows, native Windows `scrcpy` is recommended because it gives the smoothest GUI. Redroid and Docker still run inside WSL2; the viewer is only a host-side display/control tool over ADB. If a copied command from the UI contains `wsl:127.0.0.1:5600`, remove the `wsl:` prefix for native `scrcpy`; current UI builds copy the plain TCP serial on Windows automatically.

## Screenshots and Video

Screenshots and video recordings use ADB commands, not Playwright page screenshots:

- `screenshot` captures the whole Android display with `adb exec-out screencap -p`.
- `record` captures a bounded Android display video with `adb shell screenrecord` and pulls the MP4 locally.
- Android `screenrecord` is limited to 180 seconds per recording.
