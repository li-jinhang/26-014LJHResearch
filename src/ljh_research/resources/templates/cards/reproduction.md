---
id: {{ID}}
schema_version: 1
title: {{TITLE}}
type: reproduction
paper_id: {{PAPER_ID}}
method: {{METHOD}}
status: {{STATUS}}
priority: normal
dataset: {{DATASET}}
alignment_metrics: {{ALIGNMENT_METRICS}}
paper_metrics: {{PAPER_METRICS}}
tolerance: {{TOLERANCE}}
repo_url: {{REPO_URL}}
created: {{CREATED}}
updated: {{UPDATED}}
tags: {{TAGS}}
source_ids: []
related_ids: []
---

# {{TITLE}}

## 摘要

待补充：复现目标、范围与当前阶段。

## 来源与证据

- 论文标题：{{TITLE}}
- 知识库主题：{{TOPIC}}
- 上游仓库：{{REPO_URL}}

## 核心内容

待补充：模型 `{{MODELS_DIR}}/<model>.py`、配置 `{{CONFIGS_DIR}}/<MODEL>.yaml`、运行脚本与日志 `{{EXPERIMENTS_DIR}}/<REPRO-NNNN>-<Method>/`。

### 数据与评估协议

待补充：数据集 {{DATASET}}、切分、训练项屏蔽、top-K、valid_metric，以及与论文口径的已知偏差。

### 对齐指标与论文值

{{PAPER_METRICS}}

### 轮次记录

## 结果

待补充。

## 局限性

待补充。

## 当前判断

待补充。

## 关系

使用 `reproduces: [[0知识库/...]]`、`supports:` 或 `contradicts:` 记录与论文、研究点和实验的关系。

## 迭代历史

- {{CREATED}}：创建复现卡片，对齐目标 {{ALIGNMENT_METRICS}}（tolerance={{TOLERANCE}}）。
