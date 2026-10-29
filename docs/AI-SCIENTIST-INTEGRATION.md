# The AI Scientist 的受控接入

`research-ai-scientist` 将 V1/V2 中可用的选题、实验分支、失败恢复及图文审查方法接入现有流程。固定源码供核查，适配技能供 Codex 和现有 API 模型按任务读取。上游完整流水线、付费客户端和 GPU 服务未部署；本次接入没有新增模型调用或改变模型分工。

| 来源 | 固定版本 | 本项目用途 |
| --- | --- | --- |
| [AI-Scientist V1](https://github.com/SakanaAI/AI-Scientist/tree/1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb) | `1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb` | 模板起点、想法—实验—写作—审查链及审查意见处理 |
| [AI-Scientist V2](https://github.com/SakanaAI/AI-Scientist-v2/tree/96bd51617cfdbb494a9fc283af00fe090edfae48) | `96bd51617cfdbb494a9fc283af00fe090edfae48` | 并行分支、调试祖先关系、工作阶段和图文一致性审查 |

源码位于 `D:\ad\codex\research-automation\sources\ai-scientist-v1` 与 `sources\ai-scientist`，完整许可和逐文件 SHA-256 保留在来源目录及对应 `receipts/<工具ID>.json`。当前快照没有原生 Codex `SKILL.md`，因此安装的是本项目独立编写的适配入口；它复用现有控制系统，没有把 launcher 作为另一个科研执行器运行。

## 按阶段使用

选题阶段区分“已有可复现模板上的增量”和“开放式探索”，把机制、最近邻工作、可区别的预测及否证条件写入现有假设和原创性记录。通过 `research_frontier` 补文献缺口，使用真实全文与原文定位检验差异。Semantic Scholar 查询和语义相似度可帮助发现邻近工作，但没有相似结果不能证明新颖。六篇论文仍共同回答一个已批准的博士问题。

实验阶段先用 [research_iteration](RESEARCH-ITERATION.md) 整理实际运行回执、日志、阶段、全部失败和不利结果。需要比较分支目的或调试链时，再准备下面的树视图。它关联现有科学记录，不创建第二套实验计划或执行数据库。

写作阶段把实际图像、图注、正文中的对应论述、claim ID 和原始结果一起送入现有 writer/critic 环节。依照 [figure_story](FIGURE-REFERENCE-WORKBENCH.md) 绑定原文位置、图规格和结果来源，核对单位、组别、误差、不确定性、轴、图例、数值和推断范围。机械 QA、图像抽取及模型评价各有边界；无法获取图像或需要科学判断的项保留为待审，不能转为通过。通过现有问题清单、逐条决策和重绘路线修复，不增加固定“五次审稿”或另一个汇总代理。

内部评审继续采用作者与 critic 不同模型家族、初审和终审及逐项 writer 回复。上游同一模型生成多份意见不等于多个独立家族，也不能用内部评分代替人工科学判断、博士标准或期刊录用。

## 准备实验分支视图

在项目中保存 `program/research-search-tree.json`，指向实际生成的不可变 iteration 报告。下面的占位 ID、路径和阶段须替换为真实记录；尚未执行的计划节点省略 `attempt_id`，不能填造回执：

```json
{
  "kind": "research_search_tree",
  "id": "current-experiment-branches",
  "iteration_report": "reports/research-iteration/ACTUAL_ID-ACTUAL_HASH.json",
  "max_items": 10,
  "max_debug_depth": 3,
  "nodes": [
    {
      "node_id": "original",
      "parent_id": null,
      "branch_kind": "root",
      "run_id": "EXISTING_RUN_ID",
      "attempt_id": "EXACT_EXISTING_ATTEMPT_ID",
      "workflow_phase": "investigation"
    }
  ]
}
```

通过原有云端 literature 请求或 `program/cloud-operations.json` 使用非付费操作：

```json
{"action":"research_search_tree","request_file":"program/research-search-tree.json"}
```

`kind`、`id`、`iteration_report`、`nodes` 必填。请求限 64 KB，节点 1–50 个。节点 ID 唯一，未执行的 `run_id` 必须出自当前计划，指定的 `attempt_id` 必须对应 iteration 报告中的该运行和论文。旧计划已按原恢复机制封存时，也可用精确历史尝试及其封印计划作为父节点，连接“旧失败→新计划”；不能填入未执行的历史节点或把旧尝试归到另一篇论文。报告分别显示当前计划成员、历史版本和真实尝试计划，不会自动选择最后一次或最高分尝试。同一真实尝试不能扮演多个节点。多个根表示并列路径；非根须引用同论文内的既有父节点，循环或缺失父节点被拒绝。

- `branch_kind` 是 `root`、`debug` 或 `variation`。`debug` 的父节点必须绑定实际失败或超时、并具有工程失败或执行不完整诊断的回执。低分、无显著性和负结果不构成调试理由。
- 可选 `workflow_phase` 为 `investigation`、`tuning`、`main`、`ablation`，只是声明的工作分类。报告同时保留原协议封印的真实 `analysis_phase`；声明不能重标探索性/验证性实验。
- `max_items` 为 1–20，默认 10；`max_debug_depth` 为 1–10，默认 3。连续调试达到限制时列出待审提示，历史节点不会被删去。这是准备建议的边界，不批准额外执行。
- 祖先关系由请求声明。后续执行成功不能自动证明父节点根因、修复有效或科学改进；需要实际差异、回执和现有独立审查。

返回 `reports/research-search-tree/<id>-<内容哈希>.json`，绑定请求、iteration 报告、当前计划和实现。读取时重新核查 iteration 的日志、回执、协议、输入输出、模块和溯源；输入变化使旧视图失效。未变化时复用原报告，完整失败及不利尝试仍保留在源报告中。报告披露未映射尝试、工作清单截断及“未评估科学有效性”，不按指标挑选赢家或剪除分支。

将返回报告的路径和当前 SHA-256 加入 `research_toolkit` 请求的显式 `input_bindings`，选择工具 ID `ai-scientist`。按 [现有任务包机制](RESEARCH-AUTOMATION-TOOLKIT.md) 将返回的 `RESEARCH_TOOLKIT_PACKET=...` 放入当前 cycle。planner/writer/remediator 看到有界建议，独立 critic 只看到重新核查的实际事实，不获得声明的工作阶段、作者任务描述或下一轮工作清单。只读上下文最多展示 20 个节点，省略数量和完整历史路径一并保留。

真实代码修改、重试、实验和协议变更仍通过现有批准 G3 计划、预算、独立审查、`experiment_runner.py` 及人工决策。中央 CNY500 累计预算、未知费用暂停、模型身份核查、冻结终测和 G0–G5 权限继续生效。本视图不执行实验，不提供 GPU，也不改变模型路由。

## 上游运行与许可边界

当前两个版本的 [LICENSE](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/LICENSE) 为 **The AI Scientist Source Code License, Version 1.0, December 2025**，不能标成 Apache/MIT。分发上游代码须附完整许可；若使用其软件或衍生软件生成科学稿件，3.2.e.i 要求以显著、清楚的方式披露机器生成或 The AI Scientist 的使用，3.3 要求在适用下游条款中保留限制。本项目不移除许可要求的披露，期刊政策核查继续遵循 [PUBLICATION-DISCLOSURE.md](PUBLICATION-DISCLOSURE.md)。本次没有运行上游生成稿件。

原 launcher 会直接执行生成代码并调用模型，部分路线还会自动选择最佳节点、继续写作/审稿；这些行为没有继承本项目的中央计费与审批。V2 的 [launcher 第 347–359 行](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/launch_scientist_bfts.py#L347-L359) 按宽泛进程关键词终止进程，不适合共享运行器；[费用追踪](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/utils/token_tracker.py#L107-L111) 会把未知型号的计价当成零，也不满足本项目的未知费用暂停规则。V1 默认的五份同模型意见不构成独立模型家族的审查。本接入不调用这些 launcher，不采用最佳种子选择、无边界试错或未核查文献直接成文的路径。上游 CUDA/GPU 环境不由 Codex 技能安装自动提供，完整上游运行尚未验收。

文章中的 6.33 分来自 ICLR Workshop 的一次评审实验。[Sakana AI 官方说明](https://sakana.ai/ai-scientist-first-publication/) 与 [Nature 的系统论文](https://www.nature.com/articles/s41586-026-10265-5) 是不同记录；后者由研究团队署名。软件接入、云端测试或内部评审均不能据此证明我们的研究已达到发表标准。
