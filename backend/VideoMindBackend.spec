# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_server.py'],
    pathex=['.'],
    binaries=[],
    datas=[('tests/fixtures', 'app_fixtures'), ('../frontend/dist', 'frontend_dist')],
    hiddenimports=['uvicorn', 'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 桌面版按交付设计只内置 mock ASR / OCR none；真实引擎是源码环境的可选依赖，
    # 不能让 PyInstaller 把 rapidocr/onnxruntime/yueying 等整条重依赖链塞进安装包。
    excludes=[
        'yueying', 'faster_whisper', 'ctranslate2', 'av', 'tokenizers', 'huggingface_hub', 'hf_xet',
        'rapidocr', 'onnxruntime', 'cv2', 'numpy', 'scipy', 'shapely', 'pyclipper', 'PIL', 'imagehash',
        'funasr', 'torch', 'torchaudio', 'paddle', 'paddleocr', 'paddlepaddle',
        'mcp', 'mcp_types', 'httpx2', 'httpcore2', 'cryptography', 'pyjwt', 'jsonschema',
        'yt_dlp', 'imageio_ffmpeg', 'requests', 'tqdm', 'colorlog', 'omegaconf', 'fsspec',
        'filelock', 'flatbuffers', 'protobuf', 'win32', 'pywintypes',
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
