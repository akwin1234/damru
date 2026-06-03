# 🧰 Tools & Assets (`tools/`)

This directory contains external tools, assets, and third-party binaries used exclusively for debugging or managing the Android environment during research and development.

---

## 🛠️ Contents

### `magisk.apk`

Provided for developers who wish to manually explore the Redroid container, debug root access, or install custom Magisk modules during research phases.

> **Note:** The normal baked-image flow does not require users to provide Magisk. Damru uses Redroid's native `su` binary, and the baked image contains the prepared runtime pieces. On raw/manual images, Damru may use `tools/magisk.apk` as a fallback source for extracting `resetprop` if the Android image does not already provide it. The APK is kept out of Git because it is a large third-party binary; keep it as a local/release asset when you need raw-image development.

---

*Do not commit sensitive keys or large unmodified third-party binaries here unless absolutely necessary for the build pipeline.*
