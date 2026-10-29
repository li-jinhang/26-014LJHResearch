# 框架演进

只有状态为 `validated` 的 RP 才能进入框架采纳。验证说明证据足以支持该假设；它不等于主框架已经变化。

`research_point.py status --id RP-0001 --status validated` 将采纳状态置为 `pending_decision`。先向用户说明证据与最小文档修改计划，取得明确批准后，才用 `research_point.py framework` 记录 `adopted` 或 `deferred`。自动模式同样不得绕过这一决策。

采纳时同步有事实变化的 `ljh research docs/02框架信息.md` 和 `调度.md`，保留版本、来源和关联 ID；项目代码或 README 的修改须已被任务授权覆盖，超出范围时取得具体授权。
