from setuptools import setup, find_packages

setup(
    name="ivantauto",
    version="0.1.0",
    description="Automates Ivanti Secure Access Client VPN connection with TOTP injection on Windows",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="RUSSELL LISHUO TSENG",
    author_email="russell57260620@gmail.com",
    url="https://github.com/chumicat/IvantAuto",
    license="MIT",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "ivantauto=ivantauto.__main__:main",
        ],
    },
    python_requires=">=3.10",
    install_requires=[
        "pyotp>=2.9.0",
        "pywinauto>=0.6.8",
        "pyautogui>=0.9.54",
        "psutil>=5.9.0",
        "keyring>=24.0.0",
        "pywin32>=306",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Environment :: Win32 (MS Windows)",
        "Topic :: System :: Networking",
        "Topic :: Utilities",
        "Intended Audience :: End Users/Desktop",
    ],
)
