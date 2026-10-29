# 十个工具的原生能力覆盖

这份清单对应 2026-10-29 的接入范围。每个工具保留固定来源、完整适配技能和按需任务包；
有用机制复用已有控制系统或补充为原生功能。独立上游应用、模型服务、自动审批与付费账户未部署。

| 工具 | 复用已有能力 | 本轮原生增量 |
| --- | --- | --- |
| deer-flow | 问题维度阅读覆盖、原文定位、方法和代码审查指导 | 缺口与假设、来源版本及下一条检索/获取/阅读动作连接 |
| gpt-researcher | 来源去重、请求上限、阅读/索引/查询缓存 | 按真实查询回执统计新增规范化文献和证据维度，给出有界后续建议 |
| RD-Agent | 假设登记、实验设计、实际比较与反馈 | 当前及保留历史回执形成观察—条件—核查—下一轮建议 |
| AutoResearchClaw | 失败保留、授权恢复和原审批 | 真实日志的工程异常、超时、输入完整性与缺失条件诊断 |
| MiroThinker | 完整证据交接、预算/审批状态、操作历史压缩 | 方法选择扩展至全部研究阶段，包含实验执行和写作 |
| pi-autoresearch | 有界执行、全部尝试、冻结评测和留出控制 | 跨运行编号和输出名的有效配置比较，保留独立复现和未知项 |
| PaperBanana | 主图论点、语义/视觉分项审查、可编辑输出 | 实际 SVG/PDF 矢量面板缓存与增量合成，保持完整最终 QA |
| AIPOCH open-science | 整组图的论证关系、来源链、严格复现实验验证 | 面板复用与渲染范围声明；下游绘图复用不冒充端到端科学复现 |
| EvoScientist | 带正反证据的问题笔记、规则冻结评测和人工采用 | 为已有证据/决策声明 complements、contradicts、supersedes 关系，保留旧记录 |
| synthetic-sciences/openscience | 基准先行、全部实际状态与预算 | 有效配置去重建议、明确不可用字段、有界下一轮工作清单 |

机器可检查的逐工具实现和验证文件位于 `integrations/research-automation-coverage.json`。
清单覆盖只证明接入范围，不能证明模型判断正确、科学结论成立或期刊录用。

## 使用现有云端入口

准备 [实验反馈请求](RESEARCH-ITERATION.md) 或 [文献后续请求](RESEARCH-FRONTIER.md)，
将 `research_iteration` / `research_frontier` 操作加入现有 `program/cloud-operations.json`，
或通过现有非付费 cloud literature 控制调用。请求只能指向项目中实际已有的输入，
不能靠示例、虚构 ID 或自报执行结果通过核查。

报告保存在 `reports/research-iteration/` 和 `reports/research-frontier/` 的不可变路径下。
输入、模块或控制记录变化后原报告失效，历史保留。将需要使用的报告路径和当前哈希
加入 `research_toolkit` 的 `input_bindings`，再按原有任务包方式供现有模型环节使用。
各模型读取前重新核查来源；独立 critic 的投影排除下一轮建议、关系解释和作者预设结论。
没有另加总结代理、检索代理或重复审稿轮次。

多面板图使用 [矢量面板复用](FIGURE-PANEL-REUSE.md)。缓存属于确定性执行器，
模型不能自行写入或修改。数据、规格、样式或受跟踪渲染依赖变化会使对应缓存失效；
缓存命中不跳过最终标签、数学、颜色、版面、尺寸、溯源和 G5 检查。

## 研究约束继续生效

诊断与工作清单只提出核查和待审行动。真实实验仍走已批准的 G3 计划、预算和
`experiment_runner.py`；正式重试、协议修改、论文主线改变和规则采用仍用原有人工审查。
效果不佳、无显著性和负结果不归类为运行故障。同配置比较不自动删除必要复现。
低检索收益不自动证明文献饱和、研究缺口或创新性。

科学复现沿用 `research_quality.validate_baseline_reproduction`、
`validate_clean_room_reproduction` 和 `create_reproduction_confirmation`，核查实际 G3、
隔离环境、执行回执、预设容差和人工确认。图形的下游面板重组不能扩大该确认范围。
所有六篇论文继续服务同一个博士问题，模型分工、独立审查和中央付费控制不变。
