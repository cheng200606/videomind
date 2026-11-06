"""yueying 0.2.1 适配器：manifest.json 的 segments/frames 解析。"""

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from app.engines import asr as asr_module
from app.engines.asr import MockAsr, YueyingAsr


def test_mock_uses_matching_fixture_only(tmp_path: Path, monkeypatch):
    (tmp_path / "my_video.json").write_text(json.dumps({
        "duration_ms": 2000,
        "segments": [{"index": 0, "start_ms": 0, "end_ms": 2000, "text": "真实样例内容"}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(asr_module, "FIXTURE_DIR", tmp_path)

    result = MockAsr().transcribe(str(tmp_path / "my_video.mp4"))
    assert [s.text for s in result.segments] == ["真实样例内容"]


def test_mock_matches_fixture_behind_upload_prefix(tmp_path: Path, monkeypatch):
    """上传落盘会加批次前缀，演示样例仍应按原文件名命中。"""
    (tmp_path / "lecture_transcript.json").write_text(json.dumps({
        "duration_ms": 1000,
        "segments": [{"index": 0, "start_ms": 0, "end_ms": 1000, "text": "样例命中"}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(asr_module, "FIXTURE_DIR", tmp_path)
    monkeypatch.delenv("VMIND_MOCK_ALLOW_FALLBACK", raising=False)

    result = MockAsr().transcribe(str(tmp_path / "3_lecture_transcript.mp4"))
    assert [s.text for s in result.segments] == ["样例命中"]


def test_mock_refuses_unknown_video_instead_of_fake_transcript(tmp_path: Path, monkeypatch):
    """回归：任意真实视频曾被 lecture_transcript.json（Vue3 样例）冒充。"""
    monkeypatch.setattr(asr_module, "FIXTURE_DIR", tmp_path)
    monkeypatch.delenv("VMIND_MOCK_ALLOW_FALLBACK", raising=False)

    with pytest.raises(RuntimeError) as err:
        MockAsr().transcribe(str(tmp_path / "UML-6时序图.mp4"))
    message = str(err.value)
    assert "不会读取真实视频" in message
    assert "whisper" in message


def test_mock_fallback_requires_explicit_test_switch(tmp_path: Path, monkeypatch):
    (tmp_path / "lecture_transcript.json").write_text(json.dumps({
        "duration_ms": 1000,
        "segments": [{"index": 0, "start_ms": 0, "end_ms": 1000, "text": "兜底样例"}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(asr_module, "FIXTURE_DIR", tmp_path)
    monkeypatch.setenv("VMIND_MOCK_ALLOW_FALLBACK", "1")

    result = MockAsr().transcribe(str(tmp_path / "anything.mp4"))
    assert [s.text for s in result.segments] == ["兜底样例"]

def test_yueying_parses_manifest(tmp_path: Path, monkeypatch):
    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        outdir = Path(cmd[cmd.index("--out") + 1])
        frame = outdir / "frames" / "f001.jpg"
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(b"fake-jpg")
        (outdir / "manifest.json").write_text(json.dumps({
            "duration": 12.5,
            "segments": [
                {"start": 0.0, "end": 6.0, "text": "第一段"},
                {"start": 6.0, "end": 12.5, "text": "第二段"},
            ],
            "frames": [{"time": 3.2, "file": str(frame)}],
        }, ensure_ascii=False), encoding="utf-8")
        return CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("app.engines.asr.subprocess.run", fake_run)
    result = YueyingAsr().transcribe("demo.mp4")
    assert result.duration_ms == 12500
    assert [s.text for s in result.segments] == ["第一段", "第二段"]
    assert result.segments[1].start_ms == 6000
    assert len(result.frames) == 1
    assert result.frames[0].ms == 3200
    assert result.frames[0].path.endswith("f001.jpg")


def test_yueying_error_uses_last_stderr_line(monkeypatch):
    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        return CompletedProcess(
            cmd, 1, stdout="",
            stderr="Traceback (most recent call last):\n  ...\n"
                   "numpy._core._exceptions._ArrayMemoryError: Unable to allocate 440. MiB")

    monkeypatch.setattr("app.engines.asr.subprocess.run", fake_run)
    with pytest.raises(RuntimeError) as err:
        YueyingAsr().transcribe("demo.mp4")
    assert "ArrayMemoryError" in str(err.value)
    assert "Traceback" not in str(err.value)
