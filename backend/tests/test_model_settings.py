"""设置页自定义模型配置：保存/掩码/清除/校验/连接测试/LLM 使用运行时配置。"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.llm import fallback_draft, llm_ready, structure
from app.main import app
from app.model_config import active_model_config, reset_model_config_cache
from app.net import sanitize_proxy_env


@pytest.fixture(autouse=True)
def clean_model_file():
    path = Path(get_settings().media_root).parent / "model_settings.json"
    path.unlink(missing_ok=True)
    reset_model_config_cache()
    yield
    path.unlink(missing_ok=True)
    reset_model_config_cache()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _save_custom(client: TestClient):
    return client.put("/api/settings/model", json={
        "provider": "custom",
        "base_url": "http://127.0.0.1:8010/v1",
        "model": "mock-model",
        "api_key": "sk-local-test",
    })


def test_initial_settings_do_not_expose_key(client: TestClient):
    data = client.get("/api/settings/model").json()
    assert data["has_key"] is False
    assert data["source"] == "default"
    assert "api_key" not in data


def test_save_keep_and_clear_key(client: TestClient):
    saved = _save_custom(client)
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data["has_key"] is True
    assert data["source"] == "saved"
    assert "sk-local-test" not in saved.text
    assert data["provider"] == "custom"
    assert data["base_url"] == "http://127.0.0.1:8010/v1"

    # 不传 api_key 时保留原 Key
    kept = client.put("/api/settings/model", json={
        "provider": "custom", "base_url": "http://127.0.0.1:8010/v1", "model": "mock-model-2",
    }).json()
    assert kept["has_key"] is True
    assert kept["model"] == "mock-model-2"

    cleared = client.put("/api/settings/model", json={
        "provider": "custom", "base_url": "http://127.0.0.1:8010/v1",
        "model": "mock-model-2", "clear_api_key": True,
    }).json()
    assert cleared["has_key"] is False


def test_model_file_persists_without_plain_key_in_api(client: TestClient):
    _save_custom(client)
    path = Path(get_settings().media_root).parent / "model_settings.json"
    assert path.exists()
    assert "sk-local-test" in path.read_text(encoding="utf-8")
    reset_model_config_cache()
    cfg = active_model_config()
    assert cfg.api_key == "sk-local-test"
    assert cfg.source == "saved"
    assert "sk-local-test" not in client.get("/api/settings/model").text


@pytest.mark.parametrize("body", [
    {"provider": "unknown", "base_url": "https://example.com/v1", "model": "m"},
    {"provider": "custom", "base_url": "not-a-url", "model": "m"},
    {"provider": "custom", "base_url": "http://example.com/v1", "model": "m"},
    {"provider": "custom", "base_url": "https://example.com/v1", "model": "  "},
])
def test_invalid_model_settings_are_422(client: TestClient, body):
    assert client.put("/api/settings/model", json=body).status_code == 422


def test_localhost_http_is_allowed(client: TestClient):
    assert _save_custom(client).status_code == 200


def test_test_connection_success_and_redaction(client: TestClient, monkeypatch):
    _save_custom(client)
    monkeypatch.setattr("app.routers.settings.test_connection", lambda cfg: ("OK", 12))
    ok = client.post("/api/settings/model/test")
    assert ok.status_code == 200 and ok.json()["ok"] is True
    assert ok.json()["latency_ms"] == 12

    def boom(cfg):
        raise RuntimeError("401 for Bearer sk-local-test")

    monkeypatch.setattr("app.routers.settings.test_connection", boom)
    bad = client.post("/api/settings/model/test")
    assert bad.status_code == 200 and bad.json()["ok"] is False
    assert "sk-local-test" not in bad.text
    assert "***" in bad.json()["error"]


def test_test_connection_requires_key(client: TestClient):
    assert client.post("/api/settings/model/test").status_code == 422


def test_llm_uses_saved_custom_config(client: TestClient, monkeypatch):
    _save_custom(client)
    captured: list[dict] = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"one_line": "ok"})}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("app.llm.httpx.post", fake_post)
    draft = structure([(0, 1000, "测试转写内容足够长，用于结构化")], [], 1000)
    assert draft.one_line == "ok"
    assert captured
    assert captured[0]["url"] == "http://127.0.0.1:8010/v1/chat/completions"
    assert captured[0]["json"]["model"] == "mock-model"
    assert captured[0]["headers"]["Authorization"] == "Bearer sk-local-test"


def test_llm_json_mode_falls_back_on_unsupported_provider(client: TestClient, monkeypatch):
    _save_custom(client)
    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, status, content=None):
            self.status_code = status
            self._content = content

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(self._content or {})}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json.copy())
        if len(calls) == 1:
            return FakeResponse(400)
        return FakeResponse(200, {"one_line": "fallback-ok"})

    monkeypatch.setattr("app.llm.httpx.post", fake_post)
    draft = structure([(0, 1000, "测试转写内容足够长，用于结构化")], [], 1000)
    assert draft.one_line == "fallback-ok"
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


def test_without_key_uses_rule_fallback(client: TestClient):
    assert llm_ready() is False
    draft = fallback_draft([(0, 1000, "这是一条足够长的转写内容，用于规则兜底")])
    assert draft.chapters
    assert draft.items


def test_sanitize_proxy_env_removes_ipv6_brackets(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,[::1],127.0.0.1")
    sanitize_proxy_env()
    assert os.environ["NO_PROXY"] == "localhost,::1,127.0.0.1"
