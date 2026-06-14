# Native Binaries (`native/`)

Welcome to the deepest layer of Damru's stealth architecture. This folder contains the **C source code and compiled shared objects (`.so`)** used for **Layer 2 (Binary)** spoofing.

> **Why native patching?**
> Anti-bot scripts like *CreepJS* and *BrowserScan* can ask the browser directly what GPU it is using. Relying on JavaScript wrappers to fake this response leaves trace evidence. Damru bypasses this entirely by physically altering the underlying Vulkan and OpenGL drivers of the Android OS.

---

## What's Inside

| File / Component | Description |
| :--- | :--- |
| **`vulkan_layer.c` / `libVkLayer_damru.so`** | A Vulkan explicit layer. When the Chromium rendering engine requests Vulkan properties, this binary intercepts the C++ system call and replaces emulator driver strings (like "SwiftShader") with real smartphone GPU strings (like "Adreno (TM) 640"). |
| **`libfakemem.c` / `libfakemem.so`** | Intercepts `sysconf` calls to spoof the total physical RAM reported by the Android OS to Chrome, allowing us to perfectly emulate the memory size of the target device profile. |
| **`test_mem.c`, `test_sysconf.c`** | Small C programs used to test the interception hooks locally within the container before applying them to the browser. |

---

## How It Is Applied

*   **Manual Deployment**: If you are using the manual/base Redroid image, Damru will automatically push these `.so` files via ADB into the Android filesystem (e.g., `/vendor/lib64/`) and configure the environment variables (`LD_PRELOAD`, `VK_INSTANCE_LAYERS`) so Chrome loads them upon launch.
*   **Instant Boot Deployment**: If you use the pre-baked [damru-redroid-latest.tar](https://github.com/akwin1234/damru/releases/download/v1.2-beta/damru-redroid-latest.tar) OS image, these binaries are *already injected permanently* into the OS, drastically speeding up boot times and reducing runtime points of failure.

*For instructions on modifying and recompiling these binaries using the NDK, see the inline comments within the `.c` source files.*
