with open("damru/docker.py", "r") as f:
    content = f.read()
# Fix shell_root calls that incorrectly pass allow_failure
content = content.replace(
    "await adb.shell_root(clean_cmd, timeout=10, allow_failure=True)",
    "await adb.shell_root(clean_cmd, timeout=10)"
)
with open("damru/docker.py", "w") as f:
    f.write(content)
print("Fixed shell_root cleanup calls")