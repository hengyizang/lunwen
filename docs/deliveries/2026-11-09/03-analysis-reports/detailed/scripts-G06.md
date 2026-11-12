# Doctoral Research OS v2.3.0 — scripts 精读报告 G06

## 0. 报告元信息

- **精读范围**：`D:/ad/lunwen/scripts/` 下按 Python `sorted()` 字母序，从 `paper_execution.py`（索引 125）到 `research_improvementctl.py`（索引 150），含两端，共 **26 个 .py / 8710 行**，与任务描述完全一致。
- **筛选方法**：`sorted(glob('scripts/*.py'))` → `names.index(起/止)` → 切片；行数按文件逐行统计复核。
- **阅读方法**：全部用 Read 工具逐文件完整打开；7 个 >500 行文件（`primary_recovery` 712、`publication_figures` 745、`relay_guard` 602、`research_case` 673、`research_design` 745、`research_extensions` 575、`research_frontier` 511）均按 offset/limit 分两段读完；未用 grep/关键词摘要代替通读。
- **可读参考**：`AGENTS.md`（29 条运营规则）、`README.md`（架构/阶段表/能力宣称）已读，不计入精读。
- **纪律**：仅只读 `D:/ad/lunwen`，未修改仓库任何文件；唯一写入为本报告。
- **规则锚点**：证据链（规则 1/2/9）、G1/G2 人工决定（规则 5）、角色隔离 Claude 只读规划/审计、OpenAI 写持久物（规则 10/14/18/22）、来源哈希+失败留痕+累计预算（规则 23/28）、第三方网关不授信+模型身份核验（规则 16/17）、绝不自动投稿（规则 11/15）、英文正文（规则 20/25）。

---

## 1. 整体归纳

### 1.1 本组在控制平面中的定位

本组是 **G0–G5 全流程的「确定性校验 + 证据绑定 + 来源/预算守卫 + 本地产物渲染 + 阶段编排」层**，而非模型生成层。26 个文件几乎不产生「科学结论」，而是把上层（范围外的 `api_orchestrator` / `model_runtime` / `research_notebook` / `experiment_runner` / `review_panel` 等）产出的记录，逐字段、逐哈希、逐来源地校验、封存、投影和留痕。三个鲜明的横切主题：

1. **来源/哈希绑定（证据链）**：`research_artifacts.sha/path_in/bound_source/strict_json/json_field_spans/seal_manifest` 是全组基础设施；`research_candidates.anchor_errors`、`research_extensions._sources`（quote 必须「恰好出现一次」）、`research_frontier._binding/_bound`、`publication_figures`/`research_diagrams` 的数据/spec 读前后哈希、`primary_recovery` 的回执/计划/预算/冻结输入哈希，构成严密的「任何输入变化即使旧报告失效」机制。
2. **角色隔离与来源溯源（output_provenance）**：本地确定性产物一律以 `family="other"` + `provider="deterministic-control-plane"/"deterministic-local-renderer"` 登记；`research_frontier._origin` 直接拒绝 `family=="anthropic"`；`research_case.export` 用 `require_final_origins` 校验发布材料来源；`publication_disclosure`/`primary_recovery` 的自动决策要求 `family=="openai"` 的非 Claude 写入者提案。呼应规则 18/22。
3. **失败留痕 / 不夸大 / 不自动推进**：几乎每个校验器都硬编码 `scientific_validation: False`、`scientific_completion_verified: False`、`gate_approved: False`、`human_review_required: True`、`semantic_support_verified: False`；分数（`quality_gate.MIN_SCORE/MIN_OVERALL`）、Q1/Q2 分区（`research_design._planning_quartile`）、AI 政策（`publication_disclosure`）一律降格为「观察/警告」而非阻断闸门。

### 1.2 在 G0–G5 的位置

| 阶段 | 本组承担 |
|---|---|
| **G0 行政 intake** | `research_cycle.review_cycle` 的 `intake` 分支（planner→writer，无 critic）；`research_identity.prompt_contract` 给 API writer 的输入契约 |
| **G1 博士选题** | `quality_gate`(G1 维度+人工确认)、`research_candidates.audit_register`(≥3 假设/竞争解释/证伪)、`research_design` 的 `validate_theme_independence`(A/B 主题独立)、`validate_selected_direction_cloud_feasibility`(G1 阻断至有 cloud-only 路径)、`validate_originality_audit`、`validate_search_log`、`validate_paper_map`、`requirements_trace` |
| **G2 逐篇选题** | `quality_gate`(G2)、`research_design.validate_paper_map/validate_paper_contract/validate_scientific_bindings/validate_portfolio_evidence(G2)`、`research_identity.validate`(G2 仅评估提案)、`research_candidates.audit_card`、`paper_execution.enable`(G2 后拆分独立论文协议)、`public_review_anchors`(校准语料准备) |
| **G3 设计/封存/执行** | `paper_execution`(enable/prepare_datasets/plan_errors/refreshable_preregistration/dataset_snapshot)、`research_design.validate_experiment_design`、`primary_recovery.automatic_retry`、`publication_figures`/`research_diagrams`(本地渲染结果图/概念图)、`research_case.build_packet`(渐进式 case)、`research_cycle.review_cycle`(experiment-execution)、`research_identity.validate`(G3)、`research_extensions`(方法采用/可比性) |
| **G4 结果/失败留痕** | `primary_recovery.diagnosis_context`(免费失败诊断包)/`automatic_retirement`(撤销失败协议)/`gate_errors`、`quality_gate`(G4)、`research_case.export(reproduction)`、`relay_billing`/`relay_guard`(扣费对账，横切)、`research_extensions.gate_errors` |
| **G5 投稿准备** | `pre_submission_review`、`publication_disclosure`、`reporting_checklist`、`ref_verify_adapter`、`research_identity.validate`(G5 `_venues`/`reporting_statement`)、`research_case.export`(preprint/rebuttal/retarget/reproduction)、`research_design.validate_portfolio_evidence(G5)`、`research_cycle.submission_cycle`(三互盲 panel)、`publication_figures`、多个 `validate_saved_report` 的 stale 检测 |
| **横切全阶段** | `research_artifacts`(基础设施)、`paper_execution`(逐篇隔离)、`production_readiness`/`relay_billing`/`relay_guard`(生产配置/中转扣费/共享凭据守卫)、`requirements_trace`(追踪表)、`research_frontier`(文献前沿不可变准备)、`research_improvementctl`(云端 builder 统一入口)、`public_review_anchors`(校准锚点)、`research_cycle`(编排) |

### 1.3 组内调用关系（有向，箭头 = 被依赖）

```
research_artifacts.py  ←── 几乎全部 26 文件（sha/path_in/read/write/record/strict_json/
                            bound_source/schema_errors/paper_audit_cli/report_errors/...）

paper_execution.py     ←── primary_recovery(artifact_path/scope/papers/enabled/selected)
                          research_case(artifact_path/paper_scoped)
                          research_extensions(enabled/scope/selected)
                          research_identity(paper_scoped/artifact_path/approval/enabled)
                          research_cycle(enabled)
                          relay_guard（经 primary_recovery.path_in/read）

publication_figures.py ←── paper_qa, paper_reader, paper_to_ppt（PROJECTS_ROOT/safe_file/
                            sha256_file/FigureSpecError）
                          research_diagrams（_english_text/_imports/inspect_layout/safe_file）

ref_verify_adapter.py  ←── publication_disclosure, reporting_checklist, research_identity
                          （canonical_manuscript）
reporting_checklist.py ←── pre_submission_review（canonical_manuscript）
research_candidates.py ←── quality_gate, pre_submission_review, research_case（anchor_errors/text_fields）

primary_recovery.py    ←── relay_guard（path_in/read）、research_cycle（automatic_retirement）、
                          research_case（selected_attempt/receipt）
relay_billing.py       ←── production_readiness（read_meter）、relay_guard（settle/_fingerprint/_rows）
relay_guard.py         ←── production_readiness（inspect）

research_extensions.py ←── research_improvementctl（"research-extensions" action → refresh）

research_cycle ──after_reviews──▶ primary_recovery.automatic_retirement
research_case  ──export───────▶ primary_recovery.selected_attempt/receipt + 外部
public_review_anchors ──▶ literature_benchmark/literature_evidence/network_safety（范围外）
research_frontier ─────▶ literature_intelligence/reading/reasoning/workbench, research_notebook（范围外）
research_improvementctl ─▶ research_operations.BUILDERS + 10+ 范围外 builder 模块
```

**核心枢纽**：`research_artifacts.py`（确定性原语）、`paper_execution.py`（逐篇作用域）、`publication_figures.py`（路径安全+渲染原语被 4 文件复用）、`primary_recovery.py`（执行回执/失败恢复被 3 文件复用）。

### 1.4 对外能力总览（CLI / 库）

- **带 CLI 的入口**：`paper_qa`(answer)、`paper_reader`(build)、`paper_to_ppt`(build)、`pre_submission_review`(audit)、`production_readiness`(report)、`public_review_anchors`(collect/calibration)、`publication_figures`(render)、`ref_verify_adapter`(run)、`reporting_checklist`(paper_audit_cli)、`requirements_trace`(validate)、`research_candidates`(hypotheses/paper-card)、`research_case`(build_packet/export)、`research_diagrams`(render)、`research_improvementctl`(28 action 分发)。
- **纯库模块（无 main）**：`paper_execution`、`primary_recovery`、`publication_disclosure`、`quality_gate`、`relay_billing`、`relay_guard`、`research_artifacts`、`research_cycle`、`research_design`、`research_extensions`、`research_frontier`、`research_identity`——这些是被状态机/编排器/其它 builder 内部调用的确定性组件。

---

## 2. 逐文件精读

### 2.1 `paper_execution.py`（299 行）
- **职责**：G3–G5 的**逐篇执行作用域隔离**。`independent` 模式下把旧批量协议路径重写为 `experiments/papers/{paper}/` 等，保证「一篇论文的草稿不能改动另一篇的协议与回执」，同时保留单一博士范围/状态机/账本/算力上限。
- **对外能力**：`state/enabled/selected`、`scope`(contextmanager)、`paper_scoped`(装饰器)、`artifact_path`、`primary_registry_paths`、`papers`、`relevant`、`plan_errors`、`approval`、`dataset_snapshot`、`refreshable_preregistration`、`prepare_datasets`、`enable`、`prompt_contract`；常量 `ALIASES`（8 条旧→新路径映射）。
- **输入/输出**：读 `state/run.json`（`paper_execution_mode`、`active_paper`、`paper_count`、`approved_gates`、`approvals`）、`papers/Pxx/paper-contract.json`、`data/datasets.jsonl`；写 `experiments/papers/Pxx/{plan,budget,datasets}.jsonl`、`claims/papers/Pxx/claim-evidence.csv`、`state/`（经 `research_artifacts.record`）。
- **关键机制**：`ContextVar` + `scope` 绑定当前 paper；`selected` 强校验 `P[0-9]{2}` 且属于 `paper_count`；`relevant` 是复杂的路径归属过滤（按 `papers/`、`experiments/papers/`、`claims/papers/`、`experiments/supplemental/`、`experiments/history/exploration-Pxx-`、`data/quality|manifests|contracts`、`results/`、`experiments/runs/` 逐段判定）；`plan_errors` 强制 run_id 前缀、输出落在 `results/Pxx/` 或原生 cleaning 范围；`refreshable_preregistration` 仅当 G3/`experiment-design`/`awaiting_work`/未租约/未批准/registry 空/无匹配已执行回执/预注册为控制器冻结且来源为 `scripts/automated_quality.py` 时才允许作者改预注册；`prepare_datasets` 冻结选中 manifest 行，冻结后变更即抛错；`enable` 仅在 G2 approved 且无 G3–G5 批准/无已执行/冻结协议时无损拆分旧计划。
- **依赖**：`research_artifacts`(read/write/record/path_in/sha)、`output_provenance.current_origin`；`prompt_contract` 生成给模型的路径约束文本（"Never author executor receipts, freezes, approvals or outcomes"）。
- **边界/标注**：纯库；`enabled` 完全依赖 `state/run.json` 标志；`ALIASES`、路径结构、状态字段全部硬编码；`relevant` 对未列出的路径默认返回 `True`（放行共享主题契约）。

### 2.2 `paper_qa.py`（305 行）
- **职责**：**有界原生来源问答**（明确「不是 PaperQA2 SDK」）。确定性词法重叠检索（无 embeddings / rerank / 网络获取），可选 `--execute` 才调用集中计费的 OpenAI reader 角色，且只能基于选定来源块作答。
- **对外能力(CLI)**：`--project --question-file --source(repeatable) --output --execute --max-source-chars --max-output-tokens --retrieval-plan-file`；函数 `_file/_terms/_sections/retrieve/validate_response/answer/main`。
- **输入/输出**：输入为项目相对 `.md/.txt/.pdf`（`_sections` 用 pypdf）+ 问题文本 + 可选 `retrieval_plan` JSON；输出固定 `evidence/qa/*.json`（`kind=native_source_qa_diagnostic`）。
- **关键机制**：路径安全 `BLOCKED_PARTS={.git,.cache,api_runs,state,secrets,credentials,private,raw}` + 逐段 symlink 检查 + 2MB/单文件；`_terms` 词法+中文双字切分；`retrieve` 支持两条路径——(a) `retrieval_plan` 时调 `scripts.evidence_retrieval.retrieve` 融合检索（校验 plan 绑定本问题+来源集、拒收 `declared_counterevidence`、返回 `retrieval_completeness_verified:False`）；(b) 默认词法重叠，最多 12 blocks / `max_source_chars` 预算。`validate_response` 用 `strict_json`（重复键/非有限数拒绝）严格校验 `answer/abstain/citations/statements`，每条引用 `source_id+locator` 必须命中、`quote` 必须 verbatim 且 8–1200 字符、无重复、`answer` 必须恰等于 statements 文本换行拼接。`answer` 在写盘前二次校验所有来源 sha 未变；`open("x")` 拒绝覆盖。
- **付费 API 点**：`--execute` → `model_runtime.call(provider="openai", role="reader-qa", stage="auxiliary")`，`DR_OS_ROUTING_PROFILE=production` 时附 `reasoning_effort=high`；记录 `model_receipt`（requested/reported model、request_id、cache_hit）。
- **依赖/边界**：`research_artifacts.strict_json`、`model_runtime`、`output_provenance.record_model_writes`、`publication_figures`(PROJECTS_ROOT/safe_file/sha256_file)；报告硬标注 `not_paperqa2_sdk/not_scientific_evidence/human_source_review_required:True`、`retrieval_completeness_verified:False`、`semantic_support_verified:False`。**名实**：文件名 paper_qa 但明确非 PaperQA2 SDK。

### 2.3 `paper_reader.py`（148 行）
- **职责**：页锚定的个人 PDF 阅读器，可选 GPT 翻译；提取文本/页图**不是独立验证的科学证据**，仅供个人本地副本使用。
- **对外能力(CLI)**：`--project --pdf --output --max-pages --translate --include-page-images --pages`；函数 `reusable_reader/build/main`。
- **输入/输出**：本地 PDF；输出三件套 `evidence/readers/*.md` + `.source-map.json` + `.reader.json` 回执（+可选 `-page-NNN.png`）。
- **关键机制**：`reusable_reader` 复用条件（reader 实现哈希、pdf 哈希、reader 哈希、source-map 哈希、selected_pages 全匹配）；`build` 用 pypdf 提取、`pdftoppm`（subprocess，本地二进制）渲染页图；哈希绑定 `pdf_sha256/reader_sha256/reader_implementation_sha256/source-map sha256`；`source_blocks` 标注 `extracted_not_semantically_verified`；`output_provenance.record_model_writes`。
- **付费 API 点**：`--translate` → `model_runtime.call(provider="openai", role="reader-translation")`，逐页翻译，保留数字/hedges/citations。
- **边界/标注**：≤100 页、单页≤40000 字符、symlink 拒绝、不覆盖。**未接线/占位**：`reusable_reader()` 已定义但 `main` 从未调用（死代码）。回执 `not_citation_evidence:True`、`personal_use_only:True`。

### 2.4 `paper_to_ppt.py`（85 行）
- **职责**：从**审阅后的 spec** 生成证据锚定的可编辑组会 PPT（python-pptx）；幻灯片文案由研究者/GPT writer 提供，**渲染器绝不从 PDF 推断**。
- **对外能力(CLI)**：`--project --spec --output`；`build/main`。
- **输入/输出**：spec JSON（`schema_version=1.0`、`source_pdf`、`source_sha256`、2–40 slides，每个含 title/body/speaker_notes/source_page，可选 image+image_sha256）；输出 `evidence/readers/*.pptx` + `.deck.json` 回执。
- **关键机制**：`safe_file` 路径校验；源 PDF sha256 精确匹配；`source_page` 必须在真实 1-based 页范围；图片 PIL 校验尺寸+哈希；页脚/notes 写入来源页/图引用；哈希绑定 `plan_sha256/deck_sha256/source_sha256`；`record_model_writes(family="other", local-deck-renderer)`。
- **依赖/边界**：python-pptx / pypdf / PIL（可选 `.[reader]`）；回执 `visual_review_required:True`、`not_manuscript_or_experimental_evidence:True`。纯本地，无 API。

### 2.5 `pre_submission_review.py`（152 行）
- **职责**：**准则绑定、证据锚定的投稿前审查，明确「不是录用分数」**。
- **对外能力(CLI)**：`--project --paper`；`criteria_for/audit/validate_saved_report/main`；常量 `JUDGEMENTS`（EXCEEDS/MEETS/PARTLY_MEETS/DOES_NOT_MEET/NOT_ASSESSED/NOT_APPLICABLE）。
- **输入/输出**：读 `config/pre-submission-criteria.json`、`papers/Pxx/reviews/pre-submission-checklist.json`；写 `reviews/pre-submission-review.json`；返回码 2=不通过。
- **关键机制**：`calibration_status` 必须 `NOT_CALIBRATED`（否则报错"不得宣称测得录用概率"）；禁止 `score/overall_score/acceptance_probability/ranking` 及逐项 `score/points/weight`；通用准则不可 `NOT_APPLICABLE`；`manuscript_anchors` 必须在规范稿件源树内；`evidence_anchors` 用 `anchor_errors` 校验；收集 `dependencies` 路径→sha256；哈希绑定 `spec_sha256/criteria_sha256/manuscript_digest`；`validate_saved_report` 全量比对 current==saved（stale 检测）。
- **依赖**：`research_candidates`(anchor_errors/text_fields)、`research_methods`(peer_review_method/safe_path/sha256)、`reporting_checklist.canonical_manuscript`（组内）、`citation_audit`(范围外)。
- **标注**：`criteria_role="supplementary ARS...K-Dense peer-review guidance is primary"`、`scientific_validation:False`、`human_review_required:True`。

### 2.6 `primary_recovery.py`（712 行，分两段读）
- **职责**：证据绑定的**主实验失败恢复**，含「有界自动无启动重试」与「自动撤销失败协议」。全组最密集的哈希/预算/独立审计逻辑之一。
- **对外能力**（纯库，无 main）：`digest/write/path_in/records/receipt/_approval/preserved_output/_original_input/_retained_output/latest_attempt/selected_attempt/require_next_attempt/_no_start_evidence/automatic_retry/diagnosis_context/failure_control_status/automatic_retirement/prepare/apply/_retire/histories/historical_cost/gate_errors/approved_exploration`；常量 `CONTROL=state/primary-recovery`、`HISTORY=experiments/history`、`AUTOMATIC_PROPOSAL=program/primary-recovery.json`、`MODULE`。
- **输入/输出**：读 `experiments/registry.jsonl`、`state/run.json`、`experiments/plan.json`/`budget.json`、`experiments/runs/{attempt}/run.json`、日志、preregistration；写 `state/primary-recovery/{diagnostics,retries,versions}/*.json`、`experiments/history/vNNN/manifest.json`、改写 `state/run.json`（撤销时回退到 G3）、清空 registry、删除 preregistration。
- **关键机制**：`receipt` 校验执行器回执文件与 registry 行完全一致且未变；`_approval` 哈希绑定 `failed_receipt_sha256/plan_sha256/budget_sha256` + `output_provenance` 控制器来源（自动决策要求 provider=`deterministic-control-plane`、model=`scripts/primary_recovery.py`、actor、human_confirmation=False、next_attempt_number=2、`diagnosis` 与当前证据一致）；`_no_start_evidence` 极严：只认 `process_started=False`/`failure_kind=process_launch_oserror`/errno∈{ENOENT,EACCES}/空 stdout+stderr/无输出/输入完整性通过/attempt-001；`automatic_retry` 仅 G4+awaiting_work、校验计划/预算哈希、cwd/argv/seed/timeout/cost、程序 `shutil.which` 可用、累计算力 `all_compute_cost + requested <= ceiling`，**明确「never runs an experiment / changes approved protocol」**，最多 1 次；`diagnosis_context` 生成**免费**失败诊断包（`paid_calls:0, execution_authorized:False`），含**凭据泄漏检测**（环境变量中 KEY/SECRET/TOKEN/PASSWORD 的值或其 urlquote 若出现在日志文本→阻止自动模型诊断）、64KB 日志上限、100 attempts 上限；`automatic_retirement` 要求 `family=="openai"` 的 writer 提案 + `review_receipts.validate_gate(G4)` + 4 份独立审计回执（initial/audit/final/audit）；`_retire` 归档到 `vNNN`、改 `approved_gates`、状态回 G3；`histories` 校验封印/manifest/归档/回执/保留输出哈希；`gate_errors` 强制修订计划用新 run_id 与不同输出路径、分析阶段（exploratory/prospective）一致。
- **依赖**：`paper_execution.artifact_path/papers/enabled/selected`、`experiment_runner`、`supplemental_experiments.all_compute_cost`、`scientific_scope`、`study_routes`、`output_provenance`、`review_receipts`、`cloud_checkpoint`、`model_spend`（间接）。
- **标注**：硬编码 `maximum_automatic_retries=1`、`vNNN` 版本上限、100 attempts、64KB 日志、`all attempts share original cumulative total`；`status` 字段大量 `scientific_validity_verified:False`。

### 2.7 `production_readiness.py`（185 行）
- **职责**：**非生成式生产配置检查** + 可选只读目录/账单检查；「绝不授予预算、启动研究、探测推理或改状态」，目录访问只认证元数据、**不证明模型真实性**。
- **对外能力(CLI)**：`--check-models --check-billing --billing-provider --output`；`catalog/report/main`；`NoRedirect`(禁重定向)。
- **输入/输出**：`model_routing.load_policy`、`config/model-pricing.json`（或 `DR_OS_MODEL_PRICING_JSON`）、`dynamic_routing.load_policy`、环境变量凭据；输出报告 dict/JSON，返回码 1=配置错误。
- **关键机制**：`report` 校验每条 route 的 credential/family/billing quote（`quote_sha256`）、dynamic mode、billing meter（`relay_billing.read_meter`，仅 metadata）、catalog 模型存在性（**不做 suffix 剥离/模糊别名**）、`relay_guard.inspect` 的 shared guards；`safe_text` 对 env 中含 KEY/TOKEN/SECRET/PASSWORD/EMAIL 的值做脱敏替换。
- **真实网络/凭据点**：`catalog()` 用 urllib 向 `https://cheapai.info/v1/models` 或 `https://codekey.ai/v1beta/models` 发 GET（`Authorization: Bearer` 或 `x-goog-api-key`），30s 超时、2MB 限、禁重定向。域名白名单硬编码 `{cheapai.info, codekey.ai}`。
- **标注**：报告硬编码 `model_generation_calls:0`、`new_spending_authority:False`、`scientific_completion:False`、`inference_access_and_effort_passthrough_verified:False`、`optional_image_generation:"disabled_no_selected_image_model"`、`upstream_paperqa_sdk`（仅状态字符串，非实际能力）。`inference_eligible` 依赖 shared guards。

### 2.8 `public_review_anchors.py`（461 行）
- **职责**：获取/重放**有独立许可证据的 eLife 公开评审锚点**，无模型/无伪造标签；README 所称「24 篇真实公开评审论文」的落地点。另含可选的**三 seat 校准**（domain/editorial/statistics）。
- **对外能力(CLI)**：`--cache --manifest [--replay] [--plan-calibration]`；函数 `calibration_batches/calibration_predictions/calibration_metrics/calibration_costs/calibration_plan/calibration_preview/run_calibration/primary_json/_fetch/_plain/_acquire/collect`；常量 `API=https://api.elifesciences.org`、`LICENSE=CC BY 4.0`、`FROZEN=docs/acceptance/elife-public-anchors-2026-11-07.json`、`EVIDENCE_RUBRIC`、`RUBRIC_SOURCE`（硬编码 `response_sha256`）、`CALIBRATION_SEATS/TIMEOUT=300/INPUT_BYTES=750000/OUTPUT_TOKENS=4000`。
- **输入/输出**：冻结 24 篇（16 calibration + 8 holdout）固定清单；写 `program/public-review-anchors.json`、`program/judgment-benchmark.json`、`program/research-control.json`、每篇 `primary.txt/assessment.txt/rights.json/attribution`、校准 dry-run/执行报告。
- **关键机制**：`_acquire` 严格校验 eLife API article 版本/DOI/版权 `CC-BY-4.0`/elifeAssessment DOI 与 Crossref `peer-review` type+CC BY 4.0 license；`primary_json` 用 `json_field_spans` 只保留 `PRIMARY_FIELDS`（排除 review 字段）；**防泄漏**：检查 distinctive assessment 句未进入 primary、review 不在 primary 内；盲测（label 不送模型）；`calibration_predictions` 用 `strict_json` + case_sha256 绑定；`calibration_metrics` 保留 majority baseline/abstention/class imbalance、缺失→None；`calibration_costs` 区分 settled_gateway_debit/settled_usage_receipt/estimated_upper_bound/unknown。
- **真实网络点**：`_fetch` → `network_safety.fetch_bytes`/`literature_evidence.fetch_provider_bytes` 抓 `api.elifesciences.org` 与 `api.crossref.org`（域名白名单、HTTPS、40s、12MB、Crossref 礼貌 `sleep(2)`、attempts 留痕）。
- **付费 API 点**：`run_calibration(execute=True)` → `model_runtime.call(role="independent-critique", reasoning_effort="high", use_cache=False)`；要求云端 executor、`DR_OS_REQUIRE_REMOTE_RESERVATION=1`、`preflight_route`、预算 preflight、`reservation_bound`、deadline 检查；每次调用前写 `destination` 保留账单/原始响应；身份/路由/回执严格校验；失败 `partial_failed_no_retry`。
- **标注**：硬编码 24 篇/16+8 split、`RUBRIC_SOURCE.response_sha256`、`FROZEN` 路径、`LICENSE`；报告 `calibration_status:NOT_CALIBRATED`、`numeric_score_calibration_verified:False`、`three_view_panel_effectiveness_verified:False`、`model_output_accepted_for_science:False`、`automatic_acceptance:False`。**文档宣称对照**：README 的「真实 0.85 一致性」在本文件明确仍未验证（`human_claim_sample_agreement:None`）。

### 2.9 `publication_figures.py`（745 行，分两段读）
- **职责**：从**已登记数据**渲染确定性、期刊级图表；模型只能提 JSON 设计，Python 读真实表并生成矢量+高分辨率输出（角色隔离核心）。拒绝 3D chart junk、缺失轴语义、未绑定数据。
- **对外能力(CLI)**：`render --project --spec [--record --run --language-checked-by --reuse-panels]`；函数 `safe_file/_english_text/actual_figure_labels/validate_spec/_imports/_read_table/_groups/_numeric/_decorate/_draw_standard/_draw_heatmap/_draw_forest/inspect_layout/align_grid_rows/_draw_panel/_render_full/render/main`；常量 `PROJECTS_ROOT`、`KINDS`、`FORMATS={png,pdf,svg}`、`PALETTE`、`CJK_RE`、`FigureSpecError`。
- **输入/输出**：spec JSON（`schema_version=1.0`、style、formats 必含 svg+pdf、dpi≥300、英文 caption/alt_text、claim_ids、1–6 panels）；数据 CSV/TSV/JSON；输出 `papers/Pxx/figures/*` 的 svg/pdf/png + `.figure-build.json` + `.output-qa.json` + `.render-receipt.json` + `.renderer.py` wrapper + `reviews/figure-layout/*.json/pdf`。
- **关键机制**：`validate_spec` 用 `CJK_RE` 强制英文标签、拒 3D、误差区间必须包含估计；`_render_full` 读表前后 sha 一致性校验、`figure_layout.inspect_panels`、`figure_output_qa.audit_outputs`、`actual_figure_labels`；`render` 用 `GITHUB_RUN_ID`/`DR_OS_CLOUD_EXECUTION_RECEIPT_ID` + `GITHUB_ACTIONS`/`DR_OS_CLOUD_EXECUTOR` 判定 `status=pass` 否则 `unverified_execution`；`output_provenance.record_model_writes(family="other", deterministic-local-renderer)`；`--record` 调 `figure_provenance.record_figure`。`source_data_export` 为显式 opt-in（提示可能泄露受限数据）。
- **依赖**：`research_artifacts.sha`、`figure_recipes`、`figure_layout`、`figure_output_qa`、`figure_provenance`、`output_provenance`、matplotlib/numpy/pandas（可选 `.[figures]`）。
- **标注**：硬编码 `svg.hashsalt="doctoral-research-os-v2"`、`DejaVu Sans`、PALETTE、尺寸边界。**名实/退役**：`--reuse-panels` 帮助写 "Retired optimization; renders the full figure"，`panel_cache.status="retired"/mode="full_redraw"`；`reuse_panels` 旧逻辑已废弃但仍保留 CLI 参数。本文件是全组路径安全原语的供给方。

### 2.10 `quality_gate.py`（156 行）
- **职责**：校验事实质量证据，**分数/期刊观察单独报告**；「数值自评分不能验证科学」。
- **对外能力**（纯库）：`scientific_projection/_nonempty_string/_score/validate_report/validate_file`；常量 `MIN_SCORE=8.0`、`MIN_OVERALL=8.5`、`MIN_EVIDENCE`、`ACCEPTABLE_QUARTILES={Q1,Q2}`、`DIMENSIONS`（G1–G5）、`OBSERVATIONAL_CRITERIA`。
- **输入/输出**：quality report JSON（schema 1.1/1.2）；输出 `errors` 列表（阻断）+ `warnings`/observations（不阻断）。
- **关键机制**：1.2 版用 `assessments`（每条 status=satisfied + rationale + source_anchors + `anchor_errors`）；1.1 版用 `scores`（仅 observation）；`_score` 低于阈值只 warning「不是科学闸门」；`evidence` 最少条目、逐条 id/source/claim_supported/source_date；`novelty_basis` 必须比较型；`originality_assessment` 需 ≥3 closest prior work、≥3 adjacent fields、`counterevidence_considered=True`、residual_risk；`doctoral_readiness` 5 字段 + ≥3 examiner_challenges；`venue_readiness`（Q1/Q2 目标、≥2 候选、HTTPS 源、当年/上一年 JCR）全部降为 observation；G1/G2 强制 `human_review_required=True`（呼应规则 5）。
- **依赖**：`research_candidates.anchor_errors`、`venue_policy.meets_target`。
- **标注**：**名实**——文件名 quality_gate 但 `MIN_SCORE/MIN_OVERALL/ACCEPTABLE_QUARTILES` 都只是 advisory/observation，不构成放行门槛（呼应 README「无 Q1/Q2/IF 放行门槛」）。

### 2.11 `ref_verify_adapter.py`（356 行）
- **职责**：运行**固定版本** `ref-verify` 引擎，把 claim 检查绑定到论文快照；「摘要核验不夸大为全文核验」。
- **对外能力(CLI)**：`--project --paper [--claims --output --timeout]`；`canonical_manuscript/project_paper/safe_paper_file/load_claims/find_executable/installed_version/_validate_engine_payload/run/validate_saved_report/main`；常量 `EXPECTED_VERSION="1.2.0"`、`UPSTREAM_COMMIT="8d56a6c5..."`、`ALLOWED_CLAIM_TYPES={topline,numeric}`、`ALLOWED_SOURCES`、`DOI_RE`。
- **输入/输出**：`reviews/citation-claims.jsonl`（每行 id/doi/claim/claim_type/evidence_depth=abstract，唯一性+DOI 校验）；`manuscript/references.bib`；输出 `reviews/ref-verify.json`。
- **关键机制**：`canonical_manuscript` 要求恰有 `main.tex` 或 `main.docx`（非 symlink）；`run` 用 `subprocess.run`（`check=False`、300s、临时目录）调 `ref-verify check-file --format jsonl --json`，校验 `installed_version==1.2.0`、返回码 0/2、结果 id/doi/claim 与输入一致、verdict=ACCEPT/status=SUPPORTED、summary total/accept；`validate_saved_report` 做 stale 检测（input sha、bibliography sha、`manuscript_digest`）；报告 `full_text_claims_supported:False`。
- **外部/付费**：本地第三方 CLI `ref-verify==1.2.0`（可选 `--with-reference-tools` 安装）；引擎内部可能联网取 DOI 证据。
- **标注**：`UPSTREAM_COMMIT` 是硬编码字符串，仅写入报告并被 `validate_saved_report` 比对，**并不真正校验引擎二进制来源**。`canonical_manuscript` 被本组 3 个 G5 审计模块复用。

### 2.12 `relay_billing.py`（239 行）
- **职责**：**只读中转站扣费对账**；绝不生成/重试/授权；失败一律「retain reservation（保留预扣）」。所有者汇率规则「数值 USD 钱包单位 = CNY 单位，**非市场汇率**」。
- **对外能力**（纯库）：`_get_json/_count/_amount/_spec/_fingerprint/_debit_fingerprint/_rows/read_meter/_new_cheapai_rows/settle`；异常类 `BillingReconciliationError`；`_CURRENCY_RULE`、`_CHEAP_DENOMINATION`。
- **输入/输出**：环境变量凭据；`before`/`after` meter 快照；输出 `actual_cost_cny` + `debit_evidence`（含 before/after snapshot sha256）。
- **关键机制**：`_get_json` 精确端点白名单 `{(cheapai.info,/api/status),(cheapai.info,/api/log/token),(codekey.ai,/v1/usage)}`、HTTPS、无 query/fragment/用户名密码、禁重定向、15s、2MB；`_rows` 只取 `type=2` debit、模型名/计数校验、**display id 不信任**（用 `_debit_fingerprint` 排除 id 的字段多重集）；`read_meter`：codekey 返回 `total_actual_cost`，cheapai 返回 `quota_history`（`quota_per_unit=500000`）；`_new_cheapai_rows` 多重集比对新旧 debit，仅容忍单行 rollover；`settle` 最多 3 次免费 lag 轮询（`sleep(2)`），`Decimal` 算差额，匹配「恰好一个新 gateway request」。
- **真实网络/凭据点**：`_get_json` urllib GET 上述 3 个 HTTPS 端点，带 `Authorization: Bearer {key}`（密钥从 env）。
- **标注**：硬编码中转站端点、500000 quota/unit、1000 行/100 行窗口、`_CURRENCY_RULE` 字符串。被 `production_readiness`、`relay_guard` 复用。

### 2.13 `relay_guard.py`（602 行，分两段读）
- **职责**：跨云作业的**共享凭据级「未知扣费 + 单次 POST」守卫**。本组最复杂、硬编码历史最多。
- **对外能力**（纯库）：`fingerprint`、类 `CloudStore`(api/read/read_blob/write)、`_entry_provider/_number/_before/_row/_settled_receipt/_source_entry/source_holds/load/inspect/project_transport/authorize_transport/validate_debit/_immutable_trial_source/_evaluation_source/_project_settlement/_trial_settlement/prepare_reconciliation/reconciliation_snapshot/reconcile`；常量 `REPOSITORY="hengyizang/lunwen"`、`BRANCH="cloud-state/relay-guard"`、`SOURCES`（历史 trial 分支/文件）、`ALIASES`、`TRIAL_SOURCES`、`EVALUATION_TRIAL="model-evaluation-20261029"`、`EVALUATION_ORIGINAL_BLOB/EVALUATION_TICKET`、`TRIAL_ORIGINALS`（硬编码 blob SHA）、`REQUEST_FIELDS`、`_TICKET`(ContextVar)。
- **输入/输出**：GitHub `relay-guard/{key_id}.json` 共享状态（`legacy_holds/active/events/reconciled_legacy_ids/rotated_provider_credentials`）；`model_spend` 预约；reconciliation 提案 JSON。
- **关键机制**：`CloudStore.api` 用 `subprocess` 调 `gh api` 对 GitHub contents/git blobs API 做 CAS（限 `GITHUB_ACTIONS=true` 且 `GITHUB_REPOSITORY==REPOSITORY`，GH_TOKEN，60s）；`read_blob` 校验 Git blob SHA-1 与 base64；`write` 用 contents PUT + sha CAS + 回读；`fingerprint` 凭据哈希绑定；`_settled_receipt` 严格校验独立扣费回执（status/billing_status、amount≤ceiling、model、debit_evidence、before meter、whole-key 历史前缀）；`source_holds` 扫历史账本找未结清扣费→`legacy_holds`；`inspect` 的 `inference_eligible = not legacy_holds and active is None`；`project_transport`(contextmanager) + `authorize_transport` 用 `_TICKET` 保证「一次操作仅一次 POST」且端点/模型/凭据/预约哈希一致；`prepare_reconciliation` 支持 4 种 kind（new_credential/settled_active/settled_trial/settled_legacy）；全链路 fail-closed（异常即不授权生成）。
- **真实外部服务点**：`CloudStore.api` → `gh api`（GitHub REST），读写仓库分支/blob。
- **依赖**：`research_artifacts.json_digest`、`ai_providers`、`relay_billing`（组内）、`primary_recovery.path_in/read`（组内）、`model_spend`、`cloud_checkpoint.sync_billing`。
- **标注**：**大量硬编码** GitHub blob SHA、trial 名、ticket id、2026-10 日期、仓库/分支名——把历史真实试验「钉死」在代码里；`inspect` 明确 `catalog_access_does_not_release_holds:True`（呼应 production_readiness）。

### 2.14 `reporting_checklist.py`（116 行）
- **职责**：校验并绑定适用的**报告规范清单**（如 PRISMA/CONSORT 类）到稿件。
- **对外能力(CLI)**：通过 `research_artifacts.paper_audit_cli`（`--project --paper`）；`load_input/audit/validate_saved_report/main`。
- **输入/输出**：`reviews/reporting-guideline-input.json`（study_design/guideline/guideline_version/official_url(HTTPS)/reviewed_by/reviewed_at/items）；输出 `reviews/reporting-guideline.json`。
- **关键机制**：items status∈{present,not_applicable,open}，`open` 直接 error、present 需 location、not_applicable 需 rationale、evidence_ids 必填；报告含 `input.sha256` + `manuscript_digest` 哈希绑定；`validate_saved_report` 逐 key（input/manuscript/checklist）比对 stale。
- **依赖**：`citation_audit.manuscript_digest`、`ref_verify_adapter.canonical_manuscript`（组内）、`research_artifacts.paper_audit_cli`。

### 2.15 `requirements_trace.py`（81 行）
- **职责**：区分「已实现代码 / 已测试能力 / 真实科研完成」，读 `config/requirements-traceability.json`。
- **对外能力(CLI)**：无参数；`evidence_path/validate/main`；`ACCEPTANCE` 集合含 `research-not-yet-executed`、`live-network-required`、`credentials-required`、`human-review-required`、`blocked-unmetered` 等。
- **输入/输出**：追踪矩阵（schema 2.0 / `cloud_only`）；输出 `matrix_valid/all_requirements_fulfilled/errors/pending`。
- **关键机制**：每条 requirement 的 implementation/acceptance/remaining/evidence/tests 校验；`acceptance=="verified"` 需 verification receipt（哈希校验 + status=passed + requirement_ids + source_commit + workflow_run_url）；返回码 2=有错。
- **标注**：呼应 README「工程验收不代表科学有效」与 `docs/P0-P1-COMPLETION.md` 追踪表。

### 2.16 `research_artifacts.py`（321 行）
- **职责**：**全组确定性基础设施原语**；「无模型调用、无实验执行」。
- **对外能力**（纯库）：`utc_now/load_json/json_bytes/json_digest/object_fields/changed_fields/read_optional/walk_files/sha/path_in/regular_file/read/strict_json/json_field_spans/write/record/save_report/report_errors/matches_origin/verify_files/seal_manifest/validate_manifest/paper_audit_cli/bound_source/_schema_validator/_schema_source/schema_contract/schema_errors`。
- **输入/输出**：通用 JSON/路径/bytes；`schemas/*.schema.json`（jsonschema Draft202012）；`output_provenance`。
- **关键机制**：`path_in` 拒绝绝对路径/`..`/反斜杠/冒号/symlink/逃逸；`write` 原子 `NamedTemporaryFile` + `os.replace`；`strict_json` 用 `object_pairs_hook` 拒重复键、`parse_constant` 拒 NaN/Inf；`json_field_spans` 不重序列化科学数字（被 `public_review_anchors.primary_json` 用）；`record`→`record_model_writes(family="other", deterministic-control-plane)`；`seal_manifest/validate_manifest` 绑定「构建器实现哈希 + 精确输出清单」；`_schema_validator` 缓存 + 自定义 number/integer/minLength/uniqueItems + `schema_errors` 诊断**不回显私有输入值**；`schema_contract` 从 schema 导出写作导航。
- **依赖**：`jsonschema`（第三方）、`output_provenance`。
- **标注**：被几乎全部 26 文件引用，是哈希/路径/原子写/schema/来源登记的单一来源。

### 2.17 `research_candidates.py`（297 行）
- **职责**：方向筛选后的**来源绑定论文卡片与竞争假设**；不授予新颖性。
- **对外能力(CLI)**：`hypotheses|paper-card --project --spec --output [--for-gate]`；`text_fields/text_list/anchor_errors/validate_idea/audit_register/audit_card/validate_saved_register/main`。
- **输入/输出**：`program/hypothesis-register.json`、`program/hypothesis-audit.json`、paper-card spec；输出审计报告。
- **关键机制**：`anchor_errors` 是全组复用的**证据锚校验器**（path/sha256/locator/excerpt 必填、excerpt≤25 词/1000 字符，支持 pdf(pypdf)/md/txt/tex/csv/tsv/json/jsonl/bib 行定位/docx 段落定位，excerpt 必须原文包含，异常→`source verification unavailable` 而非 PASS）；`validate_idea` 强制 `novelty_status="prior_art_search_required"`、`evidence_status="hypothesis"`、≥2 竞争解释、failure_modes≥2、完整 test_plan；`audit_register` ≥3 假设、`automatic_selection=False`、`argument_plan` 允许/禁止主张互斥、`innovation_screening.validate`；`audit_card` 区分 `author_statement`/`agent_analysis`、partial source 不能断言 unseen methods/experiments。
- **依赖**：`research_methods`(safe_path/sha256)、`scientific_reasoning`、`innovation_screening`、`source_scope`、pypdf/python-docx（可选）。
- **标注**：`scientific_value_verified/novelty_granted/semantic_independence_verified:False`、`human_review_required:True`；`validate_saved_register` 兼容旧报告但重算 gate。

### 2.18 `research_case.py`（673 行，分两段读）
- **职责**：单一来源感知工作台，聚合论文论证与**本地发布材料**（渐进式 `research-case.json`）；「缺证据保持可见，不新增闸门/模型调用/实验/投稿/录用分数」。
- **对外能力(CLI)**：`--project --paper [--export case|preprint|rebuttal|retarget|reproduction]`；`_paper/_binding/_nonempty/_ids/_observed_figure/competition/_case_findings/build_packet/_table/_venue_sources/_registered_identifier/export/_reproduction/main`；`KINDS`、`FIGURE_ROLES`；内嵌 `_REPLAY_PATHS`/`_DOCKER_REPLAY` 字符串。
- **输入/输出**：`paper-contract.json`、`research-case.json`、`experiment-evidence-plan.json`、`program/paper-map.json`、`claims/claim-evidence.csv`、`evidence/journal-sources/index.json`、`program/journal-dossiers.json`、`evidence/literature-api-ledger.jsonl`；输出 `papers/Pxx/release-preparation/{kind}-{content_sha256}/`（版本化不可变快照 + manifest）。
- **关键机制**：`@paper_scoped` 跨论文隔离；`build_packet` 用 jsonschema 校验 case、聚合全 6 篇 cumulative 表、`_case_findings` 检查 headline/counterclaim、claim_ids/test_ids 绑定 contract/protocol、3 类 reader_benefits、pre_mortem、figure_first 三角色（main_result/strongest_baseline/negative_boundary）、variants、positioning、venue_fit 全字段、递归 `_binding(located=True)`；`competition` 只统计检索回执里显式选中的「同问题队列」，unknown 不归零；`_venue_sources` 要求 HTTPS 官方域名 + retrieved_at + http 200 + raw_sha256；`export` 5 种本地材料，唯一内容哈希目录、`require_final_origins`（非 Claude 来源）、不覆盖历史快照；`_reproduction` 导出**已执行**重放单元（`selected_attempt`/`receipt`/`validate_registry`、Docker digest-pinned image 或 host python 版本、requirements pins、result_table 逐行比对、生成 `reproduce.py`）。
- **外部/真实执行**：`export` 内部调 `experiment_evidence.build_report`、`figure_provenance.lineage`、`submission_package.safe_file`、`output_provenance.require_final_origins`、`experiment_runner.requested_resources`；生成的 `reproduce.py` 未来用 `subprocess.run([sys.executable, *argv])` 或 `docker run` 执行已批准研究代码（非沙箱）。
- **标注**：`limits.paid_model_calls:0/execution_authorized:False/external_publication:False`；`_observed_figure` 拒绝 planned figure-story 冒充 observed；`external` 永不自动投稿。内嵌 replay 脚本为硬编码字符串。

### 2.19 `research_cycle.py`（139 行）
- **职责**：**阶段周期编排**：行政 intake 或一次普通批评；实际问题才触发修复/复审；G5 用三互盲视图替换普通 critic。
- **对外能力**（纯库）：`research_decision/decision_errors/requires_critic/skipped_remediation/review_cycle/submission_cycle/after_reviews`。
- **输入/输出**：`state/run.json`、`review_receipts` 的 `state/review-receipts/.../attempt.json`、research_notebook 评估；回调 `invoke/remediate/refresh/writer_notes/log/prompt`。
- **关键机制**：`requires_critic(stage!="intake")`；`skipped_remediation` 对 3 种 review_mode 记录 no-call 原因；`review_cycle` 在**任何付费 reviewer 调用之前**写 `attempt.json`（`status=started`，"Replaying this ID never retries paid work"）、`review_receipts.seal_phase`、`api_orchestrator.remediation_required/validate_remediation_notes`、`automated_quality.checked_run`；只有 `not remediation_skipped` 才二次 invoke + final review；`submission_cycle` 调 `review_panel.run`（三互盲）；`after_reviews` 对 writing-and-review 走 `supplemental_experiments.automatic_approval` + `research_phase.enter_submission`，对 experiment-execution 走 `primary_recovery.automatic_retirement`（组内）。
- **标注**：`writer_family` 参数体现角色隔离；`scientific_completion_verified:False/current_stage_authorized:False`；G5 panel 与范围外 `review_panel` 协作，本组只见编排。

### 2.20 `research_design.py`（745 行，分两段读）
- **职责**：博士创新性与论文级研究设计的**确定性校验器**；「不证明新颖性/博士价值/可靠性/期刊录用」。
- **对外能力**（纯库）：`_text/_planning_quartile/_list/_string_list/_object/_https`、`validate_negative_result_plan/validate_scientific_bindings/_paper_dependencies/validate_thesis_theme/validate_theme_independence/validate_theme_mapping/validate_selected_direction_cloud_feasibility/_record_date/validate_originality_audit/validate_search_log/validate_paper_map/validate_paper_contract/validate_portfolio_evidence/validate_experiment_design`。
- **输入/输出**：`paper-map.json`、`paper-contract.json`、`program/*` 契约、`paper-experiment-design.schema.json`、state/experiment registry/claim 结果；输出 `errors` 列表。
- **关键机制**：`_planning_quartile` 明确「排名元数据不提供科学质量门槛」；`validate_scientific_bindings` 把 G2 假设/证伪措辞绑定到 G3 比较（阈值/decision_rule/primary_metric、条件全覆盖）；`validate_theme_independence` 把 A/B 主题独立性做成 G1/G2 阻断（claim IDs/papers 互斥、doctoral_question 不同）；`validate_selected_direction_cloud_feasibility` 阻断 G1 至有 cloud-only 路径，含可行性证据 provenance（**非模型自证**：provider 须 deterministic-*/human-attestation、quote 在原文、executed pilot 需真实注册成功尝试）；`validate_search_log` 要求声明的数据库/query family/closest works 全可追溯；`validate_paper_map` 六篇唯一 claim、依赖无环、pairwise 或 cumulative 独立性、thesis_synthesis argument_links；`validate_experiment_design` 禁止用 test/final/holdout 调参、stochastic ≥3 seeds、baselines 三类、clean-room 必须 digest-pinned container；`validate_portfolio_evidence` 的 G5 分支比对 `claim_outcomes` 与 evidence_alignment，**不利/不确定证据不得 retain 原始成功叙事**。
- **依赖**：`research_artifacts.schema_errors/bound_source`、`results_validation.claim_outcomes`、`research_increments`、`output_provenance.current_origin`。
- **标注**：全程 schema + 本地交叉校验；`study_route` 支持 empirical/meta_analysis/theory；呼应规则 22（六篇共同博士问题、A/B 主题、独立性）。

### 2.21 `research_diagrams.py`（237 行）
- **职责**：把**类型化研究图 IR** 编译为可编辑 JSON/HTML + SVG/PDF/PNG；「IR 是作者核对的描述，渲染器不推断研究设计/不制造机制关系」。
- **对外能力(CLI)**：`--project --spec [--record --language-checked-by]`；`load_style/validate/layout/render/main`；`TYPES`(6)、`NODE_KINDS`、`EDGE_KINDS`、`PALETTE`。
- **输入/输出**：IR JSON（schema 1.0、type、英文 title/caption/alt_text、claim_ids、2–32 nodes、≤64 edges、`output_stem=papers/Pxx/figures/<name>`、可选 `style_ref{path,sha256}`）；输出 svg/pdf/png + 静态无 JS HTML + `.layout.json` + `.renderer.py`。
- **关键机制**：`validate` 用 `_english_text`（复用 publication_figures）强制英文、layer/rank 0–7 无冲突、去重边；`layout` 拓扑分层或 mechanism 环形；`load_style` 经 `figure_story.load_visual_style` 校验 style_ref 哈希；`render` 用 matplotlib FancyBbox/FancyArrow、`inspect_layout`、`record_model_writes(family="other")`；`--record` 调 `figure_provenance.record_figure`。
- **依赖**：`publication_figures`（组内，复用 5 个符号）、`figure_story`、`figure_provenance`、`output_provenance`。
- **标注**：`human_layout_check_required:True`；`--record` 传空 inputs/runs 给 record_figure；纯本地，无 API。

### 2.22 `research_extensions.py`（575 行，分两段读）
- **职责**：证据绑定的**方法采用 / 可比性 / 阅读锚点 / 评审发现**工作清单；防止跨论文稀释与「模型自证解决」。
- **对外能力**（纯库）：`_paper_scope/_scope_call/nonempty/sources/_sources/_closest_own_anchor/_closest_prior_anchor/_closest_evaluation/closest_work_axes/comparison/method/_method/reading_anchor/review/_review/audit/refresh/gate_errors`；`DIMENSIONS`(9 可比性维度)、`PERSPECTIVES`、`CLOSEST_AXES/CLOSEST_CONTEXT`、`SharedIntegrityError`。
- **输入/输出**：`program/research-extensions.json`（4 sections、每 section ≤200 行）；输出 `reports/research-extensions/audit.json`。
- **关键机制**：`_paper_scope` 只认原生显式 paper 归属、`_scope_call` 用 `paper_execution.scope`（组内）；`_sources` 要求 1–30 证据锚、4MB 限、quote 在源文件「**恰好出现一次**」；`_closest_evaluation` 用 JSON pointer 从本论文协议/结果取实际 dataset/metric/evaluation_basis 值，禁止 unknown；`closest_work_axes` 三轴（research_object/method/result）+ disposition/conclusion_kind，quantitative 需 matched evaluation，`scientific_comparability_verified/novelty_verified:False`；`reading_anchor` 校验 reader receipt + PDF + source_map 哈希 + fitz 页文本/bbox；`_review` **禁止 `status=="verified_resolved"`**（"a model-authored status cannot certify its own resolution"）、禁止降级继承 issue 的 severity/perspective（`SharedIntegrityError`）；`audit` 保留「不得静默删除既有结构化写作问题」；`gate_errors` 按 scope 过滤、unresolved fatal/major finding 阻断。
- **依赖**：`paper_execution`（组内）、`literature_workbench`、`method_tools`、`writing_review_actions`、`output_provenance`、`fitz`(PyMuPDF 可选)。
- **标注**：`scientific_completion_verified/gate_approved:False`；`refresh` 写 OUTPUT 并 record；`research_improvementctl` 的 `research-extensions` action 直接调 `refresh`（组内调用）。

### 2.23 `research_frontier.py`（511 行，分两段读）
- **职责**：从原生阅读、检索回执、notebook 记录做**不可变前沿准备**；「无检索/获取/实验/模型调用/科学决策；关系与关联是待审声明」。
- **对外能力**（纯库，无 main）：`_digest/_keys/_array/_ids/_origin/_binding/_bound/_coverage/_ledger/_same/_rounds/_reference/_prepare/_envelope/refresh/model_context/_context_text/_context_projection`；`OUTPUT=reports/research-frontier`、`DEFAULT/LEDGER/NOTEBOOK/HYPOTHESES`。
- **输入/输出**：`program/research-frontier.json`、notebook、literature ledger、reading coverage、hypothesis register、core-thesis、state；输出 `reports/research-frontier/{id}-{sha}.json`（不可变）。
- **关键机制**：`_origin` **直接拒绝 `family=="anthropic"`**（角色隔离）；`_binding/_bound` 全输入哈希绑定 + 来源登记；`_coverage` 校验 `literature_reading` coverage 报告（question/implementation_sha256/progress_inputs/dimension locations/`wb.validate_anchor`）；`_ledger` 读 success/failed 检索回执（2000 记录上限）；`_rounds` 计算 new canonical ids / reused receipts / 失败尝试 / source-matched dimension evidence，输出 advice，`scientific_saturation_verified:False / absence_of_evidence_proven:False`；`_prepare` 生成 gaps（含 contrary evidence 优先）、proposed_queries（"proposal_only_reuse_prior_receipts_before_search"）、relations（"declared_pending_semantic_review"）、9 个模块哈希；`refresh` 经 `literaturectl.require_cloud()`、不可变报告（变化即报错保留原件）；`model_context` 支持 writer/planner/critic/**remediator** 四角色，全量校验后投影有界摘要（40 facts/20 rounds/10 sources、JSON pointer locators、omitted_counts、`original_evidence_copied:False`），critic 仅得 factual context。
- **依赖**：`literature_intelligence/reading/reasoning/workbench`、`research_notebook`、`output_provenance`、`research_artifacts`、`literaturectl.require_cloud`。
- **标注**：`paid_calls:0/network_calls:0/scientific_completion_verified:False/gate_approved:False`；读取的是**已存在**的网络检索回执，本文件自身不发起网络。声明性字段大量「pending_semantic_review」。

### 2.24 `research_identity.py`（268 行）
- **职责**：**原创研究优先**的组合规则，只读，绝不重标论文；排除 narrative review / 文献综述冒充 primary。
- **对外能力**（纯库）：`template/_text/_strings/_host/_anchor/_venues/_analysis/validate/review_binding/prompt_contract`；`PRIMARY/SECONDARY/PROTOCOL_FIELDS/FIELDS/POLICY="original-research-first-v1"`。
- **输入/输出**：`papers/Pxx/research-identity.json`、`paper-contract.json`、`program/venue-candidates.json`、`papers/Pxx/venue.json`、`pre-submission-checklist.json`、`evidence/*`、`experiments/registry`；输出 `errors` 列表 / `review_binding` 哈希 / `prompt_contract` 文本。
- **关键机制**：`@paper_scoped`；`_text` 拒绝 TODO/TBD/FIXME/PLACEHOLDER；`_host` 要求无凭据 HTTPS/443/无 query；`_anchor` evidence/ 下哈希+行范围+quote；`_venues`（仅 G5 且 `requires_submission`）校验 venue_classifications 官方域名、checked_at 30 天内、article_type 必须匹配 contract/注册且**排除 review/survey/editorial/commentary/perspective**；`_analysis`（secondary_quantitative@G4/G5）要求 G3 封存 plan 哈希 + approval actor + executor receipts + predeclared output + sha；`validate` 禁止把文献综合重标 primary、claim_ids 必须匹配 contract 独立贡献、secondary_protocol 完整、G5 `reporting_statement` + `canonical_manuscript`（组内 ref_verify_adapter）+ `verify_location` + checklist article_type 匹配；`prompt_contract` 把输入形状直接给 API writer（`g2_assesses_proposal_only:True`、"introduces no alternative executor, paid call, budget grant, or model switch"）。
- **依赖**：`paper_execution`（组内）、`research_phase`、`research_quality._registry`、`ref_verify_adapter.canonical_manuscript`（组内）、`revision_trace`。
- **标注**：呼应 `docs/ORIGINAL-RESEARCH-POLICY.md` 与规则 23；`POLICY`、30 天时效、最小字数均为硬编码。

### 2.25 `research_improvementctl.py`（90 行）
- **职责**：**云端专用确定性 builder 的统一 CLI 分发器**；本地研究执行被禁用。
- **对外能力(CLI)**：`action`（28 个 choices：notebook/daily-brief/statistics/word-revision/revision-ledger.../research-extensions/.../statistical-watermarks）+ `--project/--paper/--packet/--source/--expected-sha256/--receipt/--kind/--record-id/--task-id`。
- **输入/输出**：项目目录 + 各 action 参数；输出 builder 结果 JSON；返回码 1 当 `status∈{fail,blocked,revise}`。
- **关键机制**：强制 `GITHUB_ACTIONS=="true"` 或 `DR_OS_CLOUD_EXECUTOR=="1"`（否则 "local research execution is disabled"）；project slug 校验（2–63 小写）、部分 action 强制 `P[0-9]{2}`；`calibration-analysis` 需 `--packet`、`increments-freeze` 需 `--kind`+`--record-id`；经 `research_operations.BUILDERS/CLI_ALIASES/invoke_builder` 分发，一批 action 直接 import 范围外模块；`research-extensions` action → `research_extensions.refresh`（**组内调用**）。
- **依赖**：`research_operations` + 10+ 范围外 builder（research_increments/incremental_writing/evidence_context/academic_style/manuscript_hygiene/watermark_cleanup/style_evaluation 等）。
- **标注**：**名实不符**——文件名 "improvementctl" 实为通用云端 builder 分发器（含 notebook/journals/calibration 等非 improvement 功能）。

### 2.26 `paper_execution.py` 到 `research_improvementctl.py` 之外：26 文件已全部覆盖，无遗漏、无越界。

---

## 3. 特别标注汇总

### 3.1 TODO / 占位 / 未实现 / 退役 / 未接线
- `paper_reader.reusable_reader()`：完整实现，但 `main` 从不调用 —— **死代码/未接线**。
- `publication_figures --reuse-panels`：帮助文本明写 "Retired optimization; renders the full figure"，`panel_cache.status="retired"/mode="full_redraw"`；`reuse_panels` 旧缓存合成逻辑已退役，CLI 参数保留。
- 大量**声明性/待审占位**：`research_frontier` 的 `evidence_round_association="declared_pending_semantic_review"`、`relations.status="declared_pending_semantic_review"`、`proposed_queries.executed=False`；`research_extensions.closest_work_axes` 的 `novelty_verified:False/comparability_verified:False`；`public_review_anchors.run_calibration` dry-run 默认 `status="dry_run_no_model_call"`。
- `research_extensions._review` 明确**拒绝** `status=="verified_resolved"`（模型不能自证解决），要求走既有独立审计+人工闸门 —— 是设计约束而非缺陷。
- `research_diagrams --record` 向 `record_figure` 传空 `inputs/runs`；`--language-checked-by` 仅 `--record` 时必填。

### 3.2 硬编码（配置/身份/历史被钉死在代码里）
- **第三方/引擎**：`ref_verify_adapter.EXPECTED_VERSION="1.2.0"`、`UPSTREAM_COMMIT="8d56a6c5..."`（仅字符串，不校验二进制来源）。
- **中转站/网关**：`production_readiness`/`relay_billing` 白名单 `{https://cheapai.info, https://codekey.ai}` 及精确端点；`relay_billing._CURRENCY_RULE="numeric USD wallet unit equals CNY1; not market FX"`、`quota_per_unit=500000`。
- **GitHub 历史**：`relay_guard.REPOSITORY/BRANCH`、`EVALUATION_ORIGINAL_BLOB`、`EVALUATION_TICKET`、`TRIAL_ORIGINALS`（多个 40 位 blob SHA）、2026-10 各 trial 名。
- **校准语料**：`public_review_anchors` 的 24 篇/16+8 split、`FROZEN` 固定路径、`RUBRIC_SOURCE.response_sha256`、`CALIBRATION_*` 常量、`LICENSE` URL。
- **其它**：`publication_figures.svg.hashsalt`、`PALETTE`；`quality_gate.MIN_SCORE/MIN_OVERALL/DIMENSIONS`；`research_identity.POLICY`、30 天时效、最小字数；`research_case._REPLAY_PATHS/_DOCKER_REPLAY` 内嵌脚本；`paper_execution.ALIASES` 全部路径模板；`publication_disclosure.LIMITS` 一堆 False/True 常量与 "Journal AI policy is excluded by the recorded user instruction"；各文件回执里的 `scientific_*_verified:False` 常量。

### 3.3 真实网络 / 付费 API 调用点
| # | 文件 | 调用 | 性质 |
|---|---|---|---|
| 1 | `production_readiness.catalog` | urllib GET `cheapai.info/v1/models`、`codekey.ai/v1beta/models`（Bearer / x-goog-api-key） | 真实 HTTPS + 凭据，仅元数据 |
| 2 | `relay_billing._get_json/read_meter/settle` | urllib GET `cheapai.info/api/status`、`/api/log/token`、`codekey.ai/v1/usage` | 真实 HTTPS + 凭据，只读扣费 |
| 3 | `relay_guard.CloudStore.api` | `subprocess gh api` GitHub contents/git blobs API | 真实外部服务 + CAS 写 |
| 4 | `public_review_anchors._fetch/collect` | `network_safety.fetch_bytes` → `api.elifesciences.org` / `api.crossref.org` | 真实公网抓取（含 sleep 礼貌） |
| 5 | `public_review_anchors.run_calibration(execute)` | `model_runtime.call(role="independent-critique", high)` 三 seat | **付费推理** |
| 6 | `paper_qa.answer(execute)` | `model_runtime.call(provider=openai, role=reader-qa)` | **付费推理** |
| 7 | `paper_reader.build(translate)` | `model_runtime.call(provider=openai, role=reader-translation)` 逐页 | **付费推理** |
| 8 | `ref_verify_adapter.run` | `subprocess ref-verify check-file` | 本地第三方 CLI（引擎内可能联网） |
| 9 | `research_case.export(reproduction)` | 生成 `reproduce.py`/`docker run` 脚本 | 生成未来执行脚本，本文件不直接执行 |
| 10 | `research_improvementctl` | 强制云端，`BUILDERS` 分发 | 间接，可能触发范围外付费 builder |

> 相对地，`paper_execution/primary_recovery/research_artifacts/research_candidates/research_case(build_packet)/research_design/research_extensions/research_frontier/research_identity/quality_gate/pre_submission_review/reporting_checklist/publication_disclosure/publication_figures/research_diagrams/paper_to_ppt/requirements_trace/relay_guard(自身逻辑)` 均**零付费 API / 零网络调用**，靠 `DR_OS_*`/`GITHUB_*` 环境变量做云端门禁。

### 3.4 安全与数据完整性风险
- **凭据外发**：`production_readiness`/`relay_billing` 用真实 Bearer key 请求中转站；`safe_text` 脱敏仅替换 env 中名字含 KEY/TOKEN/SECRET/PASSWORD/EMAIL 的值，若密钥经其它变量名注入或出现在 `advertised_models`/诊断而未被匹配，存在泄漏面（边界有限）。
- **日志凭据泄漏**：`primary_recovery.diagnosis_context` 主动扫描环境变量凭据值是否出现在失败日志中，命中即**阻止自动模型诊断**（正向防护）；但依赖日志文本确实不含凭据。
- **GitHub 共享状态**：`relay_guard` 把未知扣费/单次 POST 守卫放在 GitHub 分支 blob 上，硬编码历史 blob SHA；设计 fail-closed（异常→`inference_eligible=False`），但强依赖 `gh`/`GH_TOKEN`/仓库可达。
- **渲染/执行边界**：`publication_figures` 本地渲染标 `unverified_execution`；`research_case` 生成的 `reproduce.py` 用 `subprocess.run([sys.executable, *argv])` 执行已批准研究代码，**非恶意代码沙箱**（README 亦承认「运行器不是恶意代码沙箱」）。
- **引擎完整性**：`ref_verify_adapter` 只校验 `installed_version` 与报告里 `upstream_commit` 字符串一致，不校验二进制真实来源；`UPSTREAM_COMMIT` 可被伪造写入报告。
- **路径/来源校验**：全组普遍 `path_in`/`safe_file`/symlink/`..`/BLOCKED_PARTS 防护较严；`paper_execution.relevant` 对未列举路径默认放行（共享契约），是设计取舍。
- **版本固定**：`_schema_validator`/`pypdf`/`python-docx`/`fitz`/`matplotlib`/`jsonschema`/`ref-verify` 多为可选依赖，缺失时以明确异常降级，不静默通过。

### 3.5 「文档宣称但代码未见实现」处
- **三家族互盲 panel**：README/AGENTS 强调 G5 用「三个不同模型家族互盲来源视图」；本组 `research_cycle.submission_cycle` 仅调 `review_panel.run`（范围外），`public_review_anchors` 明确 `three_family_comparison_complete:False` —— 实现不在本组。
- **累计预算/总额**：`relay_billing/relay_guard` 只做中转站扣费对账与共享凭据守卫；完整「项目累计总额 + 全部尝试计费」在 `model_spend/model_runtime/billing_quotes`（范围外），本组只见引用/预留。
- **真实 0.85 一致性 / 六篇博士质量论文**：README 自述「仍需实际研究验收」；`public_review_anchors` 报告 `human_claim_sample_agreement:None`、`numeric_score_calibration_verified:False`。
- **独立模型审计 / 引用数值核验（G5）**：本组提供的是 `pre_submission_review/ref_verify_adapter/reporting_checklist/publication_disclosure` 等**确定性**检查；「独立模型审计」实体在 `review_receipts/review_panel/api_orchestrator`（范围外）。
- **Claude 只读 / OpenAI 写持久产物**：本组多为确定性只读校验与本地渲染（`family="other"`），writer 与 orchestration 不在本组，规则一致但写入者实体未在本组出现。
- **PaperQA2 / 37 类绘图等 NEW-CAPABILITIES**：`production_readiness.upstream_paperqa_sdk` 只是状态字符串，`paper_qa` 明确 `not_paperqa2_sdk:True`。

### 3.6 名实不符 / 需正名处
- `paper_qa.py` ≠ PaperQA2 SDK（`not_paperqa2_sdk:True`，确定性词法检索）。
- `publication_figures --reuse-panels` 已退役却保留参数（"Retired optimization; renders the full figure"）。
- `paper_reader.reusable_reader` 定义未接线。
- `quality_gate.py` 名含 gate，但分数/Q1-Q2/IF 全是 advisory observation，不作阻断闸门。
- `pre_submission_review.py` "never an acceptance score"、`calibration_status:NOT_CALIBRATED`。
- `publication_disclosure.py` 名含 disclosure，却明确 `journal_ai_policy_evaluated:False`（不评估期刊 AI 政策）。
- `production_readiness.py` 自述「目录访问只认证元数据，不证明模型真实性」。
- `relay_billing.settle` 明确「settle 不接受模型身份/内容/科学有效性」。
- `research_improvementctl.py` 名 "improvementctl"，实为 28-action 通用云端 builder 分发器。
- `research_case.export` 的 preprint/rebuttal/retarget/reproduction 均为**本地发布材料准备**，`external_publication:False`，绝不自动投稿/上传。

---

## 4. 结论

本组是 Doctoral Research OS 的「**证据与信任内核**」：以 `research_artifacts` 为原语、`paper_execution` 为作用域、`output_provenance` 为来源裁判，把 G0–G5 的记录逐字段哈希绑定、失败留痕、角色隔离、预算/凭据守卫，并用本地确定性渲染（图表/图/ PPT/发布包）替代「模型写最终产物」。整体**零自动投稿、零科学结论自证、分数/分区/AI 政策一律不作闸门**，与 `AGENTS.md` 高度一致。最需警惕的是：大量历史/配置被硬编码进 `relay_guard`、`public_review_anchors`、`relay_billing`；真实付费/网络调用集中在 7 个点且严格门禁；最关键的三家族 panel、累计预算主控、writer/critic 实体均在范围外，本组只提供编排与校验——因此「工程校验通过」绝不等于「科研完成」，这一点在几乎每个文件的回执常量中被反复声明。
