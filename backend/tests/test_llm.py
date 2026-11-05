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
