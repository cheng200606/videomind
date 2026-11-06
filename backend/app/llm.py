"""DeepSeek 结构化层：同一份解析结果（StructuredDraft）供所有产物策略消费。

产物 schema 全部用 Pydantic 声明，把 model_json_schema() 塞进提示词 + response_format=json_object，
回来再用 model_validate 卡一遍——这是「可插拔产物」在代码里的落点：换策略=换一个 Pydantic 模型 + 一段提示词。
"""

import json
import re
import time

import httpx
from pydantic import BaseModel, Field

from app.enums import Confidence
from app.model_config import ModelConfig, active_model_config
from app.net import sanitize_proxy_env


class Chapter(BaseModel):
    title: str = Field(description="章节标题，不超过 20 字")
    start_ms: int
    end_ms: int
    gist: str = Field(default="", description="这一章讲了什么，一句话")


class DraftItem(BaseModel):
    title: str
    content: str = Field(description="结论正文，必须忠于原话，不补设定")
    confidence: Confidence = Confidence.INFERRED
    anchor_ms: int = Field(description="该结论在原片中的时间点")
    quote: str = Field(default="", description="支撑该结论的原话（证据溯源用）")
    pitfall: bool = Field(default=False, description="F3 易错点：讲师反复强调/纠错/演示错误写法")


class Conflict(BaseModel):
    """F2 教学一致性校验的产出，落 ConflictRecord。"""

    description: str
    source_a_ms: int = 0
    source_b_ms: int = 0


class StructuredDraft(BaseModel):
    one_line: str = Field(default="", description="整条视频的一句话结论")
    chapters: list[Chapter] = Field(default_factory=list)
    items: list[DraftItem] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, description="AI 建议标签，人工采纳或驳回")
    language: str = "python"


_SYSTEM = (
    "你是视频知识结构化助手。输入是一条知识/讲解类视频的带时间戳转写，以及画面 OCR 文本。"
    "只输出输入中出现过的信息，禁止补全未见过的内容；每条结论都要给 anchor_ms 与支撑原话 quote。"
    "识别结果仅供参考。"
)

_USER_TMPL = """【时长】{duration_s:.0f} 秒

【带时间戳转写】
{transcript}

【画面 OCR 文本（代码/板书）】
{ocr}

请产出：
1. one_line：一句话结论
2. chapters：按时间顺序切分章节，给起止毫秒
3. items：知识点条目，每条标 confidence——原话直接说出=explicit，需要归纳=inferred，OCR 或语音含糊=low；
   讲师反复强调、当场纠错、或演示了错误写法的，pitfall 置 true
4. conflicts：同一主题前后不一致之处（例如先讲用法 A 后改成用法 B、代码签名变了），给两处时间点
5. tags：3-6 个建议标签
"""


_SCHEMA = json.dumps(StructuredDraft.model_json_schema(), ensure_ascii=False)


def llm_ready() -> bool:
    return bool(active_model_config().api_key)


def _post_chat(messages: list[dict], cfg: ModelConfig, *, json_mode: bool = True,
               max_tokens: int = 4000, timeout: int = 180) -> str:
    sanitize_proxy_env()
    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}"}
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    if json_mode and resp.status_code in (400, 422):
        # 部分 OpenAI 兼容服务不支持 response_format；去掉 JSON mode 再试一次
        payload.pop("response_format", None)
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"].get("content") or "").strip()


def _chat(messages: list[dict], cfg: ModelConfig | None = None, **kwargs) -> str:
    return _post_chat(messages, cfg or active_model_config(), **kwargs)


def test_connection(cfg: ModelConfig | None = None) -> tuple[str, int]:
    """设置页“测试连接”：最小请求 + 返回耗时（毫秒）。"""
    cfg = cfg or active_model_config()
    start = time.perf_counter()
    text = _post_chat([{"role": "user", "content": "回复 OK"}], cfg,
                      json_mode=False, max_tokens=8, timeout=20)
    return text, int((time.perf_counter() - start) * 1000)


def _parse(text: str) -> StructuredDraft:
    """剥掉偶尔出现的 ```json 围栏，再用 Pydantic 卡字段类型。

    优先取全文任意位置的围栏块（不挑语言标记大小写、容错围栏前后的闲话）；
    没围栏时退回剥首尾标记——DeepSeek 偶尔会带「以下是结果：」之类的前缀。
    """
    body = text.strip()
    fenced = re.search(r"```(?:[a-zA-Z0-9_-]+)?\s*(.+?)\s*```", body, re.IGNORECASE | re.DOTALL)
    if fenced:
        body = fenced.group(1)
    else:
        body = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", body)
        body = re.sub(r"```\s*$", "", body)
    return StructuredDraft.model_validate(json.loads(body))


def structure(transcript: list[tuple[int, int, str]], ocr_text: list[tuple[int, str]],
              duration_ms: int) -> StructuredDraft:
    body = "\n".join(f"[{s / 1000:.1f}s-{e / 1000:.1f}s] {t}" for s, e, t in transcript)
    ocr_body = "\n".join(f"[{ms / 1000:.1f}s] {t}" for ms, t in ocr_text) or "（画面通道未启用或无文字）"

    if not llm_ready():
        return fallback_draft(transcript)

    cfg = active_model_config()
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _USER_TMPL.format(
            duration_s=duration_ms / 1000, transcript=body[:12000], ocr=ocr_body[:6000])},
        {"role": "user", "content": f"只输出一个 JSON 对象，不要解释、不要围栏。schema：\n{_SCHEMA}"},
    ]

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return _parse(_chat(messages, cfg, json_mode=True))
        except Exception as exc:
            last_error = exc
            messages = [*messages, {
                "role": "user",
                "content": f"上一次输出无法解析（{type(exc).__name__}: {exc}）。重新只输出合法 JSON。",
            }]
    raise RuntimeError(f"DeepSeek 结构化失败：{last_error}")


def fallback_draft(transcript: list[tuple[int, int, str]]) -> StructuredDraft:
    """无 Key / 断网时的规则兜底：按静音间隙切章、取长句为条目。

    宝贵的是切片不中断——答辩截图不能因为当天没网就出不了。
    """
    if not transcript:
        return StructuredDraft(one_line="（无转写内容）")
    chunks = [t for _, _, t in transcript]
    step = max(len(chunks) // 4, 1)
    chapters = [
        Chapter(title=f"片段 {i + 1}", start_ms=transcript[i * step][0],
                end_ms=transcript[min((i + 1) * step, len(transcript) - 1)][1],
                gist=chunks[i * step][:40])
        for i in range(min(4, len(chunks)))
    ]
    items = [
        DraftItem(title=t[:24], content=t, confidence=Confidence.EXPLICIT, anchor_ms=s, quote=t)
        for s, e, t in transcript[:12] if len(t) >= 12
    ]
    # 兜底没有可提炼的主题词，给一个说得通的通用标签；字面量「待标注」绑到条目上只会制造噪音
    tags = ["自动章节"] if not items else ["视频讲解"]
    return StructuredDraft(one_line=chunks[0][:60], chapters=chapters, items=items, tags=tags)
