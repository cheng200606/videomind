"""`AsrEngine` 的三个实现：yueying（主路径）、FunASR（备选）、Mock（跑通与出截图用）。"""

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from app.engines.base import AsrResult, KeyFrame, TranscriptSegment, register_asr

FIXTURE_DIR = Path(os.environ.get("VMIND_FIXTURE_DIR", Path(__file__).resolve().parents[2] / "tests" / "fixtures"))

# yueying 0.2.1 是 2026-09 新上传的单维护者包，接口未经本项目实测；
# 装好后按 `python -m yueying --help` 校准这一个常量即可，其余代码不动。
YUEYING_CLI_ARGS = os.environ.get("YUEYING_CLI_ARGS", "--json {video} --frames-dir {outdir}/frames")


@register_asr("mock")
class MockAsr:
    """不装任何引擎也能把整条切片跑通：读脱敏样例转写。"""

    name = "mock"

    def transcribe(self, video_path: str) -> AsrResult:
        stem = Path(video_path).stem
        candidate = FIXTURE_DIR / f"{stem}.json"
        if not candidate.exists():
            candidate = FIXTURE_DIR / "lecture_transcript.json"
        data = json.loads(candidate.read_text(encoding="utf-8"))
        segments = [
            TranscriptSegment(**{k: s.get(k, 0) for k in ("index", "start_ms", "end_ms", "text", "confidence")})
            for s in data["segments"]
        ]
        frames = [KeyFrame(ms=f["ms"], path=f["path"]) for f in data.get("frames", [])]
        return AsrResult(duration_ms=data.get("duration_ms", 0), segments=segments, frames=frames)


@register_asr("yueying")
class YueyingAsr:
    """★主路径：一次调用拿到带时间戳转写 + 关键帧 + contact sheet（离线免 API Key）。

    它不含 OCR（docs/交付与排期.md 风险 5），所以画面通道仍要走 ocr.py。
    它支持 B 站/YouTube URL，本项目只用本地文件入口——合规声明要求不留存不分发第三方内容。
    """

    name = "yueying"

    def transcribe(self, video_path: str) -> AsrResult:
        outdir = Path(tempfile.mkdtemp(prefix="yueying_"))
        cmd = [sys.executable, "-m", "yueying", *YUEYING_CLI_ARGS.format(video=video_path, outdir=outdir).split()]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            raise RuntimeError(f"yueying 解析失败：{proc.stderr.strip()[:500] or proc.stdout.strip()[:500]}")

        payload = json.loads((outdir / "transcript.json").read_text(encoding="utf-8"))
        segments = [
            TranscriptSegment(
                index=i,
                start_ms=int(seg["start"] * 1000),
                end_ms=int(seg["end"] * 1000),
                text=seg["text"],
                confidence=float(seg.get("confidence", 0.0)),
            )
            for i, seg in enumerate(payload["segments"])
        ]
        frames = [
            KeyFrame(ms=int(f.get("time", f.get("ms", 0)) * 1000), path=str(outdir / f["path"]))
            for f in payload.get("keyframes", [])
        ]
        return AsrResult(duration_ms=int(payload.get("duration", 0) * 1000), segments=segments, frames=frames)


@register_asr("funasr")
class FunAsr:
    """备选：paraformer-zh，字/句级时间戳，权重走 ModelScope（不撞风险 #9 的 HF 外网）。"""

    name = "funasr"
    _model = None

    def _load(self):
        if FunAsr._model is None:
            from funasr import AutoModel

            FunAsr._model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc")
        return FunAsr._model

    def transcribe(self, video_path: str) -> AsrResult:
        res = self._load().generate(input=video_path)
        item = res[0]
        sentences = item.get("sentence_info") or []
        segments = [
            TranscriptSegment(
                index=s.get("idx", i),
                start_ms=int(s.get("start", 0)),
                end_ms=int(s.get("end", 0)),
                text=s.get("text", ""),
                confidence=float(s.get("confidence", 0.0)),
            )
            for i, s in enumerate(sentences)
        ]
        return AsrResult(duration_ms=int(item.get("end", 0)), segments=segments)
