# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['_entry.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # pywin32
        'win32api',
        'win32con',
        'win32gui',
        'win32process',
        'win32service',
        'win32serviceutil',
        'pywintypes',
        # comtypes (pulled in by pywinauto UIA backend)
        'comtypes',
        'comtypes.client',
        'comtypes.server',
        # pywinauto
        'pywinauto',
        'pywinauto.application',
        'pywinauto.controls',
        'pywinauto.controls.uia_controls',
        # keyring Windows backend
        'keyring.backends',
        'keyring.backends.Windows',
        # standard lib used at runtime
        'configparser',
        'ctypes',
        'ctypes.wintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ivantauto',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,   # CLI tool — keep console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
