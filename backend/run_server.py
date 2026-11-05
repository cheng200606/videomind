"""桌面版后端入口：先定环境再导入 app（Settings 是 lru_cache 单例，先到先得）。

Electron 主进程通过环境变量传入 VMIND_PORT / VMIND_DATA_DIR；独立双击运行时
用默认端口 8765 与（打包态）%APPDATA%/VideoMind/data。
"""

import os
import sys
from pathlib import Path


def _prepare() -> None:
    os.environ.setdefault("VMIND_PORT", "8765")
    data_dir = os.environ.get("VMIND_DATA_DIR")
    if not data_dir:
        if getattr(sys, "frozen", False):  # PyInstaller 打包态：数据放用户目录，别写进安装目录
            data_dir = str(Path(os.environ.get("APPDATA", Path.home())) / "VideoMind" / "data")
        else:
            data_dir = str(Path(__file__).resolve().parent / "data")
    os.environ.setdefault("VMIND_DATA_DIR", data_dir)
    Path(data_dir).mkdir(parents=True, exist_ok=True)

    os.environ.setdefault(
        "DATABASE_URL", f"sqlite:///{(Path(data_dir) / 'videomind.db').as_posix()}")
    os.environ.setdefault("MEDIA_ROOT", str(Path(data_dir) / "media"))
    os.environ.setdefault("CACHE_ROOT", str(Path(data_dir) / "cache"))
    os.environ.setdefault("REDIS_URL", "")
    os.environ.setdefault("ASR_ENGINE", "mock")
    os.environ.setdefault("OCR_ENGINE", "none")

    # MockAsr 的脱敏样例转写：打包后取 _MEIPASS/app_fixtures，源码运行取 tests/fixtures
    if getattr(sys, "frozen", False):
        bundled = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "app_fixtures"
        if bundled.exists():
            os.environ.setdefault("VMIND_FIXTURE_DIR", str(bundled))

    print(f"[VideoMind] backend on http://127.0.0.1:{os.environ['VMIND_PORT']}  data={data_dir}", flush=True)


_prepare()

import uvicorn  # noqa: E402
from app.main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=int(os.environ["VMIND_PORT"]), log_level="warning")
