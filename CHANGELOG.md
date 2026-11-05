# 变更记录

> **规则（课程模板硬性要求）**：逐版本、逐人署名，**禁止合注**；工作重合部分用版本迭代区分。
> 每次 PR 合并后，由**提交人自己**补录本人条目（不设专人代写）。
> 格式：`版本 / 日期 / 涉及章节或图 / 作者 / 修改摘要`。

---

## [v0.1] — 2026-11-05

### 仓库与协作基座

- **程夏（组长）**：初始化 Git 仓库与 `main` 分支；编写 `.gitignore`（排除课程材料、视频素材、密钥）、`.gitattributes`（统一 LF 换行与二进制识别）
- **程夏（组长）**：编写 `README.md`（痛点—方案—技术栈—进度—分工—目录结构—合规声明）
- **程夏（组长）**：编写 `CONTRIBUTING.md`（工具统一表、分支模型、提交规范、评审规则、图与文档命名规范、变更记录规则、周会节奏、五条红线）
- **程夏（组长）**：创建 `CHANGELOG.md` 变更记录模板与 `.github/` PR / Issue 模板
- **程夏（组长）**：整理既有规划文档并建立索引（方案收敛 v0.2、分工方案 v2.0、选题调研 v2、毕设主线收敛等）

### 待认领

- **A**：首次提交后补录本人条目（墨刀原型线）
- **B**：首次提交后补录本人条目（UML 建模线）
- **C**：首次提交后补录本人条目（后端与数据线）

---

## [v0.2] — W2（10/30–11/05）

### 仓库文档收敛与选题冻结（2026-11-05 已合入）

- **程夏（组长）**：确定并冻结最终选题「VideoMind 视析」，明确不再讨论换题；重写 `README.md` 为单页导航（30 秒看懂要做什么 / 明确不做 / 进度 / 分工 / 仓库阅读路径）
- **程夏（组长）**：新增 `docs/产品定义.md`——定位、痛点、用户画像、核心链路、B1–B10 基础能力、F1–F5 创新功能包、三个可插拔策略、数据模型（9–10 表）、10 条用例、范围外与诚实边界
- **程夏（组长）**：新增 `docs/交付与排期.md`——评分口径反推、代码作为加分项的定位、范围载体矩阵、12 页原型清单、8+4 张图清单、七周倒排、答辩 PPT 结构、11 条风险清单
- **程夏（组长）**：新增 `docs/分工与任务卡.md`——1 组长 + 3 组员角色总责、W2–W7 逐人任务卡、协作机制、提交前检查单（已修正此前误按 5 角色拆分的问题）
- **程夏（组长）**：`CONTRIBUTING.md` 第五节增加「文档口径优先级」，冲突时以 `docs/产品定义.md` 为准
- **程夏（组长）**：五份过程稿（愿景初稿、选题调研 v2、选题备选、方案收敛 v0.2、分工方案 v2.0）退出仓库跟踪、转为本地留档，并补入 `.gitignore`；同时忽略 `.qoder/` 工具目录

### 仓库权限治理与门禁（2026-11-05 组长直推，按新规留痕）

- **程夏（组长）**：配置 `develop` / `main` 分支保护——PR 需 1 人 review + 组长 Code Owner 批准，禁止 force push 与分支删除；关闭 `enforce_admins`，使组长可直推、组员必须走 PR
- **程夏（组长）**：新增 `.github/CODEOWNERS`，全仓库归口 `@cheng200606`
- **程夏（组长）**：`CONTRIBUTING.md` 第二、四、八节改写为权限矩阵（组长直推须留痕；组员禁止直推，须组长 approve）；`README.md` 第七节与 PR 模板 Reviewer 段同步
- **程夏（组长）**：**绕过留痕**——W2 的 PR #1（→ develop）与 PR #3（→ main）合并当时无人在群内 approve，由组长临时把必需 review 降为 0 完成合并、随即恢复为 1；11-05 起门禁常驻，同类绕过不得再发生

### 待交付（W2 收尾）

- **程夏（组长）**：需求章 v0.5 定稿（用户画像、用例清单、F1–F5 新增用例）
- **A**：原型信息架构 + 12 页低保真线框
- **B**：图 1 用例图、图 2 活动图（SVG 矢量）
- **C**：可行性分析章初稿 + 辅图 1 技术路线图

> 模板：每人只写自己的条目，逐条署名，不合注。

---

## [v0.3] — W2 收尾开发冲刺（2026-11-05/06）

### 垂直切片阻断修复（组长直推，按新规留痕；commit 9dadcaf..a75f0c6）

- **程夏（组长）**：`.gitignore` 补 `backend/data/`（运行时库/上传落盘/缓存/设置快照）、`backend/tests/.pytest_tmp/`、`.zcode/`——运行时数据与工具目录不入库（红线 1 加固）
- **程夏（组长）**：修复 SSE 进度端点——路由补 `response_class=EventSourceResponse`（此前输出 application/jsonl，浏览器 EventSource 收不到），订阅先探测批次终态，页面刷新重连即补推终态并收流，不再空转 ping
- **程夏（组长）**：解析幂等——`parse_video` 入口按外键依赖清空该视频上次派生数据，重试/整批重跑不再使转写与条目翻倍；补重跑两次行数不翻倍断言
- **程夏（组长）**：证据帧可达——关键帧统一复制进 `media_root/frames/{video_id}/` 再落缓存，`Evidence.frame_path` 存 `/media` URL（此前真实引擎的帧写在临时目录，前端不可达、重启后缓存路径失效）；冲突记录改挂离 source_a 时间点最近的条目
- **程夏（组长）**：引擎设置持久化——`PUT /api/settings/engines` 落盘 `data/settings.json`，lifespan 启动读回，重启不丢（不新增 ER 表）
- **程夏（组长）**：上传反馈——响应带回 rejected 清单（格式不支持/批内重复），前端弹提示，非法文件不再静默丢弃
- **程夏（组长）**：后端小修四处——LLM 代码围栏剥离正则化（容错大小写与前置文字）；`GET /tags` 支持目标过滤返回 bound 标记；标签再绑一次视为「采纳」；讲义修订空跳转 422 拒绝；`type` 参数改别名不遮蔽内建
- **程夏（组长）**：前端工具链修正——typescript 由 7.0.2（Go 原生版，无 lib/tsc JS API）降到 6.0.3 兼容 vue-tsc 3.3.14；tsconfig 移除已弃用 baseUrl；`package-lock.json` 首次入库；补 @vue/test-utils 与 jsdom，vitest 环境接入 vite.config
- **程夏（组长）**：前端补 B5/B6 入口——视频库页新增「跨视频检索」折叠区（标签+关键词过滤条目，点行跳工作台）；工作台产物面板新增标签条（AI 建议可采纳/驳回、手动绑定）；工作台三接口并行加载并补失败错误态
- **程夏（组长）**：前端小修——SSE 连接生命周期挂到进度页 onUnmounted（原挂在根组件泄漏）；导出页检查 resp.ok 给错误态；证据抽屉直读 /media 帧 URL；el-upload 类型按 UploadRawFile 收窄；空产物文案改指上传页解析参数区
- **程夏（组长）**：测试补齐——后端新增 SSE 终态流与上传 rejected 断言（12 例全绿）；前端新增 vitest 单测 8 例（client URL 拼装 / ConfidenceTag 三档映射 / 批次 store 终态刷新），`npm run test` 首次真实通过；`npm run build`（vue-tsc + vite）与本地 uvicorn+vite 冒烟全链路验证通过

### 待交付（不动原排期）

- **B**：W4 解析链路 demo——`yueying==0.2.1 → DeepSeek → 结构化 JSON`，2 条视频跑通 + 2 种产物（本冲刺未装重引擎、未配 Key，全链路走 mock/fallback 兜底）
- **A / C**：W3 图与章节交付物按原任务卡推进

---

## [v0.4] — W2 收尾迭代 2：演示完整度与健壮性（2026-11-06）

### 组长直推，按新规留痕

- **程夏（组长）**：上传全拒不再落空批次——422 带回逐文件原因（格式不支持/批内重复），前端拦截器直接提示
- **程夏（组长）**：`Video.error` 多阶段失败改为换行累加不覆盖，失败定位仍以四阶段状态矩阵为准
- **程夏（组长）**：跨视频检索新增置信度过滤（`explicit / inferred / low`，非法值 422）——F4「按可信度找条目」前后端贯通
- **程夏（组长）**：LLM 代码围栏块改全文正则提取，容错 JSON 前后的说明性文字，减少一次无效重试调用
- **程夏（组长）**：证据抽屉新增 F2 冲突提示条——条目详情先占位后补拉，`ConflictRecord` 此前只在导出文稿渲染，前端首次可见
- **程夏（组长）**：知识要点 tab 新增「只看易错点」过滤（F3，按 `payload.pitfall`），筛选无结果给占位文案
- **程夏（组长）**：进度页新增「整批重跑」按钮，接通一直未接线的 `reparseBatch`（后端 v0.3 幂等保障不翻倍）
- **程夏（组长）**：测试 12 → 23 例全绿——新增 `test_llm.py`（围栏大小写/前后闲话/垃圾输入、fallback 形状、无 Key 断言）、冲突锚点就近、标签采纳与驳回语义、HTTP 整批重跑幂等、全拒 422、置信度过滤；前端 vue-tsc / vitest / build 回归通过；uvicorn 冒烟（422 带原因、置信度 12 命中、真实后台重跑条目 14→14）通过

---

## [v0.5] — W2 收尾迭代 3：桌面发行版与自动更新（2026-11-06）

### 目标：GitHub Release 可下载安装包，运行软件，内置自动更新（组长直推，按新规留痕）

- **程夏（组长）**：后端产物化——新增 `backend/run_server.py` 桌面入口（环境变量先行：端口/数据目录/包内 fixtures，再 import app）；`app/main.py` 挂 SPA 同源路由（打包态读包内 `frontend_dist`，历史路由回落 index.html，注册顺序保证不吞 `/api`）
- **程夏（组长）**：PyInstaller 打包后端 sidecar——`VideoMindBackend.spec` 入库（onedir，datas：tests/fixtures → app_fixtures、frontend/dist → frontend_dist，hiddenimports：uvicorn 全家），构建依赖单列 `requirements-build.txt`（pyinstaller 6.22.3）；打包产物独立验证：health / SPA 首页 / 历史路由 / 包内 fixture 四阶段解析 14 条目
- **程夏（组长）**：新增 `desktop/` Electron 壳——main.js 选空闲端口 → 拉起 `resources/backend/VideoMindBackend.exe` → 轮询健康 → BrowserWindow 加载同源页面；单实例锁、进程随窗口退出、日志落 `%APPDATA%/VideoMind/data/logs`
- **程夏（组长）**：内置自动更新——electron-updater 6.8.11 + electron-builder 26 的 GitHub Releases 通道（cheng200606/videomind），启动检查、autoDownload、autoInstallOnAppQuit，更新事件全量落 updater.log
- **程夏（组长）**：NSIS 安装包构建与发布——`VideoMind-Setup-0.5.0.exe`（183MB，含后端 sidecar 与前端）+ latest.yml + blockmap 发布至 Release v0.5.0；Pillow 生成应用图标（desktop/resources/icon.ico）
- **程夏（组长）**：v0.5.1 验证自动更新 E2E——静默安装 0.5.0 → 启动检测到 0.5.1 → **blockmap 差分下载仅 736KB**（全量 179MB）→ 优雅退出静默安装 → ProductVersion 升至 0.5.1.0；两个 Release 均已公开可下载
- **程夏（组长）**：conftest 测试库一次性（标签采纳/驳回跨运行污染断言的根因修复，23 例保持全绿）；`.gitignore` 补 `desktop/release/`
- **程夏（组长）**：构建网络策略——Electron 与 builder 二进制走 npmmirror 镜像（`ELECTRON_MIRROR` / `ELECTRON_BUILDER_BINARIES_MIRROR`），GitHub 只承担 Release 发布

### 后续（v0.5.x 候选）

- **C**：安装包代码签名（消除 SmartScreen 提示）；设置页 Key 配置写入数据目录 .env
- **A**：桌面版关于页 / 更新进度条 UI
