---
name: ljh-research
description: 'Run evidence-led autonomous research in an LJH Research workspace configured as auto: retrieve evidence, compare hypotheses, choose informative experiments, analyze credibility and continue, pivot or stop within approved task bounds. Use for sustained automatic investigation. Bounded user-selected work uses the project-local manual version; setup owns environment and version selection.'
---

# LJH Research Auto

由 coding agent 或可替换外部控制模块持续推进一个可回答的研究问题。自动科研以降低明确未知为目标，可信负面、有边界的答案或低信息收益都可以结束任务。

## 进入与恢复

1. `scripts/research.py workspace.get --project-root <project>` 核实工作区、项目约束和选择的版本。环境/初始化/切换版本交给 `$ljh-research-setup`。本入口只绑定部署它的单个项目，版本切换由全局 setup 重新部署；新任务采用 setup 的选择；已有任务读 `task.get`，以其冻结版本为准。
2. **开始科学判断前必读完整工作流**：`workflow.get` 参数 `{"version":"auto"}`；已有任务使用 `{"task_id":"TASK-..."}`。分析结果时同时读 `topic=conclusion-discipline`。这些指南由公共核心提供给两种驱动方，不能只依赖外部模型临场发挥。
3. 定义目标、已知/未知、成功与停止条件、允许修改路径/程序、实验和推理预算、单次运行/任务总时限、主要证据路径。task.create 产生具体待批准请求；真实用户同意后 decision.resolve，再 task.claim。选择 auto 本身不构成运行或修改授权。
4. 每轮通过 `research.context` 恢复科学记录，刷新已有运行并核对状态、剩余预算和控制权。摘要有截断标识，必要时 `file.read` 全文；既有日志/权重/复现足够时直接复用。unknown/submitting 先核实，不以新 key 重跑。

## 自动科研循环

遵循公共工作流：**检索证据 → 比较假设与竞争预测 → 选择有信息价值的动作 → 登记 plan → 实现/执行 → 可信度分析 → continue/pivot/stop**。

- `research.record(kind=plan)` 固定问题、至少两种解释的预测、证据、下一动作、预期信息、结果判据、停止规则和 run_keys。无新实验时 run_keys 为空。
- `run.submit` 带已登记的 plan_id、匹配的 request_key 和 argv/cwd；依据问题选择探索或受控验证，保留真实配置和评估口径。
- `research.record(kind=analysis)` 覆盖该计划全部已提交运行，分开观察、解释和局限；判断 valid/partial/invalid 后作出 continue/pivot/stop。计划未分析不能开启下一计划；决定 stop 后封存此次调查。
- `continue` 必须有明确未知和下一步价值；`pivot` 要解释旧判断如何更新；`stop` 后用 task.complete 保存有边界结论。失败/资源阻塞用 task.finish，不把无法研究写成科学否定。

auto 会在已批准范围内自行检索文献、维护卡片、实现、运行、分析和调整，不为同一授权的例行步骤反复询问。越界操作、增量预算或框架采纳通过具体人工决策请求处理。单纯耗尽预算不自动申请固定增量，不重置预算或另开任务续跑。

## 按科学对象取指南

通过 `workflow.get` 的 `topic` 按需取：`paper-management`、`research-points`、`experiments`、`reproduction`、`framework-evolution`、`align`、`review`、`foam-rag`。公共协议和可执行 plan/analysis 参数示例取 `task-control`。知识操作统一用 `knowledge.invoke`，公共包维护唯一实现和资源。

## 停止与报告

目标已回答、预定判据满足、后续信息价值低、预算/时限耗尽、资源/权限阻塞或用户要求停止时结束调度。可信负面不强制再试，初步正面及时记入证据；进一步复现/种子检验服务具体主张。报告实际做过的工作、来源和限制，区分实验成功、假设验证与框架采纳。

用户要求终止使用 task.stop，并核实所有运行已结束。驱动方离线/模型故障的暂停会保留已运行实验。已完成/失败/阻塞/取消的任务不能自动恢复。外部控制模块由 controller.start 通过公共插件协议启动，和 coding agent 遵循同一流程；提供方凭据和远程进程管理归各自插件。

调用方式：`python <this-skill>/scripts/research.py <method> --project-root <project> --params @<UTF8-JSON-file>`，或 stdin v1 JSON。`--human --evidence` 只转交真实用户决定。脚本仅选择已安装或已登记的工具环境；公共核心、指南与模板由 setup 随附安装，运行不依赖源码仓库或 setup 下载位置。本地执行是可信进程工具，不是操作系统沙箱。

## 项目部署

本 skill 由全局 `ljh-research-setup` 部署到当前项目的 `.agents/skills/ljh-research/`；项目只部署所选版本。科研记忆存入项目根目录的 `ljh research docs/`，与本 skill 分开。启动器从其安装位置确定项目，拒绝指向另一个项目的请求。

## 分层记忆读取范式

涉及读取资料、创新构思、设计/分析实验或沉淀经验时，必读 `workflow.get` 的 `topic=layered-memory`。先 `memory.search(query,purpose,budget_chars)` 检索主题和知识点，依 `memory.read` 下钻到所需对象/证据；研读后的新理解通过 `memory.extract` 引用真实片段回写。结构摘取不等于语义归纳或科学验证。
