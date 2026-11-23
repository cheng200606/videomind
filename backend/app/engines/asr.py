"""`AsrEngine` 的三个实现：yueying（主路径）、FunASR（备选）、Mock（跑通与出截图用）。"""

import importlib.util
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from app.engines.base import AsrResult, KeyFrame, TranscriptSegment, register_asr

FIXTURE_DIR = Path(os.environ.get("VMIND_FIXTURE_DIR", Path(__file__).resolve().parents[2] / "tests" / "fixtures"))


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False

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
    """演示引擎：只回放与视频同名的脱敏样例，绝不冒充真实视频的转写。"""

    name = "mock"

    @staticmethod
    def is_available() -> bool:
        return True

    def transcribe(self, video_path: str) -> AsrResult:
        stem = Path(video_path).stem
        candidates = [stem]
        # 上传落盘名带批次前缀（如 3_lecture_transcript.mp4）；演示样例按原文件名匹配
        prefix, _, rest = stem.partition("_")
        if rest and prefix.isdigit():
            candidates.append(rest)
        candidate = next((FIXTURE_DIR / f"{name}.json" for name in candidates
                          if (FIXTURE_DIR / f"{name}.json").exists()), None)
        if candidate is None:
            # 仅测试可用显式开关退回通用样例；生产环境宁可失败也不产出与视频无关的笔记
            if os.environ.get("VMIND_MOCK_ALLOW_FALLBACK") == "1":
                candidate = FIXTURE_DIR / "lecture_transcript.json"
            else:
                raise RuntimeError(
                    f"演示引擎 mock 没有「{stem}」的内置样例，不会读取真实视频内容。"
                    "请在设置页把 ASR 引擎切换为 whisper（本地真实转写）或 yueying；"
                    "源码环境需先安装 requirements-engines.txt。"
                )
        data = json.loads(candidate.read_text(encoding="utf-8"))
        segments = [
            TranscriptSegment(**{k: s.get(k, 0) for k in ("index", "start_ms", "end_ms", "text", "confidence")})
            for s in data["segments"]
        ]
        frames = [KeyFrame(ms=f["ms"], path=f["path"]) for f in data.get("frames", [])]
        return AsrResult(duration_ms=data.get("duration_ms", 0), segments=segments, frames=frames)


@register_asr("whisper")
class WhisperAsr:
    """本地真实转写：faster-whisper（CPU int8 / GPU）直接读视频音轨，无需外部 CLI。

    模型首次使用会下载到本机 HuggingFace 缓存；默认 tiny，可用 VMIND_WHISPER_MODEL 覆盖。
    """

    name = "whisper"
    _models: dict[tuple[str, str, str], object] = {}

    @property
    def cache_variant(self) -> str:
        """模型档位参与解析缓存键：tiny/base 不得命中彼此的缓存（v0.16）。"""
        return os.environ.get("VMIND_WHISPER_MODEL", "tiny")

    @staticmethod
    def is_available() -> bool:
        return _has_module("faster_whisper") and _has_module("av")

    def _load(self, size: str, device: str, compute_type: str):
        key = (size, device, compute_type)
        model = self._models.get(key)
        if model is None:
            from faster_whisper import WhisperModel

            model = WhisperModel(size, device=device, compute_type=compute_type)
            self._models[key] = model
        return model

    def transcribe(self, video_path: str) -> AsrResult:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except Exception as exc:
            raise RuntimeError(
                "本地 Whisper 引擎不可用：未安装 faster-whisper/av。"
                "源码环境请安装 requirements-engines.txt；桌面版请使用官方安装包。"
            ) from exc

        size = os.environ.get("VMIND_WHISPER_MODEL", "tiny")
        # 默认 CPU int8：桌面用户机器不一定装了 CUDA 运行库，GPU 失败会直接卡住真实解析
        device = os.environ.get("VMIND_WHISPER_DEVICE", "cpu")
        compute_type = os.environ.get("VMIND_WHISPER_COMPUTE", "int8")
        language = os.environ.get("VMIND_WHISPER_LANG") or None
        # VAD 需要 onnxruntime；v0.12 起桌面版随 RapidOCR 内置了它（实测与 ctranslate2
        # 无 OpenMP 同名冲突，打包烟雾已验证），VAD 会自动启用；缺运行时时静默关闭
        vad_filter = _has_module("onnxruntime")

        try:
            model = self._load(size, device, compute_type)
        except Exception as exc:
            if device in ("auto", "cuda"):
                device, compute_type = "cpu", "int8"
                model = self._load(size, device, compute_type)
            else:
                detail = str(exc).strip().splitlines()[-1][:300] if str(exc).strip() else type(exc).__name__
                raise RuntimeError(
                    f"本地 Whisper 模型「{size}」加载失败：{detail}。"
                    "首次使用需要联网下载模型；国内网络可设置 HF_ENDPOINT=https://hf-mirror.com。"
                ) from exc

        vad_parameters = None
        if vad_filter:
            # 长视频若整段做 STFT，28 分钟需要 500 MB 以上的临时数组；限制单段语音 30 秒
            from faster_whisper.vad import VadOptions

            vad_parameters = VadOptions(max_speech_duration_s=30)

        try:
            segments, info = model.transcribe(
                video_path, language=language, beam_size=5, vad_filter=vad_filter,
                vad_parameters=vad_parameters, condition_on_previous_text=False,
            )
        except Exception as exc:
            if device in ("auto", "cuda"):
                # GPU 推理缺少 cublas/cudnn 时退回 CPU，别让一条视频直接失败
                self._models.pop((size, device, compute_type), None)
                device, compute_type = "cpu", "int8"
                model = self._load(size, device, compute_type)
                segments, info = model.transcribe(
                    video_path, language=language, beam_size=5, vad_filter=vad_filter,
                    condition_on_previous_text=False,
                )
            else:
                detail = str(exc).strip().splitlines()[-1][:300] if str(exc).strip() else type(exc).__name__
                raise RuntimeError(f"本地 Whisper 转写失败：{detail}") from exc

        try:
            rows = [
                TranscriptSegment(
                    index=i,
                    start_ms=int(float(s.start) * 1000),
                    end_ms=int(float(s.end) * 1000),
                    text=(s.text or "").strip(),
                    confidence=max(0.0, min(1.0, float(getattr(s, "avg_logprob", 0.0) or 0.0))),
                )
                for i, s in enumerate(segments)
                if (s.text or "").strip()
            ]
        except Exception as exc:
            detail = str(exc).strip().splitlines()[-1][:300] if str(exc).strip() else type(exc).__name__
            raise RuntimeError(f"本地 Whisper 结果解析失败：{detail}") from exc

        return AsrResult(duration_ms=int(float(getattr(info, "duration", 0.0)) * 1000), segments=rows)


@register_asr("yueying")
class YueyingAsr:
    """★主路径：一次调用拿到带时间戳转写 + 关键帧 + contact sheet（离线免 API Key）。

    它不含 OCR（docs/交付与排期.md 风险 5），所以画面通道仍要走 ocr.py。
    它支持 B 站/YouTube URL，本项目只用本地文件入口——合规声明要求不留存不分发第三方内容。
    """

    name = "yueying"

    @staticmethod
    def is_available() -> bool:
        return _has_module("yueying")

    def transcribe(self, video_path: str) -> AsrResult:
        outdir = Path(tempfile.mkdtemp(prefix="yueying_"))
        if "{video}" in YUEYING_CLI_ARGS:
            args = _split_args(YUEYING_CLI_ARGS.format(video=video_path, outdir=str(outdir)))
        else:
            args = _split_args(YUEYING_CLI_ARGS.format(outdir=str(outdir)))
            args.append(video_path)
        # 走 compat 入口：给 VAD 单段长度设上限，长视频不再整段做 STFT
        cmd = [sys.executable, "-m", "app.engines.yueying_compat", *args]
        # yueying 输出 UTF-8；Windows 默认 GBK 解码会在 reader 线程里抛 UnicodeDecodeError
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
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

    @staticmethod
    def is_available() -> bool:
        return _has_module("funasr")

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
