# Damru Automation Gaps - Complete Analysis & Fix Plan

**Date**: 2026-02-18
**Status**: Partially implemented. The CLI setup/check/install path now exists; this document is retained as the broader automation roadmap.
**Priority**: High - Make damru fully automated from A to Z

---

## What Damru ALREADY Does (Good!)

| Feature | Status | Location |
|---------|--------|----------|
| Auto-install Docker |  | docker.py:287-317 |
| Auto-create containers |  | docker.py:342-387 |
| Auto-load kernel modules |  | docker.py:202-221 |
| Auto-mount binderfs |  | docker.py:223-246 |
| Auto-start Docker daemon |  | docker.py:180-195 |
| Auto-detect WSL distro |  | docker.py:257-285 |

---

## CRITICAL GAPS - What's Missing

### 1. Image Management (BIGGEST ISSUE)

**Current code (docker.py line 470):**
```python
# Just assumes image exists - no check!
await self._run_cmd(
    self._docker_cmd("run", "-d", ..., REDROID_IMAGE, ...),  #  No check!
)
```

**Missing:**
-  No `docker pull` logic
-  No image existence check
-  No fallback to `redroid/redroid:14.0.0_64only-latest` if baked image missing
-  No version/tag management

**Impact**: Crashes on first run if image not present!

---

### 2. Storage Location (WSL, NOT HDD!)

**Current**: Images stored in WSL2 virtual disk
```bash
Docker Root Dir: /var/lib/docker   Inside WSL!
```

**WSL2 disk location**: `C:\Users\<User>\AppData\Local\Packages\CanonicalGroupLimited.Ubuntu_...`
-  Uses limited VHD space
-  Can't be easily backed up
-  Not in damru directory

**Desired**: Images in `C:\path\to\damru\images\`

**Solution needed**: Configure Docker root dir to Windows path via WSL mount

---

### 3. Setup CLI / Installer

**Current status:**
- `damru` console entry point exists.
- `python -m damru setup` writes config and can run dependency setup.
- `python -m damru check-env` verifies Linux/WSL tools, Docker, binderfs, Chrome APKs, Redroid image state, and the Damru Playwright `crPage.js` patch.
- `python -m damru install-deps` installs common Linux/WSL dependencies.
- `python -m damru fix-wsl` retries safe Docker, binderfs, and netfilter fixes and reports missing WSL kernel modules clearly.
- Optional visual commands exist for manual inspection: `screenshot`, `record`, `view`, and `install-viewer`.
- On Windows, Docker/Redroid setup runs inside WSL with `wsl -u root`; native Windows Docker is not used.

**Current commands:**
```bash
python -m damru setup
python -m damru check-env
python -m damru install-deps
python -m damru fix-wsl
python -m damru bake-image
python -m damru devices
python -m damru screenshot
python -m damru record
python -m damru view
python -m damru install-viewer
```

---

### 4. No Dependency Management

**Missing checks for:**
-  ADB installed
-  Python packages (playwright, etc.)
-  Chrome APK availability
-  WSL2 kernel version (partially covered by `check-env` and `fix-wsl` when Docker/netfilter modules are missing)
-  Sufficient disk space
-  Network connectivity

---

### 5. No Image Auto-Pull on First Run

**Current behavior:**
1. User runs `AsyncDamru()`
2. `ensure_container()` -> `start_container()`
3. `docker run damru-redroid:latest`  Image doesn't exist!
4. **CRASH**: `docker: Error response from daemon: No such image`

**Should be:**
1. Check if image exists
2. If not, pull `redroid/redroid:14.0.0_64only-latest`
3. Or run `bake_image.py` automatically
4. Or prompt user with helpful message

---

## COMPREHENSIVE FIX PLAN

### Phase 1: Image Management (HIGH PRIORITY)

**Create `damru/damru/images.py`:**

```python
"""Docker image management and auto-pull logic."""
import asyncio
from typing import Optional
from .utils import logger
from .config import REDROID_IMAGE


class ImageManager:
    """Manage Docker images: check existence, pull, bake."""

    def __init__(self, docker_manager):
        self._docker = docker_manager

    async def ensure_image(self, image: str) -> bool:
        """Ensure Docker image exists. Auto-pull if missing.

        Returns True if image is available, raises DamruError if not.
        """
        if await self._image_exists(image):
            logger.info("Image %s already exists", image)
            return True

        logger.warning("Image %s not found locally", image)

        # Special handling for baked damru image
        if image == "damru-redroid:latest":
            return await self._pull_or_bake()
        else:
            return await self._pull_image(image)

    async def _image_exists(self, image: str) -> bool:
        """Check if Docker image exists locally."""
        try:
            out = await self._docker._run_cmd(
                self._docker._docker_cmd("images", "-q", image),
                timeout=10,
            )
            return bool(out.strip())
        except Exception:
            return False

    async def _pull_image(self, image: str) -> bool:
        """Pull Docker image from registry."""
        logger.info("Pulling image %s...", image)
        try:
            await self._docker._run_cmd(
                self._docker._docker_cmd("pull", image),
                timeout=600,  # 10 minutes for large images
            )
            logger.info("Successfully pulled %s", image)
            return True
        except Exception as e:
            logger.error("Failed to pull %s: %s", image, e)
            return False

    async def _pull_or_bake(self) -> bool:
        """Pull base redroid or bake custom image.

        Strategy:
        1. Try pulling base redroid image
        2. If success, offer to bake custom image (optional)
        3. If fail, show error with manual instructions
        """
        base_image = "redroid/redroid:14.0.0_64only-latest"

        # Try pulling base image
        logger.info("Baked image not found. Pulling base image %s...", base_image)
        if await self._pull_image(base_image):
            logger.info(
                "Base image pulled successfully.\n"
                "  To create optimized baked image, run:\n"
                "    python bake_image.py"
            )
            # Tag base image as damru-redroid:latest for now
            await self._docker._run_cmd(
                self._docker._docker_cmd("tag", base_image, "damru-redroid:latest"),
                timeout=10,
            )
            return True

        # Pull failed - show manual instructions
        from .errors import DamruError
        raise DamruError(
            f"Failed to pull base image {base_image}.\n"
            "Manual steps:\n"
            "  1. Pull base image: docker pull redroid/redroid:14.0.0_64only-latest\n"
            "  2. (Optional) Bake custom image: python bake_image.py\n"
            "  3. Or tag base as latest: docker tag redroid/redroid:14.0.0_64only-latest damru-redroid:latest"
        )
```

**Integrate into `docker.py`:**

```python
# In DockerManager.__init__:
from .images import ImageManager

def __init__(self, wsl_distro: Optional[str] = None):
    # ... existing code ...
    self._images = ImageManager(self)

# In start_container():
async def start_container(self, index: int) -> str:
    """Start one redroid container and return its ADB serial."""
    name = f"{REDROID_CONTAINER_PREFIX}{index}"
    port = REDROID_BASE_PORT + index

    # ADD THIS: Ensure image exists before docker run
    await self._images.ensure_image(REDROID_IMAGE)

    # Remove leftover container with same name
    await self._run_cmd(
        self._docker_cmd("rm", "-f", name),
        timeout=10, allow_failure=True,
    )

    # ... rest of existing code ...
```

---

### Phase 2: Storage Location Fix (HIGH PRIORITY)

**Option A: Symlink WSL Docker to Windows HDD**

```bash
# Commands to run in WSL:
sudo service docker stop
sudo mv /var/lib/docker /mnt/c/path/to/damru/docker-data
sudo ln -s /mnt/c/path/to/damru/docker-data /var/lib/docker
sudo service docker start
```

**Option B: Docker daemon.json config**

Create `/etc/docker/daemon.json` in WSL:
```json
{
  "data-root": "/mnt/c/path/to/damru/docker-data"
}
```

**Add to `docker.py`:**

```python
async def configure_storage_location(self, windows_path: str) -> None:
    """Configure Docker to use Windows HDD for storage instead of WSL VHD.

    Args:
        windows_path: Windows path like "C:\\path\\to\\damru\\docker-data"
    """
    # Convert Windows path to WSL mount path
    wsl_path = windows_path.replace("\\", "/").replace("C:", "/mnt/c")

    logger.info("Configuring Docker storage location: %s", windows_path)

    # 1. Stop Docker
    await self._run_cmd(
        self._wsl_sudo_cmd("service docker stop"),
        timeout=30,
    )

    # 2. Create target directory on Windows
    import os
    os.makedirs(windows_path, exist_ok=True)

    # 3. Move existing Docker data if present
    move_cmd = (
        f"if [ -d /var/lib/docker ]; then "
        f"rsync -a /var/lib/docker/ {wsl_path}/ && "
        f"rm -rf /var/lib/docker; "
        f"fi"
    )
    await self._run_cmd(
        self._wsl_sudo_cmd(move_cmd),
        timeout=300,  # Can be slow for large data
    )

    # 4. Create symlink
    await self._run_cmd(
        self._wsl_sudo_cmd(f"ln -s {wsl_path} /var/lib/docker"),
        timeout=10,
    )

    # 5. Restart Docker
    await self._run_cmd(
        self._wsl_sudo_cmd("service docker start"),
        timeout=30,
    )

    logger.info("Docker storage configured successfully")
```

**Add to config.py:**

```python
# Docker Storage Location
# None = default WSL location (/var/lib/docker)
# Set to Windows path to store images on HDD instead of WSL VHD
DOCKER_STORAGE_PATH = None  # e.g. "C:\\path\\to\\damru\\docker-data"
```

---

### Phase 3: Setup CLI (MEDIUM PRIORITY)

**Create `damru/damru/cli.py`:**

```python
"""Command-line interface for damru setup and management."""
import argparse
import asyncio
import sys
from pathlib import Path

from .docker import DockerManager
from .config import DOCKER_STORAGE_PATH
from .utils import setup_logging, logger


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="damru",
        description="Damru - Stealth Android browser automation"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # damru setup
    setup_parser = subparsers.add_parser(
        "setup",
        help="One-command setup: install Docker, configure storage, pull images"
    )
    setup_parser.add_argument(
        "--storage",
        help="Docker storage path on Windows HDD (e.g. C:\\damru\\docker-data)"
    )
    setup_parser.add_argument(
        "--skip-image",
        action="store_true",
        help="Skip image pull/bake"
    )

    # damru check
    check_parser = subparsers.add_parser(
        "check",
        help="Verify all dependencies and configuration"
    )

    # damru pull-image
    pull_parser = subparsers.add_parser(
        "pull-image",
        help="Pull or bake Docker image"
    )
    pull_parser.add_argument(
        "--bake",
        action="store_true",
        help="Bake custom image instead of using base"
    )

    # damru test
    test_parser = subparsers.add_parser(
        "test",
        help="Run quick smoke test"
    )

    # damru storage
    storage_parser = subparsers.add_parser(
        "storage",
        help="Configure Docker storage location"
    )
    storage_parser.add_argument(
        "path",
        help="Windows path for Docker data"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    setup_logging(True)

    # Run command
    if args.command == "setup":
        asyncio.run(cmd_setup(args))
    elif args.command == "check":
        asyncio.run(cmd_check(args))
    elif args.command == "pull-image":
        asyncio.run(cmd_pull_image(args))
    elif args.command == "test":
        asyncio.run(cmd_test(args))
    elif args.command == "storage":
        asyncio.run(cmd_storage(args))


async def cmd_setup(args):
    """Full setup: Docker, storage, images."""
    logger.info("Starting damru setup...")

    docker = DockerManager()

    # 1. Check/install Docker
    logger.info("Step 1/3: Checking Docker...")
    await docker.check_docker()

    # 2. Configure storage if requested
    if args.storage or DOCKER_STORAGE_PATH:
        storage_path = args.storage or DOCKER_STORAGE_PATH
        logger.info("Step 2/3: Configuring storage location...")
        await docker.configure_storage_location(storage_path)
    else:
        logger.info("Step 2/3: Using default WSL storage (skip with --storage)")

    # 3. Pull/bake image
    if not args.skip_image:
        logger.info("Step 3/3: Pulling Docker image...")
        await docker._images.ensure_image("damru-redroid:latest")
    else:
        logger.info("Step 3/3: Skipped image pull")

    logger.info("Setup complete! Run 'damru test' to verify.")


async def cmd_check(args):
    """Verify all dependencies."""
    logger.info("Checking damru dependencies...")

    checks = {}
    docker = DockerManager()

    # Check Docker
    try:
        await docker.check_docker()
        checks["docker"] = "OK"
    except Exception as e:
        checks["docker"] = f"FAIL: {e}"

    # Check image
    try:
        exists = await docker._images._image_exists("damru-redroid:latest")
        checks["image"] = "OK" if exists else "WARN: not found (run: damru pull-image)"
    except Exception as e:
        checks["image"] = f"FAIL: {e}"

    # Check ADB
    try:
        out = await docker._run_cmd(["adb", "version"], timeout=5)
        checks["adb"] = "OK" if "Android Debug Bridge" in out else "FAIL"
    except Exception:
        checks["adb"] = "FAIL: not installed"

    # Print results
    print("\nDependency Check Results:")
    print("=" * 50)
    for name, status in checks.items():
        print(f"  {name:20s} {status}")

    all_ok = all(s == "OK" for s in checks.values())
    if all_ok:
        print("\nAll checks passed! Ready to use damru.")
    else:
        print("\nSome checks failed. Run 'damru setup' to fix.")
        sys.exit(1)


async def cmd_pull_image(args):
    """Pull or bake image."""
    docker = DockerManager()

    if args.bake:
        logger.info("Baking custom image...")
        # Import and run bake_image
        from ..bake_image import main as bake_main
        bake_main()
    else:
        logger.info("Pulling image...")
        await docker._images.ensure_image("damru-redroid:latest")


async def cmd_test(args):
    """Quick smoke test."""
    logger.info("Running smoke test...")

    # Import and run smoke test
    from ..tests.test_smoke import main as test_main
    await test_main()


async def cmd_storage(args):
    """Configure storage location."""
    docker = DockerManager()
    await docker.configure_storage_location(args.path)
    logger.info("Storage configured. Restart containers to take effect.")


if __name__ == "__main__":
    main()
```

**Update `setup.py` or `pyproject.toml`:**

```python
# In setup.py:
entry_points={
    'console_scripts': [
        'damru=damru.cli:main',
    ],
}

# Or in pyproject.toml:
[project.scripts]
damru = "damru.cli:main"
```

---

### Phase 4: Health Check System (MEDIUM PRIORITY)

**Create `damru/damru/health.py`:**

```python
"""Comprehensive health check for damru dependencies."""
import asyncio
import shutil
from typing import Dict, Optional
from pathlib import Path

from .docker import DockerManager
from .utils import logger


class HealthCheck:
    """Comprehensive health check for all damru dependencies."""

    def __init__(self):
        self._docker = DockerManager()

    async def check_all(self) -> Dict[str, dict]:
        """Run all health checks.

        Returns dict with check results:
        {
            "wsl2": {"status": "ok", "message": "WSL2 Ubuntu available"},
            "docker": {"status": "error", "message": "Docker not installed"},
            ...
        }
        """
        checks = {}

        # Run all checks in parallel
        results = await asyncio.gather(
            self._check_wsl2(),
            self._check_docker(),
            self._check_adb(),
            self._check_image(),
            self._check_kernel(),
            self._check_disk_space(),
            self._check_network(),
            self._check_python_packages(),
            return_exceptions=True,
        )

        check_names = [
            "wsl2", "docker", "adb", "image",
            "kernel", "disk_space", "network", "python_packages"
        ]

        for name, result in zip(check_names, results):
            if isinstance(result, Exception):
                checks[name] = {"status": "error", "message": str(result)}
            else:
                checks[name] = result

        return checks

    async def _check_wsl2(self) -> dict:
        """Check WSL2 availability."""
        try:
            import sys
            if sys.platform != "win32":
                return {"status": "skip", "message": "Not on Windows"}

            out = await self._docker._run_cmd(
                ["wsl", "--list", "--quiet"],
                timeout=10,
            )
            distros = [
                line.strip()
                for line in out.replace("\x00", "").splitlines()
                if line.strip()
            ]

            if distros:
                return {
                    "status": "ok",
                    "message": f"WSL2 available: {', '.join(distros)}"
                }
            else:
                return {
                    "status": "error",
                    "message": "No WSL2 distros found. Run: wsl --install -d Ubuntu"
                }
        except Exception as e:
            return {"status": "error", "message": f"WSL2 not available: {e}"}

    async def _check_docker(self) -> dict:
        """Check Docker installation and daemon."""
        try:
            out = await self._docker._run_cmd(
                self._docker._docker_cmd("info", "--format", "{{.OSType}}"),
                timeout=15,
            )
            if "linux" in out.lower():
                return {"status": "ok", "message": "Docker running"}
            else:
                return {"status": "error", "message": "Docker not responding"}
        except Exception as e:
            return {"status": "error", "message": f"Docker not available: {e}"}

    async def _check_adb(self) -> dict:
        """Check ADB installation."""
        if shutil.which("adb"):
            try:
                out = await self._docker._run_cmd(
                    ["adb", "version"],
                    timeout=5,
                )
                return {"status": "ok", "message": "ADB available"}
            except Exception as e:
                return {"status": "warning", "message": f"ADB found but not working: {e}"}
        else:
            return {"status": "error", "message": "ADB not installed"}

    async def _check_image(self) -> dict:
        """Check Docker image availability."""
        try:
            exists = await self._docker._images._image_exists("damru-redroid:latest")
            if exists:
                return {"status": "ok", "message": "damru-redroid:latest available"}
            else:
                return {
                    "status": "warning",
                    "message": "Image not found. Run: damru pull-image"
                }
        except Exception as e:
            return {"status": "error", "message": f"Image check failed: {e}"}

    async def _check_kernel(self) -> dict:
        """Check WSL2 kernel version and binder support."""
        try:
            # Check kernel version
            out = await self._docker._run_cmd(
                self._docker._wsl_cmd("uname", "-r"),
                timeout=5,
            )
            version = out.strip()

            # Check binder support
            binder_check = await self._docker._run_cmd(
                self._docker._wsl_sudo_cmd("grep CONFIG_ANDROID_BINDER_IPC /boot/config-* 2>/dev/null || echo NOTFOUND"),
                timeout=5,
                allow_failure=True,
            )

            has_binder = "CONFIG_ANDROID_BINDER_IPC=y" in binder_check

            if has_binder:
                return {
                    "status": "ok",
                    "message": f"Kernel {version} with binder support"
                }
            else:
                return {
                    "status": "warning",
                    "message": f"Kernel {version} - binder support unknown"
                }
        except Exception as e:
            return {"status": "error", "message": f"Kernel check failed: {e}"}

    async def _check_disk_space(self) -> dict:
        """Check available disk space."""
        try:
            # Check WSL disk space
            out = await self._docker._run_cmd(
                self._docker._wsl_cmd("df", "-h", "/var/lib/docker"),
                timeout=5,
                allow_failure=True,
            )

            # Parse available space (rough check)
            lines = out.splitlines()
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 4:
                    available = parts[3]
                    return {
                        "status": "ok",
                        "message": f"Docker storage: {available} available"
                    }

            return {"status": "warning", "message": "Could not determine disk space"}
        except Exception as e:
            return {"status": "error", "message": f"Disk space check failed: {e}"}

    async def _check_network(self) -> dict:
        """Check network connectivity."""
        try:
            # Try pinging Docker Hub
            out = await self._docker._run_cmd(
                ["ping", "-c", "1", "-W", "2", "registry-1.docker.io"],
                timeout=5,
                allow_failure=True,
            )

            if "1 received" in out or "1 packets received" in out:
                return {"status": "ok", "message": "Network connectivity OK"}
            else:
                return {
                    "status": "warning",
                    "message": "Network connectivity issues"
                }
        except Exception:
            return {"status": "warning", "message": "Network check inconclusive"}

    async def _check_python_packages(self) -> dict:
        """Check required Python packages."""
        missing = []

        try:
            import playwright
        except ImportError:
            missing.append("playwright")

        if missing:
            return {
                "status": "error",
                "message": f"Missing packages: {', '.join(missing)}"
            }
        else:
            return {"status": "ok", "message": "All Python packages available"}
```

---

### Phase 5: Auto-Setup on First Run (LOW PRIORITY)

**Add to `async_core.py`:**

```python
class AsyncDamru:
    async def __aenter__(self) -> BrowserContext:
        # ADD THIS at the very start:
        if not await self._is_setup_complete():
            logger.info("First-time setup required...")
            await self._run_first_time_setup()

        setup_logging(self._debug)
        # ... rest of existing code ...

    async def _is_setup_complete(self) -> bool:
        """Check if damru has been set up before."""
        # Check for marker file
        marker = Path.home() / ".damru" / "setup_complete"
        return marker.exists()

    async def _run_first_time_setup(self) -> None:
        """Run first-time setup automatically."""
        from .docker import DockerManager
        from .config import DOCKER_STORAGE_PATH

        logger.info("Running first-time setup...")

        docker = DockerManager()

        # 1. Check Docker
        await docker.check_docker()

        # 2. Configure storage if set
        if DOCKER_STORAGE_PATH:
            await docker.configure_storage_location(DOCKER_STORAGE_PATH)

        # 3. Ensure image
        await docker._images.ensure_image("damru-redroid:latest")

        # 4. Mark setup complete
        marker = Path.home() / ".damru"
        marker.mkdir(exist_ok=True)
        (marker / "setup_complete").touch()

        logger.info("First-time setup complete!")
```

---

## IMPLEMENTATION PRIORITY

### Must Have (Phase 1-2):
1.  Image existence check + auto-pull
2.  Docker storage location configuration

### Should Have (Phase 3):
3.  Setup CLI (`damru setup`, `damru check`)

### Nice to Have (Phase 4-5):
4.  Health check system
5.  Auto-setup on first run

---

## ESTIMATED EFFORT

| Phase | Time | Complexity |
|-------|------|------------|
| Phase 1: Image Management | 20 min | Low |
| Phase 2: Storage Location | 25 min | Medium |
| Phase 3: Setup CLI | 30 min | Medium |
| Phase 4: Health Check | 45 min | High |
| Phase 5: Auto-Setup | 15 min | Low |
| **Total** | **~2.5 hours** | - |

---

## NEXT STEPS

When ready to implement:
1. Start with Phase 1 (image management) - highest impact
2. Then Phase 2 (storage location) - user's main concern
3. Then Phase 3 (setup CLI) - better UX
4. Optional: Phases 4-5 for polish

---

**Status**: Document saved, awaiting user decision to proceed with implementation.
