# 自包含 setup 分发验证 · 2026-10-29

根目录 `ljh-research-setup/` 现包含完整 skill、原生 bootstrap、标准库安装器、四个 wheel 与 SHA256 清单。核心 wheel 随附 auto/manual 变体、共享科研指南和模板；面板 wheel 包含前端资源。默认离线安装无需源码目录、构建依赖或包索引。维护入口为 `tools/build_setup_skill.py`，同时生成独立 ZIP。

完整行为回归 **97 项通过，0 失败，0 跳过**，耗时 79.333 秒；日志 `.local/test-results-portable-setup.txt`。新增三项测试验证随附源码/资源一致性、只读计划与损坏包拒绝，以及完整搬移安装链路。Git 换行转换在一致性检查中按 LF 归一化。

完整搬移测试仅复制 setup 目录到含空格的临时路径，通过 Windows PowerShell 原生入口创建隔离环境并从四个 wheel 离线安装。另建无核心的普通 Python 调用端，通过独立 runtime binding 创建 manual 项目、切换 auto、校验工作区；再次搬移下载目录后，已部署入口仍可读取工作区及分层记忆指南。全过程不把应用源码加入调用端路径，不修改真实科研项目或测试中的用户默认绑定。

setup、auto、manual 均通过 skill 格式校验；PowerShell 语法解析与 shell 的 `bash -n` 通过。完成本机全局 setup 同步并备份旧副本；本机运行时也由仓库内 `.venv` 切换到用户应用数据目录的独立安装，旧配置已备份。此前真实项目保持原有文件，未批量重新部署。

本轮实际运行平台为 Windows。Linux 原生安装、缺少 Python 时的下载安装、可选 PDF 依赖下载及真实推理提供方未在本轮执行；确定性夹具不证明科学判断质量。历史来源路径和旧架构的验证记录保留在下方，不是当前安装依赖。

# 分层记忆验证 · 2026-10-29

实现统一 memory.import/extract/search/read/rebuild/status：平铺论文来源、单项提炼、多领域/方法专题、跨类型知识、增量语义回写、来源哈希/行号与失效识别。实验卡更新和新经验自动接入提炼；默认上下文改为相关检索、最近两条科学记录和证据定位。

完整回归 **94 项通过，0 失败，0 跳过**；日志 `.local/test-results-layered-memory.txt`。新增 15 项记忆行为测试与 1 项参考控制器记忆闭环测试。旧双根布局仅由显式兼容入口测试，新增默认入库验证平铺布局。回归发现并修复了旧测试启动器环境变量污染新流程的问题，兼容开关现限定于旧 CLI 子进程。

真实样本为两篇论文、两份实验、两条经验，全部复制到应用 `.local/layered-memory-pilot-20261029-verified`。来源科研目录 317 个文件的路径/SHA256 前后相同。验证自动结构提取、四种中英文问题检索、4000 字符预算、主题到对象再到 98 字符证据片段，以及 agent 的来源化语义回写。没有迁移真实科研目录或启动科研训练。

两个部署版本通过 skill 格式校验。核心与控制器 wheel 已重建、离线安装到独立环境，并从中立目录验证新记忆模块。详见 [分层记忆验证报告](layered-memory-validation.md)、[样本调用记录](evidence/layered-memory-pilot.json) 与 [wheel 验证](evidence/wheel-verification.json)。自动结构提取不等同于独立科学核验；外部模型无人值守语义研读质量尚未验证。

以下保留历史验证记录。

# 项目内部署与文档目录验证 · 2026-10-29

当前 LJH Research 全局发现目录只保留 `C:/Users/QH/.agents/skills/ljh-research-setup`。原 research/router、auto、manual 目录退出全局发现；完整工作文件与 Git 历史存于 `archives/global-research-skills-20261029-113802.zip`，按 462 个文件的 SHA256 核验。旧隐藏 Git 余留采用同盘移动保留在发现目录之外，未丢弃历史。

setup 将所选版本部署到单一项目的 `.agents/skills/ljh-research/`，统一 skill 名为 ljh-research；科研记忆目录为 `ljh research docs/`。公共 JSON 核心、工作区、卡片、Foam、本地执行与资源路径均已同步。受控 marker/hash 检查保护非托管或手工修改的本地文件；项目启动器拒绝跨项目参数与 stdin 请求。

完整回归 **78 项通过，0 失败，0 跳过**，日志 `.local/test-results-project-deployment.txt`。本轮新增 9 项，验证只读计划、唯一项目部署、切换与备份、另一项目保持原版本、保护手改/非托管内容、禁止部署到全局、从中立 cwd 运行与拒绝外部根、缺失文件修复、两种旧目录迁移与预算/引用保持、活动/未知状态和冲突拒绝、失败回滚。迁移测试发现 SQLite 上下文退出未关闭句柄导致 Windows 改名失败，已改为显式关闭连接并验证修复。

全局 setup 和两个实际部署的本地变体均通过 skill-creator quick_validate。通过全局启动器在 `.local/project-deployment-demo-20261029` 完成 manual 部署，且确认中文只读 plan 输出为 UTF-8。核心/执行插件 wheel 已重建并离线安装到独立 wheel-env，从中立目录验证包内变体资源、本地部署、版本切换和项目绑定启动器，详见 [wheel-verification.json](evidence/wheel-verification.json)。

仅隔离工作区参与部署/迁移测试，没有改动真实科研项目。旧文档目录不批量改名；setup.migrate 要求支持的所有权格式、明确授权、目标不存在、任务与执行可核实地不活跃，并保存改动元数据备份。无真实模型调用或科研训练，多平台边界沿用下方说明。

以下为此前全局双入口拆分的历史验证记录，其部署位置已被本轮决定替代。

# Manual / Auto 拆分验证 · 2026-10-29

本轮新增 `C:/Users/QH/.agents/skills/ljh-research-manual` 与 `ljh-research-auto`，setup 负责版本选择，旧 `ljh-research` 为兼容入口。科学指南迁入核心资源，核心与控制器同步实现科研计划/分析和严格终止。界面未作为本轮开发范围。

完整测试 **69 项通过，0 失败，0 跳过**，耗时 49.033 秒。命令 `.venv/Scripts/python.exe -m unittest discover -s tests -v`；日志 `.local/test-results-skill-split.txt`。在既有 55 项基础上新增 14 项：版本选择/快照、配置 CLI、初始化前指南读取、真实进程停止、截止时间跨恢复保持、终态与待决策不能恢复、manual 控制模块支持声明、未知执行核实、停止与提交并发、自动计划/分析约束、可信负面结束、复用已有证据零训练、上下文来源/截断，以及推理预算耗尽不自动扩容。

四个用户目录 skill 均通过 `quick_validate.py`。验证器在工具环境缺少 PyYAML，改用已有 Anaconda 解释器加 `-X utf8` 完成校验，没有向训练环境或工具运行环境新增依赖。Manual/Auto 入口的普通 Python 启动器也使用已登记的核心环境返回 UTF-8 JSON。

核心和控制器 wheel 已重建，在独立 wheel-env 中以离线方式安装；从中立临时目录验证工作区、卡片资源、版本选择和包内工作流。文件清单与 SHA256 见 [wheel-verification.json](evidence/wheel-verification.json)。拆分前工作文件保存在 `.local/before-skill-split-20261029-110137.zip`，旧 wheel 保存在 `.local/before-skill-split-wheels.zip`。

真实执行检查使用 Windows 上的短进程；科学决策场景与控制器采用确定性夹具，没有真实科研模型调用或真实训练。已验证结构约束和终止行为，不能据此宣称自动研究的科学判断质量已经实测。无常驻监管进程时，任务过期调度在后续任务访问时封存，已提交运行的超时则被剩余任务时限限制。未知/失联执行保持 stopping，不能算已终止。

以下保留上一轮历史验证记录。

# v0.1 验证记录 · 2026-10-27

实现与验证位于 `D:/_Projects/26-014LjhResearch`；科研 skill 修改位于用户指定的 `C:/Users/QH/.agents/skills/ljh-research`，新增 setup skill 位于同级 `ljh-research-setup`。未在推荐蒸馏科研项目执行初始化、迁移或训练。

## 自动测试

最终完整命令：`.venv/Scripts/python.exe -m unittest discover -s tests -v`。

**55 项通过，0 失败，0 跳过**。最终日志：`.local/test-results-final.txt`。范围包括：

- 迁移后的论文导入/去重/PDF、研究点、实验、复现、模板、Foam、约束路径及原有保护行为。
- 任务授权、原子单一控制权、显式接管与旧 lease 失效、工作区级任务排队。
- 配置快照、文件修订校验、预算、幂等提交、UTF-8 命令与运行日志。
- 真实短进程在驱动暂停后的继续执行与结果恢复。
- HTTP 请求格式、项目绑定、来源和本地 token 检查。
- 可替换控制模块的 JSON 启动协议；实际调用 JavaScript 测试插件。
- 参考控制模块使用公开接口完成文件生成、短进程执行、证据记录和完成结论。

本次重构涉及公共基础层、多个科研功能和发布资源，因此执行全量兼容回归。两个已安装 skill 均通过 skill-creator 的 `quick_validate.py`。前端通过 `node --check`；Windows bootstrap 脚本通过 PowerShell 语法解析与不带 Apply 的只读计划检查。

## 独立行为验证

独立验证使用公开 Python/JSON CLI、临时工作区和确定性推理夹具，没有真实模型调用。验证了预算跨进程保留、驱动不能自行批准、接管、暂停保留运行、超时、取消及跨入口恢复。

恢复场景：第一控制器进程运行至等待人工决策；新的 CLI 进程批准后，第二控制器进程继续至完成；实验始终只执行一次，推理预算累计五次。复现与证据保留于 `.local/validation/`，其中早期报告保留了修复前的失败事实。

发现并修复的边界问题：Windows 插件 stdin 编码、幂等键未比较 cwd/timeout、授权输入类型错误、HTTP 非对象请求未返回结构化错误。已加入仓库回归测试。

## 浏览器交互与视觉检查

通过真实 in-app browser 验证了：

1. 展示待授权任务并批准演示范围。
2. 启动控制模块，实际短进程完成，实验计数为一次、推理计数四次。
3. 从界面读取包含中文与 `✓` 的实际进程输出。
4. 创建第二个表单测试任务并拒绝授权，任务进入取消状态。
5. 保存项目默认配置，界面提示不影响已有任务快照。

检查时页面没有 console error/warning。已目视检查任务页和配置页；保存截图 [任务总览](evidence/panel-overview.png)、[配置环境](evidence/panel-environment.png)。没有声称完成移动端或多平台视觉验收。

## 安装与位置解耦

四个 wheel 已构建，并在独立、无系统包继承的环境中以 `--no-index --find-links dist` 离线安装。切换到中立临时目录后创建与校验工作区、生成研究点成功，核心导入来自该环境的 site-packages，而非 skill 或源码目录。

详细 wheel 文件清单和 SHA256 见 [wheel-verification.json](evidence/wheel-verification.json)。这验证了包资源的分发与基本位置解耦，不等于在没有 Python 的新系统完成了安装测试。

## 实测边界

- 当前主机：Windows，Python 3.12.7。Linux 原生引导与本地执行尚未在 Linux 主机实测。
- 缺少 Python 的引导流程已实现；本机已有 Python，仅验证只读计划，没有实际执行下载安装。
- Codex/Claude 适配器实现依据本机 CLI help 和官方非交互说明；未读取凭据、未发送真实模型请求，未验证其现场登录、配额和工具组合。
- 参考推理夹具用于协议验证，不能被称为完成了科学研究或训练。
- 远端连接、路径映射和远端进程管理提供独立执行插件接口；未交付已验证的 SSH 插件。
- 本地执行为可信主机进程，并非操作系统沙箱。协议授权与真正的系统隔离须区分。
