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

# yueying 0.2.1 实际接口：--out 指定输出目录，--json 额外打印 manifest；
# 输出目录内 manifest.json 同时含 segments 与 frames（frames 为绝对路径）。
# 默认不放 {video}，避免路径里的空格被 shlex 拆开；兼容旧式含 {video} 的覆盖值。
YUEYING_CLI_ARGS = os.environ.get(
    "YUEYING_CLI_ARGS",
    "--json --out {outdir} --lang zh --model small --device auto",
)


def _split_args(raw: str) -> list[str]:
    """Windows 下必须 posix=False，否则反斜杠路径会被 shlex 当转义吃掉。"""
    return shlex.split(raw, posix=(os.name != "nt"))


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
        if "{video}" in YUEYING_CLI_ARGS:
            args = _split_args(YUEYING_CLI_ARGS.format(video=video_path, outdir=str(outdir)))
        else:
            args = _split_args(YUEYING_CLI_ARGS.format(outdir=str(outdir)))
            args.append(video_path)
        cmd = [sys.executable, "-m", "yueying", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            # 后台错误直接进 UI：优先给最后一行异常，而不是整段 traceback 的前 500 字
            raw = (proc.stderr or proc.stdout or "").strip()
            lines = [line for line in raw.splitlines() if line.strip()]
            detail = lines[-1] if lines else "未知错误"
            raise RuntimeError(f"yueying 解析失败：{detail[:500]}")

        manifest_path = outdir / "manifest.json"
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            # 兼容上游未来只打印 manifest、不落文件的情况：取 stdout 最后一个 JSON 对象
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip().startswith("{")]
            if not lines:
                raise RuntimeError("yueying 未产出 manifest.json，也没有可解析的 JSON 输出")
            payload = json.loads(lines[-1])

        segments = [
            TranscriptSegment(
                index=i,
                start_ms=int(float(seg["start"]) * 1000),
                end_ms=int(float(seg["end"]) * 1000),
                text=str(seg.get("text", "")),
                confidence=float(seg.get("confidence", 0.0)),
            )
            for i, seg in enumerate(payload.get("segments", []))
        ]
        frames = []
        for f in payload.get("frames", []):
            raw = f.get("file") or f.get("path") or ""
            frame_path = Path(raw)
            if raw and not frame_path.is_absolute():
                frame_path = outdir / frame_path
            frames.append(KeyFrame(ms=int(float(f.get("time", f.get("ms", 0))) * 1000), path=str(frame_path)))
        return AsrResult(
            duration_ms=int(float(payload.get("duration", 0)) * 1000),
            segments=segments,
            frames=frames,
        )


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
