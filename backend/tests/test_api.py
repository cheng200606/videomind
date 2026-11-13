"""走 HTTP 的端到端集成测试：上传 → 四阶段解析 → 产物 → 检索 → 笔记 → 修订 → 导出。

TestClient 会在响应返回后同步执行 BackgroundTasks，所以不用轮询等待。
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine
from app.enums import ArtifactType, BatchStatus, StageStatus, VideoStatus
from app.main import app
from app.models import Artifact, KnowledgeItem, Video, VideoBatch


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
    assert "auto" in current["asr"]["available"]
    assert current["asr"]["resolved"] in current["asr"]["available"]
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
    # v0.11 检索契约：{total, items}，且不再接受空条件全量
    for params in ({"q": "ref"}, {"tag": tags[0]["id"]}):
        body = client.get("/api/search", params=params).json()
        assert isinstance(body, dict) and isinstance(body["items"], list)
        assert body["total"] >= len(body["items"])

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
    """F4 置信度过滤：合法值返回 {total, items}，非法值 422，空条件 422。"""
    for conf in ("explicit", "inferred"):
        body = client.get("/api/search", params={"confidence": conf}).json()
        assert isinstance(body, dict) and isinstance(body["items"], list)
    assert client.get("/api/search", params={"confidence": "不存在"}).status_code == 422
    assert client.get("/api/search").status_code == 422
    assert client.get("/api/search", params={"q": "   "}).status_code == 422


def test_search_tag_scope_covers_video_and_item_level(client: TestClient, tmp_path: Path):
    """视频级标签命中该视频全部条目；条目级标签只命中自身；无绑定标签返回空。"""
    src = tmp_path / "tag_scope.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "标签作用域批次"},
                        files=[("files", ("tag_scope.mp4", fh, "video/mp4"))])
    assert r.status_code == 201, r.text
    vid = client.get(f"/api/batches/{r.json()['id']}").json()["videos"][0]["id"]
    items = client.get(f"/api/videos/{vid}/items").json()
    assert items

    video_tag = client.post("/api/tags/bind", json={
        "name": "本批视频级标签", "target_type": "video", "target_id": vid})
    assert video_tag.status_code == 201
    video_tag_id = video_tag.json()["id"]
    by_video = client.get("/api/search", params={"tag": video_tag_id}).json()
    assert by_video["total"] == len(items)
    assert len(by_video["items"]) == len(items)
    assert {x["video_id"] for x in by_video["items"]} == {vid}

    item_id = items[0]["id"]
    bound = client.post("/api/tags/bind", json={
        "name": "仅条目标签", "target_type": "item", "target_id": item_id})
    assert bound.status_code == 201
    by_item = client.get("/api/search", params={"tag": bound.json()["id"]}).json()
    assert [x["id"] for x in by_item["items"]] == [item_id]

    assert client.get("/api/search", params={
        "tag": video_tag_id, "q": "一定不存在的关键词"}).json() == {"total": 0, "items": []}

    temp = client.post("/api/tags/bind", json={
        "name": "临时无绑定标签", "target_type": "item", "target_id": item_id}).json()
    assert client.post(f"/api/tags/{temp['id']}/dismiss",
                       params={"target_type": "item", "target_id": item_id}).status_code == 200
    assert client.get("/api/search", params={"tag": temp["id"]}).json() == {"total": 0, "items": []}


def _sse_events(body: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in body.splitlines()
            if line.startswith("data: ")]


def test_sse_replays_history_and_video_terminal_is_opt_in(client: TestClient, tmp_path: Path):
    """刷新进度页要能回放历史事件；单条终态只在 video_events=1 时下发，兼容旧前端。"""
    src = tmp_path / "sse_history.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "SSE 回放批次"},
                        files=[("files", ("sse_history.mp4", fh, "video/mp4"))])
    batch_id = r.json()["id"]

    with client.stream("GET", f"/api/batches/{batch_id}/progress") as resp:
        first = _sse_events(b"".join(resp.iter_bytes()).decode("utf-8"))
    assert first, "终态批次重连也要回放历史，不能只给一条合成终态"
    seqs = [e["seq"] for e in first]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))
    batch_terminals = [e for e in first if e["stage"] == "batch"
                       and e["video_id"] is None and e["status"] in ("succeeded", "partial", "failed")]
    assert len(batch_terminals) == 1
    assert not [e for e in first if e["video_id"] is not None and e["stage"] == "batch"
                and e["status"] in ("succeeded", "partial", "failed")], "默认不下发单条终态"

    with client.stream("GET", f"/api/batches/{batch_id}/progress",
                       params={"video_events": 1}) as resp:
        opted = _sse_events(b"".join(resp.iter_bytes()).decode("utf-8"))
    video_terminals = [e for e in opted if e["video_id"] is not None and e["stage"] == "batch"
                       and e["status"] in ("succeeded", "partial", "failed")]
    assert len(video_terminals) == 1
    assert opted[-1]["stage"] == "batch" and opted[-1]["video_id"] is None
    assert not any(e["message"].startswith(f"{batch_id}_") for e in opted if e["message"]), \
        "事件流只应展示原始文件名，不能暴露落盘批次前缀"

    with client.stream("GET", f"/api/batches/{batch_id}/progress") as resp:
        again = _sse_events(b"".join(resp.iter_bytes()).decode("utf-8"))
    assert [e["seq"] for e in again] == seqs, "同一批次的回放必须稳定"


def test_revise_with_content_updates_item_and_snapshot(client: TestClient, tmp_path: Path):
    """修订接口带 content 时正文与版本快照同时更新；只跳状态时保留正文。"""
    src = tmp_path / "revision_content.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "修订正文批次"},
                        files=[("files", ("revision_content.mp4", fh, "video/mp4"))])
    assert r.status_code == 201, r.text
    vid = client.get(f"/api/batches/{r.json()['id']}").json()["videos"][0]["id"]
    item_id = client.get(f"/api/videos/{vid}/items").json()[0]["id"]

    assert client.post(f"/api/items/{item_id}/revision",
                       json={"content": "修订后的正文"}).status_code == 200
    detail = client.get(f"/api/items/{item_id}").json()
    assert detail["content"] == "修订后的正文"
    assert detail["revisions"][-1]["snapshot"] == "修订后的正文"
    assert detail["revisions"][-1]["state"] == "draft"

    assert client.post(f"/api/items/{item_id}/revision",
                       json={"state": "pending_confirm", "content": "确认版正文"}).status_code == 200
    detail = client.get(f"/api/items/{item_id}").json()
    assert detail["content"] == "确认版正文"
    assert detail["revisions"][-1]["state"] == "pending_confirm"
    assert detail["revisions"][-1]["snapshot"] == "确认版正文"

    assert client.post(f"/api/items/{item_id}/revision",
                       json={"state": "confirmed"}).status_code == 200
    detail = client.get(f"/api/items/{item_id}").json()
    assert detail["content"] == "确认版正文"
    assert detail["revisions"][-1]["snapshot"] == "确认版正文"


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
    # 落盘名统一是 {batch_id}_{filename}；API 已不再回显绝对路径，测试自行按规则核验
    stored = Path(get_settings().media_root) / f"{data['id']}_same_name.mp4"
    assert stored.exists(), "首条文件的落盘文件必须还在"


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
    video_path = Path(get_settings().media_root) / f"{batch_id}_todelete.mp4"
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


def _seed_coverage(client: TestClient, tmp_path: Path, *, name: str, filename: str,
                   notice: str, status: VideoStatus = VideoStatus.SUCCEEDED) -> int:
    """造一个已解析批次，并把解析阶段的诚实提示直接写进摘要产物 payload。"""
    src = tmp_path / filename
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": name},
                        files=[("files", (filename, fh, "video/mp4"))])
    assert r.status_code == 201, r.text
    batch_id = r.json()["id"]
    with Session(engine) as session:
        video = session.exec(select(Video).where(Video.batch_id == batch_id)).first()
        assert video is not None
        items = session.exec(select(KnowledgeItem).where(KnowledgeItem.video_id == video.id)).all()
        summary = next((i for i in items if i.type == ArtifactType.SUMMARY), None)
        assert summary is not None, "默认产物策略应产出内容总结"
        art = session.exec(select(Artifact).where(Artifact.item_id == summary.id)).first()
        assert art is not None
        payload = dict(art.payload or {})
        payload["notice"] = notice
        art.payload = payload  # 重新赋值，确保 JSON 列被标记为已修改
        session.add(art)
        if status != VideoStatus.SUCCEEDED:
            video.status = status
            session.add(video)
            batch = session.get(VideoBatch, batch_id)
            assert batch is not None
            batch.status = BatchStatus.PARTIAL
            session.add(batch)
        session.commit()
    return batch_id


def test_export_markdown_carries_coverage_notice(client: TestClient, tmp_path: Path):
    """工作台的覆盖提示必须随文稿导出，且结构化快照同源可查。"""
    notice = "第 2 段结构化失败，对应区间内容可能缺失"
    batch_id = _seed_coverage(client, tmp_path, name="覆盖提示批次",
                              filename="coverage.mp4", notice=notice)
    md = client.get(f"/api/batches/{batch_id}/export.md").text
    assert "**解析覆盖提示**" in md
    assert notice in md
    assert "请回看原片核对" in md
    snapshot = client.get(f"/api/batches/{batch_id}/structured").json()
    assert notice in snapshot["videos"][0]["coverage_notice"]


def test_export_markdown_marks_partial_video(client: TestClient, tmp_path: Path):
    """部分成功批次：批次头汇总 + 视频段状态/notice 双提示都要出现。"""
    notice = "转写较长，已按时间切 3 段完整结构化"
    batch_id = _seed_coverage(client, tmp_path, name="部分成功批次",
                              filename="partial.mp4", notice=notice,
                              status=VideoStatus.PARTIAL)
    md = client.get(f"/api/batches/{batch_id}/export.md").text
    assert "1 条视频解析状态非「成功」" in md
    assert "该视频解析状态为「部分成功」，以下产物可能不完整" in md
    assert notice in md


def test_export_markdown_has_no_notice_block_when_clean(client: TestClient, tmp_path: Path):
    """无提示、状态成功时不产生空提示块，避免把正常文稿写得像有问题。"""
    batch_id = _seed_coverage(client, tmp_path, name="干净批次",
                              filename="clean.mp4", notice="")
    md = client.get(f"/api/batches/{batch_id}/export.md").text
    assert "**解析覆盖提示**" not in md
    assert "解析状态非" not in md
    snapshot = client.get(f"/api/batches/{batch_id}/structured").json()
    assert snapshot["videos"][0]["coverage_notice"] == ""


def test_empty_output_schemas_are_422(client: TestClient):
    assert client.put("/api/settings/engines", json={"output_schemas": []}).status_code == 422
    assert client.put("/api/settings/engines", json={"output_schemas": "summary"}).status_code == 422
    assert client.put("/api/settings/engines", json={"output_schemas": ["bogus"]}).status_code == 422
    client.put("/api/settings/engines",
               json={"output_schemas": ["summary", "uml_draft", "key_points", "code_blocks"]})


def test_missing_video_endpoints_are_404_and_bad_type_422(client: TestClient):
    assert client.get("/api/videos/987654/transcript").status_code == 404
    assert client.get("/api/videos/987654/items").status_code == 404
    # FastAPI 先校验枚举参数，非法 type 会先返回 422；合法 type 才走到 404
    assert client.get("/api/videos/987654/items", params={"type": "bogus"}).status_code == 422


def test_items_bad_type_is_422_for_existing_video(client: TestClient, tmp_path: Path):
    src = tmp_path / "bad_type.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "类型校验批次"},
                        files=[("files", ("bad_type.mp4", fh, "video/mp4"))])
    vid = client.get(f"/api/batches/{r.json()['id']}").json()["videos"][0]["id"]
    assert client.get(f"/api/videos/{vid}/items", params={"type": "bogus"}).status_code == 422


def test_export_and_structured_require_terminal_batch(client: TestClient):
    with Session(engine) as session:
        batch = VideoBatch(name="运行中批次", video_count=0, status=BatchStatus.RUNNING)
        session.add(batch)
        session.commit()
        session.refresh(batch)
        batch_id = batch.id
    try:
        assert client.get(f"/api/batches/{batch_id}/export.md").status_code == 409
        assert client.get(f"/api/batches/{batch_id}/structured").status_code == 409
    finally:
        with Session(engine) as session:
            obj = session.get(VideoBatch, batch_id)
            if obj:
                session.delete(obj)
                session.commit()


def test_video_views_have_no_absolute_path(client: TestClient, tmp_path: Path):
    """面向 UI 的视频视图不得回显本机绝对落盘路径（v0.14 移除 path 兼容字段）。"""
    src = tmp_path / "no_path.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "路径脱敏批次"},
                        files=[("files", ("no_path.mp4", fh, "video/mp4"))])
    assert r.status_code == 201, r.text
    batch_id = r.json()["id"]
    batch_resp = client.get(f"/api/batches/{batch_id}")
    vid = batch_resp.json()["videos"][0]["id"]
    detail_resp = client.get(f"/api/videos/{vid}")

    for resp, view in ((batch_resp, batch_resp.json()["videos"][0]),
                       (detail_resp, detail_resp.json())):
        assert resp.status_code == 200
        assert "path" not in view
        assert view["file_name"] == "no_path.mp4"
        assert view["media_url"].startswith("/media/")
        assert ".pytest_tmp" not in resp.text, "响应体不得夹带本机运行时目录"


def test_structured_snapshot_has_no_absolute_path(client: TestClient, tmp_path: Path):
    src = tmp_path / "snapshot.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "快照脱敏批次"},
                        files=[("files", ("snapshot.mp4", fh, "video/mp4"))])
    data = client.get(f"/api/batches/{r.json()['id']}/structured").json()
    video = data["videos"][0]
    assert "path" not in video
    assert video["file_name"] == "snapshot.mp4"
    assert video["media_url"].startswith("/media/")
    assert video["item_count"] > 0


def test_empty_pending_batch_can_be_deleted(client: TestClient):
    with Session(engine) as session:
        batch = VideoBatch(name="空等待批次", video_count=0, status=BatchStatus.PENDING)
        session.add(batch)
        session.commit()
        session.refresh(batch)
        batch_id = batch.id
    assert client.delete(f"/api/batches/{batch_id}").status_code == 204
    assert client.get(f"/api/batches/{batch_id}").status_code == 404


def test_upload_same_name_case_insensitive(client: TestClient, tmp_path: Path):
    src = tmp_path / "Same.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as f1, src.open("rb") as f2:
        r = client.post("/api/batches", data={"name": "大小写同名批次"},
                        files=[("files", ("Same.mp4", f1, "video/mp4")),
                               ("files", ("same.mp4", f2, "video/mp4"))])
    assert r.status_code == 201, r.text
    assert r.json()["video_count"] == 1
    assert r.json()["rejected"][0]["reason"] == "与批内已有文件同名"


def test_upload_size_limit_rejects_without_orphan(client: TestClient, tmp_path: Path, monkeypatch):
    import app.routers.parse as parse_router
    monkeypatch.setattr(parse_router, "_MAX_FILE_BYTES", 1024)
    src = tmp_path / "too_big.mp4"
    src.write_bytes(b"\x00" * 4096)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "超限批次"},
                        files=[("files", ("too_big.mp4", fh, "video/mp4"))])
    assert r.status_code == 422
    assert "超过" in r.json()["detail"]
    # 全拒后不留下 PENDING 孤儿
    assert all(b["name"] != "超限批次" for b in client.get("/api/batches").json())


def test_reparse_running_batch_is_409(client: TestClient, tmp_path: Path):
    src = tmp_path / "reparse_guard.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "重跑守卫批次"},
                        files=[("files", ("reparse_guard.mp4", fh, "video/mp4"))])
    batch_id = r.json()["id"]
    with Session(engine) as session:
        batch = session.get(VideoBatch, batch_id)
        batch.status = BatchStatus.RUNNING
        session.add(batch)
        session.commit()
    try:
        assert client.post(f"/api/batches/{batch_id}/parse").status_code == 409
    finally:
        with Session(engine) as session:
            batch = session.get(VideoBatch, batch_id)
            batch.status = BatchStatus.SUCCEEDED
            session.add(batch)
            session.commit()


def test_retry_running_video_is_409(client: TestClient, tmp_path: Path):
    src = tmp_path / "retry_guard.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "重试守卫批次"},
                        files=[("files", ("retry_guard.mp4", fh, "video/mp4"))])
    vid = client.get(f"/api/batches/{r.json()['id']}").json()["videos"][0]["id"]
    with Session(engine) as session:
        video = session.get(Video, vid)
        video.status = VideoStatus.RUNNING
        session.add(video)
        session.commit()
    try:
        assert client.post(f"/api/videos/{vid}/retry").status_code == 409
    finally:
        with Session(engine) as session:
            video = session.get(Video, vid)
            video.status = VideoStatus.SUCCEEDED
            session.add(video)
            session.commit()


def test_reparse_sets_running_before_background(client: TestClient, tmp_path: Path, monkeypatch):
    src = tmp_path / "sync_running.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "同步置运行批次"},
                        files=[("files", ("sync_running.mp4", fh, "video/mp4"))])
    batch_id = r.json()["id"]
    monkeypatch.setattr("app.routers.parse._run_batch", lambda bid: None)
    try:
        assert client.post(f"/api/batches/{batch_id}/parse").status_code == 200
        batch = client.get(f"/api/batches/{batch_id}").json()
        assert batch["status"] == "running"
        assert all(v["stages"]["transcribe"] == "pending" for v in batch["videos"])
    finally:
        monkeypatch.undo()
        from app.routers.parse import _run_batch
        _run_batch(batch_id)


def test_search_limit_returns_total(client: TestClient, monkeypatch, tmp_path: Path):
    """检索结果有上限也要带回总数：前端才能提示「已显示前 N 条」。"""
    from app.routers import knowledge

    src = tmp_path / "search_limit.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", data={"name": "检索上限批次"},
                        files=[("files", ("search_limit.mp4", fh, "video/mp4"))])
    assert r.status_code == 201, r.text
    vid = client.get(f"/api/batches/{r.json()['id']}").json()["videos"][0]["id"]
    all_items = client.get(f"/api/videos/{vid}/items").json()
    assert len(all_items) >= 2

    monkeypatch.setattr(knowledge, "_SEARCH_LIMIT", 2)
    body = client.get("/api/search", params={"video_id": vid}).json()
    assert body["total"] == len(all_items)
    assert len(body["items"]) == 2


def test_batch_list_carries_status_counts(client: TestClient, tmp_path: Path):
    """库页卡片要能直接看出「2 成功 1 失败」：列表接口带按状态计数。"""
    src = tmp_path / "counts.mp4"
    src.write_bytes(b"\x00" * 32)
    with src.open("rb") as fh:
        r = client.post("/api/batches", files=[("files", ("counts.mp4", fh, "video/mp4"))])
    assert r.status_code == 201
    batches = client.get("/api/batches").json()
    mine = next(b for b in batches if b["id"] == r.json()["id"])
    assert mine["video_status_counts"] == {"succeeded": 1}


def test_upload_rejects_too_many_files(client: TestClient):
    """单批文件数上限：先于任何落盘拒绝。"""
    files = [("files", (f"f{i}.mp4", b"\x00" * 16, "video/mp4")) for i in range(21)]
    r = client.post("/api/batches", data={"name": "超量批次"}, files=files)
    assert r.status_code == 422
    assert "最多 20 个文件" in r.json()["detail"]


def test_upload_batch_total_cap(client: TestClient, monkeypatch):
    """批次总大小上限：超限文件记入 rejected，前面的有效文件照常创建。"""
    from app.routers import parse as parse_router

    monkeypatch.setattr(parse_router, "_MAX_BATCH_BYTES", 32)
    files = [("files", ("a.mp4", b"\x00" * 16, "video/mp4")),
             ("files", ("b.mp4", b"\x00" * 20, "video/mp4"))]
    r = client.post("/api/batches", data={"name": "总量上限"}, files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["video_count"] == 1
    assert any("总大小" in x["reason"] for x in body["rejected"])


def test_upload_content_length_precheck(client: TestClient, monkeypatch):
    """Content-Length 预检：超大请求体在落盘前就被 413 拒绝。"""
    from app.routers import parse as parse_router

    monkeypatch.setattr(parse_router, "_MULTIPART_SLACK", -(10 ** 9))
    boundary = "----vmboundary"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"name\"\r\n\r\n预检\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"pre.mp4\"\r\n"
        "Content-Type: video/mp4\r\n\r\n\x00\x00\x00\x00\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    r = client.post(
        "/api/batches",
        content=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(30 * 1024 ** 3),
        },
    )
    assert r.status_code == 413
    assert "分批" in r.json()["detail"]


def test_parse_mutex_blocks_second_batch(client: TestClient, tmp_path: Path):
    """解析互斥：已有批次在解析时，新批次创建直接 409。"""
    from app.pipeline import parse_mutex

    assert parse_mutex.claim(999_999)
    try:
        src = tmp_path / "m.mp4"
        src.write_bytes(b"\x00" * 32)
        with src.open("rb") as fh:
            r = client.post("/api/batches", files=[("files", ("m.mp4", fh, "video/mp4"))])
        assert r.status_code == 409
        assert "已有批次正在解析" in r.json()["detail"]
    finally:
        parse_mutex.release(999_999)


def test_validation_error_is_chinese(client: TestClient):
    """路径参数非法时回中文 422，不再把 pydantic 英文 detail 甩给前端。"""
    r = client.get("/api/videos/abc/items")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail.startswith("请求参数格式不正确")
    assert "video_id" in detail and "应为整数" in detail


def test_search_ranks_keyword_hits_by_relevance(client: TestClient):
    """v0.13 相关度排序：双命中 > 标题命中 > 内容命中；无关键词时保持视频+时间锚稳定序。"""
    from app.enums import ArtifactType, Confidence
    from app.models import Evidence, KnowledgeItem

    with Session(engine) as session:
        batch = VideoBatch(name="相关度批次")
        session.add(batch)
        session.commit()
        session.refresh(batch)
        video = Video(batch_id=batch.id, path="relevance_probe.mp4")
        session.add(video)
        session.commit()
        session.refresh(video)
        ev = Evidence(video_id=video.id, start_ms=0, end_ms=1000, quote="原话", channel="asr")
        session.add(ev)
        session.commit()
        session.refresh(ev)

        def add(title: str, content: str, anchor_ms: int, ordinal: int) -> None:
            session.add(KnowledgeItem(
                video_id=video.id, type=ArtifactType.KEY_POINTS, title=title, content=content,
                confidence=Confidence.EXPLICIT, anchor_ms=anchor_ms, evidence_id=ev.id,
                ordinal=ordinal))

        add("普通条目一", "内容不含关键词的普通长文", 1000, 1)
        add("内容命中样例", "正文里才出现标记词 qrank13 的条目", 2000, 2)
        add("标题命中 qrank13 样例", "正文没有该词", 3000, 3)
        add("qrank13 双命中", "qrank13 同时出现在标题与正文", 4000, 4)
        session.commit()
        video_id = video.id   # 会话关闭前取 id（expire_on_commit 下出会话再取会报 Detached）

    body = client.get("/api/search", params={"q": "qrank13"}).json()
    assert body["total"] == 3
    assert [i["title"] for i in body["items"]] == [
        "qrank13 双命中", "标题命中 qrank13 样例", "内容命中样例"]

    stable = client.get("/api/search", params={"video_id": video_id}).json()
    assert [i["anchor_ms"] for i in stable["items"]] == [1000, 2000, 3000, 4000]
