# Native Layer

This directory contains native C sources and compiled shared objects used by Damru's lower-level fingerprint controls.

## Components

| File | Purpose |
| --- | --- |
| `vulkan_layer.c` / `libVkLayer_damru.so` | Vulkan layer used to replace emulator GPU/vendor strings with profile-matched mobile GPU strings. |
| `libfakemem.c` / `libfakemem.so` | Intercepts Android runtime memory queries so Chrome sees the profile's RAM size. |
| `test_mem.c`, `test_sysconf.c` | Small local probes for validating native memory interception behavior. |

## Deployment

Raw/unbaked Redroid: Damru pushes the shared objects through ADB and configures the Android environment for Chrome.

Baked image: the native layer is already integrated into `damru-redroid:latest`, reducing cold-start time and runtime failure points.

## Rule

Native changes should be tested against both main-page and worker-scope browser probes. Avoid JavaScript wrappers for values that can be controlled below the page layer.
