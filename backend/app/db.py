from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()
_url = _settings.database_url

# 未配 MySQL 时退回 SQLite，让 W5 的切片在没有 Docker 的机器上也能直接跑
_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}
if _url.startswith("sqlite"):
    Path(_url.split("///")[-1]).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(_url, pool_pre_ping=True, connect_args=_connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
