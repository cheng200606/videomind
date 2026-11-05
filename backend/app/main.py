from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import engines  # noqa: F401  导入即把引擎实现注册进 base 的注册表
from app.config import get_settings
from app.db import init_db
from app.routers import delivery, knowledge, parse

_settings = get_settings()

# 目录必须在挂载前存在，否则 /media 要等重启才生效
Path(_settings.media_root).mkdir(parents=True, exist_ok=True)
Path(_settings.cache_root).mkdir(parents=True, exist_ok=True)


def _load_saved_settings() -> None:
    """读回上次运行保存的引擎设置（PUT /settings/engines 落盘的 data/settings.json），重启不丢。"""
    path = Path(_settings.media_root).parent / "settings.json"
    if not path.exists():
        return
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    for attr in ("asr_engine", "ocr_engine", "output_schemas"):
        if isinstance(saved.get(attr), str):
            setattr(_settings, attr, saved[attr])


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_saved_settings()
    init_db()
    yield


app = FastAPI(
    title="VideoMind 视析 API",
    version="0.1.0",
    description="知识/讲解类视频批量结构化 · 垂直切片。所有识别结果仅供参考。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=_settings.media_root), name="media")

app.include_router(parse.router)
app.include_router(knowledge.router)
app.include_router(delivery.router)


@app.get("/api/health")
def health():
    return {"ok": True, "asr": _settings.asr_engine, "ocr": _settings.ocr_engine}


# 桌面版（PyInstaller）把前端 dist 打进包里同源服务，源码开发时本地 npm run build 后也可直连。
# 必须注册在所有 /api 路由之后：前端历史路由（/videos/3 等）回落 index.html。
def _spa_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "frontend_dist"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


_spa = _spa_root()
if _spa.is_dir() and (_spa / "index.html").exists():

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str = ""):
        target = _spa / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(_spa / "index.html")
