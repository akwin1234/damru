# Device Profiles

This file is generated from `damru/devices.py` and lists the Android device profiles available to Damru.

Use a profile by passing its exact name, model, or slug to `device=...`, for example:

```python
async with AsyncDamru(device="Samsung Galaxy S24 Ultra") as browser:
    ...

async with AsyncDamru(device="samsung_galaxy_s24_ultra") as browser:
    ...
```

For an existing rooted worker that is already running, force one profile by name, model, or slug:

```bash
python -m damru force-profile --serial 127.0.0.1:5600 --device xiaomi_redmi_9a
python -m damru force-profile --serial 127.0.0.1:5600 --device "Moto G (5S) Plus" --no-chrome --clear-proxy
```

GPU families matter most for emulator compatibility. MuMu is Adreno-oriented; Redroid is the supported path for full automation.

The latest expansion added 104 regional Android profiles from the `r.txt` research set. Malformed entries, `UNKNOWN` fingerprints, obvious placeholder fingerprints, duplicate existing devices, and records with incomplete critical fields were not added. The imported set was validated on WSL Redroid with a runtime-only DataImpulse proxy: Sannysoft passed on all 104 profiles after retrying transient proxy/network timeouts, and a representative CreepJS/BrowserScan/Sannysoft/Cloudflare sample passed across Adreno, Mali, and PowerVR profiles.

Total profiles: 155

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
| 28 | Google Pixel 6a | `google_pixel_6a` | Pixel 6a | 12, 13, 14, 15 | 34 | mali | Mali-G78 | Google Tensor G1 | 1080x2400 @420dpi | 8GB | 8 | - |
| 29 | Samsung Galaxy A54 | `samsung_galaxy_a54` | SM-A546B | 13, 14, 15 | 34 | mali | Mali-G68 | Exynos 1380 | 1080x2340 @420dpi | 8GB | 8 | - |
| 30 | Samsung Galaxy A53 | `samsung_galaxy_a53` | SM-A536B | 12, 13, 14, 15 | 32 | mali | Mali-G68 | Exynos 1280 | 1080x2400 @420dpi | 8GB | 8 | - |
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
| 46 | Samsung Galaxy A15 5G | `samsung_galaxy_a15_5g` | SM-A156B | 14, 15 | 34 | mali | Mali-G57 MC2 | MediaTek Dimensity 6100+ | 1080x2340 @420dpi | 8GB | 8 | - |
| 47 | Samsung Galaxy S21 FE | `samsung_galaxy_s21_fe` | SM-G990B | 12, 13, 14 | 34 | adreno | Adreno (TM) 660 | Snapdragon 888 | 1080x2340 @420dpi | 8GB | 8 | - |
| 48 | Xiaomi Redmi Note 12 5G | `xiaomi_redmi_note_12_5g` | 22111317G | 12, 13, 14 | 34 | adreno | Adreno (TM) 619 | Snapdragon 4 Gen 1 | 1080x2400 @420dpi | 8GB | 8 | - |
| 49 | Google Pixel 9 Pro XL | `google_pixel_9_pro_xl` | Pixel 9 Pro XL | 14, 15 | 35 | mali | Mali-G715-Immortalis MC10 | Google Tensor G4 | 1344x2992 @560dpi | 8GB | 8 | - |
| 50 | Motorola Moto G (5S) Plus | `motorola_moto_g_5s_plus` | Moto G (5S) Plus | 8.1.0 | 27 | adreno | Adreno (TM) 506 | Snapdragon 625 | 1080x1920 @480dpi | 2GB | 8 | - |
| 51 | Xiaomi Redmi 9A | `xiaomi_redmi_9a` | M2006C3LG | 10, 11 | 30 | powervr | PowerVR Rogue GE8320 | MediaTek Helio G25 | 720x1600 @320dpi | 2GB | 8 | - |
| 52 | Xiaomi 11T Pro | `xiaomi_11t_pro` | 2107113SG | 11, 12, 13 | 33 | adreno | Adreno (TM) 660 | Snapdragon 888 | 1080x2400 @395dpi | 8GB | 8 | - |
| 53 | Xiaomi 12T Pro | `xiaomi_12t_pro` | 22081212UG | 12, 13 | 33 | adreno | Adreno (TM) 730 | Snapdragon 8+ Gen 1 | 1220x2712 @446dpi | 8GB | 8 | - |
| 54 | Xiaomi POCO F5 | `xiaomi_poco_f5` | 23049PCD8G | 13 | 33 | adreno | Adreno (TM) 725 | Snapdragon 7+ Gen 2 | 1080x2400 @395dpi | 8GB | 8 | - |
| 55 | Xiaomi POCO X5 Pro 5G | `xiaomi_poco_x5_pro_5g` | 22101320G | 12, 13 | 33 | adreno | Adreno (TM) 642L | Snapdragon 778G 5G | 1080x2400 @395dpi | 8GB | 8 | - |
| 56 | Xiaomi Redmi Note 11 | `xiaomi_redmi_note_11` | 2201117TG | 11, 12, 13 | 33 | adreno | Adreno (TM) 610 | Snapdragon 680 4G | 1080x2400 @409dpi | 6GB | 8 | - |
| 57 | Xiaomi Redmi Note 11 Pro 5G | `xiaomi_redmi_note_11_pro_5g` | 2201116SG | 11, 12, 13 | 33 | adreno | Adreno (TM) 619 | Snapdragon 695 5G | 1080x2400 @395dpi | 6GB | 8 | - |
| 58 | Samsung Galaxy A73 5G | `samsung_galaxy_a73_5g` | SM-A736B | 12, 13, 14 | 34 | adreno | Adreno (TM) 642L | Snapdragon 778G | 1080x2400 @393dpi | 8GB | 8 | - |
| 59 | Samsung Galaxy Z Flip 4 | `samsung_galaxy_z_flip_4` | SM-F721B | 12, 13, 14 | 34 | adreno | Adreno (TM) 730 | Snapdragon 8+ Gen 1 | 1080x2640 @426dpi | 8GB | 8 | - |
| 60 | Samsung Galaxy Z Fold 4 | `samsung_galaxy_z_fold_4` | SM-F936B | 12, 13, 14 | 34 | adreno | Adreno (TM) 730 | Snapdragon 8+ Gen 1 | 1812x2176 @373dpi | 8GB | 8 | - |
| 61 | Xiaomi POCO C65 | `xiaomi_poco_c65` | 2310FPCA4G | 13, 14 | 34 | mali | Mali-G52 MC2 | MediaTek Helio G85 | 720x1650 @268dpi | 4GB | 8 | - |
| 62 | Xiaomi Redmi 12 4G | `xiaomi_redmi_12_4g` | 23053RN02I | 13, 14 | 34 | mali | Mali-G52 MC2 | MediaTek Helio G88 | 720x1650 @268dpi | 4GB | 8 | - |
| 63 | Xiaomi Redmi Note 13 5G | `xiaomi_redmi_note_13_5g` | 2312DRAABG | 13, 14 | 34 | mali | Mali-G57 MC2 | MediaTek Dimensity 6080 | 1080x2400 @395dpi | 6GB | 8 | - |
| 64 | Samsung Galaxy A52s 5G | `samsung_galaxy_a52s_5g` | SM-A528B | 11, 12, 13 | 33 | adreno | Adreno (TM) 642L | Snapdragon 778G | 1080x2400 @405dpi | 8GB | 8 | - |
| 65 | Xiaomi 12T | `xiaomi_12t` | 22071212AG | 12, 13 | 33 | mali | Mali-G610 MC6 | MediaTek Dimensity 8100-Ultra | 1220x2712 @446dpi | 8GB | 8 | - |
| 66 | Xiaomi POCO M5 | `xiaomi_poco_m5` | 22071219CG | 12, 13 | 33 | mali | Mali-G57 MC2 | MediaTek Helio G99 | 1080x2408 @401dpi | 4GB | 8 | - |
| 67 | Xiaomi POCO M6 Pro 5G | `xiaomi_poco_m6_pro_5g` | 23076PC4BI | 13, 14 | 34 | adreno | Adreno (TM) 613 | Qualcomm Snapdragon 4 Gen 2 | 1080x2460 @396dpi | 4GB | 8 | - |
| 68 | Xiaomi POCO X6 5G | `xiaomi_poco_x6_5g` | 23122PCD1I | 13, 14 | 34 | adreno | Adreno (TM) 710 | Qualcomm Snapdragon 7s Gen 2 | 1220x2712 @450dpi | 8GB | 8 | - |
| 69 | Xiaomi Redmi Note 12 Pro 5G | `xiaomi_redmi_note_12_pro_5g` | 22101316C | 12, 13 | 33 | mali | Mali-G68 MC4 | MediaTek Dimensity 1080 | 1080x2400 @395dpi | 8GB | 8 | - |
| 70 | Samsung Galaxy A14 5G | `samsung_galaxy_a14_5g` | SM-A146B | 13, 14 | 34 | mali | Mali-G68 MC4 | Exynos 1330 | 1080x2408 @400dpi | 6GB | 8 | - |
| 71 | Samsung Galaxy A24 | `samsung_galaxy_a24` | SM-A245F | 13, 14 | 34 | mali | Mali-G57 MC2 | MediaTek Helio G99 | 1080x2340 @396dpi | 6GB | 8 | - |
| 72 | Samsung Galaxy A25 5G | `samsung_galaxy_a25_5g` | SM-A256B | 14 | 34 | mali | Mali-G68 | Samsung Exynos 1280 | 1080x2340 @396dpi | 6GB | 8 | - |
| 73 | Samsung Galaxy M14 5G | `samsung_galaxy_m14_5g` | SM-M146B | 13, 14 | 34 | mali | Mali-G68 MP2 | Samsung Exynos 1330 | 1080x2408 @400dpi | 4GB | 8 | - |
| 74 | Samsung Galaxy M34 5G | `samsung_galaxy_m34_5g` | SM-M346B | 13, 14 | 34 | mali | Mali-G68 | Exynos 1280 | 1080x2340 @396dpi | 6GB | 8 | - |
| 75 | Samsung Galaxy M54 5G | `samsung_galaxy_m54_5g` | SM-M546B | 13, 14 | 34 | mali | Mali-G68 MP5 | Exynos 1380 | 1080x2400 @399dpi | 8GB | 8 | - |
| 76 | Asus Zenfone 10 | `asus_zenfone_10` | ASUS_AI2302 | 13, 14 | 34 | adreno | Adreno (TM) 740 | Snapdragon 8 Gen 2 | 1080x2400 @445dpi | 8GB | 8 | - |
| 77 | Google Pixel 5a 5G | `google_pixel_5a_5g` | Pixel 5a | 11, 12, 13, 14 | 34 | adreno | Adreno (TM) 620 | Qualcomm Snapdragon 765G | 1080x2400 @420dpi | 4GB | 8 | - |
| 78 | Sony Xperia 1 V | `sony_xperia_1_v` | XQ-DQ54 | 13, 14 | 34 | adreno | Adreno (TM) 740 | Snapdragon 8 Gen 2 | 1644x3840 @643dpi | 8GB | 8 | - |
| 79 | Motorola Edge 30 Fusion | `motorola_edge_30_fusion` | XT2243-1 | 12, 13 | 33 | adreno | Adreno (TM) 660 | Snapdragon 888+ | 1080x2400 @402dpi | 8GB | 8 | - |
| 80 | Motorola Moto G84 5G | `motorola_moto_g84_5g` | XT2347-2 | 13 | 33 | adreno | Adreno (TM) 619 | Snapdragon 695 5G | 1080x2400 @405dpi | 8GB | 8 | - |
| 81 | OnePlus 8T | `oneplus_8t` | KB2005 | 11, 12, 13 | 33 | adreno | Adreno (TM) 650 | Snapdragon 865 5G | 1080x2400 @402dpi | 8GB | 8 | - |
| 82 | OnePlus 9 | `oneplus_9` | LE2115 | 11, 12, 13 | 33 | adreno | Adreno (TM) 660 | Snapdragon 888 5G | 1080x2400 @402dpi | 8GB | 8 | - |
| 83 | OnePlus 9 Pro | `oneplus_9_pro` | LE2123 | 11, 12, 13 | 33 | adreno | Adreno (TM) 660 | Snapdragon 888 5G | 1440x3216 @525dpi | 8GB | 8 | - |
| 84 | OnePlus Nord CE 3 Lite | `oneplus_nord_ce_3_lite` | CPH2467 | 13 | 33 | adreno | Adreno (TM) 619 | Snapdragon 695 5G | 1080x2400 @391dpi | 8GB | 8 | - |
| 85 | Google Pixel Fold | `google_pixel_fold` | Pixel Fold | 13, 14 | 34 | mali | Mali-G710 MC10 | Google Tensor G2 | 1840x2208 @380dpi | 8GB | 8 | - |
| 86 | Motorola Moto G54 5G | `motorola_moto_g54_5g` | XT2303-2 | 13, 14 | 34 | powervr | PowerVR BXM-8-256 | MediaTek Dimensity 7020 | 1080x2400 @405dpi | 8GB | 8 | - |
| 87 | iQOO Neo 7 5G | `iqoo_neo_7_5g` | I2214 | 13, 14 | 34 | mali | Mali-G610 MC6 | MediaTek Dimensity 8200 | 1080x2400 @388dpi | 8GB | 8 | - |
| 88 | iQOO Z9 5G | `iqoo_z9_5g` | I2302 | 14 | 34 | mali | Mali-G610 MC4 | MediaTek Dimensity 7200 | 1260x2800 @452dpi | 8GB | 8 | - |
| 89 | Motorola Edge 40 Neo | `motorola_edge_40_neo` | XT2307-1 | 13 | 33 | mali | Mali-G610 MC3 | MediaTek Dimensity 7030 | 1080x2400 @402dpi | 8GB | 8 | - |
| 90 | Nokia G60 5G | `nokia_g60_5g` | TA-1478 | 12, 13, 14 | 34 | adreno | Adreno (TM) 619 | Qualcomm Snapdragon 695 | 1080x2408 @400dpi | 4GB | 8 | - |
| 91 | Nokia X30 5G | `nokia_x30_5g` | TA-1450 | 12, 13, 14 | 34 | adreno | Adreno (TM) 619 | Qualcomm Snapdragon 695 | 1080x2400 @409dpi | 6GB | 8 | - |
| 92 | OnePlus Nord 2 5G | `oneplus_nord_2_5g` | DN2103 | 11, 12, 13 | 33 | mali | Mali-G77 MC9 | MediaTek Dimensity 1200 | 1080x2400 @409dpi | 8GB | 8 | - |
| 93 | OnePlus Nord CE 2 5G | `oneplus_nord_ce_2_5g` | CPH2409 | 11, 12, 13 | 33 | mali | Mali-G68 MC4 | MediaTek Dimensity 900 | 1080x2400 @409dpi | 6GB | 8 | - |
| 94 | Sony Xperia 10 V | `sony_xperia_10_v` | XQ-DC54 | 13, 14 | 34 | adreno | Adreno (TM) 619 | Qualcomm Snapdragon 695 | 1080x2520 @449dpi | 6GB | 8 | - |
| 95 | Vivo V29 | `vivo_v29` | V2250 | 13, 14 | 34 | adreno | Adreno (TM) 642L | Qualcomm Snapdragon 778G | 1260x2800 @452dpi | 8GB | 8 | - |
| 96 | ZTE Nubia RedMagic 8 Pro | `zte_nubia_redmagic_8_pro` | NX729J | 13, 14 | 34 | adreno | Adreno (TM) 740 | Qualcomm Snapdragon 8 Gen 2 | 1116x2480 @400dpi | 8GB | 8 | - |
| 97 | ZTE Nubia RedMagic 9 Pro | `zte_nubia_redmagic_9_pro` | NX769J | 14 | 34 | adreno | Adreno (TM) 750 | Qualcomm Snapdragon 8 Gen 3 | 1116x2480 @400dpi | 8GB | 8 | - |
| 98 | iQOO Neo 8 | `iqoo_neo_8` | I2302 | 13, 14 | 34 | adreno | Adreno (TM) 730 | Qualcomm Snapdragon 8+ Gen 1 | 1260x2800 @452dpi | 8GB | 8 | - |
| 99 | OnePlus 9R | `oneplus_9r` | LE2101 | 11, 12, 13 | 33 | adreno | Adreno (TM) 650 | Qualcomm Snapdragon 870 | 1080x2400 @402dpi | 8GB | 8 | - |
| 100 | Sony Xperia 5 V | `sony_xperia_5_v` | XQ-DE54 | 13, 14, 15 | 35 | adreno | Adreno (TM) 740 | Qualcomm Snapdragon 8 Gen 2 | 1080x2520 @449dpi | 8GB | 8 | - |
| 101 | Xiaomi POCO X6 Pro 5G | `xiaomi_poco_x6_pro_5g` | 2311DRK48I | 14 | 34 | mali | Mali-G615 MC6 | MediaTek Dimensity 8300-Ultra | 1220x2712 @446dpi | 8GB | 8 | - |
| 102 | Xiaomi Redmi 13 5G | `xiaomi_redmi_13_5g` | 2406ERN9CI | 14 | 34 | mali | Mali-G57 MC2 | MediaTek Dimensity 6080 | 1080x2460 @396dpi | 6GB | 8 | - |
| 103 | Xiaomi Redmi 13C 5G | `xiaomi_redmi_13c_5g` | 23124RN87I | 13, 14 | 34 | mali | Mali-G57 MC2 | MediaTek Dimensity 6100+ | 720x1650 @268dpi | 4GB | 8 | - |
| 104 | Xiaomi Redmi Note 14 5G | `xiaomi_redmi_note_14_5g` | 24090RA29C | 14 | 34 | powervr | PowerVR BXM-8-256 | MediaTek Dimensity 7025 Ultra | 1080x2400 @395dpi | 6GB | 8 | - |
| 105 | Samsung Galaxy A05 | `samsung_galaxy_a05` | SM-A055F | 13, 14 | 34 | mali | Mali-G52 MC2 | MediaTek Helio G85 | 720x1600 @262dpi | 4GB | 8 | - |
| 106 | Samsung Galaxy A15 4G | `samsung_galaxy_a15_4g` | SM-A155F | 14 | 34 | mali | Mali-G57 MC2 | MediaTek Helio G99 | 1080x2340 @396dpi | 4GB | 8 | - |
| 107 | Samsung Galaxy A24 4G | `samsung_galaxy_a24_4g` | SM-A245F | 13, 14 | 34 | mali | Mali-G57 MC2 | MediaTek Helio G99 | 1080x2340 @420dpi | 6GB | 8 | - |
| 108 | Samsung Galaxy F14 5G | `samsung_galaxy_f14_5g` | SM-E146B | 13, 14 | 34 | mali | Mali-G68 MP2 | Samsung Exynos 1330 | 1080x2408 @400dpi | 4GB | 8 | - |
| 109 | Samsung Galaxy A05s | `samsung_galaxy_a05s` | SM-A057F | 13, 14 | 34 | adreno | Adreno (TM) 610 | Qualcomm Snapdragon 680 | 1080x2400 @400dpi | 4GB | 8 | - |
| 110 | Samsung Galaxy A23 | `samsung_galaxy_a23` | SM-A235F | 12, 13, 14 | 34 | adreno | Adreno (TM) 610 | Qualcomm Snapdragon 680 | 1080x2408 @400dpi | 4GB | 8 | - |
| 111 | Honor 90 | `honor_90` | REA-NX9 | 13 | 33 | adreno | Adreno (TM) 644 | Snapdragon 7 Gen 1 Accelerated Edition | 1200x2664 @435dpi | 8GB | 8 | - |
| 112 | Honor Magic5 Pro | `honor_magic5_pro` | PGT-N19 | 13 | 33 | adreno | Adreno (TM) 740 | Snapdragon 8 Gen 2 | 1312x2848 @460dpi | 8GB | 8 | - |
| 113 | Motorola Moto G64 5G | `motorola_moto_g64_5g` | XT2431-1 | 14 | 34 | mali | Mali-G57 MC2 | MediaTek Dimensity 7025 | 1080x2400 @405dpi | 8GB | 8 | - |
| 114 | OnePlus 10R 5G | `oneplus_10r_5g` | PGKM10 | 12, 13, 14 | 34 | mali | Mali-G610 MC6 | MediaTek Dimensity 8100 Max | 1080x2412 @394dpi | 8GB | 8 | - |
| 115 | Realme 11 Pro+ | `realme_11_pro+` | RMX3741 | 13, 14 | 34 | mali | Mali-G68 MC4 | MediaTek Dimensity 7050 | 1080x2412 @394dpi | 8GB | 8 | - |
| 116 | Asus ROG Phone 7 | `asus_rog_phone_7` | AI2205 | 13, 14 | 34 | adreno | Adreno (TM) 740 | Qualcomm Snapdragon 8 Gen 2 | 1080x2448 @395dpi | 8GB | 8 | - |
| 117 | Asus ROG Phone 8 | `asus_rog_phone_8` | AI2401 | 14 | 34 | adreno | Adreno (TM) 750 | Qualcomm Snapdragon 8 Gen 3 | 1080x2400 @388dpi | 8GB | 8 | - |
| 118 | Honor 200 | `honor_200` | ELI-AN00 | 14 | 34 | adreno | Adreno (TM) 720 | Qualcomm Snapdragon 7 Gen 3 | 1200x2664 @435dpi | 8GB | 8 | - |
| 119 | Honor Magic5 Lite | `honor_magic5_lite` | RMO-NX1 | 12, 13, 14 | 34 | adreno | Adreno (TM) 619 | Qualcomm Snapdragon 695 | 1080x2400 @395dpi | 6GB | 8 | - |
| 120 | Honor X9b | `honor_x9b` | ALI-NX1 | 13, 14 | 34 | adreno | Adreno (TM) 710 | Qualcomm Snapdragon 6 Gen 1 | 1220x2652 @429dpi | 8GB | 8 | - |
| 121 | Motorola Edge 50 Fusion | `motorola_edge_50_fusion` | XT2429-1 | 14 | 34 | adreno | Adreno (TM) 710 | Qualcomm Snapdragon 7s Gen 2 | 1080x2400 @393dpi | 8GB | 8 | - |
| 122 | OPPO A58 | `oppo_a58` | CPH2577 | 13 | 33 | mali | Mali-G52 MC2 | MediaTek Helio G85 | 1080x2400 @392dpi | 6GB | 8 | - |
| 123 | OPPO A78 5G | `oppo_a78_5g` | CPH2483 | 12, 13 | 33 | mali | Mali-G57 MC2 | MediaTek Dimensity 700 | 720x1612 @269dpi | 4GB | 8 | - |
| 124 | OPPO Reno 10 5G | `oppo_reno_10_5g` | CPH2531 | 13 | 33 | mali | Mali-G68 MC4 | MediaTek Dimensity 7050 | 1080x2412 @394dpi | 8GB | 8 | - |
| 125 | OPPO Reno 8 Pro | `oppo_reno_8_pro` | CPH2357 | 12, 13 | 33 | mali | Mali-G610 MC6 | MediaTek Dimensity 8100-Max | 1080x2412 @394dpi | 8GB | 8 | - |
| 126 | Realme 10 | `realme_10` | RMX3630 | 12, 13 | 33 | mali | Mali-G57 MC2 | MediaTek Helio G99 | 1080x2400 @411dpi | 4GB | 8 | - |
| 127 | Realme C55 | `realme_c55` | RMX3710 | 13 | 33 | mali | Mali-G52 MC2 | MediaTek Helio G88 | 1080x2400 @392dpi | 6GB | 8 | - |
| 128 | ZTE Axon 50 Ultra | `zte_axon_50_ultra` | A2024H | 13, 14 | 34 | adreno | Adreno (TM) 730 | Qualcomm Snapdragon 8+ Gen 1 | 1080x2400 @400dpi | 8GB | 8 | - |
| 129 | ZTE Nubia Z60 Ultra | `zte_nubia_z60_ultra` | NX721J | 14 | 34 | adreno | Adreno (TM) 750 | Qualcomm Snapdragon 8 Gen 3 | 1116x2480 @400dpi | 8GB | 8 | - |
| 130 | Infinix Note 40 5G | `infinix_note_40_5g` | X6853 | 14 | 34 | powervr | PowerVR BXM-8-256 | MediaTek Dimensity 7020 | 1080x2436 @393dpi | 8GB | 8 | - |
| 131 | Tecno Camon 30 Pro 5G | `tecno_camon_30_pro_5g` | CL8 | 14 | 34 | mali | Mali-G610 | MediaTek Dimensity 8200 Ultimate | 1080x2436 @393dpi | 8GB | 8 | - |
| 132 | Vivo V27 5G | `vivo_v27_5g` | V2246 | 13, 14 | 34 | mali | Mali-G610 MC4 | MediaTek Dimensity 7200 | 1080x2400 @388dpi | 8GB | 8 | - |
| 133 | Vivo Y100 | `vivo_y100` | V2239 | 13, 14 | 34 | mali | Mali-G68 MC4 | MediaTek Dimensity 900 | 1080x2400 @414dpi | 8GB | 8 | - |
| 134 | iQOO Z7 5G | `iqoo_z7_5g` | I2203 | 13, 14 | 34 | mali | Mali-G68 MC4 | MediaTek Dimensity 920 | 1080x2388 @393dpi | 6GB | 8 | - |
| 135 | Vivo V30 | `vivo_v30` | V2318 | 14 | 34 | adreno | Adreno (TM) 720 | Qualcomm Snapdragon 7 Gen 3 | 1260x2800 @452dpi | 8GB | 8 | - |
| 136 | Vivo Y200 | `vivo_y200` | V2343A | 13, 14 | 34 | adreno | Adreno (TM) 619 | Qualcomm Snapdragon 4 Gen 1 | 1080x2400 @395dpi | 8GB | 8 | - |
| 137 | iQOO Neo 7 | `iqoo_neo_7` | I2214 | 13 | 33 | mali | Mali-G610 MC6 | MediaTek Dimensity 8200 | 1080x2400 @388dpi | 8GB | 8 | - |
| 138 | iQOO Z9x 5G | `iqoo_z9x_5g` | I2219 | 14 | 34 | adreno | Adreno (TM) 710 | Qualcomm Snapdragon 6 Gen 1 | 1080x2408 @400dpi | 4GB | 8 | - |
| 139 | Xiaomi Redmi 12C | `xiaomi_redmi_12c` | 22120RN86G | 12, 13 | 33 | mali | Mali-G52 MC2 | MediaTek Helio G85 | 720x1650 @268dpi | 2GB | 8 | - |
| 140 | Samsung Galaxy A33 5G | `samsung_galaxy_a33_5g` | SM-A336B | 12, 13, 14 | 34 | mali | Mali-G68 | Samsung Exynos 1280 | 1080x2400 @411dpi | 6GB | 8 | - |
| 141 | OPPO Reno 9 5G | `oppo_reno_9_5g` | PHM110 | 13, 14 | 34 | mali | Mali-G610 MC6 | MediaTek Dimensity 8100 Max | 1080x2412 @394dpi | 8GB | 8 | - |
| 142 | Infinix Note 30 Pro | `infinix_note_30_pro` | X678B | 13 | 33 | mali | Mali-G57 MC2 | MediaTek Helio G99 | 1080x2400 @395dpi | 8GB | 8 | - |
| 143 | Realme GT 6T | `realme_gt_6t` | RMX3853 | 14 | 34 | adreno | Adreno (TM) 732 | Qualcomm Snapdragon 7+ Gen 3 | 1264x2780 @450dpi | 8GB | 8 | - |
| 144 | Realme Narzo 60 | `realme_narzo_60` | RMX3750 | 13 | 33 | mali | Mali-G57 MC2 | MediaTek Dimensity 6020 | 1080x2400 @411dpi | 8GB | 8 | - |
| 145 | Tecno Camon 20 Pro 5G | `tecno_camon_20_pro_5g` | CK8n | 13 | 33 | mali | Mali-G77 MC9 | MediaTek Dimensity 8050 | 1080x2400 @395dpi | 8GB | 8 | - |
| 146 | Infinix GT 20 Pro | `infinix_gt_20_pro` | X6811 | 14 | 34 | mali | Mali-G610 MC6 | MediaTek Dimensity 8200 Ultimate | 1080x2436 @393dpi | 8GB | 8 | - |
| 147 | Infinix Hot 40 Pro | `infinix_hot_40_pro` | X6837 | 13, 14 | 34 | mali | Mali-G57 MC2 | MediaTek Helio G99 | 1080x2460 @396dpi | 8GB | 8 | - |
| 148 | Infinix Note 40 4G | `infinix_note_40_4g` | X6853B | 14 | 34 | mali | Mali-G57 MC2 | MediaTek Helio G99 Ultimate | 1080x2436 @393dpi | 8GB | 8 | - |
| 149 | Nokia C32 | `nokia_c32` | TA-1534 | 13, 14 | 34 | powervr | PowerVR GE8322 | Unisoc SC9863A1 | 720x1600 @270dpi | 2GB | 8 | - |
| 150 | Tecno Camon 20 Premier 5G | `tecno_camon_20_premier_5g` | CK9n | 13, 14 | 34 | mali | Mali-G77 MC9 | MediaTek Dimensity 8050 | 1080x2400 @395dpi | 8GB | 8 | - |
| 151 | Tecno Pova 6 Pro 5G | `tecno_pova_6_pro_5g` | LI9 | 14 | 34 | mali | Mali-G57 MC2 | MediaTek Dimensity 6080 | 1080x2436 @393dpi | 8GB | 8 | - |
| 152 | Tecno Spark 20 Pro 5G | `tecno_spark_20_pro_5g` | KI8 | 14 | 34 | mali | Mali-G57 MC2 | MediaTek Dimensity 6080 | 1080x2460 @396dpi | 8GB | 8 | - |
| 153 | iQOO 12 | `iqoo_12` | I2220 | 14 | 34 | adreno | Adreno (TM) 750 | Snapdragon 8 Gen 3 | 1260x2800 @453dpi | 8GB | 8 | - |
| 154 | Vivo V27 | `vivo_v27` | V2231 | 13, 14 | 34 | mali | Mali-G610 MC4 | MediaTek Dimensity 7200 | 1080x2400 @415dpi | 8GB | 8 | - |
| 155 | Vivo T2x | `vivo_t2x` | V2179A | 12, 13 | 33 | mali | Mali-G77 MC9 | MediaTek Dimensity 1300 | 1080x2408 @401dpi | 8GB | 8 | - |

## Notes

- `device_memory` is the Chrome-visible memory bucket, capped to browser-reported values.
- Android versions are the supported spoofing range for that profile. The default build fingerprint is the version listed in `damru/devices.py`.
- Screen variants are realistic alternate display modes used by some devices, such as FHD+ and WQHD+.
- The `gpu_family` field is derived from the configured WebGL vendor/renderer and helps avoid incompatible emulator/profile pairings.
- Empty Android `navigator.plugins` / `navigator.mimeTypes` arrays are normal for Android Chrome and are not a profile failure.
