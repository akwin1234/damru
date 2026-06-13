from damru.devices import get_device, get_devices_by_tier, get_random_device, pick_random_android_version
from damru.root import _detect_gpu_family


def test_moto_g_5s_plus_profile_from_adb_device() -> None:
    device = get_device("motorola_moto_g_5s_plus")

    assert get_device("Motorola Moto G (5S) Plus") is device
    assert get_device("Moto G (5S) Plus") is device
    assert device.brand == "motorola"
    assert device.manufacturer == "motorola"
    assert device.model == "Moto G (5S) Plus"
    assert device.device == "sanders"
    assert device.product == "sanders_retail"
    assert device.build_fingerprint == (
        "motorola/sanders_retail/sanders:8.1.0/OPS28.65-36-14/63857:user/release-keys"
    )
    assert device.android_version == "8.1.0"
    assert device.sdk_version == 27
    assert device.screen_width == 1080
    assert device.screen_height == 1920
    assert device.density_dpi == 480
    assert device.hardware_concurrency == 8
    assert device.device_memory == 2
    assert device.webgl_vendor == "Qualcomm"
    assert device.webgl_renderer == "Adreno (TM) 506"
    assert device.gpu_family == "adreno"
    assert pick_random_android_version(device) == (8, 27)

    props = device.system_props(safe_only=False)
    assert props["ro.product.model"] == "Moto G (5S) Plus"
    assert props["ro.product.device"] == "sanders"
    assert props["ro.product.name"] == "sanders_retail"
    assert props["ro.product.board"] == "sanders"
    assert props["ro.product.system.model"] == "Moto G (5S) Plus"
    assert props["ro.product.vendor.device"] == "sanders"
    assert props["ro.product.vendor_dlkm.device"] == "sanders"
    assert props["ro.build.fingerprint"] == device.build_fingerprint
    assert props["ro.build.flavor"] == "sanders_retail-user"
    assert props["ro.system.build.fingerprint"] == device.build_fingerprint
    assert props["ro.vendor.build.fingerprint"] == device.build_fingerprint
    assert props["ro.vendor.build.flavor"] == "sanders_retail-user"
    assert props["ro.vendor_dlkm.build.tags"] == "release-keys"
    assert props["ro.build.version.release"] == "8.1.0"
    assert props["ro.build.version.sdk"] == "27"
    assert props["ro.build.version.security_patch"] == "2020-01-05"
    assert "ro.system.build.version.sdk" not in props


def test_redmi_9a_profile_from_adb_device() -> None:
    device = get_device("xiaomi_redmi_9a")

    assert get_device("Xiaomi Redmi 9A") is device
    assert get_device("M2006C3LG") is device
    assert device.brand == "Redmi"
    assert device.manufacturer == "Xiaomi"
    assert device.model == "M2006C3LG"
    assert device.device == "dandelion"
    assert device.product == "dandelion_global"
    assert device.build_fingerprint == (
        "Redmi/dandelion_global/dandelion:11/RP1A.200720.011/V12.5.6.0.RCDMIXM:user/release-keys"
    )
    assert device.android_version == "11"
    assert device.sdk_version == 30
    assert device.screen_width == 720
    assert device.screen_height == 1600
    assert device.density_dpi == 320
    assert device.hardware_concurrency == 8
    assert device.device_memory == 2
    assert device.webgl_vendor == "Imagination Technologies"
    assert device.webgl_renderer == "PowerVR Rogue GE8320"
    assert device.gpu_family == "powervr"
    assert _detect_gpu_family("GLES: Imagination Technologies, PowerVR Rogue GE8320") == "powervr"
    assert pick_random_android_version(device) in {(10, 29), (11, 30)}

    props = device.system_props(safe_only=False)
    assert props["ro.product.model"] == "M2006C3LG"
    assert props["ro.product.device"] == "dandelion"
    assert props["ro.product.name"] == "dandelion_global"
    assert props["ro.product.product.brand"] == "Redmi"
    assert props["ro.product.odm.manufacturer"] == "Xiaomi"
    assert props["ro.product.odm_dlkm.name"] == "dandelion_global"
    assert props["ro.build.fingerprint"] == device.build_fingerprint
    assert props["ro.product.build.fingerprint"] == device.build_fingerprint
    assert props["ro.product.build.flavor"] == "dandelion_global-user"
    assert props["ro.odm.build.type"] == "user"
    assert props["ro.build.version.release"] == "11"
    assert props["ro.build.version.sdk"] == "30"
    assert props["ro.build.version.security_patch"] == "2022-07-01"


def test_safe_profile_covers_partition_identity_without_spoofing_sdk() -> None:
    device = get_device("google_pixel_8_pro")

    props = device.system_props()
    version_props = device.version_release_props()

    assert props["ro.product.system.model"] == "Pixel 8 Pro"
    assert props["ro.product.vendor.name"] == "husky"
    assert props["ro.product.vendor_dlkm.manufacturer"] == "Google"
    assert props["ro.system.build.fingerprint"] == device.build_fingerprint
    assert props["ro.vendor.build.fingerprint"] == device.build_fingerprint
    assert props["ro.odm.build.version.incremental"] == device.build_incremental
    assert "ro.build.version.release" not in props
    assert "ro.build.version.sdk" not in props
    assert "ro.system.build.version.sdk" not in props

    assert version_props["ro.build.version.release"] == device.android_version
    assert version_props["ro.build.version.release_or_codename"] == device.android_version
    assert version_props["ro.build.version.release_or_preview_display"] == device.android_version
    assert version_props["ro.system.build.version.release"] == device.android_version
    assert version_props["ro.system.build.version.release_or_codename"] == device.android_version
    assert version_props["ro.vendor.build.version.security_patch"] == device.security_patch
    assert "ro.build.version.sdk" not in version_props
    assert "ro.system.build.version.sdk" not in version_props


def test_profile_tiers_default_random_is_premium_only() -> None:
    assert len(get_devices_by_tier("premium")) == 100
    assert len(get_devices_by_tier("premium_verified")) == 51
    assert len(get_devices_by_tier("premium_new")) == 49
    assert len(get_devices_by_tier("medium")) == 38
    assert len(get_devices_by_tier("experimental")) == 17
    assert len(get_devices_by_tier("all")) == 155

    picked = {get_random_device().profile_tier for _ in range(300)}
    assert picked <= {"premium_verified", "premium_new"}
    assert picked == {"premium_verified", "premium_new"}


def test_explicit_profiles_ignore_default_tier_filter() -> None:
    device = get_device("Nokia C32")
    assert device.profile_tier == "experimental"

    picked = {get_random_device(profile_tier="all").profile_tier for _ in range(1000)}
    assert {"premium_verified", "premium_new", "medium", "experimental"} <= picked
