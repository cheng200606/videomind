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


def test_upload_all_rejected_is_422(client: TestClient, tmp_path: Path):
    """所有文件都被拒时不落空批次：422 并带回每个文件的原因。"""
    txt = tmp_path / "note.txt"
    txt.write_text("not a video", encoding="utf-8")
    with txt.open("rb") as ft:
        r = client.post("/api/batches", data={"name": "全拒批次"},
                        files=[("files", ("note.txt", ft, "text/plain"))])
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "没有可解析的视频" in detail and "note.txt" in detail


def test_tag_bind_adopt_and_dismiss(client: TestClient, tmp_path: Path):
    """B5 人机协同：AI 建议标签再绑一次=采纳（转人工确认），驳回=解除绑定。"""
    src = tmp_path / "vue3_lecture.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "标签语义批次"},
                        files=[("files", ("vue3_lecture.mp4", fh, "video/mp4"))])
    vid = client.get(f"/api/batches/{r.json()['id']}").json()["videos"][0]["id"]

    params = {"target_type": "video", "target_id": vid}
    bound = [t for t in client.get("/api/tags", params=params).json() if t["bound"]]
    assert bound, "解析落库的视频级标签应绑定当前视频"
    assert all(t["suggested_by_ai"] for t in bound), "未人工确认前都是 AI 建议"

    adopted = client.post("/api/tags/bind",
                          json={"name": bound[0]["name"], "target_type": "video", "target_id": vid})
    assert adopted.status_code == 201
    after = {t["id"]: t for t in client.get("/api/tags", params=params).json()}
    assert after[bound[0]["id"]]["suggested_by_ai"] is False, "采纳后不再以「建议」身份示人"
    assert after[bound[0]["id"]]["bound"] is True, "采纳不解除绑定"

    assert client.post(f"/api/tags/{bound[0]['id']}/dismiss", params=params).status_code == 200
    after2 = {t["id"]: t for t in client.get("/api/tags", params=params).json()}
    assert after2[bound[0]["id"]]["bound"] is False, "驳回应解除绑定"


def test_reparse_batch_is_idempotent_over_http(client: TestClient, tmp_path: Path):
    """整批重跑走 HTTP 后台任务后条目数不翻倍（配套 pipeline 幂等修复）。"""
    src = tmp_path / "vue3_lecture.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "重跑幂等批次"},
                        files=[("files", ("vue3_lecture.mp4", fh, "video/mp4"))])
    batch_id = r.json()["id"]
    vid = client.get(f"/api/batches/{batch_id}").json()["videos"][0]["id"]
    items_first = len(client.get(f"/api/videos/{vid}/items").json())

    assert client.post(f"/api/batches/{batch_id}/parse").status_code == 200
    # TestClient 会在响应返回后同步执行 BackgroundTasks，无需轮询
    assert client.get(f"/api/batches/{batch_id}").json()["status"] == "succeeded"
    assert len(client.get(f"/api/videos/{vid}/items").json()) == items_first


def test_search_confidence_filter(client: TestClient):
    """F4 置信度过滤：合法值返回列表，非法值 422。"""
    assert isinstance(client.get("/api/search", params={"confidence": "explicit"}).json(), list)
    assert isinstance(client.get("/api/search", params={"confidence": "inferred"}).json(), list)
    assert client.get("/api/search", params={"confidence": "不存在"}).status_code == 422


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


def test_upload_same_name_twice_keeps_first_file_intact(client: TestClient, tmp_path: Path):
    """批内同名文件拒收第二条，且不能破坏第一条的落盘文件。

    旧实现把两条同名文件写进同一目标路径，去重分支删除时连带删掉首条——
    Video 行指向已消失的文件，转写必然 WinError 2。
    """
    src = tmp_path / "same_name.mp4"
    src.write_bytes(b"\x00" * 64)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "同名批次"},
                        files=[("files", ("same_name.mp4", fh, "video/mp4")),
                               ("files", ("same_name.mp4", fh, "video/mp4"))])
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["video_count"] == 1
    assert [x["reason"] for x in data["rejected"]] == ["与批内已有文件同名"]

    batch = client.get(f"/api/batches/{data['id']}").json()
    assert batch["status"] == "succeeded", batch
    assert Path(batch["videos"][0]["path"]).exists(), "首条文件的落盘文件必须还在"


def test_sse_unknown_batch_is_404(client: TestClient):
    """订阅不存在的批次要 404，而不是返回一条只发 ping 的空流让前端挂死。"""
    assert client.get("/api/batches/99999/progress").status_code == 404


def test_unknown_api_path_returns_404_json(client: TestClient):
    """未知 /api 路径不许被 SPA catch-all 吞成 index.html——调用方会把 HTML 当响应体解析。"""
    r = client.get("/api/definitely-not-a-route")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_batch_name_too_long_rejected(client: TestClient, tmp_path: Path):
    src = tmp_path / "name_len.mp4"
    src.write_bytes(b"\x00" * 16)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "长" * 81},
                        files=[("files", ("name_len.mp4", fh, "video/mp4"))])
    assert r.status_code == 422 and "批次名过长" in r.json()["detail"]


def test_delete_batch_cascades(client: TestClient, tmp_path: Path):
    """终态批次可删：条目/证据/片段/绑定/上传文件一并清掉，Tag 本体跨视频共享保留。"""
    src = tmp_path / "todelete.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "待删批次"},
                        files=[("files", ("todelete.mp4", fh, "video/mp4"))])
    assert r.status_code == 201, r.text
    batch_id = r.json()["id"]
    batch = client.get(f"/api/batches/{batch_id}").json()
    vid = batch["videos"][0]["id"]
    video_path = Path(batch["videos"][0]["path"])
    assert client.get(f"/api/videos/{vid}/items").json()

    assert client.delete(f"/api/batches/{batch_id}").status_code == 204
    assert client.get(f"/api/batches/{batch_id}").status_code == 404
    assert client.get(f"/api/videos/{vid}").status_code == 404
    assert not video_path.exists(), "上传文件要随批次一起清掉"
    assert client.get("/api/tags").json(), "Tag 本体跨视频共享，不随批次删除"


def test_export_markdown_chinese_labels(client: TestClient, tmp_path: Path):
    """导出文稿面向中文读者：状态/置信度枚举不直接上稿。"""
    src = tmp_path / "export_label.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "导出中文批次"},
                        files=[("files", ("export_label.mp4", fh, "video/mp4"))])
    batch_id = r.json()["id"]
    md = client.get(f"/api/batches/{batch_id}/export.md").text
    assert "成功" in md and "succeeded" not in md
    assert "（明述）" in md or "（推断）" in md
