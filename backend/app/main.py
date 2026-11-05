from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import engines  # noqa: F401  导入即把引擎实现注册进 base 的注册表
from app.config import get_settings
from app.db import init_db
from app.routers import delivery, knowledge, parse

_settings = get_settings()

# 目录必须在挂载前存在，否则 /media 要等重启才生效
Path(_settings.media_root).mkdir(parents=True, exist_ok=True)
Path(_settings.cache_root).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
