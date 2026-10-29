# 分层记忆的读取与回写

四层职责：证据详情保留原件/全文/完整记录；单项提炼说明一篇论文、一次实验或一条经验；主题提炼聚合领域/方法；0知识库联结不同类型的证据与当前缺口。原件按类型存储，主题是多标签引用。一个来源只登记一个稳定身份。

## 按用途读取

先 memory.search(query,purpose,budget_chars)，其中 purpose 为 overview、innovation、experiment_design、result_analysis、debug 或 reproduction。检索覆盖登记过的对象与知识点，而非整个项目；零命中不能证明没有既有研究。返回 topic_entrypoints 可 memory.read(topic,kind) 读取主题提炼；命中 id 可读取单项。需要核实时再读取指定 source_id 的章节/行范围。硬预算单位是 JSON 结果的 Unicode 字符数，默认检索 5000、读取 7000，不冒充模型 token 计数。超出预算的完整知识点被省略并保留展开入口，不截断限定条件。

| 工作 | 优先读取 | 下钻条件 |
| --- | --- | --- |
| 了解领域/构思创新 | 主题、方法关联、旧假设与反证 | 需要核实机制、新颖性或迁移前提 |
| 设计实验 | 相关实验/研究点、控制条件、负面经验 | 需要确定配置、协议和可比性 |
| 分析结果 | 相关历史结果、适用条件与反例 | 新结果与过去不一致或证据不可信 |
| 排查问题 | 同类症状与经验 | 实施修复前核对环境与原始过程 |
| 复现 | 原协议及已有偏差 | 精确读取方法、设置与证据 |

项目硬约束仍从任务配置快照获取，不能因未命中关键词而遗漏。freshness=stale 时先核实当前证据，再更新提炼；主题来源失效时返回路由而不输出旧正文。coverage=partial 是研读范围，freshness=current 仅表示引用文件版本未变，二者都不是科学 validated。

## 导入与自动结构提取

memory.import 接受 kind、title、项目相对 path、可选 topics/keywords/origin/id/reading_notes。kind 为 paper/experiment/research_point/reproduction/experience。人类入口需真实授权；任务驱动方需有效 task_id/lease，来源须在声明目录内。论文原件直接进入 1论文/源文件库，提取全文进入 1论文/提取内容/<ID>/，单项卡进入各类型的知识提炼目录。默认可读取已有结构化笔记；PDF 缺少可读文本时标记待补，不能视为完成研读。

导入自动做保守的标题/段落/字段抽取，保留原句、公共条件、来源性质和精确行号。不把结构摘取称为独立科学核验。论文可以传 reading_notes，输出区分 reading_note 与 paper_claim。同源去重后添加主题，不复制原件。EXP/RP/REPRO 通过 knowledge.invoke 创建或结论更新后，自动按引用登记现有卡片；新经验写入 5经验/原始记录并提炼，不继续膨胀 03研发经验。

## 随研读进行语义回写

结构抽取不会替代科学归纳。读到新的重要内容后，在结束相关研读阶段前调用 memory.extract，填写简短 claims；普通重复查询没有新认识时保持原记录。新结论也须回写相关对象，文献主张、项目记录、推断与未知分别表达。语义回写默认增量合并，保留仍有效的旧点；需要修订时传 supersedes=[旧 point_id]。旧版本保存在历史快照，来源变化后的旧引用不继续作为当前知识。

每个 claim：

```json
{"text":"精炼机制/结果/经验，不扩大原证据范围","aspect":"architecture","keywords":["教师选择"],"conditions":["适用条件、配置或明确未知"],"evidence_type":"reading_note","citations":[{"source_id":"S02","source_sha256":"从 memory.read 返回","start_line":3,"end_line":5,"quote":"该行范围内真实存在的原句"}]}
```

aspect 为 architecture/innovation/application/result/condition/limitation/hypothesis/lesson/overview/unknown。evidence_type 为 paper_claim/reading_note/project_record/agent_inference/open_question。程序校验引用和哈希，但不能证明语义归纳正确。推断必须标明 inference。实验结果保留数据/划分/seed/预算/Valid/Test/选择规则与限制；负面或无效证据不得在压缩中丢失。一次单配置未提升不能概括为整个方法不可行。

memory.read(id) 返回知识点及引用；memory.read(id,view=detail,source_id) 返回章节目录；指定 section 或 start_line/end_line 才取证据片段。大段日志和完整论文不进入默认上下文。memory.extract(id) 可重做结构提取，显式 claims 则为 agent_semantic 回写；两者都会维护相关主题与派生索引。memory.rebuild 只重建视图，不替代原始事实；遇到手工专题内容会报告冲突。memory.status 报告已登记覆盖、待提取和失效对象。

## 科研调度

创新构思先查方法和历史反证；设计新实验先查相同问题/协议下的已有证据；结果分析先对照已有结果与经验。若摘要不足，按来源下钻，再决定补读论文或开展新验证。记忆查询辅助选择科研活动，不以检索分数冒充创新价值或科学证据强度。
