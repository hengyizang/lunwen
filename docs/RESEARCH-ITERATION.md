# 实验反馈与下一轮工作清单

`research_iteration` 在已有云端 literature 操作中读取真实实验记录，整理工程失败、缺失证据、配置相同的记录和下一步待审事项。不启动上游 RD-Agent、AutoResearchClaw、Pi 或 synthetic-sciences 服务，也不创建另一套实验登记、执行或审批状态。

在项目中保存 `program/research-iteration.json`：

```json
{
  "kind": "research_iteration",
  "id": "current-experiment-feedback",
  "paper_id": "P01",
  "max_items": 10
}
```

通过现有云端请求使用：

```json
{"action": "research_iteration", "request_file": "program/research-iteration.json"}
```

`kind` 和 `id` 必填。可选 `paper_id` 限定工作清单所属论文；`run_ids` 和 `hypothesis_ids` 只能选择既有计划、真实执行回执和 `program/hypothesis-register.json` 中的 ID。`max_items` 为 1–20，默认 10；截断数量单独披露。请求不接受作者预设结论、期望分数或修复指令。实验尚未执行时，已有假设或计划可以生成明确标为待准备的工作项。

返回 `reports/research-iteration/<id>-<内容哈希>.json`。未变化的请求和来源复用原报告及溯源，不改写任何状态；变化后生成新报告，历史报告保留。请求、计划、全部真实尝试、实际日志、输入输出及其缺失状态、假设来源、阶段/预算记录和实现模块均参与哈希绑定。

## 使用已有科学记录

- 当前记录来自 `experiments/registry.jsonl`，每行必须与 `experiments/runs/<attempt_id>/run.json` 完全一致，复用 `primary_recovery.receipt` 核验。
- 历次正式退役协议复用 `primary_recovery.histories` 验证版本控制封印、归档计划、每次回执和保留结果。失败尝试的被覆盖输出使用既有 recovery 映射，旧输入优先读取经封印的归档。没有归档的私有输入仍需从原授权存储定位，缺失或变化保持为未知。
- 读取回执实际 `argv`、`cwd`、`seed`、输入哈希、代码哈希、`executor_isolation`、结束状态、输入完整性、输出与缺失输出、stdout/stderr 位置。报告中的日志只保留最后 2,000 字符并标明截断，完整原日志及哈希保留。
- 分析阶段来自同一封印计划对应的既有 `experiment-evidence-plan.json` 或 `study-protocol.json`，独立复现角色来自既有设计的 `reproduction_plan`。来源必须由该计划的输入哈希，或匹配该计划的原 G3 审批 → `frozen_protocol_sha256` → `preregistration.files` 封印；退役计划使用已归档的原审批和原协议。当前文件未封印、变化或找不到阶段时保持未知，不默认为验证性实验，也不重新标记旧尝试。

## 诊断与配置比较

实际超时、非零退出、缺失输出、输入完整性失败、缺失日志或原始文件产生定位检查和最小修复建议。非零退出本身只说明执行不完整，不自动归因为工程错误；日志异常签名也只是已观察条件，不自动确立根因。相似历史经验需要真实起止时间证明前后关系，只能说明此前出现过相同条件，不能宣称某项修复有效或推断因果关系。

科学结果较差、未达阈值、零结果和负结果均不被归类为代码错误。成功退出也不证明科学有效。该操作不挑选最高分种子，不改写假设或最终协议，不丢弃任何失败、不利结果或独立复现。

跨 run ID 和输出文件名的比较使用已记录代码与输入内容哈希、封印环境、实际参数、种子和分析阶段。只将 argv 中已声明的输入位置替换为相应内容哈希、输出目的地替换为占位符；参数键及其他值保留。实例 ID、输出文件名和运行目录指纹本身不能证明重复。仅有相同 Python 版本或平台不构成封印环境；缺失任一必要字段时不计算完整配置指纹。argv、cwd、种子或输入与所称封印计划不一致时，也不形成完整指纹。

完整指纹相等只标为 `equivalent_declared_configuration_review_only`，供检查已有证据是否需要重复准备。它不证明科学目的重复，也不证明未记录的运行时因素完全相同。已声明的原始/独立复现照常保留；无自动删除、跳过、重跑或执行动作。

## 模型角色与执行边界

将返回的不可变报告作为当前任务 `research_toolkit` 的显式 `input_bindings`，由既有 planner/writer/critic/remediator 调用读取。`model_context` 仅重新计算并验证请求、全部来源、实现哈希和确定性写入溯源；不会在模型读取期间刷新、生成报告或触发模型调用。

独立 critic 只获得执行回执、输入输出状态、已观察条件、阶段、独立复现角色和未知字段等简明事实。修复建议、下一轮清单和作者偏好均不进入 critic。planner/writer/remediator 可以查看有界检查建议与同条件历史记录。事实摘要最多列出 20 次选定尝试并披露省略数量，完整历史留在报告中；摘要不是原始证据替代品。

下一轮事项必须指向已登记假设、现有计划或真实失败回执，始终标为 `proposal_only_not_executed`。计划中尚无回执的运行被列为证据缺口；是否执行仍由原有 G3 计划、预算、独立审查和人类审批决定。该操作不扩大预算，不改变模型路由，不批准重试，不跨越 G0–G5。

云端测试覆盖不同 ID/输出名的配置比较、独立复现保留、未知配置、不利结果、真实错误、退役历史、日志/模块/回执变化、不可变复用、只读角色上下文与原审批状态保持。测试夹具不构成实际研究成果。
