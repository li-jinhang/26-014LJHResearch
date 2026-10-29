# 证据审查

`audit_optimization_points.py` 只读检查证据链、卡片状态、已声明实现路径和实验控制约束。它输出的是待核验发现，不能直接当作科研结论或写入卡片。

审查只检查 `01约束文件.md` 显式声明的目录。没有声明时输出 `needs_configuration`；已声明但当前不存在、且无法检查时输出 `not_applicable`。它不会以 `src/`、Recall/NDCG 或固定种子作为隐式默认值。
