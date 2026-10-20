# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the MMI3G-Toolkit GUI builder.

Produces a single-file Windows executable that bundles the builder code plus
the modules/ and core/ data directories it reads at runtime. Build with:

    pyinstaller packaging/mmi3g-gui.spec --noconfirm

or via packaging/build_exe.ps1, which also stamps the version. Run from the
repository root so the relative paths below resolve.
"""

import os

REPO_ROOT = os.path.abspath(os.getcwd())
BUILDER = os.path.join(REPO_ROOT, "builder")

block_cipher = None

a = Analysis(
    [os.path.join(BUILDER, "gui.py")],
    pathex=[BUILDER],
    binaries=[],
    # build_sd reads modules/ and core/ at runtime; the Firmware-Tools tab
    # runs the scripts in tools/ (plus generate_manifest) in-process. Ship all
    # of them inside the bundle so the .exe is self-contained.
    datas=[
        (os.path.join(REPO_ROOT, "modules"), "modules"),
        (os.path.join(REPO_ROOT, "core"), "core"),
        (os.path.join(REPO_ROOT, "tools"), "tools"),
        (os.path.join(REPO_ROOT, "builder", "generate_manifest.py"), "builder"),
        # App icon (dino), loaded at runtime for the window + splash.
        (os.path.join(REPO_ROOT, "assets"), "assets"),
    ],
    hiddenimports=["build_sd", "encoder", "version"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MMI3G-Toolkit-Builder",
    icon=os.path.join(REPO_ROOT, "assets", "icon.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
