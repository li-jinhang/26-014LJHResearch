---
status: accepted
---

# 支持 coding agent 与外部控制模块作为研究驱动方

独立程序在 `D:/_Projects/26-014LjhResearch` 维护；科研 skill 在用户指定的 `C:/Users/QH/.agents/skills/ljh-research` 维护。coding agent 与用户自制的外部控制模块均可驱动科研任务，并共用科研操作与证据规则；显示面板可通过外部控制模块发起操作。这样保留 skill 的 agent 使用方式，也支持用户自行组装控制入口，避免每个入口分别维护科研规则。

外部控制模块可以自行接入推理提供方，既可使用 coding agent，也可使用其他模型或决策模块；科研判断不限定为由 coding agent 完成。各入口共用科研操作与证据规则，替换推理来源不改变这些规则。

UI 不依赖底层 Python 配置格式、脚本参数或内部模块结构。驱动接口和面板接口按业务操作定义，操作、查询和事件使用与语言无关的协议，自制模块不限定为 Python。Python 调用仅是可提供的适配方式之一。

命令行 JSON 接口作为跨语言调用的基础入口，可选本地 HTTP 适配器供显示面板连接。两种入口使用相同的业务操作和数据契约；coding agent 与外部控制模块使用基础操作时不要求先启动 HTTP 服务。首版公开协议为 v1，具体格式见 `docs/contracts.md`。

单任务控制权见 ADR-0003。首版实现及实际验证范围见 `docs/verification.md`。
