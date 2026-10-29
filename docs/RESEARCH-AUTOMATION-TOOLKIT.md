# 十个科研工具的 Codex 接入

这次接入包含十个可发现、可按任务调用的 **Codex 适配技能**、固定上游版本的完整源码，以及将选定技能送入现有模型环节的云端任务包。适配技能有实际的研究操作步骤，并非十个软件的独立服务部署。上游桌面程序、服务器、模型权重、GPU 服务和付费接口均未启动。

## 按实际任务选用

| 工具 / 技能名 | 已接入的方法 | 独立软件仍需要什么 |
| --- | --- | --- |
| deer-flow / `research-deer-flow` | 按证据缺口检索、论文方法审查、固定版本研究代码核验 | 后端、前端、沙箱及模型配置 |
| gpt-researcher / `research-gpt-researcher` | 有界查询队列、复用来源、小语料直接阅读、附来源报告 | Python 服务、搜索/模型/嵌入配置；原生技能只是 MCP 配置入口 |
| RD-Agent / `research-rd-agent` | 假设—实验—反馈链、失败经验及适用条件 | Python、Docker、研发场景和模型服务 |
| AutoResearchClaw / `research-autoresearchclaw` | 分阶段研究计划、真实执行证据、失败诊断与恢复建议 | Python 应用与模型服务；本版本 MCP 部分入口为占位实现 |
| MiroThinker / `research-mirothinker` | 长任务续接、工具观察和科学证据分开保留 | 模型服务与工具框架；未下载模型权重 |
| pi-autoresearch / `research-pi-autoresearch` | 有限实验会话、全部尝试记录、正确性与独立留出检查 | Pi 扩展及专有工具；不能直接当成 Codex 工具调用 |
| PaperBanana / `research-paperbanana` | 参考驱动的图示规划、语义与视觉分项检查、可编辑输出 | 完整 Python 项目及图像/模型服务；单独复制 `skill/` 不能运行 |
| aipoch/open-science / `research-aipoch-open-science` | 论文图组论证、按面板修正、复现范围和阻断原因 | Electron/CLI 及其 notebook、artifactVersion、delegate 接口 |
| EvoScientist / `research-evoscientist` | 可追溯的经验复用、证据关系、待人工审查的流程建议 | 独立 Python 代理及模型配置 |
| synthetic-sciences/openscience / `research-synthetic-openscience` | 证据绑定的想法队列、配置去重、未完成/不可用状态 | Bun/TypeScript 工作台、study/experiments/compute_job 接口 |

十项的上游仓库、完整提交号、许可、原生技能目录、适配文件和哈希见 `integrations/research-automation-tools.json`；对应来源也登记在 `integrations/upstreams.lock.json`。不按文章中的星数判断研究质量。原始技能和各组件许可保留在完整上游源码中；未将全部上游技能混装为自动触发的全局规则。

## 在 Codex 中调用

Windows 的技能主体位于 `D:\ad\codex\research-automation\skills`，发现入口位于 `$CODEX_HOME/skills`（未设置时为 `%USERPROFILE%\.codex\skills`），入口通过目录联接指向 D 盘。固定版本源码位于 `D:\ad\codex\research-automation\sources/<工具ID>`，每个文件的 SHA-256 和下载地址记录在 `receipts/<工具ID>.json`。这些是源码文件，未执行上游安装脚本或科研程序。

例如，在下一轮任务中输入：

> 使用 $research-deer-flow，检查当前课题哪些证据缺口还需要检索，复用已读文献，只准备必要的后续检索。

> 使用 $research-rd-agent 和 $research-pi-autoresearch，为已批准的实验计划整理候选改动和失败经验；按现有云端执行权限推进。

> 使用 $research-paperbanana 和 $research-aipoch-open-science，围绕最强证据规划论文主图，再用项目现有工具生成可编辑图。

技能应在下一轮可用；若当前应用没有刷新技能目录，重新打开会话。它们不改变原有模型分工。重装入口可在 Windows 运行 `scripts/install-research-toolkit.ps1`：该脚本只复制已核对哈希的适配技能并建立发现入口，已有不同内容会保留并报错，不启动科研软件。

## 让现有 API 模型按需使用

不把十项说明无条件加入每次调用。为当前任务选择实际需要的技能，创建 `program/research-tool-task.json`：

```json
{
  "id": "current-literature-gap",
  "stage": "topic-intelligence",
  "tool_ids": ["deer-flow", "gpt-researcher"],
  "task": "Inspect unresolved evidence dimensions in the current approved doctoral scope.",
  "input_bindings": [
    {"path": "program/actual-current-plan.json", "sha256": "REPLACE_WITH_CURRENT_FILE_SHA256"}
  ]
}
```

示例路径和哈希必须换成项目中实际存在、已核对的输入，阶段必须与当前项目一致；有确定论文时可附 `paper_id`。不能填写虚构材料以通过准备步骤。

绑定不可变的科学来源或预注册协议，避免绑定本轮写作者马上要改写的初稿。文件改动会使原任务包失效；需要新哈希和新任务包。大文件通过既有 `program/context-plan.json` 提供受控原文片段，不能把文件哈希当成已读证明。

把以下操作放入现有云端 literature 请求（`allow_paid: false`）：

```json
{"action": "research_toolkit", "request_file": "program/research-tool-task.json"}
```

它生成 `reports/research-toolkit/<任务ID>-<内容哈希>.json`，记录请求、选定完整技能、上游提交、输入、当前阶段和约束的绑定，以及已有操作建议。重复请求直接复用；输入或控制记录变化后必须重新准备，旧记录保留。准备步骤不执行上游代理、不调用模型、不创建科学结果。

在现有模型 cycle 的 `context` 中单独一行填写返回路径：

```text
RESEARCH_TOOLKIT_PACKET=reports/research-toolkit/<任务ID>-<内容哈希>.json
```

API 与 CLI 的规划、写作、审查和修复环节读取同一套经过校验的完整技能。科学原文仍由原有证据上下文机制读取；任务包不是原文替代品。独立审查不会读入作者任务描述中的预设结论，历史任务包和调用请求也不作为科学证据进入审查。

## 执行和验证边界

原生自动能力见 [覆盖清单](RESEARCH-AUTOMATION-COVERAGE.md)。`research_iteration`
把实际执行回执变成失败诊断、跨编号配置比较及有界下一轮工作清单；
`research_frontier` 把已有阅读缺口、真实检索回执与原有问题笔记接成后续动作。
两者复用当前云端 literature 入口，准备过程不增加付费调用。
将返回报告作为 `research_toolkit` 的显式输入绑定，模型角色才会读取经重新核验的摘要；
独立审查仅看到实际观察，历史任务和建议不会混入其原文证据。

绘图规格可设置 `"reuse_panels": true`，启用源数据、规格、样式及渲染依赖绑定的
矢量面板复用。未变面板跳过绘制，变化面板重绘，完整合成图仍需全部最终检查。
MiroThinker 的续接方法可在 intake、选题、架构、实验设计、实验执行及写作阶段使用。

- 检索、PDF、脚本、测试、实验和渲染继续在既有 GitHub 云端执行。实验必须通过批准的 G3 计划和 `experiment_runner.py`；各工具不能自批 G0–G5。
- 中央预算、模型身份检查、原有独立审查和角色权限继续生效。本次安装不授权新的付费调用，也不启用上游默认搜索、嵌入、图像或模型账户。
- 不采用上游的自动审批、模拟实验结果、只选最高分记录、破坏性清理和无限迭代。全部失败及不利证据保留；开发集改进不能代替冻结的最终检验。
- 云端验收会用固定版本的 OpenAI 官方 Skill Installer 实际安装十个适配入口，使用官方校验器检查，并核对安装后字节哈希。测试覆盖任务包复用、证据变化、越界路径、阶段、权限和独立审查。验收不代表十套独立服务已经部署，也不构成论文科学完成的证明。

重复能力沿用现有检索、阅读覆盖、实验记录、图示和模型循环，没有再叠加一套科研控制系统。可移植方法已进入当前任务执行入口；独立服务若以后确有收益，再按具体任务验证其运行环境及费用。
