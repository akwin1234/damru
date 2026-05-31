# 🛠️ Scripts (`scripts/`)

This directory contains standalone utility scripts for maintaining and deploying the Damru infrastructure.

---

## 🧰 Available Scripts

### `bake_image.py`

This is the most critical infrastructure script. It takes a base `redroid` Android Docker image, boots it up, and applies all of Damru's modifications permanently. 

**What it does:**
1. Installs the Chrome APKs (from `chrome-apks/`).
2. Injects the native C binaries (from `native/`).
3. Configures Android TTS engines.
4. "Commits" the running container into a brand new `.tar` image.

> **Result:** By using `bake_image.py`, you generate the [damru-redroid-latest.tar](https://drive.google.com/file/d/1na6YYHbpvDlaXhicg_nAKiaMFaYRN99U/view?usp=sharing) file. This turns a slow 2-minute container setup into an instant 3-second boot for your scaling operations!

---

## 🚀 Usage

```bash
python scripts/bake_image.py --help
```
*(Ensure Docker is running and you have sufficient disk space before baking images).*