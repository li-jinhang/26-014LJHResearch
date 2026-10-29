# LJH Research

独立的科研操作核心、可替换控制模块与执行插件。根目录的 **[`ljh-research-setup/`](ljh-research-setup/SKILL.md) 是可单独分发的完整 setup skill**，包含程序包及构建项目内 auto/manual skill 所需的全部资源。其他用户无需保留本仓库或配置开发者路径。

全局只有 setup skill；它为一个明确项目部署所选的 manual 或 auto 版本。coding agent 与自制控制模块使用同一公开协议。

## 其他用户安装

1. 从 [GitHub 仓库](https://github.com/li-jinhang/26-014LJHResearch) 下载 ZIP 或克隆仓库，将完整 `ljh-research-setup/` 目录复制到 agent 的全局 skills 目录，例如 `~/.agents/skills/ljh-research-setup/`。保留其中的 `assets/wheels/`。
2. 让 agent 使用 `$ljh-research-setup`，指定要配置的科研项目，并选择 manual 或 auto。setup 先检查环境、显示计划，再根据授权安装与部署。
3. 后续科研在目标项目中使用 `$ljh-research`；论文、实验和经验保存在该项目的 `ljh research docs/`。

已有 Python >= 3.11 时，程序安装默认完全离线，不需要应用源码、构建工具或 PyPI。缺少 Python 时按 setup 的平台引导准备运行时；可选 PDF 支持另行安装。安装后的运行时与原仓库及 skill 下载位置解耦。

手动检查或安装（将占位路径替换为实际位置）：

```powershell
& '<setup-skill>/scripts/bootstrap.ps1' -Python '<python.exe>'
& '<setup-skill>/scripts/bootstrap.ps1' -Python '<python.exe>' -Apply
python '<setup-skill>/scripts/setup.py' create --project-root '<project>' --version manual --approve
```

```sh
sh '<setup-skill>/scripts/bootstrap.sh' --python '/path/to/python3'
sh '<setup-skill>/scripts/bootstrap.sh' --python '/path/to/python3' --apply
python3 '<setup-skill>/scripts/setup.py' create --project-root '<project>' --version manual --approve
```

`--approve` 表示用户已批准具体项目变更。完整安装与无 Python 情况见 [bootstrap](ljh-research-setup/references/bootstrap.md)。

| 组件 | 源码 / 安装位置 |
| --- | --- |
| 公共核心与 setup 生命周期 | `src/ljh_research/` |
| 参考控制模块 | `packages/controller/` |
| 本地执行插件 | `packages/local-executor/` |
| HTTP 适配器与独立前端 | `packages/panel/` |
| 项目内科研 skill（所选 manual/auto） | `<project>/.agents/skills/ljh-research/` |
| 非全局版本资源 | `src/ljh_research/resources/skill_variants/` |
| 项目内科研记忆文档 | `<project>/ljh research docs/` |
| 完整初始化与配置 skill | `ljh-research-setup/`，可整目录安装到用户 skills 目录 |

## 开发环境直接使用

在本目录执行：

```powershell
./.venv/Scripts/python.exe -m ljh_research_panel --project-root .local/demo-project --open
```

也可运行 `Start-LjhResearch.ps1`。演示项目用于接口验证，已完成的任务使用确定性推理夹具和真实短进程；它不代表科研模型训练或科学结论。

全局 setup 与项目内启动器会读取用户级 runtime binding，选择隔离解释器。项目内启动器从安装位置绑定项目，拒绝指向其他项目的参数或 stdin 请求。科学指南统一由安装包的 workflow.get 提供。

## 准备另一个项目

让 coding agent 使用全局 `$ljh-research-setup`。先检查环境并选择 manual 或 auto，再为指定项目 `plan`；已有明确授权后 `create --approve` 创建文档目录并部署唯一项目内 skill。科研工作使用该项目内的 `$ljh-research`。`repair` 补齐缺失项，`deploy` 部署/更新本地版本，切换前保留备份且拒绝覆盖手工改动。

```powershell
python '<setup-skill>/scripts/setup.py' doctor
python '<setup-skill>/scripts/setup.py' plan --project-root '<project>'
python '<setup-skill>/scripts/setup.py' create --project-root '<project>' --version manual --approve
python '<setup-skill>/scripts/setup.py' version --project-root '<project>'
python '<setup-skill>/scripts/setup.py' version --project-root '<project>' --select auto --approve
python '<setup-skill>/scripts/setup.py' deploy --project-root '<project>' --version manual --approve
python '<setup-skill>/scripts/setup.py' migrate --project-root '<project>' --from "ljh research" --approve
```

缺少 Python 的系统由 setup 的 PowerShell / shell 引导流程准备用户级运行时；安装需提供经过核验的官方来源。当前机器仅运行了 Windows 的只读安装计划，没有重新安装 Python。Linux 引导脚本尚未在 Linux 主机实测。

旧 `ljh research/` 和 `.ljh-research/` 不会与新目录并行创建；setup 提示显式迁移。迁移仅处理受支持的已拥有格式，要求任务/运行不活跃且状态可核实；重命名后修复记录路径、保留预算和元数据备份，冲突时不合并。其他真实科研项目不会被实现验证批量改名。

## 从源码或发布包安装

此节供维护者开发和重新打包；一般用户直接使用上面的完整 setup skill。

公共核心、执行插件、控制模块和面板是四个独立发行包。Python >= 3.11；核心运行时不依赖第三方 Python 包，PDF 提取可选安装 `ljh-research-core[papers]`。

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install . ./packages/local-executor ./packages/controller ./packages/panel
```

完整 setup 的 `assets/wheels/` 随仓库提供四个 wheel，可在有 Python 的目标环境离线安装：

```text
python -m pip install --no-index --find-links ljh-research-setup/assets/wheels ljh-research-core ljh-research-local ljh-research-controller ljh-research-panel
```

修改程序、指南或变体后，重建随附包并验证，随后一并提交源码和 `ljh-research-setup/`：

```powershell
./.venv/Scripts/python.exe tools/build_setup_skill.py
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

构建脚本生成 `ljh-research-setup/assets/wheels/manifest.json` 和可独立下载的 `dist/ljh-research-setup.zip`。回归包含源码与随附包的一致性检查，以及只复制 setup 目录到临时位置后的离线安装、manual/auto 部署、搬移后启动验证。`tools/install_skills.py` 默认显示把完整 setup 同步到本机全局目录的计划；`--apply` 执行并备份旧副本。

## 任务控制

科研记忆采用证据详情 → 单项提炼 → 主题提炼 → 跨类型知识。论文原件平铺在 `1论文/源文件库/`，提取全文位于 `1论文/提取内容/<ID>/`；领域和方法通过多标签专题组织。研究点、实验、复现、经验都有各自的知识提炼。新经验写入 `5经验`，`03研发经验.md` 保留简短导航与历史内容。

使用 `memory.search(query,purpose,budget_chars)` 查找知识点和主题入口，再 `memory.read` 展开对象或证据章节/行。`memory.import` 自动做来源化的结构摘取；agent 的新理解通过 `memory.extract` 增量回写，附适用条件、来源性质、原句、行号和 SHA256。替代旧点使用 supersedes，历史版本保留。来源变化会使摘要失效，专题不继续输出旧正文。字符预算约束完整 JSON 返回，不是假定的模型 token 数。

默认研究上下文使用相关记忆、最近两条科研记录和证据定位，不加载完整任务历史或任意文件前缀；详细读取需明确选择。新论文导入默认走平铺布局；双根主题旧行为仅由显式 legacy 兼容入口保留。现有真实科研目录不自动改造。

在隔离样本中复现验证：`.venv/Scripts/python.exe -X utf8 tools/validate_layered_memory.py`。该命令只读来源项目，复制两篇论文、两份实验、两条经验到应用 `.local` 中，检查整个来源目录的前后文件哈希。行为与边界详见 `workflow.get(topic=layered-memory)` 和 [分层记忆验证](docs/layered-memory-validation.md)。

1. 配置项目约定、可验证的推理程序、控制模块和执行插件。
2. 在 setup 选择 manual 或 auto；创建任务，写明目标、允许路径/程序、实验/推理预算、单次/任务总时限与停止条件。
3. 在面板或聊天中明确批准具体授权方案。
4. coding agent 领取任务并调用公开接口；auto 任务也可启动参考控制模块。
5. 查看实验日志、证据和人工决策请求。暂停调度保留已启动实验；恢复先核实实际执行状态。

同一工作区只推进一个任务。任务控制权、授权和实验状态分别管理；配置默认值改变不影响已确认的任务快照。每次实验提交使用稳定幂等键，重复提交不会再启动或扣预算。控制模块不能批准自身请求。主框架采纳仍需独立的用户决策。

manual 完成用户选定的交付物后封存，失败/关键阻塞也须明确结束，下一轮由用户选择。task.stop 持久化终止意图、撤销控制权并取消未结束运行；未知执行保持 stopping，核实后才报告已终止。auto 按“证据→竞争假设→有信息价值的计划→执行→可信度分析→继续/转向/停止”循环；计划和分析保存在 Markdown，核心检查实验先有计划、计划先分析再进入下一轮。推理预算耗尽保留记录并封存 blocked，不自动加预算。

协议及全部操作见 [contracts.md](docs/contracts.md)，领域词汇见 [CONTEXT.md](CONTEXT.md)，已确认架构选择见 [docs/adr](docs/adr)。

## 推理适配器

- `command`：任意语言的独立程序，以 stdin JSON 接收上下文、stdout JSON 返回下一步提案。
- `codex`：本机非交互 Codex CLI，使用结构化输出及只读模式进行推理。
- `claude`：Claude Code 的非交互结构化输出适配器。

配置保存 argv 和参数，不复制 provider 凭据。本机默认 npm `codex` shim 当前损坏，应通过 setup 验证并选择实际可用的原生 CLI。代码不写死桌面版本哈希。provider 的登录、工具与模型可用性需要实际环境验证；本次未调用真实模型。

Codex 适配依据本地 CLI help 及 [官方非交互执行说明](https://learn.chatgpt.com/docs/non-interactive-mode)。可替换模块必须遵循协议，而不是依赖某个 CLI 的内部状态。

本地执行插件运行用户授权的主机进程，**不提供操作系统沙箱**。核心校验公开请求的路径、程序和预算；直接运行的可信插件或 agent 不会因此被系统层面隔离。更强隔离、SSH、路径映射等由独立执行插件扩展。

## 测试与迁移

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

测试包含迁移后的既有科研行为、公共 JSON 协议、原子接管、预算、幂等提交、UTF-8、真实短进程恢复、HTTP 边界和参考控制模块。默认不发送模型请求。运行与视觉验证记录见 [verification.md](docs/verification.md)。

原用户目录 skill 的工作区代码和模板迁入独立核心。全局旧 research/router、auto、manual 入口已退出发现目录，其 Git 历史和工作文件保存在 `archives/global-research-skills-20261029-113802.zip`。历史代码 SHA256 见 [migration-provenance.json](docs/migration-provenance.json)；初次迁移前快照仍在 `.local/pre-migration-skill.zip`。
