"""Android device profile database for damru.

Each profile includes Android system props, screen specs, GPU, and SoC info
needed for complete device identity spoofing via root.

GPU spoofing uses renderer.config to override BOTH the renderer string AND
the GL extension list per-app, so any GPU family can be spoofed on any emulator.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Raw OpenGL ES extension lists per GPU family.
# renderer.config's CustomizedGLESExtension replaces the entire extension list
# when the target GPU family differs from the emulator's native GPU.
# ---------------------------------------------------------------------------

# Mali Valhall (G68, G78, G610, G710, G715) — Tensor, Exynos, Dimensity
_MALI_GL_EXTENSIONS = (
    "GL_ARM_mali_program_binary GL_ARM_mali_shader_binary GL_ARM_rgba8 "
    "GL_ARM_shader_framebuffer_fetch GL_ARM_shader_framebuffer_fetch_depth_stencil "
    "GL_EXT_blend_minmax GL_EXT_color_buffer_float GL_EXT_color_buffer_half_float "
    "GL_EXT_copy_image GL_EXT_debug_marker GL_EXT_discard_framebuffer "
    "GL_EXT_disjoint_timer_query GL_EXT_draw_buffers_indexed "
    "GL_EXT_draw_elements_base_vertex GL_EXT_EGL_image_storage GL_EXT_float_blend "
    "GL_EXT_geometry_shader GL_EXT_gpu_shader5 "
    "GL_EXT_multisampled_render_to_texture GL_EXT_multisampled_render_to_texture2 "
    "GL_EXT_occlusion_query_boolean GL_EXT_primitive_bounding_box "
    "GL_EXT_read_format_bgra GL_EXT_robustness GL_EXT_sRGB GL_EXT_sRGB_write_control "
    "GL_EXT_shader_io_blocks GL_EXT_shader_pixel_local_storage "
    "GL_EXT_tessellation_shader GL_EXT_texture_border_clamp GL_EXT_texture_buffer "
    "GL_EXT_texture_compression_astc_decode_mode GL_EXT_texture_compression_dxt1 "
    "GL_EXT_texture_compression_s3tc GL_EXT_texture_compression_s3tc_srgb "
    "GL_EXT_texture_cube_map_array GL_EXT_texture_filter_anisotropic "
    "GL_EXT_texture_format_BGRA8888 GL_EXT_texture_rg GL_EXT_texture_storage "
    "GL_EXT_texture_type_2_10_10_10_REV "
    "GL_KHR_blend_equation_advanced GL_KHR_debug GL_KHR_no_error "
    "GL_KHR_robust_buffer_access_behavior GL_KHR_texture_compression_astc_hdr "
    "GL_KHR_texture_compression_astc_ldr GL_KHR_texture_compression_astc_sliced_3d "
    "GL_OES_compressed_EAC_R11_signed_texture GL_OES_compressed_EAC_R11_unsigned_texture "
    "GL_OES_compressed_EAC_RG11_signed_texture GL_OES_compressed_EAC_RG11_unsigned_texture "
    "GL_OES_compressed_ETC1_RGB8_texture GL_OES_compressed_ETC2_RGB8_texture "
    "GL_OES_compressed_ETC2_RGBA8_texture "
    "GL_OES_compressed_ETC2_punchthroughA_RGBA8_texture "
    "GL_OES_compressed_ETC2_punchthroughA_sRGB8_alpha_texture "
    "GL_OES_compressed_ETC2_sRGB8_alpha8_texture GL_OES_compressed_ETC2_sRGB8_texture "
    "GL_OES_copy_image GL_OES_depth24 GL_OES_depth_texture "
    "GL_OES_depth_texture_cube_map GL_OES_draw_elements_base_vertex "
    "GL_OES_element_index_uint GL_OES_fbo_render_mipmap GL_OES_geometry_shader "
    "GL_OES_get_program_binary GL_OES_mapbuffer GL_OES_packed_depth_stencil "
    "GL_OES_primitive_bounding_box GL_OES_rgb8_rgba8 GL_OES_sample_shading "
    "GL_OES_sample_variables GL_OES_shader_image_atomic GL_OES_shader_io_blocks "
    "GL_OES_shader_multisample_interpolation GL_OES_standard_derivatives "
    "GL_OES_surfaceless_context GL_OES_tessellation_shader GL_OES_texture_3D "
    "GL_OES_texture_border_clamp GL_OES_texture_buffer GL_OES_texture_cube_map_array "
    "GL_OES_texture_float GL_OES_texture_float_linear GL_OES_texture_half_float "
    "GL_OES_texture_half_float_linear GL_OES_texture_npot GL_OES_texture_stencil8 "
    "GL_OES_texture_storage_multisample_2d_array GL_OES_vertex_array_object "
    "GL_OES_vertex_half_float GL_OVR_multiview GL_OVR_multiview2 "
    "GL_OVR_multiview_multisampled_render_to_texture"
)

# Samsung Xclipse (AMD RDNA2-based) — Exynos 1480/2200/2300/2400
_XCLIPSE_GL_EXTENSIONS = (
    "GL_EXT_blend_minmax GL_EXT_color_buffer_float GL_EXT_color_buffer_half_float "
    "GL_EXT_copy_image GL_EXT_debug_marker GL_EXT_discard_framebuffer "
    "GL_EXT_disjoint_timer_query GL_EXT_draw_buffers_indexed "
    "GL_EXT_draw_elements_base_vertex GL_EXT_float_blend "
    "GL_EXT_geometry_shader GL_EXT_gpu_shader5 "
    "GL_EXT_multisampled_render_to_texture GL_EXT_multisampled_render_to_texture2 "
    "GL_EXT_occlusion_query_boolean GL_EXT_primitive_bounding_box "
    "GL_EXT_read_format_bgra GL_EXT_robustness GL_EXT_sRGB GL_EXT_sRGB_write_control "
    "GL_EXT_shader_io_blocks "
    "GL_EXT_tessellation_shader GL_EXT_texture_border_clamp GL_EXT_texture_buffer "
    "GL_EXT_texture_compression_bptc GL_EXT_texture_compression_dxt1 "
    "GL_EXT_texture_compression_rgtc "
    "GL_EXT_texture_compression_s3tc GL_EXT_texture_compression_s3tc_srgb "
    "GL_EXT_texture_cube_map_array GL_EXT_texture_filter_anisotropic "
    "GL_EXT_texture_format_BGRA8888 GL_EXT_texture_rg GL_EXT_texture_storage "
    "GL_KHR_blend_equation_advanced GL_KHR_debug GL_KHR_no_error "
    "GL_KHR_texture_compression_astc_ldr "
    "GL_OES_compressed_EAC_R11_signed_texture GL_OES_compressed_EAC_R11_unsigned_texture "
    "GL_OES_compressed_EAC_RG11_signed_texture GL_OES_compressed_EAC_RG11_unsigned_texture "
    "GL_OES_compressed_ETC1_RGB8_texture GL_OES_compressed_ETC2_RGB8_texture "
    "GL_OES_compressed_ETC2_RGBA8_texture "
    "GL_OES_compressed_ETC2_punchthroughA_RGBA8_texture "
    "GL_OES_compressed_ETC2_punchthroughA_sRGB8_alpha_texture "
    "GL_OES_compressed_ETC2_sRGB8_alpha8_texture GL_OES_compressed_ETC2_sRGB8_texture "
    "GL_OES_copy_image GL_OES_depth24 GL_OES_depth_texture "
    "GL_OES_depth_texture_cube_map GL_OES_draw_elements_base_vertex "
    "GL_OES_element_index_uint GL_OES_fbo_render_mipmap GL_OES_geometry_shader "
    "GL_OES_packed_depth_stencil "
    "GL_OES_primitive_bounding_box GL_OES_rgb8_rgba8 GL_OES_sample_shading "
    "GL_OES_sample_variables GL_OES_shader_image_atomic GL_OES_shader_io_blocks "
    "GL_OES_shader_multisample_interpolation GL_OES_standard_derivatives "
    "GL_OES_surfaceless_context GL_OES_tessellation_shader GL_OES_texture_3D "
    "GL_OES_texture_border_clamp GL_OES_texture_buffer GL_OES_texture_cube_map_array "
    "GL_OES_texture_float GL_OES_texture_float_linear GL_OES_texture_half_float "
    "GL_OES_texture_half_float_linear GL_OES_texture_npot GL_OES_texture_stencil8 "
    "GL_OES_texture_storage_multisample_2d_array GL_OES_vertex_array_object "
    "GL_OES_vertex_half_float"
)

# Exported mapping for root.py GPU spoof
GPU_EXTENSIONS: Dict[str, str] = {
    "mali": _MALI_GL_EXTENSIONS,
    "xclipse": _XCLIPSE_GL_EXTENSIONS,
    # "adreno" is NOT here — native Adreno extensions are already correct
}


@dataclass(frozen=True)
class AndroidDevice:
    """Complete Android device profile with system props."""

    # Display name
    name: str

    # System props (ro.product.*)
    brand: str           # ro.product.brand
    manufacturer: str    # ro.product.manufacturer
    model: str           # ro.product.model
    device: str          # ro.product.device
    product: str         # ro.product.name

    # Build info (ro.build.*)
    build_fingerprint: str   # ro.build.fingerprint
    android_version: str     # ro.build.version.release
    sdk_version: int         # ro.build.version.sdk
    build_id: str            # ro.build.display.id
    security_patch: str      # ro.build.version.security_patch

    # Screen (default / native resolution)
    screen_width: int
    screen_height: int
    density_dpi: int

    # Hardware
    hardware_concurrency: int
    device_memory: int       # Chrome-capped (max 8)
    max_touch_points: int

    # GPU
    webgl_vendor: str
    webgl_renderer: str

    # SoC (informational — documents which chipset this variant uses)
    chipset: str = ""

    # All Android versions this device has run (launch + updates).
    # Used for random OS version selection per session.
    # Empty tuple = only the android_version field is valid.
    supported_android_versions: Tuple[int, ...] = ()

    @property
    def device_pixel_ratio(self) -> float:
        return self.density_dpi / 160.0

    @property
    def gpu_family(self) -> str:
        """GPU family: 'adreno', 'mali', 'xclipse', or 'unknown'.

        Used to filter devices by emulator GPU compatibility.
        MuMu emulates Adreno, so only 'adreno' devices are safe there.
        """
        v = self.webgl_vendor.lower()
        r = self.webgl_renderer.lower()
        if "qualcomm" in v or "adreno" in r:
            return "adreno"
        if "arm" in v or "mali" in r:
            return "mali"
        if "samsung" in v or "xclipse" in r:
            return "xclipse"
        return "unknown"

    def system_props(self, safe_only: bool = True) -> Dict[str, str]:
        """Return dict of Android system properties to set via resetprop.

        Args:
            safe_only: If True (default), skip ro.build.version.release/sdk
                       to avoid crashing Chrome when the target Android version
                       differs from the emulator's actual version.
        """
        incremental = self.build_fingerprint.rsplit("/", 1)[0].rsplit(":", 1)[-1] if "/" in self.build_fingerprint else ""
        props = {
            "ro.product.model": self.model,
            "ro.product.brand": self.brand,
            "ro.product.manufacturer": self.manufacturer,
            "ro.product.device": self.device,
            "ro.product.name": self.product,
            "ro.build.fingerprint": self.build_fingerprint,
            "ro.build.description": f"{self.product}-user {self.android_version} {self.build_id} {incremental} release-keys",
            "ro.build.display.id": self.build_id,
        }
        if not safe_only:
            props.update({
                "ro.build.version.release": self.android_version,
                "ro.build.version.sdk": str(self.sdk_version),
                "ro.build.version.security_patch": self.security_patch,
            })
        return props

    def version_release_props(self) -> Dict[str, str]:
        """Return only release + security_patch props safe to spoof independently.

        Does NOT include ro.build.version.sdk because changing the API level
        can crash native code when it mismatches the actual runtime.
        ro.build.version.release is just the display string Chrome uses for its
        User-Agent at startup — Workers inherit it automatically.
        """
        return {
            "ro.build.version.release": self.android_version,
            "ro.build.version.security_patch": self.security_patch,
        }


# ---------------------------------------------------------------------------
# Screen size variants for devices with WQHD+ displays.
# Many flagships ship at FHD+ by default and let users toggle WQHD+.
# Format: device_name → list of (width, height, dpi)
# ---------------------------------------------------------------------------
SCREEN_VARIANTS: Dict[str, List[Tuple[int, int, int]]] = {
    # Samsung S24 Ultra: WQHD+ native, FHD+ default
    "Samsung Galaxy S24 Ultra": [
        (1440, 3120, 560),   # WQHD+ (Settings → Display → Screen resolution)
        (1080, 2340, 420),   # FHD+ (factory default)
    ],
    "Samsung Galaxy S23 Ultra": [
        (1440, 3088, 560),
        (1080, 2316, 420),
    ],
    "Samsung Galaxy S25 Ultra": [
        (1440, 3120, 560),
        (1080, 2340, 420),
    ],
    "Samsung Galaxy S22 Ultra": [
        (1440, 3088, 560),
        (1080, 2316, 420),
    ],
    # OnePlus 12: WQHD+ selectable
    "OnePlus 12": [
        (1440, 3168, 560),
        (1080, 2376, 420),
    ],
    "OnePlus 11": [
        (1440, 3216, 560),
        (1080, 2412, 420),
    ],
    "OnePlus 10 Pro": [
        (1440, 3216, 560),
        (1080, 2412, 420),
    ],
    # Xiaomi 12 Pro: WQHD+ selectable
    "Xiaomi 12 Pro": [
        (1440, 3200, 560),
        (1080, 2400, 420),
    ],
    # Google Pixel 6 Pro: WQHD+ native, can run FHD+
    "Google Pixel 6 Pro": [
        (1440, 3120, 560),
        (1080, 2340, 420),
    ],
    # OPPO Find X7 Ultra: WQHD+ selectable
    "OPPO Find X7 Ultra": [
        (1440, 3168, 560),
        (1080, 2376, 420),
    ],
    # OnePlus 13: WQHD+ selectable
    "OnePlus 13": [
        (1440, 3168, 560),
        (1080, 2376, 420),
    ],
    # POCO F6 Pro: WQHD+ selectable
    "POCO F6 Pro": [
        (1440, 3200, 560),
        (1080, 2400, 420),
    ],
}


# ---------------------------------------------------------------------------
# Device database - Real Android devices with verified build fingerprints
# ---------------------------------------------------------------------------

DEVICES: List[AndroidDevice] = [
    # =====================================================================
    # Qualcomm Snapdragon — Adreno GPU (compatible with MuMu)
    # =====================================================================

    # ---- Samsung Galaxy S24 Ultra (Snapdragon 8 Gen 3) ----
    AndroidDevice(
        name="Samsung Galaxy S24 Ultra",
        brand="samsung", manufacturer="samsung",
        model="SM-S928B", device="e3q", product="e3qxxx",
        build_fingerprint="samsung/e3qxxx/e3q:14/UP1A.231005.007/S928BXXS4AXL1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-12-01",
        screen_width=1440, screen_height=3120, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Snapdragon 8 Gen 3",
        supported_android_versions=(14, 15),
    ),
    # ---- Samsung Galaxy S24 (Snapdragon 8 Gen 3) ----
    AndroidDevice(
        name="Samsung Galaxy S24",
        brand="samsung", manufacturer="samsung",
        model="SM-S921B", device="e1q", product="e1qxxx",
        build_fingerprint="samsung/e1qxxx/e1q:14/UP1A.231005.007/S921BXXS4AXL1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-12-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Snapdragon 8 Gen 3",
        supported_android_versions=(14, 15),
    ),
    # ---- Samsung Galaxy S23 Ultra (Snapdragon 8 Gen 2) ----
    AndroidDevice(
        name="Samsung Galaxy S23 Ultra",
        brand="samsung", manufacturer="samsung",
        model="SM-S918B", device="dm3q", product="dm3qxxx",
        build_fingerprint="samsung/dm3qxxx/dm3q:14/UP1A.231005.007/S918BXXS7CXK3:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-11-01",
        screen_width=1440, screen_height=3088, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Snapdragon 8 Gen 2",
        supported_android_versions=(13, 14, 15),
    ),
    # ---- Samsung Galaxy S23 (Snapdragon 8 Gen 2) ----
    AndroidDevice(
        name="Samsung Galaxy S23",
        brand="samsung", manufacturer="samsung",
        model="SM-S911B", device="dm1q", product="dm1qxxx",
        build_fingerprint="samsung/dm1qxxx/dm1q:14/UP1A.231005.007/S911BXXS7CXK3:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-11-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Snapdragon 8 Gen 2",
        supported_android_versions=(13, 14, 15),
    ),
    # ---- Samsung Galaxy S23 FE (Exynos 2200) ----
    AndroidDevice(
        name="Samsung Galaxy S23 FE",
        brand="samsung", manufacturer="samsung",
        model="SM-S711B", device="r11s", product="r11sxxx",
        build_fingerprint="samsung/r11sxxx/r11s:14/UP1A.231005.007/S711BXXS6CXK3:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-11-01",
        screen_width=1080, screen_height=2340, density_dpi=450,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Samsung", webgl_renderer="Samsung Xclipse 920",
        chipset="Exynos 2200",
        supported_android_versions=(13, 14, 15, 16),
    ),
    # ---- Samsung Galaxy S25 Ultra (Snapdragon 8 Elite) ----
    AndroidDevice(
        name="Samsung Galaxy S25 Ultra",
        brand="samsung", manufacturer="samsung",
        model="SM-S938B", device="e4q", product="e4qxxx",
        build_fingerprint="samsung/e4qxxx/e4q:15/AP3A.241005.015/S938BXXU1AXL6:user/release-keys",
        android_version="15", sdk_version=35,
        build_id="AP3A.241005.015", security_patch="2025-01-01",
        screen_width=1440, screen_height=3120, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 830",
        chipset="Snapdragon 8 Elite",
        supported_android_versions=(15,),
    ),
    # ---- Samsung Galaxy S25 (Snapdragon 8 Elite) ----
    AndroidDevice(
        name="Samsung Galaxy S25",
        brand="samsung", manufacturer="samsung",
        model="SM-S931B", device="e1s", product="e1sxxx",
        build_fingerprint="samsung/e1sxxx/e1s:15/AP3A.241005.015/S931BXXU1AXL5:user/release-keys",
        android_version="15", sdk_version=35,
        build_id="AP3A.241005.015", security_patch="2025-01-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 830",
        chipset="Snapdragon 8 Elite",
        supported_android_versions=(15,),
    ),
    # ---- OnePlus 12 (Snapdragon 8 Gen 3) ----
    AndroidDevice(
        name="OnePlus 12",
        brand="OnePlus", manufacturer="OnePlus",
        model="CPH2583", device="taro", product="CPH2583",
        build_fingerprint="OnePlus/CPH2583/taro:14/UKQ1.230924.001/T.1806b32_1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.230924.001", security_patch="2024-10-05",
        screen_width=1440, screen_height=3168, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Snapdragon 8 Gen 3",
        supported_android_versions=(14, 15),
    ),
    # ---- OnePlus 11 (Snapdragon 8 Gen 2) ----
    AndroidDevice(
        name="OnePlus 11",
        brand="OnePlus", manufacturer="OnePlus",
        model="CPH2449", device="salami", product="CPH2449",
        build_fingerprint="OnePlus/CPH2449/salami:14/UKQ1.230924.001/U.R4T1.1587d0a_1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.230924.001", security_patch="2024-09-05",
        screen_width=1440, screen_height=3216, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Snapdragon 8 Gen 2",
        supported_android_versions=(13, 14, 15),
    ),
    # ---- Xiaomi 14 (Snapdragon 8 Gen 3) ----
    AndroidDevice(
        name="Xiaomi 14",
        brand="Xiaomi", manufacturer="Xiaomi",
        model="23127PN0CG", device="houji", product="houji_global",
        build_fingerprint="Xiaomi/houji_global/houji:14/UKQ1.231003.002/V816.0.5.0.UNCINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-09-01",
        screen_width=1200, screen_height=2670, density_dpi=480,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Snapdragon 8 Gen 3",
        supported_android_versions=(14, 15),
    ),
    # ---- Xiaomi 13 (Snapdragon 8 Gen 2) ----
    AndroidDevice(
        name="Xiaomi 13",
        brand="Xiaomi", manufacturer="Xiaomi",
        model="2211133G", device="fuxi", product="fuxi_global",
        build_fingerprint="Xiaomi/fuxi_global/fuxi:14/UKQ1.231003.002/V816.0.3.0.UMCINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-08-01",
        screen_width=1080, screen_height=2400, density_dpi=440,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Snapdragon 8 Gen 2",
        supported_android_versions=(13, 14, 15),
    ),
    # ---- Nothing Phone (2) (Snapdragon 8+ Gen 1) ----
    AndroidDevice(
        name="Nothing Phone (2)",
        brand="Nothing", manufacturer="Nothing",
        model="A065", device="Pong", product="Pong",
        build_fingerprint="Nothing/Pong/Pong:14/UP1A.231005.007/2410221830:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-10-05",
        screen_width=1080, screen_height=2412, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Snapdragon 8+ Gen 1",
        supported_android_versions=(13, 14, 15),
    ),
    # ---- Xiaomi Redmi Note 13 Pro (Snapdragon 7s Gen 2) ----
    AndroidDevice(
        name="Xiaomi Redmi Note 13 Pro",
        brand="Redmi", manufacturer="Xiaomi",
        model="23106RN0DA", device="garnet", product="garnet_global",
        build_fingerprint="Redmi/garnet_global/garnet:14/UKQ1.231003.002/V816.0.4.0.UNRMIXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-08-01",
        screen_width=1220, screen_height=2712, density_dpi=440,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 710",
        chipset="Snapdragon 7s Gen 2",
        supported_android_versions=(14, 15),
    ),
    # ---- OPPO Find X7 Ultra (Snapdragon 8 Gen 3) ----
    AndroidDevice(
        name="OPPO Find X7 Ultra",
        brand="OPPO", manufacturer="OPPO",
        model="CPH2603", device="aston", product="CPH2603",
        build_fingerprint="OPPO/CPH2603/aston:14/UP1A.231005.007/T.R4T1.1612a0b:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-10-05",
        screen_width=1440, screen_height=3168, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Snapdragon 8 Gen 3",
        supported_android_versions=(14, 15),
    ),
    # ---- Realme GT 5 Pro (Snapdragon 8 Gen 3) ----
    AndroidDevice(
        name="Realme GT 5 Pro",
        brand="realme", manufacturer="realme",
        model="RMX3888", device="aston", product="RMX3888",
        build_fingerprint="realme/RMX3888/aston:14/UP1A.231005.007/T.1752c3e_1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-10-05",
        screen_width=1264, screen_height=2780, density_dpi=480,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Snapdragon 8 Gen 3",
        supported_android_versions=(14, 15),
    ),

    # ---- Samsung Galaxy S22 Ultra (Snapdragon 8 Gen 1) [Android 12] ----
    AndroidDevice(
        name="Samsung Galaxy S22 Ultra",
        brand="samsung", manufacturer="samsung",
        model="SM-S908B", device="b0q", product="b0qxxx",
        build_fingerprint="samsung/b0qxxx/b0q:12/SP1A.210812.016/S908BXXU3CVL1:user/release-keys",
        android_version="12", sdk_version=32,
        build_id="SP1A.210812.016", security_patch="2022-12-01",
        screen_width=1440, screen_height=3088, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Snapdragon 8 Gen 1",
        supported_android_versions=(12, 13, 14, 15),
    ),
    # ---- Samsung Galaxy S22 (Snapdragon 8 Gen 1) [Android 12] ----
    AndroidDevice(
        name="Samsung Galaxy S22",
        brand="samsung", manufacturer="samsung",
        model="SM-S901B", device="r0q", product="r0qxxx",
        build_fingerprint="samsung/r0qxxx/r0q:12/SP1A.210812.016/S901BXXU3CVL1:user/release-keys",
        android_version="12", sdk_version=32,
        build_id="SP1A.210812.016", security_patch="2022-12-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Snapdragon 8 Gen 1",
        supported_android_versions=(12, 13, 14, 15),
    ),
    # ---- OnePlus 10 Pro (Snapdragon 8 Gen 1) [Android 12] ----
    AndroidDevice(
        name="OnePlus 10 Pro",
        brand="OnePlus", manufacturer="OnePlus",
        model="NE2210", device="ovaltine", product="ovaltine",
        build_fingerprint="OnePlus/NE2210/ovaltine:12/SKQ1.211113.001/T.125cbb5_1:user/release-keys",
        android_version="12", sdk_version=32,
        build_id="SKQ1.211113.001", security_patch="2022-11-05",
        screen_width=1440, screen_height=3216, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Snapdragon 8 Gen 1",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Xiaomi 12 Pro (Snapdragon 8 Gen 1) [Android 12] ----
    AndroidDevice(
        name="Xiaomi 12 Pro",
        brand="Xiaomi", manufacturer="Xiaomi",
        model="2201122G", device="zeus", product="zeus_global",
        build_fingerprint="Xiaomi/zeus_global/zeus:12/SKQ1.211006.001/V14.0.3.0.TLBMIXM:user/release-keys",
        android_version="12", sdk_version=32,
        build_id="SKQ1.211006.001", security_patch="2022-11-01",
        screen_width=1440, screen_height=3200, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Snapdragon 8 Gen 1",
        supported_android_versions=(12, 13, 14),
    ),

    # =====================================================================
    # ARM Mali GPU (Google Tensor, Exynos, MediaTek Dimensity)
    # WARNING: These are INCOMPATIBLE with MuMu (Adreno emulator).
    # Only use on emulators/devices with actual Mali GPU or no GPU check.
    # =====================================================================

    # ---- Google Pixel 8 Pro (Tensor G3 → Mali-G715) ----
    AndroidDevice(
        name="Google Pixel 8 Pro",
        brand="google", manufacturer="Google",
        model="Pixel 8 Pro", device="husky", product="husky",
        build_fingerprint="google/husky/husky:14/AP2A.240805.005/12025142:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="AP2A.240805.005", security_patch="2024-08-05",
        screen_width=1344, screen_height=2992, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G715-Immortalis MP11",
        chipset="Google Tensor G3",
        supported_android_versions=(14, 15),
    ),
    # ---- Google Pixel 8 (Tensor G3 → Mali-G715) ----
    AndroidDevice(
        name="Google Pixel 8",
        brand="google", manufacturer="Google",
        model="Pixel 8", device="shiba", product="shiba",
        build_fingerprint="google/shiba/shiba:14/AP2A.240805.005/12025142:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="AP2A.240805.005", security_patch="2024-08-05",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G715-Immortalis MP11",
        chipset="Google Tensor G3",
        supported_android_versions=(14, 15),
    ),
    # ---- Google Pixel 7 (Tensor G2 → Mali-G710) ----
    AndroidDevice(
        name="Google Pixel 7",
        brand="google", manufacturer="Google",
        model="Pixel 7", device="panther", product="panther",
        build_fingerprint="google/panther/panther:14/AP2A.240705.004/11860632:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="AP2A.240705.004", security_patch="2024-07-05",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G710 MP7",
        chipset="Google Tensor G2",
        supported_android_versions=(13, 14, 15),
    ),
    # ---- Google Pixel 7a (Tensor G2 → Mali-G710) ----
    AndroidDevice(
        name="Google Pixel 7a",
        brand="google", manufacturer="Google",
        model="Pixel 7a", device="lynx", product="lynx",
        build_fingerprint="google/lynx/lynx:14/AP2A.240805.005/12025142:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="AP2A.240805.005", security_patch="2024-08-05",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G710 MP7",
        chipset="Google Tensor G2",
        supported_android_versions=(13, 14, 15),
    ),
    # ---- Google Pixel 9 Pro (Tensor G4 → Mali-G715) ----
    AndroidDevice(
        name="Google Pixel 9 Pro",
        brand="google", manufacturer="Google",
        model="Pixel 9 Pro", device="caiman", product="caiman",
        build_fingerprint="google/caiman/caiman:15/AP3A.241005.015/12366759:user/release-keys",
        android_version="15", sdk_version=35,
        build_id="AP3A.241005.015", security_patch="2024-10-05",
        screen_width=1280, screen_height=2856, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G715-Immortalis MC10",
        chipset="Google Tensor G4",
        supported_android_versions=(14, 15),
    ),
    # ---- Google Pixel 9 (Tensor G4 → Mali-G715) ----
    AndroidDevice(
        name="Google Pixel 9",
        brand="google", manufacturer="Google",
        model="Pixel 9", device="tokay", product="tokay",
        build_fingerprint="google/tokay/tokay:15/AP3A.241005.015/12366759:user/release-keys",
        android_version="15", sdk_version=35,
        build_id="AP3A.241005.015", security_patch="2024-10-05",
        screen_width=1080, screen_height=2424, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G715-Immortalis MC10",
        chipset="Google Tensor G4",
        supported_android_versions=(14, 15),
    ),
    # ---- Google Pixel 6 Pro (Tensor G1 → Mali-G78) [Android 12] ----
    AndroidDevice(
        name="Google Pixel 6 Pro",
        brand="google", manufacturer="Google",
        model="Pixel 6 Pro", device="raven", product="raven",
        build_fingerprint="google/raven/raven:12/SQ3A.220705.003.A1/8672226:user/release-keys",
        android_version="12", sdk_version=32,
        build_id="SQ3A.220705.003.A1", security_patch="2022-07-05",
        screen_width=1440, screen_height=3120, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G78",
        chipset="Google Tensor G1",
        supported_android_versions=(12, 13, 14, 15),
    ),
    # ---- Google Pixel 6 (Tensor G1 → Mali-G78) [Android 12] ----
    AndroidDevice(
        name="Google Pixel 6",
        brand="google", manufacturer="Google",
        model="Pixel 6", device="oriole", product="oriole",
        build_fingerprint="google/oriole/oriole:12/SQ3A.220705.003.A1/8672226:user/release-keys",
        android_version="12", sdk_version=32,
        build_id="SQ3A.220705.003.A1", security_patch="2022-07-05",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G78",
        chipset="Google Tensor G1",
        supported_android_versions=(12, 13, 14, 15),
    ),
    # ---- Google Pixel 6a (Tensor G1 → Mali-G78) ----
    AndroidDevice(
        name="Google Pixel 6a",
        brand="google", manufacturer="Google",
        model="Pixel 6a", device="bluejay", product="bluejay",
        build_fingerprint="google/bluejay/bluejay:14/AP2A.240805.005/12025142:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="AP2A.240805.005", security_patch="2024-08-05",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G78",
        chipset="Google Tensor G1",
        supported_android_versions=(12, 13, 14, 15),
    ),
    # ---- Samsung Galaxy A54 (Exynos 1380 → Mali-G68) ----
    AndroidDevice(
        name="Samsung Galaxy A54",
        brand="samsung", manufacturer="samsung",
        model="SM-A546B", device="a54x", product="a54xnsxx",
        build_fingerprint="samsung/a54xnsxx/a54x:14/UP1A.231005.007/A546BXXS9CXK1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-11-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68",
        chipset="Exynos 1380",
        supported_android_versions=(13, 14, 15),
    ),
    # ---- Samsung Galaxy A53 (Exynos 1280 → Mali-G68) [Android 12] ----
    AndroidDevice(
        name="Samsung Galaxy A53",
        brand="samsung", manufacturer="samsung",
        model="SM-A536B", device="a53x", product="a53xnsxx",
        build_fingerprint="samsung/a53xnsxx/a53x:12/SP1A.210812.016/A536BXXU5CVL2:user/release-keys",
        android_version="12", sdk_version=32,
        build_id="SP1A.210812.016", security_patch="2022-12-01",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68",
        chipset="Exynos 1280",
        supported_android_versions=(12, 13, 14, 15),
    ),
    # ---- Samsung Galaxy A55 (Exynos 1480 → Xclipse 530) ----
    AndroidDevice(
        name="Samsung Galaxy A55",
        brand="samsung", manufacturer="samsung",
        model="SM-A556B", device="a55x", product="a55xnsxx",
        build_fingerprint="samsung/a55xnsxx/a55x:14/UP1A.231005.007/A556BXXS3AXK1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-11-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Samsung", webgl_renderer="Samsung Xclipse 530",
        chipset="Exynos 1480",
        supported_android_versions=(14, 15),
    ),
    # ---- OnePlus Nord 3 (MediaTek Dimensity 9000 → Mali-G710) ----
    AndroidDevice(
        name="OnePlus Nord 3",
        brand="OnePlus", manufacturer="OnePlus",
        model="CPH2493", device="ivan", product="CPH2493",
        build_fingerprint="OnePlus/CPH2493/ivan:14/UKQ1.230924.001/T.1703d2e_1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.230924.001", security_patch="2024-09-05",
        screen_width=1080, screen_height=2412, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G710 MC10",
        chipset="MediaTek Dimensity 9000",
        supported_android_versions=(13, 14),
    ),
    # ---- Motorola Edge 40 (MediaTek Dimensity 8020 → Mali-G77) ----
    AndroidDevice(
        name="Motorola Edge 40",
        brand="motorola", manufacturer="motorola",
        model="XT2303-1", device="lyriq", product="lyriq_g",
        build_fingerprint="motorola/lyriq_g/lyriq:14/U1TLS34.39-18-2/72e3c5:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="U1TLS34.39-18-2", security_patch="2024-09-01",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G77 MC9",
        chipset="MediaTek Dimensity 8020",
        supported_android_versions=(13, 14),
    ),

    # =====================================================================
    # Additional popular devices — new GPU strings, brands, form factors
    # =====================================================================

    # ---- OnePlus 13 (Snapdragon 8 Elite → Adreno 830) ----
    AndroidDevice(
        name="OnePlus 13",
        brand="OnePlus", manufacturer="OnePlus",
        model="CPH2655", device="aston", product="CPH2655",
        build_fingerprint="OnePlus/CPH2655/aston:15/AP3A.241005.015/T.2101b2a_1:user/release-keys",
        android_version="15", sdk_version=35,
        build_id="AP3A.241005.015", security_patch="2025-01-05",
        screen_width=1440, screen_height=3168, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 830",
        chipset="Snapdragon 8 Elite",
        supported_android_versions=(15,),
    ),
    # ---- POCO F6 (Snapdragon 8s Gen 3 → Adreno 735) ----
    AndroidDevice(
        name="POCO F6",
        brand="POCO", manufacturer="Xiaomi",
        model="24069PC21G", device="peridot", product="peridot_global",
        build_fingerprint="POCO/peridot_global/peridot:14/UKQ1.231003.002/V816.0.4.0.UNQMIXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-09-01",
        screen_width=1220, screen_height=2712, density_dpi=440,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 735",
        chipset="Snapdragon 8s Gen 3",
        supported_android_versions=(14, 15),
    ),
    # ---- Nothing Phone (1) (Snapdragon 778G+ → Adreno 642L) ----
    AndroidDevice(
        name="Nothing Phone (1)",
        brand="Nothing", manufacturer="Nothing",
        model="A063", device="Spacewar", product="Spacewar",
        build_fingerprint="Nothing/Spacewar/Spacewar:14/UP1A.231005.007/2410121830:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-10-05",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 642L",
        chipset="Snapdragon 778G+",
        supported_android_versions=(12, 13, 14, 15),
    ),
    # ---- Honor Magic6 Pro (Snapdragon 8 Gen 3 → Adreno 750) ----
    AndroidDevice(
        name="Honor Magic6 Pro",
        brand="HONOR", manufacturer="HONOR",
        model="BVL-N49", device="BVL", product="BVL-N49",
        build_fingerprint="HONOR/BVL-N49/BVL:14/HONOR.BVL-N49/601.0.0.74:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="HONOR.BVL-N49", security_patch="2024-10-01",
        screen_width=1280, screen_height=2800, density_dpi=480,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Snapdragon 8 Gen 3",
        supported_android_versions=(14, 15),
    ),
    # ---- Samsung Galaxy A35 (Exynos 1380 → Mali-G68) ----
    AndroidDevice(
        name="Samsung Galaxy A35",
        brand="samsung", manufacturer="samsung",
        model="SM-A356B", device="a35x", product="a35xnsxx",
        build_fingerprint="samsung/a35xnsxx/a35x:14/UP1A.231005.007/A356BXXS3AXK2:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-11-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68",
        chipset="Exynos 1380",
        supported_android_versions=(14, 15),
    ),
    # ---- Google Pixel 8a (Tensor G3 → Mali-G715) ----
    AndroidDevice(
        name="Google Pixel 8a",
        brand="google", manufacturer="Google",
        model="Pixel 8a", device="akita", product="akita",
        build_fingerprint="google/akita/akita:14/AP2A.240805.005/12025142:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="AP2A.240805.005", security_patch="2024-08-05",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G715-Immortalis MP11",
        chipset="Google Tensor G3",
        supported_android_versions=(14, 15),
    ),
    # ---- Nothing Phone (2a) (Dimensity 7200 Pro → Mali-G610) ----
    AndroidDevice(
        name="Nothing Phone (2a)",
        brand="Nothing", manufacturer="Nothing",
        model="A142", device="Pacman", product="Pacman",
        build_fingerprint="Nothing/Pacman/Pacman:14/UP1A.231005.007/2409281741:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-09-05",
        screen_width=1080, screen_height=2412, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC6",
        chipset="MediaTek Dimensity 7200 Pro",
        supported_android_versions=(14, 15),
    ),
    # ---- Vivo X100 (Dimensity 9300 → Immortalis-G720) ----
    AndroidDevice(
        name="Vivo X100",
        brand="vivo", manufacturer="vivo",
        model="V2324", device="PD2324", product="PD2324",
        build_fingerprint="vivo/PD2324/PD2324:14/UP1A.231005.007/compiler0928114619:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-09-05",
        screen_width=1260, screen_height=2800, density_dpi=480,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Immortalis-G720 MC12",
        chipset="MediaTek Dimensity 9300",
        supported_android_versions=(14, 15),
    ),
    # ---- OnePlus Nord 4 (Snapdragon 7+ Gen 3 → Adreno 732) ----
    AndroidDevice(
        name="OnePlus Nord 4",
        brand="OnePlus", manufacturer="OnePlus",
        model="CPH2661", device="larry", product="CPH2661",
        build_fingerprint="OnePlus/CPH2661/larry:14/UKQ1.230924.001/T.1815a2b_1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.230924.001", security_patch="2024-10-05",
        screen_width=1240, screen_height=2772, density_dpi=450,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 732",
        chipset="Snapdragon 7+ Gen 3",
        supported_android_versions=(14, 15),
    ),
    # ---- POCO F6 Pro (Snapdragon 8 Gen 2 → Adreno 740) ----
    AndroidDevice(
        name="POCO F6 Pro",
        brand="POCO", manufacturer="Xiaomi",
        model="23113RKC6G", device="vermeer", product="vermeer_global",
        build_fingerprint="POCO/vermeer_global/vermeer:14/UKQ1.231003.002/V816.0.3.0.UNKMIXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-09-01",
        screen_width=1440, screen_height=3200, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Snapdragon 8 Gen 2",
        supported_android_versions=(14, 15),
    ),
    # ---- Samsung Galaxy S24 FE (Exynos 2400e → Xclipse 940) ----
    AndroidDevice(
        name="Samsung Galaxy S24 FE",
        brand="samsung", manufacturer="samsung",
        model="SM-S721B", device="e1s", product="e1sxxx",
        build_fingerprint="samsung/e1sxxx/e1s:14/UP1A.231005.007/S721BXXU1AXK1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-11-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=10, device_memory=8, max_touch_points=5,
        webgl_vendor="Samsung", webgl_renderer="Samsung Xclipse 940",
        chipset="Exynos 2400e",
        supported_android_versions=(14, 15),
    ),
    # ---- Xiaomi 15 (Snapdragon 8 Elite → Adreno 830) ----
    AndroidDevice(
        name="Xiaomi 15",
        brand="Xiaomi", manufacturer="Xiaomi",
        model="24129PN74G", device="dada", product="dada_global",
        build_fingerprint="Xiaomi/dada_global/dada:15/AP3A.241005.015/V816.0.2.0.VACMIXM:user/release-keys",
        android_version="15", sdk_version=35,
        build_id="AP3A.241005.015", security_patch="2025-01-01",
        screen_width=1200, screen_height=2670, density_dpi=480,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 830",
        chipset="Snapdragon 8 Elite",
        supported_android_versions=(15,),
    ),
    # ---- Samsung Galaxy A15 5G (Dimensity 6100+ → Mali-G57) ----
    AndroidDevice(
        name="Samsung Galaxy A15 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-A156B", device="a15", product="a15nsxx",
        build_fingerprint="samsung/a15nsxx/a15:14/UP1A.231005.007/A156BXXS3AXK1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-11-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Dimensity 6100+",
        supported_android_versions=(14, 15),
    ),
    # ---- Samsung Galaxy S21 FE (Snapdragon 888 → Adreno 660) ----
    AndroidDevice(
        name="Samsung Galaxy S21 FE",
        brand="samsung", manufacturer="samsung",
        model="SM-G990B", device="r9q", product="r9qxxx",
        build_fingerprint="samsung/r9qxxx/r9q:14/UP1A.231005.007/G990BXXS9FXK1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-11-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 660",
        chipset="Snapdragon 888",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Xiaomi Redmi Note 12 5G (Snapdragon 4 Gen 1 → Adreno 619) ----
    AndroidDevice(
        name="Xiaomi Redmi Note 12 5G",
        brand="Redmi", manufacturer="Xiaomi",
        model="22111317G", device="sunstone", product="sunstone_global",
        build_fingerprint="Redmi/sunstone_global/sunstone:14/UKQ1.231003.002/V816.0.2.0.UMSMIXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-08-01",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 619",
        chipset="Snapdragon 4 Gen 1",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Google Pixel 9 Pro XL (Tensor G4 → Mali-G715) ----
    AndroidDevice(
        name="Google Pixel 9 Pro XL",
        brand="google", manufacturer="Google",
        model="Pixel 9 Pro XL", device="komodo", product="komodo",
        build_fingerprint="google/komodo/komodo:15/AP3A.241005.015/12366759:user/release-keys",
        android_version="15", sdk_version=35,
        build_id="AP3A.241005.015", security_patch="2024-10-05",
        screen_width=1344, screen_height=2992, density_dpi=560,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G715-Immortalis MC10",
        chipset="Google Tensor G4",
        supported_android_versions=(14, 15),
    ),
]

# Build lookup index by name/model
_DEVICE_INDEX: Dict[str, AndroidDevice] = {}
for _d in DEVICES:
    # Index by multiple keys for flexible lookup
    _DEVICE_INDEX[_d.name.lower()] = _d
    _DEVICE_INDEX[_d.model.lower()] = _d
    # Also index by short name like "pixel_8_pro", "samsung_s24_ultra"
    _short = _d.name.lower().replace(" ", "_").replace("(", "").replace(")", "")
    _DEVICE_INDEX[_short] = _d
    # Also short name without brand (e.g. "s24_ultra")
    _short2 = _short.split("_", 1)[-1] if "_" in _short else _short
    if _short2 not in _DEVICE_INDEX:
        _DEVICE_INDEX[_short2] = _d


def get_device(name: str) -> AndroidDevice:
    """Look up a device by name, model, or short key (slug).

    Examples:
        get_device("pixel_8_pro")        # matches "Google Pixel 8 Pro"
        get_device("SM-S928B")           # matches model directly
        get_device("s24_ultra")          # matches short key
    """
    key = name.lower().strip()
    if key in _DEVICE_INDEX:
        return _DEVICE_INDEX[key]
    
    # Try slugifying the input key to match index format
    key_slug = key.replace(" ", "_").replace("(", "").replace(")", "")
    if key_slug in _DEVICE_INDEX:
        return _DEVICE_INDEX[key_slug]

    # Fuzzy match fallback
    for k, d in _DEVICE_INDEX.items():
        if key in k or k in key:
            return d
    available = sorted(set(d.name for d in DEVICES))
    raise ValueError(f"Unknown device '{name}'. Available: {', '.join(available)}")


def get_random_device(
    android_version: Optional[str] = None,
    gpu_family: Optional[str] = None,
) -> AndroidDevice:
    """Return a random device, filtered by Android version and GPU family.

    Args:
        android_version: Filter to devices matching this Android version.
        gpu_family: Filter by GPU family ('adreno', 'mali', 'xclipse').
            On MuMu (Adreno emulator), pass 'adreno' to avoid GPU mismatch.
    """
    pool = DEVICES
    if android_version:
        filtered = [d for d in pool if d.android_version == android_version]
        if filtered:
            pool = filtered
    if gpu_family:
        filtered = [d for d in pool if d.gpu_family == gpu_family]
        if filtered:
            pool = filtered
        else:
            # If no matches with both filters, relax android_version
            pool = [d for d in DEVICES if d.gpu_family == gpu_family]
            if not pool:
                pool = DEVICES  # ultimate fallback
    return random.choice(pool)


def pick_screen_variant(device: AndroidDevice) -> Tuple[int, int, int]:
    """Pick a random screen resolution variant for a device.

    Many flagships have WQHD+ and FHD+ modes. Returns (width, height, dpi).
    Falls back to the device's default screen if no variants are defined.
    """
    variants = SCREEN_VARIANTS.get(device.name)
    if variants:
        return random.choice(variants)
    return (device.screen_width, device.screen_height, device.density_dpi)


def get_devices_by_brand(brand: str) -> List[AndroidDevice]:
    """Get all devices from a specific brand."""
    b = brand.lower()
    return [d for d in DEVICES if d.brand.lower() == b]


def pick_random_android_version(device: AndroidDevice) -> Tuple[int, int]:
    """Pick a random supported Android version for this device.

    Returns (android_version_int, sdk_version) tuple.
    Uses supported_android_versions field if available, otherwise falls
    back to the device's default android_version.

    Many real users don't update immediately, so this gives a realistic
    spread of OS versions for the same device model.
    """
    _VERSION_TO_SDK = {12: 31, 13: 33, 14: 34, 15: 35, 16: 36}

    if device.supported_android_versions:
        ver = random.choice(device.supported_android_versions)
    else:
        ver = int(device.android_version)

    sdk = _VERSION_TO_SDK.get(ver, device.sdk_version)
    return (ver, sdk)


# ---------------------------------------------------------------------------
# Chrome for Android version database — verified sub-versions.
# Sources: Chrome Releases Blog + APKMirror (Android x86/x86_64 APKs only).
# Desktop-only patch numbers excluded (Android often differs by 1). Keep this
# aligned with validated folders under chrome-apks/ so UA/client hints match
# the real installed Chrome binary when APK rotation is used.
# Each entry: (full_version_string, weight) — higher weight = more common.
# ---------------------------------------------------------------------------
CHROME_VERSIONS: List[Tuple[str, int]] = [
    # --- Chrome 149 (Build 7827) ---
    # APKMirror x86/x86_64 pages currently publish non-English 1-lang splits
    # only, so keep 149 out of auto UA rotation until an English-compatible
    # bundle is validated for Redroid.
    # --- Chrome 148 (Build 7778) ---
    ("148.0.7778.217", 24),
    ("148.0.7778.180", 14),
    ("148.0.7778.178", 8),
    ("148.0.7778.168", 6),
    ("148.0.7778.120", 4),
    # --- Chrome 147 (Build 7727) ---
    ("147.0.7727.138", 14),
    ("147.0.7727.101", 8),
    ("147.0.7727.49", 4),
    # --- Chrome 146 (Build 7680) ---
    ("146.0.7680.177", 12),
    ("146.0.7680.166", 8),
    ("146.0.7680.164", 6),
    ("146.0.7680.154", 5),
    ("146.0.7680.153", 5),
    ("146.0.7680.119", 4),
    ("146.0.7680.65", 2),
    ("146.0.7680.31", 1),
    # --- Chrome 145 (Build 7632) — CURRENT STABLE, Feb 2026 ---
    ("145.0.7632.75", 30),   # latest security patch (Feb 15)
    ("145.0.7632.46", 4),    # broad stable (Feb 13)
    ("145.0.7632.45", 8),    # full stable rollout (Feb 10)
    ("145.0.7632.26", 1),    # early stable (Jan 28)
    # --- Chrome 144 (Build 7559) — previous stable, Jan 2026 ---
    ("144.0.7559.132", 15),  # latest Android patch (Feb 3)
    ("144.0.7559.109", 6),   # security update (Jan 27)
    ("144.0.7559.59", 1),    # initial stable (Jan 13)
    # --- Chrome 143 (Build 7499) — 2 versions back, Nov-Dec 2025 ---
    ("143.0.7499.194", 4),   # APKMirror (Jan 16, 2026)
    ("143.0.7499.192", 8),   # blog-confirmed final (Jan 6)
    ("143.0.7499.146", 3),   # security update (Dec 16)
    ("143.0.7499.109", 1),   # security update (Dec 10)
    ("143.0.7499.34", 1),    # initial stable (Nov 20)
    # --- Chrome 142 (Build 7444) — 3 versions back, Oct-Nov 2025 ---
    ("142.0.7444.173", 5),   # latest Android (Dec 3)
    ("142.0.7444.171", 2),   # APKMirror (Nov 27)
    ("142.0.7444.158", 1),   # security update (Nov 11)
    ("142.0.7444.138", 1),   # security update (Nov 5)
    ("142.0.7444.48", 1),    # initial stable (Oct 30)
]


def _compute_grease_brand(major: int) -> Tuple[str, str]:
    """Compute the Chromium GREASE brand name and version for a major version.

    Mirrors Chromium's GetGreasedUserAgentBrandVersion() algorithm:
    - Two chars picked from a rotation set based on major version
    - Version is major % 96 (always < 100)

    Returns (brand_name, brand_version) tuple.
    """
    _GREASE_CHARS = [" ", "(", ":", "-", ".", "/", ")", ";"]
    c1 = _GREASE_CHARS[major % 8]
    c2 = _GREASE_CHARS[(major + 1) % 8]
    return (f"Not{c1}A{c2}Brand", str(major % 96))


def _compute_brand_order(major: int) -> List[int]:
    """Compute the permuted brand order for sec-ch-ua.

    Mirrors Chromium's brand permutation: major % 6 selects one of 6
    orderings of (Chromium=0, Google Chrome=1, Grease=2).
    """
    _ORDERS = [
        [0, 1, 2], [0, 2, 1], [1, 0, 2],
        [1, 2, 0], [2, 0, 1], [2, 1, 0],
    ]
    return _ORDERS[major % 6]


def pick_random_chrome_version(force_version: Optional[str] = None) -> Tuple[str, dict]:
    """Pick a Chrome version and compute brand/grease info.

    Args:
        force_version: If provided, use this exact version instead of
            random selection. Use the real installed Chrome version to
            ensure Workers (which see the real version) match the main
            page's CDP-overridden version.

    Returns (full_version, brand_info) where brand_info contains:
      - brands: list of {brand, version} for sec-ch-ua (low-entropy)
      - fullVersionList: list of {brand, version} for high-entropy CH
      - grease_brand: the "Not X Brand" string for this version
    """
    if force_version:
        chrome_ver = force_version
    else:
        versions, weights = zip(*CHROME_VERSIONS)
        chrome_ver = random.choices(versions, weights=weights, k=1)[0]
    major = int(chrome_ver.split(".")[0])

    grease_name, grease_ver = _compute_grease_brand(major)
    order = _compute_brand_order(major)

    # Build brands in correct permuted order
    raw_brands = [
        {"brand": "Chromium", "version": str(major)},
        {"brand": "Google Chrome", "version": str(major)},
        {"brand": grease_name, "version": grease_ver},
    ]
    raw_full = [
        {"brand": "Chromium", "version": chrome_ver},
        {"brand": "Google Chrome", "version": chrome_ver},
        {"brand": grease_name, "version": f"{grease_ver}.0.0.0"},
    ]

    brands = [raw_brands[i] for i in order]
    full_version_list = [raw_full[i] for i in order]

    return chrome_ver, {
        "brands": brands,
        "fullVersionList": full_version_list,
    }


def list_device_names() -> List[str]:
    """List all device names."""
    return [d.name for d in DEVICES]
