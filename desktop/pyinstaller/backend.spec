# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the SinyalAbidnet Kliper Pro backend (onedir desktop build).

Build with:
    python -m PyInstaller --noconfirm --clean \
        --distpath desktop/pyinstaller/dist \
        --workpath desktop/pyinstaller/build \
        desktop/pyinstaller/backend.spec
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]  # project root
BACKEND = ROOT / "backend"

hiddenimports = []

# uvicorn loads its protocol/loop/lifespan implementations dynamically.
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("yt_dlp")
hiddenimports += collect_submodules("youtube_transcript_api")
hiddenimports += collect_submodules("google.genai")
hiddenimports += collect_submodules("backend")

hiddenimports += [
    "anyio._backends._asyncio",
    "certifi",
    "dotenv",
    "email_validator",
    "httptools",
    "multipart",
    "python_multipart",
    "websockets",
    "watchfiles",
]

datas = [
    (str(BACKEND / "fonts"), "backend/fonts"),
    (str(BACKEND / "cascades"), "backend/cascades"),
    (str(BACKEND / "haarcascade_frontalface_default.xml"), "backend"),
]
datas += collect_data_files("yt_dlp")
datas += collect_data_files("youtube_transcript_api")

# Transcription now uses a small whisper.cpp CLI that build-backend.mjs copies
# next to the executable, so PyTorch and openai-whisper are deliberately excluded.
# This keeps startup fast and avoids shipping ~1 GB of unused ML libraries.
excludes = [
    "whisper",
    "torch",
    "torchaudio",
    "torchvision",
    "tkinter",
    "matplotlib",
    "IPython",
    "pytest",
    "notebook",
    "jupyter",
    "setuptools",
    "pip",
]

a = Analysis(
    [str(BACKEND / "desktop_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="cheat-clip-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # keep stdout/stderr pipes intact for yt-dlp/ffmpeg progress parsing
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="cheat-clip-backend",
)
