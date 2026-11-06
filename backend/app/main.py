from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import engines  # noqa: F401  导入即把引擎实现注册进 base 的注册表
from app.config import get_settings
from app.db import engine, init_db
from app.model_config import active_model_config, reset_model_config_cache
from app.net import sanitize_proxy_env
from app.pipeline import recover_orphan_runs
from app.routers import delivery, knowledge, parse
from app.routers import settings as settings_router

sanitize_proxy_env()

_settings = get_settings()

# 目录必须在挂载前存在，否则 /media 要等重启才生效
Path(_settings.media_root).mkdir(parents=True, exist_ok=True)
Path(_settings.cache_root).mkdir(parents=True, exist_ok=True)


def _load_saved_settings() -> None:
    """读回上次运行保存的引擎设置（PUT /settings/engines 落盘的 data/settings.json），重启不丢。

    v0.7.1 迁移：旧版本把 mock 写成了默认值，导致真实视频被内置样例冒充。
    没有 schema_version 的旧文件若仍是 mock，一次性改成 auto（之后用户显式选择 mock 会保留）。
    """
    from app.engines.base import available_asr, available_ocr

    path = Path(_settings.media_root).parent / "settings.json"
    if not path.exists():
        return
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    changed = False
    if saved.get("schema_version") != 2:
        if saved.get("asr_engine") == "mock":
            saved["asr_engine"] = "auto"
        saved["schema_version"] = 2
        changed = True
    if saved.get("asr_engine") not in [*available_asr(), "auto"]:
        # 升级后引擎可能不再随包提供（例如桌面版未内置某重引擎）：回到 auto 由后端解析
        saved["asr_engine"] = "auto"
        changed = True
    if saved.get("ocr_engine") not in ["none", *available_ocr()]:
        # v0.7.0 桌面版设置页曾列出未打包的 rapid/paddle；选中后升级会 500，统一回退为 none
        saved["ocr_engine"] = "none"
        changed = True
    for attr in ("asr_engine", "ocr_engine"):
        if isinstance(saved.get(attr), str):
            setattr(_settings, attr, saved[attr])
    schemas = saved.get("output_schemas")
    if isinstance(schemas, str):
        names = [s.strip() for s in schemas.split(",") if s.strip()]
        if names:
            _settings.output_schemas = ",".join(names)
    if changed:
        try:
            path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_saved_settings()
    reset_model_config_cache()
    active_model_config()   # 启动时读回本机模型配置，Key 不落日志
    init_db()
    with Session(engine) as session:
        recover_orphan_runs(session)
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
app.include_router(settings_router.router)


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
        if full_path == "api" or full_path.startswith("api/"):
            # catch-all 兜的是前端历史路由；拼错/不存在的 /api 路径要回 404 JSON，
            # 回 index.html 会让调用方把 HTML 当响应体解析，掩盖真实错误
            raise HTTPException(404, "接口不存在：请检查请求路径")
        target = _spa / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(_spa / "index.html")
