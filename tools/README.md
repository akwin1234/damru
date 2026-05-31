# 🧰 Tools & Assets (`tools/`)

This directory contains external tools, assets, and third-party binaries used exclusively for debugging or managing the Android environment during research and development.

---

## 🛠️ Contents

### `magisk.apk`

Provided for developers who wish to manually explore the Redroid container, debug root access, or install custom Magisk modules during research phases.

> **Note:** Damru does *not* require Magisk at runtime. The framework utilizes Redroid's native `su` binary. However, having Magisk is highly useful for reverse-engineering anti-bot systems, inspecting TLS traffic via system certificates, or hooking Java methods directly on the emulator.

---

*Do not commit sensitive keys or large unmodified third-party binaries here unless absolutely necessary for the build pipeline.*