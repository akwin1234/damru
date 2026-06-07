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
        """GPU family: 'adreno', 'mali', 'xclipse', 'powervr', or 'unknown'.

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
        if "imagination" in v or "powervr" in r:
            return "powervr"
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
    # ---- Motorola Moto G (5S) Plus (Snapdragon 625 → Adreno 506) ----
    AndroidDevice(
        name="Motorola Moto G (5S) Plus",
        brand="motorola", manufacturer="motorola",
        model="Moto G (5S) Plus", device="sanders", product="sanders_retail",
        build_fingerprint="motorola/sanders_retail/sanders:8.1.0/OPS28.65-36-14/63857:user/release-keys",
        android_version="8.1.0", sdk_version=27,
        build_id="OPS28.65-36-14", security_patch="2020-01-05",
        screen_width=1080, screen_height=1920, density_dpi=480,
        hardware_concurrency=8, device_memory=2, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 506",
        chipset="Snapdragon 625",
        supported_android_versions=(8,),
    ),
    # ---- Xiaomi Redmi 9A (MediaTek Helio G25 → PowerVR GE8320) ----
    AndroidDevice(
        name="Xiaomi Redmi 9A",
        brand="Redmi", manufacturer="Xiaomi",
        model="M2006C3LG", device="dandelion", product="dandelion_global",
        build_fingerprint="Redmi/dandelion_global/dandelion:11/RP1A.200720.011/V12.5.6.0.RCDMIXM:user/release-keys",
        android_version="11", sdk_version=30,
        build_id="RP1A.200720.011", security_patch="2022-07-01",
        screen_width=720, screen_height=1600, density_dpi=320,
        hardware_concurrency=8, device_memory=2, max_touch_points=5,
        webgl_vendor="Imagination Technologies", webgl_renderer="PowerVR Rogue GE8320",
        chipset="MediaTek Helio G25",
        supported_android_versions=(10, 11),
    ),
    # ---------------------------------------------------------------------
    # Additional regional profiles imported from r.txt research dataset.
    # Confidence in the source file is advisory; live benchmark decides use.
    # ---------------------------------------------------------------------
    # ---- Xiaomi 11T Pro (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi 11T Pro",
        brand="xiaomi", manufacturer="Xiaomi",
        model="2107113SG", device="vili", product="vili_global",
        build_fingerprint="Xiaomi/vili_global/vili:13/TKQ1.220829.002/V14.0.3.0.TKDMIXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TKQ1.220829.002", security_patch="2023-08-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 660",
        chipset="Snapdragon 888",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- Xiaomi 12T Pro (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi 12T Pro",
        brand="xiaomi", manufacturer="Xiaomi",
        model="22081212UG", device="diting", product="diting_global",
        build_fingerprint="Xiaomi/diting_global/diting:13/TKQ1.220829.002/V14.0.1.0.TLFMIXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TKQ1.220829.002", security_patch="2023-01-01",
        screen_width=1220, screen_height=2712, density_dpi=446,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Snapdragon 8+ Gen 1",
        supported_android_versions=(12, 13),
    ),
    # ---- Xiaomi POCO F5 (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi POCO F5",
        brand="poco", manufacturer="Xiaomi",
        model="23049PCD8G", device="marble", product="marble_global",
        build_fingerprint="POCO/marble_global/marble:13/TKQ1.221114.001/V14.0.4.0.TMRMIXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TKQ1.221114.001", security_patch="2023-06-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 725",
        chipset="Snapdragon 7+ Gen 2",
        supported_android_versions=(13,),
    ),
    # ---- Xiaomi POCO X5 Pro 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi POCO X5 Pro 5G",
        brand="poco", manufacturer="Xiaomi",
        model="22101320G", device="redwood", product="redwood_global",
        build_fingerprint="POCO/redwood_global/redwood:13/TKQ1.221114.001/V14.0.2.0.TMSMIXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TKQ1.221114.001", security_patch="2023-08-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 642L",
        chipset="Snapdragon 778G 5G",
        supported_android_versions=(12, 13),
    ),
    # ---- Xiaomi Redmi Note 11 (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi Redmi Note 11",
        brand="redmi", manufacturer="Xiaomi",
        model="2201117TG", device="spes", product="spes_global",
        build_fingerprint="Redmi/spes_global/spes:13/TKQ1.221114.001/V14.0.2.0.TGCMIXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TKQ1.221114.001", security_patch="2023-05-01",
        screen_width=1080, screen_height=2400, density_dpi=409,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 610",
        chipset="Snapdragon 680 4G",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- Xiaomi Redmi Note 11 Pro 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi Redmi Note 11 Pro 5G",
        brand="redmi", manufacturer="Xiaomi",
        model="2201116SG", device="veux", product="veux_global",
        build_fingerprint="Redmi/veux_global/veux:13/TKQ1.221114.001/V14.0.2.0.TKCMIXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TKQ1.221114.001", security_patch="2023-07-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 619",
        chipset="Snapdragon 695 5G",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- Samsung Galaxy A73 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A73 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-A736B", device="a73xq", product="a73xqxx",
        build_fingerprint="samsung/a73xqxx/a73xq:14/UP1A.231005.007/A736BXXU7DXA1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-01-01",
        screen_width=1080, screen_height=2400, density_dpi=393,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 642L",
        chipset="Snapdragon 778G",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Samsung Galaxy Z Flip 4 (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy Z Flip 4",
        brand="samsung", manufacturer="samsung",
        model="SM-F721B", device="b4q", product="b4qxxx",
        build_fingerprint="samsung/b4qxxx/b4q:14/UP1A.231005.007/F721BXXU4DWD1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-04-01",
        screen_width=1080, screen_height=2640, density_dpi=426,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Snapdragon 8+ Gen 1",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Samsung Galaxy Z Fold 4 (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy Z Fold 4",
        brand="samsung", manufacturer="samsung",
        model="SM-F936B", device="q4q", product="q4qxxx",
        build_fingerprint="samsung/q4qxxx/q4q:14/UP1A.231005.007/F936BXXU4DWD1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-04-01",
        screen_width=1812, screen_height=2176, density_dpi=373,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Snapdragon 8+ Gen 1",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Xiaomi POCO C65 (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi POCO C65",
        brand="xiaomi", manufacturer="Xiaomi",
        model="2310FPCA4G", device="water", product="water",
        build_fingerprint="POCO/water/water:14/TP1A.220624.014/V816.0.2.0.TGEINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.014", security_patch="2024-01-01",
        screen_width=720, screen_height=1650, density_dpi=268,
        hardware_concurrency=8, device_memory=4, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G52 MC2",
        chipset="MediaTek Helio G85",
        supported_android_versions=(13, 14),
    ),
    # ---- Xiaomi Redmi 12 4G (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi Redmi 12 4G",
        brand="xiaomi", manufacturer="Xiaomi",
        model="23053RN02I", device="heat", product="heat",
        build_fingerprint="xiaomi/heat/heat:14/UKQ1.230917.001/V816.0.1.0.UMXINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.230917.001", security_patch="2024-01-01",
        screen_width=720, screen_height=1650, density_dpi=268,
        hardware_concurrency=8, device_memory=4, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G52 MC2",
        chipset="MediaTek Helio G88",
        supported_android_versions=(13, 14),
    ),
    # ---- Xiaomi Redmi Note 13 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi Redmi Note 13 5G",
        brand="xiaomi", manufacturer="Xiaomi",
        model="2312DRAABG", device="gold", product="gold",
        build_fingerprint="xiaomi/gold/gold:14/UKQ1.231003.002/V816.0.5.0.UNQINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-04-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=6, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Dimensity 6080",
        supported_android_versions=(13, 14),
    ),
    # ---- Samsung Galaxy A52s 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A52s 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-A528B", device="a52sxq", product="a52sxqxx",
        build_fingerprint="samsung/a52sxqxx/a52sxq:13/TP1A.220624.014/A528BXXU2DWD1:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220624.014", security_patch="2023-04-01",
        screen_width=1080, screen_height=2400, density_dpi=405,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 642L",
        chipset="Snapdragon 778G",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- Xiaomi 12T (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi 12T",
        brand="xiaomi", manufacturer="Xiaomi",
        model="22071212AG", device="plato", product="plato_global",
        build_fingerprint="Xiaomi/plato_global/plato:13/TP1A.220624.014/V14.0.4.0.TLQMIXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220624.014", security_patch="2023-10-01",
        screen_width=1220, screen_height=2712, density_dpi=446,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC6",
        chipset="MediaTek Dimensity 8100-Ultra",
        supported_android_versions=(12, 13),
    ),
    # ---- Xiaomi POCO M5 (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi POCO M5",
        brand="poco", manufacturer="Xiaomi",
        model="22071219CG", device="rock", product="rock_global",
        build_fingerprint="POCO/rock_global/rock:13/TP1A.220624.014/V14.0.3.0.TLUMIXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220624.014", security_patch="2023-09-01",
        screen_width=1080, screen_height=2408, density_dpi=401,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Helio G99",
        supported_android_versions=(12, 13),
    ),
    # ---- Xiaomi POCO M6 Pro 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi POCO M6 Pro 5G",
        brand="xiaomi", manufacturer="Xiaomi",
        model="23076PC4BI", device="sky", product="sky",
        build_fingerprint="POCO/sky/sky:14/UKQ1.230917.001/V816.0.1.0.UMUINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.230917.001", security_patch="2024-01-01",
        screen_width=1080, screen_height=2460, density_dpi=396,
        hardware_concurrency=8, device_memory=4, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 613",
        chipset="Qualcomm Snapdragon 4 Gen 2",
        supported_android_versions=(13, 14),
    ),
    # ---- Xiaomi POCO X6 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi POCO X6 5G",
        brand="xiaomi", manufacturer="Xiaomi",
        model="23122PCD1I", device="garnet", product="garnet",
        build_fingerprint="POCO/garnet/garnet:14/UKQ1.230917.001/V816.0.1.0.UNRINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.230917.001", security_patch="2024-01-01",
        screen_width=1220, screen_height=2712, density_dpi=450,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 710",
        chipset="Qualcomm Snapdragon 7s Gen 2",
        supported_android_versions=(13, 14),
    ),
    # ---- Xiaomi Redmi Note 12 Pro 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Xiaomi Redmi Note 12 Pro 5G",
        brand="redmi", manufacturer="Xiaomi",
        model="22101316C", device="ruby", product="ruby_global",
        build_fingerprint="Redmi/ruby_global/ruby:13/TP1A.220624.014/V14.0.6.0.SMOMIXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220624.014", security_patch="2023-11-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MC4",
        chipset="MediaTek Dimensity 1080",
        supported_android_versions=(12, 13),
    ),
    # ---- Samsung Galaxy A14 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A14 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-A146B", device="a14x", product="a14xnsxx",
        build_fingerprint="samsung/a14xnsxx/a14x:14/UP1A.231005.007/A146BXXU3DXC1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-03-01",
        screen_width=1080, screen_height=2408, density_dpi=400,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MC4",
        chipset="Exynos 1330",
        supported_android_versions=(13, 14),
    ),
    # ---- Samsung Galaxy A24 (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A24",
        brand="samsung", manufacturer="samsung",
        model="SM-A245F", device="a24", product="a24nsxx",
        build_fingerprint="samsung/a24nsxx/a24:14/UP1A.231005.007/A245FXXU3DXC1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-03-01",
        screen_width=1080, screen_height=2340, density_dpi=396,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Helio G99",
        supported_android_versions=(13, 14),
    ),
    # ---- Samsung Galaxy A25 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A25 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-A256B", device="a25x", product="a25xnsxx",
        build_fingerprint="samsung/a25xnsxx/a25x:14/UP1A.231005.007/A256BXXU1AXA1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-01-01",
        screen_width=1080, screen_height=2340, density_dpi=396,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68",
        chipset="Samsung Exynos 1280",
        supported_android_versions=(14,),
    ),
    # ---- Samsung Galaxy M14 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy M14 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-M146B", device="m14x", product="m14xnsxx",
        build_fingerprint="samsung/m14xnsxx/m14x:14/UP1A.231005.007/M146BXXU4CXD1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-04-01",
        screen_width=1080, screen_height=2408, density_dpi=400,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MP2",
        chipset="Samsung Exynos 1330",
        supported_android_versions=(13, 14),
    ),
    # ---- Samsung Galaxy M34 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy M34 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-M346B", device="m34x", product="m34xnsxx",
        build_fingerprint="samsung/m34xnsxx/m34x:14/UP1A.231005.007/M346BXXU3DXC1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-03-01",
        screen_width=1080, screen_height=2340, density_dpi=396,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68",
        chipset="Exynos 1280",
        supported_android_versions=(13, 14),
    ),
    # ---- Samsung Galaxy M54 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy M54 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-M546B", device="m54x", product="m54xnsxx",
        build_fingerprint="samsung/m54xnsxx/m54x:14/UP1A.231005.007/M546BXXU4CXC1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-03-01",
        screen_width=1080, screen_height=2400, density_dpi=399,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MP5",
        chipset="Exynos 1380",
        supported_android_versions=(13, 14),
    ),
    # ---- Asus Zenfone 10 (HIGH source confidence) ----
    AndroidDevice(
        name="Asus Zenfone 10",
        brand="asus", manufacturer="asus",
        model="ASUS_AI2302", device="AI2302", product="WW_AI2302",
        build_fingerprint="asus/WW_AI2302/AI2302:14/UP1A.231005.007/34.1004.0204.65:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-01-05",
        screen_width=1080, screen_height=2400, density_dpi=445,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Snapdragon 8 Gen 2",
        supported_android_versions=(13, 14),
    ),
    # ---- Google Pixel 5a 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Google Pixel 5a 5G",
        brand="google", manufacturer="google",
        model="Pixel 5a", device="barbet", product="barbet",
        build_fingerprint="google/barbet/barbet:14/AP1A.240505.004/11583682:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="AP1A.240505.004", security_patch="2024-05-05",
        screen_width=1080, screen_height=2400, density_dpi=420,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 620",
        chipset="Qualcomm Snapdragon 765G",
        supported_android_versions=(11, 12, 13, 14),
    ),
    # ---- Sony Xperia 1 V (HIGH source confidence) ----
    AndroidDevice(
        name="Sony Xperia 1 V",
        brand="sony", manufacturer="Sony",
        model="XQ-DQ54", device="XQ-DQ54", product="XQ-DQ54_EEA",
        build_fingerprint="Sony/XQ-DQ54_EEA/XQ-DQ54:14/67.1.A.2.193/067001A002019300000:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="67.1.A.2.193", security_patch="2024-02-01",
        screen_width=1644, screen_height=3840, density_dpi=643,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Snapdragon 8 Gen 2",
        supported_android_versions=(13, 14),
    ),
    # ---- Motorola Edge 30 Fusion (HIGH source confidence) ----
    AndroidDevice(
        name="Motorola Edge 30 Fusion",
        brand="motorola", manufacturer="motorola",
        model="XT2243-1", device="tundra", product="tundra_g",
        build_fingerprint="motorola/tundra_g/tundra:13/T1SJ33.117-30-3/c0ebf:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="T1SJ33.117-30-3", security_patch="2023-10-01",
        screen_width=1080, screen_height=2400, density_dpi=402,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 660",
        chipset="Snapdragon 888+",
        supported_android_versions=(12, 13),
    ),
    # ---- Motorola Moto G84 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Motorola Moto G84 5G",
        brand="motorola", manufacturer="motorola",
        model="XT2347-2", device="cancun", product="cancun_g",
        build_fingerprint="motorola/cancun_g/cancun:13/T1TC33.18-42-4/30dfa:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="T1TC33.18-42-4", security_patch="2023-12-01",
        screen_width=1080, screen_height=2400, density_dpi=405,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 619",
        chipset="Snapdragon 695 5G",
        supported_android_versions=(13,),
    ),
    # ---- OnePlus 8T (HIGH source confidence) ----
    AndroidDevice(
        name="OnePlus 8T",
        brand="oneplus", manufacturer="OnePlus",
        model="KB2005", device="kebab", product="OnePlus8T",
        build_fingerprint="OnePlus/OnePlus8T/kebab:13/TP1A.220905.001/S.202302221200:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-02-05",
        screen_width=1080, screen_height=2400, density_dpi=402,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 650",
        chipset="Snapdragon 865 5G",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- OnePlus 9 (HIGH source confidence) ----
    AndroidDevice(
        name="OnePlus 9",
        brand="oneplus", manufacturer="OnePlus",
        model="LE2115", device="lemonade", product="OnePlus9",
        build_fingerprint="OnePlus/OnePlus9/lemonade:13/TP1A.220905.001/S.202301131558:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-01-05",
        screen_width=1080, screen_height=2400, density_dpi=402,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 660",
        chipset="Snapdragon 888 5G",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- OnePlus 9 Pro (HIGH source confidence) ----
    AndroidDevice(
        name="OnePlus 9 Pro",
        brand="oneplus", manufacturer="OnePlus",
        model="LE2123", device="lemonadep", product="OnePlus9Pro_EEA",
        build_fingerprint="OnePlus/OnePlus9Pro_EEA/lemonadep:13/TP1A.220905.001/S.202302151608:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-02-05",
        screen_width=1440, screen_height=3216, density_dpi=525,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 660",
        chipset="Snapdragon 888 5G",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- OnePlus Nord CE 3 Lite (HIGH source confidence) ----
    AndroidDevice(
        name="OnePlus Nord CE 3 Lite",
        brand="oneplus", manufacturer="OnePlus",
        model="CPH2467", device="CPH2467", product="CPH2467",
        build_fingerprint="OnePlus/CPH2467/CPH2467:13/TP1A.220905.001/S.202306201524:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-06-05",
        screen_width=1080, screen_height=2400, density_dpi=391,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 619",
        chipset="Snapdragon 695 5G",
        supported_android_versions=(13,),
    ),
    # ---- Google Pixel Fold (HIGH source confidence) ----
    AndroidDevice(
        name="Google Pixel Fold",
        brand="google", manufacturer="Google",
        model="Pixel Fold", device="felix", product="felix",
        build_fingerprint="google/felix/felix:14/UP1A.231005.007/10750268:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2023-10-05",
        screen_width=1840, screen_height=2208, density_dpi=380,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G710 MC10",
        chipset="Google Tensor G2",
        supported_android_versions=(13, 14),
    ),
    # ---- Motorola Moto G54 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Motorola Moto G54 5G",
        brand="motorola", manufacturer="motorola",
        model="XT2303-2", device="cancun", product="cancun_g",
        build_fingerprint="motorola/cancun_g/cancun:14/U1TRS34.8-30-5-2/cdfbba:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="U1TRS34.8-30-5-2", security_patch="2024-03-01",
        screen_width=1080, screen_height=2400, density_dpi=405,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Imagination Technologies", webgl_renderer="PowerVR BXM-8-256",
        chipset="MediaTek Dimensity 7020",
        supported_android_versions=(13, 14),
    ),
    # ---- iQOO Neo 7 5G (HIGH source confidence) ----
    AndroidDevice(
        name="iQOO Neo 7 5G",
        brand="iqoo", manufacturer="vivo",
        model="I2214", device="v2237", product="v2237",
        build_fingerprint="vivo/v2237/v2237:14/TP1A.220624.032/compiler04101551:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.032", security_patch="2024-04-01",
        screen_width=1080, screen_height=2400, density_dpi=388,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC6",
        chipset="MediaTek Dimensity 8200",
        supported_android_versions=(13, 14),
    ),
    # ---- iQOO Z9 5G (HIGH source confidence) ----
    AndroidDevice(
        name="iQOO Z9 5G",
        brand="iqoo", manufacturer="vivo",
        model="I2302", device="PD2319", product="PD2319",
        build_fingerprint="vivo/PD2319/PD2319:14/UP1A.231005.007/compiler04101553:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-06-01",
        screen_width=1260, screen_height=2800, density_dpi=452,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC4",
        chipset="MediaTek Dimensity 7200",
        supported_android_versions=(14,),
    ),
    # ---- Motorola Edge 40 Neo (HIGH source confidence) ----
    AndroidDevice(
        name="Motorola Edge 40 Neo",
        brand="motorola", manufacturer="motorola",
        model="XT2307-1", device="cancun", product="cancun_g_vext",
        build_fingerprint="motorola/cancun_g_vext/cancun:13/T1TD33.50-20/4b82a:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="T1TD33.50-20", security_patch="2024-01-01",
        screen_width=1080, screen_height=2400, density_dpi=402,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC3",
        chipset="MediaTek Dimensity 7030",
        supported_android_versions=(13,),
    ),
    # ---- Nokia G60 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Nokia G60 5G",
        brand="nokia", manufacturer="HMD Global",
        model="TA-1478", device="SNT", product="SNT_00EEA",
        build_fingerprint="Nokia/SNT_00EEA/SNT:14/UKQ1.231018.001/00WW_3_38E:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231018.001", security_patch="2024-04-01",
        screen_width=1080, screen_height=2408, density_dpi=400,
        hardware_concurrency=8, device_memory=4, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 619",
        chipset="Qualcomm Snapdragon 695",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Nokia X30 5G (HIGH source confidence) ----
    AndroidDevice(
        name="Nokia X30 5G",
        brand="nokia", manufacturer="HMD Global",
        model="TA-1450", device="SCW", product="SCW_00EEA",
        build_fingerprint="Nokia/SCW_00EEA/SCW:14/UKQ1.231018.001/00WW_3_39E:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231018.001", security_patch="2024-04-01",
        screen_width=1080, screen_height=2400, density_dpi=409,
        hardware_concurrency=8, device_memory=6, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 619",
        chipset="Qualcomm Snapdragon 695",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- OnePlus Nord 2 5G (HIGH source confidence) ----
    AndroidDevice(
        name="OnePlus Nord 2 5G",
        brand="oneplus", manufacturer="OnePlus",
        model="DN2103", device="denniz", product="OnePlusNord2_EEA",
        build_fingerprint="OnePlus/OnePlusNord2_EEA/denniz:13/TP1A.220905.001/S.202306141200:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-06-05",
        screen_width=1080, screen_height=2400, density_dpi=409,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G77 MC9",
        chipset="MediaTek Dimensity 1200",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- OnePlus Nord CE 2 5G (HIGH source confidence) ----
    AndroidDevice(
        name="OnePlus Nord CE 2 5G",
        brand="oneplus", manufacturer="OnePlus",
        model="CPH2409", device="luna", product="luna",
        build_fingerprint="OnePlus/luna/luna:13/TP1A.220905.001/R.1678245835:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-10-01",
        screen_width=1080, screen_height=2400, density_dpi=409,
        hardware_concurrency=8, device_memory=6, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MC4",
        chipset="MediaTek Dimensity 900",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- Sony Xperia 10 V (HIGH source confidence) ----
    AndroidDevice(
        name="Sony Xperia 10 V",
        brand="sony", manufacturer="Sony",
        model="XQ-DC54", device="pdx234", product="pdx234",
        build_fingerprint="Sony/pdx234/pdx234:14/67.1.A.2.112/067001A002011200519602518:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="67.1.A.2.112", security_patch="2024-06-01",
        screen_width=1080, screen_height=2520, density_dpi=449,
        hardware_concurrency=8, device_memory=6, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 619",
        chipset="Qualcomm Snapdragon 695",
        supported_android_versions=(13, 14),
    ),
    # ---- Vivo V29 (HIGH source confidence) ----
    AndroidDevice(
        name="Vivo V29",
        brand="vivo", manufacturer="vivo",
        model="V2250", device="V2250", product="V2250",
        build_fingerprint="vivo/V2250/V2250:14/TP1A.220624.032/compiler04101554:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.032", security_patch="2024-04-01",
        screen_width=1260, screen_height=2800, density_dpi=452,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 642L",
        chipset="Qualcomm Snapdragon 778G",
        supported_android_versions=(13, 14),
    ),
    # ---- ZTE Nubia RedMagic 8 Pro (HIGH source confidence) ----
    AndroidDevice(
        name="ZTE Nubia RedMagic 8 Pro",
        brand="nubia", manufacturer="ZTE",
        model="NX729J", device="NX729J", product="NX729J",
        build_fingerprint="nubia/NX729J/NX729J:14/UKQ1.231003.002/20240215:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-02-01",
        screen_width=1116, screen_height=2480, density_dpi=400,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Qualcomm Snapdragon 8 Gen 2",
        supported_android_versions=(13, 14),
    ),
    # ---- ZTE Nubia RedMagic 9 Pro (HIGH source confidence) ----
    AndroidDevice(
        name="ZTE Nubia RedMagic 9 Pro",
        brand="nubia", manufacturer="ZTE",
        model="NX769J", device="NX769J", product="NX769J",
        build_fingerprint="nubia/NX769J/NX769J:14/UKQ1.231003.002/20240115:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-01-01",
        screen_width=1116, screen_height=2480, density_dpi=400,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Qualcomm Snapdragon 8 Gen 3",
        supported_android_versions=(14,),
    ),
    # ---- iQOO Neo 8 (HIGH source confidence) ----
    AndroidDevice(
        name="iQOO Neo 8",
        brand="iqoo", manufacturer="vivo",
        model="I2302", device="PD2302", product="PD2302",
        build_fingerprint="vivo/PD2302/PD2302:14/TP1A.220624.032/compiler04101552:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.032", security_patch="2024-05-01",
        screen_width=1260, screen_height=2800, density_dpi=452,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Qualcomm Snapdragon 8+ Gen 1",
        supported_android_versions=(13, 14),
    ),
    # ---- OnePlus 9R (HIGH source confidence) ----
    AndroidDevice(
        name="OnePlus 9R",
        brand="oneplus", manufacturer="OnePlus",
        model="LE2101", device="lemonades", product="lemonades",
        build_fingerprint="OnePlus/lemonades/lemonades:13/TP1A.220905.001/R.1678245835:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-08-01",
        screen_width=1080, screen_height=2400, density_dpi=402,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 650",
        chipset="Qualcomm Snapdragon 870",
        supported_android_versions=(11, 12, 13),
    ),
    # ---- Sony Xperia 5 V (HIGH source confidence) ----
    AndroidDevice(
        name="Sony Xperia 5 V",
        brand="sony", manufacturer="Sony",
        model="XQ-DE54", device="pdx237", product="pdx237",
        build_fingerprint="Sony/pdx237/pdx237:15/67.2.A.0.191/067002A000019100519602518:user/release-keys",
        android_version="15", sdk_version=35,
        build_id="67.2.A.0.191", security_patch="2025-01-01",
        screen_width=1080, screen_height=2520, density_dpi=449,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Qualcomm Snapdragon 8 Gen 2",
        supported_android_versions=(13, 14, 15),
    ),
    # ---- Xiaomi POCO X6 Pro 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Xiaomi POCO X6 Pro 5G",
        brand="xiaomi", manufacturer="Xiaomi",
        model="2311DRK48I", device="duchamp", product="duchamp",
        build_fingerprint="POCO/duchamp/duchamp:14/UP1A.231005.007/V816.0.1.0.UNLINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-02-01",
        screen_width=1220, screen_height=2712, density_dpi=446,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G615 MC6",
        chipset="MediaTek Dimensity 8300-Ultra",
        supported_android_versions=(14,),
    ),
    # ---- Xiaomi Redmi 13 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Xiaomi Redmi 13 5G",
        brand="xiaomi", manufacturer="Xiaomi",
        model="2406ERN9CI", device="breeze", product="breeze",
        build_fingerprint="xiaomi/breeze/breeze:14/UP1A.231005.007/V816.0.2.0.UMBINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-07-01",
        screen_width=1080, screen_height=2460, density_dpi=396,
        hardware_concurrency=8, device_memory=6, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Dimensity 6080",
        supported_android_versions=(14,),
    ),
    # ---- Xiaomi Redmi 13C 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Xiaomi Redmi 13C 5G",
        brand="xiaomi", manufacturer="Xiaomi",
        model="23124RN87I", device="air", product="air",
        build_fingerprint="xiaomi/air/air:14/UP1A.231005.007/V816.0.1.0.UMXINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-02-01",
        screen_width=720, screen_height=1650, density_dpi=268,
        hardware_concurrency=8, device_memory=4, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Dimensity 6100+",
        supported_android_versions=(13, 14),
    ),
    # ---- Xiaomi Redmi Note 14 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Xiaomi Redmi Note 14 5G",
        brand="xiaomi", manufacturer="Xiaomi",
        model="24090RA29C", device="beryl", product="beryl",
        build_fingerprint="xiaomi/beryl/beryl:14/UP1A.240105.007/V816.0.3.0.UNQINXM:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.240105.007", security_patch="2024-10-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=6, max_touch_points=10,
        webgl_vendor="Imagination Technologies", webgl_renderer="PowerVR BXM-8-256",
        chipset="MediaTek Dimensity 7025 Ultra",
        supported_android_versions=(14,),
    ),
    # ---- Samsung Galaxy A05 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A05",
        brand="samsung", manufacturer="samsung",
        model="SM-A055F", device="a05", product="a05nsxx",
        build_fingerprint="samsung/a05nsxx/a05:14/UP1A.231005.007/A055FXXU2BXA1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-01-01",
        screen_width=720, screen_height=1600, density_dpi=262,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G52 MC2",
        chipset="MediaTek Helio G85",
        supported_android_versions=(13, 14),
    ),
    # ---- Samsung Galaxy A15 4G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A15 4G",
        brand="samsung", manufacturer="samsung",
        model="SM-A155F", device="a15", product="a15nsxx",
        build_fingerprint="samsung/a15nsxx/a15:14/UP1A.231005.007/A155FXXU1AXA1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-03-01",
        screen_width=1080, screen_height=2340, density_dpi=396,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Helio G99",
        supported_android_versions=(14,),
    ),
    # ---- Samsung Galaxy A24 4G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A24 4G",
        brand="samsung", manufacturer="samsung",
        model="SM-A245F", device="a24", product="a24nsxx",
        build_fingerprint="samsung/a24nsxx/a24:14/UP1A.231005.007/A245FXXU5CXE1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-03-01",
        screen_width=1080, screen_height=2340, density_dpi=420,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Helio G99",
        supported_android_versions=(13, 14),
    ),
    # ---- Samsung Galaxy F14 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy F14 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-E146B", device="f14x", product="f14xnsxx",
        build_fingerprint="samsung/f14xnsxx/f14x:14/UP1A.231005.007/E146BXXU4CXD1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-04-01",
        screen_width=1080, screen_height=2408, density_dpi=400,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MP2",
        chipset="Samsung Exynos 1330",
        supported_android_versions=(13, 14),
    ),
    # ---- Samsung Galaxy A05s (MEDIUM source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A05s",
        brand="samsung", manufacturer="samsung",
        model="SM-A057F", device="a05s", product="a05snsxx",
        build_fingerprint="samsung/a05snsxx/a05s:14/UP1A.231005.007/A057FXXU1BXA1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-02-01",
        screen_width=1080, screen_height=2400, density_dpi=400,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 610",
        chipset="Qualcomm Snapdragon 680",
        supported_android_versions=(13, 14),
    ),
    # ---- Samsung Galaxy A23 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A23",
        brand="samsung", manufacturer="samsung",
        model="SM-A235F", device="a23", product="a23nsxx",
        build_fingerprint="samsung/a23nsxx/a23:14/UP1A.231005.007/A235FXXU6DXA1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-01-01",
        screen_width=1080, screen_height=2408, density_dpi=400,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 610",
        chipset="Qualcomm Snapdragon 680",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Honor 90 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Honor 90",
        brand="honor", manufacturer="HONOR",
        model="REA-NX9", device="REA-NX9", product="REA-NX9",
        build_fingerprint="HONOR/REA-NX9/REA-NX9:13/HONORREA-NX9/7.1.0.150C431:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="HONORREA-NX9", security_patch="2023-09-01",
        screen_width=1200, screen_height=2664, density_dpi=435,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 644",
        chipset="Snapdragon 7 Gen 1 Accelerated Edition",
        supported_android_versions=(13,),
    ),
    # ---- Honor Magic5 Pro (MEDIUM source confidence) ----
    AndroidDevice(
        name="Honor Magic5 Pro",
        brand="honor", manufacturer="HONOR",
        model="PGT-N19", device="PGT-N19", product="PGT-N19",
        build_fingerprint="HONOR/PGT-N19/PGT-N19:13/HONORPGT-N19/7.1.0.194C431:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="HONORPGT-N19", security_patch="2023-11-01",
        screen_width=1312, screen_height=2848, density_dpi=460,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Snapdragon 8 Gen 2",
        supported_android_versions=(13,),
    ),
    # ---- Motorola Moto G64 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Motorola Moto G64 5G",
        brand="motorola", manufacturer="motorola",
        model="XT2431-1", device="cancunp", product="cancunp_g",
        build_fingerprint="motorola/cancunp_g/cancunp:14/U1TD34.8-30-5-2/cdfbbap:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="U1TD34.8-30-5-2", security_patch="2024-05-01",
        screen_width=1080, screen_height=2400, density_dpi=405,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Dimensity 7025",
        supported_android_versions=(14,),
    ),
    # ---- OnePlus 10R 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="OnePlus 10R 5G",
        brand="oneplus", manufacturer="OnePlus",
        model="PGKM10", device="pickle", product="pickle",
        build_fingerprint="OnePlus/pickle/pickle:14/UKQ1.230924.001/R.1706245835:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.230924.001", security_patch="2024-02-01",
        screen_width=1080, screen_height=2412, density_dpi=394,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC6",
        chipset="MediaTek Dimensity 8100 Max",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Realme 11 Pro+ (MEDIUM source confidence) ----
    AndroidDevice(
        name="Realme 11 Pro+",
        brand="realme", manufacturer="Realme",
        model="RMX3741", device="RMX3741", product="RMX3741",
        build_fingerprint="realme/RMX3741/RMX3741:14/UP1A.231005.007/R.2403151230:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-03-05",
        screen_width=1080, screen_height=2412, density_dpi=394,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MC4",
        chipset="MediaTek Dimensity 7050",
        supported_android_versions=(13, 14),
    ),
    # ---- Asus ROG Phone 7 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Asus ROG Phone 7",
        brand="asus", manufacturer="Asus",
        model="AI2205", device="ZE554KL", product="WW_AI2205",
        build_fingerprint="asus/WW_AI2205/ZE554KL:14/UKQ1.240128.001/33.0300.0000:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.240128.001", security_patch="2024-03-01",
        screen_width=1080, screen_height=2448, density_dpi=395,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 740",
        chipset="Qualcomm Snapdragon 8 Gen 2",
        supported_android_versions=(13, 14),
    ),
    # ---- Asus ROG Phone 8 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Asus ROG Phone 8",
        brand="asus", manufacturer="Asus",
        model="AI2401", device="ZE554KL", product="WW_AI2401",
        build_fingerprint="asus/WW_AI2401/ZE554KL:14/UKQ1.240128.001/34.0300.0000:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.240128.001", security_patch="2024-02-01",
        screen_width=1080, screen_height=2400, density_dpi=388,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Qualcomm Snapdragon 8 Gen 3",
        supported_android_versions=(14,),
    ),
    # ---- Honor 200 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Honor 200",
        brand="honor", manufacturer="Honor",
        model="ELI-AN00", device="HNAELI", product="HNAELI",
        build_fingerprint="HONOR/HNAELI/HNAELI:14/HONORELI-AN00/8.0.0.120:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="HONORELI-AN00", security_patch="2024-06-01",
        screen_width=1200, screen_height=2664, density_dpi=435,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 720",
        chipset="Qualcomm Snapdragon 7 Gen 3",
        supported_android_versions=(14,),
    ),
    # ---- Honor Magic5 Lite (MEDIUM source confidence) ----
    AndroidDevice(
        name="Honor Magic5 Lite",
        brand="honor", manufacturer="Honor",
        model="RMO-NX1", device="HNARMO", product="HNARMO",
        build_fingerprint="HONOR/HNARMO/HNARMO:14/HONORRMO-N11/6.1.0.185:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="HONORRMO-N11", security_patch="2024-04-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=6, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 619",
        chipset="Qualcomm Snapdragon 695",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- Honor X9b (MEDIUM source confidence) ----
    AndroidDevice(
        name="Honor X9b",
        brand="honor", manufacturer="Honor",
        model="ALI-NX1", device="HNALI", product="HNALI",
        build_fingerprint="HONOR/HNALI/HNALI:14/HONORALI-N11/7.2.0.162:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="HONORALI-N11", security_patch="2024-05-01",
        screen_width=1220, screen_height=2652, density_dpi=429,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 710",
        chipset="Qualcomm Snapdragon 6 Gen 1",
        supported_android_versions=(13, 14),
    ),
    # ---- Motorola Edge 50 Fusion (MEDIUM source confidence) ----
    AndroidDevice(
        name="Motorola Edge 50 Fusion",
        brand="motorola", manufacturer="motorola",
        model="XT2429-1", device="hiphi", product="hiphi_g",
        build_fingerprint="motorola/hiphi_g/hiphi:14/U1TD34.8-30-5-3/hiphiabc:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="U1TD34.8-30-5-3", security_patch="2024-05-01",
        screen_width=1080, screen_height=2400, density_dpi=393,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 710",
        chipset="Qualcomm Snapdragon 7s Gen 2",
        supported_android_versions=(14,),
    ),
    # ---- OPPO A58 (MEDIUM source confidence) ----
    AndroidDevice(
        name="OPPO A58",
        brand="oppo", manufacturer="OPPO",
        model="CPH2577", device="CPH2577", product="CPH2577",
        build_fingerprint="OPPO/CPH2577/CPH2577:13/TP1A.220905.001/S.202308201100:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-08-05",
        screen_width=1080, screen_height=2400, density_dpi=392,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G52 MC2",
        chipset="MediaTek Helio G85",
        supported_android_versions=(13,),
    ),
    # ---- OPPO A78 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="OPPO A78 5G",
        brand="oppo", manufacturer="OPPO",
        model="CPH2483", device="CPH2483", product="CPH2483",
        build_fingerprint="OPPO/CPH2483/CPH2483:13/TP1A.220905.001/S.202308151430:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-08-05",
        screen_width=720, screen_height=1612, density_dpi=269,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Dimensity 700",
        supported_android_versions=(12, 13),
    ),
    # ---- OPPO Reno 10 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="OPPO Reno 10 5G",
        brand="oppo", manufacturer="OPPO",
        model="CPH2531", device="CPH2531", product="CPH2531",
        build_fingerprint="OPPO/CPH2531/CPH2531:13/TP1A.220905.001/S.202307181030:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-07-05",
        screen_width=1080, screen_height=2412, density_dpi=394,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MC4",
        chipset="MediaTek Dimensity 7050",
        supported_android_versions=(13,),
    ),
    # ---- OPPO Reno 8 Pro (MEDIUM source confidence) ----
    AndroidDevice(
        name="OPPO Reno 8 Pro",
        brand="oppo", manufacturer="OPPO",
        model="CPH2357", device="CPH2357", product="CPH2357",
        build_fingerprint="OPPO/CPH2357/CPH2357:13/TP1A.220905.001/S.202305101614:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-05-05",
        screen_width=1080, screen_height=2412, density_dpi=394,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC6",
        chipset="MediaTek Dimensity 8100-Max",
        supported_android_versions=(12, 13),
    ),
    # ---- Realme 10 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Realme 10",
        brand="realme", manufacturer="Realme",
        model="RMX3630", device="RMX3630", product="RMX3630",
        build_fingerprint="realme/RMX3630/RMX3630:13/TP1A.220905.001/R.202304151200:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-04-05",
        screen_width=1080, screen_height=2400, density_dpi=411,
        hardware_concurrency=8, device_memory=4, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Helio G99",
        supported_android_versions=(12, 13),
    ),
    # ---- Realme C55 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Realme C55",
        brand="realme", manufacturer="Realme",
        model="RMX3710", device="RMX3710", product="RMX3710",
        build_fingerprint="realme/RMX3710/RMX3710:13/TP1A.220905.001/R.2305101010:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-05-05",
        screen_width=1080, screen_height=2400, density_dpi=392,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G52 MC2",
        chipset="MediaTek Helio G88",
        supported_android_versions=(13,),
    ),
    # ---- ZTE Axon 50 Ultra (MEDIUM source confidence) ----
    AndroidDevice(
        name="ZTE Axon 50 Ultra",
        brand="zte", manufacturer="ZTE",
        model="A2024H", device="A2024H", product="A2024H",
        build_fingerprint="ZTE/A2024H/A2024H:14/TKQ1.230127.002/20240301:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TKQ1.230127.002", security_patch="2024-05-01",
        screen_width=1080, screen_height=2400, density_dpi=400,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 730",
        chipset="Qualcomm Snapdragon 8+ Gen 1",
        supported_android_versions=(13, 14),
    ),
    # ---- ZTE Nubia Z60 Ultra (MEDIUM source confidence) ----
    AndroidDevice(
        name="ZTE Nubia Z60 Ultra",
        brand="nubia", manufacturer="ZTE",
        model="NX721J", device="NX721J", product="NX721J",
        build_fingerprint="nubia/NX721J/NX721J:14/UKQ1.231003.002/20240201:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231003.002", security_patch="2024-04-01",
        screen_width=1116, screen_height=2480, density_dpi=400,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Qualcomm Snapdragon 8 Gen 3",
        supported_android_versions=(14,),
    ),
    # ---- Infinix Note 40 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Infinix Note 40 5G",
        brand="infinix", manufacturer="Infinix",
        model="X6853", device="Infinix-X6853", product="X6853",
        build_fingerprint="Infinix/X6853/X6853:14/UP1A.231005.007/240301:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-06-01",
        screen_width=1080, screen_height=2436, density_dpi=393,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Imagination Technologies", webgl_renderer="PowerVR BXM-8-256",
        chipset="MediaTek Dimensity 7020",
        supported_android_versions=(14,),
    ),
    # ---- Tecno Camon 30 Pro 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Tecno Camon 30 Pro 5G",
        brand="tecno", manufacturer="Tecno",
        model="CL8", device="Tecno-CL8", product="CL8",
        build_fingerprint="TECNO/CL8/CL8:14/UP1A.231005.007/240115:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-05-01",
        screen_width=1080, screen_height=2436, density_dpi=393,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G610",
        chipset="MediaTek Dimensity 8200 Ultimate",
        supported_android_versions=(14,),
    ),
    # ---- Vivo V27 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="Vivo V27 5G",
        brand="vivo", manufacturer="vivo",
        model="V2246", device="V2246", product="V2246",
        build_fingerprint="vivo/V2246/V2246:14/UP1A.231005.007/compiler02220857:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-02-01",
        screen_width=1080, screen_height=2400, density_dpi=388,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC4",
        chipset="MediaTek Dimensity 7200",
        supported_android_versions=(13, 14),
    ),
    # ---- Vivo Y100 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Vivo Y100",
        brand="vivo", manufacturer="vivo",
        model="V2239", device="V2239", product="V2239",
        build_fingerprint="vivo/V2239/V2239:14/TP1A.220624.032/compiler04101557:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.032", security_patch="2024-04-01",
        screen_width=1080, screen_height=2400, density_dpi=414,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MC4",
        chipset="MediaTek Dimensity 900",
        supported_android_versions=(13, 14),
    ),
    # ---- iQOO Z7 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="iQOO Z7 5G",
        brand="iqoo", manufacturer="vivo",
        model="I2203", device="PD2203", product="PD2203",
        build_fingerprint="vivo/PD2203/PD2203:14/TP1A.220624.032/compiler04101558:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.032", security_patch="2024-04-01",
        screen_width=1080, screen_height=2388, density_dpi=393,
        hardware_concurrency=8, device_memory=6, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G68 MC4",
        chipset="MediaTek Dimensity 920",
        supported_android_versions=(13, 14),
    ),
    # ---- Vivo V30 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Vivo V30",
        brand="vivo", manufacturer="vivo",
        model="V2318", device="V2318", product="V2318",
        build_fingerprint="vivo/V2318/V2318:14/UP1A.231005.007/compiler04101555:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-05-01",
        screen_width=1260, screen_height=2800, density_dpi=452,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 720",
        chipset="Qualcomm Snapdragon 7 Gen 3",
        supported_android_versions=(14,),
    ),
    # ---- Vivo Y200 (MEDIUM source confidence) ----
    AndroidDevice(
        name="Vivo Y200",
        brand="vivo", manufacturer="vivo",
        model="V2343A", device="V2343", product="V2343",
        build_fingerprint="vivo/V2343/V2343:14/TP1A.220624.032/compiler04101556:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.032", security_patch="2024-05-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 619",
        chipset="Qualcomm Snapdragon 4 Gen 1",
        supported_android_versions=(13, 14),
    ),
    # ---- iQOO Neo 7 (MEDIUM source confidence) ----
    AndroidDevice(
        name="iQOO Neo 7",
        brand="iqoo", manufacturer="vivo",
        model="I2214", device="I2214", product="I2214",
        build_fingerprint="vivo/I2214/I2214:13/TP1A.220624.014/compiler02161200:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220624.014", security_patch="2023-02-01",
        screen_width=1080, screen_height=2400, density_dpi=388,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC6",
        chipset="MediaTek Dimensity 8200",
        supported_android_versions=(13,),
    ),
    # ---- iQOO Z9x 5G (MEDIUM source confidence) ----
    AndroidDevice(
        name="iQOO Z9x 5G",
        brand="iqoo", manufacturer="vivo",
        model="I2219", device="PD2319", product="PD2319F",
        build_fingerprint="vivo/PD2319/PD2319:14/UP1A.231005.007/compiler04101559:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-06-01",
        screen_width=1080, screen_height=2408, density_dpi=400,
        hardware_concurrency=8, device_memory=4, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 710",
        chipset="Qualcomm Snapdragon 6 Gen 1",
        supported_android_versions=(14,),
    ),
    # ---- Xiaomi Redmi 12C (LOW source confidence) ----
    AndroidDevice(
        name="Xiaomi Redmi 12C",
        brand="xiaomi", manufacturer="Xiaomi",
        model="22120RN86G", device="earth", product="earth",
        build_fingerprint="xiaomi/earth/earth:13/TP1A.220624.014/V816.0.1.0.UMXINXM:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220624.014", security_patch="2024-01-01",
        screen_width=720, screen_height=1650, density_dpi=268,
        hardware_concurrency=8, device_memory=2, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G52 MC2",
        chipset="MediaTek Helio G85",
        supported_android_versions=(12, 13),
    ),
    # ---- Samsung Galaxy A33 5G (LOW source confidence) ----
    AndroidDevice(
        name="Samsung Galaxy A33 5G",
        brand="samsung", manufacturer="samsung",
        model="SM-A336B", device="a33x", product="a33xnsxx",
        build_fingerprint="samsung/a33xnsxx/a33x:14/UP1A.231005.007/A336BXXU7CXE1:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-05-01",
        screen_width=1080, screen_height=2400, density_dpi=411,
        hardware_concurrency=8, device_memory=6, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G68",
        chipset="Samsung Exynos 1280",
        supported_android_versions=(12, 13, 14),
    ),
    # ---- OPPO Reno 9 5G (LOW source confidence) ----
    AndroidDevice(
        name="OPPO Reno 9 5G",
        brand="oppo", manufacturer="OPPO",
        model="PHM110", device="RE5C52", product="RE5C52",
        build_fingerprint="OPPO/PHM110/RE5C52:14/TKQ1.220905.001/R.1234567900:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TKQ1.220905.001", security_patch="2024-05-01",
        screen_width=1080, screen_height=2412, density_dpi=394,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC6",
        chipset="MediaTek Dimensity 8100 Max",
        supported_android_versions=(13, 14),
    ),
    # ---- Infinix Note 30 Pro (LOW source confidence) ----
    AndroidDevice(
        name="Infinix Note 30 Pro",
        brand="infinix", manufacturer="Infinix",
        model="X678B", device="X678B", product="X678B",
        build_fingerprint="Infinix/X678B/X678B:13/TP1A.220624.014/230415V120:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220624.014", security_patch="2023-04-05",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Helio G99",
        supported_android_versions=(13,),
    ),
    # ---- Realme GT 6T (LOW source confidence) ----
    AndroidDevice(
        name="Realme GT 6T",
        brand="realme", manufacturer="realme",
        model="RMX3853", device="RE5CAL1", product="RE5CAL1",
        build_fingerprint="realme/RMX3853/RE5CAL1:14/SKQ1.220804.001/R.1234567901:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="SKQ1.220804.001", security_patch="2024-06-01",
        screen_width=1264, screen_height=2780, density_dpi=450,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 732",
        chipset="Qualcomm Snapdragon 7+ Gen 3",
        supported_android_versions=(14,),
    ),
    # ---- Realme Narzo 60 (LOW source confidence) ----
    AndroidDevice(
        name="Realme Narzo 60",
        brand="realme", manufacturer="Realme",
        model="RMX3750", device="RMX3750", product="RMX3750",
        build_fingerprint="realme/RMX3750/RMX3750:13/TP1A.220905.001/R.202307101100:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220905.001", security_patch="2023-07-05",
        screen_width=1080, screen_height=2400, density_dpi=411,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Dimensity 6020",
        supported_android_versions=(13,),
    ),
    # ---- Tecno Camon 20 Pro 5G (LOW source confidence) ----
    AndroidDevice(
        name="Tecno Camon 20 Pro 5G",
        brand="tecno", manufacturer="TECNO",
        model="CK8n", device="CK8n", product="CK8n",
        build_fingerprint="TECNO/CK8n/CK8n:13/TP1A.220624.014/230501V151:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220624.014", security_patch="2023-05-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G77 MC9",
        chipset="MediaTek Dimensity 8050",
        supported_android_versions=(13,),
    ),
    # ---- Infinix GT 20 Pro (LOW source confidence) ----
    AndroidDevice(
        name="Infinix GT 20 Pro",
        brand="infinix", manufacturer="Infinix",
        model="X6811", device="Infinix-X6811", product="X6811",
        build_fingerprint="Infinix/X6811/X6811:14/UP1A.231005.007/240401:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-06-01",
        screen_width=1080, screen_height=2436, density_dpi=393,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC6",
        chipset="MediaTek Dimensity 8200 Ultimate",
        supported_android_versions=(14,),
    ),
    # ---- Infinix Hot 40 Pro (LOW source confidence) ----
    AndroidDevice(
        name="Infinix Hot 40 Pro",
        brand="infinix", manufacturer="Infinix",
        model="X6837", device="Infinix-X6837", product="X6837",
        build_fingerprint="Infinix/X6837/X6837:14/TP1A.220624.014/231101:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.014", security_patch="2024-05-01",
        screen_width=1080, screen_height=2460, density_dpi=396,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Helio G99",
        supported_android_versions=(13, 14),
    ),
    # ---- Infinix Note 40 4G (LOW source confidence) ----
    AndroidDevice(
        name="Infinix Note 40 4G",
        brand="infinix", manufacturer="Infinix",
        model="X6853B", device="Infinix-X6853B", product="X6853B",
        build_fingerprint="Infinix/X6853B/X6853B:14/UP1A.231005.007/240201:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-05-01",
        screen_width=1080, screen_height=2436, density_dpi=393,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Helio G99 Ultimate",
        supported_android_versions=(14,),
    ),
    # ---- Nokia C32 (LOW source confidence) ----
    AndroidDevice(
        name="Nokia C32",
        brand="nokia", manufacturer="HMD Global",
        model="TA-1534", device="SNT", product="SNT_00EEA",
        build_fingerprint="Nokia/TA-1534_00EEA/SNT:14/UKQ1.231018.001/00WW_3_38E:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UKQ1.231018.001", security_patch="2024-03-01",
        screen_width=720, screen_height=1600, density_dpi=270,
        hardware_concurrency=8, device_memory=2, max_touch_points=5,
        webgl_vendor="Imagination Technologies", webgl_renderer="PowerVR GE8322",
        chipset="Unisoc SC9863A1",
        supported_android_versions=(13, 14),
    ),
    # ---- Tecno Camon 20 Premier 5G (LOW source confidence) ----
    AndroidDevice(
        name="Tecno Camon 20 Premier 5G",
        brand="tecno", manufacturer="Tecno",
        model="CK9n", device="Tecno-CK9n", product="CK9n",
        build_fingerprint="TECNO/CK9n/CK9n:14/TP1A.220624.014/230901:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.014", security_patch="2024-04-01",
        screen_width=1080, screen_height=2400, density_dpi=395,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G77 MC9",
        chipset="MediaTek Dimensity 8050",
        supported_android_versions=(13, 14),
    ),
    # ---- Tecno Pova 6 Pro 5G (LOW source confidence) ----
    AndroidDevice(
        name="Tecno Pova 6 Pro 5G",
        brand="tecno", manufacturer="Tecno",
        model="LI9", device="Tecno-LI9", product="LI9",
        build_fingerprint="TECNO/LI9/LI9:14/UP1A.231005.007/240301:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-05-01",
        screen_width=1080, screen_height=2436, density_dpi=393,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Dimensity 6080",
        supported_android_versions=(14,),
    ),
    # ---- Tecno Spark 20 Pro 5G (LOW source confidence) ----
    AndroidDevice(
        name="Tecno Spark 20 Pro 5G",
        brand="tecno", manufacturer="Tecno",
        model="KI8", device="Tecno-KI8", product="KI8",
        build_fingerprint="TECNO/KI8/KI8:14/UP1A.231005.007/240201:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2024-04-01",
        screen_width=1080, screen_height=2460, density_dpi=396,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G57 MC2",
        chipset="MediaTek Dimensity 6080",
        supported_android_versions=(14,),
    ),
    # ---- iQOO 12 (LOW source confidence) ----
    AndroidDevice(
        name="iQOO 12",
        brand="iqoo", manufacturer="vivo",
        model="I2220", device="I2220", product="I2220",
        build_fingerprint="vivo/I2220/I2220:14/UP1A.231005.007/compiler11281816:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="UP1A.231005.007", security_patch="2023-12-01",
        screen_width=1260, screen_height=2800, density_dpi=453,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="Qualcomm", webgl_renderer="Adreno (TM) 750",
        chipset="Snapdragon 8 Gen 3",
        supported_android_versions=(14,),
    ),
    # ---- Vivo V27 (LOW source confidence) ----
    AndroidDevice(
        name="Vivo V27",
        brand="vivo", manufacturer="vivo",
        model="V2231", device="V2231", product="V2231",
        build_fingerprint="vivo/V2231/V2231:14/TP1A.220624.032/compiler04101560:user/release-keys",
        android_version="14", sdk_version=34,
        build_id="TP1A.220624.032", security_patch="2024-05-01",
        screen_width=1080, screen_height=2400, density_dpi=415,
        hardware_concurrency=8, device_memory=8, max_touch_points=10,
        webgl_vendor="ARM", webgl_renderer="Mali-G610 MC4",
        chipset="MediaTek Dimensity 7200",
        supported_android_versions=(13, 14),
    ),
    # ---- Vivo T2x (LOW source confidence) ----
    AndroidDevice(
        name="Vivo T2x",
        brand="vivo", manufacturer="vivo",
        model="V2179A", device="V2179A", product="V2179A",
        build_fingerprint="vivo/V2179A/V2179A:13/TP1A.220624.014/compiler05201100:user/release-keys",
        android_version="13", sdk_version=33,
        build_id="TP1A.220624.014", security_patch="2023-05-01",
        screen_width=1080, screen_height=2408, density_dpi=401,
        hardware_concurrency=8, device_memory=8, max_touch_points=5,
        webgl_vendor="ARM", webgl_renderer="Mali-G77 MC9",
        chipset="MediaTek Dimensity 1300",
        supported_android_versions=(12, 13),
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
        gpu_family: Filter by GPU family ('adreno', 'mali', 'xclipse', 'powervr').
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
    _VERSION_TO_SDK = {8: 27, 9: 28, 10: 29, 11: 30, 12: 31, 13: 33, 14: 34, 15: 35, 16: 36}

    if device.supported_android_versions:
        ver = random.choice(device.supported_android_versions)
    else:
        ver = int(device.android_version.split(".", 1)[0])

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

    Mirrors the modern Chromium UA-CH GREASE shape seen on Android Chrome:
    - Two punctuation characters are rotated by major version.
    - Version rotates through Chromium's GREASE versions.
    - No leading whitespace/punctuation is emitted, matching current Android
      Chrome low-entropy headers such as ``Not:A-Brand`` for Chrome 145.

    Returns (brand_name, brand_version) tuple.
    """
    _GREASE_CHARS = [" ", "(", ":", "-", ".", "/", ")", ";", "=", "?", "_"]
    _GREASE_VERSIONS = ["8", "99", "24"]
    c1 = _GREASE_CHARS[major % len(_GREASE_CHARS)]
    c2 = _GREASE_CHARS[(major + 1) % len(_GREASE_CHARS)]
    return (f"Not{c1}A{c2}Brand", _GREASE_VERSIONS[major % len(_GREASE_VERSIONS)])


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

    # Chromium's GenerateBrandVersionList() stores GREASE at order[0],
    # Chromium at order[1], and the browser brand at order[2]. Do not build a
    # raw list and permute it by index; that changes the meaning of the order.
    brands = [None, None, None]
    full_version_list = [None, None, None]
    brands[order[0]] = {"brand": grease_name, "version": grease_ver}
    brands[order[1]] = {"brand": "Chromium", "version": str(major)}
    brands[order[2]] = {"brand": "Google Chrome", "version": str(major)}
    full_version_list[order[0]] = {"brand": grease_name, "version": f"{grease_ver}.0.0.0"}
    full_version_list[order[1]] = {"brand": "Chromium", "version": chrome_ver}
    full_version_list[order[2]] = {"brand": "Google Chrome", "version": chrome_ver}

    return chrome_ver, {
        "brands": brands,
        "fullVersionList": full_version_list,
    }


def list_device_names() -> List[str]:
    """List all device names."""
    return [d.name for d in DEVICES]
