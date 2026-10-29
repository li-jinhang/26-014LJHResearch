# Foam 派生检索

`ljh research docs` 是 Foam workspace。Markdown 和 front matter 是唯一真源；图、查询和后续向量索引都是可重建的派生层。

`foam_bridge.py status` 只读报告配置和 CLI 可用性。`bootstrap` 仅补齐缺失的 `.foam` 模板与查询；除非用户明确请求强制覆盖，否则不替换已有副本。查询使用受控状态值，例如 `active`、`planned`、`running` 和 `validated`。
