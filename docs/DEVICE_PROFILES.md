# Device Profiles

This file is generated from `damru/devices.py` and lists the Android device profiles available to Damru.

Use a profile by passing its exact name, model, or slug to `device=...`, for example:

```python
async with AsyncDamru(device="Samsung Galaxy S24 Ultra") as browser:
    ...

async with AsyncDamru(device="samsung_galaxy_s24_ultra") as browser:
    ...
```

GPU families matter most for emulator compatibility. MuMu is Adreno-oriented; Redroid is the supported path for full automation.

Total profiles: 51

| # | Profile | Slug | Model | Android | SDK | GPU family | GPU renderer | Chipset | Screen | RAM | Cores | Screen variants |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Samsung Galaxy S24 Ultra | `samsung_galaxy_s24_ultra` | SM-S928B | 14, 15 | 34 | adreno | Adreno (TM) 750 | Snapdragon 8 Gen 3 | 1440x3120 @560dpi | 8GB | 8 | 1440x3120 @560dpi<br>1080x2340 @420dpi |
| 2 | Samsung Galaxy S24 | `samsung_galaxy_s24` | SM-S921B | 14, 15 | 34 | adreno | Adreno (TM) 750 | Snapdragon 8 Gen 3 | 1080x2340 @420dpi | 8GB | 8 | - |
| 3 | Samsung Galaxy S23 Ultra | `samsung_galaxy_s23_ultra` | SM-S918B | 13, 14, 15 | 34 | adreno | Adreno (TM) 740 | Snapdragon 8 Gen 2 | 1440x3088 @560dpi | 8GB | 8 | 1440x3088 @560dpi<br>1080x2316 @420dpi |
| 4 | Samsung Galaxy S23 | `samsung_galaxy_s23` | SM-S911B | 13, 14, 15 | 34 | adreno | Adreno (TM) 740 | Snapdragon 8 Gen 2 | 1080x2340 @420dpi | 8GB | 8 | - |
| 5 | Samsung Galaxy S23 FE | `samsung_galaxy_s23_fe` | SM-S711B | 13, 14, 15, 16 | 34 | xclipse | Samsung Xclipse 920 | Exynos 2200 | 1080x2340 @450dpi | 8GB | 8 | - |
| 6 | Samsung Galaxy S25 Ultra | `samsung_galaxy_s25_ultra` | SM-S938B | 15 | 35 | adreno | Adreno (TM) 830 | Snapdragon 8 Elite | 1440x3120 @560dpi | 8GB | 8 | 1440x3120 @560dpi<br>1080x2340 @420dpi |
| 7 | Samsung Galaxy S25 | `samsung_galaxy_s25` | SM-S931B | 15 | 35 | adreno | Adreno (TM) 830 | Snapdragon 8 Elite | 1080x2340 @420dpi | 8GB | 8 | - |
| 8 | OnePlus 12 | `oneplus_12` | CPH2583 | 14, 15 | 34 | adreno | Adreno (TM) 750 | Snapdragon 8 Gen 3 | 1440x3168 @560dpi | 8GB | 8 | 1440x3168 @560dpi<br>1080x2376 @420dpi |
| 9 | OnePlus 11 | `oneplus_11` | CPH2449 | 13, 14, 15 | 34 | adreno | Adreno (TM) 740 | Snapdragon 8 Gen 2 | 1440x3216 @560dpi | 8GB | 8 | 1440x3216 @560dpi<br>1080x2412 @420dpi |
| 10 | Xiaomi 14 | `xiaomi_14` | 23127PN0CG | 14, 15 | 34 | adreno | Adreno (TM) 750 | Snapdragon 8 Gen 3 | 1200x2670 @480dpi | 8GB | 8 | - |
| 11 | Xiaomi 13 | `xiaomi_13` | 2211133G | 13, 14, 15 | 34 | adreno | Adreno (TM) 740 | Snapdragon 8 Gen 2 | 1080x2400 @440dpi | 8GB | 8 | - |
| 12 | Nothing Phone (2) | `nothing_phone_2` | A065 | 13, 14, 15 | 34 | adreno | Adreno (TM) 730 | Snapdragon 8+ Gen 1 | 1080x2412 @420dpi | 8GB | 8 | - |
| 13 | Xiaomi Redmi Note 13 Pro | `xiaomi_redmi_note_13_pro` | 23106RN0DA | 14, 15 | 34 | adreno | Adreno (TM) 710 | Snapdragon 7s Gen 2 | 1220x2712 @440dpi | 8GB | 8 | - |
| 14 | OPPO Find X7 Ultra | `oppo_find_x7_ultra` | CPH2603 | 14, 15 | 34 | adreno | Adreno (TM) 750 | Snapdragon 8 Gen 3 | 1440x3168 @560dpi | 8GB | 8 | 1440x3168 @560dpi<br>1080x2376 @420dpi |
| 15 | Realme GT 5 Pro | `realme_gt_5_pro` | RMX3888 | 14, 15 | 34 | adreno | Adreno (TM) 750 | Snapdragon 8 Gen 3 | 1264x2780 @480dpi | 8GB | 8 | - |
| 16 | Samsung Galaxy S22 Ultra | `samsung_galaxy_s22_ultra` | SM-S908B | 12, 13, 14, 15 | 32 | adreno | Adreno (TM) 730 | Snapdragon 8 Gen 1 | 1440x3088 @560dpi | 8GB | 8 | 1440x3088 @560dpi<br>1080x2316 @420dpi |
| 17 | Samsung Galaxy S22 | `samsung_galaxy_s22` | SM-S901B | 12, 13, 14, 15 | 32 | adreno | Adreno (TM) 730 | Snapdragon 8 Gen 1 | 1080x2340 @420dpi | 8GB | 8 | - |
| 18 | OnePlus 10 Pro | `oneplus_10_pro` | NE2210 | 12, 13, 14 | 32 | adreno | Adreno (TM) 730 | Snapdragon 8 Gen 1 | 1440x3216 @560dpi | 8GB | 8 | 1440x3216 @560dpi<br>1080x2412 @420dpi |
| 19 | Xiaomi 12 Pro | `xiaomi_12_pro` | 2201122G | 12, 13, 14 | 32 | adreno | Adreno (TM) 730 | Snapdragon 8 Gen 1 | 1440x3200 @560dpi | 8GB | 8 | 1440x3200 @560dpi<br>1080x2400 @420dpi |
| 20 | Google Pixel 8 Pro | `google_pixel_8_pro` | Pixel 8 Pro | 14, 15 | 34 | mali | Mali-G715-Immortalis MP11 | Google Tensor G3 | 1344x2992 @560dpi | 8GB | 8 | - |
| 21 | Google Pixel 8 | `google_pixel_8` | Pixel 8 | 14, 15 | 34 | mali | Mali-G715-Immortalis MP11 | Google Tensor G3 | 1080x2400 @420dpi | 8GB | 8 | - |
| 22 | Google Pixel 7 | `google_pixel_7` | Pixel 7 | 13, 14, 15 | 34 | mali | Mali-G710 MP7 | Google Tensor G2 | 1080x2400 @420dpi | 8GB | 8 | - |
| 23 | Google Pixel 7a | `google_pixel_7a` | Pixel 7a | 13, 14, 15 | 34 | mali | Mali-G710 MP7 | Google Tensor G2 | 1080x2400 @420dpi | 8GB | 8 | - |
| 24 | Google Pixel 9 Pro | `google_pixel_9_pro` | Pixel 9 Pro | 14, 15 | 35 | mali | Mali-G715-Immortalis MC10 | Google Tensor G4 | 1280x2856 @560dpi | 8GB | 8 | - |
| 25 | Google Pixel 9 | `google_pixel_9` | Pixel 9 | 14, 15 | 35 | mali | Mali-G715-Immortalis MC10 | Google Tensor G4 | 1080x2424 @420dpi | 8GB | 8 | - |
| 26 | Google Pixel 6 Pro | `google_pixel_6_pro` | Pixel 6 Pro | 12, 13, 14, 15 | 32 | mali | Mali-G78 | Google Tensor G1 | 1440x3120 @560dpi | 8GB | 8 | 1440x3120 @560dpi<br>1080x2340 @420dpi |
| 27 | Google Pixel 6 | `google_pixel_6` | Pixel 6 | 12, 13, 14, 15 | 32 | mali | Mali-G78 | Google Tensor G1 | 1080x2400 @420dpi | 8GB | 8 | - |
| 28 | Google Pixel 6a | `google_pixel_6a` | Pixel 6a | 12, 13, 14, 15 | 34 | mali | Mali-G78 | Google Tensor G1 | 1080x2400 @420dpi | 4GB | 8 | - |
| 29 | Samsung Galaxy A54 | `samsung_galaxy_a54` | SM-A546B | 13, 14, 15 | 34 | mali | Mali-G68 | Exynos 1380 | 1080x2340 @420dpi | 8GB | 8 | - |
| 30 | Samsung Galaxy A53 | `samsung_galaxy_a53` | SM-A536B | 12, 13, 14, 15 | 32 | mali | Mali-G68 | Exynos 1280 | 1080x2400 @420dpi | 4GB | 8 | - |
| 31 | Samsung Galaxy A55 | `samsung_galaxy_a55` | SM-A556B | 14, 15 | 34 | xclipse | Samsung Xclipse 530 | Exynos 1480 | 1080x2340 @420dpi | 8GB | 8 | - |
| 32 | OnePlus Nord 3 | `oneplus_nord_3` | CPH2493 | 13, 14 | 34 | mali | Mali-G710 MC10 | MediaTek Dimensity 9000 | 1080x2412 @420dpi | 8GB | 8 | - |
| 33 | Motorola Edge 40 | `motorola_edge_40` | XT2303-1 | 13, 14 | 34 | mali | Mali-G77 MC9 | MediaTek Dimensity 8020 | 1080x2400 @420dpi | 8GB | 8 | - |
| 34 | OnePlus 13 | `oneplus_13` | CPH2655 | 15 | 35 | adreno | Adreno (TM) 830 | Snapdragon 8 Elite | 1440x3168 @560dpi | 8GB | 8 | 1440x3168 @560dpi<br>1080x2376 @420dpi |
| 35 | POCO F6 | `poco_f6` | 24069PC21G | 14, 15 | 34 | adreno | Adreno (TM) 735 | Snapdragon 8s Gen 3 | 1220x2712 @440dpi | 8GB | 8 | - |
| 36 | Nothing Phone (1) | `nothing_phone_1` | A063 | 12, 13, 14, 15 | 34 | adreno | Adreno (TM) 642L | Snapdragon 778G+ | 1080x2400 @420dpi | 8GB | 8 | - |
| 37 | Honor Magic6 Pro | `honor_magic6_pro` | BVL-N49 | 14, 15 | 34 | adreno | Adreno (TM) 750 | Snapdragon 8 Gen 3 | 1280x2800 @480dpi | 8GB | 8 | - |
| 38 | Samsung Galaxy A35 | `samsung_galaxy_a35` | SM-A356B | 14, 15 | 34 | mali | Mali-G68 | Exynos 1380 | 1080x2340 @420dpi | 8GB | 8 | - |
| 39 | Google Pixel 8a | `google_pixel_8a` | Pixel 8a | 14, 15 | 34 | mali | Mali-G715-Immortalis MP11 | Google Tensor G3 | 1080x2400 @420dpi | 8GB | 8 | - |
| 40 | Nothing Phone (2a) | `nothing_phone_2a` | A142 | 14, 15 | 34 | mali | Mali-G610 MC6 | MediaTek Dimensity 7200 Pro | 1080x2412 @420dpi | 8GB | 8 | - |
| 41 | Vivo X100 | `vivo_x100` | V2324 | 14, 15 | 34 | mali | Immortalis-G720 MC12 | MediaTek Dimensity 9300 | 1260x2800 @480dpi | 8GB | 8 | - |
| 42 | OnePlus Nord 4 | `oneplus_nord_4` | CPH2661 | 14, 15 | 34 | adreno | Adreno (TM) 732 | Snapdragon 7+ Gen 3 | 1240x2772 @450dpi | 8GB | 8 | - |
| 43 | POCO F6 Pro | `poco_f6_pro` | 23113RKC6G | 14, 15 | 34 | adreno | Adreno (TM) 740 | Snapdragon 8 Gen 2 | 1440x3200 @560dpi | 8GB | 8 | 1440x3200 @560dpi<br>1080x2400 @420dpi |
| 44 | Samsung Galaxy S24 FE | `samsung_galaxy_s24_fe` | SM-S721B | 14, 15 | 34 | xclipse | Samsung Xclipse 940 | Exynos 2400e | 1080x2340 @420dpi | 8GB | 10 | - |
| 45 | Xiaomi 15 | `xiaomi_15` | 24129PN74G | 15 | 35 | adreno | Adreno (TM) 830 | Snapdragon 8 Elite | 1200x2670 @480dpi | 8GB | 8 | - |
| 46 | Samsung Galaxy A15 5G | `samsung_galaxy_a15_5g` | SM-A156B | 14, 15 | 34 | mali | Mali-G57 MC2 | MediaTek Dimensity 6100+ | 1080x2340 @420dpi | 4GB | 8 | - |
| 47 | Samsung Galaxy S21 FE | `samsung_galaxy_s21_fe` | SM-G990B | 12, 13, 14 | 34 | adreno | Adreno (TM) 660 | Snapdragon 888 | 1080x2340 @420dpi | 8GB | 8 | - |
| 48 | Xiaomi Redmi Note 12 5G | `xiaomi_redmi_note_12_5g` | 22111317G | 12, 13, 14 | 34 | adreno | Adreno (TM) 619 | Snapdragon 4 Gen 1 | 1080x2400 @420dpi | 4GB | 8 | - |
| 49 | Google Pixel 9 Pro XL | `google_pixel_9_pro_xl` | Pixel 9 Pro XL | 14, 15 | 35 | mali | Mali-G715-Immortalis MC10 | Google Tensor G4 | 1344x2992 @560dpi | 8GB | 8 | - |
| 50 | Motorola Moto G (5S) Plus | `motorola_moto_g_5s_plus` | Moto G (5S) Plus | 8.1.0 | 27 | adreno | Adreno (TM) 506 | Snapdragon 625 | 1080x1920 @480dpi | 2GB | 8 | - |
| 51 | Xiaomi Redmi 9A | `xiaomi_redmi_9a` | M2006C3LG | 10, 11 | 30 | powervr | PowerVR Rogue GE8320 | MediaTek Helio G25 | 720x1600 @320dpi | 2GB | 8 | - |

## Notes

- `device_memory` is the Chrome-visible memory bucket, capped to browser-reported values.
- Android versions are the supported spoofing range for that profile. The default build fingerprint is the version listed in `damru/devices.py`.
- Screen variants are realistic alternate display modes used by some devices, such as FHD+ and WQHD+.
- The `gpu_family` field is derived from the configured WebGL vendor/renderer and helps avoid incompatible emulator/profile pairings.
