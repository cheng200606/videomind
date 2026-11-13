"""LLM 结构化层单测：围栏解析容错与无 Key 兜底（不联网、不依赖引擎）。"""

import json

import pytest

from app.llm import _parse, fallback_draft, llm_ready


def _draft_json(**over) -> str:
    body = {"one_line": "一句话结论", "chapters": [], "items": [], "conflicts": [], "tags": ["t1"]}
    body.update(over)
    return json.dumps(body, ensure_ascii=False)


def test_parse_accepts_plain_json():
    assert _parse(_draft_json()).one_line == "一句话结论"


def test_parse_strips_fences_case_insensitive():
    for fence in ("```json", "```JSON", "```Json"):
        assert _parse(f"{fence}\n{_draft_json()}\n```").one_line == "一句话结论", fence


def test_parse_tolerates_text_around_fence():
    text = f"好的，以下是结构化结果：\n```json\n{_draft_json()}\n```\n以上就是全部内容。"
    assert _parse(text).tags == ["t1"]


def test_parse_rejects_garbage():
    with pytest.raises(Exception):
        _parse("这不是一段 JSON")


def test_fallback_draft_shapes_without_key():
    transcript = [
        (0, 4000, "第一句比较长的话讲生命周期"),
        (4000, 8000, "短句"),
        (8000, 12000, "第三句也不短讲 ref 响应式原理"),
    ]
    draft = fallback_draft(transcript)
    assert draft.chapters, "fallback 也要切出章节，切片不能中断"
    assert draft.items, "长句应被选为条目"
    assert all(i.confidence.value == "explicit" for i in draft.items)
    assert draft.tags == ["视频讲解"], "兜底标签名应可读，不该把「待标注」原样绑到条目上"


def test_no_key_in_test_env():
    """conftest 清空了 DEEPSEEK_API_KEY，结构化必须走 fallback 而不是真调外网。"""
    assert llm_ready() is False


def test_structure_chunks_long_transcript(monkeypatch):
    """长转写按段边界分块逐段调用：全部内容参与结构化，合并后跨块产物齐全。"""
    from app import llm

    calls: list[str] = []
    progress_calls: list[tuple[int, int]] = []

    def fake_chat(messages, cfg=None, **kw):
        prompt = messages[1]["content"]
        if "收尾" in prompt:   # 多块合并后的收尾调用
            return json.dumps({"one_line": "全局结论", "tags": ["t0", "t1", "t2"]}, ensure_ascii=False)
        idx = int(prompt.split("第 ")[1].split("/")[0]) - 1 if "第 " in prompt else 0
        calls.append(prompt)
        return _draft_json(one_line=f"结论{idx}", tags=[f"t{idx}"],
                           items=[{"title": f"条目{idx}", "content": f"内容{idx}",
                                   "anchor_ms": idx * 1000, "quote": f"原话{idx}"}])

    monkeypatch.setattr(llm, "llm_ready", lambda: True)
    monkeypatch.setattr(llm, "_chat", fake_chat)

    seg_text = "这是一个很长的句子用来撑字符数。" * 60   # 约 960 字符/段
    transcript = [(i * 1000, (i + 1) * 1000, seg_text) for i in range(30)]
    report: dict = {}
    draft = llm.structure(transcript, [], 30000, report=report,
                          progress=lambda i, n: progress_calls.append((i, n)))
    assert report["chunk_count"] == 3, "30 段 × ~960 字符应切成 3 块（每块上限 12000）"
    assert report["transcript_truncated"] is False, "段边界分块不该有物理截断"
    assert report["failed_chunks"] == []
    assert len(calls) == 3
    assert progress_calls == [(1, 3), (2, 3), (3, 3)]
    assert [item.title for item in draft.items] == ["条目0", "条目1", "条目2"], "三块的条目都要在"
    assert draft.tags == ["t0", "t1", "t2"], "收尾标签与合并标签去重后齐全"
    assert draft.one_line == "全局结论"

    short_report: dict = {}
    llm.structure(transcript[:2], [], 2000, report=short_report)
    assert short_report["chunk_count"] == 1
    assert short_report["transcript_truncated"] is False


def test_structure_single_huge_segment_truncates(monkeypatch):
    """单个段自身超过 12000 字符：该块物理截断，report 必须带回截断事实并写入提示词。"""
    from app import llm

    seen: dict = {}

    def fake_chat(messages, cfg=None, **kw):
        seen["prompt"] = messages[1]["content"]
        return _draft_json()

    monkeypatch.setattr(llm, "llm_ready", lambda: True)
    monkeypatch.setattr(llm, "_chat", fake_chat)

    transcript = [(0, 1000, "超长单段。" * 3000)]   # 约 15000 字符
    report: dict = {}
    draft = llm.structure(transcript, [], 1000, report=report)
    assert draft.one_line == "一句话结论"
    assert report["chunk_count"] == 1
    assert report["transcript_truncated"] is True
    assert report["transcript_chars"] > 12000
    assert "本段转写超过长度上限" in seen["prompt"]


def test_structure_tolerates_partial_chunk_failure(monkeypatch):
    """个别块失败不拖垮整条：report 记 failed_chunks，成功块的产物照常合并。"""
    from app import llm

    def fake_chat(messages, cfg=None, **kw):
        prompt = messages[1]["content"]
        if "第 2/" in prompt:
            raise RuntimeError("DeepSeek 结构化失败：boom")
        idx = int(prompt.split("第 ")[1].split("/")[0]) - 1 if "第 " in prompt else 0
        return _draft_json(items=[{"title": f"条目{idx}", "content": "c",
                                   "anchor_ms": idx, "quote": "q"}])

    monkeypatch.setattr(llm, "llm_ready", lambda: True)
    monkeypatch.setattr(llm, "_chat", fake_chat)

    seg_text = "这是一个很长的句子用来撑字符数。" * 60
    transcript = [(i * 1000, (i + 1) * 1000, seg_text) for i in range(30)]
    report: dict = {}
    draft = llm.structure(transcript, [], 30000, report=report)
    assert report["failed_chunks"] == [2]
    assert [item.title for item in draft.items] == ["条目0", "条目2"]


def test_structure_raises_when_all_chunks_fail(monkeypatch):
    from app import llm

    monkeypatch.setattr(llm, "llm_ready", lambda: True)
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        llm.structure([(0, 1000, "一句话")], [], 1000, report={})


def test_structure_refines_summary_for_chunks(monkeypatch):
    """多块合并后用收尾调用补全局 one_line 与 tags；收尾失败保持合并结果。"""
    from app import llm

    def fake_chat(messages, cfg=None, **kw):
        if "收尾" in messages[1]["content"]:
            return json.dumps({"one_line": "全局结论", "tags": ["全局", "t0"]}, ensure_ascii=False)
        return _draft_json(one_line="局部", tags=["t0"])

    monkeypatch.setattr(llm, "llm_ready", lambda: True)
    monkeypatch.setattr(llm, "_chat", fake_chat)

    seg_text = "这是一个很长的句子用来撑字符数。" * 60
    transcript = [(i * 1000, (i + 1) * 1000, seg_text) for i in range(30)]
    draft = llm.structure(transcript, [], 30000)
    assert draft.one_line == "全局结论"
    assert draft.tags == ["全局", "t0"], "收尾标签生效且与合并标签去重"


def test_allocate_ocr_by_time():
    """画面文字按时间归属到对应块，不重复计费。"""
    from app.llm import _allocate_ocr, _chunk_transcript

    transcript = [(0, 1000, "a" * 6000), (1000, 2000, "b" * 6000), (2000, 3000, "c" * 6000)]
    chunks = _chunk_transcript(transcript)
    assert len(chunks) == 3
    ocr = [(300, "第一块的字"), (1500, "第二块的字"), (9999, "最后一块的字")]
    parts = _allocate_ocr(ocr, chunks)
    assert [[t for _, t in p] for p in parts] == [["第一块的字"], ["第二块的字"], ["最后一块的字"]]


def test_structure_salvages_truncated_output(monkeypatch):
    """v0.15 实测修复：输出在 max_tokens 处截断时，抢救已完整条目并如实上报。"""
    from app import llm

    good = json.dumps({
        "one_line": "一句话结论", "chapters": [], "tags": ["t1"],
        "items": [
            {"title": "条目一", "content": "内容一", "anchor_ms": 0, "quote": "q1"},
            {"title": "条目二", "content": "内容二", "anchor_ms": 1, "quote": "q2"},
        ]})
    truncated = good[:-40] + '"content": "被截'   # 第三条写一半被上限切断
    caps = []

    def fake_chat(messages, cfg=None, **kw):
        caps.append(kw.get("max_tokens"))
        return truncated

    monkeypatch.setattr(llm, "llm_ready", lambda: True)
    monkeypatch.setattr(llm, "_chat", fake_chat)
    report: dict = {}
    draft = llm.structure([(0, 1000, "一句话")], [], 1000, report=report)
    assert [i.title for i in draft.items] == ["条目一"], "只保留截断前完整的条目"
    assert draft.tags == ["t1"]
    assert report["output_salvaged"] is True
    assert all(c == llm._MAX_TOKENS_STRUCTURE for c in caps), "结构化调用必须用调高后的输出上限"


def test_structure_retry_message_warns_about_truncation(monkeypatch):
    """彻底无法解析时，重试消息要提示精简输出，而不是原样重发同样的请求。"""
    from app import llm

    seen_last: list[str] = []

    def fake_chat(messages, cfg=None, **kw):
        seen_last.append(messages[-1]["content"])
        return "这不是 JSON"

    monkeypatch.setattr(llm, "llm_ready", lambda: True)
    monkeypatch.setattr(llm, "_chat", fake_chat)
    with pytest.raises(RuntimeError):
        llm.structure([(0, 1000, "一句话")], [], 1000, report={})
    assert any("截断" in m and "精简" in m for m in seen_last)


def test_structure_rebases_chunk_anchors_to_absolute(monkeypatch):
    """v0.15：分块输入时间归零，模型输出相对锚点，合并时由代码回移为绝对时间。"""
    from app import llm

    def fake_chat(messages, cfg=None, **kw):
        prompt = messages[1]["content"]
        if "收尾" in prompt:
            return json.dumps({"one_line": "全局", "tags": ["t"]}, ensure_ascii=False)
        idx = int(prompt.split("第 ")[1].split("/")[0]) - 1 if "第 " in prompt else 0
        return _draft_json(
            items=[{"title": f"条目{idx}a", "content": "c", "anchor_ms": 0, "quote": "q"},
                   {"title": f"条目{idx}b", "content": "c", "anchor_ms": 5000, "quote": "q"}],
            chapters=[{"title": f"章{idx}", "start_ms": 0, "end_ms": 11000, "gist": ""}])

    monkeypatch.setattr(llm, "llm_ready", lambda: True)
    monkeypatch.setattr(llm, "_chat", fake_chat)

    transcript = [(i * 1000, (i + 1) * 1000, "字" * 900) for i in range(30)]
    draft = llm.structure(transcript, [], 30000)

    spans = [(c[0][0], c[-1][1]) for c in llm._chunk_transcript(transcript)]
    for k, (span_start, span_end) in enumerate(spans):
        pair = draft.items[k * 2:k * 2 + 2]
        expect_second = min(span_start + 5000, span_end)   # 末块溢出会被夹取到 span_end
        assert [i.anchor_ms for i in pair] == [span_start, expect_second]
        assert span_start <= draft.chapters[k].start_ms < draft.chapters[k].end_ms <= span_end
    assert all(0 <= i.anchor_ms <= 30000 for i in draft.items), "回移后必须落在整条视频范围内"
