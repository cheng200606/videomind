"""yueying 0.2.1 适配器：manifest.json 的 segments/frames 解析。"""

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from app.engines.asr import YueyingAsr

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
