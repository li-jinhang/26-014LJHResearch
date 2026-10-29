# 研究点（RP）

RP 是 `ljh research docs/2研究点/` 下的可验证假设卡片。使用 `research_point.py add` 创建 `RP-0001-<slug>.md`；`--slug` 可选，ID 是唯一引用。

状态只能为 `draft`、`active`、`validated`、`rejected`、`paused`。`implemented` 只表示已有实现证据，不表示科学验证完成。状态变更先补充卡片的来源与证据、核心内容、当前判断；manual 遵循本次批准的卡片/状态范围，auto 可在任务授权内更新证据支持的状态。

每个 RP 明确假设、适用条件、竞争解释、可区分预测和证据缺口。检索既有 RP/EXP/REPRO/PAPER 后再新增，避免同一未知被换标题重复研究。暂停低收益方向用 paused 并记录重启需要什么新证据；rejected 需要与假设范围匹配的反证，不能仅因预算用完。

从 `active` 到 `validated` 会产生 `framework_adoption: pending_decision`，之后由 `scheduler.py next --id RP-0001` 提示用户是否采纳；不能自动改写主框架。

所有 RP 与 EXP、REPRO、PAPER 的关联都使用稳定 ID 写入 `related_ids` 或 Markdown 链接，不能通过猜测标题建立关联。
