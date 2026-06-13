import json
import inspect
import hashlib
import shlex
import zipfile

import pytest

from damru.devices import get_device
from damru.docker import RedroidManager
from damru.root import (
    RootError,
    RootOps,
    _build_proc_mountinfo_spoof,
    _build_proc_version_spoof,
    _build_proc_cpuinfo_spoof,
    _extract_webview_native_library,
    _find_multitouch_event,
    _parse_pm_package_uids,
    _runtime_arch_deleted_props,
    _runtime_arch_props,
    _stable_android_id,
    _stable_uuid,
    _webview_version_candidates,
)


def test_build_proc_cpuinfo_spoof_uses_arm_profile() -> None:
    device = get_device("samsung_galaxy_s24")
    cpuinfo = _build_proc_cpuinfo_spoof(8, device)

    assert cpuinfo.count("processor\t:") == 8
    assert "CPU architecture: 8" in cpuinfo
    assert "Features\t: fp asimd" in cpuinfo
    assert "Qualcomm Technologies, Inc Snapdragon 8 Gen 3" in cpuinfo
    assert "AuthenticAMD" not in cpuinfo
    assert "GenuineIntel" not in cpuinfo
    assert "hypervisor" not in cpuinfo
    assert "x86" not in cpuinfo.lower()


def test_slot_identity_helpers_are_stable_and_android_like() -> None:
    slot0_id = _stable_android_id("host-0|profile")
    slot1_id = _stable_android_id("host-1|profile")
    slot0_boot_id = _stable_uuid("host-0|profile", "boot-id")
    version = _build_proc_version_spoof(get_device("xiaomi_redmi_note_12_5g"))

    assert slot0_id == _stable_android_id("host-0|profile")
    assert len(slot0_id) == 16
    assert int(slot0_id, 16) >= 0
    assert slot0_id != slot1_id
    assert slot0_boot_id == _stable_uuid("host-0|profile", "boot-id")
    assert "Linux version" in version
    assert "android" in version.lower()
    assert "Ubuntu" not in version
    assert "x86" not in version.lower()
    mountinfo = _build_proc_mountinfo_spoof()
    assert "/system" in mountinfo
    assert "docker" not in mountinfo.lower()
    assert "containerd" not in mountinfo.lower()
    assert "overlay" not in mountinfo.lower()


def test_runtime_arch_props_use_arm_abi_and_soc_hardware() -> None:
    device = get_device("samsung_galaxy_s24")
    props = _runtime_arch_props(device)

    assert props["ro.product.cpu.abi"] == "arm64-v8a"
    assert props["ro.product.cpu.abilist"] == "arm64-v8a,armeabi-v7a,armeabi"
    assert props["ro.bionic.arch"] == "arm64"
    assert props["ro.dalvik.vm.isa.arm64"] == "arm64"
    assert props["ro.debuggable"] == "0"
    assert props["ro.secure"] == "1"
    assert props["ro.adb.secure"] == "1"
    assert props["ro.hardware"] == "qcom"
    assert props["ro.boot.hardware"] == "qcom"
    assert props["ro.hardware.gralloc"] == "default"
    for partition in ("odm", "system", "vendor"):
        prefix = f"ro.{partition}.product.cpu"
        assert props[f"{prefix}.abi"] == "arm64-v8a"
        assert props[f"{prefix}.abilist64"] == "arm64-v8a"
    assert not any(key.startswith("ro.product.product.cpu.") for key in props)
    assert "x86" not in "\n".join(props.values())


def test_runtime_arch_deleted_props_cover_x86_and_redroid_residue() -> None:
    deleted = set(_runtime_arch_deleted_props())

    assert "ro.dalvik.vm.isa.x86_64" in deleted
    assert "dalvik.vm.isa.x86_64.features" in deleted
    assert "dalvik.vm.isa.x86_64.variant" in deleted
    assert "ro.boot.redroid_gpu_mode" in deleted
    assert "ro.boot.use_redroid_c2" in deleted
    assert "ro.product.product.cpu.abilist" in deleted


@pytest.mark.unit
async def test_install_native_preload_assets_pushes_library_and_proc_files(monkeypatch, tmp_path) -> None:
    fake_so = tmp_path / "libfakemem_x86_64.so"
    fake_so.write_bytes(b"so")

    class FakeADB:
        shell_root_commands: list[str] = []
        pushes: list[tuple[str, str]] = []

        async def shell(self, command: str, *args, **kwargs) -> str:
            if command.startswith("sha256sum /data/local/tmp/libfakemem.so"):
                return ""
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_commands.append(command)
            return ""

        async def push(self, source: str, destination: str) -> None:
            self.pushes.append((source, destination))

    monkeypatch.setattr(RootOps, "_compile_fakemem", staticmethod(lambda: str(fake_so)))

    adb = FakeADB()
    await RootOps(adb).install_native_preload_assets()

    assert adb.pushes == [(str(fake_so), "/data/local/tmp/libfakemem.so")]
    joined = "\n".join(adb.shell_root_commands)
    assert "chmod 755 /data/local/tmp/libfakemem.so" in joined
    assert "/data/local/tmp/damru_proc_mountinfo" in joined
    assert "chmod 0644 /data/local/tmp/damru_proc_mountinfo" in joined
    assert "/data/local/tmp/damru_fakemem_gb" not in joined
    assert "setprop wrap." not in joined


@pytest.mark.unit
async def test_install_native_preload_assets_can_write_memory_target_without_repush(monkeypatch, tmp_path) -> None:
    fake_so = tmp_path / "libfakemem_x86_64.so"
    fake_so.write_bytes(b"so")
    fake_sha = hashlib.sha256(fake_so.read_bytes()).hexdigest()

    class FakeADB:
        shell_root_commands: list[str] = []
        pushes: list[tuple[str, str]] = []

        async def shell(self, command: str, *args, **kwargs) -> str:
            if command.startswith("sha256sum /data/local/tmp/libfakemem.so"):
                return f"{fake_sha}  /data/local/tmp/libfakemem.so\n"
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_commands.append(command)
            return ""

        async def push(self, source: str, destination: str) -> None:
            self.pushes.append((source, destination))

    monkeypatch.setattr(RootOps, "_compile_fakemem", staticmethod(lambda: str(fake_so)))

    adb = FakeADB()
    await RootOps(adb).install_native_preload_assets(target_gb=8, force=False)

    assert adb.pushes == []
    joined = "\n".join(adb.shell_root_commands)
    assert "printf '%s\\n' 8 > /data/local/tmp/damru_fakemem_gb" in joined
    assert "chmod 0644 /data/local/tmp/damru_fakemem_gb" in joined
    assert "/data/local/tmp/damru_proc_mountinfo" in joined
    assert "setprop wrap." not in joined


@pytest.mark.unit
async def test_install_native_preload_assets_replaces_stale_baked_library(monkeypatch, tmp_path) -> None:
    fake_so = tmp_path / "libfakemem_x86_64.so"
    fake_so.write_bytes(b"new-so")

    class FakeADB:
        shell_root_commands: list[str] = []
        pushes: list[tuple[str, str]] = []

        async def shell(self, command: str, *args, **kwargs) -> str:
            if command.startswith("sha256sum /data/local/tmp/libfakemem.so"):
                return "oldhash  /data/local/tmp/libfakemem.so\n"
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_commands.append(command)
            return ""

        async def push(self, source: str, destination: str) -> None:
            self.pushes.append((source, destination))

    monkeypatch.setattr(RootOps, "_compile_fakemem", staticmethod(lambda: str(fake_so)))

    adb = FakeADB()
    await RootOps(adb).install_native_preload_assets(force=False)

    assert adb.pushes == [(str(fake_so), "/data/local/tmp/libfakemem.so")]


def test_bake_image_installs_native_preload_assets() -> None:
    source = inspect.getsource(RedroidManager.bake_image)

    assert "install_native_preload_assets" in source


def test_bake_image_defaults_to_redroid_base_for_custom_tags() -> None:
    source = inspect.getsource(RedroidManager.bake_image)

    assert "DAMRU_BAKE_BASE_IMAGE" in source
    assert "DAMRU_BAKE_FROM_LAUNCH_IMAGE" in source
    assert "base_image = REDROID_BASE_IMAGE" in source


def test_bake_image_keeps_startup_root_manageable_until_runtime_hardening() -> None:
    source = inspect.getsource(RedroidManager.bake_image)

    assert '("ro.debuggable", "1")' in source
    assert '("ro.secure", "0")' in source
    assert '("ro.adb.secure", "0")' in source


def test_webview_native_library_extract_accepts_libmonochrome_without_64(tmp_path) -> None:
    apk = tmp_path / "trichrome.apk"
    out = tmp_path / "libmonochrome_64.so"

    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("lib/x86_64/libmonochrome.so", b"native payload")

    assert _extract_webview_native_library(apk, out) is False
    assert out.read_bytes() == b"native payload"


def test_installed_webview_platform_patch_uses_root_access() -> None:
    source = inspect.getsource(RootOps.ensure_installed_webview_apk_platform_patch)

    assert "shell_root(find_command" in source
    assert "_pull_root_readable_file" in source


def test_live_webview_library_patcher_uses_root_discovery_and_copy() -> None:
    find_source = inspect.getsource(RedroidManager._patch_webview_x_requested_with_header)
    patch_source = inspect.getsource(RedroidManager._patch_one_webview_x_requested_with_library)

    assert "su 0 sh -c" in find_source
    assert "libmonochrome.so" in find_source
    assert "damru-libmonochrome-native-source" in patch_source
    assert '"-lc"' not in patch_source


def test_webview_xrw_native_patch_is_opt_in() -> None:
    root_source = inspect.getsource(_extract_webview_native_library)
    docker_source = inspect.getsource(RedroidManager._patch_one_webview_x_requested_with_library)

    assert "DAMRU_ENABLE_WEBVIEW_XRW_NATIVE_PATCH" in root_source
    assert "DAMRU_ENABLE_WEBVIEW_XRW_NATIVE_PATCH" in docker_source


def test_installed_webview_native_mutation_is_opt_in() -> None:
    root_source = inspect.getsource(RootOps.ensure_installed_webview_apk_platform_patch)
    docker_source = inspect.getsource(RedroidManager._patch_webview_x_requested_with_header)

    assert "DAMRU_ENABLE_INSTALLED_WEBVIEW_NATIVE_PATCH" in root_source
    assert "DAMRU_ENABLE_INSTALLED_WEBVIEW_NATIVE_PATCH" in docker_source
    assert "DAMRU_ENABLE_WEBVIEW_XRW_NATIVE_PATCH" in docker_source


@pytest.mark.unit
async def test_setup_memory_preload_can_wrap_webview_renderer_targets(monkeypatch, tmp_path) -> None:
    fake_so = tmp_path / "libfakemem_x86_64.so"
    fake_so.write_bytes(b"so")
    fake_sha = hashlib.sha256(fake_so.read_bytes()).hexdigest()

    class FakeADB:
        shell_root_commands: list[str] = []
        props: dict[str, str] = {}

        async def shell(self, command: str, *args, **kwargs) -> str:
            if command.startswith("sha256sum /data/local/tmp/libfakemem.so"):
                return f"{fake_sha}  /data/local/tmp/libfakemem.so\n"
            if command == "test -f /system/bin/app_process64.real && echo OK":
                return ""
            if command == "test -f /data/local/tmp/libfakemem.so && echo OK":
                return "OK\n"
            if command.startswith("getprop wrap."):
                key = command.removeprefix("getprop ").strip()
                return self.props.get(key, "") + "\n"
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_commands.append(command)
            if command.startswith("setprop wrap."):
                _, key, value = command.split(" ", 2)
                self.props[key] = value
            return ""

    monkeypatch.setattr(RootOps, "_compile_fakemem", staticmethod(lambda: str(fake_so)))

    adb = FakeADB()
    await RootOps(adb).setup_memory_preload(
        "com.android.browser",
        extra_packages=("com.android.webview",),
        restart_webview_zygote=True,
    )

    joined = "\n".join(adb.shell_root_commands)
    assert "setprop wrap.com.android.browser /data/local/tmp/damru_chrome_wrap.sh" in joined
    assert "setprop wrap.com.android.webview /data/local/tmp/damru_chrome_wrap.sh" in joined
    assert "setprop wrap.webview_zygote" not in joined
    assert "killall webview_zygote" in joined


@pytest.mark.unit
async def test_setup_native_proc_preload_removes_memory_target_and_wraps_package(monkeypatch, tmp_path) -> None:
    fake_so = tmp_path / "libfakemem_x86_64.so"
    fake_so.write_bytes(b"so")
    fake_sha = hashlib.sha256(fake_so.read_bytes()).hexdigest()

    class FakeADB:
        shell_root_commands: list[str] = []
        props: dict[str, str] = {}

        async def shell(self, command: str, *args, **kwargs) -> str:
            if command.startswith("sha256sum /data/local/tmp/libfakemem.so"):
                return f"{fake_sha}  /data/local/tmp/libfakemem.so\n"
            if command == "test -f /system/bin/app_process64.real && echo OK":
                return ""
            if command == "test -f /data/local/tmp/libfakemem.so && echo OK":
                return "OK\n"
            if command.startswith("getprop wrap."):
                key = command.removeprefix("getprop ").strip()
                return self.props.get(key, "") + "\n"
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_commands.append(command)
            if command.startswith("setprop wrap."):
                _, key, value = command.split(" ", 2)
                self.props[key] = value
            return ""

    monkeypatch.setattr(RootOps, "_compile_fakemem", staticmethod(lambda: str(fake_so)))

    adb = FakeADB()
    await RootOps(adb).setup_native_proc_preload("com.android.browser")

    joined = "\n".join(adb.shell_root_commands)
    assert "/data/local/tmp/damru_proc_mountinfo" in joined
    assert "rm -f /data/local/tmp/damru_fakemem_gb" in joined
    assert "printf '%s\\n'" not in joined
    assert "setprop wrap.com.android.browser /data/local/tmp/damru_chrome_wrap.sh" in joined


@pytest.mark.unit
async def test_apply_runtime_arch_props_sets_arm_values_and_deletes_leaks() -> None:
    class FakeADB:
        props: dict[str, str] = {}
        shell_root_commands: list[str] = []

        async def shell(self, command: str, *args, **kwargs) -> str:
            if command.startswith("cmd package list packages"):
                return "package:android\n"
            if command == "which resetprop":
                return "/system/bin/resetprop\n"
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_commands.append(command)
            for line in command.splitlines():
                parts = shlex.split(line)
                if len(parts) >= 3 and parts[0].endswith("resetprop"):
                    self.props[parts[1]] = parts[2]
            return ""

        async def get_prop(self, key: str) -> str:
            return self.props.get(key, "")

    adb = FakeADB()
    await RootOps(adb).apply_runtime_arch_props(get_device("xiaomi_redmi_note_12_5g"))

    assert adb.props["ro.product.cpu.abi"] == "arm64-v8a"
    assert adb.props["ro.bionic.arch"] == "arm64"
    assert adb.props["ro.debuggable"] == "0"
    assert adb.props["ro.secure"] == "1"
    assert adb.props["ro.adb.secure"] == "1"
    assert adb.props["ro.hardware"] == "qcom"
    assert adb.props["ro.hardware.gralloc"] == "default"
    joined = "\n".join(adb.shell_root_commands)
    assert "--delete ro.dalvik.vm.isa.x86_64" in joined
    assert "--delete dalvik.vm.isa.x86_64.features" in joined
    assert "--delete ro.boot.redroid_gpu_mode" in joined
    assert "--delete ro.boot.use_redroid_stream" in joined
    assert "--delete ro.product.product.cpu.abilist" in joined


@pytest.mark.unit
async def test_apply_slot_identity_spoof_sets_secure_id_and_proc_bind_mounts() -> None:
    seed = "host-0|profile"
    expected_android_id = _stable_android_id(seed)
    expected_boot_id = _stable_uuid(seed, "boot-id")

    class FakeADB:
        shell_root_commands: list[str] = []

        async def shell(self, command: str, *args, **kwargs) -> str:
            if command == "settings get secure android_id":
                return expected_android_id
            if command == "cat /proc/sys/kernel/random/boot_id":
                return expected_boot_id
            if command == "cat /proc/version":
                return _build_proc_version_spoof(get_device("xiaomi_redmi_note_12_5g"))
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_commands.append(command)
            return ""

    adb = FakeADB()
    result = await RootOps(adb).apply_slot_identity_spoof(
        seed,
        device=get_device("xiaomi_redmi_note_12_5g"),
    )

    assert result is True
    joined = "\n".join(adb.shell_root_commands)
    assert f"settings put secure android_id {expected_android_id}" in joined
    assert "mount --bind /data/local/tmp/damru_proc_boot_id /proc/sys/kernel/random/boot_id" in joined
    assert "mount --bind /data/local/tmp/damru_proc_version /proc/version" in joined
    assert "/data/local/tmp/damru_proc_mountinfo" in joined


def test_webview_version_candidates_include_trimmed_version_and_major() -> None:
    assert _webview_version_candidates("148.0.7778.178.0") == [
        "148.0.7778.178.0",
        "148.0.7778.178",
        "148",
    ]


def test_find_multitouch_event_from_proc_devices() -> None:
    devices = """
I: Bus=0006 Vendor=18d1 Product=4ee7 Version=0001
N: Name="goodix_ts"
H: Handlers=mouse2 event4
B: PROP=2
B: EV=b
"""

    assert _find_multitouch_event(devices) == ("event4", 68)


def test_parse_pm_package_uids_filters_unsafe_entries() -> None:
    output = """
package:android uid:1000
package:com.android.permissioncontroller uid:10076
package:app.vanadium.trichromelibrary_777817839 uid:10137
package:bad/pkg uid:10100
package:com.android.permissioncontroller uid:10076
package:com.example.no_uid
"""

    assert _parse_pm_package_uids(output) == [
        ("com.android.permissioncontroller", 10076),
        ("app.vanadium.trichromelibrary_777817839", 10137),
    ]


@pytest.mark.unit
async def test_repair_app_data_dirs_builds_native_reconcile_script() -> None:
    class FakeADB:
        shell_root_command = ""

        async def shell(self, command: str, *args, **kwargs) -> str:
            assert command == "pm list packages -U"
            return (
                "package:com.android.inputmethod.latin uid:10052\n"
                "package:com.android.permissioncontroller uid:10076\n"
            )

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_command = command
            return "damru_app_data_dirs_created=3\n"

    adb = FakeADB()
    package_count, created_count = await RootOps(adb).repair_app_data_dirs()

    assert package_count == 2
    assert created_count == 3
    assert "for base in /data/user_de/0 /data/user/0" in adb.shell_root_command
    assert "com.android.inputmethod.latin 10052" in adb.shell_root_command
    assert "com.android.permissioncontroller 10076" in adb.shell_root_command
    assert "restorecon -R /data/user_de/0 /data/user/0" in adb.shell_root_command


@pytest.mark.unit
async def test_ensure_multitouch_stack_writes_xml_and_event_node() -> None:
    class FakeADB:
        shell_root_commands: list[str] = []

        async def shell(self, command: str, *args, **kwargs) -> str:
            if command.startswith("cat /proc/bus/input/devices"):
                return 'N: Name="goodix_ts"\nH: Handlers=mouse2 event4\nB: PROP=2\n'
            if command.startswith("pm list features"):
                return "feature:android.hardware.touchscreen\n"
            if command.startswith("cmd package list packages"):
                return "package:android\n"
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_commands.append(command)
            return ""

    adb = FakeADB()
    assert await RootOps(adb).ensure_multitouch_stack() is True

    joined = "\n".join(adb.shell_root_commands)
    assert "damru_multitouch.xml" in joined
    assert "mknod /dev/input/event4 c 13 68" in joined
    assert "chown 0:1000 /dev/input/event4" in joined
    assert "setprop ctl.restart zygote" not in joined


@pytest.mark.unit
async def test_apply_gpu_binary_spoof_skips_restart_when_renderer_already_patched() -> None:
    class FakeADB:
        shell_commands: list[str] = []
        shell_root_commands: list[str] = []

        async def shell(self, command: str, *args, **kwargs) -> str:
            self.shell_commands.append(command)
            if command.startswith("test -f /vendor/lib64/hw/vulkan.pastel.so"):
                return "OK\n"
            if command.startswith("cat /data/local/tmp/damru_gpu_binary_spoof.json"):
                return json.dumps(
                    {
                        "renderer": "Adreno (TM) 619",
                        "vendor": "Qualcomm",
                        "vendor_id": 0x5143,
                        "device_id": 0x043A,
                        "gpu_family": "adreno",
                    }
                )
            if command.startswith("pm path android"):
                return "package:/system/framework/framework-res.apk\n"
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            self.shell_root_commands.append(command)
            return ""

    adb = FakeADB()
    device = get_device("xiaomi_redmi_note_12_5g")

    await RootOps(adb).apply_gpu_binary_spoof(device)

    assert any("damru_gpu_binary_spoof.json" in command for command in adb.shell_commands)
    assert not any("surfaceflinger" in command for command in adb.shell_root_commands)


@pytest.mark.unit
async def test_apply_gpu_binary_spoof_rejects_cross_family_repatch() -> None:
    class FakeADB:
        async def shell(self, command: str, *args, **kwargs) -> str:
            if command.startswith("test -f /vendor/lib64/hw/vulkan.pastel.so"):
                return "OK\n"
            if command.startswith("cat /data/local/tmp/damru_gpu_binary_spoof.json"):
                return json.dumps(
                    {
                        "renderer": "Adreno (TM) 619",
                        "vendor": "Qualcomm",
                        "vendor_id": 0x5143,
                        "device_id": 0x043A,
                        "gpu_family": "adreno",
                    }
                )
            return ""

        async def shell_root(self, command: str, *args, **kwargs) -> str:
            raise AssertionError("cross-family GPU patch should fail before root writes")

    with pytest.raises(RootError, match="already patched for adreno"):
        await RootOps(FakeADB()).apply_gpu_binary_spoof(get_device("samsung_galaxy_a35"))
