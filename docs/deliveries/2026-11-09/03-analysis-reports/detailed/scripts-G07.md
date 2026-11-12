# Doctoral Research OS v2.3.0 — scripts 精读报告 G07

> 精读范围：`D:/ad/lunwen/scripts/` 下，按 Python `sorted()` 文件名字母序，从 `research_increments.py` 起、到 `review_panel.py` 止（含两端）的全部 `.py` 文件。
> 阅读方式：先 `ls -1 | sort` 列目录并筛选；对 16 个文件逐一用 Read 工具**完整打开**；超过 500 行的文件按 ≤500 行分段读完，未使用 grep/关键词摘要代替通读。
> 规则基线：`AGENTS.md`（30 条运营规则）、`README.md`（v2.3.0 说明）已读，不计入精读范围。
> 纪律：全程只读 `D:/ad/lunwen`，未修改仓库内任何文件；唯一写入为本报告文件。

## 0. 范围核对与行数

`ls -1 | sort` 结果中，按 Python `sorted()`（注意 `'_'`(95) < `'c'`(99)，故所有 `research_*.py` 排在 `researchctl.py` 之前）落在此区间的 `.py` 恰好 16 个，`wc -l` 合计 **8578 行**，与任务描述完全一致。

| # | 文件 | 行数 | 分段阅读 |
|---|---|---:|---|
| 1 | `research_increments.py` | 545 | 1–500 / 501–545 |
| 2 | `research_iteration.py` | 540 | 1–500 / 501–540 |
| 3 | `research_mcp.py` | 89 | 1–89 |
| 4 | `research_methods.py` | 270 | 1–270 |
| 5 | `research_notebook.py` | 389 | 1–389 |
| 6 | `research_operations.py` | 134 | 1–134 |
| 7 | `research_phase.py` | 436 | 1–436 |
| 8 | `research_quality.py` | **2591** | 1–500 / 501–1000 / 1001–1500 / 1501–2000 / 2001–2500 / 2501–2591（6 段） |
| 9 | `research_search_tree.py` | 198 | 1–198 |
| 10 | `research_support.py` | 623 | 1–500 / 501–623 |
| 11 | `research_task_acceptance.py` | 113 | 1–113 |
| 12 | `research_toolkit.py` | 195 | 1–195 |
| 13 | `researchctl.py` | 720 | 1–500 / 501–720 |
| 14 | `results_validation.py` | 373 | 1–373 |
| 15 | `review_packets.py` | 556 | 1–500 / 501–556 |
| 16 | `review_panel.py` | 806 | 1–500 / 501–806 |

**统一模式**：本组几乎全部为「确定性控制平面」代码——大量 `sha256` 哈希绑定、`output_provenance.current_origin` 来源校验、`record()` 失败留痕、`@paper_scoped` 论文隔离，以及成片的 `scientific_completion_verified=False` / `gate_approved=False` / `paid_calls=0` / `gate_authority=False` 声明式不越权标记。**只有 `review_panel.run()` 发生真实付费模型 API 调用，只有 `research_support.fetch_sources()` 发生真实公网 HTTP GET**；其余「运行」均为只读重算、本地子进程或纯元数据分发。

---

## 1. 逐文件精读

### 1.1 `research_increments.py`（545 行）

**职责**：「八组科研增量」（`GROUPS = arguments / lineage / gaps / ingestion / lessons / dependencies / voices / editing`）的计划装载、审计构建、交接、冻结与 G5 闸门错误。对应 `docs/RESEARCH-INCREMENTS.md` 与 README「八组科研增量」。

**对外能力**（纯库函数，无 `main`）：
`initialize`、`load`、`implementations`、`scientific_spec`、`context_dependencies`、`paper_review_binding`（`@paper_scoped`）、`scientific_audit`、`confirmation`、`prepare_confirmation`、`dependencies`、`build`、`handoff`、`refresh`、`freeze_plans`、`freeze`、`record_editing_attempt`、`prompt_feedback`、`gate_errors`（`@paper_scoped`, `gate="G5"`）。

**输入/输出**：
- 输入：`program/research-increments.json`（PLAN，schema 1.0，每组 ≤200 行、ID 唯一、`required_at_submission` 必须含 `arguments`+`lineage`）、`state/research-increment-confirmations/{voice,lesson}-*.json`、`reports/research-increments/audit.json`(REPORT)、`state/run.json`、`state/model-spend-control.json`、`program/novelty-claim-matrix.json`、`papers/Pxx/reviews/paper-facts.json`、`experiments/runs/<id>/run.json`。
- 输出：`reports/research-increments/audit.json`、`handoff.json`、`context-summary.json`、`reports/research-increments/rule-evaluations/*.json`、`editing-history/*.json`；`prompt_feedback()` 返回紧凑 JSON 字符串（voice 样本文本标注 `untrusted_style_data`，截断 12000 字符）。

**关键机制**：
- **哈希绑定与实现自校验**：`implementations()` 对本文件及 `incremental_evidence / incremental_writing / incremental_rules / evidence_context / source_scope / research_artifacts` 共 7 个模块逐一 `sha()`；`build()` 产出 `plan_sha256`、`scientific_plan_sha256`（`digest(scientific_spec(spec))`）、`implementation`。任何实现文件变动都会使既有确认/审计失效。
- **人工决策边界**：`prepare_confirmation()` 仅允许 `voice→authorize_sample`、`lesson→adopt_rule/rollback_rule`；`confirmation()` 要求同时满足 `spec_sha256==digest(spec)`、`implementation==implementations()`、`confirmed_by`、`source_run_id`、`cloud_review_sha256` 非空，且 `output_provenance.current_origin` 为 `tracked` + `provider=="deterministic-cloud-human-control"`。
- **C 类观察隔离**：`OBSERVATIONS={"voices","editing"}`；`scientific_spec/scientific_audit` 将其从「科学部分」中剔除；`gate_errors` 对这两组不计入阻断。
- **依赖 DAG**：`dependencies()` 校验节点 `kind`（8 类）、每个 `source` 必须恰为 `{path,sha256}` 且文件哈希匹配、`result/failure` 节点必须匹配 `primary_attempts()` 真实回执且 `experiments/runs/<id>/run.json` 与登记一致、结果节点必须是完整性通过的确切输出、跨论文共享资产需 `reuse_disclosure` 且 `independence_status` 只能 `not_assessed/shared_evidence`、环检测、`stale` 沿父节点传播；`independence_verified=False` 恒不宣称。
- **所有权稳定**：`build()` 在 `enabled(project)` 时从既往审计继承 `paper_owners`，`ownership_changed` 直接记 error（防静默换论文归属）。
- **来源校验**：`build()` 若 REPORT 已存在，要求 `current_origin` 为 `tracked`+`deterministic-control-plane`，否则报「audit is stale or lacks control-plane provenance」；`gate_errors(G5)` 还比对保存审计的 `scientific_audit` 与重算一致。
- **预算/交接**：`handoff()` 只读 `model_spend.read`，产出 CNY 成本对象（`authorized_ceiling_cny / spent_cny / pending_reservations / remaining_after_reservations / billing_reconciled`），`amount_basis="persisted estimates; provider invoice controls final billing"`；明确「no invented completion percentage or ETA」，`scientific_completion_verified=False`。
- **零模型调用**：`build()` 固定 `model_calls=0`。

**依赖模块**：`incremental_evidence`（DIGEST/digest/gaps/ingest/lineage/primary_attempts/rows/strings/text）、`research_artifacts`（path_in/read/record/sha/write）、`paper_execution`（enabled/paper_scoped/selected）、`incremental_writing`、`incremental_rules`、`output_provenance`、`model_spend`。
**边界限制**：不制造审批、不替代各阶段既有科学合同；`freeze_plans` 注明「called by the trusted writer boundary before the initial paid write」；`record_editing_attempt` 只在 writer 边界记录一次。

---

### 1.2 `research_iteration.py`（540 行）

**职责**：「Source-bound experiment feedback and bounded proposals; never execute or approve.」——把已登记实验回执重算为只读反馈报告与有界工作清单。

**对外能力**（无 `main`）：`refresh(project, request_file, root=ROOT)`、`model_context(project, report_relative, role, root=ROOT)`；内部 `_request/_prepare/_prepare_request/_report/_validate_origin/_phase_and_replication/_configuration/_diagnostics/_run_refs/_time/_ids`。

**输入/输出**：
- 输入：`program/research-iteration-*.json`（≤64KB，`kind=research_iteration`、小写 id、`run_ids`/`hypothesis_ids` 选择器、`max_items` 1–20）、`state/run.json`、`intake/constraints.json`、`experiments/plan.json`、`budget.json`、`registry.jsonl`、`program/hypothesis-register.json`、`papers/Pxx/preregistration.json`、各 `papers/Pxx/experiments/*.json`、`primary_recovery` 的历史归档与回执、stdout/stderr 日志。
- 输出：不可变报告 `reports/research-iteration/<id>-<report_sha256>.json`（`OUTPUT`），含 `source_bindings`、`module_bindings`、`attempts`、`equivalent_configurations`、`similar_past_lessons`、`hypotheses`、`next_iteration_worklist`；`paid_calls=0 / experiments_executed=0 / scientific_validation="not_assessed" / status="prepared_not_executed"`。

**关键机制**：
- **封存阶段不可被当前设计重标**：`add_plan()` 只接受 `G3` approval 中 `experiment_plan_sha256==sha(plan)` 且 `frozen_protocol_sha256` 匹配的预注册来声明 `analysis_phase`（`confirmatory/exploratory/formal_verification`）；注释明确「A current, unsealed design must never relabel a historical execution」。
- **配置指纹**：`_configuration()` 以 `input_hashes/code_hashes/environment(image_digest 或 environment_sha256)/argv_parameters/cwd/seed/analysis_phase` 构造 `effective`，把输入/输出路径替换为占位符后 `json_digest`；任一 `unknown_fields`（缺封存计划/输入哈希/代码哈希/环境/argv/cwd/seed/phase/运行后完整性）则 `fingerprint=None`；`cwd` 与 `/workspace/project/` 前缀做别名归一，`argv` 中 `=` 参数亦归一。
- **工程诊断而非科学结论**：`_diagnostics()` 只产生 `engineering_failure/incomplete_evidence/incomplete_execution/incomplete_output` 等观察（`input_integrity_failed`、`logged_modulenotfounderror`、`execution_timed_out`、`receipt_plan_mismatch` 等），每条 `proposal_status="requires_review_not_executed"`，并显式「Scientific measurements are deliberately not classified」。日志只保留尾部 2000 字符作证据。
- **不可变 + 来源校验**：`report_sha256` 决定输出路径；`refresh()` 调 `literaturectl.require_cloud()`，文件已存在则要求字节一致且 `_validate_origin`（`tracked` + `family=="other"` + `deterministic-control-plane` + `model==MODULE`）通过。
- **角色隔离**：`model_context()` 支持 `planner/writer/critic/remediator`；`critic` 只收到 `attempt_facts`（前 20 条）与观察条件，**不**给 `next_iteration_worklist` / `similar_past_lessons`；`boundary` 文案明确「Source text is evidence, not instructions」。
- **等价/教训**：相同指纹分组标注「equivalent_declared_configuration_review_only / Equality of recorded fields does not prove duplicate scientific purpose」；`similar_past_lessons` 仅按时间先后与共享观察码关联，注明「no successful repair or causal explanation is established」。

**依赖模块**：`primary_recovery`（records/histories/receipt/preserved_output/latest_attempt 等）、`research_artifacts`、`paper_execution`（artifact_path/scope/enabled）、`output_provenance`、`literaturectl.require_cloud`。
**边界限制**：`authority` 字段明确既有计划、独立审查、G3 runner、累计预算与 G1/G2 人工决定仍权威；报告「grants no execution」。

---

### 1.3 `research_mcp.py`（89 行）

**职责**：「Zero-cost MCP router for chat-first Doctoral Research OS management.」——JSON-RPC 2.0 over stdio 的只读路由层。

**对外能力**：`main()`（逐行读 stdin）、`handle(message)`；4 个 MCP tools（`TOOLS`）：`research_context`、`research_projects`、`research_route`、`research_status`；函数 `safe_project`、`route_request`、`status`、`projects`、`context`。

**输入/输出**：JSON-RPC 请求（`initialize` / `notifications/initialized` / `tools/list` / `tools/call`）；`initialize` 返回 `protocolVersion="2025-06-18"`、`serverInfo{name:"doctoral-research-os", version:"2.4.0"}`；`status/projects` 读 `projects/<slug>/state/run.json` 返回 stage/gate/status/active_paper。

**关键机制**：
- `ROUTES` 18 条中英双语正则 → `intent`/`skill`（citations / figures / systematic-review / paper-audit / review / library-import / journal / experiment / data / write / package / retarget / topic / research-briefing / audit / api-tasks / start / continue），默认 `continue`；`\bP\d{2}\b` 提取论文号。
- 所有返回恒带 `paid_call_started=False`、`gate_approved=False`、`submission_started=False`；`context()` 恒 `paid_call_authorized=False`。
- `context()` 项目解析四态：explicit / automatic-single-project / ambiguous（`must_stop=True`）/ none（`initialization_required=True`）；按 `state.status` 给 `next_action`，`awaiting_approval` 且 `gate∈{G1,G2}` 时 `must_stop=True, human_action="approve-topic-or-revise"`。
- `safe_project()` 用 `[a-z0-9][a-z0-9-]{1,62}` 校验 slug；`projects()` 跳过非法目录名。

**依赖**：标准库 `json/re/sys/pathlib`。**边界限制**：纯路由，绝不执行付费调用、闸门或投稿。
**标注**：`serverInfo.version="2.4.0"` 与仓库/README 的 **v2.3.0 不一致**（版本硬编码、名实不符）。

---

### 1.4 `research_methods.py`（270 行）

**职责**：「Load reviewed, stage-scoped research methods without provider calls.」——加载并校验已审查、阶段限定的研究方法，拼装模型上下文。

**对外能力**：CLI `--validate` / `--stage` / `--role(planner|writer|critic)`；函数 `pinned_text_sha256`、`safe_path`、`load_catalog`、`installation_errors`、`peer_review_method`、`peer_review_context`、`venue_fit_context`、`stage_context`、`load_vendored_module`。

**输入/输出**：
- 输入：`config/research-methods.json`（模块目录）、`integrations/vendored-research-methods.json`（文件清单+SHA）、`integrations/upstreams.lock.json`（源/commit 注册）、`third_party/kdense/skills/peer-review/SKILL.md`、`config/scientific-reasoning` 策略、`papers/Pxx/venue.json` 与 `research-case.json`。
- 输出：向 stdout 打印 `stage_context()` 拼出的大段提示词（多段 `blocks` 以空行连接）；`--validate` 打印 `{pass, errors}` 并以退出码 2 表示失败。

**关键机制**：
- **完整性校验**：`pinned_text_sha256()` 先把 CRLF 归一为 LF 再哈希（对齐 Git 规范）；`installation_errors()` 校验 `source_ids` 已注册、每个 vendored 文件哈希与 source_repository/commit 匹配、每个 `module` 哈希、`scientific_reasoning.load_policy`；`safe_path()` 拒绝绝对路径、`..`、隐藏路径、符号链接、逃逸 root。
- **阶段/角色限定加载**：`stage_context()` 先 `installation_errors`（有错即抛），再拼 `ccfa_runtime.model_contract` + `research_phase.stage_rules`；`writing-and-review` 且（critic 或含 peer-review/submission-review/pre-submission-checklist 标记）时插入 `peer_review_context`；`paper_execution.prompt_contract`；仅当 `module["id"] in context or module["path"] in context or "full-method-review" in context` 才加载**完整方法正文**，否则只列 `available`（明确「not loaded」索引）；`research_toolkit.task_context`；`experiment-execution` 加 `primary_recovery.diagnosis_context`（失败实验包，附带 `retire_primary_plan` 操作提示，强调不得改写冻结输入/隐藏失败/授权花费）；`writing-and-review` 加 `venue_fit_context` 与 `contribution_reporting.feedback`。
- **K-Dense 抽取而非执行**：`peer_review_method()` 从 pinned SKILL.md 按 `### N. title` 切出完好章节（含 stop 串截断），声明「PRIMARY PEER-REVIEW METHOD ... ARS questions supplementary」、`upstream intake / licence/research-use / venue AI-policy gates are not adopted`。
- **venue fit**：`venue_fit_context()` 用 `research_case._venue_sources` 绑定官方来源，逐 `VENUE_FIELDS` 产出 `bound_official_source` 或 `unknown`，明确不新增付费 pass/分数阈值/C 类闸门、不得发明 target/venue。
- **受控动态导入**：`load_vendored_module()` 仅导入清单内且哈希未变、路径在 `integrations/codex-research-tools/skills/` 的 helper，用 `importlib.util.spec_from_file_location`，模块名由路径哈希派生。

**依赖**：`scientific_reasoning`、`research_artifacts.sha`、`ccfa_runtime`、`research_phase`、`research_case`、`paper_execution`、`primary_recovery`、`research_toolkit`、`contribution_reporting`。
**边界限制**：无 provider 调用、不执行上游工作流、不新增付费审查层。

---

### 1.5 `research_notebook.py`（389 行）

**职责**：「Incremental question-centred evidence and decision views; never invent evidence.」——以「问题」为中心的证据/决策台账与循环决策链。

**对外能力**：`failed_memory`、`build`、`cycle_prompt`、`cycle_review`、`cycle_assessment`、`_historical_assessment`、`_delta`、`daily_brief`、`refresh`。

**输入/输出**：
- 输入：`program/research-notebook.json`（NOTEBOOK）、`state/run.json`、`reports/research-notebook-history.jsonl`、`review_receipts` 的 observation/latest、`review_panel.PREFIX/<paper>/latest.json`、`reviews/independent` 审计文件、`api_orchestrator` 的处置说明。
- 输出：`reports/research-notebook.json` + `.md`、`reports/research-notebook-history.jsonl`（schema 2.0 事件，`event_id=sha256(event)`）、`reports/research-notebook-daily/<date>.json` + `.md`；`daily_brief` 默认时区 `Asia/Shanghai`。

**关键机制**：
- `build()`：`bound_source` 哈希绑定每条证据；`stance∈{supports,contradicts,mixed,unknown}`、`read_scope∈{metadata,abstract,fulltext,experiment}` 必须诚实；决策必须链接真实 `evidence_ids`（含反证，省略反证需 `contrary_evidence_rationale`）、必填 `failure_condition`/`stop_rule`；允许诚实 `pending/unchanged`（配合 `missing_evidence`），但不得虚构结果；`input_fingerprint`、恒 `gate_approved=False`、`interpretation_verified=False`。
- `failed_memory()`：把 `failed/stopped` 决策作为「prior_attempt_lead_not_scientific_fact」，拒绝 `state/`、`reviews/`、`reports/`、`program/` 及 notebook 自身作为科学断言来源，并要求 `output_provenance` 为 `tracked` + `deterministic-control-plane` 或 `human-attestation`；`model_call_made=False`。
- `cycle_review()`：校验本轮 `cycle_id` 决策，`scientific_reasoning.concrete` 具体性、stage/paper 绑定，禁止引用自身 notebook / 控制回执；输出 `status="recorded_requires_independent_review"`。
- `cycle_assessment()`：串接 `review_receipts.observation` / `review_panel.responses` / 最新 final receipt，产出 `independently_observed` / `independently_reviewed` / `recorded_with_limited_panel_observations` / `historically_reviewed`；恒 `current_stage_authorized=False, gate_authority=False`；`review_receipts.validate_gate` + `source_matches` 校验来源未变。
- `_historical_assessment()`：控制器切换后读过去工作（G5 scientific-writing 完成 / G4 archived exploration），校验 initial+final invocation 一致、`researchctl.audit_document_valid`、`api_orchestrator.validate_remediation_notes`、无 `unresolved:` findings；`scope` 仅 `completed_scientific_writing` / `archived_exploration`。
- `_delta()`：前后快照差异分类（questions/evidence/decisions 增改删、missing 增删、conflicts 新增/清除待复核）。

**依赖**：`research_artifacts`、`scientific_reasoning`、`literature_workbench._id`、`review_receipts`、`review_panel`、`research_phase`、`researchctl.audit_document_valid`、`api_orchestrator.validate_remediation_notes`、`paper_execution`、`output_provenance`。
**边界限制**：`resolution_verified=False`、`independent_scientific_review_required=True`；「Removed evidence or a cleared conflict is not proof of resolution」。

---

### 1.6 `research_operations.py`（134 行）

**职责**：「Allowlisted operation metadata shared by cloud transport and execution.」——纯元数据/分发表（无 `main`、无 CLI）。

**对外能力**：`Request`（frozen dataclass，`__call__` 动态 `import_module('scripts.'+(module or action)).refresh`）、`OPERATIONS`（约 50 项）、`FIELDS`、`AUTOMATED_OPERATIONS`、`handler(action)`、`BUILDERS`（约 20 项）、`CLI_ALIASES`、`invoke_builder`、`run_builder`。

**输入/输出**：`operation` 字典（`action` + 允许字段）；`Request.__call__(project, operation)` 调对应模块 `refresh()`；`run_builder` 按 `(allowed_stages)` 过滤阶段后执行 `BUILDERS[action]` 指定的 `module.func(project, *fields)`。

**关键机制**：
- `OPERATIONS[name] = (allowed_fields, required_fields[, Request])`，覆盖 `scientific_judgment / research_case / literature_* / ccfa_* / data_row_* / figure_* / diagram_mermaid` 等；`Request` 支持 `default`（默认 request 路径）、`keyword`、`task`、`execute=True`（显式布尔）。
- `AUTOMATED_OPERATIONS = set(OPERATIONS) - {"literature_feedback_review"}` —— 唯独文献反馈复核保留人工。
- `BUILDERS` 把 `research_notebook.refresh`、`research_support.refresh/fetch_sources`、`review_packets.refresh`、`research_increments.freeze`、`cloud_runtime.compile_tex`、`word_render.render`、`statistical_reporting` 等映射到允许阶段；`CLI_ALIASES` 含 `notebook / daily-brief / statistics / word-revision / journals / method-contracts`。
- `run_builder()` 对 `stage=="intake"`（specification[0] is None）与阶段不匹配返回 `False`（不执行）。

**依赖**：`importlib.import_module`（运行时动态导入 `scripts.*`）。
**边界限制**：本身不执行科研，只是白名单 + 字段级校验 + 阶段门控的分发元数据。
**风险标注**：动态 `import_module` 拼 `action` 为模块名，虽 `action` 来自 `OPERATIONS`/`BUILDERS` 白名单键，仍是可控的代码加载面（见 §5.3）。

---

### 1.7 `research_phase.py`（436 行）

**职责**：「Research intensity within native paper plans and G3/G4 state transitions.」——探索/确证研究强度、写作阶段判定、G3/G4 状态转换。

**对外能力**：`phase`、`exploratory`、`writing_phase`、`requires_submission`、`disposition_stage`、`writing_contract`、`stage_rules`、`submission_only`、`enter_submission`、`plan_errors`、`histories`、`historical_cost`、`exposure_errors`、`design_errors`、`preregistration_inputs`（`@paper_scoped`）、`exploration_execution`、`build_report`（`@paper_scoped`）、`archive_and_reopen`。

**输入/输出**：
- 输入：`experiments/plan.json`（`research_phase`）、`state/run.json`（`writing_phases / paper_statuses / approved_gates / approvals / history`）、`papers/Pxx/paper-contract.json`、`preregistration.json`、`experiment-evidence.json`、`experiments/history/exploration-*/manifest.json`、`data/datasets.jsonl`。
- 输出：`writing_contract`/`stage_rules` 返回提示词字符串；`enter_submission()` 写 `state/run.json`（`writing_phases[paper]="submission"` + `history` 事件 `submission_preparation_started`, `decision_type="automated"`）；`archive_and_reopen()` 写 `experiments/history/exploration-<paper>-<hash>/` 归档 + 重置 `state/run.json` 到 `stage_index=3 / stage="experiment-design" / gate="G3"`，并 `unlink` 旧 registry/preregistration/evidence/quality 报告；`build_report()` 返回探索观察清单。

**关键机制**：
- **阶段判定**：`phase()` 只接受 `exploratory/confirmatory`；`writing_phase()` 依 `writing_phases` → `contract.writing_phase` → 由 `stage=="submission-ready"` / `paper_statuses` / `approved_gates` / `approvals` 推断 `scientific|submission`；`disposition_stage()` 把非投稿的 writing 归为 `scientific-writing`；`requires_submission()` 仅 writing-and-review 且 `proposal_pending` 为假且 `writing_phase=="submission"`。
- **唯一显式机器转换**：`enter_submission()` 要求 `errors == [SUBMISSION_PENDING]`、`!requires_submission()`、`gate=="G5" && status=="awaiting_work"`，写自动化 history，弹掉 `ready_gate/ready_artifact_sha256`。
- **规则绑定**：`stage_rules()` 拼接 `scientific_reasoning.load_policy` 的 `common/roles/stages/phases`，并在头部附 `policy` 文件的 SHA-256，明确「One config-bound scientific rule block」。
- **探索不可冒充确证**：`plan_errors()` 要求 exploration 声明 `unknown/discriminating_test/continue_if/revise_if/stop_if/claim_limit/prior_outcomes_seen`；`histories()` 校验 `exploration_completed` 事件的 archive binding、`current_origin`（`tracked` + `deterministic-control-plane` + `model=="scripts/research_phase.py"`）与每个归档文件哈希；`exposure_errors()` 要求新协议保留全部 `prior_exploration` 绑定、`prior_outcomes_seen=true`、新 run ID/output（「exploration cannot be relabeled as confirmatory evidence」）；`design_errors()` 校验最小探索的数据权利、精确输入哈希、dataset manifest、原始哈希非 `pending`、budget authority。
- **失败留痕**：`exploration_execution()` 从真实 registry 派生 `observations/unexecuted_runs/pending_run_ids`，失败前置只阻断其后代，未执行后代无合成 registry entry 或成本；`build_report()` 要求 G3 `experiment_plan_sha256` + `frozen_protocol_sha256` 精确封存、registry 回执与 `run.json` 一致、`input_integrity.passed && verified_after_run`、`status=complete` 否则 blocked。
- **归档不可变**：`archive_and_reopen()` 若 `experiments/history/exploration-<paper>-<sha16>` 已存在则拒绝（「exploratory history is immutable; use a new protocol」），要求 `status=="approved"` 的探索性 G4、无未决 `experiment-execution-lease.json`。

**依赖**：`paper_execution`、`scientific_reasoning`、`research_artifacts`、`supplemental_experiments`、`experiment_runner`、`research_quality`、`dataset_fetch`、`results_validation`、`primary_recovery`、`output_provenance`。
**边界限制**：「Exploration records observations without granting confirmatory evidence. Writing intensity uses the existing paper contract; neither mode creates authority.」；`archive_and_reopen` 的 `unlink` 作用于 `projects/<slug>/` 下的运行产物，非仓库源码。

---

### 1.8 `research_quality.py`（2591 行，本组最大）

**职责**：「Evidence-bound novelty, data-quality, power and reproducibility controls.」——G1 新颖性、G3/G4 数据质量/功效/预注册/复现的核心确定性闸门。文档字符串明确「The mandatory validators are dependency-free ... a model-authored assertion never substitutes for a local file hash or a successful experiment-registry entry」。

**对外能力（CLI 子命令，`parser()`/`main()`）**：`novelty-check --for-gate`、`data-audit`、`confirm-data-quality`、`power`、`simulation-power`、`freeze --all/--paper`、`validate --stage auto|g3|g4`、`environment-digest`、`runtime-catalog`、`confirm-reproduction`。
库函数主要：`_load_json/_project/_safe_path/_text/_string_list/_paper_ids/_manifest_map/_registry`、`_saturation_executions`、`validate_novelty_claim_matrix`、`_iter_rows/_row_key/_split_from_path/_tabular_profile/_cross_split_overlap/_profile_non_tabular`、`create/validate_data_quality_report`、`create/validate_data_quality_confirmation`、`optional_tool_status`、`create/validate_power_report`、`create_simulation_power_report`、`_preregistration_inputs`、`create/validate_preregistration`、`_successful_runs/_planned_reproduction/_selected_attempts/_attempt_output_pairs/_validate_evidence_files/_validate_comparison_values`、`validate_baseline_reproduction`、`validate_clean_room_reproduction`、`create/validate_reproduction_confirmation`、`registry_environment_digest`、`refresh_runtime_evidence_catalog`、`validate_g3_quality`、`validate_g4_quality`、`quality_summary`、各 `_cmd_*`。

**输入/输出（路径/schema）**：
- 输入：`program/novelty-claim-matrix.json`（schema 1.0/1.1）、`program/originality-audit.json`、`evidence/search-log.jsonl`、`evidence/literature-api-ledger.jsonl`、`data/datasets.jsonl`（dataset manifest）、`data/quality/<id>.json` 与 `<id>-confirmation.json`、`papers/Pxx/power-analysis.json`、`preregistration.json`、`baseline-reproduction.json`、`clean-room-reproduction.json`、`reproduction-confirmation.json`、`papers/Pxx/experiments/*.json`、`experiments/plan.json`/`budget.json`/`registry.jsonl`、`papers/Pxx/paper-contract.json`。
- 输出：上述报告文件；`validate` 打印 `{stage,status:pass|block,errors,summary:quality_summary}`；`quality_summary()` 统计 novelty/matrix、已执行/已筛选检索、theme B 独立、venue 候选、data quality reports/confirmations、power/prereg/baseline/clean-room/reproduction confirmations 数量、`optional_tools`；`runtime-catalog` 写 `reports/runtime-evidence-catalog.json`。

**关键机制**：
- **检索饱和绑定真实执行**：`_saturation_executions()` 读 `literature_evidence.read_jsonl(evidence/literature-api-ledger.jsonl)`，要求每个 supporting search 有 `status=="success"` 的真实回执、`requested_at/completed_at` 为过去带时区时间；对 backward/forward chaining 校验 `mode=="citation_graph"`、`provider=="opencitations"`、`direction`、`request_url` 恰为 `https://api.opencitations.net/index/v2/<references|citations>/doi:<seed>`（**仅字符串比对，不发请求**）、raw edges 与 normalized works 的 DOI/direction/seed 一致；「Renaming the search-log ID cannot create another execution」——每轮 `search_ids` 必须映射到互不重复的真实 `receipt_id`。
- **novelty matrix**：≥5 `closest_prior_work`；每 claim ≥3 `closest_work_ids` 且必须已知；`claim/precise_difference/mechanism_or_rationale/falsification_test/expected_if_false/boundary_conditions/residual_risk` 全必填；`search_saturation.status∈{exploring,saturated,reopened}`，G1 要求 saturated；schema 1.1 需 `stopping_rule∈{coverage_assessed,budget_limit,time_limit}` 且保留 `unresolved_search_gaps`；`human_review_required=true` 恒。
- **数据质量**：`create_data_quality_report()` 拒绝符号链接，逐文件 `bytes+sha256` inventory，单表 CSV/TSV/JSONL 走 `_tabular_profile`（缺失/精确重复/常量列/标签失衡 >95%/split 泄漏/group 跨 split），多文件走 `_profile_non_tabular`（Pillow 图片 `verify()`、`wave` WAV、NumPy `allow_pickle=False`、h5py、pyarrow，记录 handler/version）；`canonical_match` 要求与 manifest `download.sha256` 一致（derived 数据需 `provenance.transformations`）；`generated_by="deterministic_local_control_plane"`；`human_review_required=False` 但 `validate_*` 兼容旧策略为 bool。确认分 `automated`（`confirmed_by="deterministic_control_plane"`、`unresolved_warning_count`）与具名人工（`reviewed_warning_count`），严禁 automated 冒充人工。
- **功效分析**：`create_power_report()` 锁定 `statsmodels==0.15.0`（`REVIEWED_STATSMODELS_VERSION`），5 种方法 `ttest_ind/ttest_paired/ttest_one_sample/anova/proportion_ind`，`bound_files` 绑定 contract+designs 哈希。`create_simulation_power_report()` **真实本地重跑**：`subprocess.run([sys.executable,"-I",script], cwd=临时干净目录, env=精简白名单, stdin=DEVNULL, timeout=300s)` 共 2 次，要求输出 JSON ≤16MiB、非符号链接、两次规范 JSON 与 `evidence_value` 逐字节一致，`rejection_count/simulation_count==achieved_power`、`generated_by_script_sha256` 匹配脚本、`random_seeds` 非空整数数组；`validate_power_report()` 复核 `rerun_receipts` 恰 2 条且 `output_sha256` 全等、`clean_working_directory/sanitized_environment=true`、`bound_files` 哈希未变。
- **预注册冻结**：`create_preregistration()` 若 `experiments/registry.jsonl` 非空则拒绝（「cannot freeze after experiment attempts exist」）；empirical 需有效 power report + 每数据集 data-quality report + confirmation；`files` 为 `_preregistration_inputs()` 的 `sorted(set(inputs))` 逐哈希；`validate_preregistration()` 校验 `confirmatory_lock`（探索分支为 `protocol_lock`）、`human_confirmation` 与 `confirmation_kind="automated"` 的一致性、`frozen_by`、`deviation_policy`、每个文件当前哈希、以及 `expected - recorded` 无遗漏。
- **复现**：`_planned_reproduction()` 从 G3 冻结的 `experiments/*.json` 读 `domain_standard/strong_recent/original/clean_room` run IDs、`metric_tolerances`、`baselines` 的 `primary_source_url`；`validate_baseline_reproduction()` 要求两类 baseline、`reference_source_url` 必须 `https://`、`comparable_protocol/within_tolerance=true`、数值差在预声明容差内、evidence_files 恰为所选成功 attempt 的输出；`validate_clean_room_reproduction()` 要求 original/reproduction run 不相交、`executor_isolation` 的 `kind=container / isolated_executor / network_disabled / read_only_root / image_digest(64hex)`、`instance_id` 不相交、`registry_environment_digest` 与原/复现环境摘要一致且二者不同、`source_commit` 匹配所有选中 run、`metric_comparisons` 恰好覆盖预声明容差。
- **环境摘要**：`registry_environment_digest()` 刻意排除 run/attempt 标识，只哈希 `git_commit/cwd/runtime/executor_isolation_environment`，「differently named attempts in the same checkout/runtime must have the same digest, rather than masquerading as isolated reproductions」。
- **G3/G4 汇总**：`validate_g3_quality()`（探索走 `design_errors`；否则数据质量报告+确认、experiment-evidence-plan、power、preregistration、study_routes.plan_errors）；`validate_g4_quality()`（探索走 `experiment_evidence.validate_report`；否则 experiment-evidence + prereg + baseline + clean-room + reproduction-confirmation）。

**依赖模块**：`research_artifacts`、`paper_execution`、`literature_evidence`、`research_phase`、`study_routes`、`experiment_runner`、`experiment_evidence`、`results_validation`、`primary_recovery`、`empirical_workflow`、`dataset_fetch`；**可选第三方**：`statsmodels==0.15.0`、`Pillow`、`numpy`、`h5py`、`pyarrow`（`optional_tool_status` 另探测 `fg-data-profiling/pandera/evidently/dvc/tooluniverse/paper-qa`）。
**边界限制**：未知/不可读格式一律 blockers；「Unknown or unreadable formats are blockers. The function never uploads data」；`--max-rows` 必须为正；`validate` 有错以退出码 2 结束。

---

### 1.9 `research_search_tree.py`（198 行）

**职责**：「Receipt-bound experiment search views; no search agent, execution or selection.」——基于 `research_iteration` 报告的只读搜索树声明视图。

**对外能力**：`refresh(project, request_file, root=ROOT)`、`model_context(project, relative, role, root=ROOT)`；内部 `_prepare/_origin/_id`。

**输入/输出**：请求 `program/research-search-tree-*.json`（`kind=research_search_tree`、`nodes` 1–50、`max_items` 1–20、`max_debug_depth` 1–10、`iteration_report` 指向不可变迭代报告）；输出 `reports/research-search-tree/<id>-<sha>.json`，含 `nodes`（facts）、`root_ids/leaf_ids`、`worklist`、`paid_calls=0 / experiments_executed=0 / gate_approved=False / automatic_selection_or_pruning=False / scientific_completion_verified=False`。

**关键机制**：`_prepare()` 先调 `iteration.model_context(project, report_path, "critic", root=root)` 校验全部来源/模块/provenance 绑定而不写；node 字段白名单、`branch_kind∈{root,debug,variation}`、root 与 parent_id 互斥一致、跨 paper scope 禁止、debug 必须有真实 `engineering_failure/incomplete_execution`（「never a weak score」）、`consecutive_debug_depth` 达上限标记、`retired` run 需精确历史 attempt + sealed plan（哈希匹配）；`status="executed_<status>_pending_scientific_review" / "attempt_not_selected" / "planned_not_executed"`；`workflow_phase_verified=False`、`scientific_validation="not_assessed"`、`selected_by_metric=False`。`_origin()` 要求 `tracked` + `model==MODULE` + `deterministic-control-plane`；`model_context` 中 `critic` 不收 `worklist`、剔除 `declared_workflow_phase`。

**依赖**：`research_iteration`、`research_artifacts`、`paper_execution`、`output_provenance`、`literaturectl.require_cloud`。
**边界限制**：boundary 文案「Declared ancestry is not a repaired-bug, novelty, scientific-quality, or execution-approval verdict. Retain all failed, negative and independent replication paths.」

---

### 1.10 `research_support.py`（623 行）

**职责**：「Question clarification, primary-method dissection and honest FAIR metadata.」——从真实来源锚点构建审阅辅助；**本组唯一真实公网 HTTP GET 出口**。

**对外能力**：`fetch_sources`（有 `fetcher` 可注入，便于测试）、`audit`、`refresh`、`validate_saved_report`；内部 `_timestamp/_text/_strings/_url/_requests/_origin/_receipt/_anchor/_statement/_clarification/_number/_arithmetic/_worked_example/_method/_contains/_datasets/_availability`。

**输入/输出**：
- 输入：`program/research-support.json`（INPUT，`schema_version=1.0`、`metadata_sources` ≤80 条、`clarifications` ≤30、`method_dissections` ≤80、`data_availability` ≤80）、`data/datasets.jsonl`、`evidence/support-sources/index.json`（INDEX）、各 `evidence/support-sources/<sha>.txt` 与 `.response.txt`、`papers`/`evidence` 下的来源文件、独立 JSON 计算记录。
- 输出：`reports/research-support.json`（OUTPUT）；`fetch_sources()` 写 INDEX 与盲化元数据文本 + raw 响应；`audit()` 产出含 `source_bindings`（递归收集所有 `{path,sha256}`）、`pending_inputs`、`errors`、`status∈{blocked,pending_inputs,needs_scientific_review}` 的结构。

**关键机制**：
- **URL 白名单（SSRF 防护）**：`_url()` 基于 `network_safety.validate_https_url`，拒绝 `localhost` / `.local` / `.localhost`、非 `{None,443}` 端口、`ipaddress` 判私有/保留地址、query 中含 `token/key/secret/password/authorization/signature` 参数、`api.openai.com` / `api.anthropic.com`、以及 `.pdf/.zip/.gz/.tar/.csv/.tsv/.parquet/.h5/.hdf5/.bin/.npy/.npz/.docx/.xlsx` 路径；返回规范化 `https` URL。`_requests()` 要求每条 `purpose=="public_metadata"` 且 URL 主机名 ∈ 声明的 `official_domains`（精确小写主机名）。
- **真实 GET 限额**：`fetch_sources()` ——「At most ten public metadata GETs, seven-day cache, six-hour failure cooldown」；`fetcher(url, max_bytes=500_000)`；content-type 仅 `text/html/text/plain/application/json/application/ld+json/application/xml/text/xml/application/atom+xml`；HTML 经 `direction_evidence.PageText` 抽文本；标识符 `sha256(url + sha256(raw))` 决定 `evidence/support-sources/<id>.txt` 与 `.response.txt`；`record()` 标记 `deterministic-control-plane` provenance；ledger 记 `paid_calls=0`、`publishing_authorized=False`、`data_download_authorized=False`、失败为 `status="unavailable"`（6 小时冷却）。
- **回执校验**：`_receipt()` 要求 INDEX 有 `tracked` + `family=="other"` + `provider==META_PROVIDER` + `model=="scripts/research_support.py"` 的受保护来源；`retrieved` + `http_status==200`、`retrieved_at` 在 7 天内且非未来、`final_url` 不越声明域、raw/source 双哈希匹配、派生路径匹配。
- **安全算术重算**：`_arithmetic()` 用 `ast.parse(mode="eval")` + 节点白名单（仅 `Constant/Name/UnaryOp(+,-)/BinOp(+,-,*,/,**)`、表达式 ≤500 字符、节点 ≤80、指数为 ≤6 的整数、`Decimal` 精度 28、除零检查），明确「never code/tool execution」；`_worked_example()` 重算每步并与 `stated` 比对（容差 ≤1e-6），`arithmetic_checked=True` 但 `method_validated=False`、`experiment_result=False`。
- **方法/FAIR 诚实标注**：`_method()` 要求 `METHOD_FIELDS` 全 10 项、`source_scope` 与 `methods_assessed`；`full_text` 需 `source_scope.verify`；`_availability()` 要求 FAIR 四态分别陈述、deposit `planned/record_observed/unavailable`、repository access_label 映射、`negative access evidence cannot support an open deposit`；输出恒 `fair_certified=False / fair_requires_unrestricted_open_access=False / upload_ownership_verified=False / data_files_retrieved_or_verified=False / publishing_authorized=False / human_license_and_access_review_required=False`，并提示「Public metadata or viewing access does not grant redistribution」。
- **整报绑定**：`audit()` 递归 `collect()` 所有 `{path,sha256}`/`{raw_path,raw_sha256}` 生成 `source_bindings`；`refresh()` 走 `save_report`；`validate_saved_report()` 用 `report_errors` 比对干净重算。

**依赖**：`research_artifacts`（含 `save_report/report_errors`）、`network_safety`（`fetch_bytes`/`validate_https_url`）、`output_provenance`、`research_candidates.anchor_errors`、`source_scope.verify`、`direction_evidence.PageText`。
**边界限制**：文档字符串「Metadata GETs cannot publish, authorize data acquisition, certify a method, resolve an owner question or prove scientific completion. FAIR can include controlled-access data.」；`owner_approval_inferred=False`、`experiments_authorized=False`、`semantic_entailment_verified=False`、`official_domain_authenticity_requires_human_review=True`。

---

### 1.11 `research_task_acceptance.py`（113 行）

**职责**：「Render generated Mermaid in actual cloud Chromium using a pinned local bundle.」——**验收夹具**，不是科研能力。

**对外能力**：CLI `--directory --mermaid-package`；函数 `exercise`、`_render_cases`；内部类 `Rendered(HTMLParser)`（解析 `<body data-status/nodes/edges/error>`）。

**输入/输出**：输入为 pinned mermaid 包目录（校验 `package.json` 的 `name=="mermaid"` 且 `version=="12.2.0"`、`dist/mermaid.esm.min.mjs` 存在）与输出目录；输出 `mermaid-1/2.html`、`.rendered.html`、`.stderr.log`、`mermaid-acceptance.json`（`status=pass, runtime=actual_headless_chromium, paid_model_calls=0, scientific_validity_verified=False`）。

**关键机制**：`require_cloud()`；`shutil.which` 找 `google-chrome/chromium/chromium-browser`；`ThreadingHTTPServer(("127.0.0.1",0))` 仅服务临时目录中的 pinned bundle + 测试夹具（注释说明 `file:` 模块导入在 `--dump-dom` 下可能 pending，故走 loopback 以便网络空闲计入所有模块 fetch）；页面 CSP `default-src 'none'; script-src 'unsafe-inline' 'self' ...`，`mermaid.initialize({securityLevel:"strict", flowchart:{htmlLabels:false}})`；两个 case，第二个把节点标签改成 `Input "] --> injected["extra` 做**注入/XSS 测试**；`subprocess.run([browser,"--headless=new","--no-sandbox","--disable-dev-shm-usage","--dump-dom","--virtual-time-budget=8000",...], timeout=60)`；要求 `status=="passed" && nodes=="3" && edges=="2"`。

**依赖**：`diagram_mermaid.text`、`literaturectl.require_cloud`、`research_artifacts.write`；标准库 `http.server/subprocess/tempfile/threading/html.parser`。
**边界限制**：仅工程验收，恒 `paid_model_calls=0`、`scientific_validity_verified=False`。
**标注**：文件名 `research_task_acceptance` 语义宽泛，实际只做 Mermaid 渲染验收（名实不符，见 §5.5）；会起本地回环端口并拉起真实浏览器子进程（见 §5.2）。

---

### 1.12 `research_toolkit.py`（195 行）

**职责**：「Task-selected research-tool guidance; no upstream runtime or provider calls.」——任务选定的研究工具指导包。

**对外能力**：`catalog`、`installation_errors`、`_binding`、`_prepare`、`refresh`、`task_context`；CLI 无（由 `research_operations` 经 `Request` 调 `refresh`）。

**输入/输出**：输入 `integrations/research-automation-tools.json`（CATALOG）、请求 `program/research-toolkit-*.json`（≤64KB，`id/stage/tool_ids/task/input_bindings` + 可选 `paper_id`）、绑定 `state/run.json` 与 `intake/constraints.json`；输出不可变 `reports/research-toolkit/<id>-<packet_sha256>.json`（`paid_calls=0 / upstream_runtime_executed=False / scientific_validation="not_assessed" / status="prepared_not_executed"`）；`task_context()` 返回给模型的提示词字符串。

**关键机制**：`catalog()` 校验每条 tool 的 `id`（小写）、`repository`（`owner/repo`）、`commit`（40 hex）、`recipe_path==skill_path` 且以 `integrations/codex-research-tools/skills/` 开头、`recipe_sha256` ∈ `{sha(file), pinned_text_sha256(file)}`、`stages⊆STAGES`、`native_operations`；`_binding()` 限制输入前缀为 `program/|papers/|evidence/|literature/|reports/|experiments/|data/` 且哈希匹配；`_prepare()` 选 1–10 个适用于该 stage 的工具、1–40 个输入绑定、校验 `state/run.json` 的 `stage` 与请求一致；`task_context()` 只读 `RESEARCH_TOOLKIT_PACKET=` marker 指定的不可变包，重算校验，按角色给 boundary（`planner` 只读语义规划 / `critic` 独立评估 / `writer` OpenAI 独立写 / `remediator` 解决记录问题），`critic` 省略请求者 task narrative，拼接所选 adapter recipe 全文，并仅对显式绑定的 `reports/research-iteration|frontier|search-tree/` 调对应 `model_context`。

**依赖**：`research_artifacts`、`research_methods.pinned_text_sha256`、`literaturectl.require_cloud`、`output_provenance`、`research_iteration/research_frontier/research_search_tree`（`import_module` 动态调 `model_context`）。
**边界限制**：`selection≠execution`；「Hashes identify inputs; they do not mean their contents were read or verified」；`execution_authority` 明确仍需既有云控、冻结 G3 runner、真实预算权限，G1/G2 人工。

---

### 1.13 `researchctl.py`（720 行）

**职责**：「Human-gated Doctoral Research OS state manager with publication-quality floors.」——**核心状态机 + G0–G5 闸门总聚合器**，本组的调度中枢。

**对外能力（CLI `parser()`）**：`init`（`--project/--paper-count/--venue`）、`status`（`--json`）、`gate-check`（`--gate`）、`ready`（`--note`）、`reopen`（`--note`）、`approve`（`--gate/--actor/--paper/--note`）、`advance`、`set-venue`、`stages`。
库函数主要：`read_json/write_text/validate_slug/validate_paper_id/project_dir/state_path/load_state/save_state`、`nonempty/load_nonempty_json/jsonl_objects`、`audit_document_valid`、`independent_audit_errors`、`quality_path/quality_errors`、`summarize_gate_errors`、`paper_scientific_errors`(A 类)、`paper_observations`(C 类)、`gate_errors`、`active_paper_id`、`artifact_hash`、`paper_artifact_hash`、`initialize`、`print_status/print_gate_error_groups/check_gate/mark_ready/reopen/approve/_record_gate_decision/advance/set_venue_values/set_venue/list_stages`。

**输入/输出**：
- 核心状态：`projects/<slug>/state/run.json`（`schema_version 2.0 / stage_index / stage / gate / status / active_paper / paper_count / paper_statuses / approved_gates / approvals / history / writing_phases / paper_execution_mode / paper_topic_approvals`）。
- `STAGES`：intake→G0、topic-intelligence→G1、paper-architecture→G2、experiment-design→G3、experiment-execution→G4、writing-and-review→G5、submission-ready→None。
- `init` 创建全套骨架：`intake/constraints.json`（`status="needs_user_input"`、`execution_mode="cloud_only"`、大量空值字段）、`intake/capabilities.json`（`status="unverified"`）、`state/output-provenance.json`、`research_increments.initialize`、`state/model-spend-control.json`（`model_spend.initial()`）、`program/core-thesis.json`/`extension-thesis.json`（全空 draft）、`topic-shortlist.json`（空）、`paper-map.json`（空）、`novelty-claim-matrix.json`（schema 1.1 全 0/False/空）、5 个空 jsonl、`claims/claim-evidence.csv`（表头）、每篇 `papers/Pxx/` 各子目录 + `research-identity.json`（`research_identity.template`）+ `paper-contract.json`（schema 2.0，含 `target_jcr_quartile=venue_policy.default_target`）+ `reviews/citation-claims.jsonl` + `response-matrix.csv`；强制 6 篇（非 6 篇且 `command=="init"` 或 `DR_OS_ROUTING_PROFILE=production` 时直接报错，仅低层夹具放行）。
- `status --json` 输出 `{**state, gate_ready, gate_errors, gate_warnings, gate_error_groups, [intake_guidance]}`。

**关键机制**：
- **状态机**：`load_state()` 校验 `stage_index` 与 `stage/gate` 一致，为旧状态补 `paper_statuses`；`mark_ready()` 要求 `gate_errors` 全空，记录 `ready_gate` + `ready_artifact_sha256=artifact_hash` + history；`approve()` **仅 G1/G2 人工**（`actor` 不能为 `deterministic-control-plane`，G2 必须 `--paper` 逐篇投票，凑齐全部论文才 `_record_gate_decision`）；其它 gate 由 `mark_ready` 直接 `_record_gate_decision(..., "deterministic-control-plane", ..., "deterministic")`；`reopen()` 需 `--note` 且弹掉 ready 快照；`advance()` 重算 `artifact_hash` 比对、再次 `gate_errors` 全空才推进。
- **哈希绑定**：`artifact_hash()` 遍历项目文件（排除 `state/`、`experiments/runs/`、`raw/`、`venue-template/`、`build/`，G3/G4/G5 再按 `paper_execution.relevant` 过滤）逐文件 `路径+\0+字节+\0` 进 SHA-256，末尾混入 gate；`paper_artifact_hash()` 叠加 `research_increments.paper_review_binding`、`manuscript_hygiene.integrity_binding`、`reviewer_rounds/publication_disclosure.review_binding`、`research_identity.review_binding`、`review_receipts/scientific_scope.review_binding`、`supplemental_experiments.internal_binding` 的规范化 JSON。`ready/approve/advance` 三处重算比对，变更即要求重走流程。
- **G3/G5 决策封存**：`_record_gate_decision()` 在 G3 记 `experiment_plan_sha256`、`experiment_budget_sha256`、各篇 `frozen_protocol_sha256`、`compute_budget_authority`；G5 记 `paper_artifact_sha256`、`submission_checks_sha256`，key 为 `G5:<paper>`；G1/G2 调 `scientific_scope.seal_approval`；G5 `advance` 逐篇标 `submission_ready` 并把下一篇切回 G3（`enable` 独立论文执行模式）。
- **闸门聚合 `gate_errors(slug, gate)`**（本文件最核心）：G0 校验 `intake/constraints.json`（`intake_validation.validate_constraints`）；G1 聚合 `direction_evidence.validate_saved`、search-log、`ai4science_evidence`、topic-shortlist ≥3 候选 + `validate_selected_direction_cloud_feasibility`、core/extension `validate_theme_independence`、`research_design.validate_originality_audit/validate_search_log`、`literature_evidence.validate_search_evidence`、`research_quality.validate_novelty_claim_matrix`、`topic-decision.md`、`research_candidates.validate_saved_register`；G2 聚合 `research_design.validate_portfolio_evidence`、venue-candidates/journal-screening（仅 warnings）、paper-map、theme mapping、逐篇 paper-contract（含 `target_jcr_quartile`/`target_venues` 规划目标一致性 warning、`unique_claim_ids` 与 paper-map 一致、`originality_boundary` 引用 G1 prior work）；G3 探索分支走 `research_quality.validate_g3_quality`，否则 dataset manifests（`download.sha256!="pending"`）、`experiment_runner.validate_plan`、`paper_execution.plan_errors`、`research_design.validate_experiment_design`、design_id/run_id/hypothesis/dataset 一致性、budget `hard_ceiling_usd` + `compute_budget_authority`；G4 校验 registry/plan/`results_validation.validate_registry`/`validate_claim_evidence`/`reports/reproducibility.md`/`research_quality.validate_g4_quality`；G5 拒绝探索性进入、`supplemental_experiments.internal_errors`、`study_routes.validation_errors`、`paper_scientific_errors`、C 类 `paper_observations`，`requires_submission` 时走 `submission_package.submission_checks`（绑定未变快照 `submission_checks_sha256`）否则返回 `SUBMISSION_PENDING`。所有 gate 还叠加 `innovation_screening.validate_novelty_gate`、`scientific_scope.validate`、`research_extensions.gate_errors`、`research_increments.gate_errors`、`quality_errors`（可选）、`independent_audit_errors`（`review_receipts.validate_gate` + `reviews/decision-log.md`）。
- **A/C 分类**：`paper_scientific_errors`（A 类事实/保全）含 paper-facts、全文引用支持、统计报告、修订完整性、图件来源、保留原件、稿件存在性；`paper_observations`（C 类诊断）含 academic style/hygiene/language/watermark/pre-submission/figure layout/appearance/revision trace/ledger/Word revisions/concern cards，注释明确「never acquire data, call a model or grant scientific approval」，异常被 `_observe` 吞为 warning。
- **错误分组**：`summarize_gate_errors()` 用 9 条规则把重复校验归为中文标题 + `next_action`（novelty_search/literature_screening/source_integrity/data_rights/experiment_protocol/experiment_execution/claim_support/independent_review/submission_preparation），明确「Counts describe validator messages, never independent scientific problems」「Only known shared causes are combined」，原始检查保留在 `checks`。
- **fail-closed**：数十处 `try: from scripts import X ... except ImportError as exc: errors.append("validator unavailable: ...")` —— 依赖缺失会阻断闸门而非静默放行。

**依赖**：`paper_execution`、`research_artifacts`、`quality_gate`、`research_design`、`innovation_screening`、`scientific_scope`、`research_phase`、`experiment_evidence`、`empirical_workflow`、`primary_recovery`、`research_identity`、`research_extensions`、`research_increments`、`intake_validation`、`direction_evidence`、`ai4science_evidence`、`research_candidates`、`literature_evidence`、`research_quality`、`results_validation`、`submission_package`、`venue_policy`、`model_spend`、`artifact_ownership`、`manuscript_audit` / `statistical_reporting` / `revision_integrity` / `figure_provenance` / `manuscript_hygiene` / `literature_source_tasks` / `academic_style` / `manuscript_language` / `statistical_watermarks` / `pre_submission_review` / `figure_layout` / `automated_visual_review` / `revision_trace` / `revision_ledger` / `docx_revision` / `manuscript_docx` / `reviewer_rounds` / `publication_disclosure`。
**边界限制**：`approve` 仅 G1/G2；`advance` 终点为 `submission_ready`，**绝不自动投稿**；G5 探索性观察直接打回「return to a reviewed confirmatory G3 protocol」。

---

### 1.14 `results_validation.py`（373 行）

**职责**：「Validate G4 experiment attempts and claim-to-evidence traceability.」——G4 执行回执与「主张↔证据」可追溯性校验。

**对外能力**：`validate_registry`、`_outcome_error`、`claim_outcomes`（`@paper_scoped`）、`validate_result_statuses`（`@paper_scoped`）、`validate_claim_evidence`、`_resolve/_ids`。

**输入/输出**：输入 `experiments/plan.json`、`experiments/registry.jsonl`、`state/run.json`（G3 approval）、`claims/claim-evidence.csv`、`papers/Pxx/paper-contract.json`、`experiment-evidence*.json`；输出 `list[str]` 错误，或 `claim_outcomes()` 返回 `{paper_id, claim_matrix_sha256, evidence_plan_sha256, claims{claim→{result_status, comparison_ids, analysis_ids}}}`。

**关键机制**：
- `validate_registry()`：要求 `approval.experiment_plan_sha256 == sha(当前 plan)`（「current experiment plan does not match the recorded G3 protocol decision」）；逐条校验 `run_id∈planned`、`attempt_id` 非空唯一、`schema_version=1.0`、`status∈{succeeded,failed,timed_out}`、`paper_id/seed/approved_plan_sha256/argv/cwd/timeout_seconds/estimated_cost_usd/timed_out` 与计划一致、`started_at/finished_at/runtime_seconds`、`inputs` 精确匹配且每个文件当前哈希一致、`input_integrity`（`verified_after_run=true`、`passed` 与 `mutated_or_missing` 逻辑一致、成功 run 不得输入被改）、`outputs` 存在且哈希一致（失败/超时走 `primary_recovery.preserved_output`）、成功 run 的 `expected_outputs` 集合一致且不得有 `missing_outputs`；计划内所有 run 必须有 attempt；多次尝试用 `selected_attempt`/`latest_attempt` 校验。
- `_outcome_error()`：防夸大——`supported` 需所有 confirmatory 比较达到 `meets_preregistered_threshold/kernel_checked`；`partially_supported` 需至少一个通过的确证 primary；`contradicted`（empirical）需确证 primary 置信区间建立相反（`high < -margin` 或 equivalence 的区间判据），「absence of significance is insufficient」。
- `claim_outcomes()`：重算「当前视图，never a new ledger」，要求 claim IDs 与 contract `unique_claim_ids` 完全一致、`comparison_ids` 覆盖 `experiment_evidence.build_report` 的所有实际比较、`sources ⊆ analysis_ids ⊆ known_runs`、通过 `_outcome_error`。
- `validate_result_statuses()`：G4/G5 适配器，稿件 `claim_alignment` 必须逐 claim 覆盖且 `result_status` 与当前正式结果一致。
- `validate_claim_evidence()`：CSV 列、contracted claim 覆盖（missing/extra 均报错）、`paper_id` 匹配、`support∈SUPPORT_VALUES`、`analysis_ids` 为已知 run 且同论文；非 empirical 路线用 `experiment_evidence.validate_report/build_report` 核对 `comparison_ids`/primary result；empirical 路线核对 preregistered comparisons 与 `confirmatory` 阈值；`supported/partially_supported` 必须引用成功 run。

**依赖**：`research_artifacts.sha`、`paper_execution`、`primary_recovery`、`experiment_evidence`、`study_routes`。
**边界限制**：`_resolve()` 拒绝绝对路径与逃逸项目目录；「A current view, never a new ledger」；保留全部 adverse/exploratory 比较。

---

### 1.15 `review_packets.py`（556 行）

**职责**：「Protected internal blind/visual review; no calls, approvals or inferred scores.」——内部盲评（calibration）与视觉审查（visual）包。

**对外能力**：`digest/identifier/text/source/rubric/plan`、`applies_to_paper`、`base`、`label`（HMAC）、`plain`、`calibration`、`render_dependencies`、`visual`、`build`、`refresh`、`review_snapshot`、`judgments_checked`、`create_confirmation`、`validate_gate_reviews`、`audit`。

**输入/输出**：输入 `program/review-packets.json`（INPUT，1–64 packets，kind `calibration|visual`）、`reports/review-packets/<id>/`（manifest.json、answer-key.json、materials/、history/、refresh-attempts.jsonl）、`state/review-packet-confirmations/<id>/*.json`、render receipt、QA report、`automated_visual_review` 结果；输出 `reports/review-packets.json` 与各包产物。

**关键机制**：
- **盲化**：`label(seed,*values)` 用 HMAC-SHA256 生成 20 hex 匿名标签（稳定仅依赖 ID）；`plain()` 要求盲化文本为 `.txt/.md`、≤4MiB、不含 `path/文件名/model/channel/price/¥/CNY` 等隐藏词（「do not rewrite scientific facts to hide clues」）；`calibration()` 的 `version=digest(packet)[:20]` 保留旧/失败候选文本，每个 candidate 需 `authorized_for_internal_review=true`、`author_id`、`status∈{success,failed}`，失败需 `failure_reason`+`failure_receipt`，失败候选记 `origin="no_artifact_failed_attempt"`；盲化材料经 `output_provenance.record_model_writes(role="internal-read-only-review-copy")` 登记。
- **answer key + 不可变历史**：`build()` 产出 `answer_key{seed, answer_key: private}`（含真实来源/作者/来源 provenance）与 manifest；`refresh()` 用 `secrets.token_hex(32)` 或既有 seed，写 `history/<digest(archive_value)>.json`（已存在则字节必须一致）、`refresh-attempts.jsonl`（每次追加 `input_sha256` + result）。
- **视觉来源绑定**：`visual()`/`render_dependencies()` 要求渲染器 ∈ `RENDERERS`（`cloud_runtime`→`cloud-tex-renderer`、`word_render`→`cloud-word-renderer`、`publication_figures`→`publication-figure-renderer`），`renderer.implementation_sha256 == sha(ROOT/scripts/<script>)`、render receipt 有 `tracked` + `family=="other"` + 对应 provider + `role=="render-receipt"`、`status=pass` + `execution.mode=="cloud"` + `receipt_id`、评审源 ∈ 实际 render inputs、产物/预览 ∈ 实际 render outputs；QA report 需 `status∈{pass,review_required}` 且有受控 provenance；checklist 必须含 `math_symbols/final_size_readability/statistical_labels` +（`color_vision` 或 docx 的 `Word_complex_content`）。
- **独立人工评分员**：`judgments_checked()` 要求 `independent=true`、具名 `rater_id` + `independence_note`，rater 不能是任何候选作者；calibration 必须评每个候选（含失败为 `unscorable_failed`，不得伪造评分），ratings 精确覆盖冻结 rubric 维度且符合 typed bounds，critical_errors 全 boolean；visual 必须逐 artifact 覆盖 required boolean checklist。`create_confirmation()` 仅 prepare（「caller enforces owner authorization and whole-dossier hash」），append `attempts` 并各自 `attempt_sha256`。
- **不利观察不可被否决**：`validate_gate_reviews()` / `audit()` 对每个 visual 包调 `automated_visual_review.verify`，且若历史确认中存在「unchanged adverse visual observation」（`not all(checks.values())`）则报「requires a correction」——注释「Historical adverse visual observations are retained and cannot be outvoted on unchanged material by a subsequent machine pass」。
- **恒不宣称**：`calibration_status="NOT_CALIBRATED"`、`gate_approved=False`、`scientific_completion_verified=False`、`blindness_verified=False`、`rater_independence_verified=False`。

**依赖**：`output_provenance`、`research_artifacts`、`calibration_analysis.protocol`、`automated_visual_review`。
**边界限制**：「no calls, approvals or inferred scores」；human calibration ratings 为可选的诚实观察；`applies_to_paper()` 把 visual 门控限定到当前完成论文。

---

### 1.16 `review_panel.py`（806 行）

**职责**：「Three mutually blind source views; frozen findings are never votes or acceptance odds.」——G5 最终三家族互盲 panel，**本组唯一真实付费模型 API 调用点**。

**对外能力**：`request_path`、`contract`、`digest`、`_source`、`_normal/_section/_tex_fields/_canonical_scope/_data_text/_study_material`、`prepare`、`_owned/_response/_frozen`、`responses`、`author_context`、`submission_errors`、`_pointer_in_view`、`run`。

**输入/输出**：
- 输入 `papers/<paper>/reviews/panel-inputs.json`（`paper_id` + 三 `views` 各 1–30 行 `{kind,path,sha256,start_line/end_line 或 start_paragraph/end_paragraph}` + 可选 `dispositions`）、规范稿件（`.tex` 或 `.docx`）、`papers/<paper>/preregistration.json` + `experiment-evidence-plan.json`/`study-protocol.json`、`papers/<paper>/figures/figure-provenance.json`、`state/run.json`、`state/review-receipts/panel/<paper>/latest.json`。
- 输出：`reviews/independent/panel/<paper>/<run_id>/<seat>.json`（冻结意见）、`state/review-receipts/panel/<paper>/<run_id>/`（attempt.json、`<seat>-attempt.json`、`<seat>-actual-response.json`、`<seat>.json`、synthesis.json、失败时 failure.json）、`latest.json` 指针；`run()` 返回 `{status, paid_calls, findings, manifest, actual_routes, usage, record_errors, gate_authority=False, scientific_completion_verified=False}`。

**关键机制**：
- **来源隔离**：`_source()` 拒绝 `raw/private/reviews/reports/state/secrets/credentials/labels/benchmark` 路径段与 `secret/password/credential/answer-key/sample-label` 文件名，只允许 `papers/<paper>/manuscript|tables|figures/`、`results/<paper>/`、`experiments/papers/<paper>/` 前缀及 3 个 exact 文件 + `formal_sources`，≤8MB。`VIEWS`：domain `{methods,results,numeric_table}`、editorial `{title,abstract,figure_one,headline_claim}`、statistics `{protocol,numeric_table,figure_values}`；theory route 改用 `formal_proof`。`contract()` 给 writer 规定输入契约，强调「three different source views, not three copies of the full manuscript」「A panel request cannot declare a route or waive empirical materials」。
- **Canonical scope 推导（不信任 row 的 kind）**：`_canonical_scope()` 对 `.tex` 用 `tex_sources.expand` + 花括号配对（`_tex_fields`）识别 `\title` / `\begin{abstract}` / `\section` 家族 / `figure|table` 环境 / `\graphicspath` / `\includegraphics|pgfplotstable...` 解析图表源；对 `.docx` 用 `revision_integrity.WordSource` 解析 `word/styles.xml` 的 `styleId/name/outlineLvl/basedOn`、OMML 公式、脚注/尾注、数字表格、`Figure 1` caption 邻接图片（仅紧邻图片入 scope）。逐物理行/段落计算角色交集（`locations`），「A line that crosses sections cannot be relabeled as one of them」。`figure-provenance.json` 的 `data_chart` 需 `figure_provenance.lineage` 绑定执行器来源。
- **prepare 强校验**：每行 `kind` 必须属于该 seat 的 `required`、哈希匹配、行/段落范围合法、`selected_text_sha256` 绑定交付抽取；`protocol` 必须是完整 canonical 注册 JSON（全行、`schema_errors`、paper_id）；`statistics` 需同时 `preregistration.json` 与科学 protocol 且后者在冻结 binding 的 `files` 中；theory 需覆盖全部 formal proof 源；三 view 的路径组合与规范化内容均不得相同（「cannot receive identical views under different labels」）；`dispositions` 的 `finding_id` 唯一、`status∈{maintained,addressed,disagreed}`，改变意见需真实 `evidence` 且哈希匹配。
- **冻结意见**：`_frozen()` 要求 `latest.json` + manifest + 每 seat 回执 + response 均有 `deterministic-control-plane` + `model==MODULE` provenance、哈希匹配、`gate_authority=False`、`mutually_blind=True`、`view_sha256==digest(sources)`、三 `identity.family` 互不相同；`_response()` 限定字段恰为 `{view,findings,uncertainty}`，每条 finding 含 7 个必填字段与 `severity∈{fatal,major,minor,question}`；历史 panel 兼容 `literature_source_tasks.RESPONSE_FIELDS`（剥离但不重解释为当前任务）。
- **真实付费调用 `run()`**：`review_receipts._cloud()`；要求 `active_paper==paper && stage=="writing-and-review" && requires_submission`；`model_routing.select("writing-and-review","independent-critic-panel-"+seat)` 得三 route，要求 `len({family})==3` 且均 ≠ `writer_family`（默认 `"openai"`）；`model_runtime.preflight_route`；`run_id` 已尝试则拒绝（「never overwrite or repay it」）；写 `attempt.json` 后对每个 seat `model_runtime.call(project, run_id, stage="writing-and-review", role, provider, model, reasoning_effort, task_kind="scientific-judgment", task_profile={task_class:scientific-judgment, science_risk:"critical", priority:"quality"}, prompt, attachments, max_output_tokens, use_cache=False)`；校验 `api_identity(result)` 的 family 与 route 一致、`_pointer_in_view` 限制 finding 的 `claim_pointer/evidence_pointer` 不越出本 view；写 response + receipt + `record`；三 seat 完成后 `current = prepare(project, paper)` 与初始 packet 比对（输入变化则「retain these historical opinions」）；synthesis manifest 固定 `synthesis="all_independent_findings_preserved_no_voting"`、`acceptance_probability=None`、`calibration_status="not_established_by_this_panel"`、`gate_authority=False`、`scientific_completion_verified=False`；**任意异常写 `failure.json` + `record` 后 `raise`**（失败留痕、不重放、不吞异常）。
- **作者/投稿侧**：`author_context()` 仅作者/规划者可见历史意见（三 reviewer view 永不看到）；`submission_errors()` 只做 B 类覆盖检查（fatal/major finding 必须有 rationale + 当前 evidence），「opinion severity never certifies scientific truth」；`responses()` 比对冻结 view_sha256 与当前 packet。

**依赖**：`model_routing`、`model_runtime`、`output_provenance`、`review_receipts`、`research_artifacts`、`ref_verify_adapter.canonical_manuscript`、`tex_sources`、`revision_integrity`、`figure_provenance`、`study_routes`、`research_quality`、`paper_execution`、`research_phase`、`literature_source_tasks`。
**边界限制**：`gate_authority=False`；`source_task_execution="not_performed_by_final_panel"`；`paid_calls` 如实计数；拒绝缓存复用旧意见时虚报（复用分支 `paid_calls=0`）。

---

## 2. 本组整体能力归纳

1. **状态机与 G0–G5 闸门中枢**：`researchctl.py` 定义 7 阶段状态机、人工 G1/G2、机器记录其它决定、artifact-hash 三段式绑定（ready/approve/advance）、逐篇推进、**绝不自动投稿**；`gate_errors()` 聚合全仓库校验器形成闸门结论。
2. **科研质量确定性闸门**：`research_quality.py`（新颖性/数据质量/功效/预注册/基线复现/clean-room 复现）+ `results_validation.py`（执行回执/claim-evidence）+ `research_phase.py`（探索/确证强度与 G3/G4 转换）构成 G1/G3/G4 的证据-哈希-预算-复现控制面。
3. **只读「重算视图」族**：`research_iteration.py`、`research_search_tree.py`、`research_toolkit.py` 把已封存回执/计划/工具目录重算为**不可变、来源绑定、角色隔离**的报告（`prepared_not_executed`、`paid_calls=0`），供 planner/writer/critic/remediator 分角色取用，critic 只看事实不给建议。
4. **证据与决策台账**：`research_notebook.py`（问题中心证据/循环决策/失败记忆/每日简报）、`research_increments.py`（八组增量的依赖 DAG、人工确认、handoff 预算交接、G5 门控）。
5. **规则/方法/工具装配**：`research_methods.py`（pinned 方法目录 + 阶段规则 + K-Dense peer-review 抽取 + venue fit）、`research_operations.py`（白名单操作/BUILDERS 分发）、`research_mcp.py`（零成本 chat 路由）。
6. **真实来源采集**：`research_support.py` 以严格白名单做 ≤10 次公网 HTTPS 元数据 GET（7 天缓存/6 小时冷却），配合安全算术重算与 FAIR 诚实标注。
7. **审查与验收线**：`review_packets.py`（内部盲评 + 视觉审查，HMAC 匿名、独立人工评分员、不利观察不可否决）、`review_panel.py`（**G5 三家族互盲模型 panel**，真实付费 API、冻结意见、不投票）、`research_task_acceptance.py`（Mermaid Chromium 工程验收夹具）。

一句话：本组是「**确定性控制平面的右半段**」——以 `researchctl` 为调度、`research_quality`/`results_validation` 为科学闸门、以四大只读视图与两套审查线支撑，唯一的「湿」出口是 `review_panel` 的付费模型调用与 `research_support` 的公网 GET。

---

## 3. 在 G0–G5 的位置

| 阶段 | 本组承担 |
|---|---|
| **G0 intake** | `researchctl.initialize`（项目骨架/空占位输入）、`gate_errors(G0)`（intake constraints）、`research_mcp`（零成本入口路由）、`research_operations`（intake 阶段 builder 过滤，`increments_freeze` 标 `None` 阶段） |
| **G1 选题（人工）** | `researchctl.gate_errors(G1)` + `approve(G1)`；`research_quality.validate_novelty_claim_matrix(--for-gate)`（检索饱和/≥5 prior works/claim 差异）；`research_support`（问题澄清、primary-method 剖析、FAIR 辅助）；`research_notebook`（探索记录） |
| **G2 架构（人工逐篇）** | `researchctl.gate_errors(G2)` + `approve(G2 --paper Pxx)`（逐篇投票）；`research_design`/venue/journal 校验（经 researchctl 聚合）；`research_increments` 开始门控 |
| **G3 设计/封存** | `research_quality`（data-audit / power / simulation-power / freeze / validate g3 / preregistration / design_errors）、`research_phase`（exploratory design/plan_errors/exposure_errors/preregistration_inputs）、`researchctl.gate_errors(G3)` + `_record_gate_decision(G3)` 记 plan/budget/protocol/compute 哈希 |
| **G4 执行/结果** | `results_validation`（registry + claim-evidence）、`research_quality.validate_g4_quality`（baseline/clean-room reproduction + confirmation）、`research_iteration`（只读实验反馈）、`research_search_tree`（搜索树视图）、`research_phase.exploration_execution/build_report/archive_and_reopen`（探索回新 G3）、`researchctl.gate_errors(G4)/advance` |
| **G5 写作/投稿准备** | `review_panel.run`（三家族互盲 panel，**仅 requires_submission**）、`review_packets`（内部盲评/视觉）、`research_increments.gate_errors(G5)`、`researchctl.gate_errors(G5)`（A 类 `paper_scientific_errors` + C 类 `paper_observations` + `submission_package.submission_checks` 绑定未变快照）、`_record_gate_decision(G5)`、`advance` 标记 `submission_ready`（不投稿） |
| **横切全体** | `researchctl` 状态机与 artifact hash、`research_operations` 白名单分发、`research_methods.stage_rules` 规则装配、`research_toolkit` 工具指导、`research_notebook` 决策台账、`research_increments` 增量/预算交接、`research_mcp` 入口、`output_provenance`（组外但被全体依赖） |

---

## 4. 组内调用/依赖关系

```
researchctl.gate_errors()  ──总聚合──┬─> research_quality.validate_g3_quality / validate_g4_quality / validate_novelty_claim_matrix
                                     ├─> results_validation.validate_registry / validate_claim_evidence
                                     ├─> research_increments.gate_errors
                                     ├─> research_phase.exploratory / exposure_errors / archive_and_reopen / requires_submission / SUBMISSION_PENDING
                                     ├─> review_receipts.validate_gate (independent_audit_errors)
                                     ├─> submission_package.submission_checks / submission_check_binding (G5)
                                     └─> experiment_runner.validate_plan / compute_budget_authority, dataset_fetch.validate_manifest 等
researchctl.paper_artifact_hash() ──> research_increments.paper_review_binding
                                     + manuscript_hygiene.integrity_binding + reviewer_rounds/publication_disclosure.review_binding
                                     + research_identity/review_receipts/scientific_scope.review_binding + supplemental_experiments.internal_binding
researchctl.initialize() ──> research_increments.initialize, model_spend.initial, research_identity.template, venue_policy.default_target
researchctl._record_gate_decision(G3) ──> experiment_runner.compute_budget_authority

research_notebook.cycle_assessment() ──> review_panel.PREFIX / review_panel.responses
                                      ├─> review_receipts.observation / validate_gate / source_matches / _key
                                      ├─> research_phase.requires_submission / histories / writing_phase
                                      ├─> researchctl.audit_document_valid
                                      └─> api_orchestrator.validate_remediation_notes
research_notebook._historical_assessment() ──> review_receipts._material_identity/_owned/_identity, researchctl.audit_document_valid

research_operations.BUILDERS ──> research_notebook.refresh/daily_brief, research_support.refresh/fetch_sources,
                                 review_packets.refresh, research_increments.freeze, cloud_runtime.compile_tex, word_render.render ...
research_operations.OPERATIONS(Request) ──> research_toolkit/ research_iteration/ research_frontier/ research_search_tree .refresh

research_methods.stage_context() ──> ccfa_runtime.model_contract, research_phase.stage_rules/disposition_stage,
                                     research_toolkit.task_context, primary_recovery.diagnosis_context,
                                     contribution_reporting.feedback, research_case._venue_sources
research_toolkit.task_context() ──> research_iteration / research_frontier / research_search_tree .model_context
research_search_tree._prepare() ──> research_iteration.model_context(project, report_path, "critic")  【先校验绑定】
research_iteration / research_search_tree / research_toolkit .refresh ──> literaturectl.require_cloud

research_quality._saturation_executions() ──> literature_evidence.read_jsonl / validate_search_evidence / _doi / safe_project_file
research_quality.validate_g3/g4_quality() ──> experiment_evidence, study_routes, results_validation, research_phase
research_quality._preregistration_inputs/create_preregistration() ──> research_phase.exploratory/design_errors/preregistration_inputs,
                                                                      study_routes, empirical_workflow
research_phase.design_errors/build_report() ──> research_quality._manifest_map / validate_preregistration / _registry,
                                                 experiment_runner, dataset_fetch, results_validation
results_validation ──> primary_recovery, experiment_evidence, study_routes, paper_execution

review_packets.validate_gate_reviews/audit() ──> automated_visual_review.verify/packet_target, calibration_analysis.protocol
review_panel.run() ──> model_routing.select / model_runtime.preflight_route,call / review_receipts._cloud,_identity,api_identity
review_panel.prepare/_canonical_scope() ──> ref_verify_adapter.canonical_manuscript, tex_sources, revision_integrity,
                                            figure_provenance, study_routes, research_quality, paper_execution, research_phase
research_task_acceptance.exercise() ──> diagram_mermaid.text, literaturectl.require_cloud
```

**两条独立审查线**（易混淆）：`review_packets` 是**内部人工盲评/视觉**（seed+answer key+独立评分员，`calibration_status=NOT_CALIBRATED`）；`review_panel` 是 **G5 三家族互盲模型 panel**（真实付费、冻结意见、不投票）。二者互不调用，仅经 `researchctl`/`submission_package`/`automated_visual_review` 间接关联。

---

## 5. 特别标注

### 5.1 TODO / 占位 / 未实现 / 硬编码

- **未发现显式 `TODO` / `FIXME` / `NotImplementedError` / 空 `pass` 占位**：本组 16 文件均为可运行逻辑；大量 `*=False` / `*=0` / `"not_assessed"` 是**刻意的不越权声明**，不是未完成代码。
- **初始化空占位（设计性待用户提供）**：`researchctl.initialize()` 生成的 `intake/constraints.json`（`status="needs_user_input"`、研究目标/背景/时间/预算/`ranking_weights` 全 `None` 或空）、`capabilities.json`（`unverified`）、`core-thesis.json`/`extension-thesis.json`（全空 draft）、`topic-shortlist.json`/`paper-map.json`（空）、`novelty-claim-matrix.json`（全 0/False/空）、5 个空 `*.jsonl`、`paper-contract.json`（空字段）——这些是「不伪造输入」的占位，README 明确 G0 需真实提供目标/时间/预算。
- **恒为否定/未知的硬编码字段**：`research_increments`（`model_calls=0`、`scientific_completion_verified=False`、`quality_level_verified=False`）、`review_packets`（`calibration_status="NOT_CALIBRATED"`、`blindness_verified=False`、`rater_independence_verified=False`）、`review_panel`（`acceptance_probability=None`、`calibration_status="not_established_by_this_panel"`、`synthesis="...no_voting"`、`gate_authority=False`）、`research_iteration/search_tree/toolkit`（`paid_calls=0`、`experiments_executed=0`、`upstream_runtime_executed=False`、`scientific_validation="not_assessed"`）。
- **硬编码常量**：`research_quality.REVIEWED_STATSMODELS_VERSION="0.15.0"`、`POWER_RERUN_TIMEOUT_SECONDS=300`、`POWER_RERUN_MAX_BYTES=16MiB`；`research_task_acceptance` 硬编码 mermaid `12.2.0`、`nodes=="3"`/`edges=="2"`、`--virtual-time-budget=8000`；`research_support._url` 硬编码拒绝 `api.openai.com`/`api.anthropic.com`、端口 `443`、二进制扩展名集合；`research_notebook.daily_brief` 默认时区 `Asia/Shanghai`；`research_mcp.serverInfo.version="2.4.0"`；`researchctl` 强制 `paper_count==6`（production/init 报错，仅低层夹具放行）；`research_increments` 上限 2000 源 / 单源 50MB / 每组 200 行；`review_panel` 单源 8MB / 单 view 150_000 字节。
- **缺依赖降级**：`researchctl.gate_errors` 中约 20 处 `except ImportError: errors.append("validator unavailable: ...")` —— 若可选校验器模块缺失，闸门会**阻断**（fail-closed），不是静默放行；但生产环境确实缺依赖时会卡住闸门。

### 5.2 真实网络或付费 API 调用点

| 位置 | 类型 | 说明 |
|---|---|---|
| `review_panel.run()` line ~750 `model_runtime.call(...)` ×3 | **真实付费模型 API** | 本组唯一付费调用。`model_routing.select` 三 seat 必须 3 个不同 family 且 ≠ `writer_family`（默认 `"openai"`），`preflight_route` 校验；`task_kind="scientific-judgment"`、`science_risk="critical"`、`use_cache=False`；`paid_calls` 如实计数；`review_receipts.api_identity` 核对实际 model/endpoint identity；失败写 `failure.json` 后 raise（不重放、不吞） |
| `research_support.fetch_sources()` `fetcher(url, max_bytes=500_000)`（默认 `network_safety.fetch_bytes`） | **真实公网 HTTPS GET** | ≤10 次/次、7 天缓存、6 小时失败冷却；严格 URL/域/IP/端口/凭据/内容类型/大小白名单；`paid_calls=0` 指「付费模型调用为 0」，GET 不计付费 |
| `research_quality._saturation_executions()` 构造 `https://api.opencitations.net/index/v2/...` | **仅字符串比对，不发请求** | 校验回执的 `request_url` 是否等于由 DOI 派生的期望 URL；实际 OpenCitations 请求由组外 `literature_evidence` 产生并留回执 |
| `research_quality.create_simulation_power_report()` `subprocess.run([sys.executable,"-I",script])` ×2 | **真实本地子进程（执行用户脚本）** | 非网络、非付费，但确实执行项目内 `.py` 仿真脚本；`-I` 隔离、临时干净 cwd、精简 env、`stdin=DEVNULL`、300s 超时、16MiB 上限、两次规范 JSON 逐字节比对 |
| `research_task_acceptance.exercise()` `ThreadingHTTPServer(("127.0.0.1",0))` + `subprocess.run([browser,"--headless=new",...])` | **本地回环 HTTP + 真实浏览器子进程** | 仅服务临时目录内 pinned mermaid bundle 与测试夹具；`paid_model_calls=0` |
| `literaturectl.require_cloud()`（被 `research_iteration/search_tree/toolkit/refresh`、`research_task_acceptance` 调用） | 云环境门禁 | 非网络调用，仅校验执行环境 |

**范围外但被文档宣称的付费/编排入口**：`scripts/api_orchestrator.py`（AGENTS 规则 13 规定模型编排统一走它）、`scripts/autopilot.py`（start/resume/plan）、`scripts/experiment_runner.py` 的实际执行部分、`model_spend`、`submission_package` —— 这些文件**不在本精读范围**，本组内仅见 `research_notebook._historical_assessment` 调 `api_orchestrator.validate_remediation_notes`、以及 `experiment_runner` 的 `validate_plan/compute_budget_authority/prior_estimated_cost/accounted_run_cost` 等只读函数。不能据本组断定其实现与否。

### 5.3 安全与数据完整性风险

- **动态模块加载**：`research_operations.Request.__call__` 用 `import_module('scripts.'+(module or operation['action']))`、`research_toolkit.task_context` / `review_packets` 亦有动态 `import_module`；`action` 来自 `OPERATIONS/BUILDERS` 白名单键，风险可控但仍是可控代码加载面。`research_methods.load_vendored_module()` 相对更严（清单内 + `pinned_text_sha256` 校验 + 路径约束）。
- **用户脚本执行**：`research_quality.create_simulation_power_report()` 执行项目内仿真 `.py`，已用 `-I`、干净临时目录、`env` 白名单（仅 `PATH/LANG/LC_ALL/TZ/VIRTUAL_ENV/CONDA_PREFIX` + 5 个 `RESEARCH_OS_*` + `PYTHONHASHSEED=0`）、`stdin=DEVNULL`、超时、大小上限、两次重放一致性缓解；但仍是本地代码执行，且 `evidence_value` 内容来自项目文件（信任项目文件系统）。
- **SSRF 面**：`research_support.fetch_sources()` 防护较完整，但允许「声明域内任意路径/查询参数」与「重定向到同域其它路径」；`_receipt` 的 7 天时效依赖 `retrieved_at` 与系统时钟；`official_domains` 由 `program/research-support.json` 自带，`official_domain_authenticity_requires_human_review=True` 把域名真实性留给人工。
- **本地信任模型**：全组 `sha256` 绑定均为本地文件哈希 + `output_provenance` 记录（无数字签名）；`artifact_hash/paper_artifact_hash` **刻意排除** `state/`、`experiments/runs/`、`raw/`、`build/`、`venue-template/`、`submission/` 及 `paper_observation_path` 命中项——若把关键输入放进这些目录，其变更不会使 ready/approve 的哈希失效（设计上避免运行产物重算，但形成潜在绕过面）。
- **盲评 seed 存储**：`review_packets` 的 `seed`/`answer_key` 存于项目内 `reports/review-packets/<id>/answer-key.json`，解盲能力依赖文件系统权限；`record_model_writes` 仅登记来源，不加密。
- **canonical 解析复杂度**：`review_panel._canonical_scope()` 手写 TeX 花括号配对、`\graphicspath`/`\includegraphics` 解析、Word `styles.xml` 的 `basedOn/outlineLvl/name` 链、Figure 1 caption 邻接判断——边界 case 多（跨节行、嵌套表格、OMML、`OLEObject`），代码已用「crosses boundaries 即报错」多处兜底，但仍是复杂解析面。
- **`_arithmetic` AST 求值**：`research_support` 已用节点白名单、长度/节点数/指数上限、`Decimal` 精度、除零检查缓解；属于受控求值而非 `eval`。
- **fail-closed 副作用**：`researchctl` 的 ImportError 降级为 error 会阻断闸门（正向），但生产环境漏装可选依赖会卡住流程；`quality_errors` 缺文件仅 warning（可选质量评估），与 A 类强校验区分。
- **诚实标注（正向）**：`handoff.cost.amount_basis="persisted estimates; provider invoice controls final billing"`、`billing_reconciled`、多处 `scientific_completion_verified=False` —— 均不把估算/工程检查冒充真实账单或科学有效。

### 5.4 「文档宣称但本组代码未见实现」处

- **Claude 只读规划 / OpenAI 写持久产物 / 角色隔离（AGENTS 规则 10、14、17、18）**：本组以 `gate_approved=False`、`scientific_completion_verified=False`、`review_panel.writer_family="openai"`、`research_toolkit.task_context` 的按角色 boundary 文案、`review_panel` 三 family 校验、`output_provenance` 来源检查来**落实边界**；但 Claude/OpenAI 的实际分工、model family 判定、`output_provenance` 写入由组外 `model_routing`/`model_runtime`/`output_provenance` 实现，本组内未见其定义。
- **统一编排 `scripts/api_orchestrator.py`（AGENTS 规则 13）**：本组仅 `research_notebook._historical_assessment` 调其 `validate_remediation_notes`，未见 `api_orchestrator` 的 planner→writer→critic 主链；编排器本体在范围外。
- **实验只经 `experiment_runner.py` 执行（AGENTS 规则 14）**：本组只见其 `validate_plan/compute_budget_authority/prior_estimated_cost/accounted_run_cost` 等只读/计算函数，未见 `run` 执行逻辑（在范围外）。
- **累计预算 / 全部尝试计费（AGENTS 规则 23）**：`research_increments.handoff` 读 `model_spend.read`、`researchctl` 无直接预算闸门；预算实账与累计上限执行在 `model_spend`/组外；`quality_summary` 仅统计报告数量。
- **README「逐主张全文证据三态、15% 抽检、独立引用差异」**：`results_validation` 有 claim 三态（supported/partially_supported/...）与 claim-evidence 覆盖；**15% 抽检、独立引用差异**在本组 16 文件未见实现（疑在 `citation_audit`/`literature_source_tasks` 等范围外文件）。
- **README「本轮没有运行付费研究 / 真实 0.85 一致性仍需验收」**：与代码一致——`review_panel.calibration_status="not_established_by_this_panel"`、`review_packets.calibration_status="NOT_CALIBRATED"`，均未宣称校准达成。
- **README「三家族互盲 panel」**：`review_panel.run()` 用 `model_routing.select` + `len(families)==3` + `≠writer_family` 校验落实；但 `acceptance_probability=None`、不投票、不预测编辑决定，与 README「freeze 后综合保留分歧」一致。
- **README「不自动投稿」**：`researchctl.approve` 仅 G1/G2、`advance` 终点 `submission_ready`、`review_panel.gate_authority=False`、`research_mcp.submission_started=False` —— 组内一致落实。

### 5.5 名实不符处

1. **`research_task_acceptance.py`**：名字暗示「研究任务验收框架」，实际只是 **Mermaid 12.2.0 + headless Chromium 渲染验收夹具**（含一个注入测试 case），且 `scientific_validity_verified=False`。
2. **`research_mcp.py` 的 `serverInfo.version="2.4.0"`** 与仓库/README 的 **v2.3.0** 不一致（版本号硬编码漂移）。
3. **`review_packets.py` 的 "blind review"**：是**内部人工盲评/视觉夹具**（HMAC 匿名 + seed + answer key + 独立具名评分员），不是真正的双盲同行评审；且 `calibration_status` 恒 `NOT_CALIBRATED`、`blindness_verified=False`、`rater_independence_verified=False`。
4. **`research_methods.py` 的 "K-Dense peer-review method"**：只是从 pinned `SKILL.md` **抽取完好章节作提示词**，明确「never execute an upstream workflow」；不运行任何上游方法。
5. **`research_iteration.py` / `research_search_tree.py` / `research_toolkit.py`**：名称暗示「迭代 / 搜索树 / 工具箱执行」，实际全是 `status="prepared_not_executed"` 的**只读重算视图**（无 search agent、无 execution、无 upstream runtime）。`research_iteration` 文档亦明言「never execute or approve」。
6. **`research_support.py` 的 `paid_calls=0`**：指「付费模型调用为 0」，但它确实发**真实公网 GET**；措辞上需区分「网络 GET」与「付费调用」，否则易误读为「零网络」。
7. **`researchctl.quality_errors` / `paper_observations`**：标为「质量闸门」但缺文件仅 warning、C 类观察「never grant scientific approval」，与 A 类 `paper_scientific_errors` 强阻断分属不同权威层级，命名上易被误认为同级闸门。

---

## 6. 关键路径 / 常量速查

| 模块 | 关键常量 / 路径 |
|---|---|
| research_increments | `PLAN=program/research-increments.json`、`ROOT=reports/research-increments`、`REPORT=.../audit.json`、`CONFIRMATIONS=state/research-increment-confirmations`、`GROUPS=8 组`、`OBSERVATIONS={voices,editing}` |
| research_iteration | `OUTPUT=reports/research-iteration`、`MODULE=scripts/research_iteration.py`、报告名 `<id>-<report_sha256>.json` |
| research_mcp | `ROOT/projects`、4 tools、`protocolVersion=2025-06-18`、`version=2.4.0` |
| research_methods | `config/research-methods.json`、`integrations/vendored-research-methods.json`、`integrations/upstreams.lock.json`、`third_party/kdense/skills/peer-review/SKILL.md` |
| research_notebook | `NOTEBOOK=program/research-notebook.json`、`reports/research-notebook-history.jsonl`、`reports/research-notebook-daily/<date>.{json,md}` |
| research_operations | `OPERATIONS`(~50) / `BUILDERS`(~20) / `AUTOMATED_OPERATIONS` / `CLI_ALIASES` |
| research_phase | `SUBMISSION_PENDING` 常量、`exploration-*` 归档、`writing_phases` |
| research_quality | `REVIEWED_STATSMODELS_VERSION=0.15.0`、`POWER_RERUN_TIMEOUT_SECONDS=300`、`POWER_RERUN_MAX_BYTES=16MiB`、`data/quality/<id>.json`、`papers/Pxx/{power-analysis,preregistration,baseline-reproduction,clean-room-reproduction,reproduction-confirmation}.json` |
| research_search_tree | `OUTPUT=reports/research-search-tree`、`PHASES={investigation,tuning,main,ablation}` |
| research_support | `INPUT=program/research-support.json`、`OUTPUT=reports/research-support.json`、`INDEX=evidence/support-sources/index.json`、`META_PROVIDER=deterministic-control-plane` |
| research_task_acceptance | mermaid `12.2.0`、`dist/mermaid.esm.min.mjs`、`mermaid-acceptance.json` |
| research_toolkit | `CATALOG=integrations/research-automation-tools.json`、`OUTPUT=reports/research-toolkit`、`MARKER=RESEARCH_TOOLKIT_PACKET=`、`STAGES=6` |
| researchctl | `STAGES`(7)、`DEFAULTS_PATH=config/defaults.json`、`quality_path` 映射、`state/run.json`、`artifact_hash/paper_artifact_hash` |
| results_validation | `CLAIM_COLUMNS`、`SUPPORT_VALUES`、`STATUS_VALUES`、`claims/claim-evidence.csv` |
| review_packets | `INPUT=program/review-packets.json`、`CHECKS=5`、`RENDERERS=3`、`reports/review-packets/<id>/`、`state/review-packet-confirmations/` |
| review_panel | `PREFIX=state/review-receipts/panel`、`VIEWS=3 类`、`papers/<paper>/reviews/panel-inputs.json`、`reviews/independent/panel/<paper>/<run_id>/`、`MODULE=scripts/review_panel.py` |

---

*报告结束。16 个文件 / 8578 行全部逐段通读；未修改 `D:/ad/lunwen` 内任何文件。*
