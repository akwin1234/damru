with open("damru/docker.py", "r") as f:
    content = f.read()

old = '                await adb.shell_root(clean_cmd, timeout=10)'
new = '                try:\n                    await adb.shell_root(clean_cmd, timeout=10)\n                except Exception:\n                    pass'

# Only replace the one inside the cleanup loop, not elsewhere
# Find the cleanup block
idx = content.find("Cleaning up temp files")
if idx >= 0:
    # Find the first occurrence of shell_root after the block
    block = content[idx:idx+800]
    if old in block:
        block = block.replace(old, new)
        content = content[:idx] + block + content[idx+800:]
        with open("damru/docker.py", "w") as f:
            f.write(content)
        print("Fixed cleanup try/except")
    else:
        print("old text not found in block")
        print(repr(block[-200:]))
else:
    print("cleanup block not found")