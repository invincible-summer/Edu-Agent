# Next Tutor Agent

面向小学 / 初中 / 高中 / 本科阶段学生的智能学习 Agent。不是问答机器人，而是构建「学习目标 → 知识理解 → 练习训练 → 能力评估 → 调整」完整学习闭环的长期陪伴式私人学习智能体。架构主文档见 [docs/DESIGN.md](docs/DESIGN.md)（模块职责 / 数据流 / 接口契约 / 存储布局）。

## 特性

- **流式对话（SSE）**：实时推送思考过程 + 回答增量 + 工具进度；前端 token 本地累积 + 50ms 节流 flush（React.memo + pinned 滚动），流式丝滑不卡顿。
- **Supervisor 编排（M1）**：意图理解 → 规划 → Skill 路由 → ReAct 工具执行 → 状态更新；硬性 `max_steps` 防死循环，参数校验 / 反射器 / 熔断器 / 截断落盘全套护栏。
- **学习能力运行时（M10）**：Agent Skill 与知识图谱中的学习 Skill 分命名空间管理；Manifest/Registry 统一声明版本、前置条件、成功标准、fallback、风险与成本。支持 `shadow` 旁路评估与 `gated` 强制执行；`start.sh` 默认进入 gated 完整模式，执行前检查前置条件、缺参考题时最小澄清、按计划步骤逐个暴露工具，并用学习证据门保护 M4→M2 掌握度写回。动态 Prompt 只注入本轮计划 Skill Card；教学策略要求收尾检测时会把 `generate_quiz` 连同结构化参数加入计划，模型漏调时由执行器按授权计划确定性补执行。SessionLearningCard 把当前目标、教学模式、未完成检测和最近证据投影成有界工作上下文，但不复制 M2 掌握度或 M6 长期记忆。
- **上下文与推理运行时**：64K 平衡档按 Provider 能力、工具 schema、原生 Tool Message 和安全区逐调用核算输入/输出；历史按完整回合增量压缩，压缩输入注入确定性出题/作答摘要（「练习与错题」不再无米下锅），旧摘要不会在二次压缩时丢失，空摘要不会裁掉原文。工具决策阶段在预算充足时保留模型思考、预算紧张时优先保答案预算；Provider 只有共享 completion envelope 时以答案通道检测 + 自动直答恢复兜底。前端展示模板过程摘要 + 对真实模型推理的二次提炼（real_summary，原始 CoT 不外露）；“一句话 / 简短 / 不要出题 / 表格 / 分步骤”等学生显式格式约束会压过默认教学展开与策略收尾检测。
- **文件上传 + RAG 混合检索**：PDF / DOCX / PPTX / TXT / MD / 图片自动解析、结构化切块（页边界 + 段落 + 句子吸附），BM25（CJK 分词，常驻）+ 向量（Chroma + 离线本地 MiniLM 或 OpenAI 兼容 Embedding，可选）RRF 融合；跨文件结果先做来源覆盖；工具卡片顶部展示文件、页码/章节等结构化来源。上传/引用/明确要求根据资料时由 R10 确定性预检索，未命中禁止编造。图片直接写入当前会话 KnowledgeStore；扫描/混合 PDF、DOCX/PPTX 嵌入图片走视觉 OCR（配置可用时）并回退本地 tesseract，纯文字文件短路不调用 OCR。
- **练习生成 + 交互批改**：可交互答题卡（先答后揭晓），选择题本地判分并回传掌握度闭环，填空/简答 LLM 流式批改（三级评分 + 思路讲解）；拟合出题（fit_quiz）从参考题生成同考点变式。**出题质量门**：所有出题路径先过确定性结构校验，再经 LLM 独立重解审题（critic），错题/错答案/错解析在投递前丢弃并重生成，校验审计随 Trace 可查。
- **作答全链路可见**：每次作答统一写入会话 quiz_history、transcript【作答记录】与独立 `learning_records` 学习账本；题目、作答、评分、知识点和时间不随来源对话删除。旧 M6 episodic 仅兼容只读，不再新增详细跨聊天事件。
- **教材库（Textbook）**：上传任意教材（≤256MB 大 PDF，扫描版自动逐页 OCR）→ 自动切块索引 + 后台构建专属知识图谱（书签/LLM/确定性目录切片，Unicode 与全角空白容错 / 长章首中末覆盖 / 逐章概念抽取 / DAG 守卫合并 / 概念→chunks 预索引）；长教材无法可靠分章时会明确标记需重建，但全文 RAG 不受影响。上传必选学段（小学/初中/高中/本科/其他），图谱按学段分组。**教材组**：上下册/分册多 PDF 可编为一组（自定义组名），构建**一个**统一知识谱系（跨卷同名概念合并、跨卷前置边、概念索引跨卷），支持追加卷/删卷自动重建。**公用教材库**：管理员上传的教材全账号可选用；知识谱系与教材绑定（删教材即删谱系）。知识图谱**只来自教材**（考纲内置谱系已移除，手动构建已下线）。
- **工作学习区（Workspace）**：类 ChatGPT Projects——跨对话共享教材、工作区直接上传资料与公共记忆，按账号隔离；教材组勾选会展开全部卷；工作区上传文件只在本工作区可检索。
- **资料库（Library）**：按账号隔离的个人资料底座，两级文件夹 + 原件保留 + 任意重新下载；外部资料显式选入工作区时仍只允许教材；对话引用会复制为当前会话私有来源。
- **管理员（Admin）**：`.env` 配置 `ADMIN_EMAIL/ADMIN_PASSWORD` 启动引导管理员；管理台页查看/注销账号；公用教材库上传与管理仅管理员。
- **学段去僵化（P1）**：学段不再硬编码默认「高中」。每个对话可自选学段，不选则「自动」——模型按提问内容/资料自适应深度与语言；显式学段才注入七维度强约束。前端学段选择器会话内切换即持久化。
- **账户体系（M0）**：注册 / 登录 / 登出 / 自助注销（JWT + bcrypt）+ 管理员角色（管理台注销账号、公用教材库）；每用户数据全隔离（会话、工作区、资料库、全部学习数据、图谱 mastery 变色），仅公用教材库共享；游客模式零配置可用。
- **十层智能（M1-M10）**：学生模型（BKT 掌握度）/ 自适应教学引擎（六模式状态机）/ 智能测评（三级评分 + CAT 自适应）/ 知识图谱（教材驱动：公用+自有教材图谱，按学段分组）/ 记忆生命周期（精简提示词画像 + 策略聚合；旧情景/语义兼容只读；工作区共同记忆隔离）/ 评估改进（诊断 + 人工确认改进建议）/ 交互体验适配（因人而异的表达）/ 学习编排（目标 → 周计划 → 今日任务 + SM-2 复习）/ Skill Runtime（契约、决策、证据门）。
- **完整前端（学习工作区）**：Next.js + Tailwind v4「纸墨书院」设计体系（宣纸底/黛青/朱砂，浅深双主题），模块页：对话工作台 / 学习总览 / 知识图谱 / 学习计划 / 学习编排 / 测评中心 / 记忆中心 / 资料中心 / 系统洞察 / 我的画像 / 管理台（仅管理员），外加登录注册页。
- **会话历史**：JSON 持久化于 `chat_history/`，可恢复 / 重命名 / 删除 / 批量删除；轮数口径「一次 agent 回复算一轮」。
- **中英双语 + 主题 + 字号**：设置齿轮切换，偏好持久化；回答语言 auto/zh/en 可选。

## 技术栈

| 层 | 技术 |
|----|------|
| Frontend | Next.js 16 + React + TypeScript + Tailwind CSS v4 + Zustand + lucide-react |
| Backend | FastAPI + Python 3.11 + OpenAI SDK（async streaming） |
| Auth | JWT（PyJWT）+ bcrypt + resolve_student_id 依赖注入（AUTH_MODE 开关） |
| Agent | 自研轻量框架：Supervisor + M10 Skill Registry/Decision/Runtime + ReAct function-calling + 统一工具协议 + Trace |
| 检索 | BM25（常驻）+ 向量（Chroma + 本地 MiniLM/OpenAI 兼容 Embedding，可选），RRF(k=60) 融合 |
| 语音（P10，可选） | 电话式 WebSocket 语音对话 + 可插拔 STT/TTS（默认 `whisper.cpp` + `ggml-small-q5_1.bin` + MeloTTS-Chinese；许可证审计见 `docs/VOICE_LICENSES.md`） |
| 持久化 | JSON 文件（原子写 + 文件锁）+ 磁盘上传文本/原件 |

## 快速开始

### 环境（WSL2 + Miniconda）

```bash
conda create -y -n edu_agent -c conda-forge --override-channels python=3.11 pip
conda activate edu_agent
pip install -r backend/requirements.txt  # 自动应用 backend/constraints.txt
# 完整后端向量回归另装：pip install -r backend/requirements-test.txt
cd frontend && pnpm install
```

### 配置

```bash
cp .env.example .env   # 填入 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，切勿提交 .env
```

默认推荐 DeepSeek 官方 API；可改为任意 OpenAI 兼容端点（OpenAI / GLM / 本地 vLLM 等）。基础 `backend/requirements.txt` 只安装 BM25/OCR/API 运行时，并由 `backend/constraints.txt` 固定生产版本；不会安装 Chroma、NumPy、PyTorch 或 sentence-transformers。可选：安装 `requirements-vector.txt` 或按 `docs/LOCAL_SEMANTIC_RAG.md` 安装 CPU 本地语义依赖后，再用 `EMBEDDING_PROVIDER=local|openai` 启用 RAG 向量轨（默认 `off`，即开箱纯 BM25 检索）。RAG 模型后端走统一 provider 接口（`core/embedding.py`）：跨 provider 的 `embed(texts)` 契约稳定，local（离线 CPU MiniLM）与 openai（OpenAI 兼容端点）只是两个内置实现，新增本地或远端模型后端只需实现同一接口并扩展 `EMBEDDING_PROVIDER` 枚举，任一 provider 故障都自动回退 BM25。`MULTIMODAL_*` 启用视觉识题/OCR（缺省本地 tesseract）。聊天图片上传会先进入当前会话资料库并返回 OCR 预览。

### 运行

```bash
./start.sh        # 一键启动：最新完整运行时 + 自动端口/CORS + 直连网络
```

前端默认**生产模式**（`FRONTEND_MODE=prod`）：按需 `next build` 后 `next start`，页面秒开、Link 预取生效；源码或后端端口变化时自动重建，`REBUILD=1 ./start.sh` 强制重建。前端开发热重载：`./start.sh dev`（等价 `FRONTEND_MODE=dev`，显式覆盖 `.env`）。

分别启动：

```bash
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
cd frontend && NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 npx next dev -p 3000
```

按 `start.sh` 输出访问前端地址（端口可能为 3000/3001/3030）。启动器会把实际前端 Origin 注入后端 CORS；LLM、Embedding、视觉模型均直接连接，不读取系统 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`。 默认启用 `SUPERVISOR_MODE=v2`、`SKILL_RUNTIME_MODE=gated`、`LLM_RUNTIME_MODE=adapter`、工具上下文投影 `on`、原生 Tool Message `native`、自适应过程摘要与前端 `FRONTEND_MODE=prod`；可用显式 shell 或 `.env` 非敏感配置逐层回滚。部署到服务器：同机生产部署手册见 **[`docs/The_Website_deployment_plan.md`](docs/The_Website_deployment_plan.md)**，形态与模板见 DESIGN.md §21.4 与 `deploy/`。

### CLI（调试用）

```bash
cd backend && python cli.py --grade 初中 --once "讲一下惯性"
```

## API 概览（前缀 `/api/v1`）

- **对话**：`POST /chat/stream`（SSE）、`POST /chat/upload`、`GET/PATCH/DELETE /chat/sessions[/{id}]`（详情支持 `?tail=N` 渐进加载）、`POST /chat/sessions/{sid}/attach_library`
- **测评**：`POST /quiz/grade`（SSE）、`POST /quiz/record`、`GET /quiz/recent`（跨会话最近习题，上限 100 道）、`POST /assessment/{start,answer,next,abandon}`、`GET /assessment/report`
- **工作区**：`GET/POST /workspaces`、`GET/PATCH/DELETE /workspaces/{id}`、`POST /workspaces/{id}/upload`、`POST/DELETE /workspaces/{id}/sessions[/{sid}]`、`GET /sidebar`（组合快照：会话+工作区+详情一次取齐，带 ETag/304）
- **资料库**：`GET /library`、`POST /library/{folders,upload}`、`PATCH/DELETE /library/folders/{id}`、`POST /library/files/{id}/move`、`DELETE /library/files/{id}`、`GET /library/files/{id}/download`、`GET /library/files/{id}/page/{n}`（PDF 原件页快照 PNG，图表证据「查看原页」）
- **教材库**（P2/P6）：`POST /textbooks/upload`（`level` 学段 + `scope` 公用 + `group`/`group_id` 教材组）、`GET /textbooks[/{id}]`、`GET /textbooks/{id}/download`、`PATCH /textbooks/{id}`、`POST /textbooks/{id}/rebuild_graph`、`GET /textbooks/{id}/figure-status`（图表/印刷页码标记探测，旧书刷新升级提示）、`POST /textbooks/{id}/cancel`（终止在途解析，已有文本与切片保留）、`DELETE /textbooks/{id}`、`DELETE|GET /textbooks/{gid}/volumes/{fid}[/download]`
- **管理**（仅 admin）：`GET /admin/users`、`DELETE /admin/users/{id}`
- **投影（只读）**：`GET /student/{profile,mastery,teaching-log,learning-path,error-notebook}`、`GET /knowledge/graph`、`GET /memory/{episodes,semantic,procedural}`、`GET /evaluation/{report,traces,proposals,context-budget}`、`GET /ux/{profile,engagement,motivation,greeting}`、`GET /orchestration/{plan,today,habit,review,simulation}`
- **写操作**：`POST /orchestration/{goal,regenerate,task/{id}/complete}`、`PATCH /evaluation/proposals/{id}`（人工确认）
- **认证**：`POST /auth/{register,login,logout}`、`GET /auth/{status,me}`、`GET/PUT /user/profile`、`DELETE /user/account`
- **OpenAI 兼容门面**（第三方平台接入，`COMPAT_API_KEY` Bearer 鉴权，未配置=关闭）：`GET /models`、`POST /chat/completions`
- **语音通话**（P10，默认关闭）：`GET /voice/status`、`POST /voice/ticket`（换取单次 WebSocket 握手凭证）、`WS /voice/ws`（push-to-talk 通话：上行 16 kHz PCM16 帧，下行逐句语音 + 实时字幕事件；详见 DESIGN.md 语音章节）
- **其他**：`GET /health`、`GET /model-info`、`GET /trace/{run_id}[/html]`（知识图谱手动构建端点已移除，图谱只来自教材）

完整端点表（含参数与语义）见 DESIGN.md §23。

## 配置与环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `LLM_BASE_URL/API_KEY/MODEL` | 主模型（OpenAI 兼容 Chat Completions，必配） | — |
| `LLM_MAX_TOKENS/TEMPERATURE` | 生成参数 | 4000 / 0.3 |
| `LLM_CONTEXT_WINDOW` | Provider 声明的模型硬上下文窗口；64K 平衡档兼顾辅导深度与输入成本，窗口更小的模型请调低 | 65536 |
| `LLM_MAX_OUTPUT_TOKENS` | 主 Agent 输出绝对上限，具体阶段会进一步收窄 | 8000 |
| `LLM_CONTEXT_SAFETY_MARGIN` | 输入预算为工具、协议和突发增长保留的安全区 | 2500 |
| `CONTEXT_SOFT/HARD_TRIGGER_RATIO` | 动态上下文软/硬压缩阈值 | 0.72 / 0.88 |
| `CONTEXT_HISTORY_MAX_TOKENS` | L3 历史工作集上限，不等于模型硬窗口 | 24000 |
| `CONTEXT_RECENT_FULL_TURNS` | 压缩后保留的完整师生回合数 | 4 |
| `LLM_PROVIDER/LLM_RUNTIME_MODE` | Provider 能力档案与迁移模式（off/shadow/adapter） | openai_compatible / adapter（start.sh） |
| `LLM_SUPPORTS_REASONING*` | 显式声明 reasoning、关闭 thinking、effort/budget 与 usage 能力 | 按 Provider 配置 |
| `REASONING_SUMMARY_LEVEL` | adaptive（按任务摘要，避免本地开发额外 LLM 调用）/ real_summary（模板+真实推理提炼）/ compact / standard / detailed | adaptive |
| `EXECUTOR_TOOL_THINKING` | 工具步保留模型 LOW 思考（预算守卫与续写兜底）；0=旧行为一律关闭 | 1 |
| `EXECUTOR_TOOL_MAX_OUTPUT_TOKENS` | 工具步输出信封上限（max_tokens 是上限不是消费）；旧硬顶 4000 易被思考吃光触发续写，窗口富余时放宽反而省 token | 6000 |
| `REASONING_LIVE_MAX_CHARS` | 兼容旧配置但不再向浏览器发送原始推理（隐藏 CoT）；固定关闭 | -1 |
| `QUIZ_VERIFY_MODE` | 出题后校验：critic=结构校验+LLM 独立重解审题 / basic=仅结构校验 / off=不校验 | critic |
| `TOOL_CONTEXT_PROJECTION_MODE` | 工具专用上下文投影 off/shadow/on；SSE 与业务存储始终保留完整结果 | on |
| `TOOL_MESSAGE_MODE` | legacy/shadow/native；native 使用原生 call/result，Provider 400 自动回退 legacy | native |
| `EMBEDDING_PROVIDER` / `EMBEDDING_*` | RAG 向量模型 provider：off/local/openai；local=离线 CPU MiniLM，openai=OpenAI 兼容端点。接口可拓展——统一 `embed(texts)` 契约，新增后端只需实现同一接口并扩展枚举；任何 provider 故障回退 BM25 | off |
| `MULTIMODAL_BASE_URL/API_KEY/MODEL` | 可选视觉模型（图片/扫描页/文档嵌入图片 OCR） | 未配=本地 tesseract |
| `MULTIMODAL_DISABLE_THINKING` | VLM OCR 默认关闭思考/最低思考强度，网关拒绝自动去参重试 | 1 |
| `MULTIMODAL_OCR_RETRIES` | 单页 vision 调用重试次数（异常/空 content 退避重试，耗尽回退 tesseract） | 3 |
| `AUTH_MODE` | 0=游客宽容 / 1=登录必选 | 0 |
| `AUTH_JWT_SECRET` | JWT 签名密钥（生产必改） | 开发默认值 |
| `COMPAT_API_KEY` / `COMPAT_GRADE` | OpenAI 兼容门面接入凭证 / 门面会话学段；未配置=门面关闭（503） | 空 / 高中 |
| `SUPERVISOR_MODE` | v2（默认）/ legacy | v2 |
| `SKILL_RUNTIME_MODE` | M10：shadow=旁路；gated=前置条件+逐步执行+澄清门；off=关闭诊断注入 | gated（start.sh） |
| `STUDENT_MODEL_MODE` 等模块开关 | 各智能层开关（见 DESIGN.md §1.4） | 1 |
| `TEXTBOOK_GRAPH_ENABLED` | 教材库：上传教材是否自动构建知识图谱；0=只解析+索引跳过图谱 | 1 |
| 教材知识谱系容量 | 默认不限；上传时可设组默认并逐本覆盖，之后可从教材详情快速重合并 | `null` |
| `PDF_OCR_MODE` | 扫描 PDF OCR：auto=仅扫描PDF触发 / on=所有PDF / off=禁用 | auto |
| `PDF_OCR_MAX_PAGES/SYNC_MAX_PAGES` | 教材库后台 / 聊天与工作区上传 OCR 页数上限 | 1024 / 20 |
| `PDF_OCR_CONCURRENCY` | 全系统教材后台页面 OCR 并发 bootstrap；管理员页面可在 1–100 动态调整（重试间隔可设 0=到点即重试，实际节奏受构建队列轮询限位；100 并发下 100 页渲染+base64 同时驻留内存，小内存实例慎用） | 20 |
| `ADMIN_EMAIL/ADMIN_PASSWORD` | 管理员引导（启动时确保存在 role=admin 账号；不配=无管理员） | 空 |
| `CROSS_SESSION_MEMORY` | 详细 transcript 跨会话召回范围：workspace/all/off；精简 prompt memory 独立按用户 5–30 会话窗口管理 | workspace |
| `EDU_SOFT_BUDGET_TOKENS` | 旧版固定上下文预算；未设置时按模型窗口、输出上限和安全区动态计算 | 动态 |
| `RAG_HYBRID` / `CHROMA_DIR` | 混合检索开关 / 向量库目录；`EMBEDDING_PROVIDER=off`（默认）时向量轨不激活，实际检索为纯 BM25 | 1 / `knowledge/vector_db` |
| `CORS_ORIGINS` | 跨域白名单（生产禁 `*`）；start.sh 自动加入实际本地前端端口 | 3000/3001/3030 本地 Origin |
| `TRACE_DIR` | trace 落盘目录 | `backend/traces` |
| `VOICE_STT_PROVIDER` | 语音 STT 插件：off/stub/whisper（whisper.cpp 子进程）。未装或配置错误时自动降级为不可用，聊天不受影响 | off |
| `VOICE_TTS_PROVIDER` | 语音 TTS 插件：off/stub/melo（MeloTTS-Chinese sidecar，`start.sh` 在 melo 时自动拉起） | off |
| `VOICE_WHISPER_BIN/MODEL/LANG/THREADS/PROMPT` | whisper.cpp 二进制与 ggml 模型路径、语言、线程数、简体偏置初始提示（转写还会经内置 OpenCC 繁→简词典兜底） | 空 |
| `VOICE_WHISPER_SIZE`（安装脚本） | 安装脚本下载的 GGML 模型尺寸；默认使用 `small-q5_1`，可显式改为其他已支持尺寸 | small-q5_1 |
| `VOICE_WHISPER_CPP_REF/MODEL_REF/MELO_REF`（安装脚本） | 可复现的 whisper.cpp、GGML 模型仓库和 MeloTTS revision；覆盖后同步更新许可证审计 | 文档中的核查 revision |
| `VOICE_TTS_BASE_URL/SPEED` | TTS sidecar 地址与语速 | 127.0.0.1:8130 / 1.0 |
| `VOICE_MAX_AUDIO_SECONDS` | 单轮语音时长上限（超出截断，保护 CPU 转写延迟） | 30 |

R10 资料定界规则：本轮上传文件/图片、引用资料中心教材，或明确要求根据教材/附件回答时，系统会在回答前强制执行一次 `knowledge_search`；当前轮有明确 file_id 时只检索对应资料。工作区仅存在公共资料时，问候等无关轮次不会强制检索；定义/原理/公式/解释等内容型问题由确定性 grounding contract 强制检索，不再依赖模型自行判断。

## 项目结构

```
Edu_Agent/
├── start.sh                 # 一键启动（端口回退 + 注入 API 地址）
├── .env.example             # 配置模板
├── README.md / docs/DESIGN.md  # 入门 / 架构主文档
├── backend/
│   ├── requirements.txt / constraints.txt       # BM25 生产依赖 + 精确约束
│   ├── requirements-{vector,local-rag,cpu,test}.txt # 可选语义/测试运行时
│   ├── serve.py / cli.py
│   └── app/
│       ├── main.py          # FastAPI 工厂
│       ├── api/v1/          # chat/quiz/assessment/workspace/library/student/
│       │                    #   knowledge/memory/evaluation/ux/orchestration/auth/user/trace/health
│       ├── identity/        # M0 身份：models/store/security/deps（JWT + bcrypt）
│       ├── agents/
│       │   ├── supervisor.py + {task_understanding,planner,router,executor,state}.py  # M1
│       │   ├── student_model/         # M2   teaching_engine/        # M3
│       │   ├── assessment/            # M4   knowledge/              # M5
│       │   ├── memory/                # M6   evaluation/             # M7
│       │   ├── ux_intelligence/       # M8   learning_orchestration/ # M9
│       │   ├── skill_runtime/          # M10 Manifest/Registry/Policy/Decision/Runtime/Evidence
│       │   └── chat_agent.py          # run_turn 调度（默认 v2）+ legacy chat_turn
│       ├── core/            # llm_async / context(GSSC) / session / trace / tool 协议
│       │                    #   retriever(BM25) / knowledge_store / file_parser /
│       │                    #   workspace / library / ocr / atomic / ratelimit
│       ├── prompts/tutor.py # 三层提示：红线 / 教学过程 / 学段适配
│       └── tools/           # knowledge_search / generate_quiz / fit_quiz / recall_history
└── frontend/src/
    ├── app/                 # (workspace) 十大模块页 + login/register
    ├── components/          # ui(设计系统) / charts / shell / sidebar / chat / workspace / pages
    └── lib/                 # api(SSE) / store(zustand) / i18n / types
```

## 测试

```bash
cd backend && python -m unittest discover -s tests   # 当前共 871 个 test 方法
cd frontend && npx tsc --noEmit && npx next lint     # 前端类型 + 规范
```

## 第三方组件与许可证（语音）

语音功能默认关闭；运行 `deploy/install_voice.sh` 后，再按输出设置 `VOICE_*` 才会启用。
本节只概括当前默认链路，完整的核查日期、上游 revision、实际文件名、模型权重边界和发布
义务见 [`docs/VOICE_LICENSES.md`](docs/VOICE_LICENSES.md) 及
[`docs/licenses/VOICE_THIRD_PARTY_NOTICES.md`](docs/licenses/VOICE_THIRD_PARTY_NOTICES.md)。

### 许可证总览

| 组件/制品 | 用途 | 代码许可证 | 模型/数据许可证 | 可商业使用 | 可闭源集成 | 分发时义务 |
|---|---|---|---|---|---|---|
| OpenAI Whisper 代码 | STT 参考实现和权利来源 | MIT | — | 是 | 是 | 保留 MIT 版权声明和全文 |
| OpenAI Whisper 官方模型权重 | STT 模型权重 | — | MIT | 是 | 是 | 保留模型来源、版权和许可声明 |
| `ggml-small-q5_1.bin` | 当前默认 STT 量化权重 | — | 以 Whisper 权重 MIT 为基础；模型仓库元数据为 MIT | 是 | 是 | 记录文件名、来源 revision/hash，并随发布物带声明 |
| `whisper.cpp` | CPU STT 推理引擎 | MIT | — | 是 | 是 | 保留 MIT 版权声明和全文 |
| `ggml` | whisper.cpp 底层张量库 | MIT | — | 是 | 是 | 保留 ggml 版权声明和 MIT 全文 |
| `MeloTTS` | TTS 推理代码 | MIT | — | 是 | 是 | 保留 MIT 版权声明和全文 |
| `MeloTTS-Chinese` `checkpoint.pth` | 中文 TTS 声学模型 | — | MIT（模型卡） | 是 | 是 | 不删除模型卡/README/许可信息，记录 revision |
| `bert-base-multilingual-uncased` | MeloTTS 中文前端 BERT | — | Apache-2.0 | 是 | 是 | 保留许可证、版权/归属、修改声明；如有 NOTICE 一并保留 |
| OpenCC `TSCharacters` / `TSPhrases` | STT 结果繁→简的 vendored 转换数据 | — | Apache-2.0 | 是 | 是 | 保留 Apache-2.0 和来源/归属说明 |
| sidecar 中已核实的直接依赖 | TTS 导入期和中文合成 | 各包自己的 Apache-2.0、BSD/ISC、MIT 等许可证 | — | 按各包许可 | 通常可以，需逐包确认 | 分发 venv/镜像时带版本化 SBOM 与各包 license/NOTICE |

### MIT/Apache-2.0 能做什么

在遵守通知义务的前提下，MIT/Apache-2.0 允许将这些组件用于商业产品、教育平台、SaaS
服务、比赛作品、内部系统和闭源软件：可以免费使用、复制、修改、合并、发布、再分发和
销售包含它们的产品，不要求支付授权费或版税，也不要求公开 Edu_Agent 自身源代码。

- **MIT 义务与限制**：分发软件或模型文件时保留原版权声明和 MIT 全文；修改代码时建议
  标明修改内容；许可证不授予商标或背书权，不提供质量、适用性或不侵权保证，上游通常不
  承担使用组件造成的损失责任。
- **Apache-2.0 额外事项**：保留许可证、版权/归属和修改声明；上游有 `NOTICE` 时一并
  保留；该许可证包含一定范围的专利授权及专利诉讼终止条款，但不授予商标权，也不提供
  质量、适用性或不侵权保证。
- **代码不等于权重**：开源代码仓库的许可证不能自动证明模型权重可商用。Whisper、
  GGML 量化文件、MeloTTS-Chinese、BERT 和 OpenCC 数据均在本表中分开核查。
- **合规边界**：许可证只覆盖软件、模型或数据制品本身，不自动覆盖用户录音、转写文本、
  训练数据、生成内容、个人信息处理或商标使用；商业部署仍需遵守适用法律和用户授权。

### 分发检查清单

1. 保留 `docs/licenses/` 下与实际发布物对应的许可证全文和第三方声明。
2. 发布 Docker 镜像、安装包、sidecar venv 或模型包时，同时携带版权、许可证和 NOTICE（如有）。
3. 不删除模型文件内或模型仓库附带的许可证、README、模型卡和归属信息。
4. 记录实际模型名称、量化格式、来源仓库、revision/commit 和文件 hash。
5. 检查新增 Python 包、系统库、编解码器、加速后端和模型依赖的许可证，并生成版本化 SBOM。
6. 不将用户录音、转写文本或私有模型缓存提交到仓库。
7. 如果替换成其他中文 ASR/TTS 模型，重新核查权重和再分发权限，不能只检查代码许可证。

安装脚本不主动安装 `unidecode`、`pykakasi`、`num2words` 和完整 `unidic`；其中部分 MeloTTS
模块的导入期符号由 `melo_bootstrap.py` 提供 stub。复用旧 venv、启用其他语言或可选后端时，
必须重新扫描实际文件，不能把默认中文路径的核查结果套用到整个环境。许可证核查不替代法律意见。

## 安全与隐私

- `.env`、密钥、`users/`、`students/`、私有会话/上传/工作区及本地向量库均由 `.gitignore` 排除；唯一数据例外是版本化公共教材命名空间：`books/`、`chat_history/library/public*`、`chat_history/library/data/public/` 与 `knowledge/custom/public/`。
- 密码 bcrypt 哈希，绝不回传客户端；JWT secret 生产必换。
- 多用户数据物理隔离（会话 / 工作区 / 资料库 / 学习数据）；按 id 资源端点对外人 404。
- `GET /model-info` 只暴露模型名与多模态配置状态，不暴露任何 key。

### M5 教材谱系三级分类（2026-08-10）

知识谱系现在按 **学段 → 资料中心学科 → 教材组/栏目** 三层动态展示。物理学下的《大学物理学（张三慧）》和其他教材不会再混合显示。资料中心教材的栏目名、备注、学科、学段是唯一事实源；修改后 taxonomy 即时重新归类，不重建图谱节点或边。

新增/扩展接口：

- `GET /api/v1/knowledge/taxonomy`
- `GET /api/v1/knowledge/graph?textbook_id=...`
- `PATCH /api/v1/textbooks/{id}`：支持 `title/group_name/group_note/subject/level`
- `PATCH /api/v1/textbooks/{id}/volumes/{file_id}`：重命名教材 PDF 显示名
- `PATCH /api/v1/library/files/{file_id}`：重命名普通资料文件

公用教材的元数据编辑仍仅管理员可执行；普通用户可浏览、选择和检索公用教材。


## 归档中心、彻底删除与记忆生命周期（2026-08-13）

删除对话、普通资料/文件夹、教材/教材组、知识谱系或工作区时，系统先生成完整归档包，统一放在 `chat_history/trash/items/<owner>/<trash_id>/`，前端 `/archive` 可查看项目相对归档位置（不暴露服务器绝对路径）、大小、到期时间和内容类型。恢复会保留原 ID；教材/资料恢复时可选择重新挂接哪些学习区；工作区恢复为 workspace、成员对话、专属资料和共同记忆整体恢复。

“彻底删除”是归档中心的二次确认操作，会删除归档包及所有可恢复/技术副本：活动与归档图谱、原件、解析/OCR 文本、附件、chunks、BM25/Chroma、会话 JSON、transcript、trace、工作区引用和 manifest。独立学习结果账本仍按契约保留题目、作答、评分、知识点和时间；归档期间来源状态显示为“来源对话已删除，无法查看”；永久删除后底层来源会话 ID 也被不可逆清空，同时保留题目、作答、评分与知识点，不提供正文跳转。账号注销本轮不改动。

默认回收站保留 7 天，用户可在 1–30 天内选择；管理员可设置默认、上限、强制最长保留和 manual/auto 模式。启动时及进程内定时任务自动幂等清扫到期归档。

用户级提示词记忆与业务学习档案分离：默认最近 15 个会话，用户可选 5–30；普通对话和工作区对话统一计数。只有总体学习概况、当前水平、语气偏好和讲解偏好进入 prompt；策略成功率与习惯分别写入有界 `procedural.json` / `habit_patterns.json`，旧 episodic/semantic 生产只读；滑出窗口的贡献会合并为硬上限画像，最近窗口内可在删除对话时选择永久遗忘。若归档阶段未选择，永久删除或到期清扫时也会自动移除仍可单项归属的最近贡献；已合入整体压缩画像的影响不可安全拆分。工作区共同记忆始终只在本工作区可见，并随工作区 bundle 恢复或彻底删除。

新增主要接口：

- `GET /api/v1/trash`、`GET /api/v1/trash/{id}`、`POST /api/v1/trash/{id}/restore`、`DELETE /api/v1/trash/{id}`、`DELETE /api/v1/trash`
- `GET/PUT /api/v1/trash/policy`
- `GET /api/v1/memory/prompt-profile`、`PUT /api/v1/memory/prompt-profile/window`
- 管理员：`GET/PUT /api/v1/admin/data-retention`、`GET/PUT /api/v1/admin/prompt-memory-policy`、`GET/POST/DELETE /api/v1/admin/public-trash`

### 教材知识谱系容量与按需视图

教材统一采用“学段 → 学科 → 教材组 → 单本教材 → 章节 → 概念”。上传时章节数和概念数默认不限制，可设置教材组默认值并为每一本教材独立覆盖；保存容量设置只复用 `volume_specs` 完整缓存重新裁剪/合并，不重新 OCR、解析或调用 LLM。`GET /api/v1/knowledge/graph` 支持 `textbook_id`、`file_id` 与 `view=overview|chapter|search|full`，新前端默认按需加载。管理员通过 `GET/PUT /api/v1/admin/ocr-policy` 动态管理全系统教材后台 OCR 页面并发。

### 教材刷新与 RAG V2

教材卡片的刷新按钮默认选择 **RAG + 知识谱系**：直接复用已经解析/OCR 后的 `.txt`，不会重新 OCR；它会在内存 staging 质检后，按教材组原子更新 Structured V2 切片、BM25、可选向量索引和必要知识谱系。同一用户/公共库的刷新任务串行发布，避免批量升级互相覆盖。只有文本缺页、质量差或人工明确要求时才选择“完整重新 OCR”。管理员可在管理页设置教材多模态 OCR 的持久重试策略；解析进行中（OCR/构建）可在教材卡点「终止解析」停止（已有文本与切片保留，终态自动结算）。切块与图谱索引均惰性自动重建（.txt 变化/定位器或 prompt 版本变化即失效），不再需要任何「批量升级」管理操作。聊天临时附件、工作区和普通资料库的 OCR 降级行为未改变。

教材后台 OCR 的重试语义：瞬时错误（429/5xx/超时/连接）在 `persistent_api` 模式下按设置间隔持续等待重试（默认间隔 10 秒，等待单页响应的超时独立可调至最高 300 秒），`bounded_*` 模式在页级 `max_attempts` 后本地 tesseract 兜底或暂停；**空白页类失败**（视觉模型正常响应但页面无文字，如书末版权页/空白页）在达到 `max_attempts` 后按空白页收尾、教材继续构建，不会无限重试。每页完成即增量落盘，服务中途重启只重试未完成页。`request_timeout_seconds`（10–300）应不低于所用视觉模型的**最慢单页延迟**。同一用户的教材自动构建（上传/启动恢复/删卷重建）严格一本接一本：队首教材到达终态后下一本才开建，不会出现多本书同时「等重试、建一半」；手动刷新不受队列约束。

新增灰度配置：`RAG_CHUNKER_MODE=legacy|v2`、`RAG_EVIDENCE_GATE=off|shadow|on`、`RAG_CONTEXT_COMPRESS=0|1`。默认启用 V2/证据门/完整证据块上下文。检索卡片显示通过门的 evidence excerpt、页码与高/中置信度；所有候选都弱时返回 NOT_FOUND，不再为了凑来源数注入低相关正文。

P7 图表与页码：`RAG_FIGURE_HARVEST=0|1`（默认 1）控制原生 PDF 教材的表格结构化与插图图述收割（关闭即降级纯文本层；扫描书不受影响——其 `[图|…]图述`/`[表|…]`/`[页码=N]` 标记由 OCR prompt v2 直接产出）。检索证据双轨页码：**教材第 N 页**（教材自标印刷页码，OCR/收割阶段保存）优先，无则 PDF 第 M 页；图表证据带 `[图]`/`[表]` 徽标并可「查看原页」。旧书升级：转录于图表提取上线前的教材需对每本跑一次「完整重新 OCR（升级图表与页码提取）」，刷新弹窗会自动探测并默认推荐；之后日常刷新仍用 RAG + 知识谱系。对话多模态路由：本轮含图（图片附件 / RAG 图表证据页快照）时 tutor 自动切换 `MULTIMODAL_*` 通道并**开启思考推理**（未配置 MULTIMODAL 时降级纯文本）；教材 OCR 等提取型调用保持关闭思考（转录任务，开推理更慢更贵）。证据门对自然语言问句（「X 要学点什么/是什么」类）按内容词匹配，不再被整句短语覆盖门误杀；弱模型在正文里叙述假 `<knowledge_search>` 标签时由流式护栏拦截并执行真实检索。

P7.7 知识谱系统一规范：谱系建模走主 LLM（`disable_thinking` 小 JSON 调用），OCR 走 MULTIMODAL 视觉通道（关思考）——分工契约不可互换。章节层只允许教学单元：Tier 1 书签标题质检（文件名/印刷工单/卷名包装/目录噪声，类级规则）自动剔除，垃圾过半整层弃用交 LLM 从正文定位；卷名包装剥前缀（「化学反应原理第1章」→「第1章」）；兜底章名统一「全册」；概念名 ≤12 字。页码标记位置容错（页首/行尾/句中均可，取页末值）。组级章序按卷偏移，画布同层按构建顺序稳定排序，长标签两行渲染（悬停显全名）。恢复轮与进程重启传播 `force_full` 意图，完整重新 OCR 不再因中途失败丢失升级成果。前置页（封面/扉页/版权/目录）不进入图谱正文（页级判定剔除）；合并 spec 后 DS 图谱设计阶段统一标签、归并同义概念、补跨章前置（`GRAPH_DESIGN_MODE=0` 关闭，失败自动降级）。

**刷新清理契约**：各模式只清理/重建对应文件——`rag_graph` 重建 chunks/BM25/向量（含本 scope 孤儿向量剪枝）+ 图谱重合并，`.txt` 可被原生收割追加、原 PDF 与 OCR 状态不动；`graph_only` 完全不触碰 `.txt` 与 RAG（图谱强制重抽）；`full_ocr` 页级全量重写 `.txt`、清空 OCR 状态、构建后全量重建 RAG+图谱；删除教材/教材组则全部进归档区（可恢复）。
