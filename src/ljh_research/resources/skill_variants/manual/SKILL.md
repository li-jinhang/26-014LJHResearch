---
name: ljh-research
description: 'Complete user-directed, bounded LJH Research work with strict task termination: papers, research points, experiments, reproduction and evidence review. Use when setup selects manual or the user asks for a specific research action. Continuous autonomous investigation uses the project-local auto version; environment preparation uses ljh-research-setup.'
---

# LJH Research Manual

完成用户选定的一项科研工作，分析真实证据并在约定交付范围结束。manual 可以完成实现、运行和分析所需的多个步骤；下一轮优化实验或研究方向由用户选择。

## 进入任务

1. 用 `scripts/research.py workspace.get --project-root <project>` 确认科研工作区、项目约束与 `research_version`。缺失环境/工作区交给全局 `$ljh-research-setup`。已有任务读 `task.get`，遵循其冻结版本；本入口只绑定部署它的单个项目；新任务使用 setup 选择的版本。通过全局 setup 重新部署切换版本，不改本地模板或全局目录。
2. **开始工作前必读终止协议**：`workflow.get`，参数 `{"version":"manual"}`；有任务时改为 `{"task_id":"TASK-..."}`。返回的 manual 规则是本版本的执行准则。公共接口详细用法取 `topic=task-control`。
3. 先检索已有卡片、论文、代码、日志与结果，确定本次交付物、允许范围、尝试上限、运行/任务时限和终止条件。将用户已明确授权的具体内容登记为 task.create → decision.resolve，再 task.claim；已有授权不重复询问，未授权的实际写入/运行先获得具体同意。

## 受控执行与交付

按用户选定目标完成操作。读下表对应的 `workflow.get` 主题，较大的资料用 `file.read` 获取；工具实现通过 `knowledge.invoke` 调用核心，不复制到 skill。

| 工作 | topic |
| --- | --- |
| 论文核验、导入与分析 | paper-management |
| 研究假设、卡片关联和状态 | research-points |
| 实验、预实验及结果解释 | experiments + conclusion-discipline |
| 官方实现复现与偏差分析 | reproduction + conclusion-discipline |
| 主框架采纳 | framework-evolution |
| 文档代码对齐／证据审查／知识检索 | align / review / foam-rag |

任务内机械步骤不逐次确认。修复当前交付物的错误需受尝试/预算上限约束；一次可信负面结果可以交付，不自动再跑“最小改动”或穷尽优化轴。记录事实、推断、假设和未知的区别。实现完成不等于验证完成，验证不自动采纳主框架。

## 严格结束

- 达到交付范围且全部运行已核实结束：`task.complete`，给出结果、证据和局限，然后结束本任务。
- 失败或当前关键阻塞无法推进：保存日志，以 `task.finish(outcome=failed/blocked)` 封存；有活动运行时使用 `task.stop`。不靠无限重试、另开任务或扩大范围继续。
- 用户要求停止/终止：立即 `task.stop`，不再做科研动作；核实 `outstanding_run_ids`，只有执行确已结束才报告“已终止”。`stopping` 和 `unknown` 要如实报告并继续停止核实。
- 已封存任务不能由旧 lease、旧批准或自动换任务 ID 恢复；下一项研究需要用户的新指令。用户明确说稍后继续时用 `task.pause`，它会保留已运行实验。

## 调用边界

`python <this-skill>/scripts/research.py <method> --project-root <project> --params @<UTF8-JSON-file>`；也可 stdin 发送 v1 JSON。`--human --evidence` 只用于转交真实用户授权，模型和插件不能批准自身请求。文件更新需先读 SHA256；执行用 argv 数组和稳定 request_key。manual 使用有界 agent/外部模块操作，不启动持续研究控制器。

公共协议、科研指南与模板由 setup 随附并安装的独立核心包提供；运行时与源码仓库、setup 下载位置无关。skill 中的脚本仅选择已安装或已登记的工具环境。本地执行插件是可信进程工具，不是操作系统沙箱。

## 项目部署

本 skill 由全局 `ljh-research-setup` 部署到当前项目的 `.agents/skills/ljh-research/`；项目只部署所选版本。科研记忆存入项目根目录的 `ljh research docs/`，与本 skill 分开。启动器从其安装位置确定项目，拒绝指向另一个项目的请求。

## 分层记忆读取范式

涉及读取资料、创新构思、设计/分析实验或沉淀经验时，必读 `workflow.get` 的 `topic=layered-memory`。先 `memory.search(query,purpose,budget_chars)` 检索主题和知识点，依 `memory.read` 下钻到所需对象/证据；研读后的新理解通过 `memory.extract` 引用真实片段回写。结构摘取不等于语义归纳或科学验证。
