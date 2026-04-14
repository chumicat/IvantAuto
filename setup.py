from setuptools import setup, find_packages

setup(
    name="ivantauto",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "ivantauto=ivantauto.__main__:main",
        ],
    },
    python_requires=">=3.10",
)
