# Damru Core Library

This directory contains the Python runtime that drives Damru sessions: Redroid startup, ADB control, Android identity patching, Chrome lifecycle, CDP attachment, proxy-aware profile shaping, and multi-worker pools.

## Core Modules

| Module | Role |
| --- | --- |
| `async_core.py` | Primary async browser entry point. |
| `core.py` | Synchronous wrapper around the async runtime. |
| `pool.py` | Multi-container orchestration through `DamruPool`. |
| `devices.py` | 49 real Android device profiles. |
| `chrome.py` | Chrome/WebView lifecycle, preferences, flags, first-run cleanup. |
| `root.py` | Android root operations, props, iptables, display, native patching. |
| `proxy.py` | Proxy parsing plus IP-aware timezone and locale selection. |
| `cdp.py` | Chrome DevTools Protocol attachment and port routing. |
| `cli.py` | `python -m damru` setup, checks, WSL repair, viewer, image/APK commands. |
| `playwright_patch/` | Bundled Playwright `crPage.js` runtime patch. |
| `wsl_kernel/` | Bundled WSL2 kernel artifact and metadata. |

## Design Rule

Damru avoids JavaScript monkey-patching for core stealth. Prefer Android, native, browser-engine, CDP, or container-level fixes before adding any page script behavior.
