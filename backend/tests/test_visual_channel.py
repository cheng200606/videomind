"""画面通道冒烟（v0.17 质量门 P0）。

为什么要单独一个文件：`tests/conftest.py` 把 `OCR_ENGINE` 固定成 `none`，全仓 108 例里
`visual_status` 只能是 SKIPPED，画面通道 → 代码块产物 → 证据帧这条链一次都没被走过。
conftest 那句「每次删 test.db」是一次性语义的红线，不能为跑这一条去改全局值，
所以这里用注册表加一个确定性替身引擎 + 独立的 Settings 实例，把整条链走到 done。

顺带回答交付文档线的问题：CODE_BLOCKS 到底由哪个通道产出。
"""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db import engine, init_db
from app.engines.base import FrameText, KeyFrame, register_ocr
from app.enums import ArtifactType, Channel, StageStatus, VideoStatus
from app.models import Evidence, KnowledgeItem, Video, VideoBatch
from app.pipeline import parse_video


@register_ocr("qa_stub")
class QaStubOcr:
    """确定性画面引擎替身：不走 onnxruntime，不下载权重，输出可预期。

    真实 RapidOcr 的连通性另行手工验证（本机 2.9s 检出 2 行文字），
    这里要锁的是「引擎 → 产物 → 证据」的接线，不是 OCR 识别率。
    """

    name = "qa_stub"

    @staticmethod
    def is_available() -> bool:
        return True

    def recognize(self, frames) -> list[FrameText]:
        out: list[FrameText] = []
        for frame in frames:
            for i in range(8):
                out.append(FrameText(ms=frame.ms, text=f"code line {i}", confidence=0.9))
        return out


def _synth_frame(tmp_path: Path) -> str:
    """造一张可读的真图片：_localize_frames 会检查存在性并复制进 media_root。"""
    p = tmp_path / "frame_0.png"
    im = Image.new("RGB", (320, 120), "white")
    ImageDraw.Draw(im).text((10, 40), "def locate_anchor(ms): return ms", fill="black")
    im.save(p)
    return str(p)


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()


@pytest.fixture()
def video(tmp_path: Path) -> Video:
    src = tmp_path / "vue3_lecture.mp4"
    src.write_bytes(b"\x00")
    with Session(engine) as session:
        batch = VideoBatch(name="画面通道冒烟", video_count=1)
        session.add(batch)
        session.commit()
        session.refresh(batch)
        v = Video(batch_id=batch.id, path=str(src))
        session.add(v)
        session.commit()
        session.refresh(v)
        return v


def test_visual_stage_reaches_done_and_emits_code_blocks(tmp_path, video: Video, monkeypatch):
    """画面通道开到 done 时：阶段状态、代码块产物、证据帧三者必须同时成立。

    monkeypatch 只替换「抽帧」这一步（测试视频是 32 字节假文件，av 解不出帧是预期的），
    引擎与产物策略全走真实代码路径。
    """
    frame_path = _synth_frame(tmp_path)
    monkeypatch.setattr("app.pipeline._keyframes", lambda v: [KeyFrame(ms=0, path=frame_path)])

    settings = get_settings().model_copy(update={"ocr_engine": "qa_stub"})
    assert isinstance(settings, Settings)

    with Session(engine) as session:
        parsed = parse_video(session, session.get(Video, video.id), settings)

        assert parsed.visual_status == StageStatus.DONE, "画面通道没有走到 done，冒烟没覆盖到目标状态"
        assert parsed.status == VideoStatus.SUCCEEDED

        items = session.exec(select(KnowledgeItem).where(
            KnowledgeItem.video_id == parsed.id)).all()
        code_blocks = [i for i in items if i.type == ArtifactType.CODE_BLOCKS]
        assert code_blocks, "画面通道产出文字后仍没有代码块产物"

        block = code_blocks[0]
        ev = session.get(Evidence, block.evidence_id)
        assert ev.channel == Channel.OCR, "代码块必须标成画面通道（看到的），不能冒充语音"
        assert ev.frame_path, "画面通道产出的证据必须带帧文件"
        assert ev.frame_path.startswith("/media/"), "帧路径要转成 /media URL，不能回显本机绝对路径"
        # 帧文件真的落到了 media_root/frames/{video_id}/ 下
        on_disk = Path(get_settings().media_root) / ev.frame_path[len("/media/"):]
        assert on_disk.exists(), f"证据里的帧路径指向不存在的文件：{ev.frame_path}"


def test_channel_both_is_unreachable_in_current_pipeline(video: Video, monkeypatch):
    """锁住一条实现事实：`Channel.BOTH` 目前是死值，任何解析都不会产出。

    出处 `app/artifacts.py:180`：`channel=Channel.ASR if seg else Channel.BOTH`，
    而 `seg = _nearest_segment(...)` 只在**没有任何转写段**时返回 None；
    那种情况下 `structure()` 返回的 draft.items 也是空的（无 Key 走 fallback_draft，
    空转写 → 0 items），于是 key_points 一条都不会产出，BOTH 分支永远进不去。
    前端 `EvidenceDrawer.vue:14` 却已经给了「语音 + 画面」的中文标签。

    这条一旦被修（例如真做 F5 交叉校验），本用例会失败——那时应当改成断言 BOTH 可达，
    而不是删掉它。
    """
    frame_path = _synth_frame(tmp_path=Path(get_settings().cache_root))
    monkeypatch.setattr("app.pipeline._keyframes", lambda v: [KeyFrame(ms=0, path=frame_path)])
    settings = get_settings().model_copy(update={"ocr_engine": "qa_stub"})

    with Session(engine) as session:
        parsed = parse_video(session, session.get(Video, video.id), settings)
        items = session.exec(select(KnowledgeItem).where(
            KnowledgeItem.video_id == parsed.id)).all()
        channels = {session.get(Evidence, i.evidence_id).channel for i in items}

    assert Channel.OCR in channels and Channel.ASR in channels
    assert Channel.BOTH not in channels, (
        "Channel.BOTH 现在可达了——说明 F5 或证据通道判定被改过，"
        "请把本用例改成正面覆盖，并同步 frontend/src/api/labels.ts"
    )
