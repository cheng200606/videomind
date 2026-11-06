# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# 桌面版内置 Whisper 本地转写（faster-whisper / ctranslate2 / av / tokenizers）。
# 其余重引擎（yueying、RapidOCR、Paddle、FunASR、torch）仍排除，避免安装包无限膨胀。
_whisper_packages = (
    'faster_whisper', 'ctranslate2', 'av', 'tokenizers',
    'huggingface_hub', 'httpx2', 'httpcore2', 'numpy',
)
extra_datas, extra_binaries, extra_hidden = [], [], []
for _pkg in _whisper_packages:
    _d, _b, _h = collect_all(_pkg)
    extra_datas += _d
    extra_binaries += _b
    extra_hidden += _h

a = Analysis(
    ['run_server.py'],
    pathex=['.'],
    binaries=extra_binaries,
    datas=[
        ('tests/fixtures', 'app_fixtures'),
        ('../frontend/dist', 'frontend_dist'),
        *extra_datas,
    ],
    hiddenimports=[
        'uvicorn', 'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
        *extra_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'yueying', 'funasr', 'torch', 'torchaudio',
        'rapidocr', 'onnxruntime', 'cv2', 'scipy', 'shapely', 'pyclipper', 'PIL', 'imagehash',
        'paddle', 'paddleocr', 'paddlepaddle',
        'mcp', 'mcp_types', 'cryptography', 'pyjwt', 'jsonschema',
        'yt_dlp', 'imageio_ffmpeg', 'colorlog', 'omegaconf',
        'flatbuffers', 'protobuf', 'win32', 'pywintypes', 'hf_xet',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VideoMindBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VideoMindBackend',
)
