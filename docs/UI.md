# Damru UI

Damru UI is the official local control panel for setup, checks, WSL repair, profiles, screenshots, recording, viewer launch, and live command logs.

Run it from Ubuntu/Linux or from the Damru Python environment on Windows when WSL is configured:

```bash
python -m damru ui
```

It starts a local web server and opens:

```text
http://127.0.0.1:8765
```

## Options

```bash
python -m damru ui --host 127.0.0.1 --port 8765
python -m damru ui --no-open
python -m damru ui --wsl-distro Ubuntu
```

Damru binds to localhost by default. Binding to `0.0.0.0` is intentionally explicit and prints a warning because the UI can run local setup and device commands.

## What It Can Do

- Show host, WSL, Docker, Redroid image, ADB, and APK bundle status.
- Run `setup`, `install-deps`, `check-env`, `fix-wsl`, image/APK installers, and WSL kernel status/install.
- Show live command logs with proxy/password redaction.
- List Android device profiles.
- List ADB devices.
- Start, stop, reset, and stop all `damru-worker-*` Redroid containers.
- Capture screenshots and short screen recordings.
- Launch the optional scrcpy viewer with or without input control.

## Safety

- Localhost only by default.
- No telemetry.
- No credentials saved by the UI.
- Proxy credentials and password-like assignments are redacted in job logs and JSON responses.
- WSL kernel install still requires the existing CLI confirmation flags internally.

## Scope

This is a control panel, not a no-code task builder yet. It does not store accounts, run cloud jobs, or expose a public API. Python API users should still use `AsyncDamru`, `Damru`, or `DamruPool` directly for automation logic.
