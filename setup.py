from setuptools import setup, find_packages

setup(
    name="damru",
    version="0.1.0",
    author="Damru Framework",
    author_email="contact@damru.dev",
    packages=find_packages(include=["damru*"]),
    package_data={
        "damru.playwright_patch": ["*.js"],
        "damru.wsl_kernel": ["wsl2-kernel-*", "*.config", "SHA256SUMS", "README.md", "source_metadata/*"],
        "damru.assets": ["magisk.apk", "libfakemem.c"],
        "damru.ui": ["static/*"],
    },
    install_requires=[
        "playwright>=1.40,<1.60",
        "requests>=2.28",
        "pysocks>=1.7",
        "websockets>=12",
    ],
    extras_require={
        "dev": ["pytest", "pytest-asyncio", "aiohttp"],
    },
    entry_points={
        "console_scripts": [
            "damru=damru.cli:main",
            "damru-benchmark=damru.benchmark:main",
        ],
    },
)
