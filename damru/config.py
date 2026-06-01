"""Damru configuration - single source of truth for all settings.

Edit values here. They are used across pool, docker, and auto-install.
"""

# Pool Defaults
# "auto" = spin up redroid Docker containers (WSL2 on Windows, native Linux)
# "mumu" = auto-manage MuMu instances via MuMuManager.exe
# "manual" = use existing ADB devices (MuMu instances, phones)
MODE = "auto"
# Number of concurrent browser instances (= containers in auto mode)
# Set this to match your bot's thread count (e.g. 30 threads = 30 devices)
NUM_DEVICES = 1
# Fixed device name (e.g. "galaxy_s24_ultra"), or None = random per session
DEVICE = None

# Proxy Configuration
# Single proxy shared by all workers (set one or the other, not both)
PROXY = None                   # SOCKS5: "socks5://host:port"
HTTP_PROXY = None              # HTTP for Android system: "host:port"
# Per-worker proxy lists (round-robin if fewer than NUM_DEVICES)
PROXIES = None                 # ["socks5://host1:port", "socks5://host2:port"]
HTTP_PROXIES = None            # ["host1:port", "host2:port"]

# Location
TIMEZONE = None                # IANA timezone (e.g. "Asia/Manila"), auto from proxy if None
LOCALE = None                  # BCP-47 locale (e.g. "fil-PH"), auto from timezone if None

# Chrome APK
# Path to APK file or split-APK directory. None = auto-search in chrome-apks/
CHROME_APK = None

# WSL2 Configuration (Windows only, for redroid auto mode)
WSL_DISTRO = "Ubuntu"
WSL_USERNAME = "YOUR_WSL_USERNAME_HERE"
WSL_PASSWORD = "YOUR_WSL_PASSWORD_HERE"

# MuMu Configuration (Windows only, for mode="mumu")
# Path to MuMuManager.exe. None = auto-detect common paths.
MUMU_MANAGER_PATH = None
# Optional explicit MuMu instance indices (e.g. [1,2,3]); None = auto-pick
MUMU_INSTANCE_INDICES = None
# Auto-create missing instances if NUM_DEVICES exceeds available instances
MUMU_AUTO_CREATE = False
# Enforce MuMu VM resources in auto mode
MUMU_CPU = 2                   # minimum proven stable baseline
MUMU_MEMORY_GB = 1             # keep memory low where possible
MUMU_STRICT_RESOURCE_LIMIT = True  # enforce baseline, then step fallback on boot loops
MUMU_BOOT_FALLBACK_CPU = 2
MUMU_BOOT_FALLBACK_MEMORY_GB = 2
# Baseline MuMu settings applied in mode="mumu"
MUMU_SYSTEM_DISK_WRITABLE = True
# Optional overrides (None = dynamic from selected device profile each session)
MUMU_GPU_MODE = None          # "low" | "middle" | "high" | "custom" | None
MUMU_GPU_MODEL = None
MUMU_PHONE_BRAND = None
MUMU_PHONE_MODEL = None
MUMU_PHONE_MIIT = None

# Redroid Container Settings
REDROID_IMAGE = "damru-redroid:latest"
# Upstream base image, pulled automatically when the baked image is absent
# (see RedroidManager.ensure_image).
REDROID_BASE_IMAGE = "redroid/redroid:14.0.0_64only-latest"
REDROID_BASE_PORT = 5600
REDROID_CONTAINER_PREFIX = "damru-worker-"
# Resources per container (2 cores + 2 GB for heavy SPAs at high resolution)
REDROID_CPUS = 2.0
REDROID_MEMORY = "2g"
# Renderer mode (redroid docs): "guest" (software), "host" (GPU passthrough), "auto"
REDROID_GPU_MODE = "guest"
# Disable setup wizard in GApps-enabled images.
REDROID_SETUPWIZARD_DISABLED = True

# Timeouts (seconds)
CONTAINER_BOOT_TIMEOUT = 90
MUMU_BOOT_TIMEOUT = 240
DOCKER_CMD_TIMEOUT = 30
APK_INSTALL_TIMEOUT = 120
SESSION_SETUP_TIMEOUT = 120    # Max time for fingerprint + Chrome launch + CDP connect

# Session Reliability
MAX_SESSION_RETRIES = 2        # Retry session setup on failure (0 = no retry)
TASK_TIMEOUT = None            # Max seconds for user code per session (None = no limit)
                               # When hit: Chrome is killed, slot freed for next task

# Health Monitoring
HEALTH_CHECK_INTERVAL = 30     # Seconds between ADB health checks (0 = disabled)
MAX_SLOT_FAILURES = 3          # Mark slot dead after N consecutive failures

# Debug
DEBUG = False
