# VideoMind 视析 · 视频知识结构化平台

> **一批视频进去，一份可溯源、可检索、可导出的知识库出来——不用看完就知道里面讲了什么**
>
> 软件工程课程项目 · 4 人小组（1 名组长 + 3 名组员）· 交付截止 **2026-12-11**
> **选题已于 2026-11-05 冻结，不再讨论换题。** 本文是导航，细节看 `docs/`。

---

## 一、30 秒看懂要做什么

给**知识/讲解类视频**（技术教程、产品演示、系统介绍、课程录播、需求访谈）做批量结构化。它们信息密度高但只能线性播放，我们的解法：

```
批量导入本地视频（一个批次 = N 条）
   ├─ 音频通道：ASR 转写 → 带时间轴字幕
   └─ 画面通道：关键帧抽取 → OCR 识别代码/文字   ← 双通道策略模式
        ↓
   LLM 结构化解析 → 章节 · 知识条目 · 代码块
        ├─ 产物可插拔：UML 草稿 / 内容总结 / 知识点要点 / 代码块
        ├─ 证据溯源：每条结论带 时间戳 + 原话 + 来源片段 + 置信度
        └─ 两层标签：视频级 / 条目级，AI 建议 + 人工采纳
             ↓
   视频库 · 跨视频检索 · 溯源回看 → 导出批次级 Markdown 文稿
```

**不是"把视频变成文字"，而是把一批视频变成带证据链的结构化知识资产。核心差异化三个词：可信、可查、可带走。**

AI 生成的字幕、代码块、知识点、UML 草稿与总结均为**识别结果仅供参考**，不保证正确；文稿会自带解析覆盖提示，标注可能缺失的内容区间。

---

## 二、明确不做

用户注册与权限 · 部署上云 · 并发任务队列与队列持久化 · 向量语义检索 · 推荐与社区 · 在线代码沙盒 · B 站视频下载 · 知识图谱自动推理

> 这些全部**进原型、不进代码**或直接排除，理由见 `docs/交付与排期.md` 第三节「范围载体矩阵」。解析为顺序处理，同一时间只允许一个批次解析，SSE 进度存于进程内存。

---

## 三、技术栈（与当前实现一致）

| 层 | 选型 |
| --- | --- |
| 前端 | Vue 3 + Vite + TypeScript + Element Plus（按需引入）+ Pinia；播放器为原生 `<video>` + 自绘证据刻度条，不引播放器库 |
| 后端 | FastAPI + SQLModel + pydantic-settings；默认本地 SQLite，可通过 `DATABASE_URL` 接 MySQL |
| ASR 策略 | `faster-whisper`（本地）/ `yueying==0.2.1`（锁版本）/ FunASR / mock 演示样例；`ASR_ENGINE=auto` 按实际依赖可用性选择 |
| 画面通道 | `av` 独立关键帧抽样（16×16 灰度均值差去重）+ RapidOCR / PaddleOCR / 视觉模型 / 关闭 |
| 结构化 | DeepSeek 或任意 OpenAI 兼容模型（httpx 直连 OpenAI 兼容协议，**不用 openai SDK**）；长转写按段边界分块后合并 |
| 产物策略 | `OutputSchemaStrategy` 可插拔：内容总结 / UML 草稿（Mermaid）/ 知识要点 / 代码块 |
| 进度推送 | SSE（`ProgressBus`，进程内内存总线），四阶段状态矩阵 + 单条重试 |
| 交付形态 | 桌面版 Electron + PyInstaller sidecar（NSIS 安装包 + 便携 ZIP）；另提供 Docker Compose 与源码前后端分离运行 |

> `backend/requirements.txt` 只装轻量主依赖；重引擎单列在 `requirements-engines.txt`，桌面发行版内置 Whisper 与 RapidOCR 运行时。

---

## 四、当前进度

| 线 | 状态（2026-11-13） |
| --- | --- |
| 代码线（组长） | **v0.13 已完成**：上传 → 四阶段解析 → 证据溯源 → 检索 → 笔记/讲义 → Markdown 导出全链路可用；桌面发行版线上最新 Release **v0.12.0**（v0.13 只迭代代码，未发 Release） |
| 回归基线 | 后端 pytest 99 例、前端 vitest 38 例全绿；`npm run build`（vue-tsc + vite）通过 |
| 文档 / UML / 原型线（组员） | 按 `docs/分工与任务卡.md` 的 W2–W7 任务卡各自推进；进度以周会纪要为准，本文不代为标注 |
| 交付节奏 | W1–W7 倒排与硬节点见 `docs/交付与排期.md`；最终交付 2026-12-11 |

版本逐条留痕见 `CHANGELOG.md`；测试与迭代结论见 `docs/测试与迭代报告_v0.7.md` / `_v0.8.md` / `_v0.11.md` / `_v0.12.md` 与 `docs/迭代方案_v0.13.md`。

**文档口径优先级**（冲突时按序）：`docs/产品定义.md` → `docs/交付与排期.md` → `docs/分工与任务卡.md` → 本文件。

---

## 五、谁干什么

| 成员 | 负责 | 对应评分项 |
| --- | --- | --- |
| **组长（程夏）** | 需求规格主笔 · 文档统稿排版 · 代码线实现与发布 · 过程管理 · 答辩主讲 | 过程 20 / 排版 15 / 汇报 10 |
| **A** | 墨刀 12 页高保真原型 · 前端切片 · PPT 制作 | 原型 25 |
| **B** | UML 图 1–4 + 图 7 状态机 · 解析链路 | 需求·设计 25 |
| **C** | 类图 / ER 图 / 部署图 · 后端 · 可行性分析 | 设计 25 |

> 讨论记录全员轮值（A→B→C→组长），每周日 30 分钟周会，纪要直接归档为课程「小组讨论记录」。

---

## 六、仓库怎么读

```
.
├── README.md                    本文件：导航 + 30 秒看懂
├── CONTRIBUTING.md              协作规约（分支/提交/评审/红线）—— 提 PR 前必读
├── CHANGELOG.md                 变更记录（逐版本逐人署名，禁止合注）
├── AGENTS.md                    本机开发速查（按团队政策不入库）
├── backend/                     FastAPI 垂直切片
│   ├── app/routers/             parse / knowledge / delivery / settings（/api 前缀）
│   ├── app/pipeline.py          四阶段主链路 + 单条重试 + SSE 进度
│   ├── app/engines/             ASR / OCR 策略注册表与适配器
│   ├── app/llm.py               分块结构化与运行时模型配置
│   └── tests/                   pytest 用例
├── frontend/                    Vue 3 + Vite（9 视图 / api 契约 / 组件 / 组合式函数）
├── desktop/                     Electron 壳 + IPC 桥 + NSIS/ZIP 构建与发布脚本
├── docs/                        权威口径文档、迭代方案、测试报告、发布方案
└── docker-compose.yml           可选容器运行方式
```

**新组员上手路径**：读本页 → 读 [docs/产品定义.md](docs/产品定义.md) 确认自己那条线要交付什么 → 读 [docs/分工与任务卡.md](docs/分工与任务卡.md) 里自己那一列 → 按 [CONTRIBUTING.md](CONTRIBUTING.md) 开分支提 PR。

> 常用命令（后端 pytest / uvicorn、前端 dev/build/test、桌面打包与发布）见 `AGENTS.md` 与 `docs/桌面版发布方案.md` §八。

---

## 七、协作方式（详见 CONTRIBUTING.md）

- 分支模型：`feature/<姓名>-<topic>` → PR → **`develop`（集成测试分支）** → 每周版本冻结 → `main`
- **权限（GitHub 分支保护 + CODEOWNERS 已强制）**：组员禁止直推 `develop` / `main`，PR 必须由**组长 Approve** 才能合并；组长可直推，但要在 `CHANGELOG.md` 留痕
- 提交信息：Conventional Commits（如 `feat(design): 类图新增 OutputSchemaStrategy 抽象`），scope ∈ {design, prototype, frontend, backend, parse, docs}
- **变更记录逐版本、逐人署名，禁止合注**；每次 PR 合并后由提交人自己补录本人条目
- 图源文件（draw.io / PlantUML）入库，导出物必须是 SVG 矢量，禁止 PNG 代替结构图

---

## 八、合规声明

- 本项目为**软件工程课程作业**，仅供学习与教学交流
- **不提供视频下载、不留存、不分发**任何第三方视频内容；平台仅处理用户本地视频
- AI 生成内容（字幕、代码块、知识点、UML 草稿、总结）**识别结果仅供参考**，不保证正确
- 课程评分标准等他人材料不在本仓库中；API Key 只落本机 `backend/data/model_settings.json`，不入库

---

## 九、桌面版下载与更新

**[下载最新安装包 →](https://github.com/cheng200606/videomind/releases/latest)** 每个 Release 提供两个附件：`VideoMind-Setup-x.y.z.exe`（NSIS 安装版）与 `VideoMind-x.y.z-win.zip`（便携版，解压即用，适合无安装权限的机器）。

- 安装包内置 Python 后端 sidecar、本地 Whisper（faster-whisper tiny）与 RapidOCR 运行时，无需另配 Python 环境
- 内置演示样例（mock）无需 API Key 即可走通四阶段流程；**mock 只回放同名内置样例，不读取真实视频内容**。处理自己的视频请使用内置 Whisper 引擎，并在「设置 → 模型」填写 DeepSeek 或 OpenAI 兼容模型的 API Key；未配置时走无 Key 兜底，结论质量会下降
- 更新为**手动流程**：应用启动静默检查一次，用户在「设置 → 应用更新」自行点「检查更新 / 下载更新 / 重启并安装」。实测 NSIS blockmap 差分对独立构建退化为全量下载，故按全量通道预期；详见 [docs/桌面版发布方案.md](docs/桌面版发布方案.md)
- 数据目录 `%APPDATA%\VideoMind\data`，日志在同目录 `logs/`（backend.log / updater.log）；便携版可设 `VMIND_APP_DATA_DIR` 隔离，两版不要同时运行
- 源码构建：`backend/` 跑 `pyinstaller VideoMindBackend.spec` → `desktop/` 跑 `npm run dist`（详见 `desktop/` 与 CHANGELOG v0.5；发布操作手册见发布方案 §八）

## 十、许可

MIT License — 见 [LICENSE](LICENSE)。
