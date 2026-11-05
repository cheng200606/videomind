import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_WORK = _HERE / ".pytest_tmp"
_WORK.mkdir(exist_ok=True)

# 必须在导入 app.* 之前设置：Settings 是 lru_cache 的，先到先得
os.environ["DATABASE_URL"] = f"sqlite:///{(_WORK / 'test.db').as_posix()}"
os.environ["MEDIA_ROOT"] = (_WORK / "media").as_posix()
os.environ["CACHE_ROOT"] = (_WORK / "cache").as_posix()
os.environ["ASR_ENGINE"] = "mock"
os.environ["OCR_ENGINE"] = "none"
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["REDIS_URL"] = ""
os.environ["VMIND_FIXTURE_DIR"] = str(_HERE / "fixtures")

# 引擎设置会持久化到 data/settings.json 并在 lifespan 读回；先清掉上次运行残留，保证测试封闭
(_WORK / "settings.json").unlink(missing_ok=True)
# 测试库一次性：标签采纳/驳回会改 Tag.suggested_by_ai 并跨运行持久，残留会污染断言
(_WORK / "test.db").unlink(missing_ok=True)
