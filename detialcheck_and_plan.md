# Edu_Agent 全功能只读检查报告与优化方案

- **检查日期**：2026-08-24
- **检查方式**：全程只读（WSL Ubuntu 内直接读取源码/文档/数据文件结构与时间戳；未修改、未删除项目任何现有文件；未向运行中的服务发送任何写请求；未运行测试）。本文件是本次检查唯一新增的产物。
- **检查对象**：`~/daily/vibecoding/Agent_Develop/Edu_Agent`（AI Tutor OS，FastAPI + Next.js 16）
- **重点**：学习总览 / 学习编排 / 测评中心 / 记忆中心 / 我的画像 / 系统洞察六个待优化模块；知识谱系与长期目标的结合可行性；记忆体系（用户级永久记忆 / 工作区共同记忆 / 压缩）的实现与可视化缺口。
- **依据**：`docs/DESIGN.md`（1230 行架构主文档全文通读）、`README.md`、前端 `frontend/src` 全部目标模块页面与组件、后端 `backend/app` 相关路由与 agent 实现、`students/` 等数据文件的**结构/大小/时间戳**（未引用任何私人对话内容）、`.env` 非敏感开关、git 状态与在途计划文档。

---

## 0. 运行状态与数据现状快照（检查时点）

| 项 | 状态 |
|---|---|
| 后端 | `python -m uvicorn app.main:app`，pid 413，端口 **8123**，08:32 启动至今（正在处理教材构建） |
| 前端 | `next start`（生产模式），pid 441，端口 **3001** |
| 同机另一项目 | Paper_Agent 占用 8000/3000（dev 模式）——本次检查未触碰 |
| git | 仅 4 个提交（v1–v4）；工作区有**未提交的进行中修改**：`knowledge/graph.py`、`knowledge/manager.py`、`knowledge/store.py`、`learning_orchestration/manager.py`、`student_model/manager.py`、`student_model/skill_graph.py`、`api/v1/orchestration.py`、`main.py`、`test_orchestration.py` + 公共教材图谱/文本数据。`.zcode/plans/plan-sess_2ecbb4bb….md` 证实这是「知识图谱冷构建性能修复」（对应 DESIGN §14.7：邻接索引、graph_for 构建锁、`/orchestration/today` 确定性优先、`_mastery_view_safe` 命名空间修复）。**任何后续优化都应等这批改动落地后再动相关文件。** |
| 用户数据 | `students/` 下 3 个命名空间：`usr_dd845d7b6c`（重度用户，含旧版 `.episodes.jsonl` 16KB / `.semantic.json` 9KB / `.events.jsonl`）、`usr_66662250af`（新用户，**没有** episodes/semantic 文件）、`student_default`（游客）；另有全局 `prompt_memory_policy.json` |
| 会话/工作区 | `chat_history/` 根目录当前**没有任何会话 JSON**（只剩 `library/ settings/ trash/ workspaces/` 四个目录）；`chat_history/workspaces/` 下**没有活动工作区**（只剩 `uploads/` 空目录）→ 工作区共同记忆当前实例数为 0 |
| 知识谱系 | `knowledge/custom/` 下 `public`（公共教材图谱 20+ 册，含 `.chunks.json` 与 `volume_specs/`）、`student_default`、两个 usr 命名空间 |
| 笔记 | `notes/` 下 3 个命名空间（student_default + 两个用户） |
| `.env` 关键项（脱敏） | LLM/多模态走 `cctq.ai` 的 `gpt-5.6-luna`；`QUIZ_VERIFY_MODE=critic`；`REASONING_SUMMARY_LEVEL=adaptive`；`AUTH_MODE` 未设置（=0 游客宽容）；`ADMIN_EMAIL` 已配置（有管理员）；**`DEFAULT_GRADE=高中` 已证实是死配置**（`core/config.py:144` 读入后全库无任何消费方，P1 学段去僵化后的残留） |

---

## 1. 模块地图与导航对照

`frontend/src/lib/nav.ts` 三组导航（篆刻徽章标注模块归属）：

- **学习组**：`/chat`(M1 对话工作台)、`/notes`(MN 笔记)、`/dashboard`(M2 学习总览)、`/knowledge`(M5 知识图谱/谱系)、`/plan`(M3 学习计划)、`/orchestration`(M9 学习编排)、`/assessment`(M4 测评中心)
- **归档组**：`/memory`(M6 记忆中心)、`/resources`(RAG 资料中心：`/resources/files` 文件库 + `/resources/textbooks` 教材库)、`/archive`(归档中心)、`/profile`(M2·M8 我的画像)
- **系统组**：`/insights`(M7 系统洞察)、`/admin`(M0 管理台，仅 admin)

后端智能层 M1–M10 与前端页面的映射、每层的正交开关（`*_MODE` 环境变量，默认全开）与 DESIGN §1.4 一致，未发现文档与代码不符。

---

## 2. 逐模块功能核对（前端可见功能 × 后端实现 × 数据源 × 真实性判定）

> 判定口径：**真实** = 有确定性实现或真实 LLM 调用且数据链路闭合；**旧版冻结** = 数据源已停产只读；**死功能** = 端点/代码存在但无消费方或无实际效果；**重复** = 与其他模块语义重叠。

### 2.1 学习总览 `/dashboard`（M2+M3+M8+M9+M7 混合投影）

页面结构（`app/(workspace)/dashboard/page.tsx`，8 个卡片区域）：

| 卡片 | 功能 | 取数 | 后端实现 | 判定 |
|---|---|---|---|---|
| GreetingBar | 个性化问候 + 连续天数火焰徽章 + 下一里程碑 | `GET /ux/greeting`、`GET /ux/motivation` | `ux_intelligence/context_builder.greeting`（模板拼装）+ `motivation_engine.motivation_snapshot` | **⚠️ 数据源死亡（P0）**：greeting 的“继续上次学的 X”与 streak 全部读旧版 episodic（见 §4 问题 1/2/3） |
| StatCards 四统计 | 已掌握(≥0.8) / 学习中(0.5–0.8) / 需关注(误解或<0.5，注意卡片描述文案写 <0.4，代码实际 `p_known < 0.4`，与“需关注”口径在 StatCards(<0.5) 与 AttentionCard(<0.4) 之间**不一致**) / 连续天数 | `GET /student/mastery` + `/ux/motivation` | M2 BKT 掌握度真实；streak 死源 | 掌握度三项**真实**；streak **死源** |
| TodayTasksCard | 今日任务前 3 条速览 + 连击 + 跳编排；**无目标时整卡隐藏** | `GET /orchestration/plan` + `/today` | M9 真实 | **真实**（`plan.goal.title` 为空 return null） |
| RadarCard | 学科掌握雷达（按 subject 求均值） | `/student/mastery` | 前端聚合，数据真实 | **真实** |
| ActivityCard | 近 14 天学习活动 Sparkline（每日事件数） | `getEpisodes(200)` → `GET /memory/episodes` | **旧版情景记忆只读端点** | **⚠️ 数据源死亡（P0）**：生产不再写 episodes，新用户此卡永远空态“近 14 天暂无学习活动”，重度用户数据停在最后一次旧版写入（8/23） |
| RecentCard | 最近学习（teaching-log 按 last_ts 排序，分页，点击跳 `/knowledge`） | `GET /student/teaching-log` | M3 教学日志真实 | **真实** |
| AttentionCard | 需要关注（misconception 或 p<0.4，进度条 + 首条错误） | `/student/mastery` | 真实 | **真实** |
| EvalSummaryCard | M7 摘要条（平均学习增益/已评估轮数/待审批 + 跳洞察） | `GET /evaluation/report` | M7 聚合真实 | **真实但与 /insights OverviewStats 四数字完全重复** |

页面级容错：M8 问候/动机与 M7 报告允许独立降级，M2/M3/M6 投影失败整页报错（代码注释明确）。

**小结**：总览页 8 卡中 5.5 卡真实可用；**活动图与全部 streak 展示绑定在已停产的旧版 episodic 数据上**；评估摘要与洞察页重复。

### 2.2 学习编排 `/orchestration`（M9，本次优化的重点模块之一）

#### 前端功能全量清单（`orchestration/page.tsx` + `components/pages/orchestration/*`）

1. **无目标态**：整页引导 + GoalForm（目标名 60 字、类型三选一 exam/ability/interest、学段+学科两级下拉（M5.8 catalog，失败回退自由文本按逗号拆分）、截止日期；**description 字段后端类型里有但表单恒传 `""`**）。
2. **needs_replan 横幅**：警告条 + “让教练帮我调整”对话深链（`/chat?q=…&send=1`）；旧“重新规划”按钮已按 DESIGN 移除（确属死按钮）。
3. **Kickoff 卡**：目标保存成功后展示周计划数 + 首个任务 CTA（`taskChatHref` kind 感知深链）。
4. **GoalCard 长期目标卡**：标题/学科徽标/描述/截止倒期（逾期红字）/进度条（mastered_ratio + n/m 概念）/当前等级→目标等级/紧迫度进度条/推荐策略一行（foundation_first / intensive_review / mixed_progress / advanced_refinement 四种模板文案）。
   - **差距分析区（GapRow）**：`missing`(红)/`weak`(黄) 徽标 + 概念名 + 当前%→目标%（取前 6 条）。
   - **长期任务子区（LongTaskSection）**：常驻承诺列表（如“每天背 20 个单词”），逐条 ✨LLM 建议（`POST /orchestration/longtask/{id}/suggest`）、删除、分页、新增输入框。
5. **TodayCard 今日任务卡**：
   - “学习计划 / 间隔复习”双子栏（kind=review 归复习栏，带待办计数徽标）；
   - 昨日结转（overdue）置顶 + 红色“结转”徽标；
   - 行交互：勾选完成（乐观更新）、行动按钮（去学/去复习/去练/去总结 → kind 感知 auto-send 深链）、编辑（日期/标题/类型/阶段 foundation·reinforce·sprint/时长/优先级；编辑态不暴露概念字段——PATCH 契约无 concept_name）、删除（二次确认）、重置（completed/skipped → pending）；
   - 添加任务弹窗（标题或概念名二选一、kind 四类、phase、5–240 分钟、优先级 1–5）；
   - LLM 教练批注 `task.reason` 展示（accent 色小字）。
6. **HabitCard 习惯卡**：连击（右上有火焰时）/最长连击/累计活跃天数/拖延计数四 MiniStat + 完成率进度条（completed/total）。
7. **WeeklyPlanCard 周计划卡**：
   - 周 tabs（本周高亮 ●）+ 周起始日期 + focus + `origin=user` 自定义徽标；
   - 概念胶囊（难度 5 点阵 + phase 徽标 + planned_mastery 悬停 + 单个移除）；「添加概念」小弹窗（下拉选已有概念或自由文本）；「添加一周」弹窗（本周重点 + ConceptMultiPick 概念多选）；整周删除（二次确认）；
   - **行动级周任务**（WeekTaskRow）：标题 + kind 徽标 + source=user 徽标 + 子任务完成计数 + ✨子任务推荐（`POST …/task/{tid}/suggest`，失败黄色提示）+ 删除；展开后子任务可勾选/删除/新增（80 字）；周任务新增输入框；分页 5/页；
   - 「本周复盘」按钮：父组件拼好“本周 focus + 全计划完成统计”的 auto-send 对话深链。
8. 页面级：`visibilitychange` 回源刷新（对话内学习行为会自动推进任务状态）。

#### 后端链路验证（全部真实，且质量门齐全）

- **目标设定/编辑** `POST/PATCH /orchestration/goal` → `manager.set_goal/update_goal` → `_analyze_goal_safe`：读 M2 mastery_view + M5 合并教材图谱的 per-student SkillGraph 投影（`_subject_skills_safe`/`_prereq_map_safe`），`goal_analyzer.compute_gap_analysis` 做差距分析 + 拓扑排序倒推链 + 截止紧迫度 + 策略推荐（纯函数零 LLM）。响应带 `weeks + first_task`（kickoff）。
- **周规划** `regenerate_plan`：LLM-first（`weekly_planner_llm`，一次 `disable_thinking` 小调用产出 N 周语义化周计划：每周 focus + 行动级周任务 + 子任务），**校验门**（概念 ⊆ 窗口、全覆盖、非复习任务无重复概念、数量上限、kind 合法）不过则回退确定性 `learning_planner + derive_tasks_fallback`。大考纲窗口 = 前 `num_weeks×5` 概念。人工不可覆盖契约（origin=user 周 / source=user 任务按 7 天 bucket 并回）在 `_merge_user_plan` 实现。
- **今日任务** `GET /today`：确定性优先（读路径缺当日任务时确定性生成器即时返回，`asyncio.to_thread` 包裹重活——正是本次未提交性能修复的内容）；LLM 组合（`daily_composer`：候选池 = SRS 到期 ∪ 本周未掌握概念 ∪ 未完成子任务 ∪ active 长期任务 ∪ M2 弱项 ∪ 昨日结转，LLM 挑 ≤slots 并产 reason，校验门回退）只发生在 POST /goal、/regenerate 等显式写动作。
- **完成回写**：`POST /task/{id}/complete` 带子任务引用回写 SubTask.done（标题守卫防位置 id 复用刷完成）。
- **SRS**：经典 SM-2，`quality_from_verdict` 是 M4→M9 组合点；笔记温故卡（`note:<id>` 前缀）同队列。
- **习惯**：`record_turn`（supervisor 6g 钩子）→ `habit_tracker.refresh_habit`。
- **持久化**：`students/<id>.orchestration.json`（工作集）+ `.orchestration_events.jsonl`（黑盒）。

#### 判定与问题

- 核心链路**真实且工程化程度高**（校验门、回退、人工不可覆盖、唯一性契约都有测试覆盖）。
- **P0：HabitCard 的连击/最长连击/活跃天数三个数字的数据源是旧版 episodes**（`manager.record_turn:153` → `_episodes_safe` → `read_episodes` 读 `.episodes.jsonl`，生产已停产）。只有完成率/拖延计数来自 `daily_tasks` 是活的。新用户习惯卡连击恒 0。
- **死代码**：`/orchestration/simulation` 端点 + `learning_state_simulator.py`（327 行）前端已无任何调用（`api-modules.ts` 里 `getOrchSimulation`/`regenerateOrchPlan` 两个客户端函数也无页面引用）；`_habit_patterns_safe`（manager.py:1241）定义后无调用方。
- **长期目标 ↔ 知识谱系联动弱**（详见 §5.2 方案）：
  1. 目标只取 `subjects[0]` 一个学科参与分析；
  2. 学科匹配靠字符串全等（goal.subjects ↔ 图谱节点 subject，或标题关键词表 `_SUBJECT_KEYWORDS` 命中“数学/物理/化学/生物/英语”五类），教材 subject 元数据若写“高等数学”“语文”等则匹配不上 → skills 为空 → `_analyze_goal_safe` 直接 return，GoalState 保持默认（进度 0%、无 gaps、无差距链）；
  3. gaps 是“该学科**全量**未掌握概念”，不是“达成该目标所需的概念链”——目标粒度（如“期末物理上册考到 85 分”）没有概念级绑定；
  4. goal_type 只影响 target_level（proficient/intermediate），description 不参与任何分析（且表单恒空）；
  5. deadline 只变成 urgency 0–1 进度条，不参与周数/密度决策的可见解释；
  6. 长期任务建议（longtask_advisor）是**纯文本 LLM 建议**（门控：1–3 条、≤120 字、id ⊆ 请求集、回退模板），完全不查知识图谱/掌握度，建议是通用套话的概率高。

### 2.3 测评中心 `/assessment`（M4）

功能全量清单（页面状态机 `idle → asking → feedback → done`）：

1. **CAT 自适应测试**：ConfigCard（概念自由文本 + 学段下拉（账户学段兜底）+ 学科）→ start（后端建会话，首题经 `/next` 生成）→ QuestionCard 作答 → `/assessment/answer` 判分（SSE 三级评分）→ FeedbackCard（判定 + 讲解 + 停止原因提示）→ `/next` 下一题或 SummaryCard 总结（概念/答题数/对错部分对/正确率/最终难度/停止原因）→ 再来一轮。放弃按钮随时可退。
2. **错题本卡**：`GET /student/error-notebook`（`core/error_notebook.py`：优先读 `learning_records` 独立账本，回退旧 quiz_history；verdict ∈ {wrong, partial}，题干前缀去重，上限 200，新→旧），分页 + **重练深链**（`?q=带题干&send=1` → 教练用 fit_quiz 出变式，不在本页复制作答 UI）。
3. **最近习题卡**：`GET /quiz/recent`（跨会话最近习题快照，每生上限 100 道 FIFO；答题卡判分按 (session_id, 题干前缀) 回填 verdict），分页，点击回出题会话。
4. **近期练习会话卡**：`GET /chat/sessions` 过滤 `quiz_count>0` 按时间排序，点击进会话。
5. 挂载时用 `GET /assessment/report` 探测 M4 开关（disabled 整页降级）。

后端真实性核验：

- **CAT 是真的**：`adaptive_test.py` 四条停止规则（mastered：末 2 对且难度≥3；confirmed_gap：末 2 错且难度触底；max_reached；oscillating：≥4 题对错交替）+ 难度步进（镜像 M3 阈值 ≥0.8 升 / ≤0.4 降，partial 计半，钳位 1–5）全是纯函数；LLM 只用于出题（`generator.py` 约束驱动 prompt，`disable_thinking=True`）。
- **出题质量门真实**：三条出题路径（generate_quiz / fit_quiz / M4 约束出题与 CAT）统一过 `core/quiz_verify.py` 确定性结构校验 + LLM critic 独立重解（`.env` 已开 `QUIZ_VERIFY_MODE=critic`），错题丢弃重生成，审计随 Trace。
- **三级评分真实**：MC 确定性字母比对零 LLM；主观题 LLM 三级（对/部分对/错）+ ≤120 字讲解。
- **M10 证据门真实**：E0–E5，“仅口头说懂了”不产生高置信掌握度写回；`unknown` 判定不落盘。

问题（都很轻）：

- 前端 `assessmentStart/Answer/Next/Abandon` 仍传 `student_id: "student_default"`——后端 JWT 单一事实源会忽略它（曾有 CAT 信任 body id 的漏洞已修复并有回归测试），属于**冗余传参**而非 bug，建议清理以免误导。
- ConfigCard 的概念是**自由文本**，不接知识谱系选择器——测评概念与图谱概念无法关联（BKT 归因靠 SkillGraph 模糊匹配兜底）。可与知识谱系联动（见 §5.3）。
- 页面同时呈现 4 个区块，CAT 卡与三个历史卡的信息层级可以更聚焦，但功能本身无问题。

**结论：测评中心是六个待优化模块中实现最扎实的，基本不需要“智能化补课”，只需要联动性与小清理。**

### 2.4 记忆中心 `/memory`（M6，重构重点）

现状页面结构（`memory/page.tsx`）：

1. **顶部说明卡**（info 色）：文案与你的理解完全一致——“情景/语义列表是旧版兼容审计数据，不再新增详细对话记忆，也不会直接注入提示词；新提示词记忆仅保留总体水平与表达偏好。”（`memory/strings.ts` mem.note，中英双语）。
2. **提示词记忆窗口卡**：`GET /memory/prompt-profile` → 只展示“最近会话数（5–30）”数字输入框（失焦 `PUT …/window`）+ “已压缩 %n 个旧会话贡献”一行说明。
3. **三个 Tab**：
   - **情景记忆**：`GET /memory/episodes`（旧版 `.episodes.jsonl` 只读，按日分页，一页一天，“加载更多”向服务器取更早；事件类型图标 concept_taught/quiz_graded/goal_set，重要度条、得分）；
   - **语义记忆**：`GET /memory/semantic`（旧版 `.semantic.json` 只读，事实卡网格 6/页，superseded 灰显 + 取代者 ID 审计链、置信度、证据数）；
   - **程序性记忆**：`GET /memory/procedural`（**活数据** `students/<id>.procedural.json`：各教学策略滑窗成功率 + 试用次数条形图 8/页，“试用不足 3 次不注入教学提示”脚注）。

后端事实（`api/v1/memory.py` docstring 与实现一致）：

- episodes/semantic 端点即“compatibility read-only”，生产回合不再追加；`append_episode` 函数存在但**全库无调用方**（grep 验证）。
- `/memory/prompt-profile` 返回远比页面展示丰富的数据（`prompt_memory.public_view`）：`core_profile` 四字段**内容**（总体学习情况/当前水平/语气偏好/讲解偏好）、`recent_sessions`（会话 id/工作器归属/时间戳/是否有贡献）、`compacted_session_count`、`compacted_attribution_count`、`legacy_compacted_attribution_unknown`、`directive_chars`（当前注入提示词的字符数）——**前端只用了 window/max/compacted_count 三个字段，画像内容与会话清单完全没有可视化**。
- 另有 `GET /memory/prompt-profile/sessions/{sid}`（单会话归属状态 recent/compacted/legacy_unknown/none，归档删除流程在用，记忆中心页未直接用）。

判定：

- 页面定位诚实（顶部说明 + 文案准确），**程序性记忆 Tab 与窗口卡是活的**；
- 但整个页面 2/3 的版面（情景/语义时间线）是**旧版审计数据陈列**，且对新用户永远空态；空态文案还在描述旧机制（“完成对话学习、测验评分或设定学习目标后，关键事件会作为情景记忆写入”——**这句已经不成立**，会误导用户等待永远不来的数据）；语义空态文案同样描述已停用的“LLM 周期性巩固”。
- **工作区共同记忆在本页无任何入口**（目前唯一可视化是侧边栏工作区展开区直接展示 `public_memory` 原文，`sidebar/WorkspaceItem.tsx:97,160`）。
- **独立学习账本 `learning_records.json`（题目/作答/评分/知识点/时间）没有任何直接可视化**（只通过错题本间接消费一半）。
- M6 `habit_patterns.json`（习惯聚合）**写而不读**（见 §4 问题 6）。

### 2.5 我的画像 `/profile`（M2+M8+M0）

功能清单：

1. **AccountCard**（M0，仅登录态）：查看/编辑 UserProfile + 危险区自助注销（密码 + 输入“注销”双确认）。
2. **IdentityCard**（仅游客态渲染，避免与账户卡重复）：游客身份 + 学段。
3. **AcademicCard**（M2）：学习风格两行（preference/depth——由 `style_inference.py` 从 M8 反馈窗口折叠翻转，“太长”≥2→basic 等，**该写入路径是活的**）、学习目标列表（M2 profile.goals）、优势/待加强徽标墙、页脚（最近活跃/事件数）。
4. **InteractionCard**（M8）：五维交互风格（语气/详略/图示/节奏/耐心）+ 近期反馈分类计数 + 互动信号（平均回答长度/放弃信号/事件数）。数据 `students/<id>.ux_profile.json` 真实（M8 每轮规则分类 + 滞后效应 ≥2 信号才切换）。
5. **MotivationCard**（M8 激励）：连续天数大数字 + 累计活跃 + 里程碑节点条（3/7/14/30/60/100）。**数据源 = 旧版 episodes（`/ux/motivation`）→ 死源，新用户恒 0**。

问题：

- **P1 重复语义**：M2 `profile.goals` 来自对话中规则检测的 `goal_set` 事件（supervisor 每轮把含目标短语的用户消息记进 M2），与 M9 长期目标是**两套并行的目标系统**（不同存储、不同展示、互不同步）。用户在编排页设的目标不会出现在画像页，反之亦然。
- **P2 重复语义**：InteractionCard 的“语气/详略”与记忆中心 prompt memory 的“语气偏好/讲解偏好”语义高度相近，但数据源不同（M8 ux_profile vs M6 prompt_memory），两套都在各自注入链路里影响表达（M8 `[交互智能·…]` 软指令 vs M6 `[提示词记忆·精简画像]`）——单真相源边界在 M2/M8 之间做过划分，但 M6 prompt memory 的语气/讲解偏好实际上是第三个拥有者。
- MotivationCard 死源（同 §4 问题 2）。
- 页面底部有“关于本页”说明条，解释 M2/M8 分工——文档意识好，但用户视角是“两张差不多的画像卡”。

### 2.6 系统洞察 `/insights`（M7，"智能评估没有真正智能"的主要出处）

功能清单：

1. **观察者声明条**：固定文案说明 M7 是纯观察者。
2. **OverviewStats 四统计卡**：总轮次 / 已评估（含百分比）/ 平均学习增益 / 待审批提案。与 dashboard EvalSummaryCard 数字重复。
3. **ContextBudgetPanel 上下文与推理预算面板**：模型窗口/平均输入/平均输出/节省 tokens 四格 + Provider·runtime 模式/工具投影节省比/恢复计数/思考-答案双通道均值 + 压力比进度条。数据 `GET /evaluation/context-budget`（`core/context_telemetry.py` 聚合，只回统计不回原文）——**真实且有价值**。
4. **DiagnosisCharts 两栏**：失败诊断分布 Donut（七类 FailureType）+ 策略效果排名 Bars（mode×subject 的 avg_gain/成功率/样本数）。数据 `GET /evaluation/report`（`strategy_analyzer` 跨轮聚合，纯函数）——**真实**。
5. **ProposalsList 改进提案**（人工确认门）：`GET /evaluation/proposals` + `PATCH …/proposals/{id}`（approved/rejected/applied 三态按钮、置信度条、证据数）。
6. **TracesTable 轮次黑盒表**：最近 50 轮（`GET /evaluation/traces`），时间/概念/学科/模式/结果/增益/失败类型，行展开看失败原因 + intent/工具数/token/时长 + 跳回会话，10 条/页——**真实**（`students/<id>.eval_traces.jsonl` 黑盒 + 规则诊断瀑布）。

**核心问题（P1，用户直觉正确）——改进提案是一个“假闭环”**：

- 提案生产是真实的：`advisor.maybe_advise` 每 15 条 trace 频率门控（`ADVISOR_FREQUENCY_GATE=15`，schema.py:388），LLM 读失败分布 + 各模式效果，产出一条结构化提案（target ∈ {prompt, policy, strategy} 白名单、change/rationale/confidence，解析失败静默丢弃并重置门）。
- 但 **`status="applied"` 只是一个标签**：全库检索确认，**没有任何代码消费 approved/applied 提案去真正修改 prompt、policy 或 strategy**。用户点“批准”→“标记已应用”之后，系统什么都不会发生。DESIGN §16 写“approve/deploy 是人工确认（API）”，但 deploy 侧根本不存在。
- 提案本身也**只有一条文本建议**（change 是一句话），没有结构化的“改哪个 prompt 的哪一段/哪个参数从多少到多少”，即使想接 apply 也缺乏可执行载体。
- **experiment.py（A/B 实验层）是彻底死代码**：确定性分桶、record_outcome、sample≥2 宣布 winner 的整套实现（DESIGN §16 第 4 层）**无任何调用方**（evaluation 包内外均无 import），API 也没有暴露实验数据的端点，前端更无界面。
- 诊断瀑布（trace_analyzer）本身是真实且设计良好的（优先级瀑布定位失败发生地），但它的产出只进了 traces 表和提案 prompt，**没有回流**到教学决策（例如 PREREQUISITE_MISSING 高发时给 planner 注入“先补前置”提示——这类联动不存在；M7 的 build_directive 读的是失败模式历史，给的是泛化提醒）。

### 2.7 知识谱系 `/knowledge`（M5，冻结但作为联动核心）

功能全量清单（`knowledge/page.tsx`，754 行主逻辑 + 8 个子组件）：

1. **三级筛选**：学段 segmented 单选（默认本科，无数据回落首个学段）→ 学科（必选单科）→ 教材组 → 卷；“全部教材”全局重置；下层“当前学段全部学科/当前范围全部教材组”分层清除；大数据量时显示“仅前置关系”开关。
2. **搜索穿透**：学段全量概念/节匹配（`search.ts` 统一匹配逻辑），结果面板 + ‹ i/N › 循环定位，命中后自动切换学科/教材组范围并下钻定位。
3. **三级下钻**：章节总览（章卡：节数·概念数副标题，跨教材范围时补教材组来源前缀）→ 节卡片层（课/篇目 + “本单元概念”虚拟卡承载直挂章概念）→ 章内概念 DAG（PREREQUISITE/RELATED 边）；面包屑逐级返回；零概念课文下钻改开详情抽屉不留空画布。
4. **概念抽屉 ConceptDrawer**：概念详情 + **双 CTA**（“在对话中学这个”/“出几道题考我”，带概念上下文 auto-send 深链）。
5. **个性化学习路径条 LearningPathBar**：`GET /student/learning-path`（四级优先组装 `_personalized_next`，零 LLM 确定性：① M9 本周计划未掌握概念 → ② 承接最近教学日志的可学后继 → ③ M9 目标学科内可学节点 → ④ 学段基础补全），每条带 reason 徽标（学习计划/承接“X”/目标学科/学段基础），点击带推荐理由深链进对话。**这是知识谱系与 M9 目标唯一的现有交点**。
6. **掌握度 overlay**：节点四态变色（未学/初学/掌握/熟练，BKT 记录 ∪ 记忆状态并集，账号隔离）。
7. **教材图谱管理 CustomGraphList**：自有教材图谱列表（查看=切学段选组 / 删除二次确认；P6-A4 手动构建端点已移除，图谱只来自教材）。
8. 头部统计（章·节·概念·边·learned_edges）+ “去教材库”按钮。

后端：`GET /knowledge/graph`（支持 `level/subject/textbook_id/file_id/view=overview|chapter|search|full` 按需加载）、`GET /knowledge/taxonomy`（学段→学科→教材组三级动态投影，资料中心元数据是唯一事实源）、`GET /knowledge/concepts/{id}`。合并视图 `graph_for` = seed(空) ∪ learned ∪ 公用 ∪ 自有（双命名空间 mtime 缓存）。**判定：功能真实、性能问题正在被在途提交修复。**

### 2.8 学习计划 `/plan`（M3）

功能清单：

1. **教学模式卡**：ModeStepper 六模式步进条（当前模式 = teaching-log 里 last_ts 最近概念的 current_mode）+ 当前模式 focus 文案 + **动态难度表盘**（1–5 内部模型，最近 5 题准确率 ≥80% 升 / ≤40% 降，DifficultyDots 可视化）。
2. **PathList 两栏**：“下一步学什么”（`learning-path.next_to_learn`，去对话深链“帮我学 X”）/“该复习什么”（掌握 0.3–0.8 且久未触碰）。
3. **TeachingLog 教学日志**：每概念 (mode, outcome) 历史跨轮记录全表。

后端 `GET /student/learning-path` = M3 curriculum + M9 plan/goal + M2 mastery 的确定性组装（`student.py:269`），**真实**。

问题：**与 /knowledge 底部 LearningPathBar 是同一个端点、同一种数据**（next_to_learn + review + difficulty），只是 /plan 多了教学模式/难度/教学日志三块 M3 视图。两个页面各拿一半，用户需要在两页之间跳才能看全“计划”。这是**页面级重复语义**的最典型样本。

### 2.9 冻结模块状态确认（不迭代，仅核对现状）

- **RAG 教材库 `/resources/textbooks`**：功能完整在位（上传必选学段/scope公用/group 组、构建状态机与进度、详情抽屉章节大纲、终止解析、刷新三模式 rag_graph/graph_only/full_ocr、卷管理、容量策略、图表/页码状态探测）。当前实例正在跑公共教材构建/升级（git 工作区里大量 `knowledge/custom/public/*.json` 与 `chat_history/library/data/public/*.txt` 变化即为证据）。**冻结状态正常，勿动。**
- **知识检索（knowledge_search 工具 + 证据门 + 混合检索）**：BM25 常驻 + 可选向量 + RRF、Structured V2 切块、证据门（问句门修复在案）、R10 确定性预检索、伪工具标签护栏——全部在位且为对话/笔记共用底座。**冻结状态正常，勿动。**
- **笔记 `/notes`（M-Notes）**：三栏仓库 + 四模式笔记智能体 + M9 温故同步在位。**冻结状态正常；注意其 M9 温故同步（`upsert_review_card`）是活的，M9 改动时需兼容 `note:` 前缀概念。**
- 其他在位模块一句话：`/chat` 对话工作台（SSE/答题卡/引用资料/当前资料栏/语音）正常；`/archive` 归档中心（含记忆遗忘状态展示：recent/compacted/legacy_unknown 三态文案）正常；`/admin` 管理台（账号/数据清理/OCR 策略/回收站/保留策略）正常。

---

## 3. 记忆体系专项核查（对照你的描述逐条确认）

### 3.1 你的三层记忆描述 vs 实际实现

| 你的描述 | 实际对应物 | 核查结论 |
|---|---|---|
| “智能体永久记忆之一：**用户风格记忆**（改善对话质量）” | `students/<id>.prompt_memory.json`（M6 活动提示词记忆）：仅 4 字段——总体学习情况 / 当前水平 / 语气偏好 / 讲解偏好；窗口默认 15 会话（用户可调 5–30）；每轮经 supervisor 3e 钩子注入 `[提示词记忆·精简画像]` 软指令；legacy 路径同样注入（`chat_agent._legacy_prompt_memory_block`） | **确认存在且工作**。注意：写入是**规则型**（`_detect_preferences` 正则匹配“简洁/耐心/一步一步/举例/先给结论”等偏好句式 + 作答对错计数），不是每轮 LLM 提炼；LLM 只在整体压缩时用一次 |
| “永久记忆之二：**学习内容之类的记忆**（维护其他模块、不放入跨对话记忆读取）” | **不是一份存储，而是一组业务档案**，确实都不进跨对话 prompt：① M2 `students/<id>.json`（画像+BKT+概念状态）；② M3 `<id>.teaching.json`（每概念教学模式史）；③ M9 `<id>.orchestration.json` + events（计划/SRS/习惯）；④ `<id>.learning_records.json`（独立学习账本：题目/作答/评分/知识点/时间，删来源对话仍保留）；⑤ `<id>.quiz_recent.json`（最近 100 题快照）；⑥ `<id>.procedural.json`（策略成功率，有界、活）；⑦ `<id>.habit_patterns.json`（习惯聚合——**写而不读，死数据**）；⑧ `<id>.ux_profile.json` + ux_events（M8 交互画像） | **确认存在**。跨会话对话召回另由 `recall_history` 工具的 transcript 检索承担（`CROSS_SESSION_MEMORY=workspace`，仅同工作区会话），与 prompt memory 是两条独立通道 |
| “**工作区共同记忆**（记录工作区学习情况、服务工作区其他对话、可在工作区内跨对话读取）” | `Workspace.public_memory`（`core/workspace_memory.py`）：7 字段 LLM 结构化摘要（学习领域/已讲概念/资料/错题/偏好/进展/待办）；每轮对话后异步合并更新（fire-and-forget，重载合并防竞态）；超 `SOFT_BUDGET_TOKENS×4` 字符自压缩；**新会话边界整体压缩一次**（`compact_workspace_memory_on_new_session`，session.py:221 触发）；移入对话时扫描 transcript 初始化；注入为 L2 preamble 独立块并声明“与检索原文冲突时以检索原文为准”；随工作区 bundle 归档/恢复/彻底删除；单聊删除不回退 | **确认存在且边界正确**。当前实例 0 个活动工作区，功能处于“实现完毕但无实例”状态；唯一可视化是侧边栏工作区展开区原文展示 |
| “这些记忆也会被压缩” | 三层压缩全部在位：① 会话内 GSSC compaction（完整回合增量压缩 + 出题作答 digest 注入 + 二次压缩不丢旧摘要）；② prompt memory 滑出窗口确定性折叠进 core + `maybe_compact_core` 整体 LLM 压缩（每代一次，`disable_thinking`，700 字/字段上限 + core 1800 字符硬上限轮裁）；③ workspace memory 超限自压缩 + 边界压缩 | **确认存在**。压缩的“代数”（compaction_generation）与会话归属（compacted_session_ids，旧数据标 legacy_unknown 不伪造归属）都有审计 |

### 3.2 注入与隔离验证

- 用户级 prompt memory：普通对话与工作区对话**全局统一计数与读取**（register_session 在会话边界注册，session.py:203）；压缩在新会话边界后异步触发（supervisor.py:1549 也有轮末触发点）。
- 工作区共同记忆：仅同工作区会话 preamble 注入；`test_workspace_memory_boundary.py` 在案。
- 旧版 episodic/semantic：**不注入任何 prompt**（M6 `build_directive` 只走 prompt_memory；retrieval.py 头注“active prompt path uses only prompt_memory.build_directive”）。
- 删除/遗忘契约：归档对话可勾选“永久遗忘提示词影响”；窗口内 contribution 立即可撤；压入 core 的不可拆分（UI 明示）；到期清扫自动移除可归属贡献——前端归档页三态文案（memoryWillForget/memoryCompacted/memoryLegacyUnknown）与后端 `session_forget_status` 一致。

### 3.3 旧版情景/语义数据的实况（你的判断 100% 正确）

- 生产写侧停产证据链：`append_episode` 无调用方；M6 `consume_turn` 只写 procedural/habit/prompt_memory；`maybe_consolidate` 直接返回 `{"consolidated": False, "reason": "legacy_read_only"}`；memory API docstring 明言 compatibility read-only。
- 但**四个消费方仍在读这份死数据**（这是本次检查最重要的 bug 级发现，详见 §4 问题 1–3）：dashboard 活动图、M8 streak/greeting、M9 习惯连击、M9 模拟置信度。
- 数据实况：重度用户旧 episodes 最后写入 8/23（16KB），新用户无此文件；`.semantic.json` 停在 8/10。记忆中心两个 Tab 对新用户是永久空态，且空态文案描述的是已停产的机制。

### 3.4 可视化缺口汇总（你说“这些记忆也应该有可视化”——当前确实没有）

| 记忆 | 内容 | 当前可视化 | 缺口 |
|---|---|---|---|
| 用户级提示词记忆 | 4 字段画像内容、最近窗口会话清单、压缩代数/计数、注入字符数 | 仅“窗口数字输入框 + 已压缩 N 个”一行 | **画像内容本体不可见**（用户无从知道 AI 记住了自己什么、也无从纠正）；recent_sessions 不可见；directive_chars 不可见 |
| 工作区共同记忆 | 7 字段摘要全文 + 更新时间 | 侧边栏工作区展开区纯文本 | 记忆中心无入口；无结构化字段展示；无压缩状态/历史；无“哪些对话贡献了记忆” |
| 学习账本 learning_records | 题目/作答/评分/知识点/时间/来源状态 | 无直接视图（错题本只取 wrong/partial） | 完整作答历史无处可看 |
| 程序性记忆 procedural | 策略成功率 | 记忆中心 Tab（活） | 已覆盖，够用 |
| 习惯聚合 habit_patterns | 连续性/时段效率等 | 无 | 且数据本身写而不读（应先决定去留） |
| 旧版情景/语义 | 审计数据 | 记忆中心 2 个 Tab | 占 2/3 版面展示死数据 |

---

## 4. 问题总清单（按严重度分级）

### P0 —— 数据源已死，用户可见的错误/冻结信息（应最先修）

1. **学习总览“近 14 天学习活动”卡**：`dashboard/page.tsx:63 getEpisodes(200)` → 旧版 episodic。生产停产写入后，新用户永远空态；老用户数据冻结在最后一次旧版写入日。空态还会让用户以为“系统没记录我的学习”。
2. **三处“连续学习天数”全部死源**：① `/ux/motivation`（`motivation_engine._active_days_from_episodes`）→ dashboard StatCards + GreetingBar + profile MotivationCard；② M8 greeting 的 streak；③ M9 HabitCard 连击/最长连击/活跃天数（`manager.record_turn:153` → `refresh_habit(episodes)`）。同一死源喂了两个模块的四个 UI 位置，且 M8/M9 各算一遍（重复语义 + 重复计算）。
3. **问候语“继续上次的内容——X”死源**：`ux_intelligence/context_builder.greeting` 读旧 episodes 最近 5 条找 last_concept。应改读 M3 teaching-log（真实、活跃）。

### P1 —— “假智能”/死功能（展示存在但无实效，或代码已死）

4. **M7 改进提案假闭环**：approved/applied 无任何消费方；提案只是一句话文本，无可执行载体；每 15 trace 才产 1 条。用户在洞察页做的“批准/已应用”操作实际不改变任何系统行为。
5. **M7 A/B 实验层（experiment.py）死代码**：无调用方、无端点、无 UI。
6. **M6 habit_patterns.json 写而不读**：M6 consume_turn 在 M9 事件（habit_milestone/task_batch_completed/goal_progress）时写入；唯一读者 `M9 manager._habit_patterns_safe` 自身无调用方。纯浪费写入。
7. **M9 进度预测（learning_state_simulator.py 327 行 + `/orchestration/simulation` 端点）死代码**：前端卡已下线（真实用户反馈“抽象投影数字不可行动”），端点与模拟器保留但无人调用；`simulate()` 还读死源 episodes 做置信度。前端 `api-modules.ts` 的 `getOrchSimulation`/`regenerateOrchPlan` 同为死客户端。
8. **`.env` 的 `DEFAULT_GRADE=高中` 死配置**：config.py 读入后无消费方（P1 学段去僵化残留），留着会误导维护者以为还有默认学段。

### P2 —— 重复语义/重复展示（合并优化的主要对象）

9. **两套目标系统**：M2 profile.goals（对话规则检测 goal_set 事件 → 画像页“学习目标”）vs M9 长期目标（编排页唯一真目标体系）。互不同步、语义重叠。
10. **两套 streak**：M8 motivation streak vs M9 habit streak（且同源同算法各算一遍）。
11. **/plan 与 /knowledge 重复**：同一个 `GET /student/learning-path` 端点，/knowledge 底部条拿 next_to_learn，/plan 拿全套 + M3 视图；用户需要两页跳转。
12. **表达偏好三拥有者**：M2 learning_style（学术深度）、M8 ux_profile（语气/详略/图示/节奏/耐心）、M6 prompt_memory（语气偏好/讲解偏好）——三者都注入提示词影响表达，边界有文档但用户视角是三张说不清差别的画像。
13. **dashboard EvalSummaryCard 与 insights OverviewStats 四数字完全重复**。
14. **dashboard StatCards“需关注”口径（<0.5）与 AttentionCard（<0.4）不一致**（`StatCards.tsx:19` vs `AttentionCard.tsx:30`）。

### P3 —— 联动弱/体验细节

15. **长期目标与知识谱系联动弱**（§2.2 六点详述：单学科、字符串匹配、全量 gap 而非目标链、description 恒空、deadline 无解释力、长期任务建议不查图谱）。
16. 测评中心概念自由文本不接图谱（BKT 归因靠模糊匹配兜底）；前端冗余传 `student_id:"student_default"`。
17. 记忆中心情景/语义空态文案描述已停产机制（误导）；两 Tab 占 2/3 版面。
18. GoalCard 差距分析只显示前 6 条且无“这是全学科 gap 还是目标链”的说明。
19. `/memory` 页与 `/profile` 页、侧边栏三处分散展示记忆/画像碎片，无统一入口。

---

## 5. 优化建议（按模块；只给方案不给代码改动）

> 总原则：① 先修 P0 数据源（一处实现、多处消费）；② 再做合并与联动（用户可感知的价值）；③ 死代码清理放最后（低风险高整洁度）；④ 全程不动冻结模块（教材库/知识检索/笔记）；⑤ 等在途“图谱冷构建性能修复”提交后再动 M5/M9 相关文件。

### 5.0 数据源统一修复（P0，所有模块优化的前置）

新建一个“学习活跃度聚合”读侧助手（确定性，零 LLM），把“某生在哪些天有学习行为”从**一份活数据**推导，候选源（全部活跃且已有读取器）：

- `learning_records.json`（每次作答都有 ts）；
- `teaching.json`（每概念 last_ts / 历史）；
- `orchestration_events.jsonl`（任务完成/复习/连击事件）；
- `ux_events.jsonl`（每轮 UX 事件）；
- `eval_traces.jsonl`（每轮 trace）。

取并集按日聚合后：

- 替换 `motivation_engine._active_days_from_episodes` → M8 streak/greeting/active_days 复活；
- 替换 `habit_tracker.compute_streak_from_episodes` 的输入 → M9 HabitCard 复活（顺带消灭双算：M9 refresh_habit 与 M8 current_streak 调同一助手）；
- dashboard ActivityCard 改喂同一聚合（14 天每日计数；事件类型可细分作答/讲解/复习三色）；
- greeting 的 last_concept 改读 teaching.json 最新概念。
- 旧 episodes 仅在聚合为空时作为**兼容回退**（照顾存量老用户的历史活跃天数），并在报告中标注来源。

### 5.1 学习总览 `/dashboard`

1. **活动卡**：按 5.0 换源；副标题从“每日学习事件数”升级为“作答 / 讲解 / 复习”三系列 Sparkline（数据都有）。
2. **统计卡**：streak 换活源；“需关注”口径统一为 <0.4（与 AttentionCard 一致）或反之，二选一。
3. **EvalSummaryCard 处置**：总览页的目标是“学生视角”，M7 增益/待审批是“系统视角”——建议**移除**该卡（洞察页已有完整版），或降级为一句“系统健康度”文案 + 链接。
4. **增强（可选）**：加一张“最近作答成绩”迷你卡（learning_records 最近 10 次对错），比 M7 增益对学生更有行动性。
5. TodayTasksCard 保持（无目标隐藏的决策合理）。

### 5.2 学习编排 × 知识谱系联动（本次优化的核心价值点）

目标：让“长期目标”从一张静态卡片变成“基于知识链的可行进路线图”。分四步，全部复用现有件：

1. **目标创建接图谱（概念级绑定）**：
   - GoalForm 增加“从知识谱系选概念”：复用编排页已有的 `ConceptMultiPick` + `/knowledge/taxonomy`，按学段→学科→教材组浏览勾选目标概念（支持整章勾选）；自由文本仍保留（模糊匹配到图谱节点后提示确认）。
   - 后端 `LearningGoal` 增加 `target_concept_ids`（持久化在 orchestration state）；`_analyze_goal_safe` 改为：目标概念集的**前置闭包**（沿 PREREQUISITE 向下取依赖，剔去已掌握 p≥0.75）作为 required_skills——gap 从“全学科未掌握”变成“达成该目标缺的链”。多学科自然支持（不再依赖 subjects[0]）。
   - 学科字符串匹配降级为兜底（无概念绑定时维持现状）。
2. **GoalCard 差距区升级为“路线图”**：
   - gap 列表按拓扑层分组展示（第 1 层现在就能学 → 第 2 层需先完成…），每条带掌握度与“去学”深链；
   - “进度”分母从全学科概念数改为目标链概念数——进度条从此有真实含义；
   - 每条 gap 与 `/knowledge` 概念抽屉互通（点击跳谱系定位）。
3. **周计划/今日任务与图谱互相导航**：周概念胶囊、今日任务行加“在谱系中查看”链接（`/knowledge?…` 定位参数）；知识谱系概念抽屉反向显示“属于目标《X》· 距目标还差 N 个概念 · 当前层 L”。两端各加一个入口即可，无需新端点（concept_id 双方都有）。
4. **长期任务建议接图谱上下文**：`longtask_advisor` 的 LLM prompt 目前只有任务标题；把该生目标学科的图谱片段（目标概念 + 最近教学日志概念 + 弱项概念名列表）注入同一小调用，建议从“通用套话”变成“结合你正在学的 X”。门控逻辑不变。
5. **deadline 变成解释性输出**：GoalState 已有 urgency 与 required_skills 数量——在 GoalCard 显示“按每周 N 个概念，预计 X 周完成，距截止还有 Y 周 → 紧凑/宽松”一行人话结论（纯函数，零 LLM；复活一点 `learning_state_simulator` 里 headline() 的确定性思路，但只输出这一句，不做抽象投影卡）。
6. **清理**：确认移除 `simulation` 端点与 `learning_state_simulator.py`（或整文件留着但不暴露端点——建议直接删，git 有历史）；`_habit_patterns_safe` 删除；`api-modules.ts` 的 `getOrchSimulation`/`regenerateOrchPlan` 删除。

### 5.3 测评中心 `/assessment`（轻改）

1. ConfigCard 概念输入接 `/knowledge/taxonomy` 概念选择器（与 5.2 同一个选择组件），自由文本保留为兜底——测评结果从此稳定归因到图谱节点。
2. 前端删掉 `student_id:"student_default"` 冗余传参（后端本就忽略）。
3. 错题本/最近习题/近期会话三卡保持；可选把“错题本”置顶为默认第一屏（CAT 是低频操作，错题重练是高频）。
4. 可选：SummaryCard 完成后给“把薄弱概念加入周计划”一键（调既有 `POST /orchestration/week/{i}/concept`），打通 M4→M9。

### 5.4 记忆中心 `/memory` 重构为“记忆总览”（可视化三层记忆）

页面重排为四个区块（旧情景/语义降级收尾）：

1. **提示词记忆（用户级永久记忆）——核心新区**：
   - 画像内容卡：`core_profile` 四字段逐条展示（只读 + “这就是 AI 跨对话记住你的内容”说明）；`directive_chars` 显示为“当前每轮注入约 N 字”徽标；
   - 最近窗口会话清单：`recent_sessions`（会话名/所属工作区/最近贡献时间/是否有贡献），窗口外的显示“已压缩 N 个（不可按会话撤销）”；
   - 窗口设置沿用现有 5–30 输入框；
   - （可选）每字段旁给“不准确？通过对话纠正即可”提示——写入路径本就靠对话中的偏好表达。
   - 以上**全部字段后端已返回**（`public_view`），纯前端工作，零后端改动。
2. **工作区共同记忆区**：列出用户各工作区（`GET /workspaces` 已含 `public_memory`）→ 展开显示 7 字段结构化摘要 + 更新时间；无工作区给引导（“创建学习区后，同区对话共享一份学习情况记忆”）。侧边栏原文展示可保留为快捷入口。
3. **学习内容档案区（不进对话的记忆）**：三个入口卡——学习账本（`learning_records`：最近作答列表 + 对错分布；新增一个只读端点或复用错题本端点扩参）、教学档案（链接 `/plan` 教学日志）、编排档案（链接 `/orchestration`）；明示“这些记忆用于维护你的掌握度与计划，不会被注入对话提示词”——正是你描述的语义边界。
4. **程序性记忆 Tab 保留**；旧情景/语义合并为一个“历史审计（只读）”折叠区或独立 Tab 排最后，顶部加“以下为旧版系统留存数据，仅审计用途，不再更新”，修正两处误导性空态文案。
5. 后端小改（可选）：`GET /memory/prompt-profile` 增加“最近一次压缩时间/代数”展示字段（state 里已有 compaction_generation，public_view 补一个即可）。

### 5.5 我的画像 `/profile`（合并去重）

1. **删 M2 goals 区**（或改为只读镜像 M9 目标：`GET /orchestration/plan` 已有 goal）——目标唯一真相源归 M9；M2 的 goal_set 事件写入保留（无妨）但不再展示。
2. **MotivationCard 换活源**（按 5.0）；或直接删除（dashboard/编排已各有一个 streak 展示，三处展示同一数字过多）——建议保留 profile 版（里程碑节点条是三处中信息最丰富的），删 dashboard GreetingBar 的重复徽章。
3. **画像卡整合**：M2 学术卡 + M8 交互卡保留双卡，但每张卡加一行“数据从哪来”（事件驱动/反馈驱动），把“为什么有两张画像”说清；中期可把 M6 提示词记忆的语气/讲解偏好与 M8 的语气/详略做**读侧合并展示**（各字段标注来源模块），写侧维持现状不动（避免破坏注入链路）。
4. IdentityCard（游客）逻辑保留。

### 5.6 系统洞察 `/insights`（让“智能评估”真智能，或诚实降级）

两个方向二选一（推荐 A，工作量可控且闭环完整）：

- **方向 A：把提案做成可执行的真闭环**
  1. advisor prompt 升级：要求输出结构化提案（target 具体化：`teaching_strategy.{mode}.depth_floor`、`prompt.tutor.{section}` 一类**可寻址参数**，或限定为“给某教学模式的策略参数建议”）；一次产 1–3 条。
  2. 新增一个**策略覆盖存储**（per-student，例如 `students/<id>.policy_overrides.json`，白名单字段 + 值域校验）：`PATCH /evaluation/proposals/{id}` 带 `status=applied` 时把提案落进覆盖存储；
  3. 一个真实消费点起步即可：M3 `TeachingEngine` 选模式/深度时读覆盖（例如“该生 REMEDIATION depth 上调一档”），并在 teaching directive 里注明“来自已应用的改进提案 #id”——闭环最小化、可观测、可撤销（DELETE 覆盖即回滚）。
  4. 洞察页提案卡显示“已应用 → 影响了最近 N 轮”（读 eval_traces 对比），让用户看见因果。
- **方向 B：诚实降级**：洞察页删除 approve/apply 按钮，提案改为“诊断建议（只读）”，文案说明“建议供人工参考”；同时删 experiment.py。页面保留诊断分布/策略排名/上下文预算/Trace 表（这些是真实有价值的观测）。
- 无论 A/B：删除 experiment.py 死代码；OverviewStats 与 dashboard 的重复按 5.1.3 处理。

### 5.7 页面级合并建议（汇总）

| 合并项 | 建议 | 理由 |
|---|---|---|
| `/plan` + `/knowledge` | **/plan 并入 /knowledge**：知识谱系页加“计划”区（教学模式步进 + 难度表盘 + 教学日志入口），`/plan` 路由重定向保留旧深链 | 同一 learning-path 端点；谱系是概念的家，模式/难度/路径天然同屏；导航从 11 项减 1 |
| dashboard EvalSummary | 删除 | 与洞察页重复 |
| streak 三处展示 | 保留 profile MotivationCard + 编排 HabitCard（数据统一后二者口径一致），删 dashboard GreetingBar 徽章 | 同一数字三处展示 |
| M2 goals vs M9 goal | 画像页改为镜像 M9 | 目标唯一真相源 |
| 记忆中心 + 画像 | **不合并页面**（一个管“AI 记住什么”，一个管“你是谁/账号”），但互相加链接；画像页“表达偏好”与记忆中心“提示词画像”字段级标注来源 | 语义有别，合并会把 M0 账户/注销混进记忆页 |
| 记忆中心情景/语义 | 合并为“历史审计”尾区 | 死数据不应占主版面 |

### 5.8 清理清单（低风险，放最后做）

- 删 `backend/app/agents/evaluation/experiment.py`（死代码）。
- 删 `learning_orchestration/learning_state_simulator.py` + `/orchestration/simulation` 端点 + `simulate()` 方法 + 前端 `getOrchSimulation`/`regenerateOrchPlan`。
- 删 `_habit_patterns_safe`；决定 habit_patterns.json 去留——若 M9 事件不再需要长期习惯聚合则同时删 `habit_pattern.consolidate_habit_events` 写侧与数据文件迁移说明；若保留则给它一个读者（如 daily_composer 候选池参考），**二选一，不要维持写而不读**。
- 删 `.env` 的 `DEFAULT_GRADE`（及 config.py 字段或保留字段但文档标注 deprecated）。
- 修正记忆中心两处旧机制空态文案。
- 测评前端删冗余 student_id 传参。
- （文档）DESIGN §16 补充“提案消费点/或明确无消费点”的现状描述，避免下次再误读。

---

## 6. 实施顺序与风险控制

1. **前置**：等待并验证在途“图谱冷构建性能修复”提交（涉及 `knowledge/*`、`learning_orchestration/manager.py`、`student_model/*`、`api/v1/orchestration.py`、`main.py`）——§5.2/5.0 会动到相同文件。
2. **第一批（P0，纯后端读侧 + 少量前端）**：学习活跃度聚合助手 + 三处 streak/greeting/活动卡换源。改动面小、行为可预期、新老用户立即可见。
3. **第二批（价值最高）**：§5.2 目标×谱系联动（后端 target_concept_ids + 前置闭包 gap；前端 GoalForm 选择器 + 路线图 + 双向导航）。
4. **第三批**：§5.4 记忆中心重构（几乎纯前端，后端最多加 1 个只读字段/端点）。
5. **第四批**：§5.6 洞察闭环（方向 A 涉及 M3 读侧，注意回归 `test_teaching_engine.py`）与 §5.5 画像去重、§5.7 页面合并。
6. **收尾**：§5.8 清理清单。
7. **全程红线**：不动 `/resources`（教材库正在跑公共库构建）、不动 knowledge_search/证据门/hybrid 检索、不动 `/notes`；M9 改动兼容 `note:` 前缀温故卡；所有新读侧助手遵循现有“try/except 只记 trace 不影响对话流”的钩子纪律；每批跑 `python -m unittest discover -s tests`（871 个用例）+ 前端 `tsc --noEmit && next lint`。

---

## 7. 附录

### A. 目标模块前后端对照速查

| 模块页 | 读取端点 | 写端点 | 数据文件 |
|---|---|---|---|
| /dashboard | /ux/greeting /ux/motivation /student/mastery /student/teaching-log /memory/episodes(旧) /evaluation/report /orchestration/plan /orchestration/today | — | students/\<id\>.json · teaching.json · episodes.jsonl(旧) · ux_profile.json · orchestration.json |
| /orchestration | /orchestration/plan /orchestration/today | /orchestration/{goal,regenerate,task,task/{id}/complete,week,week/{i}/concept,week/{i}/task,week/{i}/task/{tid}/subtask,week/{i}/task/{tid}/suggest,longtask,longtask/{id}/suggest} + PATCH/DELETE 族 + PATCH /schedule | students/\<id\>.orchestration.json · .orchestration_events.jsonl |
| /assessment | /assessment/report /quiz/recent /student/error-notebook /chat/sessions | /assessment/{start,answer,next,abandon} | students/\<id\>.assessment.json · quiz_recent.json · learning_records.json |
| /memory | /memory/{episodes,semantic,procedural} /memory/prompt-profile | PUT /memory/prompt-profile/window | episodes.jsonl(旧) · semantic.json(旧) · procedural.json · prompt_memory.json · prompt_memory_pref.json |
| /profile | /student/profile /ux/profile /ux/motivation /user/profile | PUT /user/profile · DELETE /user/account | students/\<id\>.json · ux_profile.json · users/accounts.json |
| /insights | /evaluation/{report,traces,proposals,context-budget} | PATCH /evaluation/proposals/{id} | eval_traces.jsonl · evaluation.json |
| /knowledge | /knowledge/{graph,taxonomy,concepts/{id},custom} | DELETE /knowledge/custom/{topic_key} | knowledge/custom/\<sid\>/tb-*.json |
| /plan | /student/learning-path /student/teaching-log | — | teaching.json · students/\<id\>.json |

### B. 关键代码位置索引（本次核实过的）

- 前端：`dashboard/page.tsx:63`（getEpisodes）· `StatCards.tsx:19` vs `AttentionCard.tsx:30`（口径）· `ActivityCard.tsx`（episodes 源）· `TodayTasksCard.tsx:24`（无目标隐藏）· `orchestration/page.tsx`（全流程）· `GoalCard.tsx:275`（description 恒空）· `HabitCard.tsx` · `WeeklyPlanCard.tsx` · `memory/page.tsx` + `memory/strings.ts`（mem.note）· `lib/api.ts:875-895`（prompt-profile 客户端）· `lib/types.ts:259`（PromptMemoryProfile 全字段）· `sidebar/WorkspaceItem.tsx:97,160`（工作区记忆展示）· `api-modules.ts:192-263`（编排客户端，含死函数）
- 后端：`agents/memory/prompt_memory.py`（全文 409 行：策略/正则偏好/折叠/压缩/public_view）· `agents/memory/manager.py:47-57`（build_directive 只走 prompt_memory）· `core/workspace_memory.py`（全文）· `api/v1/memory.py` · `supervisor.py:256-327`（3e/6d 钩子）· `core/session.py:203-226`（会话边界注册 + 压缩任务 + 工作区边界压缩）· `ux_intelligence/motivation_engine.py:21-60` · `ux_intelligence/context_builder.py:59-95`（greeting）· `learning_orchestration/manager.py:153/211-434/1145-1318` · `learning_orchestration/goal_analyzer.py` · `learning_orchestration/habit_tracker.py:79-169` · `evaluation/trace_analyzer.py` · `evaluation/advisor.py` · `evaluation/schema.py:388`（GATE=15）· `evaluation/experiment.py`（死）· `assessment/adaptive_test.py` · `api/v1/student.py:269`（learning-path）· `core/config.py:144`（default_grade 死配置）
- 数据：`students/usr_dd845d7b6c.*`（含旧 episodes/semantic）· `students/usr_66662250af.*`（无 episodes）· `students/prompt_memory_policy.json` · `chat_history/workspaces/`（无活动工作区）

### C. 本次检查通读/核对的文件

- 文档：README.md、docs/DESIGN.md（全文）、.zcode/plans/plan-sess_2ecbb4bb….md（在途工作确认）
- 前端：lib/nav.ts、lib/api-modules.ts、lib/api.ts(prompt-profile 段)、lib/types.ts(PromptMemoryProfile 段)；dashboard/orchestration/assessment/memory/profile/insights/knowledge/plan 八个模块的 page.tsx + strings.ts + 全部子组件（含 ConceptDrawer/LearningPathBar/ConfigCard/ErrorNotebook/RecentQuestions 关键行为）；sidebar/WorkspaceItem.tsx
- 后端：api/v1/{memory,evaluation,student,ux,orchestration,assessment(探针),workspace(段)}.py；agents/memory/{manager,prompt_memory,episodic(接口),store(段)}.py；core/workspace_memory.py；core/session.py(段)；supervisor.py(钩子段)；ux_intelligence/{motivation_engine,context_builder(段),manager(段)}.py；learning_orchestration/{manager,goal_analyzer,habit_tracker}.py；evaluation/{manager,trace_analyzer,advisor,experiment(调用面)}.py；assessment/adaptive_test.py；core/{error_notebook(段),config(段)}.py
- 数据形态：students/、chat_history/、knowledge/custom/、notes/、users/ 的目录结构与文件时间戳（未读取任何对话正文）

---

*本报告只描述检查时点（2026-08-24）的现状。若与后续代码演进冲突，以代码为准。*

---

## 附录：核验修正与处置对照（2026-08-25，原文不改）

> 本附录是对上文的逐条核验结果：报告主体判断基本准确，以下 10 处细节与代码事实有出入，特此修正并附智能化统一改造（批次1-6）后的终态。行号以核验时（v4 提交后）为准。

1. **streak 消费点为 4 处，报告漏了 TopBar**：除 StatCards/MotivationCard/HabitCard 外，`TopBar.tsx` 顶栏火焰徽章也读连续天数。终态：四处全部换源到统一活动聚合（批次1），语义一致。
2. **「subjects 为空就全图谱分析」有前置条件**：仅当 subjects 为空**且**消息中提取不到任何学科关键词时才落入全图谱分支；有任一学科线索则按学科。终态：批次2 修正了空 subject 直接全图的分支（无绑定→学科兜底→仍无→全图）。
3. **goal_type 与 target_level 的真实语义**：goal_type=EXAM/ABILITY 映射 PROFICIENT 目标水平、仅 INTEREST 映射 INTERMEDIATE；target_level 仅展示用，不参与推理。报告表述为独立决策因素有偏差。
4. **urgency 的作用面**：urgency 参与 recommended_strategy 排序，但**不影响**周计划的任务密度（密度由 weekly_pace/schedule 决定）。终态：批次2 新增的确定性排期预估（tight/ok/loose）同样不吃 urgency。
5. **ConceptMultiPick 的选项来源**：其选项来自**计划内概念**（当前周/差距），不接 taxonomy 全量——所以批次2 另建了谱系概念选择器（GenealogyConceptPicker）供目标表单/测评共用，原组件语义保留。
6. **/knowledge 原无 URL 参数处理**：核验属实。终态：批次2 已加 `?concept=<图谱节点id>` 一次性深链（切范围+下钻+高亮+开抽屉），编排差距行/测评/任务胶囊均走此入口。
7. **EvalSummaryCard 是 3 个数字**（增益/已评估/待审批），非 2 个。终态：批次1 已整卡替换为「最近作答卡」（读学习账本），与 M7 观察职责解耦。
8. **注意力阈值差异在代码而非配置**：AttentionCard 0.4 与画像口径 0.5 的差异是两处硬编码，无配置项。终态：批次1 统一为 0.5。
9. **habit_patterns 的触发事件确为 4 种**（habit_milestone/task_batch_completed/milestone_completed/goal_progress），但核验时**写而不读**（零消费）。终态：批次6 C9 转正——M9 日编排经 `daily_composer.habit_context` 真实消费。
10. **文案夸大与测试基数**：insights「每 15 轮生成一批提案」不实（每次仅 1 条，批次5 C11 已修）；全量测试核验时约 1371 项，改造收口后为 **1402 项**（新增活动聚合/布鲁姆/目标链/教学指导/文档页等回归）。

> 逐项核验均以 `file:line` 证据复核；完整架构与遗留物处置见 `docs/DESIGN.md` 文末「智能化统一改造（2026-08-25 收口）」章节（含 C1–C16 台账）。
