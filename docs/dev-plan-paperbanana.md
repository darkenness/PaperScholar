# PaperBanana 功能复刻开发计划

> 创建时间：2026-02-28
> 目标：将 PaperScholar 的生成质量提升到 PaperBanana 原版水平

## 现状总结

PaperScholar 已复刻了 PaperBanana 的五 Agent 流水线架构，但提示词和风格指南被大幅简化，核心差距：
- Stylist 风格指南：105 行 → 7 行（信息量损失 >90%）
- Critic 评审提示词：~80 行 → ~15 行（丢失所有具体评审规则）
- Retriever 检索提示词：~70 行 → ~10 行（丢失检索策略）
- 评估框架：完全缺失
- Critic 回滚机制：缺失
- Pipeline Evolution 可视化：缺失

---

## 任务列表

### 第一轮：P0 提示词复刻（可并行）

#### P0-1: 完整复刻 Stylist 风格指南（Diagram + Plot）
- **状态**：✅ 已完成
- **文件**：`backend/app/agents/pipeline.py`（StylistAgent）、`backend/app/agents/polish_agent.py`
- **工作**：
  1. 将 `PaperBanana/style_guides/neurips2025_diagram_style_guide.md`（105 行）完整内容替换 pipeline.py 中的 `STYLE_GUIDE_CONTENT`（当前仅 7 行）
  2. 将 `PaperBanana/style_guides/neurips2025_plot_style_guide.md`（90 行）注入（当前 Plot 风格指南完全缺失）
  3. 同步更新 polish_agent.py 中的 `STYLE_GUIDE_DIAGRAM` 和 `STYLE_GUIDE_PLOT`
  4. 改为从文件加载风格指南（而非内联常量），方便后续更新
  5. 恢复丢失内容：颜色 HEX 码、形状规范、线条语义、排版规则、图标语义、领域特定风格、各图表类型指南
- **影响**：生成质量最大瓶颈，风格指南直接决定输出的学术美感
- **阻塞**：→ P0-2, P2-1, P2-2

#### P0-3: 完整复刻 Retriever Agent 检索提示词
- **状态**：✅ 已完成
- **文件**：`backend/app/agents/retriever_agent.py`
- **工作**：
  1. 恢复 Diagram Retriever 完整系统提示词：背景说明、Topic + Intent 双维度匹配逻辑、三级排名优先级（Best Match / Second Best / Avoid）、输出格式示例
  2. 恢复 Plot Retriever 完整系统提示词
  3. 添加 manual 检索模式支持（从预选的 agent_selected_12.json 加载 few-shot 示例）
  4. 恢复 Plot 任务不限制候选池大小的行为（当前统一截断到 200 条）
  5. 评估是否恢复 content 字段不截断的行为（当前截断到 200 字符可能影响检索质量）
- **影响**：检索质量决定 Few-shot 学习效果，间接影响所有下游 Agent
- **阻塞**：→ P1-2, P2-2

#### P1-1: 恢复 Planner Agent 缺失的学习指导语句
- **状态**：✅ 已完成
- **文件**：`backend/app/agents/pipeline.py`（PlannerAgent）
- **工作**：
  1. Diagram Planner：恢复 "and grasp the principles for generating such figures"
  2. Plot Planner：恢复 "and grasp the principles for generating such plots" 和 "You should learn from the examples' content presentation and aesthetic design (e.g., color schemes)"
  3. 检查 Few-shot 构建逻辑，确保参考示例的 content 不被过度截断（当前截断到 1500 字符）
- **影响**：引导 LLM 从参考示例中学习美学风格

---

### 第二轮：P0 逻辑复刻（串行）

#### P0-2: 完整复刻 Critic Agent 评审提示词
- **状态**：✅ 已完成
- **依赖**：← P0-1
- **文件**：`backend/app/agents/pipeline.py`（CriticAgent）
- **工作**：
  1. Diagram Critic：恢复 Content 评审维度（Fidelity & Alignment、Text QA、Validation of Examples、Caption Exclusion）
  2. Diagram Critic：恢复 Presentation 评审维度（Clarity & Readability、Legend Management）
  3. Plot Critic：恢复 Content（Data Fidelity、Text QA、Validation of Values、Caption Exclusion）
  4. Plot Critic：恢复 Presentation（Clarity & Readability、Overlap & Layout、Legend Management）
  5. Plot Critic：恢复 Handling Generation Failures 部分
  6. 恢复修改原则："modifications based on the original description, rather than rewriting from scratch"
- **影响**：Critic 是迭代优化的核心，提示词质量直接影响每轮改进的有效性
- **阻塞**：→ P0-4, P1-2, P2-2

#### P0-4: 实现 Critic 迭代回滚机制
- **状态**：✅ 已完成
- **依赖**：← P0-2
- **文件**：`backend/app/agents/pipeline.py`（_run_critic_loop）
- **工作**：
  1. 添加 `current_best_image_key` 追踪每轮最佳图片
  2. Visualizer 生成失败时回滚到上一轮最佳图片
  3. 参考 PaperBanana `paperviz_processor.py` 的 `_run_critic_iterations`
  4. 确保回滚时 SSE 事件正确推送
- **影响**：防止 Critic 迭代中单次生成失败导致整个任务失败
- **阻塞**：→ P1-3, P2-3

---

### 第三轮：P1 功能增强

#### P1-2: 实现完整的评估框架
- **状态**：✅ 已完成
- **依赖**：← P0-2, P0-3
- **文件**：新建 `backend/app/services/evaluation_service.py`、`backend/app/api/evaluate.py`
- **工作**：
  1. 移植 `PaperBanana/utils/eval_toolkits.py` 的评估逻辑
  2. 移植 8 个评估提示词（Diagram 4 维度 + Plot 4 维度）：Faithfulness、Conciseness、Readability、Aesthetics
  3. 实现两层决策：Tier 1（Faithfulness + Readability）→ Tier 2（Conciseness + Aesthetics）
  4. 后端 API：`POST /api/v1/evaluate/{task_id}`
  5. 前端：历史记录/结果详情页添加"评估质量"按钮
  6. 支持多模型评估（Gemini/Claude/OpenAI）

#### P1-3: 实现 Pipeline Evolution 可视化
- **状态**：✅ 已完成
- **依赖**：← P0-4
- **文件**：新建 `backend/app/api/evolution.py`、前端新增组件
- **工作**：
  1. 后端 API：`GET /api/v1/generate/{task_id}/evolution` 返回各阶段中间产物
  2. 前端：横向时间线（Planner → Stylist → Critic Round 1 → ...）
  3. 每个节点展示：阶段名称、描述文本、图片
  4. Critic 节点额外展示改进建议
  5. 支持点击放大和左右对比模式

#### P1-4: 完善 Vanilla Agent 独立实现
- **状态**：✅ 已完成
- **依赖**：无
- **文件**：`backend/app/agents/pipeline.py`
- **工作**：
  1. 从 `PaperBanana/agents/vanilla_agent.py` 移植 Diagram/Plot 系统提示词（各约 15 行）
  2. 为 vanilla 模式添加独立处理逻辑

#### P1-5: 添加 dev_polish 和 dev_retriever Pipeline 模式
- **状态**：✅ 已完成
- **依赖**：无
- **文件**：`backend/app/agents/pipeline.py`（PipelineEngine）、前端 Generate 页面
- **工作**：
  1. dev_polish 模式：直接对用户上传图片执行 Polish Agent
  2. dev_retriever 模式：仅执行 Retriever，返回检索到的参考示例
  3. 前端下拉框添加这两个选项

---

### 第四轮：P2 优化打磨

#### P2-1: 实现风格指南自动生成工具
- **状态**：✅ 已完成
- **依赖**：← P0-1
- **文件**：新建 `backend/app/services/style_guide_service.py`
- **工作**：
  1. 移植 `PaperBanana/style_guides/generate_category_style_guide.py`（304 行）
  2. 管理员 API：`POST /api/v1/admin/generate-style-guide`
  3. 支持用户上传自定义参考图集 → 自动生成风格指南

#### P2-2: 清理 prompts/ 目录死代码，统一提示词管理
- **状态**：✅ 已完成
- **依赖**：← P0-1, P0-2, P0-3
- **文件**：`backend/app/prompts/`、`backend/app/agents/pipeline.py`
- **工作**：
  1. 确认 prompts/ 目录是否被引用
  2. 统一提示词管理位置
  3. 添加提示词版本标记

#### P2-3: Visualizer 图像格式统一为 JPG + 智能跳过优化
- **状态**：✅ 已完成
- **依赖**：← P0-4
- **文件**：`backend/app/agents/pipeline.py`（VisualizerAgent）
- **工作**：
  1. 添加 PNG → JPG 转换（quality=95）
  2. "No changes needed" 时复用上一轮图片而非重新生成
  3. 确保前端兼容 JPG base64

---

## 依赖关系图

```
P0-1 (风格指南) ──┬──→ P0-2 (Critic提示词) ──→ P0-4 (回滚机制) ──┬──→ P1-3 (Evolution可视化)
                  │                                                │
                  │                                                └──→ P2-3 (JPG+智能跳过)
                  │
                  ├──→ P2-1 (风格指南自动生成)
                  │
                  └──┐
P0-3 (Retriever) ──┤──→ P2-2 (清理死代码)
                    │
P0-2 ──────────────┤
                    │
P0-3 + P0-2 ───────┴──→ P1-2 (评估框架)

P1-1 (Planner语句)     → 无依赖，随时可做
P1-4 (Vanilla Agent)    → 无依赖，随时可做
P1-5 (新Pipeline模式)   → 无依赖，随时可做
```

## 参考文件路径

| 源文件 (PaperBanana) | 目标文件 (PaperScholar) |
|---|---|
| `PaperBanana/style_guides/neurips2025_diagram_style_guide.md` | `backend/app/agents/pipeline.py` StylistAgent |
| `PaperBanana/style_guides/neurips2025_plot_style_guide.md` | `backend/app/agents/pipeline.py` StylistAgent |
| `PaperBanana/style_guides/generate_category_style_guide.py` | 新建 `backend/app/services/style_guide_service.py` |
| `PaperBanana/agents/retriever_agent.py` 提示词 | `backend/app/agents/retriever_agent.py` |
| `PaperBanana/agents/critic_agent.py` 提示词 | `backend/app/agents/pipeline.py` CriticAgent |
| `PaperBanana/agents/vanilla_agent.py` 提示词 | `backend/app/agents/pipeline.py` vanilla 模式 |
| `PaperBanana/agents/planner_agent.py` 提示词 | `backend/app/agents/pipeline.py` PlannerAgent |
| `PaperBanana/utils/eval_toolkits.py` | 新建 `backend/app/services/evaluation_service.py` |
| `PaperBanana/prompts/diagram_eval_prompts.py` | 新建 `backend/app/prompts/eval_prompts.py` |
| `PaperBanana/prompts/plot_eval_prompts.py` | 同上 |
| `PaperBanana/scripts/paperviz_processor.py` _run_critic_iterations | `backend/app/agents/pipeline.py` _run_critic_loop |

---

## 补充差距分析（dev-plan 未覆盖）

> 以下问题在上方任务列表中未被完整覆盖，按优先级排列。

### S1: Stylist 系统提示词本身被严重简化

- **优先级**：P0（与 P0-1 同步处理）
- **文件**：`backend/app/agents/pipeline.py` L29-42
- **现状**：
  - `DIAGRAM_STYLIST_SYSTEM` 仅 ~10 行通用指令
  - `PLOT_STYLIST_SYSTEM` 仅 2 行
- **原版**（`PaperBanana/agents/stylist_agent.py`）：
  - `DIAGRAM_STYLIST_AGENT_SYSTEM_PROMPT` ~40 行，包含完整 ROLE/TASK/INPUT/OUTPUT 结构和 5 条 Crucial Instructions：
    1. Preserve Semantic Content（不改语义）
    2. Preserve High-Quality Aesthetics（已有高质量描述不要覆盖）
    3. Respect Diversity（不同领域有不同风格，不要盲目标准化）
    4. Enrich Details（补充缺失的视觉属性）
    5. Handle Icons with Care（图标有语义含义，如 snowflake=frozen，需参考原文验证）
  - `PLOT_STYLIST_AGENT_SYSTEM_PROMPT` ~20 行，包含 Context Awareness 指导
- **建议**：在执行 P0-1 时一并替换系统提示词，直接使用原版完整内容

### S2: StylistAgent 未按 task_type 区分风格指南

- **优先级**：P0（与 P0-1 同步处理）
- **文件**：`backend/app/agents/pipeline.py` L126-153
- **现状**：`StylistAgent.process()` 对 diagram 和 plot 都注入同一个 `STYLE_GUIDE_CONTENT`（仅含 diagram 内容：形状、箭头、图标等）。Plot 任务收到的是 diagram 风格指南，完全不相关。
- **原版**：根据 `task_name` 从 `neurips2025_diagram_style_guide.md` 或 `neurips2025_plot_style_guide.md` 分别加载
- **注意**：`backend/app/agents/style_guides/` 目录下已有完整的两个 md 文件，但 pipeline.py 完全没有引用
- **建议**：改为从文件动态加载，按 task_type 选择对应风格指南

### S3: Retriever 候选 content 截断过于激进（200 字符）

- **优先级**：P0（与 P0-3 同步处理）
- **文件**：`backend/app/agents/retriever_agent.py` L134
- **现状**：每个候选的 content 截断到 200 字符 `str(item.get("content", ""))[:200]`
- **原版**：不截断，完整传入 `str(item['content'])`
- **影响**：200 字符对于理解一篇论文的方法论远远不够，LLM 无法准确判断候选与目标的相关性
- **建议**：移除截断或大幅放宽（至少 2000 字符），同时注意 token 预算

### S4: Planner few-shot 示例 content 截断到 1500 字符

- **优先级**：P1（与 P1-1 同步处理）
- **文件**：`backend/app/agents/pipeline.py` L89
- **现状**：`str(item_content)[:1500]`
- **原版**：不截断，完整传入 `item_content`
- **影响**：长方法论被截断后，LLM 无法从参考示例中学习完整的描述模式
- **建议**：移除截断，依赖模型的上下文窗口自然限制

### S5: Critic 迭代中 revised_description 传递存在 Bug

- **优先级**：P0（与 P0-4 同步修复）
- **文件**：`backend/app/agents/pipeline.py` L317-330, L470-481
- **现状**：
  - CriticAgent 解析 JSON 失败时 `parsed = {}`，导致 `revised_description = "No changes needed."`
  - 此时 Visualizer 会用旧描述重新生成，浪费一轮迭代
  - 更严重的是：如果 critic 给了 suggestions 但 revised_description 解析失败，`_run_critic_loop` 不会 break（因为 suggestions != "No changes needed."），但 Visualizer 用的是旧描述，产生无效循环
- **建议**：JSON 解析失败时应视为本轮无效，跳过 Visualizer 重新生成

### S6: Visualizer Plot 模式代码清洗不够健壮

- **优先级**：P1
- **文件**：`backend/app/agents/pipeline.py` L168
- **现状**：`code.replace("```python", "").replace("```", "").strip()` — 如果 LLM 返回代码前后有解释文本，会被一起传给 exec
- **原版**：用正则 `re.search(r"```python(.*?)```", code_text, re.DOTALL)` 精确提取代码块
- **建议**：改用正则提取，fallback 到 strip 后的全文

### S7: `POLISH_SYSTEM` 是死代码

- **优先级**：P2
- **文件**：`backend/app/agents/polish_agent.py` L18-22
- **现状**：定义了 `POLISH_SYSTEM` 常量但 `PolishAgent.process()` 从未引用。polish 步骤的图像生成用裸内联 prompt，没有 system prompt
- **建议**：要么删除死代码，要么在 polish 图像生成时注入 system prompt

### S8: Retriever 目标 content 截断到 2000 字符

- **优先级**：P1（与 P0-3 同步评估）
- **文件**：`backend/app/agents/retriever_agent.py` L131
- **现状**：`content[:2000]`
- **原版**：不截断，完整传入 `str(data["content"])`
- **影响**：目标论文的方法论被截断后，检索匹配精度下降
- **建议**：与 S3 一起评估，考虑 token 预算后决定截断策略

---

## 补充任务与现有任务的关联

| 补充项 | 建议合并到 | 说明 |
|---|---|---|
| S1 Stylist 系统提示词 | P0-1 | 替换风格指南时一并替换系统提示词 |
| S2 风格指南按 task_type 区分 | P0-1 | 改为从文件加载时自然解决 |
| S3 Retriever 候选截断 | P0-3 | 恢复检索提示词时一并调整截断策略 |
| S4 Planner content 截断 | P1-1 | 恢复 Planner 语句时一并处理 |
| S5 Critic 描述传递 Bug | P0-4 | 实现回滚机制时一并修复 |
| S6 Plot 代码清洗 | P2-3 | Visualizer 优化时一并处理 |
| S7 POLISH_SYSTEM 死代码 | P2-2 | 清理死代码时一并处理 |
| S8 Retriever 目标截断 | P0-3 | 与 S3 一起评估 |
