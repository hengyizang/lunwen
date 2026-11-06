# 审查意见修复与迁移

本轮修改将审查中有依据的缺口接入现有记录与模型循环。它不记录新的真实研究结果，
不宣称已完成自主科研、模型训练、论文或外部同行评审。

## 适用政策

- 正式博士组合为六篇，同一博士问题下每篇有独立价值；至少三篇当前 JCR Q1，
  其余最低 Q2，且 IF >1。失败、阴性结果或替换提案不自动减少篇数或降低期刊目标。
- 人工只决定 G1 博士选题和 G2 每篇选题。其他阶段保留真实、可追溯的自动检查。
- 费用计算和既有项目累计总额度继续适用；所有尝试均计入，不新增单篇上限、
  逐次付费确认、人工账务门禁或固定追加档位。[现行费用政策](TOTAL-COST-POLICY.md)。
- Claude 保持只读规划与独立审查，OpenAI/Codex 写入持久科研材料；既有初审、
  作者逐项处置、终审和来源记录继续使用，不另设三模型裁决流水线。

## 当前记录

| 记录 | 变化与证据边界 |
| --- | --- |
| `program/novelty-claim-matrix.json` 1.1 | `prior_art_comparisons` 将本候选与各项最近工作逐项比较，绑定真实检索、文献登记及原文锚点；未知、重合和异议不能靠打分消除 |
| 现有独立模型审查 | `novelty_assessment` 保存 `claim_id`、`inspected_work_ids`、`decision`、`rationale`、`remaining_uncertainty`，G1/G2/G5 复核当前矩阵及实际初审、终审 |
| `search_saturation` | `stopping_rule`、`retrieval_dispositions`、`search_rounds` 记录真实新增、筛选和停止原因；检索窗口不冒充完整语料，新 DOI 不直接等于重要近作 |
| `program/quality-G*.json` 1.2 | 用 `assessments` 逐项说明 `satisfied`、`unresolved` 或 `failed`、理由及 `source_anchors`，不再凭 8/8.5 分的自评分通过正式门禁 |
| `topic-shortlist.selection_decision` | `chosen_candidate_id`、`strongest_rival_candidate_id`、`why_selected_over_rival`、`change_of_mind_evidence` 汇总裁决，复用已有候选比较 |
| `selected_direction_cloud_feasibility.feasibility_evidence` | `data_access`、`research_rights`、`compute_cost` 保留可定位来源；`pilot` 区分 `not_run`、`unknown`、`executed`，执行声明必须有回执 |
| 主、副课题及单篇契约 `negative_result_plan` | `informative_if_unsupported`、`precision_limitations`、`stop_rule`、`claim_boundary` 预先说明信息价值和边界，不承诺阴性结果一定可发表 |
| 单篇 `scientific_bindings` 1.0 | 连接原主结局文字、指标、方向、汇总方法、判定规则、最小效应和证伪条件，保持 G2—G3 比较语义一致 |
| `claims/claim-evidence.csv` | `comparison_ids` 与真实比较、运行及全部结果对应，G5 稿件标签须与正式结果一致；阴性、不确定和探索结果仍保留 |
| `dependency_bindings` | 区分共用资产和确实依赖的科学前提，核对 ID、自指及环；根据受影响证据复查，避免一律等待整篇 `submission_ready` 造成顺序死锁 |
| `thesis_synthesis` | `argument_links` 将每篇 claim 连到博士论证；`evidence_alignment` 在 G5 将已产生的结果、收窄和解释与原承诺对账，不预填未来论文结果 |
| `data_protocol.model_selection` | 声明是否调参；实际调参须列选择数据集、有限候选空间、选择指标及同设计运行，不允许用最终测试集选择模型 |
| 原有稿件审计 `warnings` | 对主张相对绑定原文的全称量词、比较词增强给出词面提示；不代替语境审查，也不冒称覆盖所有越界 |

质量 1.2 的 `assessments` 键集合沿用 `scripts/quality_gate.py` 中当前阶段的
`DIMENSIONS`。每项 `source_anchors` 需包含 `path`、`sha256`、`locator`、`excerpt`，
并由来源检查确认；仅把状态改成 `satisfied` 不足以通过。创新性比较使用原文行锚点
`path/sha256/start_line/end_line/quote`，可附 `pdf_page`，不要混淆两种记录格式。

`scientific_bindings.hypotheses` 的每项包含：
`hypothesis_id`、`primary_outcome_statement`、`primary_metric`、`direction`、
`aggregation`、`decision_rule`、`minimum_effect`、`condition_ids`、`rationale`。
`falsification_conditions` 的每项包含：`condition_id`、`hypothesis_id`、
与原契约逐字一致的 `statement`、`metric`、`decision_rule`、`threshold`、`rationale`。
G3 的比较用 `condition_ids` 回绑，主比较不能换成无关次要指标。当前支持的统计规则
仍以实际适配器为准；加一个字符串枚举不能实现新的检验。

## 旧项目迁移

1. 保存原材料、决定、检索、费用、实验和审查历史。初始化新字段只提供空草稿，
   不生成候选、引句、成功运行、审稿意见或人工决定。
2. 在原记录中根据真实材料补齐新字段。质量报告迁移到 1.2，创新性矩阵迁移到
   1.1；旧版记录可作为历史阅读，不能仅改版本号冒充新证据。
3. 重跑来源、契约、质量和创新性检查，使用原有作者与独立审查轮次处理实质问题。
   不自动沿用材料已经变更的审稿收据，不把历史签名绑定到新文件。
4. 冻结 G3 后不得修改原主结局、输入、统计或运行记录；通过既有保留历史的恢复、
   补充实验或范围修订路径处理。已看过结果的后续分析保留其探索性标记。
5. 是否需要 G1/G2 重新选题决定，由当前门禁与科学范围检查确定；博士问题或
   论文映射实质改变时，重新确认受影响选题。技术迁移不伪造人工批准。

Meta 分析和形式化 theory 保持各自证据协议；通用 `empirical` 仍是默认路线。
不要为其他研究类型填造不适用的实证数据、指标或实验。当前有受控代码执行入口，
并不等于完整 GPU 调度、自动训练恢复或自主发现能力已完成验收。

## 工程边界与验收

真实云运行 `41287314302` 的诊断包显示：500 个自动发现候选形成约 1.6 MB
文件，规划请求构造前超过单文件上下文上限。现在只对受控命名空间中的大型
自动发现元数据提供全候选导航索引，保留原始文件哈希、全部候选身份、原行范围、
筛选及未知状态；不把索引当作阅读过正文或完成科学筛选。具体候选仍通过原有
`context-plan.json` 读取完整原记录。正式科学源的大小检查继续生效，模型不能
把超限反证改名为发现回执来隐藏。索引没有提高上下文或费用上限。

写作者家族在入口即核对；正式初始化明确六篇范围。损坏的失败时间戳不会视为
冷却已到期，示例 `trial_only` 期刊不能交付。云端人类操作收据独立保存实际 owner
事件身份与显示名，本地声明不冒充认证；自动 continuation 仍使用既有授权。

回归和仓库检查验证的是实现行为。真实课题仍需实际完成检索、来源阅读、研究
设计、实验、阴性结果解释和稿件审查；软件测试不授予科学有效性或发表保证。
