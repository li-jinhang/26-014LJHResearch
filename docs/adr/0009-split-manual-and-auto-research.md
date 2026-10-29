---
status: accepted
---

# 拆分 Manual 与 Auto 科研入口

用户要求两套明确的科研行为契约：manual 由用户选择研究动作并严格结束任务，auto 自主完成证据检索、假设比较、实验选择、可信度分析与继续/转向/停止。setup 统一选择版本；两者继续支持 coding agent 与可替换外部模块。

安装两个独立 skill：ljh-research-manual 和 ljh-research-auto。旧 ljh-research 保留为兼容路由。两个版本共享同一核心、科学资源、证据链和插件协议，不复制 Python 实现。通用指南由核心 workflow.get 提供，外部模块无需读取技能目录。

选择仅存于项目约束 update_mode：manual 映射 manual，auto 映射 automatic。公开接口投影 research_version/skill_name；任务创建冻结版本，旧缺失版本的任务保持 manual 语义。setup 修改默认选择只影响新任务。

manual 明确 completed/failed/blocked/cancelled 终态，禁止旧 lease/旧决策恢复。新增 task.stop 先持久化 stopping、撤销控制权、关闭待决定项，再由执行插件取消并核实运行；状态未知时保持 stopping。task.pause/旧 task.cancel 保持既有保留进程语义。任务总时限从首次 claim 开始，恢复不重置；运行超时上限受剩余时限约束。无常驻监管进程时，空闲任务的截止状态在下次访问时更新。

auto 的计划与分析写入 Markdown 任务笔记；执行账本只引用 plan_id。公共核心校验计划先于新实验、分析覆盖全部关联运行、最终 stop 分析先于成功封存。可信度与假设质量仍由科研推理负责，结构校验不证明科学判断正确。推理预算耗尽不自动请求固定增量或再调用模型，封存现有证据并报告 blocked。
