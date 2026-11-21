#!/usr/bin/env python
"""G4 可达性扫描（v0.17 质量门）：一条命令跑完 axe-core 亮/暗 × 8 页。

v0.16 的扫描法是临时会话里手敲的，脚本没入库（在 gitignored 的 output/ 下），
结果就是「门存在，执行者不存在」——下一个人拿不到、门也就复现不了。这个脚本把
那套方法固化下来，只依赖本机已有的东西：

  * 后端：`backend/.venv`（fastapi + uvicorn + httpx）
  * 浏览器：本机 msedge（`C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe`）
  * 注入载荷：`frontend/node_modules/axe-core/axe.min.js`（已是 devDependency）

**不需要 playwright**。直接用 Chrome DevTools Protocol 驱动 headless msedge：
Python 3.14 自带 `websockets`，Node 侧的 playwright 在本机并未安装。

扫描法沿用 v0.16 的结论（`docs/迭代方案_v0.16.md` §五）：`axe.run` 在注入后**同步跑容易
被调用方超时掐断**，所以改成「起跑后把 promise 存到 window，再轮询取结果」。

**每页扫「默认态 + 有数据态」**（v0.17 口径）：v0.16 只扫默认态，导出页当时扫的是
「批次未进终态」的空态、上传页扫的是空拖拽区，于是只在有数据时才渲染的组件从没被扫过
——复扫立刻在导出页终态与上传页已选文件态各发现问题。状态定义见 `ROUTE_STATES`，
没扫成的状态一律进「未覆盖清单」并让退出码为 1，不许沉默略过。

用法（仓库根执行，需先 `npm run build` 让 frontend/dist 跟上源码）：
    backend/.venv/Scripts/python tools/check_a11y.py
    backend/.venv/Scripts/python tools/check_a11y.py --theme dark --only /settings
    backend/.venv/Scripts/python tools/check_a11y.py --json output/v017/g4.json

退出码：0 = 亮/暗 × 8 页 × 声明状态 0 个 serious/critical violation 且全部扫成；
1 = 有违规或有状态没扫成（未覆盖清单）；2 = 环境没准备好。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
AXE_JS = ROOT / "frontend" / "node_modules" / "axe-core" / "axe.min.js"
DIST_INDEX = ROOT / "frontend" / "dist" / "index.html"
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

# v0.16 基线的 8 页（不含 not-found）。
#
# **每页扫几个状态**：v0.16 只扫了各页的默认态，而导出页默认态是「批次未进终态，
# 只有一句提示」、上传页默认态是「空拖拽区」。于是那些只在**有数据时**才渲染的组件
# 从来没被扫过——2026-11-21 复扫立刻在导出页终态（暗色 code 对比度 1.84）与上传页
# 已选文件态（el-upload-list 的 li[role=button] 触发 list / aria-allowed-role）各
# 发现问题。所以这里每个路由声明的是**状态列表**，不是单个 URL。
#
# 详情页（批次进度 / 工作台 / 导出）默认渲染的就是「有数据态」——样例批次已解析完成，
# 这些页面没有第二个有意义的形态，`note` 里写明，不假装扫了两个状态。
ROUTE_STATES = [
    {
        "tpl": "/", "title": "视频库",
        "states": [
            {"name": "默认态"},
            {"name": "筛选选中态",
             "js": "document.querySelectorAll('.el-radio-button__inner')[1]?.click()",
             "note": "点第二个状态筛选，覆盖选中态 el-radio-button__inner"},
        ],
    },
    {
        "tpl": "/upload", "title": "批量上传",
        "states": [
            {"name": "默认态"},
            {"name": "已选文件态", "files": True,
             "note": "选中文件后 el-upload-list 才渲染出 li[role=button]"},
        ],
    },
    {
        "tpl": "/search", "title": "知识检索",
        "states": [
            {"name": "默认态"},
            {"name": "已出结果态",
             "js": """(() => {
               const el = document.querySelector('input[aria-label="检索关键词"]');
               if (!el) return 'no-input';
               const set = Object.getOwnPropertyDescriptor(
                 HTMLInputElement.prototype, 'value').set;
               set.call(el, '视频');
               el.dispatchEvent(new Event('input', {bubbles: true}));
               const btn = [...document.querySelectorAll('button')]
                 .find(b => b.textContent.trim() === '检索');
               if (!btn) return 'no-button';
               btn.click();
               return 'ok';
             })()""",
             "note": "填入关键词并触发检索，覆盖结果命中高亮态"},
        ],
    },
    {
        "tpl": "/batches/{batch_id}", "title": "批次进度",
        "states": [{"name": "有数据态",
                    "note": "详情页默认即渲染已解析批次，无第二个有意义形态"}],
    },
    {
        "tpl": "/videos/{video_id}", "title": "知识工作台",
        "states": [{"name": "有数据态",
                    "note": "详情页默认即渲染条目与证据，无第二个有意义形态"}],
    },
    {
        "tpl": "/notes/{item_id}", "title": "笔记",
        "states": [
            {"name": "默认态"},
            {"name": "讲义页签态",
             "js": "document.querySelectorAll('.el-tabs__item')[1]?.click()",
             "note": "切到讲义页签，覆盖另一套 MdEditor（全局主题联动）"},
        ],
    },
    {
        "tpl": "/batches/{batch_id}/export", "title": "导出",
        "states": [{"name": "终态", "note":
                    "批次已 succeeded，默认即渲染 MdPreview 终态；v0.16 扫的是空态"}],
    },
    {
        "tpl": "/settings", "title": "设置",
        "states": [{"name": "默认态"}],
    },
]

BLOCKING = {"serious", "critical"}

# 每处 serious/critical 的**处置**：修 or 接受，理由必须写在这里，不能只留个红叉。
# 键是 `(主题, 路由模板, 状态名, 规则 id)`；没登记的一律报「未处置」，因为
# 「没人认领的红灯」和「已知并接受的红灯」在交付文档里是两件事。
DISPOSITIONS: dict[tuple[str, str, str, str], dict] = {
    ("light", "/upload", "已选文件态", "list"): {
        "action": "接受",
        "owner": "质量线裁决",
        "reason": "el-upload 把 li[role=button] 直接放进 ul，是 Element Plus 内部结构，"
                  "不在本组代码里；改它要放弃 el-upload 或包一层，v0.17 不改 UI 结构。",
    },
    ("dark", "/", "默认态", "color-contrast"): {
        "action": "修（前端线已提交 2f7b6a3）",
        "owner": "前端开发工程师",
        "reason": "EP 把 --el-radio-button-checked-bg-color 声明在 .el-radio-button 自身，"
                  "覆盖要写 html.dark .el-radio-button；白字 on #6f95e3 = 2.96:1。",
    },
    ("dark", "/", "筛选选中态", "color-contrast"): {
        "action": "修（同 2f7b6a3，同一元素）",
        "owner": "前端开发工程师",
        "reason": "与默认态是同一个 .el-radio-button__inner，修一处两种状态一起消失。",
    },
    ("dark", "/upload", "已选文件态", "list"): {
        "action": "接受",
        "owner": "质量线裁决",
        "reason": "同 light 版：Element Plus 内部结构，v0.17 不改 UI 结构。",
    },
    ("dark", "/batches/{batch_id}/export", "终态", "color-contrast"): {
        "action": "修（前端线已提交 2f7b6a3）",
        "owner": "前端开发工程师",
        "reason": "MdPreview 从没传 theme，根节点钉死 data-theme=light；暗色下 .paper 仍是"
                  "白底 #ffffff，内部 code 用 #9eb7eb = 1.84:1，29 个节点。",
    },
}


# ───────────────────────────── 环境 ─────────────────────────────
def find_edge() -> Path:
    for p in EDGE_CANDIDATES:
        if p.is_file():
            return p
    raise SystemExit("[G4] 找不到 msedge，本机没有 Chrome，必须用 Edge")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def check_dist() -> None:
    if not DIST_INDEX.is_file():
        raise SystemExit("[G4] frontend/dist 不存在：先在 frontend/ 下跑 npm.cmd run build")
    newest_src = max(
        (p.stat().st_mtime for p in (ROOT / "frontend" / "src").rglob("*") if p.is_file()),
        default=0)
    if DIST_INDEX.stat().st_mtime < newest_src:
        print("[G4] 警告：frontend/dist 比 src 旧，扫描的不是当前源码（先 npm.cmd run build）",
              file=sys.stderr)


def wait_http(url: str, timeout: float = 40.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return
        except Exception:                                          # noqa: BLE001
            time.sleep(0.4)
    raise SystemExit(f"[G4] 服务没起来：{url}")


# ───────────────────────────── 后端 ─────────────────────────────
class Backend:
    """临时数据目录 + mock ASR + OCR 关闭起一个后端，扫完就关。

    刻意不碰 `backend/data/`：那里的库是开发者的真实数据，扫描不该往里写。
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.port = free_port()
        self.proc: subprocess.Popen | None = None
        self.base = f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        data = self.root / "data"
        media = self.root / "media"
        cache = self.root / "cache"
        for d in (data, media, cache):
            d.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.update({
            "DATABASE_URL": f"sqlite:///{(data / 'a11y.db').as_posix()}",
            "MEDIA_ROOT": str(media),
            "CACHE_ROOT": str(cache),
            "ASR_ENGINE": "mock",
            "OCR_ENGINE": "none",
            "VMIND_MOCK_ALLOW_FALLBACK": "1",
            "VMIND_FIXTURE_DIR": str(ROOT / "backend" / "tests" / "fixtures"),
            "DEEPSEEK_API_KEY": "",
            "REDIS_URL": "",
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
        })
        self.proc = subprocess.Popen(
            [str(VENV_PY), "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=str(ROOT / "backend"), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_http(f"{self.base}/api/health")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def seed(self) -> dict[str, int]:
        """上传一条样例视频跑完四阶段，拿到真实 batch/video/item 供详情页扫描。"""
        import httpx

        src = self.root / "vue3_lecture.mp4"
        src.write_bytes(b"\x00" * 32)
        with httpx.Client(base_url=self.base, timeout=60) as c:
            with src.open("rb") as fh:
                r = c.post("/api/batches", data={"name": "可达性扫描批次"},
                           files=[("files", ("vue3_lecture.mp4", fh, "video/mp4"))])
            r.raise_for_status()
            batch_id = r.json()["id"]
            deadline = time.time() + 90
            while time.time() < deadline:
                b = c.get(f"/api/batches/{batch_id}").json()
                if b["status"] in ("succeeded", "partial", "failed"):
                    break
                time.sleep(0.5)
            else:
                raise SystemExit("[G4] 样批解析超时")
            video_id = b["videos"][0]["id"]
            items = c.get(f"/api/videos/{video_id}/items").json()
            if not items:
                raise SystemExit("[G4] 样例没产出条目，详情页扫不了")
            return {"batch_id": batch_id, "video_id": video_id, "item_id": items[0]["id"]}


# ───────────────────────────── CDP ─────────────────────────────
class Cdp:
    """最小 CDP 客户端：一个浏览器 WS，多个 target 会话（flatten）。

    顺带把事件消息攒进 `self.events`——`send` 在等自己那条响应时会收到别人的事件，
    丢掉就再也拿不到了。网络空闲判定靠的就是这个缓冲。
    """

    def __init__(self, ws_url: str) -> None:
        from websockets.sync.client import connect
        # legacy=True：本类要长期持有连接，不用 with 语句
        self.ws = connect(ws_url, max_size=64 * 1024 * 1024, open_timeout=15,
                          legacy=True)
        self._id = 0
        self.session: str | None = None
        self.target_id: str | None = None
        self.theme_script_id: str | None = None
        self.events: list[dict] = []
        self._event_cursor = 0

    def send(self, method: str, params: dict | None = None,
             session: bool = True) -> dict:
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session and self.session:
            msg["sessionId"] = self.session
        self.ws.send(json.dumps(msg))
        while True:
            raw = json.loads(self.ws.recv())
            if raw.get("id") == self._id:
                if "error" in raw:
                    raise RuntimeError(f"CDP {method} 失败：{raw['error']}")
                return raw.get("result", {})
            if "method" in raw:
                self.events.append(raw)

    def drain(self) -> list[dict]:
        """发一条最便宜的调用，把积压的事件读进来。"""
        self.evaluate("1")
        fresh = self.events[self._event_cursor:]
        self._event_cursor = len(self.events)
        return fresh

    def evaluate(self, expression: str, await_promise: bool = False):
        res = self.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": await_promise, "userGesture": True})
        if res.get("exceptionDetails"):
            det = res["exceptionDetails"]
            # 只报 `Uncaught` 等于没说：把真正的报错文本与位置带出来，否则扫失败时
            # 只能靠猜是哪一句表达式炸的。
            exc = det.get("exception") or {}
            desc = exc.get("description") or det.get("text") or ""
            where = ""
            if exc.get("lineNumber") is not None:
                where = f"（行 {exc.get('lineNumber')}:{exc.get('columnNumber')}）"
            raise RuntimeError(f"页面里报错：{desc}{where}｜表达式：{expression[:120]}")
        return res.get("result", {}).get("value")

    def open_target(self, theme: str = "light") -> None:
        """建一个 target 并挂上会话，但**不导航**。

        导航必须留给 `scan_page`：本脚本第四版在这里先导航到首页，再让 scan_page
        导航到目标页，结果首页那次 document 请求被新导航打断、收不到
        `Network.loadingFinished`，网络空闲判定就永远超时。一个 target 只导航一次，
        请求起落才配得平。

        **主题必须在文档创建前注入**（`Page.addScriptToEvaluateOnNewDocument`）。
        本脚本第七版是「先 navigate，再补 localStorage 并手动 `classList.add('dark')`」，
        那是**假绿**：`frontend/src/composables/useTheme.ts:16` 的 `mode` 是模块级 ref，
        `readStored()` 只在模块初始化时读一次 localStorage，导航后再写它读不到；
        而手动加上的 `html.dark` 类让 `html.dark` 的 CSS 生效了，`MdPreview` 却仍按
        `data-theme="light"` 渲染。于是脚本看到的是「页面类已切暗、组件还停在亮」——
        恰好是缺陷本身，却被当成暗色页面扫出 0 violation。v0.16 报出「暗色 8 页
        0 violation」也有这一半的原因。前端线 2026-11-21 查出并给了这个修法。

        `background=False` + `activateTarget` + `bringToFront` 三件套缺一不可：headless
        下新建的标签页默认是**后台**的，`document.hidden === true`，axe 遇到不可见文档
        会提前退出给出假绿（本脚本第五版就栽在这，症状见 `close_target`）。命令行参数
        里那个 `about:blank` 也占着一个标签页，所以浏览器里始终不止一个 target。
        """
        tid = self.send("Target.createTarget",
                        {"url": "about:blank", "background": False},
                        session=False)["targetId"]
        self.target_id = tid
        self.session = self.send("Target.attachToTarget",
                                 {"targetId": tid, "flatten": True}, session=False)["sessionId"]
        self.send("Page.enable")
        self.send("Runtime.enable")
        self.send("Network.enable")
        # 关键：在**新文档执行任何脚本之前**把主题写进 localStorage，站点自己的
        # useTheme.ts 初始化时就能读到。不要改成导航后补写。
        self.theme_script_id = self.send(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": f"try{{localStorage.setItem('vm-theme','{theme}');}}catch(e){{}}"})["identifier"]
        self.send("Page.bringToFront")
        self.send("Target.activateTarget", {"targetId": tid}, session=False)

    def close_target(self) -> None:
        """关掉当前 target，下一次扫描另开一个。

        实测教训（本脚本第五版，本轮排查最久的一处）：headless msedge 里**同一个 target
        连续导航到第 3～4 次之后，页面会被浏览器判成不可见**（`visibilityState === 'hidden'`、
        `document.hidden === true`、`hasFocus() === false`）。axe-core 遇到不可见文档会提前
        退出，`passes` 桶直接空掉、`violations` 也变空——看上去是「全绿」，其实是**根本没
        评估**。同一页 6 连扫得到 `viol = [29, 29, 29, 0, 0, 0]`，而每次新开 target 6 连扫
        恒为 29。所以「一次扫描 = 一个新 target」不是保险，是这个门能不能用的前提。
        """
        if not getattr(self, "target_id", None):
            return
        try:
            self.send("Target.closeTarget",
                      {"targetId": self.target_id}, session=False)
        except Exception:                                          # noqa: BLE001
            pass
        self.target_id = None
        self.session = None
        self.theme_script_id = None

    def set_file_input(self, selector: str, files: list[str]) -> str:
        """往 `<input type=file>` 塞真实文件路径（走 CDP，不靠 JS 伪造 FileList）。

        Element Plus 的 `el-upload` 在选中文件后会渲染 `el-upload-list`，而那个
        `<ul>` 的直接子节点是 `li[role=button]`——只在**已选文件态**才存在的违规，
        v0.16 扫空拖拽区自然扫不到。JS 造 File 对象绕不过各家的 `files` 校验，
        所以用 `DOM.setFileInputFiles` 让浏览器自己去读盘。
        """
        self.send("DOM.enable")
        doc = self.send("DOM.getDocument", {"depth": -1})["root"]["nodeId"]
        node = self.send("DOM.querySelector",
                         {"nodeId": doc, "selector": selector})["nodeId"]
        if not node:
            return "no-input"
        self.send("DOM.setFileInputFiles", {"nodeId": node, "files": files})
        return "ok"

    def ensure_visible(self, tries: int = 5) -> dict:
        """扫描前确认页面真的在前台；不可见就重新提到前台再确认。

        实测（2026-11-21 探针 `output/v017/_probe_vis.py`）：即使每次新开 target，
        `document.hidden` 仍会在**导航之后、扫描之前**被翻成 true——msedge 在临时
        profile 里会陆续装配扩展（Tampermonkey 之类），扩展页开起来就把前台抢走。
        所以「新开 target」只是第一道，开扫前还得再确认一次；确认不了就报错，
        绝不能带着 `hidden` 去跑 axe。
        """
        state = None
        for _ in range(tries):
            state = self.evaluate(
                "({hidden: document.hidden === true ||"
                " document.visibilityState === 'hidden',"
                " vis: document.visibilityState,"
                " focused: document.hasFocus()})")
            if state and not state.get("hidden"):
                return state
            try:
                self.send("Page.bringToFront")
                self.send("Target.activateTarget",
                          {"targetId": self.target_id}, session=False)
            except Exception:                                      # noqa: BLE001
                pass
            time.sleep(0.5)
        return state or {}

    def wait_network_idle(self, idle_s: float = 1.0, timeout: float = 25.0) -> dict:
        """等网络静下来：连续 idle_s 秒没有请求起落才算完。

        实测教训（本脚本第三版）：只等 DOM 落定是不够的。导出页的 Markdown 预览是
        md-editor-v3 的**懒加载 chunk** 渲染出来的，chunk 没到之前页面上连一个 `code`
        元素都没有，axe 自然扫出「0 violation」——同一份代码连跑两遍、一遍报 2 处一遍
        报全绿，就是这么来的。所以口径必须是「DOM 静了**且**网络静了」才开扫。
        """
        deadline = time.time() + timeout
        last_activity = time.time()
        inflight: dict[str, str] = {}
        requests = 0
        while time.time() < deadline:
            for ev in self.drain():
                method = ev.get("method")
                params = ev.get("params") or {}
                if method == "Network.requestWillBeSent":
                    requests += 1
                    inflight[params.get("requestId")] = \
                        (params.get("request") or {}).get("url", "")
                    last_activity = time.time()
                elif method in ("Network.loadingFinished", "Network.loadingFailed"):
                    inflight.pop(params.get("requestId"), None)
                    last_activity = time.time()
            idle = time.time() - last_activity
            if not inflight and idle >= idle_s:
                return {"requests": requests, "idle_s": round(idle, 2),
                        "timed_out": False}
            time.sleep(0.15)
        return {"requests": requests, "idle_s": None, "timed_out": True,
                "inflight": sorted(inflight.values())}

    def wait_ready(self, timeout: float = 25.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.evaluate("document.readyState === 'complete'"):
                    return
            except Exception:                                      # noqa: BLE001
                pass
            time.sleep(0.25)
        raise RuntimeError("页面加载超时")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:                                          # noqa: BLE001
            pass


def run_axe(cdp: Cdp, timeout: float = 60.0,
            exclude: list[str] | None = None) -> dict:
    """起跑 → 轮询取结果。GET 结果前先把 promise 挂到 window，避免调用方超时。

    `exclude` 是**显式**排除的 CSS 选择器（axe context 的 exclude）。被排除的东西
    必须原样写进结果 JSON——静默排除等于换个形式的假绿。
    """
    ctx = "document"
    if exclude:
        ctx = ("{include: [document], exclude: [" +
               ", ".join(json.dumps(s) for s in exclude) + "]}")
    cdp.evaluate("window.__axe = {done:false, err:null, res:null};"
                 f"axe.run({ctx}, {{resultTypes:['violations','incomplete']}})"
                 ".then(r => {window.__axe.res = {violations: r.violations,"
                 " incomplete: r.incomplete}; window.__axe.done = true})"
                 ".catch(e => {window.__axe.err = String(e); window.__axe.done = true});"
                 "'started'")
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = cdp.evaluate("({done: !!window.__axe?.done, err: window.__axe?.err || null})")
        if state and state.get("done"):
            if state.get("err"):
                raise RuntimeError(f"axe.run 报错：{state['err']}")
            return cdp.evaluate("window.__axe.res")
        time.sleep(0.5)
    raise RuntimeError("axe.run 超时")


def wait_dom_quiet(cdp: Cdp, window_ms: int = 1200, rounds: int = 3) -> dict:
    """等首屏挂载落定再扫，否则结果不可复现。

    实测教训（本脚本第一版）：固定 `sleep(0.6)` 会让同一个页面两次扫描报出不同的
    违规——笔记页的 CodeMirror、导出页的 Markdown 渲染都是异步挂载的，扫早了漏报、
    扫晚了多报。而「等 DOM 完全静止」也不可行：笔记页的 cm-content 一直在改属性，
    永远静不下来。

    所以口径是「观察一个时间窗口，统计变更次数」，并把实测值写进结果——门可以接受
    合理的变动，但必须留下证据，而不是靠一个魔数 sleep 蒙过去。
    注意**不能用 requestAnimationFrame 计时**：headless 下没有合成器帧，rAF 会被
    节流到根本不触发（本脚本第二版就因此卡死了一半页面）。
    """
    observed: list[dict] = []
    for _ in range(rounds):
        out = cdp.evaluate(f"""new Promise(resolve => {{
          let n = 0;
          const mo = new MutationObserver(list => {{ n += list.length; }});
          mo.observe(document.documentElement,
            {{childList: true, subtree: true, attributes: true, characterData: true}});
          const t0 = Date.now();
          setTimeout(() => {{
            mo.disconnect();
            resolve({{mutations: n, elapsed: Date.now() - t0}});
          }}, {window_ms});
        }})""", await_promise=True)
        if not out:
            raise RuntimeError("等 DOM 落定时页面没回话")
        observed.append(out)
        # 空页面/纯静态页面一轮就够；仍在持续挂载（如列表批量渲染）才再等一轮
        if out["mutations"] <= 40:
            break
    return {"samples": observed, "settle_ms": sum(o["elapsed"] for o in observed),
            "mutations": sum(o["mutations"] for o in observed)}


def scan_page(cdp: Cdp, url: str, theme: str, axe_src: str,
              state: dict | None = None, upload_file: Path | None = None,
              exclude: list[str] | None = None) -> dict:
    """扫一个页面的一种状态。

    `state` 来自 `ROUTE_STATES` 的一项：`js` 是在扫描前要执行的页面脚本（点筛选、
    填关键词、切页签），`files` 为真表示要往文件框塞真实文件（走 CDP 的
    `DOM.setFileInputFiles`，见 `Cdp.set_file_input`）。**默认态之外的状态不扫出来，
    就等于默认这些状态没有可访问性问题**——v0.16 就是在这一步上失守的。
    """
    state = state or {"name": "默认态"}
    # 一次扫描 = 一个全新 target。同一 target 连导航到第 3～4 次页面会被判成隐藏，
    # axe 提前退出给出假的「0 violation」（见 Cdp.close_target 的说明）。
    # 主题在 open_target 里用 addScriptToEvaluateOnNewDocument 注入，**必须在建 target
    # 时就把 theme 传进去**——晚一步就是在测假页面（见 Cdp.open_target 的说明）。
    cdp.close_target()
    cdp.open_target(theme)
    cdp.drain()
    cdp.send("Page.navigate", {"url": url})
    cdp.wait_ready()
    # 只校验，不再补写：注入脚本若没生效，说明这个门的主题注入坏了，必须报错而不是
    # 手动把 dark 类贴上去假装成功。
    want_dark = theme == "dark"
    deadline = time.time() + 15
    while time.time() < deadline:
        if cdp.evaluate(f"document.documentElement.classList.contains('dark') === {str(want_dark).lower()}"):
            break
        time.sleep(0.3)
    else:
        raise RuntimeError(f"主题没切到 {theme}（addScriptToEvaluateOnNewDocument 注入未生效）")

    # 把页面推进到目标状态。主题先切，状态后设：切主题只是改 class，设状态会触发
    # 请求/渲染，顺序反了就要多等一轮。
    state_applied = "default"
    if state.get("files"):
        if not upload_file or not upload_file.is_file():
            raise RuntimeError(f"状态「{state['name']}」需要样例文件，但没提供")
        state_applied = cdp.set_file_input(
            'input[type="file"]', [str(upload_file)])
        if state_applied != "ok":
            raise RuntimeError(f"文件框没找到（{state_applied}），无法进入已选文件态")
    elif state.get("js"):
        out = cdp.evaluate(state["js"])
        if out not in (None, "ok"):
            raise RuntimeError(f"状态「{state['name']}」没设成：{out}")

    # 网络与 DOM 必须**都**静下来。导出页的 Markdown 预览由 md-editor-v3 的懒加载
    # chunk 渲染，只等 DOM 会在 chunk 到达前就收工——页面上一个 code 元素都没有，
    # axe 扫出「0 violation」，于是同一份代码两轮跑出两种结论。
    settle_rounds: list[dict] = []
    elements = 0
    for _ in range(3):
        net = cdp.wait_network_idle()
        quiet = wait_dom_quiet(cdp)
        settle_rounds.append({"net": net, "dom": quiet})
        before = elements
        elements = cdp.evaluate(
            "document.querySelectorAll('*').length") or 0
        if not net.get("timed_out") and elements == before:
            break

    cdp.evaluate(axe_src)                 # axe-core 是 UMD，注入即挂到 window.axe
    if not cdp.evaluate("typeof window.axe !== 'undefined'"):
        raise RuntimeError("axe 注入失败")
    # 扫的那一刻页面长什么样，必须留证据。没有它，两轮结论不同就只能靠猜。
    vis = cdp.ensure_visible()
    probe = cdp.evaluate("""(() => ({
        code: document.querySelectorAll('code').length,
        mdEditor: document.querySelectorAll('.md-editor').length,
        radioInner: document.querySelectorAll('.el-radio-button__inner').length,
        radioActive: document.querySelectorAll('.el-radio-button.is-active').length,
        uploadItems: document.querySelectorAll('.el-upload-list__item').length,
        floatingBall: document.querySelectorAll('.floating-ball').length,
        // md-editor 自己的主题（dataset.theme）。html 上贴了 dark 不代表组件也是暗的，
        // 两者不一致时扫出来的颜色是凭空的（见 Cdp.open_target 的说明）。
        mdThemes: [...document.querySelectorAll('.md-editor')].map(e => e.dataset.theme || null),
        hidden: document.hidden === true || document.visibilityState === 'hidden',
        paperBg: (() => {
          const p = document.querySelector('.md-editor.paper');
          return p ? getComputedStyle(p).backgroundColor : null;
        })(),
      }))()""")
    # 被排除的选择器命中多少个节点，也要留证：排除本身必须可审计
    excluded_hits = {sel: cdp.evaluate(
        f"document.querySelectorAll({json.dumps(sel)}).length") or 0
        for sel in (exclude or [])}
    res = run_axe(cdp, exclude=exclude)
    res["settle"] = {
        "rounds": settle_rounds,
        "elements": elements,
        "probe": probe,
        "state": state["name"],
        "state_applied": state_applied,
        "visibility": vis,
        "excluded": excluded_hits,
        # 主题到底是怎么生效的：值必须来自注入，不是事后补写
        "theme_injected": theme,
        "theme_script_id": getattr(cdp, "theme_script_id", None),
        # 一旦网络超时没静下来，这组结果就不可信：宁可报「扫失败」也不能假装绿
        "timed_out": any(r["net"].get("timed_out") for r in settle_rounds),
    }
    if res["settle"]["timed_out"]:
        left = next((r["net"].get("inflight") for r in settle_rounds
                     if r["net"].get("timed_out")), None)
        raise RuntimeError(f"网络未在超时前静下来，拒绝用这次结果判定"
                           f"（始终未完成的请求：{left}）")
    # 同一个坑的第二道闸：页面不可见时 axe 会静默跳过大半规则，`passes` 桶空掉，
    # 结论跟「真的没违规」长得一模一样。不校验这一点，这个门会在不确定的时候报绿。
    if probe.get("hidden"):
        raise RuntimeError("页面被判为不可见（document.hidden），axe 结果不可信")
    return res


# ───────────────────────────── 主流程 ─────────────────────────────
def main() -> int:
    # Windows 控制台默认 GBK，本脚本输出含 ✓/✗ 会 UnicodeEncodeError 把结论吞掉
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="G4 axe 可达性扫描（msedge + CDP）")
    ap.add_argument("--theme", choices=["light", "dark", "both"], default="both")
    ap.add_argument("--only", help="只扫该路由（可写模板 /notes/{item_id} 或页名「设置」）")
    ap.add_argument("--json", help="结果 JSON（一般放 output/v017/g4.json）")
    ap.add_argument("--exclude", action="append", default=[],
                    metavar="SELECTOR",
                    help="显式排除的 CSS 选择器（可多次）。被排除的选择器与命中数"
                         "会写进 JSON，绝不静默跳过")
    ap.add_argument("--keep", action="store_true", help="扫完不删临时数据目录")
    args = ap.parse_args()

    edge = find_edge()
    if not VENV_PY.is_file():
        raise SystemExit(f"[G4] 找不到后端 venv：{VENV_PY}")
    if not AXE_JS.is_file():
        raise SystemExit(f"[G4] 找不到 axe-core：{AXE_JS}（在 frontend/ 下 npm i 即可）")
    check_dist()

    themes = ["light", "dark"] if args.theme == "both" else [args.theme]
    tmp = Path(tempfile.mkdtemp(prefix="vm-a11y-"))
    backend = Backend(tmp)
    edge_proc = None
    cdp = None
    results: list[dict] = []
    failures: list[str] = []
    unclaimed: list[str] = []        # 没登记处置的 serious——不能红着交付
    unaccepted: list[str] = []       # 登记为「修」但扫描里仍在——修复没进被扫的那份构建
    accepted: list[str] = []         # 登记为「接受」且写明理由

    try:
        print(f"[G4] 起后端（临时数据目录 {tmp}）…")
        backend.start()
        ids = backend.seed()
        print(f"[G4] 样例已就绪：batch={ids['batch_id']} video={ids['video_id']} "
              f"item={ids['item_id']}")

        profile = tmp / "edge-profile"
        port = free_port()
        edge_proc = subprocess.Popen(
            [str(edge), "--headless=new", f"--remote-debugging-port={port}",
             f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
             "--disable-gpu", "--hide-scrollbars",
             # 扩展是假绿的第二个来源（2026-11-21 实测）：临时 profile 里 msedge 会在
             # 开扫期间**装并加载扩展**，Tampermonkey / 各种助手随即弹出自己的页面把
             # 前台抢走，我们的页于是 `document.hidden = true`，axe 提前退出报假绿。
             # `--disable-extensions` 只是"尽量"，这组开关一起上才干净。
             "--disable-extensions", "--disable-component-extensions-with-background-pages",
             "--disable-background-timer-throttling",
             "--disable-renderer-backgrounding",
             "--disable-backgrounding-occluded-windows",
             "--disable-features=Translate,BackForwardCache,AcceptCHFrame",
             "--no-service-autorun", "--password-store=basic", "--use-mock-keychain",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
                    ws_url = json.load(r)["webSocketDebuggerUrl"]
                break
            except Exception:                                      # noqa: BLE001
                time.sleep(0.4)
        if not ws_url:
            raise SystemExit("[G4] msedge 的 CDP 端口没开")
        cdp = Cdp(ws_url)
        # 不预先开 target：每一页各开一个新的（见 scan_page），否则同 target 连导航
        # 到第 3～4 次会被判成隐藏，axe 给出假的「0 violation」。
        axe_src = AXE_JS.read_text(encoding="utf-8")
        # 上传页「已选文件态」要真实文件。放临时目录里，不进仓库。
        upload_file = tmp / "a11y_sample.mp4"
        upload_file.write_bytes(b"\x00" * 32)

        for theme in themes:
            for route in ROUTE_STATES:
                tpl, title = route["tpl"], route["title"]
                if args.only and args.only != tpl and args.only != title:
                    continue
                path = tpl.format(**ids)
                url = backend.base + path
                for state in route["states"]:
                    label = f"{title}·{state['name']}"
                    try:
                        res = scan_page(cdp, url, theme, axe_src,
                                        state=state, upload_file=upload_file,
                                        exclude=args.exclude)
                    except Exception as exc:                        # noqa: BLE001
                        failures.append(f"{theme} {path} [{state['name']}]: 扫描失败 {exc}")
                        print(f"  ✗ {theme:5s} {label:20s} {path}  扫描失败：{exc}")
                        continue
                    violations = res.get("violations") or []
                    blocking = [v for v in violations if v.get("impact") in BLOCKING]
                    results.append({
                        "theme": theme, "path": path, "title": title,
                        "state": state["name"],
                        "state_note": state.get("note"),
                        "violations": [{
                            "id": v.get("id"), "impact": v.get("impact"),
                            "nodes": len(v.get("nodes") or []),
                            "help": v.get("help"),
                            # 处置：修 or 接受+理由。没登记就是未处置。
                            "disposition": DISPOSITIONS.get(
                                (theme, tpl, state["name"], v.get("id"))),
                            # 定位到元素与差值：报缺陷时下游要能直接照着复现
                            "detail": [{
                                "target": n.get("target"),
                                "html": (n.get("html") or "")[:200],
                                "summary": (n.get("failureSummary") or "")[:400],
                                "data": n.get("any", [{}])[0].get("data")
                                if n.get("any") else None,
                            } for n in (v.get("nodes") or [])],
                        } for v in violations],
                        "blocking": len(blocking),
                        # 落盘时带上「扫的时候页面长什么样」，两轮结论不同才能对账
                        "settle": res.get("settle"),
                    })
                    mark = "✓" if not blocking else "✗"
                    print(f"  {mark} {theme:5s} {label:20s} {path}  "
                          f"violation={len(violations)} blocking={len(blocking)}")
                    if blocking:
                        for v in blocking:
                            disp = DISPOSITIONS.get((theme, tpl, state["name"], v.get("id")))
                            tag = f"［{disp['action']}］" if disp else "［未处置］"
                            failures.append(
                                f"{theme} {path} [{state['name']}]: {v.get('id')} "
                                f"({v.get('impact')}, "
                                f"{len(v.get('nodes') or [])} 节点) {tag} — {v.get('help')}")
                            if not disp:
                                unclaimed.append(
                                    f"{theme} {path} [{state['name']}] {v.get('id')}")
                            elif disp["action"].startswith("接受"):
                                accepted.append(
                                    f"{theme} {path} [{state['name']}] {v.get('id')} — "
                                    f"{disp['reason']}")
                            else:
                                unaccepted.append(
                                    f"{theme} {path} [{state['name']}] {v.get('id')} — "
                                    f"{disp['action']}")
    finally:
        if cdp:
            cdp.close()
        if edge_proc and edge_proc.poll() is None:
            edge_proc.terminate()
            try:
                edge_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                edge_proc.kill()
        backend.stop()
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print(f"[G4] 临时数据保留在 {tmp}")

    print()
    scanned = len(results)
    blocking_total = sum(r["blocking"] for r in results)
    planned = [(theme, route, state) for theme in themes for route in ROUTE_STATES
               if not args.only or args.only in (route["tpl"], route["title"])
               for state in route["states"]]
    printed = {f"{theme} {route['tpl'].format(**ids)} [{state['name']}]"
               for theme, route, state in planned}
    got = {f"{r['theme']} {r['path']} [{r['state']}]" for r in results}
    # 未覆盖清单：声明了要扫、实际没扫成的，逐个列出来。门不能靠「没扫到」冒充「没问题」。
    uncovered = sorted(printed - got)
    print(f"[G4] 扫描 {scanned} 组（{len(themes)} 主题 × {len(ROUTE_STATES)} 页 × 声明状态数）· "
          f"serious/critical {blocking_total} 处 · 失败 {len(failures)} 处 · "
          f"未覆盖 {len(uncovered)} 组")
    for f in failures:
        print(f"  ✗ {f}")
    if uncovered:
        print("[G4] 未覆盖清单（这些状态**没扫成**，不代表没问题）：")
        for u in uncovered:
            print(f"    · {u}")

    # 已登记的处置要逐条打出来：修好的应该消失，没消失就是「说了修、其实没修」。
    if unaccepted:
        print("[G4] 登记为「已修」但仍扫到（修复没进被扫的那份构建？）：")
        for u in unaccepted:
            print(f"    · {u}")
    if accepted:
        print("[G4] 已接受的违规（理由见 DISPOSITIONS）：")
        for a in accepted:
            print(f"    · {a}")
    if unclaimed:
        print("[G4] 未处置：serious 违规必须登记修/接受，直接红着交付不算处置：")
        for u in unclaimed:
            print(f"    · {u}")

    if len(results) < len(planned):
        print(f"[G4] 失败：{len(planned) - len(results)} 组没扫成（见上面的未覆盖清单）")
        code = 1
    elif unclaimed:
        print("[G4] 失败：有 serious 违规没登记处置")
        code = 1
    elif unaccepted:
        print("[G4] 失败：有登记为「已修」的违规仍扫到")
        code = 1
    else:
        print("[G4] 通过：亮/暗全部页面与声明状态无未处置的 serious/critical"
              f"（已接受 {len(accepted)} 处，理由见 DISPOSITIONS）")
        code = 0

    # 「导出页亮/暗两态都 0 violation」——组长要单独留的可断言字段。
    # 亮态靠 theme.css 的 data-theme 分流、暗态靠 md-editor 自身主题，是个非对称结构，
    # vitest 在 jsdom 里不算颜色守不住；只能靠这个脚本断言。缺任一态就 False。
    export_key = "/batches/{batch_id}/export"
    export_checks: dict[str, dict] = {}
    for theme in themes:
        found = [r for r in results if r["path"].endswith("/export")
                 and r["theme"] == theme]
        export_checks[theme] = {
            "scanned": bool(found),
            "blocking": sum(r["blocking"] for r in found),
            # 主题必须真的注入到组件，不是 html 上贴个 dark 类糊弄 axe
            "md_themes": [m for r in found
                          for m in ((r.get("settle") or {}).get("probe") or {}).get("mdThemes", [])],
            "ok": bool(found) and all(r["blocking"] == 0 for r in found),
        }
    export_both_ok = (export_checks.get("light", {}).get("ok", False)
                      and export_checks.get("dark", {}).get("ok", False))

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"ok": code == 0, "scanned": scanned,
                                   "planned": len(planned),
                                   "uncovered": uncovered,
                                   "excluded": args.exclude,
                                   "export_both_themes_zero_violation": export_both_ok,
                                   "export_checks": export_checks,
                                   "accepted": accepted,
                                   "unaccepted": unaccepted,
                                   "unclaimed": unclaimed,
                                   "results": results, "failures": failures},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[G4] 结果已写入 {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
