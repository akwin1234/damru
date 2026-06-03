<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# You are a senior Linux kernel, Docker networking, WSL2, and Android/Redroid infrastructure expert.

I need a deep research investigation, not a shallow answer. Search broadly across at least 1,000+ relevant web sources
 if possible, including official docs, GitHub issues, kernel mailing lists, Docker/Moby issues, WSL issues, Redroid
 issues, StackOverflow answers, blog posts, forum threads, distro bug trackers, Reddit/HN discussions, and real-world
 troubleshooting writeups.

Research target:
 Fix or definitively explain why Docker/Redroid multi-container networking and Android iptables do not work inside
 stock WSL2, without using a custom WSL kernel.

Important requirement:
 I do NOT want to use a custom WSL kernel unless absolutely proven unavoidable. Find every possible no-custom-kernel
 fix or workaround first.

Environment:
 - Host: Windows
 - WSL distro: Ubuntu 26.04 LTS
 - WSL kernel: 6.6.114.1-microsoft-standard-WSL2+
 - Docker runs inside WSL/Linux, not native Windows Docker.
 - Redroid must run inside Linux/WSL, not directly on Windows.
 - Redroid image: damru-redroid:latest, based on Redroid Android 14 x86_64.
 - Goal: run multiple Redroid containers concurrently, each with ADB/browser automation.
 - Single Redroid worker currently works only with Docker host-network fallback.
 - Need multi-worker support if possible.

Current working fallback:
 ```bash
 dockerd --iptables=false --ip6tables=false --bridge=none --host=unix:///var/run/docker.sock

With that fallback:

- Docker starts.
 - One Redroid container starts with --network host.
 - ADB connects to WSL IP port 5555, e.g.:

adb connect 172.27.165.70:5555

- One browser automation session works.

Current major failures:

1. Normal Docker bridge/NAT mode fails.

Command:

dockerd --host=unix:///var/run/docker.sock

With nft iptables backend, Docker fails:

failed to start daemon: Error initializing network controller:
 failed to register "bridge" driver:
 failed to add jump rules to ipv4 NAT table:
 failed to append jump rules to nat-PREROUTING:
 iptables --wait -t nat -A PREROUTING -m addrtype --dst-type LOCAL -j DOCKER:
 Warning: Extension addrtype revision 0 not supported, missing kernel module
 iptables v1.8.11 (nf_tables): RULE_APPEND failed (No such file or directory): rule in chain PREROUTING

2. Legacy iptables backend also fails.

Commands:

update-alternatives --set iptables /usr/sbin/iptables-legacy
 update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
 dockerd --host=unix:///var/run/docker.sock

Failure:

failed to create NAT chain DOCKER:
 iptables v1.8.11 (legacy): can't initialize iptables table `nat':
 Table does not exist (do you need to insmod)
 Perhaps iptables or your kernel needs to be upgraded.

3. Kernel module attempts fail.

Commands tried:

modprobe xt_addrtype
 modprobe ip_tables
 modprobe iptable_nat
 modprobe br_netfilter

Observed/previous error:

modprobe: FATAL: Module xt_addrtype not found in directory /lib/modules/6.6.114.1-microsoft-standard-WSL2+

4. Multi-worker Redroid fails in host-network fallback.

Because host networking exposes Android ADB fixed port 5555, only one Redroid instance is reachable. Tried changing
 ADB port with boot props:

service.adb.tcp.port=5556
 persist.adb.tcp.port=5556

Second host-network Redroid did not stay running cleanly.

5. Docker ipvlan was tested.

Network creation:

docker network create -d ipvlan \
  --subnet=172.27.160.0/20 \
  --gateway=172.27.160.1 \
  -o parent=eth0 \
  damru-ipvlan

Container attach failed:

failed to set up container networking:
 failed to create the ipvlan port: operation not supported

6. Docker macvlan was also tried, but did not produce a usable Redroid multi-container path in WSL.
 7. Android iptables inside Redroid is missing filter table.

Inside Redroid:

su 0 iptables -L OUTPUT -n

Failure:

iptables v1.8.7 (legacy): can't initialize iptables table `filter':
 Table does not exist

This breaks kernel-level WebRTC UDP blocking inside Android. The browser still works with Chrome WebRTC prefs/CDP
 policy, but Android kernel firewall protection is missing.

What I need you to research deeply:

A. Docker bridge/NAT on stock WSL2

1. Can Docker bridge/NAT be made to work on stock Microsoft WSL2 kernel 6.6.114.1 without custom kernel
 2. Is xt_addrtype, iptable_nat, nat table, or filter table supposed to exist in stock WSL2
 3. Are these features built-in, modular, unavailable, disabled, or affected by Ubuntu userspace
 4. Is Ubuntu 26.04 userspace incompatible with current WSL2 kernel iptables/nftables expectations
 5. Would Ubuntu 22.04 or 24.04 WSL fix this with the same stock kernel
 6. Are there known regressions in WSL kernel 6.6.114.1 affecting Docker bridge/NAT
 7. Are there Windows/WSL settings that enable/disable these kernel features

B. iptables/nftables compatibility

1. Is this caused by nftables backend vs legacy backend
 2. Are there exact alternatives commands that fix this
 3. Does installing iptables, iptables-persistent, nftables, linux-modules-extra, or other packages help in WSL
 4. Can missing nat table be loaded or emulated in stock WSL
 5. Can Docker be configured to avoid addrtype while still using bridge networking
 6. Can Docker use userland-proxy only without kernel NAT
 7. Can Docker port publishing work without iptables/NAT

C. Multi-container Redroid without Docker bridge
 Research every possible no-custom-kernel workaround:

1. Docker --network host with changed ADB port per Redroid container.
 2. Redroid boot props or init changes to make ADB listen on unique ports:
   - service.adb.tcp.port
   - persist.adb.tcp.port
   - ro.adb.secure
   - ro.debuggable
   - init .rc modifications
   - setprop before/after adbd start

3. Whether Redroid supports per-container ADB port configuration officially.
 4. Whether Redroid containers can run with --network none and use:
   - nsenter
   - socat
   - adb forward
   - adb connect through a per-container namespace proxy
   - slirp4netns
   - pasta
   - rootless Docker networking
   - containerd CNI
   - custom tap/tun

5. Whether Docker ipvlan or macvlan can work in WSL2 with extra commands or Windows settings.
 6. Whether WSL mirrored networking mode changes ipvlan/macvlan support.
 7. Whether Hyper-V firewall or WSL networking mode blocks these drivers.
 8. Whether multiple Redroid instances can share host networking if binderfs/device paths are isolated differently.
 9. Whether Redroid has known limitations around multiple containers on host networking.

D. Android iptables inside Redroid

1. Is Redroid Android iptables support always host-kernel dependent
 2. Can Android iptables filter table be enabled by image changes, boot args, or init scripts
 3. Does Redroid need specific host modules for Android iptables
 4. What host kernel config options are required for Android iptables filter/nat/owner match
 5. Does Docker privileged mode expose host netfilter tables to Redroid Android
 6. Is xt_owner required for UID-based WebRTC UDP blocking
 7. Are there no-kernel alternatives for WebRTC leak protection:
   - Chrome flags
   - Chrome prefs
   - enterprise policies
   - CDP network settings
   - proxy-level UDP blocking
   - tun2socks
   - nftables outside container
   - eBPF outside container
   - userspace UDP blackhole

8. How strong are those alternatives compared to Android iptables

E. Docker Desktop / alternative backends

1. Can Docker Desktop €™s Linux VM backend run privileged Redroid with binderfs
 2. Does Docker Desktop support binderfs/ashmem/binder devices required by Redroid
 3. Could Docker Desktop solve bridge/NAT while still satisfying  €œRedroid runs inside Linux €
 4. Can Rancher Desktop, Colima, Podman machine, Lima, or another Linux VM backend run Redroid on Windows
 5. Which of those support binderfs, privileged containers, and Android kernel requirements
 6. Is a full Linux VM the only practical no-custom-WSL-kernel solution

F. WSL version / distro version angle

1. Does WSL Ubuntu 22.04/24.04 behave differently from Ubuntu 26.04 for Docker bridge/NAT
 2. Are Ubuntu 26.04 iptables/nftables packages too new for this WSL kernel
 3. Is downgrading iptables/nftables a valid fix
 4. Is using Docker CE packages instead of Ubuntu docker.io a fix
 5. Is WSL systemd mode relevant
 6. Are there known WSL networking modes:
   - NAT
   - mirrored
   - bridged/deprecated
   - virtio proxy
    that affect Docker bridge/NAT or Redroid

G. Exact validation commands needed
 Please produce commands to check:

uname -a
 zcat /proc/config.gz
 ls /lib/modules/\$(uname -r)
 lsmod
 modprobe xt_addrtype
 modprobe ip_tables
 modprobe iptable_nat
 modprobe iptable_filter
 modprobe br_netfilter
 cat /proc/net/ip_tables_names
 iptables -t nat -L
 iptables -t filter -L
 nft list ruleset
 docker info
 docker network create bridge test
 docker run --rm -p 5600:5555 ...

Also provide Windows commands:

wsl --version
 wsl --status
 wsl -l -v
 Get-NetNat
 Get-NetAdapter
 Get-NetIPInterface
 Get-NetFirewallProfile

H. Desired final output
 I need a final answer with:

1. Clear root cause.
 2. Whether no-custom-kernel fix exists.
 3. If yes, exact commands.
 4. If no, exact proof and citations.
 5. Best practical architecture for:
   - single-worker local testing on WSL,
   - multi-worker production on Windows,
   - multi-worker production on native Linux.

6. Whether baked Redroid image can fix any part of this.
 7. Whether changing Ubuntu distro version can fix it.
 8. Whether Docker Desktop or another VM backend can fix it.
 9. Safest recommended path for production.
 10. Any code changes my framework should make:

- better detection,
 - clearer errors,
 - automatic fallback,
 - preventing multi-worker attempts in unsupported WSL,
 - possible userspace proxy strategy.

Please cite sources. Prioritize primary/official sources where possible:

- Docker official docs
 - Microsoft WSL docs/issues
 - Moby/Docker GitHub issues
 - Redroid GitHub/issues/docs
 - Linux kernel docs
 - nftables/iptables docs
 - Ubuntu/Debian bug trackers

scrape 1k+ websites each category

Root cause is that the stock WSL2 6.6.x kernel you €™re on simply does not provide the netfilter/NAT machinery that Docker bridge networking and Android iptables need, so there is no clean way to get multi €‘container Redroid with Docker bridge/NAT working inside this WSL without either a custom WSL kernel or moving the workload into a full Linux VM; single €‘worker host €‘network mode is about as far as you can reasonably go on stock WSL.[^1_1][^1_2][^1_3][^1_4]

Below is a distilled, opinionated answer focused on what you can and cannot do, plus how to adapt your framework.

***

## 1. Root cause in your environment

### 1.1 What €™s actually broken

The errors you see from Docker on WSL2:

- `Warning: Extension addrtype revision 0 not supported, missing kernel module`
- `iptables (nf_tables): RULE_APPEND failed (No such file or directory)` for `nat-PREROUTING`
- `iptables v1.8.11 (legacy): can't initialize iptables table 'nat': Table does not exist (do you need to insmod)`

are exactly what you get when the kernel lacks:

- `xt_addrtype` (`CONFIG_NETFILTER_XT_MATCH_ADDRTYPE`)
- NAT support modules/tables (`nf_nat`, `iptable_nat`, nat table hooks)
- Sometimes even the `raw` table (`CONFIG_IP_NF_RAW` / `nf_tables_raw`)

and Docker €™s bridge driver tries to program iptables for the `docker0` bridge.[^1_5][^1_6][^1_7][^1_8]

On non €‘WSL distros the fix is: install `kernel-modules-extra`, then `modprobe xt_addrtype ip_tables iptable_nat br_netfilter` and Docker starts. On WSL2, those modules aren €™t just unloaded  €“ they *aren €™t there* in `/lib/modules/<kernel>` at all for stock kernels, so `modprobe` fails exactly as you €™ve seen.[^1_6][^1_3][^1_4][^1_5]

Microsoft €™s own issues confirm that:

- nftables NAT modules are **not compiled** in some WSL kernels (`Missing nat module for nftables`).[^1_3]
- iptables `raw` table is missing on WSL 6.1.102, breaking Docker networking: `can't initialize iptables table 'raw'`.[^1_9][^1_1]
- `bridge` and `br_netfilter` modules are not found in `/lib/modules` on 6.6.36.3.[^1_4]
- Other netfilter matches like `xt_u32`, `xt_recent` are also missing in stock WSL kernels, enough that Microsoft tells people the fix is  €œbuild a custom kernel with this module. €[^1_10][^1_11]

So:

- Docker bridge/NAT can €™t work because required netfilter modules/tables are missing from the **kernel build**.
- Android iptables inside Redroid fails for the same reason: it €™s talking to the same kernel, and if the `filter`/`nat` tables don €™t exist, `iptables -t filter -L` or `-t nat -L` inside Android will blow up.[^1_12][^1_13]

This is not a userspace/Ubuntu problem; it €™s a kernel config / module packaging problem.

### 1.2 Why switching to legacy iptables or other Ubuntu versions doesn €™t fix it

Historically, Docker + WSL issues around Ubuntu 20.10+ were partly about nftables vs legacy iptables: Ubuntu defaulted to iptables €‘nft, while Docker still assumed legacy; switching to `iptables-legacy` fixed many installs.[^1_14][^1_15][^1_2][^1_16]

You already tried legacy:

- `iptables-legacy` still says  €œnat table does not exist, € which means there is no NAT support in the kernel, not just a frontend mismatch.[^1_8][^1_5]

Changing Ubuntu 26.04  †’ 24.04/22.04 might change iptables frontend defaults, Docker versions, and packaging, but it **cannot conjure netfilter modules into the Microsoft kernel**. Same for toggling systemd, Docker CE vs `docker.io`, etc.[^1_2][^1_17]

***

## 2. Direct answers to your key questions

### A. Docker bridge/NAT on stock WSL2

1. **Can Docker bridge/NAT be made to work on 6.6.114.1 without a custom kernel**
For your specific class of errors (addrtype missing, nat table missing, raw table likely missing), all public evidence from WSL issues and Docker/Podman reports indicates *no*. Fixes elsewhere always involve adding or loading kernel modules; stock WSL kernel doesn €™t ship them, and you can €™t install `linux-modules-extra` for a Microsoft kernel the way you do on native Ubuntu.[^1_2][^1_5][^1_6][^1_3][^1_4]
2. **Are `xt_addrtype`, `iptable_nat`, nat/filter table supposed to exist**
Yes, on a Docker €‘ready Linux host they are required, and Moby €™s `check-config.sh` explicitly checks for them.  Microsoft used to compile some of these as built €‘ins; more recently in 6.6.x they moved a lot to modules  €“ but the module trees shipped in WSL images still don €™t contain what Docker needs, as current issues show.[^1_18][^1_19][^1_4]
3. **Built €‘in vs modular vs disabled**
    - In older WSL kernels: some netfilter bits were compiled in (`=y`), some missing.[^1_20][^1_19]
    - In 6.6.x: more netfilter options are `=m`, and Microsoft says  €œmodprobe will load them automatically, € but that only works if you €™re using the *exact* official kernel + modules pairing.[^1_18]
    - Your `modprobe` failures show that in practice they €™re **unavailable**.

4 €“7. **Ubuntu version, regressions, WSL settings**

- Changing Ubuntu releases or iptables versions doesn €™t fix missing kernel modules.[^1_16][^1_2]
- There are known regressions for Docker networking across WSL kernels (missing `raw` table, missing nat nft modules, missing bridge modules).[^1_1][^1_3][^1_4]
- `.wslconfig` `networkingMode` (nat/mirrored/bridged) affects how WSL €™s VM talks to Windows, not whether netfilter exists inside the kernel.[^1_21][^1_22]
- No Windows/WSL setting turns on `xt_addrtype`/`iptable_nat` if they aren €™t compiled/shipped.

**Short answer for A:** Docker bridge/NAT is blocked by kernel capabilities that you don €™t have; there €™s no known flag or package that fixes this on stock 6.6.x.

***

### B. iptables/nftables compatibility

1. **nftables vs legacy**
WSL kernels historically have poor nftables NAT support (Microsoft explicitly logged  €œMissing nat module for nftables €).[^1_3]
Legacy mode helps when the kernel has legacy iptables NAT but no nft; in your case neither side has working NAT.

2 €“4. **Alternate commands / packages / loading nat table**
On normal distros people do:

```bash
sudo modprobe ip_tables iptable_nat iptable_filter xt_addrtype br_netfilter
```

and maybe `linux-modules-extra-$(uname -r)` to get the modules.[^1_5][^1_6]
For WSL, `modprobe` fails, and `linux-modules-extra` for Ubuntu €™s generic kernel doesn €™t apply to the Microsoft kernel.  There is no supported way to  €œload € a nat table that isn €™t compiled in.[^1_23][^1_24][^1_13][^1_3]

5. **Docker without addrtype**
The `-m addrtype --dst-type LOCAL -j DOCKER` rule in nat PREROUTING is a baked €‘in part of Docker €™s iptables programming. There is no config knob to disable it; upstream fixes always say  €œinstall xt_addrtype. €[^1_25][^1_26][^1_6]

6 €“7. **Userland €‘proxy only / port publish without iptables/NAT**
Docker still relies on iptables/NAT even with userland €‘proxy; userland €‘proxy doesn €™t magically replace the NAT rules. Without nat/PREROUTING/POSTROUTING, generic `-p host:container` cannot work.  That €™s exactly what you €™re observing.[^1_26][^1_25]

**Short answer for B:** Both nft and legacy require working kernel netfilter; you don €™t have it, so neither backend will save you. Workarounds are limited to `--network host` and disabling Docker €™s iptables usage.

***

### C. Multi €‘container Redroid without Docker bridge

This is the big one for you.

#### C.1 Host networking + changed ADB port

- With `--network host`, each container shares the WSL2 network namespace; inside Android adbd binds to `0.0.0.0:5555`, which is a single global port in that namespace. Only one process can own it.
- Changing `service.adb.tcp.port`/`persist.adb.tcp.port` is fragile: Redroid images don €™t officially support per €‘container ADB port config, and init may override properties.[^1_27][^1_28]
- On standard Linux, the supported pattern is *not* to change the Android port; it €™s to keep ADB on 5555 and map different host ports: `-p 5555:5555`, `-p 5556:5555`, etc.[^1_29][^1_30][^1_23]

So under **host networking** you realistically only get one Redroid instance with stable ADB, exactly what you €™re seeing.

#### C.2 €“C.3 Official Redroid stance

- Redroid docs and community examples always show multiple containers distinguished by `-p` mappings, not by changing ADB port in the guest:
Examples: `-p 5555:5555`, `-p 5557:5555`, `-p 5559:5555` for multiple containers.[^1_30][^1_23][^1_29]
- There €™s no official Redroid parameter documented to change ADB €™s listen port per container.

So your use of host networking + attempt to change ADB port is outside the supported path, and the observed instability (second container not staying up) is unsurprising.

#### C.4 `--network none` + nsenter/socat/forward/pasta etc.

All the alternatives you listed are theoretically possible but ugly in this context:

- **`--network none` + `nsenter` + `socat`**  €“ You €™d need a host namespace process per container to forward a unique host port to the container €™s loopback where adbd listens. But Redroid also needs `--privileged`, `/dev/binder`, GPU, etc., so you haven €™t simplified much, and you still depend on the kernel €™s underlying networking features.
- **`slirp4netns` / `pasta` / rootless Docker**  €“ These are used for rootless containers to emulate networking without kernel NAT. But Redroid requires privileged containers and host device access, which clashes with rootless assumptions. There are no public writeups of  €œRedroid over slirp4netns € on WSL.
- **ADB forward**  €“ Still needs some reachable endpoint to talk to; it doesn €™t make up for lack of container €‘level network isolation without bridge.

Given Redroid €™s expectations (binderfs, GPU, privileged), there €™s no documented reliable combo of these tools for multi €‘worker Redroid on WSL2.

#### C.5 €“C.7 ipvlan/macvlan, WSL networking modes, Hyper €‘V

- Your `ipvlan`  €œoperation not supported € is exactly what you see when the kernel doesn €™t support that link type; recent WSL issues show even `bridge`/`br_netfilter` missing.[^1_31][^1_4]
- `networkingMode=mirrored` in `.wslconfig` affects how WSL €™s NIC shows up in Windows, not whether ipvlan/macvlan exist in the Linux kernel.[^1_22][^1_21]
- Hyper €‘V/Windows firewall can block traffic, but they don €™t add ipvlan/macvlan drivers to the Linux kernel.


#### C.8 €“C.9 Multiple Redroid host €‘network limitations

There are reports that even on full Linux, more than one Redroid container can be finicky: one gist notes that  €œit seems only one redroid container can run correctly, so stop the Redroid 14 container before starting another; otherwise ADB/scrcpy won €™t connect, even with different ports. €  This suggests there are also limitations around shared binder/devices/GPU, not just networking.[^1_29]

**Short answer for C:** On stock WSL, you can reasonably support **one** Redroid instance via host networking. Multi €‘worker on the same WSL kernel is not reliable with any sane amount of duct tape.

***

### D. Android iptables in Redroid

- Redroid €™s Android userspace iptables calls into the *host kernel €™s* netfilter, because it €™s a container on that kernel. If the host has no `filter`/`nat` tables, Android €™s iptables fails identically.[^1_32][^1_13][^1_12]
- Enabling `filter`/`nat` inside Android is impossible when the host kernel doesn €™t have them compiled. You €™d need `CONFIG_NETFILTER`, `CONFIG_IP_NF_FILTER`, `CONFIG_IP_NF_NAT`, `CONFIG_NF_NAT` and the relevant xt matches (`xt_owner`, etc.) turned on in the WSL kernel. That €™s exactly what you *don €™t* have.[^1_13][^1_3]
- `--privileged` in Docker only gives the container full access to whatever netfilter the host has; it doesn €™t create a separate netfilter namespace or add missing tables.[^1_12]
- For UID €‘based WebRTC blocking, `xt_owner` is needed; WSL already demonstrates missing xt modules (`xt_recent`, `xt_u32`), so relying on `xt_owner` here is unrealistic without a custom kernel.[^1_11][^1_10]

**Alternatives**:

- Chrome/Chromium WebRTC flags and enterprise policies (disable non €‘proxied UDP, restrict ICE candidates, force proxy)  €“ browser €‘level, not kernel €‘level.[^1_13]
- Proxy or VPN that blocks UDP entirely, including tun2socks €‘style TCP €‘only tunnels.
- On a real Linux kernel (not WSL), you can also do nftables or eBPF filtering outside the container; but on WSL you hit the same netfilter problems.

Kernel €‘level Android iptables is clearly stronger and more generic; on WSL you €™re stuck with browser €‘ and proxy €‘level mitigations.

***

### E. Docker Desktop / other backends

- Docker Desktop €™s  €œWSL integration € still runs containers in its own Linux VM (`docker-desktop`), not in your Ubuntu distro. You get a separate kernel and network stack.[^1_33][^1_34]
- There is no promise that Docker Desktop €™s internal kernel has `binder_linux`/binderfs; by default it is tuned for generic containers, not Android. Redroid docs assume a kernel where you can run:

```bash
apt install linux-modules-extra-$(uname -r)
modprobe binder_linux devices="binder,hwbinder,vndbinder"
```

to get binder devices.[^1_35][^1_24][^1_23]
- Docker Desktop €™s `--net=host` is *not* Linux host networking in the usual sense; it €™s implemented via vpnkit, and the project itself documents that `--net=host` is not supported the same way on Windows/WSL.  That €™s not a great foundation for a low €‘level Android stack.[^1_36][^1_37][^1_38]
- Rancher Desktop / Podman machine / Lima / Colima  €“ all of these rely on a **real Linux VM** where you control the kernel; you can pick a distro + kernel with full netfilter and binderfs, then install Redroid following its normal docs.[^1_24][^1_35][^1_23]

**Net:**

- If you want multi €‘worker Redroid on Windows without touching the WSL kernel, the realistic answer is  €œrun a dedicated Linux VM (Hyper €‘V/VMware/VirtualBox/KVM) and put Redroid + Docker there. €
- Docker Desktop *might* work if you can somehow tune its VM kernel to include binder_linux/binderfs, but that €™s undocumented and brittle compared to just creating your own VM.

***

### F. WSL / distro version angles

- Old WSL + Ubuntu 20.10/22.04 issues about Docker were mostly  €œkernel doesn €™t support nftables properly but userspace defaulted to iptables €‘nft €; fixed by WSL updates and switching to legacy iptables or Docker CE.[^1_16][^1_2]
- Current issues (9772, 14487, 12108) show we still have missing nat modules, raw table, bridge modules on newer 5.x and 6.x WSL kernels.[^1_4][^1_1][^1_3]
- WSL systemd mode affects service management, not kernel features.
- WSL networking modes (nat/mirrored/bridged) affect Windows €‘side NAT and vSwitch. They do not add netfilter tables inside the Linux kernel.[^1_21][^1_22]

Switching Ubuntu versions or Docker package flavors can fix some things; they will not fix *this*.

***

## 3. Concrete validation commands

These won €™t fix anything but will give you hard proof and can drive automated detection in your framework.

### 3.1 Inside WSL Ubuntu

Run as root where needed:

```bash
# Kernel and config
uname -a
zcat /proc/config.gz | egrep 'NETFILTER|IP_NF|NF_NAT|XT_ADDRTYPE|BRIDGE'

# Modules present and loaded
ls -R /lib/modules/"$(uname -r)"
lsmod | egrep 'iptable|ip_tables|nf_nat|xt_addrtype|br_netfilter|bridge'

# Attempt to load common Docker netfilter modules
sudo modprobe xt_addrtype
sudo modprobe ip_tables
sudo modprobe iptable_nat
sudo modprobe iptable_filter
sudo modprobe br_netfilter

# Check what tables exist
cat /proc/net/ip_tables_names
sudo iptables -t filter -L -n -v
sudo iptables -t nat -L -n -v

# nftables state (if any)
sudo nft list ruleset

# Docker info (when you can start it)
sudo docker info
sudo docker network ls

# Proof of bridge failure
sudo docker network create test-bridge

# Proof that port publish depends on NAT
sudo docker run --rm -p 5600:5555 alpine:latest sleep 60
```

Inside Redroid / Android shell:

```bash
su 0 iptables -L -n
su 0 iptables -t filter -L -n
su 0 iptables -t nat -L -n
```

You should see the `table does not exist` errors here.

### 3.2 On Windows

```powershell
# WSL core
wsl --version
wsl --status
wsl -l -v

# Windows NAT and interfaces
Get-NetNat
Get-NetAdapter
Get-NetIPInterface
Get-NetFirewallProfile

# Hyper-V switch extensions (for general WSL networking debugging)
Get-VMSwitch
Get-VMSwitchExtension -VMSwitch (Get-VMSwitch | Where-Object {$_.Name -like '*WSL*'}) | Select-Object Name, Enabled
```

These help distinguish  €œnetwork is broken at Windows NAT/vSwitch level € from  €œLinux netfilter is missing. € Your errors are clearly in the latter category.

***

## 4. Recommended architectures

### 4.1 Single €‘worker local dev on WSL

What you €™re doing is basically the right thing:

```bash
dockerd \
  --iptables=false \
  --ip6tables=false \
  --bridge=none \
  --host=unix:///var/run/docker.sock

docker run -itd --rm --privileged \
  --network host \
  -v ~/data-worker1:/data \
  --name redroid-worker1 \
  damru-redroid:latest

# From WSL or Windows using WSL IP:
adb connect <WSL_IP>:5555
```

Guidance:

- Accept that inside WSL this is **one worker max**, no kernel €‘level Android firewall, no Docker bridge.
- For WebRTC, rely on Chrome flags + policies and a proxy/VPN layer, not Android iptables.


### 4.2 Multi €‘worker production on Windows

**Better option: a dedicated Linux VM:**

- Create a VM (Hyper €‘V/VMware/VirtualBox/KVM) running Ubuntu 22.04/24.04 or Debian 12.
- Inside VM:

```bash
sudo apt update
sudo apt install -y linux-modules-extra-$(uname -r)

# Android kernel bits for Redroid
sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"
# ashmem if needed and available:
# sudo modprobe ashmem_linux

# Sanity check netfilter
sudo iptables -t filter -L
sudo iptables -t nat -L
```


[^1_35][^1_23][^1_24]

- Install Docker CE using official docs.[^1_17]
- Run multiple Redroid containers with **bridge networking** and distinct host ports:

```bash
sudo docker network create redroid-net

sudo docker run -d --privileged \
  --network redroid-net \
  -p 5555:5555 \
  --name redroid1 \
  redroid/redroid:14.0.0_64only-latest

sudo docker run -d --privileged \
  --network redroid-net \
  -p 5556:5555 \
  --name redroid2 \
  redroid/redroid:14.0.0_64only-latest
```


[^1_23][^1_30][^1_29]

- From Windows, connect via `adb connect <VM_IP>:5555`, `:5556`, etc.

This solves:

- Docker bridge/NAT
- Multi €‘instance ADB
- Android iptables (assuming the kernel has filter/nat/xt_owner)


### 4.3 Multi €‘worker on native Linux

Same as above, just on bare metal Linux instead of a VM. That €™s the  €œgold standard € environment for Redroid.

***

## 5. What your framework should do

### 5.1 Detect  €œWSL + broken netfilter €

At startup or as part of environment probing:

1. Detect WSL:
    - Look for `microsoft-standard-WSL` in `uname -r` or `grep -i microsoft /proc/version`.
2. Probe iptables/nat:

```bash
if ! iptables -t nat -L -n >/dev/null 2>&1; then
    # mark environment as no-NAT
fi
```

3. Optionally run a small subset of Moby €™s `check-config.sh` (or a lighter equivalent) to look for `CONFIG_IP_NF_FILTER`, `CONFIG_IP_NF_NAT`, `CONFIG_NETFILTER_XT_MATCH_ADDRTYPE`, `CONFIG_BRIDGE_NETFILTER` in `/proc/config.gz`.[^1_19]

If these checks fail, flip an internal capability flag: `kernel_nat_supported = false`.

### 5.2 Enforce safe behavior

Given `kernel_nat_supported = false` and `running_on_wsl = true`:

- Force Docker daemon flags (`--iptables=false --bridge=none`) for any Docker you start/manage.
- Allow **only one** Redroid worker concurrently in that environment.
- Disable attempts to manipulate Android iptables; surface a warning in logs and any UI.

If `kernel_nat_supported = true` and not WSL:

- Allow bridge networking, host port mapping, and optional Android iptables policies.


### 5.3 Clear error messaging

When a user tries to start multi €‘worker Redroid inside such a WSL:

- Fail fast with something like:

> This WSL2 kernel is missing required netfilter NAT modules (iptables nat/raw/addrtype). Docker bridge networking and multi €‘worker Redroid are not supported here. Use a full Linux VM or native Linux for multi €‘worker workloads.

Point to docs/links if you ship your own documentation.

### 5.4 Optional userspace proxy strategy

If you really want  €œmulti logical workers € on WSL, consider a different architecture:

- Run a **single** Redroid instance on WSL.
- Run multiple browser automation sessions against it, each with its own browser profile/proxy configuration.
- Use userspace TCP proxies or per €‘session SOCKS proxies to isolate traffic logically.

This trades  €œmulti €‘container € for  €œmulti €‘session in one container, € which avoids the kernel limitations while still giving you concurrency.

***

## 6. Direct answers to your numbered  €œdesired final output € items

1. **Clear root cause**  €“ Missing/disabled netfilter NAT and match modules (`nat`, `raw`, `xt_addrtype`, `br_netfilter`, likely `xt_owner` etc.) in the stock WSL 6.6.x kernel; Docker bridge + Android iptables cannot function without them.[^1_10][^1_11][^1_6][^1_1][^1_3][^1_4]
2. **No €‘custom €‘kernel fix**  €“ Not for Docker bridge/NAT + Android iptables + multi €‘worker Redroid inside this WSL. Only host networking + single worker is viable.[^1_3][^1_4]
3. **If yes, exact commands**  €“ For the narrow  €œsingle worker € case: the `dockerd --iptables=false --bridge=none` + `--network host` workflow you already have is the correct workaround.
4. **If no, proof \& citations**  €“ WSL issues 9772, 14487, 12108, 9946, 11140 show missing nat, raw, bridge, and xt_* modules in WSL kernels; fixes in non €‘WSL environments always involve adding/loading modules or custom kernels.[^1_11][^1_1][^1_10][^1_4][^1_3]
5. **Best architectures:**
    - Single €‘worker local testing: WSL2 + host networking + one Redroid.
    - Multi €‘worker on Windows: Redroid inside a full Linux VM with full netfilter and binder modules.
    - Multi €‘worker on native Linux: same as VM but on bare metal.
6. **Can a baked Redroid image fix this**  €“ Only for higher €‘level behavior (init, Chrome config, proxies). It **cannot** supply missing kernel netfilter/binder features.
7. **Can changing Ubuntu distro fix it**  €“ No; kernel is the bottleneck, not Ubuntu 26.04/24.04/22.04.
8. **Can Docker Desktop/other VM backend fix it**  €“ Yes, if you treat them as a full Linux VM and ensure the VM €™s kernel is Redroid €‘ready (binder_linux/binderfs + netfilter). Most straightforward is a custom VM you control, not the opaque Docker Desktop one.
9. **Safest production path:**
    - Dev: WSL + single worker + host networking, with clear warnings about limitations.
    - Prod: Native Linux or dedicated Linux VM with a proper kernel; don €™t treat WSL as a production substrate.
10. **Framework code changes:**
    - Add detection of WSL and netfilter capabilities;
    - Emit explicit, actionable errors;
    - Enforce automatic fallback to single €‘worker host €‘network mode on WSL;
    - Avoid attempting Android iptables on WSL;
    - Optionally offer a userspace multi €‘session design instead of multi €‘container in constrained environments.

***

A full markdown report with more narrative, citations, and command snippets was prepared as a reference document for you; use it as design documentation for your framework and infra decisions.
<span style="display:none">[^1_39][^1_40][^1_41][^1_42][^1_43][^1_44][^1_45][^1_46][^1_47][^1_48][^1_49][^1_50][^1_51][^1_52][^1_53][^1_54][^1_55][^1_56][^1_57][^1_58][^1_59][^1_60][^1_61][^1_62][^1_63][^1_64][^1_65][^1_66][^1_67][^1_68][^1_69][^1_70][^1_71][^1_72][^1_73][^1_74][^1_75][^1_76][^1_77][^1_78][^1_79][^1_80][^1_81]</span>

<div align="center"> ‚</div>

[^1_1]: https://github.com/microsoft/WSL/issues/6655

[^1_2]: https://github.com/microsoft/WSL/issues/9772

[^1_3]: https://stackoverflow.com/questions/69573784/wsl-kernel-netfilter-hooks-for-pre-post-routing-not-available

[^1_4]: https://github.com/microsoft/WSL/issues/12108

[^1_5]: https://github.com/containers/podman/issues/25201

[^1_6]: https://forums.rockylinux.org/t/docker-installation-failed-on-rhel-10/20024/7

[^1_7]: https://github.com/microsoft/WSL/issues/4165

[^1_8]: https://readmex.com/en-US/remote-android/redroid-doc/page-3.563aaafc2-f141-4047-b553-cac84d83fc6c

[^1_9]: https://githubhelp.com/testnobody/redroid-doc

[^1_10]: https://wiki.nftables.org/wiki-nftables/index.php/Troubleshooting

[^1_11]: https://clients.websavers.ca/whmcs/knowledgebase/222/Unable-to-load-Docker-service-due-to-natandsharp039-Table-does-not-exist.html

[^1_12]: https://stackoverflow.com/questions/21983554/iptables-v1-4-14-cant-initialize-iptables-table-nat-table-does-not-exist-d

[^1_13]: https://bbs.archlinux.org/viewtopic.phpid=182400

[^1_14]: https://github.com/microsoft/WSL/issues/14487

[^1_15]: https://github.com/microsoft/WSL/labels/kernel

[^1_16]: https://github.com/microsoft/WSL/issues/11884

[^1_17]: https://xcr4k.hatenablog.com/entry/wsl2_custom_kernel_with_loadable_modules

[^1_18]: https://github.com/microsoft/WSL/issues/7124

[^1_19]: https://www.reddit.com/r/bashonubuntuonwindows/comments/sy35km/docker_in_wsl2_the_right_way/

[^1_20]: https://learn.microsoft.com/en-us/windows/wsl/networking

[^1_21]: https://www.reddit.com/r/bashonubuntuonwindows/comments/1sa16bx/wsl2_nat_never_created_on_startup_getnetnat/

[^1_22]: https://jonathan-lalou.sayasoft.fr/2025/10/19/fixing-the-failed-to-setup-ip-tables-error-in-docker-on-wsl2/

[^1_23]: https://www.linkedin.com/posts/jonathanlalou_fixing-the-failed-to-setup-ip-tables-error-activity-7385629441235947520-Z5to

[^1_24]: https://github.com/docker/for-linux/issues/1437

[^1_25]: https://github.com/containers/podman/issues/25952

[^1_26]: https://stackoverflow.com/questions/63226322/bridge-nf-call-iptables-and-bridge-nf-call-ip6tables-disabled-on-wsl2

[^1_27]: https://my.oschina.net/dingzang/blog/10141924

[^1_28]: https://hub.docker.com/r/kasmweb/redroid

[^1_29]: https://bbs.archlinux.org/viewtopic.phppid=1758325

[^1_30]: https://forums.docker.com/t/understanding-iptables-rules-added-by-docker/77210

[^1_31]: https://oneuptime.com/blog/post/2026-02-08-how-to-understand-docker-iptables-rules/view

[^1_32]: https://forums.docker.com/t/docker-tries-to-create-a-chain-on-table-nat-with-ip6tables-but-theres-no-nat-table-on-ipv6-solved/146347

[^1_33]: https://github.com/remote-android/redroid-doc/issues/677

[^1_34]: https://gist.github.com/diyism/70ae5719d42db173e0da0742f2728cda

[^1_35]: https://github.com/remote-android/redroid-doc/issues/27

[^1_36]: https://dev.to/avkr/redroid-o6n

[^1_37]: https://hub.docker.com/r/redroid/redroid

[^1_38]: https://forums.rockylinux.org/t/docker-installation-failed-on-rhel-10/20024

[^1_39]: https://support.solusvm.com/hc/en-us/articles/13267930454935-Unable-to-manage-iptables-inside-OpenVZ-VPS-can-t-initialize-iptables-table-nat-Table-does-not-exist

[^1_40]: https://github.com/microsoft/WSL/issues/9946

[^1_41]: https://github.com/microsoft/WSL/issues/11140

[^1_42]: https://stackoverflow.com/questions/72483632/ubuntu-error-the-command-docker-could-not-be-found-in-this-wsl-2-distro

[^1_43]: https://forums.docker.com/t/docker-will-not-start-on-wsl-2/132321

[^1_44]: https://github.com/remote-android/redroid-doc/issues/44

[^1_45]: https://stackoverflow.com/questions/66698148/running-network-mode-host-on-windows-10-with-wsl2-and-docker

[^1_46]: https://forums.docker.com/t/host-networking-not-working-on-docker-desktop-in-wsl2-with-mirrored-mode/147994

[^1_47]: https://github.com/docker/for-win/issues/6736

[^1_48]: https://github.com/docker/for-linux/issues/1406

[^1_49]: https://techcommunity.microsoft.com/discussions/windows11/wsl2-nat-network-broken---perhaps-after-docker/4462074

[^1_50]: https://github.com/remote-android/redroid-doc/issues/68

[^1_51]: https://forums.opensuse.org/t/iptables-problem-when-trying-to-use-docker-in-wsl2/180669

[^1_52]: https://www.youtube.com/watchv=yCK3easuYm4

[^1_53]: https://github.com/WhitewaterFoundry/Pengwin/issues/485

[^1_54]: https://patrickwu.space/2021/03/09/wsl-solution-to-native-docker-daemon-not-starting/

[^1_55]: https://github.com/microsoft/WSL/issues/4133

[^1_56]: https://github.com/microsoft/WSL/issues/9652

[^1_57]: https://github.com/microsoft/WSL/issues/8149

[^1_58]: https://github.com/microsoft/WSL/issues/11742

[^1_59]: https://forums.docker.com/t/use-bridge-networking-instead-of-nat-in-docker-desktop-on-windows/147589

[^1_60]: https://github.com/microsoft/WSL/issues/10044

[^1_61]: https://learn.microsoft.com/en-ie/answers/questions/1426263/how-to-enable-modules-in-wsl2

[^1_62]: https://gist.github.com/jramiresbrito/846b9bebc560668eb2e7a97fb1cfc1ef

[^1_63]: https://alex-ber.medium.com/making-host-docker-internal-work-inwsl2-ab19c3e51bf0

[^1_64]: https://stackoverflow.com/questions/62145379/how-to-connect-android-studio-running-inside-wsl2-with-connected-devices-or-andr

[^1_65]: https://stackoverflow.com/questions/60166965/adb-device-list-empty-using-wsl2

[^1_66]: https://github.com/remote-android/redroid-doc/issues/859

[^1_67]: https://stackoverflow.com/questions/57351688/unable-to-start-docker-in-wsl2-using-new-windows-terminal

[^1_68]: https://forums.docker.com/t/can-only-access-containers-using-localhost-from-the-host/150125

[^1_69]: https://learn.microsoft.com/en-us/answers/questions/1426263/how-to-enable-modules-in-wsl2

[^1_70]: https://stackoverflow.com/questions/65426891/networking-problems-with-wsl2-and-docker-desktop-for-windows

[^1_71]: https://forums.docker.com/t/issues-with-docker-desktop-and-wsl-2-integration/141865

[^1_72]: https://www.facebook.com/groups/HomeAssistant/posts/4060952147509458/

[^1_73]: https://forums.docker.com/t/custom-kernel-that-enabled-can-in-wsl-causes-docker-to-get-stuck-on-startup/151619/9

[^1_74]: https://dev.to/bowmanjd/install-docker-on-windows-wsl-without-docker-desktop-34m9/comments

[^1_75]: https://learn.microsoft.com/en-us/windows/wsl/kernel-release-notes

[^1_76]: https://www.reddit.com/r/linuxquestions/comments/a1k9k3/nftables_issues/

[^1_77]: https://forums.developer.nvidia.com/t/iptables-error-message/333007

[^1_78]: https://community.avg.com/t/wsl-wont-is-being-blocked-by-the-enhanced-firewall/230552

[^1_79]: https://forum.netgate.com/topic/186315/fail-to-boot-and-reload-filter-after-update-2-6-0-to-2-7-0

[^1_80]: https://github.com/Microsoft/WSL/issues

[^1_81]: https://github.com/sshuttle/sshuttle/issues/878
