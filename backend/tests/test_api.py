"""走 HTTP 的端到端集成测试：上传 → 四阶段解析 → 产物 → 检索 → 笔记 → 修订 → 导出。

TestClient 会在响应返回后同步执行 BackgroundTasks，所以不用轮询等待。
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_engine_settings_roundtrip(client: TestClient):
    current = client.get("/api/settings/engines").json()
    assert "mock" in current["asr"]["available"]
    assert "none" in current["ocr"]["available"]

    changed = client.put("/api/settings/engines", json={"output_schemas": ["summary", "uml_draft"]})
    assert changed.status_code == 200 and changed.json()["output_schemas"] == ["summary", "uml_draft"]
    client.put("/api/settings/engines",
               json={"output_schemas": ["summary", "uml_draft", "key_points", "code_blocks"]})

    assert client.put("/api/settings/engines", json={"asr": "不存在的引擎"}).status_code == 422


def test_full_slice_over_http(client: TestClient, tmp_path: Path):
    src = tmp_path / "vue3_lecture.mp4"
    src.write_bytes(b"\x00" * 32)

    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "集成测试批次"},
                        files=[("files", ("vue3_lecture.mp4", fh, "video/mp4"))])
    assert r.status_code == 201, r.text
    batch_id = r.json()["id"]

    batch = client.get(f"/api/batches/{batch_id}").json()
    assert batch["status"] == "succeeded", batch
    video = batch["videos"][0]
    assert video["stages"]["transcribe"] == "done"
    assert video["stages"]["visual"] == "skipped"      # OCR 关闭 → 降级，不是失败

    vid = video["id"]
    meta = client.get(f"/api/videos/{vid}").json()
    assert meta["duration_ms"] > 0 and meta["batch_id"] == batch_id

    assert len(client.get(f"/api/videos/{vid}/transcript").json()) == 13

    items = client.get(f"/api/videos/{vid}/items").json()
    kinds = {i["type"] for i in items}
    assert {"summary", "uml_draft", "key_points"} <= kinds
    assert all(i["evidence"] for i in items), "每条产物都必须带证据，否则 F1 溯源不成立"

    uml = next(i for i in items if i["type"] == "uml_draft")
    assert "flowchart TD" in uml["content"]
    assert uml["payload"]["elements"], "页 6 需要可点回证据的元素锚点"

    tags = client.get("/api/tags").json()
    assert tags, "AI 建议标签应已落库"
    assert isinstance(client.get("/api/search", params={"q": "ref"}).json(), list)
    assert isinstance(client.get("/api/search", params={"tag": tags[0]["id"]}).json(), list)

    item_id = next(i for i in items if i["type"] == "key_points")["id"]
    note = client.post(f"/api/items/{item_id}/notes", json={"content": "复习用", "anchor_ms": 12000})
    assert note.status_code == 201
    assert client.put(f"/api/notes/{note.json()['id']}",
                      json={"content": "改过了", "anchor_ms": 12000}).status_code == 200

    assert client.post(f"/api/items/{item_id}/revision", json={"state": "revised"}).status_code == 422
    assert client.post(f"/api/items/{item_id}/revision", json={"state": "pending_confirm"}).status_code == 200

    detail = client.get(f"/api/items/{item_id}").json()
    assert detail["revisions"][-1]["state"] == "pending_confirm"
    assert detail["notes"]

    exp = client.get(f"/api/batches/{batch_id}/export.md")
    assert exp.status_code == 200
    assert exp.headers["content-type"].startswith("text/markdown")
    assert "集成测试批次" in exp.text
    assert "识别结果仅供参考" in exp.text
    assert "```mermaid" in exp.text

    structured = client.get(f"/api/batches/{batch_id}/structured").json()
    assert structured["videos"] and structured["disclaimer"]


def test_missing_batch_is_404(client: TestClient):
    assert client.get("/api/batches/987654").status_code == 404
    assert client.get("/api/batches/987654/export.md").status_code == 404


def test_upload_reports_rejected_files(client: TestClient, tmp_path: Path):
    """非法后缀文件不再静默丢弃：响应要带回 rejected 清单，用户才知道哪个文件没进批次。"""
    src = tmp_path / "vue3_lecture.mp4"
    src.write_bytes(b"\x00" * 32)
    txt = tmp_path / "note.txt"
    txt.write_text("not a video", encoding="utf-8")
    with src.open("rb") as fh, txt.open("rb") as ft:
        r = client.post("/api/batches", data={"name": "拒绝反馈批次"},
                        files=[("files", ("vue3_lecture.mp4", fh, "video/mp4")),
                               ("files", ("note.txt", ft, "text/plain"))])
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["video_count"] == 1
    assert [x["filename"] for x in data["rejected"]] == ["note.txt"]
    assert "不支持的格式" in data["rejected"][0]["reason"]


def test_sse_progress_streams_terminal_state(client: TestClient, tmp_path: Path):
    """进度端点必须是真 SSE（text/event-stream）；订阅前批次已结束则立即推终态并收流，
    否则页面刷新重连后会永远 ping 空转。"""
    src = tmp_path / "vue3_lecture.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "SSE 终态批次"},
                        files=[("files", ("vue3_lecture.mp4", fh, "video/mp4"))])
    assert r.status_code == 201, r.text
    batch_id = r.json()["id"]

    with client.stream("GET", f"/api/batches/{batch_id}/progress") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream"), resp.headers
        body = b"".join(resp.iter_bytes()).decode("utf-8")

    events = [json.loads(line[len("data: "):]) for line in body.splitlines()
              if line.startswith("data: ")]
    assert events, "SSE 必须至少推一条事件，而不是只发 ping"
    last = events[-1]
    assert last["stage"] == "batch" and last["status"] == "succeeded"
    assert last["batch_id"] == batch_id
