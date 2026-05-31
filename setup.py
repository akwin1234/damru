from setuptools import setup, find_packages

setup(
    name="damru",
    version="0.1.0",
    packages=find_packages(include=["damru*"]),
    install_requires=[
        "playwright>=1.40",
        "requests>=2.28",
        "pysocks>=1.7",
    ],
    extras_require={
        "dev": ["pytest", "pytest-asyncio"],
    },
    entry_points={
        "console_scripts": [
            "damru-benchmark=damru.benchmark:main",
        ],
    },
)
