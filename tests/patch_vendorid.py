#!/usr/bin/env python3
"""Find and patch Vulkan vendorID in vulkan.pastel.so.

SwiftShader uses vendorID=0x1AE0 (Google) and deviceID=0xC0DE.
We patch vendorID to target vendor (e.g. 0x5143=Qualcomm).
"""
import struct
import sys

VENDOR_IDS = {
    "qualcomm": 0x5143,
    "arm": 0x13B5,
    "samsung": 0x144D,
    "google": 0x1AE0,
}

SWIFTSHADER_VENDOR_ID = 0x1AE0
SWIFTSHADER_DEVICE_ID = 0xC0DE

def find_vendor_id(data: bytearray, window: int = 64) -> list:
    vendor_bytes = struct.pack("<I", SWIFTSHADER_VENDOR_ID)
    device_bytes = struct.pack("<I", SWIFTSHADER_DEVICE_ID)

    device_positions = []
    idx = 0
    while True:
        idx = data.find(device_bytes, idx)
        if idx == -1:
            break
        device_positions.append(idx)
        idx += 4

    print(f"Found {len(device_positions)} occurrences of deviceID 0x{SWIFTSHADER_DEVICE_ID:04X}")

    candidates = []
    for dpos in device_positions:
        search_start = max(0, dpos - window)
        search_end = min(len(data), dpos + window)
        vidx = search_start
        while True:
            vidx = data.find(vendor_bytes, vidx, search_end)
            if vidx == -1:
                break
            offset = vidx - dpos
            candidates.append((vidx, dpos, offset))
            print(f"  vendorID at 0x{vidx:08X}, deviceID at 0x{dpos:08X}, offset={offset}")
            vidx += 4

    return candidates

def patch_vendor_id(filepath: str, target_vendor: str) -> bool:
    if target_vendor.lower() not in VENDOR_IDS:
        print(f"Unknown vendor: {target_vendor}. Known: {list(VENDOR_IDS.keys())}")
        return False

    target_id = VENDOR_IDS[target_vendor.lower()]
    target_bytes = struct.pack("<I", target_id)

    with open(filepath, "rb") as f:
        data = bytearray(f.read())

    print(f"File size: {len(data):,} bytes")
    print(f"Target vendor: {target_vendor} (0x{target_id:04X})")

    candidates = find_vendor_id(data)

    if not candidates:
        print("No vendorID found near deviceID")
        return False

    for vidx, dpos, offset in candidates:
        print(f"Patching vendorID at 0x{vidx:08X}: 0x{SWIFTSHADER_VENDOR_ID:04X} -> 0x{target_id:04X}")
        data[vidx:vidx + 4] = target_bytes

    with open(filepath, "wb") as f:
        f.write(data)

    print(f"Patched {len(candidates)} vendorID(s)")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <file.so> <vendor>")
        sys.exit(1)
    success = patch_vendor_id(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)
