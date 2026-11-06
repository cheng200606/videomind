"""以受控 VAD 分块启动 yueying：避免整段长音频一次性做 STFT 导致数百 MB 分配失败。

yueying 内部固定 `vad_filter=True`，但 faster-whisper 默认不限制单段语音长度；
28 分钟连续讲课会生成一个超长 chunk，`np.fft.rfft` 需要约 513 MB 的 float64 数组。
这里在子进程启动前把 VAD 单段上限压到 30 秒，与 Whisper 的 30 秒窗口一致。
"""

import sys

MAX_SPEECH_SECONDS = 30.0


def cap_vad_chunks(max_seconds: float = MAX_SPEECH_SECONDS) -> None:
    import faster_whisper.transcribe as ft
    import faster_whisper.vad as fv

    from faster_whisper.vad import VadOptions

    original = ft.get_speech_timestamps

    def capped(audio, vad_options=None, **kwargs):
        if vad_options is None:
            vad_options = VadOptions(max_speech_duration_s=max_seconds)
        elif getattr(vad_options, "max_speech_duration_s", 0) == float("inf"):
            vad_options.max_speech_duration_s = max_seconds
        return original(audio, vad_options, **kwargs)

    ft.get_speech_timestamps = capped
    fv.get_speech_timestamps = capped


def main() -> int:
    cap_vad_chunks()
    from yueying.cli import main as yueying_main

    return yueying_main()


if __name__ == "__main__":
    sys.exit(main())
