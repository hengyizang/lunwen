# 创新候选的比较与筛选

在现有 `program/hypothesis-register.json` 内填写 `innovation_screening`，
由 `scripts/research_candidates.py hypotheses` 生成原有 `program/hypothesis-audit.json`。
G1 读取并重算这一审计；API 和 CLI 的既有规划、写作、初审、终审使用相同阶段指导。
没有新增模型角色、自动选题器或付费研究循环，预算与 G0–G5 权限沿用当前项目。

## 吸收的方法与记录

| 方法 | 实际记录与检查 |
| --- | --- |
| 问题拆解 | `scope` 写一个焦点问题、共同博士问题、内外范围和真实/假定/可协商/未知约束；焦点问题须与 `argument_plan` 一致 |
| 防止锚定 | `generation` 记录方法、理由、真实贡献来源、已有/缺失视角、提前见到的例子和独立性偏差 |
| 保留原始想法 | 初始与查证后的轮次各绑定真实 JSON 文件及 SHA-256；保留原始文字、ID、证据输入和检索限制，不能只留下最终标题 |
| 聚类、合并、拆分 | `clustering_events` 声明关系、原因及前后 ID；原候选继续保留，不能凭措辞相似宣称科学等价 |
| 显式假设 | `assumptions` 列出类别、状态、依赖它的候选、定位证据、检验和失效后果；与候选的引用须双向一致 |
| 支持、反证、缺口 | 每个候选分别记录原文支持、反证、证据状态、缺口问题、解决办法与搜索限制；没有证据不能填“已定位” |
| 实质差异 | 每对候选记录机制差异、预测差异和区分检验；相同假设/预测/差异三元组的编号复制被拒绝 |
| 共同失效风险 | 每对候选显式列出全部共同假设及其风险；允许共同博士背景，不要求三个完全无关的方向 |
| 反方审查与回应 | `adversarial_checks` 保存具体质疑、回应、下一检验和剩余不确定性；这些自查提案随后接受既有独立 critic 审查 |
| 已见数据 | `prior_exposure` 记录看过或无法确定是否看过的数据/结果、原文件哈希及未来新证据；同一已见观察上的后续分析保持探索性 |
| 保留与淘汰 | 每个候选均有 retain/revise/defer/reject、理由、下一步、重访条件与责任人；阻断项不能靠总分抵消 |
| 评分不确定性 | 可用文字判断或可选矩阵；保留原始/修改评分、弃权、未知区间、分歧和方法限制，数值只辅助安排下一证据检查 |

这些检查确认记录完整、引用一致、来源当前和计算可重放。它们不判断机制是否真的
独立，也不授予新颖性、科学有效性、博士资格或选题批准；这些继续由原有全文原创性
核查、独立模型审查和具名人工 G1 决定承担。六篇论文始终服务同一博士问题。

## 使用步骤

1. 从实际观察、材料和项目约束写出至少三个具体假设，保留“先测量/先查资料/暂不干预”这一类有信息价值的候选。
2. 保存初始想法，再查最近邻、相邻领域和反证；为查证后的修订保留独立轮次记录。
3. 填写原假设字段和新增筛选记录。具体类型见 `schemas/research-hypotheses.schema.json`；
   新增字段包含 `scope`、`generation`、`assumptions`、`candidates`、`comparisons`、`evaluation`。
4. 在现有云端运行假设审计，处理真实来源、字段或计算问题。旧版登记需要补齐记录后重新审计；
   不填写虚构人物、审查意见、独立性或结果来通过检查。
5. 由现有不同模型家族的 critic 检查科学差异、共同风险、文献增量和候选处置；writer 逐项回应。
   实验需使用原有 G3 计划、预算与 `experiment_runner.py`，候选被保留不构成执行许可。

轮次引用的 JSON 必须包含相同的 `round_id`、`stage`、`candidate_ids`，以及
`ideas: [{"hypothesis_id": "实际ID", "statement": "当时的原始想法", "prediction": "当时预测", "precise_difference": "当时差异"}]`、
`evidence_inputs: [{"path": "实际相对路径", "sha256": "当前哈希"}]` 和 `evidence_limits`。
初始阶段为 `independent`，后续至少有一次 `post_evidence`；无法独立生成时如实声明
`independence: unknown/not_achieved` 及偏差，不把这些标签当成独立性证明。
AI-only 流程可以继续工作，不虚构人类先行的讨论或专家共识。
每个当前候选必须有对应轮次，最后保留的想法、预测和差异须与当前登记一致；
修订需保存新的绑定记录，不能只改最终标题而丢失演化过程。

## 按卡点选择方法

- 假设被固定：反转关键假设、改变尺度/边界，比较改变前后的可观察结果。
- 方法组合单一：用形态矩阵或 SCAMPER，先检查组合的机制与可行条件。
- 想跨领域迁移：记录源系统与目标系统的结构映射、不匹配、目标基线、单位、时间尺度和区分结果。
- 方向看似都合理：做失败预演、共同假设检查与最小区分性试验；明确无结论和控制失败条件，
  控制失败不自动否定机制。
- 多人讨论或分歧：按实际需要采用独立写入、轮流澄清或异步汇总；仅在真有相应参与者与方法设计时使用
  NGT、Delphi 或专家数量判断，重复模型样本不构成专家小组。

完整方法参考位于固定版 `third_party/kdense/skills/scientific-brainstorming/references/`。
按当前问题读取相关材料，不把所有方法和完整参考文献塞入每次模型调用。

## 可选的确定性评分矩阵

默认可使用 `evaluation.mode: narrative`。所有候选/标准仍须有理由或明确弃权记录，
`score/low/high` 可以为 null；不必为了形成数字而添加模型调用。

需要量化排序时使用 `weighted_matrix`，预先定义标准、方向、尺度锚点、正权重和证据要求。
每项评分保留 `rating_id`、候选、标准、评分者、理由与来源；修改通过 `supersedes` 指向原评分，
原记录不删除。矩阵明确选用一位评分者的当前评分，不暗中平均不同意见。

`matrix` 绑定 `criteria_file`、`scores_file`、`result_file`，记录 `rater_id`、`weight_delta`
和 `deferred_candidate_ids`。云端直接重放已固定哈希的上游标准库 CLI，对照当前评分、输入和结果。
缺失中心评分必须明确暂缓该候选，不能补零。未知上下界保持未知；合理范围不是置信区间。
一次只改变一个权重的敏感性分析说明本地排名稳定性，不能代表全部偏好和模型不确定性。
阻断项、异议和被暂缓候选仍保留在登记中，结果的 `decision` 必须为 null。

## 版本、引用和边界

`scientific-brainstorming` 完整子目录已固定到
[`a92663a0214b3b9fa1ba6b958284ffd919c00a0c`](https://github.com/K-Dense-AI/scientific-agent-skills/tree/a92663a0214b3b9fa1ba6b958284ffd919c00a0c/skills/scientific-brainstorming)
的 1.4，保留 MIT 许可、全部参考和辅助脚本。旧 `hypothesis-generation` 保持原固定版本。
新增登记原生检查并不运行上游模型服务；矩阵辅助程序不调用网络或模型。
云端测试使用明确标记的合成记录，只验证软件行为。

方法来源已加入本说明的软件引用：Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026).
*Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*.
[arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065)。作者与版本于 2026-10-29 核对原站。
