import os
import shutil
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
# 测试用任意文件名频繁造视频；显式允许 mock 退回通用样例。生产环境没有这个开关。
os.environ["VMIND_MOCK_ALLOW_FALLBACK"] = "1"
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["REDIS_URL"] = ""
os.environ["VMIND_FIXTURE_DIR"] = str(_HERE / "fixtures")

# 引擎设置会持久化到 data/settings.json 并在 lifespan 读回；先清掉上次运行残留，保证测试封闭
(_WORK / "settings.json").unlink(missing_ok=True)
# 自定义模型配置同理；Key 不能跨测试残留
(_WORK / "model_settings.json").unlink(missing_ok=True)
# 测试库一次性：标签采纳/驳回会改 Tag.suggested_by_ai 并跨运行持久，残留会污染断言
(_WORK / "test.db").unlink(missing_ok=True)
# 媒体与缓存目录同样一次性（v0.17 P0-5）：缓存键是内容寻址的，各测试的视频内容高度相似
# （多为 1 字节桩文件），跨运行残留的转写/帧缓存会让「该重抽却命中旧缓存」的用例假通过或
# 假失败；关键帧又按 video.id 落盘，而 test.db 删掉后 SQLite 主键会复用，残留帧会串到新视频上。
for _dir in ("media", "cache"):
    shutil.rmtree(_WORK / _dir, ignore_errors=True)

