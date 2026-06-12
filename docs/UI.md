# Damru Local UI

Damru includes an experimental localhost dashboard for setup, worker management, manual browser inspection, screenshots, logs, gallery review, and quick troubleshooting.

```bash
python -m damru ui
```

Open the printed `http://127.0.0.1:<port>` URL in your browser. The default bind address is `127.0.0.1`; do not bind it publicly unless you add your own access control around it.

> **Experimental:** use the Python API and CLI for production automation. The UI is best for setup, debugging, visual inspection, and learning what Damru is doing.

## Routes

| Page | URL | Purpose |
| --- | --- | --- |
| Dashboard | `/` | Host health, worker count, ADB count, recent jobs, visible setup issues. |
| Setup | `/setup` | First-run checks and install/repair actions. |
| Workers | `/workers` | Redroid container lifecycle and per-worker actions. |
| Work Lab | `/work` | URL launch, stealth checks, screenshots, browser viewer, gallery. |
| Work Lab alias | `/viewer`, `/work-lab` | Same page as Work Lab. |
| Settings | `/settings` | Safe config editor, backups, WSL kernel controls. |
| Logs | `/logs` | Job list, output, statuses, and clear logs. |

## Dashboard

The dashboard summarizes system health without exposing secrets. Passing checks collapse by default so warnings and failures stay visible.

Shows:

- supported host status
- Python and Damru version
- WSL distro and kernel when running from Windows
- Docker, binderfs, image, APK, ADB, Playwright patch, viewer, disk/RAM status
- worker count and booted worker count
- ADB online device count
- recent UI jobs and latest job output shortcut
- critical warnings and quick repair button when available

![Damru UI dashboard](assets/ui/dashboard.png)

## Setup

The setup page groups first-run tasks in the order a new machine normally needs them.

Actions:

- **Check environment**: runs `python -m damru check-env` style validation.
- **Install dependencies**: installs Linux/WSL packages such as Docker, ADB, curl, wget, jq, iptables, and module tooling.
- **Repair runtime**: runs safe Docker, binderfs, iptables, NAT, DNS, and WSL route repair paths.
- **Install APK bundle**: downloads/extracts Chrome, matching per-version WebView, TTS, RHVoice, eSpeak, and Magisk/resetprop assets when needed.
- **Install Redroid image**: loads or downloads the baked `damru-redroid:latest` image.
- **Install native viewer**: installs/checks optional `scrcpy` tooling.

The UI shows WSL-specific controls only on Windows. Native Ubuntu users see native Linux actions instead.

![Damru UI setup page](assets/ui/setup.png)

## Workers

The workers page manages Damru Redroid containers and ADB workers. It does not intentionally touch unrelated Docker containers.

Worker rows are paginated and searchable. When Docker workers exist but ADB is still reconnecting, Work Lab shows that state explicitly instead of claiming no worker exists.

Top actions:

- **Start all**: starts existing stopped Damru workers, or starts the configured worker count when none exist.
- **Add workers**: adds the requested number of new workers using the next free indexes.
- **Fix internet all**: repairs host/WSL/Docker/Android DNS and routing for reachable workers.
- **Refresh ADB**: refreshes the ADB device list.
- **Stop all**: stops Damru workers without deleting their containers.
- **Delete all**: removes Damru worker containers.

Per-worker actions:

- **Viewer**: opens the selected worker in Work Lab viewer.
- **Work**: selects the worker in Work Lab for browser actions.
- **Fix internet**: repairs DNS/routing for that worker.
- **Random profile**: applies a new random Android profile, timezone/locale, screen, Chrome settings, and rotates Chrome plus matching WebView from the APK bundle when available.
- **Stealth checker**: runs proof/stealth checks for that worker.
- **Restart**: restarts the worker container.
- **Stop**: pauses the worker container.
- **Delete**: removes the worker container.

![Damru UI workers page](assets/ui/workers.png)

## Work Lab

Work Lab is the manual browser and viewer workspace. It is useful for debugging one worker at a time.

Browser actions:

- select an ADB serial
- open a URL through Damru's default `stealth-open-url --mode reattach` path: apply stealth, detach CDP for the first navigation, open with Android Chrome, then reattach CDP for inspection and manual automation
- optionally provide `socks5://user:pass@host:port`, `http://user:pass@host:port`, or `host:port` proxy format
- fix internet for the selected worker
- apply a random profile to the selected worker
- run **Quick checker** for fast Android/Chrome sanity
- run **Full checker** for proof targets and screenshots
- capture a screenshot
- run **Random profile all** across workers
- run **Stealth checker all** sequentially across workers

Viewer actions:

- open browser-based live viewer
- enable/disable mouse and keyboard control
- set max viewer size for faster frame updates
- capture screenshot
- record 15 seconds
- copy native `scrcpy` command for smoother viewing
- send text through the text box
- send Back, Home, and Recent keys

Gallery actions:

- reload local captures
- open screenshots/recordings/proof folders
- clear the local UI gallery folder

![Damru UI Work Lab](assets/ui/work-lab.png)

## Settings

Settings edits only selected safe Damru config keys. The UI creates a backup before saving.

Editable/readable areas include:

- mode
- worker count
- WSL distro and username
- Redroid image tag
- Chrome APK path
- Redroid base port
- other allowlisted local config values exposed by the UI backend

Buttons:

- **Save config**: validates and writes selected keys.
- **Reload**: reloads config from disk.
- **Restore latest backup**: restores the newest UI-created config backup.
- **Kernel status**: checks bundled/active WSL kernel state.
- **Install WSL kernel**: Windows-only danger action. It requires typing `yes` because it changes Windows `.wslconfig`.

![Damru UI settings page](assets/ui/settings.png)

## Logs

Logs tracks UI jobs started from buttons. Use it when a button shows an error, when setup is slow, or when you need sanitized output for debugging.

Job history is paginated so long setup/debug sessions stay usable.

Shows:

- job name
- queued/running/success/failed status
- duration
- exit code
- summarized output
- full log drawer

Actions:

- open a job log
- retry by running the original UI action again where available
- clear finished log records

![Damru UI logs page](assets/ui/logs.png)

## Safety Model

- The UI backend is local-only by default.
- Backend actions are allowlisted; the browser cannot submit arbitrary shell commands.
- Proxy URLs and credentials are redacted from logs where possible.
- Physical USB ADB devices are not selected automatically by Damru.
- Stop and Delete are separate: Stop pauses a worker, Delete removes the container.
- WSL kernel installation is intentionally high-friction and requires explicit `yes`.

## When To Use CLI Instead

Use CLI/Python directly for repeatable automation, CI, fleet checks, and production scraping tasks:

```bash
python -m damru check preflight --json --timeout 3
python -m damru check-env
python -m damru quick-check --serial 127.0.0.1:5600
python -m damru open-url --serial 127.0.0.1:5600 --url https://example.com
```

Use `AsyncDamru`, `Damru`, or `DamruPool` for real automation code. The UI is a control panel, not the primary automation API.

## Screenshot Capture

The screenshots in this file were captured from the local UI at desktop size with Playwright. They are stored in `docs/assets/ui/` and are safe to include in README/docs.


## Experimental Backend Flags

The UI backend respects the same DAMRU_EXPERIMENTAL_* env vars as the CLI. Set them before starting the UI:

`ash
export DAMRU_EXPERIMENTAL_SENSOR_HAL=1   # enable native sensor HAL
python -m damru ui
`

See README.md **Experimental Features** for the full list.
