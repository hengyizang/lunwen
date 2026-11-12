# scripts-G02 源码精读报告

> 仓库：`D:/ad/lunwen`（Doctoral Research OS v2.3.0）
> 精读范围：`scripts/` 下按 Python `sorted(*.py)` 字母序，自 `citation_audit.py` 起至 `docx_revision.py` 止，含两端，共 **27 个文件 / 8742 行**（`wc -l` 实测与题面完全一致）。全部用 `Read` 逐文件完整通读；5 个超 500 行文件分段读完：`citation_audit.py`(1011,2 段)、`cloud_job.py`(841,2 段)、`cloud_recovery.py`(551,2 段)、`cloud_research_steps.py`(604,2 段)、`data_discovery.py`(588,2 段)。
> 背景文档 `AGENTS.md`(107 行) / `README.md`(353 行) 已通读，仅作规则参照，**不计入精读范围**。
> 纪律：本次只读仓库，未修改/新建/删除 `D:/ad/lunwen` 下任何文件；唯一写入为本报告。
> 承接 `scripts-G01.md`（`__init__.py`–`check_env.py`，20 文件 / 8518 行）；本组是紧随 `check_env.py` 之后的第二段，两组相加为 `citation_audit.py` 之前的全部 20 文件 + 本组 27 文件。

## 0. 文件清单（字母序，行数为实测）

| # | 文件 | 行数 | 角色一句话 |
|---|---|---|---|
| 1 | `citation_audit.py` | 1011 | G5 引用身份核验：Crossref 实时核验 + 无 DOI 的离线来源重放 + 双抽取机械交叉检查 |
| 2 | `claim_evidence.py` | 189 | 逐主张「定位引用证据 + 记录独立判断」，15% 抽检 / 0.85 目标，**绝不自动验证** |
| 3 | `cloud_checkpoint.py` | 301 | 哈希校验云 checkpoint：小文件进 Git、其余进 Actions artifact、凭据扫描、预留远端持久化 |
| 4 | `cloud_continuation.py` | 420 | owner 授权的持续研究决策（should_run/reason），不授予闸门或花费 |
| 5 | `cloud_human_acceptance.py` | 224 | **合成验收夹具**：G3/G4 人工控制机制的软件验收 |
| 6 | `cloud_human_controls.py` | 388 | 哈希绑定 dossier 的 22 类 owner 人工决定，从不调用模型 |
| 7 | `cloud_job.py` | 841 | **云端作业总枢纽**：owner-only GitHub issue 控制面，所有 action 的入口 |
| 8 | `cloud_pipeline_acceptance.py` | 197 | **合成两-runner 验收**：checkpoint 恢复 / 负结果 / 原生 DOCX·图·TeX 导出 |
| 9 | `cloud_progress.py` | 379 | 停滞检测与成本归属（防无新输入重复工作） |
| 10 | `cloud_recovery.py` | 551 | owner 授权云恢复：有界重试 + AST 级窄范围回滚 + PR 验证合并 |
| 11 | `cloud_recovery_acceptance.py` | 45 | 既有 unittest 套件的单一回执 |
| 12 | `cloud_research_steps.py` | 604 | API 周期前后的确定性研究步骤（数据获取 + 20 余种 builder 分派） |
| 13 | `cloud_retry.py` | 73 | 幂等基础设施操作的有界重试（git/pip），含脱敏 |
| 14 | `cloud_runtime.py` | 151 | 云工具链装配 + 沙箱化 Docker TeX 编译 |
| 15 | `concept_illustrations.py` | 83 | 可选概念插图；**GPT Image 付费路径被禁用**，仅本地 PNG 导入 |
| 16 | `context_efficiency.py` | 190 | 无损 JSON 压缩 + 发现导航索引 + 独立审查包的「调用信封」排除 |
| 17 | `contribution_reporting.py` | 211 | 在 paper-facts 权威下机械准备可审查贡献记录 |
| 18 | `cost_audit.py` | 165 | 确定性成本诊断 / 场景预测，绝不预测成功或节省 |
| 19 | `data_cleaning_runtime.py` | 249 | **供实验容器使用的独立离线清洗命令**（无 scripts 包依赖） |
| 20 | `data_contracts.py` | 425 | 变量字典 / CSV 全扫描诊断 / 面板·连接 / G3 数据准备与清洗 |
| 21 | `data_discovery.py` | 588 | 8 家公开数据集元数据发现（真实 HTTPS API），不声明许可或适配性 |
| 22 | `data_row_provenance.py` | 320 | 完整源绑定行级溯源，只出元数据不导出原始行 |
| 23 | `dataset_fetch.py` | 279 | 源/版本绑定清单校验 + SSRF 防护的公网 HTTPS 下载 |
| 24 | `detector_feedback.py` | 94 | 用户提供的检测器分数编辑账本，不调用检测器、不认证作者身份 |
| 25 | `diagram_mermaid.py` | 106 | 既有类型化 IR → 可编辑 Mermaid（不渲染、不批准） |
| 26 | `direction_evidence.py` | 271 | G1 方向情报：带日期主来源回执 + owner 权重打分 + 敏感性分析 |
| 27 | `docx_revision.py` | 387 | 真实 OOXML 跟踪修订 + accept/reject 往返验证 |

---

## 1. 逐文件精读

### 1.1 `citation_audit.py`（1011 行）

- **职责定位**：G5 引用与数值核验。文件头 `"""Audit reference identity using actual provider evidence or legacy human records."""`——只核验**书目身份**，明确不证明许可、主张支持、全文阅读或科学完成。
- **对外能力**：CLI `citation_audit.py <bibliography> --output <json> [--manual-verifications] [--offline] [--refresh-metadata] [--cache-metadata] [--docx-citations-verified-by]`；退出码 pass=0/fail=1/错误=2。主要函数：`parse_bibtex`、`citation_usages`/`docx_citation_keys`/`citation_prose`/`_citation_scopes`/`_docx_usage_inventory`、`crossref_record`/`cached_crossref_record`、`provider_identity`/`validate_provider_identities`、`_crossref_fields`/`_crossref_authors`、`audit`、`_citation_population`、`crosscheck`、`main`。
- **输入输出**：输入 `papers/Pxx/manuscript/references.bib`、规范稿件 `main.tex`/`main.docx`、可选 `--manual-verifications`（每条须含 `verified_by/verified_at/source_url/title`）、项目内 `evidence/literature-api-ledger.jsonl` 与 `state/citation-metadata/*.json` 缓存。输出 `papers/Pxx/reviews/citation-audit.json`（`schema_version=1.0`）：`bibliography_sha256`、`manuscript_sha256`（TeX 用 `tex_sources.expand` 展开全部 `\input` 后的多文件摘要）、`findings[]`（status=`verified_crossref`/`verified_provider_identity`/`verified_manual`/`unverified`）、`citation_usage`（逐处 `usage_id`/`source`/`context`/`claim_text`/`missing_bibliography_keys`/`unused_bibliography_keys`）。
- **关键机制**：① 哈希绑定——`usage_id = sha256(json(binding))[:24]`、每文件 `sha256`、`cached_crossref_record` 的 `record_sha256` + 24h 缓存（**"never cache a bibliography PASS decision"**）+ symlink 防护 + `retrieved_at` 时间窗校验；`validate_provider_identities` 在源文件变化后令已存结论失效。② **真实公网调用**：`crossref_record` 走 `fetch_json("https://api.crossref.org/works/{doi}")`（默认 `network_safety.fetch_json`），`--offline` 跳过。③ 无 DOI 身份走 `provider_identity`：离线重放 `literature_evidence` 的 receipt，强制 `output_provenance.current_origin` 为 `deterministic-control-plane / scripts/literature_evidence.py`、receipt 为 `live_search` 成功、请求/最终 URL 与官方端点路径一致、raw/normalized 文件哈希一致、normalized works 能从原始响应重放，标题/年份/作者精确匹配且唯一。④ **fail closed**：BibTeX 宏/拼接、不平衡条目、未支持的 `\cite` 命令、无 key 的 DOI 超链接、DOCX 数字引用、CSL_CITATION、OMML 公式外内容、`CITATION` 字段未闭合、引用数 >5000、DOCX XML >10 MiB 一律拒绝或记 unresolved。⑤ `crosscheck`：两份**不同抽取器、不同文件、绑定同一原始来源**的抽取做机械字段比较，明确 `blindness_verified=False`、`bibliographic_truth_verified=False`、`semantic_support_verified=False`、`model_call_made=False`、`scientific_completion_verified=False`；writer 不得自封独立抽取器。⑥ `_citation_population` 只在能证明「完整字面 BibTeX 总体」时才给 `status=known`，否则保持 `coverage_unknown`。
- **依赖**：`research_artifacts`(sha/utc_now/path_in/read/write/bound_source)、`network_safety`(fetch_json/validate_https_url/NetworkSafetyError)、`tex_sources`(expand/comments/locate)、`literature_evidence`（大量常量与重放函数）、`output_provenance`(current_origin)、`literature_workbench`(_id/_text)、`literature_source_tasks`(citation_source/citation_extractions/judgment_responses)。
- **边界与限制**：`title_similarity < 0.75` 硬阈值；`--docx-citations-verified-by` 仅写历史注记字段，不参与判定（README 明确「不能替代映射或全文判断」）；明确不评估主张是否被引用支持、不验证许可/研究用途、不预测检测器、不证明人工撰写。

### 1.2 `claim_evidence.py`（189 行）

- **职责定位**：`"""Located citation evidence and recorded judgments, never automatic verification."""`——准备免费且可诚实保持不充分；判断由既有独立审查角色提供；人工抽检测一致性而非科学真理。无 CLI / 无 main，纯库。
- **对外能力**：`manuscript_usages(project, paper_id)`、`prepare(project, spec)`、`assess(project, packet, responses, labels=None)`、`build(project, spec)`；`OUTCOMES={"supports","contradicts","insufficient"}`。
- **输入输出**：spec `{schema_version=1.0,id,paper_id(Pxx),claims[1..500]{claim_id,claim,citation_key,library_id,evidence},sample_labels}`；读 `canonical_manuscript`、`references.bib`、文献库 `wb.CONFIG`、claim_fingerprint 绑定的人工抽检标签。输出 packet：`manuscript_sha256`/`bibliography_sha256`/`claims[]`/`citation_usages`/`uncovered_usages`/`claim_fingerprint`/`sample_claim_ids`/`sample_fraction=.15`；`assess` 追加 `spot_check{agreement,target_agreement:.85,target_met,...}`。
- **关键机制**：① **15% 抽检按科学引用范围选样**：`sample = sorted(claims, key=digest([population, usage_ids]))[:ceil(.15*n)]`，防「renamed duplicate claims」膨胀抽样总体；claim 文本必须经 `citation_prose` 归一化后与 `citation_key` 定位到**同一完整当前稿件引用范围**。② 哈希绑定：`claim_fingerprint`（含 manuscript_usages、evidence、source_basis）、标签 `sha256` + 指纹必须匹配、`output_provenance.current_origin` 要求 `provider=="human-attestation"` 且 tracked。③ 来源校验：DOI 格式、注册源 DOI/URL 与引用一致、`_registered_basis` 主源一致、`_full_text_available` 完整原文范围、`config_origin.model=="scripts/literature_registration.py"`。④ 角色隔离：支持/反驳结论必须有合法原文全文 + 定位证据；`insufficient` 必须给出实际证据缺口；保留 `disagreement` 与 `assessment_status`；`claim["outcome"]` 仅在单一结果且 `full_text_ready` 时采用，否则回落 `insufficient`。⑤ 固定不宣称：`semantic_support_verified/scientific_completion_verified/model_call_made/scientific_validity_verified=False`。
- **依赖**：`citation_audit`、`literature_workbench`(wb)、`research_artifacts`、`ref_verify_adapter`(canonical_manuscript)、`literature_source_tasks`(_anchors/_full_text_available/_library/judgment_responses)、`source_scope`(_registered_basis)、`output_provenance`。
- **边界与限制**：不引入 provider / downloader / 第二审查循环；`target_agreement=.85` 与 `sample_fraction=.15` 为**硬编码目标值**，代码不宣称已达成（README 明确「真实 0.85 一致性仍须实际研究验收」）；`a quote match never proves support`。

### 1.3 `cloud_checkpoint.py`（301 行）

- **职责定位**：`"""Hash-verified cloud checkpoints: small sources in Git, other results in Actions."""` 原始数据集从授权获取回执重水合（rehydrate），绝不上传；密钥/私有路径绝不归档；缺失/过期产物 fail closed。无 CLI / 无 main，纯库。
- **对外能力**：`relative`/`excluded`/`check_file`/`inventory`/`git_files`/`prepare`/`sync_billing`/`sync_experiment_reservation`/`download_archive`/`restore`；异常类 `CheckpointError`。
- **输入输出**：清单 `MANIFEST="state/cloud-checkpoint.json"`（`schema_version=1.0`,`run_id`,`created_at`,`artifact_name=research-checkpoint-{run_id}`,`archive_sha256`,`retention_days=90`,`files[{path,bytes,sha256,storage}]`,`raw_data_policy`）；输出 `checkpoint.zip`（`RUNTIME/checkpoint/`）与 Actions artifact。
- **关键机制**：① 分类：`DIRECTORIES`（17 个允许顶层目录）、`GIT_SUFFIXES`/`DATA_SUFFIXES` 白名单、`GIT_FILE_LIMIT=2MB`、`GIT_TOTAL_LIMIT=14MB`、`ARCHIVE_LIMIT=512MB`；`state/` 控制文件若超出 Git 上限直接报错 **"archive cannot replace authority"**（控制状态不得降级为 artifact）。② **凭据泄漏防护**：`SECRET_NAMES`（UUAPI_*/OPENAI_API_KEY/ANTHROPIC_API_KEY/DR_OS_*/GH_TOKEN 等约 30 个）+ 动态 `DR_OS_WATERMARK_KEY_*`，`check_file` 逐 1 MiB 块扫描文件内容是否含任何 ≥8 字节的密钥值，用 overlap 尾处理跨块命中；symlink 全路径拒绝。③ `prepare` 幂等：files 未变且 <60 天则复用旧 manifest（避免空闲 job 抖动，90 天过期前刷新）；**"previous checkpoint was not fully restored"** 阻止用更小 checkpoint 覆盖缺件旧归档。④ `restore` 先整体校验（条目数、文件名集合、非 symlink/目录、逐文件 `sha256`、大小、凭据扫描）再统一落盘——"Validate the entire archive before exposing any restored output"。⑤ `sync_billing`/`sync_experiment_reservation`：网络生成前把预留推送到远端 `cloud-state/{project}` 分支，runner 丢失后恢复阻塞预留；由 `DR_OS_REQUIRE_REMOTE_RESERVATION/DR_OS_STATE_WORKTREE/DR_OS_STATE_BRANCH/GITHUB_ACTIONS` 门控，失败即阻塞传输。
- **依赖**：`research_artifacts`(sha/walk_files)；外部命令 `git`（commit/push）、`gh run download`（`--repo hengyizang/lunwen` 硬编码）。
- **真实外部命令**：`subprocess.run(["git", ...])`、`subprocess.run(["gh","run","download",...])`（timeout=180）。
- **边界与限制**：`retention_days=90`/60 天刷新阈值硬编码；`prepare` 中 `json.loads(old_path.read_text())` 未捕获解析异常（manifest 损坏会抛 `JSONDecodeError` 而非 `CheckpointError`）；无 manifest 的旧项目 `restore` 静默返回（"can migrate without inventing missing evidence"）。

### 1.4 `cloud_continuation.py`（420 行）

- **职责定位**：`"""Evaluate owner-confirmed continuous work without granting gates or spending."""` 一个串行化云 job 跑一个有界 API 周期；成功工作可请求下一个 job；cron 只提供恢复唤醒；每个 job 重读项目、原始 owner 确认、精确约束、累计 ledger。
- **对外能力**：CLI `scheduled-request --event --output`、`enqueue-followup --decision`；函数 `task_profile`/`set_task_profile`、`configuration_errors`、`startup_report`、`evaluate`、`checkpoint`、`transition_ready_gate`、`scheduled_request`、`enqueue_followup`。
- **输入输出**：`POLICY=state/continuation.json`（`POLICY_FIELDS` 9 字段集合必须精确相等）、`STATUS=state/continuation-status.json`、`TASK_PROFILE=state/task-routing-profile.json`、`intake/constraints.json`；输出决策 `{project,should_run,reason,...}` 与 startup report（`paid_calls:0`）。
- **关键机制**：① owner 确认强校验：具名 `actor`/`confirmation_note`、过去且带时区时间戳、`constraints_sha256` 与 `g0_approval_artifact_sha256` 精确 64 位哈希；`intake/constraints.json` 当前哈希不等即 `constraints_changed_since_confirmation`。② **硬编码调度**：`system_execution_hours_per_day==24`、`resume_interval_minutes==15`、`stop_when=="all_papers_submission_ready"`，其它值直接 `ContinuationError`。③ G0/G1/G2 人工：G0 approval 校验，`G1/G2 → human_gate_pending`，`transition_ready_gate` 中 "human topic decisions cannot be reopened automatically"；自动闸门置 `decision_type="deterministic"`（不伪造人工）。④ 累计预算：`remaining = ceiling - spent - reserved`，≤0 → `cumulative_budget_boundary`；配置错误 → `configuration_pending`；上周期失败 → `previous_cycle_failed_requires_inspection`；`cloud_progress.pause_reason` 暂停。⑤ `configuration_errors` 复用 `ai_providers.configuration` 校验 strict model id、作者/critic 不同精确模型 ID、`DR_OS_MODEL_PRICING_JSON` 正有限 CNY 单价。⑥ `set_task_profile` 绑定当前 stage 与 `persistent-writer` 角色，经 `output_provenance.record_model_writes` 记录 `manager-task-declaration`，返回 `paid_calls_executed:0/budget_granted_cny:0/scientific_gate_approved:False`。
- **依赖**：`research_artifacts`(strict_json/sha)、`ai_providers`、`intake_validation`、`model_spend`、`researchctl`、`dynamic_routing`、`output_provenance`、`production_readiness`、`paper_execution`、`cloud_progress`、`cloud_job`(REPOSITORY/OWNER_ID/validate_request)。
- **真实外部命令**：`enqueue_followup` → `gh workflow run research-continuation.yml` 或 `gh api .../disable`；`scheduled_request` 严格校验 GitHub 事件（repo full_name、owner id、GITHUB_REF=refs/heads/main、event_name∈{schedule,workflow_dispatch}、手动触发者 id∈{OWNER_ID,41898282}）。
- **边界与限制**：**硬编码极重**：`project="my-phd"`、`actor="Hengyi Zang"`、bot id `41898282`、workflow 名、调度参数；`startup_report` 明确 `provider_authentication_verified=False`（"real authentication is not yet verified"）。

### 1.5 `cloud_human_acceptance.py`（224 行）

- **职责定位**：`"""Cloud-only software acceptance of human controls using synthetic projects."""`——不打开真实项目、不给 my-phd 授予科学闸门、不做任何模型/provider 请求。G3/G4 fixtures 测控制机制而非研究。
- **对外能力**：CLI `--directory <dir>`（无子命令），输出 `<dir>/acceptance.json`；函数 `request`/`review`/`decide`/`fixture`/`set_fixture_stage`/`quality_fixture`/`reproduction_fixture`/`run`。
- **输入输出**：构造 `projects/human-control-fixture/`，写 constraints（`model_api_budget_cny=300`）、`state["synthetic_acceptance_only"]=True`、dataset.csv/manifest/paper-contract/design/prereg/power/quality report、registry 4 个合成 run（含 `synthetic_acceptance_only:True`）、baseline/clean-room reproduction。
- **关键机制**：① 全文件合成标注（`Synthetic reviewer - software acceptance only`、`allow_paid:False`、`example.org` URL、假 `git_commit="a"*40`、假 `fingerprint="c/e"*64`、假 `image_digest="d"*64`、metric 0.8/0.79/0.82）。② 验收断言：G0 deterministic、incomplete G1 仍阻塞、自动质量确认/预注册冻结/复现确认通过**原始 validator**、`spend_control` 与 `intake` 哈希不变、`approved_gates` 恰为 `["G0","G1","G2"]`（证据确认不得授予 G3/G4）。③ `real_power=True` 时真调 `quality.create_power_report`（statsmodels）；`False` 时手写假 power 报告却仍写 `generated_by:"statsmodels"`/`engine_version:"0.15.0"`。④ `expected_sha256` 绑定 review dossier；`decision_log_sha256`/`spend_control_sha256` 留痕。
- **依赖**：`cloud_checkpoint`(cp.sha)、`cloud_human_controls`、`automated_quality`(G01)、`cloud_job`、`researchctl`、`research_quality`(quality)、`acceptance_scope.prepare_scope`(G01)。
- **边界与限制**：`run()` 临时改写 `researchctl.PROJECTS_ROOT`（try/finally 恢复，非线程安全）；`main()` 无异常转退出码；输出 `status:"pass"` 但 `scope:"synthetic software controls only"`、`scientific_completion_verified:False`、`paid_provider_calls:0`。

### 1.6 `cloud_human_controls.py`（388 行）

- **职责定位**：`"""Hash-bound owner decisions for cloud scientific gates; never calls a model."""` 仅由 `cloud_job` 的 owner issue 边界调用；review dossier 作为 run artifact 返回，不写进被哈希的科学证据。无 CLI / 无 main，纯库。
- **对外能力**：`selectors_for`/`validate_fields`/`_papers`/`_screen_inputs`/`_check_and_prepare`/`dossier`/`execute`；常量 `ACTIONS`（22 个操作）、`SELECTORS`、`DECISIONS`、`AUDIT="state/cloud-human-decisions.jsonl"`、`VOLATILE`。
- **ACTIONS 全集**：闸门 `ready/approve/advance/reopen`；质量 `freeze_preregistration/confirm_data_quality/confirm_reproduction/confirm_study_validation`；其它 `screen_literature, confirm_source_scope, confirm_review_packet, confirm_research_increment, start_revision, approve_supplemental, confirm_supplemental, retire_supplemental, approve_primary_retry, retire_primary_plan, approve_scope_amendment, reconcile_relay_guard, amend_operating_constraints`。
- **输入输出**：请求带 `expected_sha256`（64 位）+ `note`（10–500 字符）+ 各 selector；`dossier` 返回快照 + `review_sha256` + `blockers` + `ready_for_operation`；`execute` 写各操作产物并 append 一条 receipt 到 `AUDIT`。
- **关键机制**：① **dossier 哈希绑定**：snapshot 含 project/operation/actor/selectors/state/gate_artifact_sha256 + **`implementation`（`scripts/**.py`、`schemas/*.json`、`config/*.json`、`.github/workflows/*.yml` 全部 SHA-256）** + `files`（`cp.inventory` 排除 `VOLATILE`/`api_runs`/`.cache`）——"an upgrade requires a new human review"。② `execute` 复算 dossier，哈希不等或 blockers 非空即拒绝；"Prepare all requested freezes before writing any of them"。③ 闸门操作：`approve` 要求 `status==awaiting_approval` 且 `ready_gate/ready_artifact_sha256` 匹配当前 `artifact_hash`（防 "artifacts changed after ready"）；`advance` 要求 approval 不 stale；G5 scoped 到 active_paper。④ 证据决定要求匹配闸门开放（G1 screen_literature、G3 冻结/数据质量、G4 复现/研究验证）。⑤ **owner 认证**：仅当调用方传 `owner_authorization` 才调 `cloud_job.authenticated_owner_event` 校验当前认证 GitHub 事件；否则 `actor_identity={"source":"local_operator_declaration","verified":False}`。⑥ 产物 `output_provenance.record_model_writes(..., provider="deterministic-cloud-human-control", model="scripts/cloud_human_controls.py", role="human-reviewed-control")`；receipt 含 `paid_calls:0`、`scientific_completion_verified:False`、outputs 哈希、state_before/after。
- **依赖**：`cloud_checkpoint`、`output_provenance`、`researchctl`、`research_quality`(quality)；按 action 动态导入 `operating_constraints`/`relay_guard`/`primary_recovery`/`scientific_scope`/`reviewer_rounds`/`supplemental_experiments`/`research_increments`/`review_packets`/`literature_evidence`/`study_routes`/`source_scope`/`cloud_job.authenticated_owner_event`。
- **边界与限制**：`dossier` 中 `amend_operating_constraints` 的 `prepare` 被调用两次（preview + `_check_and_prepare`）；G2 approve 的 `next(x for x in state["paper_topic_approvals"] ...)` 无匹配会抛 `StopIteration`；`approval_effect` 明确 "No decision is recorded by generating this dossier"。

### 1.7 `cloud_job.py`（841 行）——本组最关键文件

- **职责定位**：`"""Owner-only GitHub issue control plane for a single cloud research job."""` 所有云端 action 的唯一入口与编排器。
- **对外能力**：CLI `schema`（导出 JSON Schema）、`validate-event --event --output [--github-output]`、`execute --config --run-id`、`comment --issue --summary`。函数 `validate_request`/`literature_operation`/`issue_request`/`job_schema`/`restore_state`/`persist_state`/`git`/`run_command`/`authenticated_owner_event`/`run_job`/`cycle_command`/`main`。
- **action 全集**（`EXTRA` keys）：`review_dossier`、全部 `cloud_human_controls.ACTIONS`、`preflight`、`acceptance`、`free_jev_probe`、`bocha_jev_probe`、`init`、`status`、`authorize_budget`、`reconcile_budget`、`authorize_data`、`resume`、`cycle`、`continuation`、`routing_status`、`set_routing_profile`、`accept_route`、`paperqa`、`tooluniverse`、`auxiliary`、`literature`。
- **输入输出**：GitHub issue body 中的 `MARKER + ```json fenced 块`（≤16000 字节，`unique_pairs` 拒重复 JSON 属性）；输出 `.runtime/cloud-artifact/` 下 `failure.json`、`redacted-log.txt`、`tracked-results.zip`、各 action receipt、`cloud-summary.md`、`GITHUB_STEP_SUMMARY`、`continuation-followup.json`。
- **关键机制**：① **身份/角色隔离**：`issue_request` 严格 owner-only（`OWNER_ID=163310614` 同时校验 repo owner 与 issue user、非 PR、标题前缀 `[research-cloud]`）；`authenticated_owner_event` 绑定真实 GitHub 事件与 `GITHUB_RUN_ID`，"never the displayed actor"；`literature_feedback_review` 在 mutation boundary 二次认证（"A model-authored operation cannot supply this authority"）。② **累计预算**：`spending_boundary` 检查 `ceiling - spent - reserved <= 0` 拒绝并置 `DR_OS_REQUIRE_MODEL_AUTH=1`/`DR_OS_REQUIRE_REMOTE_RESERVATION=1`；`authorize_budget`/`reconcile_budget` 走 `model_spend`。③ **状态持久化**：`restore_state`/`persist_state` 用 git worktree + `cloud-state/{slug}` 分支；`finally` 保证 `cloud_checkpoint.prepare` + `persist_state`，失败时「control-only recovery push」只保留 billing/continuation 保守状态。④ **真实付费周期启动点**：`cycle_command` 生成 `scripts/api_orchestrator.py cycle ... --planner-provider {codekey-kiro-enterprise|uuapi-anthropic} --writer-provider {cheapai-gpt-pro|uuapi-openai} --critic-provider ...`，context 明确 "Keep Claude read-only and OpenAI as the persistent author"、"Do not approve or advance a human gate, change spending authority, or auto-submit"；`production` profile 由 `DR_OS_ROUTING_PROFILE=production` 决定。⑤ `run_command` 只允许 `scripts/*.py` 入口、`python -m`、遵守 `DR_OS_CLOUD_JOB_DEADLINE_EPOCH`、输出截断 50000 字并做密钥脱敏。⑥ **失败留痕**：`failure.json` 含 status/phase/execution_started/checkpoint_persisted/diagnostic；summary 明确 "G1/G2 topic decisions require the owner"、"Software receipts do not establish scientific completion"。⑦ `acceptance` 校验固定版本 `paper-qa 2026.08.12`/`tooluniverse 1.5.1`/`ref-verify 1.2.0` 并跑 `live_acceptance.py`（6 个文献 provider + docker 容器）。
- **依赖**：`ai_providers`、`cloud_checkpoint`、`cloud_continuation`、`cloud_human_controls`、`model_runtime`、`model_spend`、`researchctl`、`cloud_retry`、`cloud_research_steps`、`cloud_progress`、`cloud_runtime`、`automated_quality`、`literaturectl`、`dynamic_routing`、`model_routing`、`production_readiness`、`paper_qa`、`ai4science_evidence`、`research_operations.FIELDS`。
- **真实外部命令**：`git ls-remote/fetch/push`（走 `cloud_retry.run`）、`git worktree add/remove`、`gh api ... comments`、`python -m scripts.*` 子进程。
- **边界与限制**：`init` 强制 `paper_count==6`（"the supported doctoral workflow requires exactly six papers"）；`PAID={"cycle","continuation","paperqa","tooluniverse","auxiliary"}` 命名"付费"但 `run_job` 主要用作「需 restore_state 的 action 集合」；`except Exception:` 宽捕获但 `finally` 保证 checkpoint；`free_jev_probe` 需 `OPENROUTER_API_KEY`（零额度专用 key），`bocha_jev_probe --live` 走真实 Bocha 传输探针。

### 1.8 `cloud_pipeline_acceptance.py`（197 行）

- **职责定位**：`"""Two-runner cloud acceptance using explicitly synthetic, non-research fixtures."""` 验证 checkpoint 恢复、失败尝试不自动重试、负结果保留、控制状态只读、原生导出链。
- **对外能力**：CLI `{produce|consume} --directory`；函数 `fixture`/`print_executor_diagnostics`/`produce`/`consume`。
- **输入输出**：`runner-one/acceptance-fixture`（measure.py 故意产出一个 negative `-0.5` 与一个 failure；尝试写 `state/run.json` 以验证控制状态只读）→ `transfer/{checkpoint.zip,git/,hashes.json,produce.json}` → `runner-two` 恢复 → `acceptance.json`。
- **关键机制**：① 失败/负结果留痕：`-0.5` 负结果、`failed.txt` 失败证据、`registry.jsonl` 哈希不变（"failed attempt was automatically retried" 即报错）、`state/run.json` 哈希不变。② 哈希绑定：`cp.prepare/restore`、全文件 `hashes.json`、`export_sha256`、`checkpoint_sha256`。③ **真实本地渲染链**：`publication_figures.render`（从 `results/negative.csv` 出 png/svg/pdf）、`manuscript_docx.build`（`prefer_pandoc=False` 原生 DOCX）、python-docx 加表格/符号/图/分页、`word_render.render`（PDF）、`fitz` 校验 PDF 文本、`revision_render.validate_render_manifest`、`cloud_runtime.compile_tex`（P02）、TeXLive PDF 页位置索引。④ 来源标注：`output_provenance.record_model_writes(..., provider="synthetic-fixture", model="none", role="acceptance-only")`。
- **依赖**：`cloud_checkpoint`、`cloud_research_steps`、`output_provenance`、`live_acceptance.DEFAULT_IMAGE`、`acceptance_scope`、`publication_figures`、`manuscript_docx`/`docx`、`word_render`、`revision_render`、`cloud_runtime`、`fitz`(PyMuPDF)。
- **边界与限制**：注释明确 "These artifacts never enter my-phd and cannot satisfy any scientific evidence or human review gate"；`os.environ['GITHUB_RUN_ID']` 直接索引（CI 必需）；`requirement_ids=['R25','R26','R31']`、workflow URL `hengyizang/lunwen` 硬编码；`main()` 无异常转退出码。

### 1.9 `cloud_progress.py`（379 行）

- **职责定位**：`"""Record actual activity and stop repeated work that has no new inputs."""` 停滞检测 / 防重复工作 / 成本归属。无 CLI / 无 main，纯库。
- **对外能力**：`human_inputs`/`work_inputs`/`experiment_attempts`/`_amount`/`decision_resources`/`resource_snapshot`/`snapshot`/`external_blockers`/`record`/`pause_reason`/`resume`；`FILE="state/continuation-progress.json"`、`MAX_CONTROL_CYCLES=12`、`MAX_STALLED_CYCLES=2`。
- **输入输出**：`snapshot(slug)` 返回 `scope/errors/gate_error_groups/experiment_attempts/resource_snapshot/receipts/human_inputs/work_inputs/notebook_sha256`；`record` 写 FILE；`pause_reason` 返回 `{reason,blockers,...}`；`resume` 追加 `state/continuation-resumes.jsonl` 并重置状态。
- **关键机制**：① **防重复**：`progressed = errors 减少 or 新 receipts or work_inputs 变化`；无进展累加 `control_cycles`/`stalled_cycles`，达阈值 `control_retry_limit`/`no_new_research_inputs`；`human_inputs` 只由 3 个控制面文件重置——"Draft timestamps and audit wording do not establish new scientific evidence"；`pause_reason.next_action` 明确 "a clock wakeup or rephrased draft does not restart work"。② **成本归属**：`decision_resources` 把 `model_runtime.ledger_entries` 与 cycle_id 关联，区分 `verified_charge`/`estimated_or_calculated`/`pending_reservation`/`unknown`；"No API usage rows match this cycle; absent usage is not zero cost"、"CLI subscription charges are not measured by the API ledger"。③ 哈希绑定：`usage_sha256`（校验 prior ledger 未变，否则 "cannot be isolated"）、`receipt_sha256`、`notebook_sha256`、`work_inputs`/`human_inputs`；`resume` 要求 status 文件精确哈希 + 10–500 字符 note。④ 独立审查：`research_notebook.cycle_assessment`，status∈{independently_observed,independently_reviewed,historically_reviewed} 才产生语义进展记录，否则 `decision.status="pending"`；`scientific_progress_verified:False`/`scientific_gain_verified:False`。⑤ 失败留痕：`experiment_attempts` 含所有 attempt（含归档），"Keep failed attempts too"。
- **依赖**：`researchctl`、`research_artifacts`、`paper_execution`、`research_phase`、`primary_recovery`、`model_runtime`、`model_spend`、`experiment_runner`(accounted_run_cost)、`literature_evidence`、`literature_model_screening`、`research_notebook`、`cloud_continuation`(STATUS)。
- **边界与限制**：`automatic_kinds` 排除集合硬编码（数据权利/质量/复现/图视觉/文献筛选为自动）；JCR 来源需求作为外部 blocker；`MAX_CONTROL_CYCLES/MAX_STALLED_CYCLES` 硬编码。

### 1.10 `cloud_recovery.py`（551 行）

- **职责定位**：`"""Owner-authorized cloud recovery: evidence, bounded retries and tested rollback."""`——无模型调用、无科学决定、无实验重放、无任意补丁；特权代码总来自 main；失败运行产物是惰性 JSON。
- **对外能力**：CLI `--event <path> [--inspect] [--validation-output <path>]`；函数 `api`/`blob`/`trusted_run`/`checks_pass`/`rollback`/`authority`/`report_blocker`/`safe_report`/`classify`/`bounded`/`incident_fingerprint`/`alert`/`resume`/`propose`/`verify_pending`/`merge_pending`/`failure_report`/`setup_retry`/`handle_failure`/`validation_request`/`capability_probe`/`run`。
- **输入输出**：`config/cloud-recovery.json`（policy）、`state/cloud-recovery.json`（events/alerts/seen/pending）、`failure.json` artifact（≤50 KB、非 symlink）、GitHub PR / branch / issue / workflow dispatch。
- **关键机制**：① **极度保守 policy**：`model_calls_allowed is False`、`external_paid_compute_usd==0`、`max_incident_recoveries==2`、`max_daily_recoveries==4`、`project=="my-phd"`、`owner_id==OWNER_ID`，任一不符报错。② `trusted_run` 校验 run 的 path/head_branch/repo/actor id/head_sha/event；`checks_pass` 要求 `REQUIRED` **11 个 CI 检查名**全部 success。③ **AST 级窄回滚**：`ALLOWED={"scripts/cloud_runtime.py":"prepare","scripts/manuscript_docx.py":"_python_docx"}`；`rollback` 只替换一个函数体，签名/imports/其它函数/protected statements 的 `ast.dump` 必须完全一致；`propose` 在最近 12 个 revision 中找 CI 验证过的 helper 并创建 PR；`verify_pending` 校验 PR 身份/单文件/内容哈希；`merge_pending` 用 `force=False` fast-forward 合并（其他 writer 移动 main 则被 GitHub 原子拒绝）。④ `classify`：`environment_retry`（transient 且 execution 未开始）/`rollback:{path}`/`inspection_required`；`setup_retry` 仅当执行步骤 `skipped` 且失败仅 `actions/checkout|setup-python@v7` 时重放旧 job。⑤ `alert` 用中文 issue 告警（marker 去重），明确「没有增加预算、重发模型请求、重跑正式实验或批准科学关卡」；`AUXILIARY_CHECKPOINT_PRESERVED` 辅助任务不自动付费重试。⑥ `capability_probe` 真实创建**永不合并的 draft PR** 后关闭并删分支，实测 Actions 权限。
- **依赖**：`cloud_job`、`cloud_continuation`、`cloud_progress`、`cloud_checkpoint`、`model_spend`、`researchctl`、`cloud_retry`(redact/transient)、`paper_execution.artifact_path`。
- **真实外部命令**：`gh api`（issues、pulls、git/refs、git/commits、git/trees、actions/runs、actions/workflows/*/dispatches、rerun-failed-jobs、contents，含 GET/POST/PATCH/DELETE）、`gh run download`、`git worktree`。
- **边界与限制**：**硬编码密集**：`REPO`、OWNER_ID、bot `41898282`、`my-phd`、11 个 REQUIRED 名、2 个 ALLOWED 函数、policy 数值、12 revisions、64 MB artifact / 50 KB failure.json、`validate.yml`；`run()` 直接索引 `GITHUB_RUN_ID`；自动恢复能力实际极窄（多数故障仅告警人工）。

### 1.11 `cloud_recovery_acceptance.py`（45 行）

- **职责定位**：`"""One receipt for existing software suites; real integration runners stay separate."""` 为既有 unittest 套件生成单一回执。
- **对外能力**：CLI `--suite {recovery,cost-quality} --output`；`SUITES` 映射 `recovery → tests.test_cloud_retry + tests.test_cloud_recovery`，`cost-quality → tests.test_cost_optimization.LosslessContextTests/CostRuntimeTests`。
- **输入输出**：要求 `GITHUB_ACTIONS=true` 或 `DR_OS_CLOUD_EXECUTOR=1`；输出 receipt `{status,tests_run,failures,errors,skipped,model_calls:0,external_paid_compute_usd:0,production_state_mutated:False,scientific_completion_verified:False}`；`cost-quality` 另加 `fixture_only=True,real_paid_model_calls=0,network_requests=0,scientific_quality_or_actual_cost_savings_verified=False,real_model_families_or_routing_not_evaluated=True`。
- **边界与限制**：纯软件/合成验收，`not result.skipped` 也计入 pass 条件（有 skip 即 fail）；明确不评估真实模型家族/路由或实际成本节省。

### 1.12 `cloud_research_steps.py`（604 行）——确定性步骤的最大扇出点

- **职责定位**：`"""Bounded, deterministic research work around the API author/critic cycle."""` 科学批准保留在受保护记录中；生成的计划只**请求**工作，不能授予数据权利、伪造检索回执或授权实验。无 CLI / 无 main，纯库，由 `cloud_job`/`api_orchestrator` 周期前后调用。
- **对外能力**：`read`/`write`（原子 `os.replace`）/`path_in`/`fresh`/`literature_context`/`authorize_data`/`acquire_data`/`_cloud_run_eligible`/`resume_experiments`/`before_cycle`/`after_write`；`REPORT="state/research-steps.json"`、`AUTHORIZATIONS="state/data-authorizations.json"`、`MAX_DATA_BYTES=2_000_000_000`、`ResearchStepError`。
- **输入输出**：`before_cycle(project, stage)` 与 `after_write(project, stage)` 读写 `state/research-steps.json`；`program/cloud-operations.json`（≤16 个 operation）、`program/literature-search-plan.json`、`data/manifests/*.json`、`state/cloud-operations-cache.json`；`program/*.json` 文献操作请求。
- **关键机制**：① `literature_context`：1–60 条显式 searches、`max_search_calls` 默认 12（1–60）、7 天 `fresh`（校验 raw/normalized 响应哈希）、失败 6h 冷却、按 `provider/query/request_url/query_family` 命中缓存、`literature_evidence.execute_search`（**真实公开文献 API**）、去重后 `works[:90]` 预览并保留 `work_count`/`works_omitted`；固定 `bounded_metadata_only:True`、`human_screening_required:False`、`model_screening_required:True`、`novelty_proven:False`、明确的 `next_query_guidance`（"fallback suffixes do not establish saturation"）。② `authorize_data`：owner/`deterministic_control_plane` 授权，要求 `expected_sha256` 精确、`dataset_fetch.validate_manifest` 通过；`economic_scope` 走「唯一完整 source-bound observation request」分支；写 `AUTHORIZATIONS` 时固定 `license_review_performed:False`、`research_use_rights_verified:False`（许可仅可选元数据，AGENTS 规则 7/11）；automated 需 `actor=="deterministic_control_plane"`。③ `acquire_data`：自动 source binding 或复用已授权，`dataset_fetch.download_dataset`（**真实 HTTPS 下载**），校验 `sha256` + `expected_bytes ≤ 2 GiB`，已存在文件变化则 "downloaded dataset changed; inspect it before reacquiring"；独立论文模式只取当前 paper contract 的 datasets。④ `resume_experiments`：`experiment_runner.approved_plan`、registry 与 executor receipt 必须逐条一致、输出哈希未变；`exploratory` 分支走 `research_phase.exploration_execution`，失败经 `primary_recovery.automatic_retry` 判定；`_cloud_run_eligible` 要求 container/docker、`cloud_runtime.execution_window`、无 `resource_errors`、`empirical_workflow.cloud_outputs_allowed`；**一次真实 attempt/checkpoint per job**；成功后 `experiment_evidence.refresh` 统计证据。⑤ `before_cycle`：按 stage 触发 `acquire_data`、supplemental 审批/确认、experiment-execution 的恢复与 `research_quality.refresh_runtime_evidence_catalog`。⑥ `after_write`：先 `research_operations.run_builder` 再按 action 分派 20 余种确定性 builder（见下），operation 用 `operation_sha` 缓存避免重复构建；每个 operation 异常记 `operation_errors` 不中断其它；末尾对 writing-and-review 做 `supplemental.automatic_confirmation` 后检；"never treat model output as a receipt"。
- **`after_write` 分派表（本组与全仓的关键接口）**：`data_contract→data_contracts.refresh`、`empirical_design/empirical_reporting`、`economic_data.execute`、**真实网络**、`data_quality/power→research_quality`、`derive_figure_data→figure_provenance.derive`、`render_figure→publication_figures.render + figure_provenance.register_rendered_figures`、`read_paper→paper_reader`、`docx→manuscript_docx.build`、**`citation_audit→citation_audit.audit + research_artifacts.record`（组内直接调用 #1.1）**、`research_increments`、`increments_inventory→incremental_writing`、`research_extensions`、`evidence_context`、`retrieve_evidence→evidence_retrieval.refresh`（`automatic_source_exclusion:False,paid_calls:0`）、`watermark_cleanup`、`ccfa_*→ccfa_runtime.execute`、`AUTOMATED_OPERATIONS→literaturectl.execute_operation`、`citation_graph→literature_evidence.execute_citation_graph`、`triage_leads→lead_triage.triage`、**`direction_search→web_research.search`（真实公网搜索）**；未知 action 一律 "operation is unsupported in this stage; no arbitrary commands or approvals are allowed"。
- **依赖**：`cloud_checkpoint`、`dataset_fetch`、`experiment_runner`、`literature_evidence`、`research_operations`(AUTOMATED_OPERATIONS/run_builder)、`paper_execution`；函数内动态导入 `direction_evidence`/`data_contracts`/`citation_audit`/`economic_data`/`empirical_design`/`empirical_reporting`/`research_quality`/`figure_provenance`/`publication_figures`/`paper_reader`/`manuscript_docx`/`research_increments`/`incremental_writing`/`research_extensions`/`evidence_context`/`evidence_retrieval`/`watermark_cleanup`/`manuscript_hygiene`/`ccfa_runtime`/`literaturectl`/`lead_triage`/`web_research`/`supplemental_experiments`/`research_phase`/`primary_recovery`/`experiment_evidence`/`empirical_workflow`/`cloud_runtime`。
- **边界与限制**：90 works 预览 / 12 默认检索 / 7 天 fresh / 6h 冷却 / 2 GiB / 16 operations / 每周期最多 1 个 direction_search（3 queries）硬编码；`direction_search`/`read_paper`/`citation_graph`/`triage_leads` 为真实网络或需授权全文；与 `direction_evidence` 存在模块级循环依赖（见 2.3）。

### 1.13 `cloud_retry.py`（73 行）

- **职责定位**：`"""Bounded retries of explicitly idempotent cloud infrastructure operations."""` 绝不用于模型调用、实验执行或整个 job。
- **对外能力**：`redact`/`transient`/`run`；`ATTEMPTS=3`、`DELAYS=(2,8)`、`TRANSIENT`/`PERMANENT` 正则。
- **输入输出**：`run(command, operation, cwd, receipt, timeout=240)` 每次尝试 append 一条 JSONL 回执（at/operation/attempt/exit_code/retry/diagnostic[-3000:] 已脱敏）。
- **关键机制**：仅允许 `git-ls-remote/git-fetch/git-push`（`command[:2]` 匹配、无 `--force`/`+` 前缀）或 3 个固定 pip 安装命令（`pinned-runtime-install`、`figure-retrieval-runtime`、`literature-paperqa-runtime`，其中 `paper-qa==2026.8.12`）；只对 transient 错误重试；`redact` 脱敏名称含 KEY/TOKEN/SECRET/PASSWORD/EMAIL 且值 ≥8 字节的环境变量，并替换 URL 中 `user:pass@`。
- **边界与限制**：固定安装 extras 硬编码；`cloud_job.py` 期望 `paper-qa==2026.08.12` 而此处为 `2026.8.12`（数值等价、字符串不一致）；`raise AssertionError("unreachable")` 作为循环兜底。

### 1.14 `cloud_runtime.py`（151 行）

- **职责定位**：`"""Provision the declared cloud toolchain and compile TeX without host secrets."""`
- **对外能力**：`execution_window`/`prepare`/`compile_tex`；`PACKAGES` 10 个包、`DEFAULT_TEX_IMAGE`（硬编码 `ghcr.io/xu-cheng/texlive-small@sha256:f6a0...`，注释标明 2026-10-01 检查 + 来源 URL）。
- **输入输出**：`prepare` 写 `state/cloud-runtime.json`（python/platform/versions/docker_available/disk_free/cpu/available_resources/container_engines/requested_runs/request_errors/experiment_limits/`model_credentials_in_experiment_environment:False`）；`compile_tex` 写 `papers/Pxx/reviews/cloud-tex-build.json` + `manuscript/main.pdf` + render manifest。
- **关键机制**：① `prepare` 用 `cloud_retry.run` 装 `.[figures,reader,research-quality,reference-tools]`，探测 `runner_capabilities`（docker/podman），读 `experiments/plan.json` 的 runs 计算 `requested_resources`/`readiness_errors`。② `compile_tex` 要求 `GITHUB_ACTIONS` 或 `DR_OS_CLOUD_EXECUTOR=1`；`output_provenance.require_final_origins`（源必须当前非 Claude 来源）；绑定 manuscript/figures/tables/supplement 全部输入哈希、拒 symlink；镜像必须匹配 `ghcr.io/xu-cheng/texlive-(small|full)@sha256:[64]` 正则；`docker run` 严格沙箱（`--network=none --read-only --cap-drop=ALL --pids-limit=256 --cpus=2 --memory=4g --security-opt no-new-privileges --tmpfs /tmp --mount ... readonly`），`env` 只保留 `PATH/LANG/LC_ALL/TZ`（**不带宿主密钥**）；`latexmk -no-shell-escape`；输入未变校验；成功后 `record_model_writes(model=image)` + `build_render_manifest`。③ `execution_window` 遵守 controller deadline 留 120s checkpoint 余量，无 deadline 默认 1200s、上限 604800s。
- **依赖**：`cloud_research_steps`(path_in/write)、`output_provenance`、`cloud_checkpoint`(sha)、`cloud_retry`、`experiment_runner`(container_user/runner_capabilities/...)、`paper_execution`、`revision_render`。
- **边界与限制**：`human_visual_review_required:True`（只标记不验证）；TeX 镜像/资源限制/超时（300s）/日志尾 20000 硬编码；真实 `pip install`（网络）与 `docker run`（隐含镜像拉取）。

### 1.15 `concept_illustrations.py`（83 行）

- **职责定位**：`"""Optional GPT Image conceptual illustrations; never use for measured results."""` **付费图像生成被禁用**，直到有单独验证的图像路由具备中央预算预留/对账/身份支持；ChatGPT-web 下载需人工导入，脚本不借用会话；所有图片在人工视觉检查与单独批准前保持 UNREGISTERED。
- **对外能力**：CLI `--project --paper --stem --prompt-file --source {gpt-image-api,chatgpt-web} --model [--source-file] [--execute]`；`prepare`/`_png`/`main`。
- **输入输出**：`source=gpt-image-api` → `{dry_run:True,available:False,notice:"No paid request sent..."}`（execute=True 直接抛错）；`chatgpt-web` → 写 `papers/Pxx/figures/{stem}.png` + `.image-source.json` receipt。
- **关键机制**：PNG magic 校验 + ≤20 MB；receipt 含 `prompt_sha256`/`output_sha256`/`model_identity_note:"user-reported"`/`not_experimental_evidence:True`/`human_visual_review_required:True`；`output_provenance.record_model_writes(family="openai")`；状态 `unregistered-pending-human-review`。
- **边界与限制**：**无任何真实付费 API 调用**（明确 fail closed）；`--execute` help 自述 "legacy option; paid image generation currently fails closed"；对应 AGENTS 规则 10「GPT Image 可出单独标注的概念插图，绝不作为数据图」——付费路径未实现。

### 1.16 `context_efficiency.py`（190 行）

- **职责定位**：`"""Lossless text preparation and explicit discovery navigation; no source edits."""` 上下文无损压缩与独立审查包隔离。
- **对外能力**：`discovery_navigation_index`/`operational_path`/`instruction_paths`/`_compact_json`/`lossless_text`；常量 `OPERATIONAL_PREFIXES`（约 17 个运行/缓存/报告前缀）、`REVIEW_PREFIXES`、`INSTRUCTION_FILES`、`OPERATIONAL_FILES`。
- **输入输出**：`discovery_navigation_index` 输入 `data/discovery-broad-auto-*.json` + `source_sha256`，输出紧凑 JSON（每个候选的 `start_line/end_line` + provider/provider_id/doi/landing_url/screening_status/license_status/fitness_status 经 value_table 编码、`omitted_candidate_count:0`）；`lossless_text` 返回 `(rendered, method)`，method∈{None,`"json-whitespace-compacted"`}。
- **关键机制**：① **无损**：`_compact_json` 只删 JSON 格式空白，**不反序列化/重序列化数值**（防四舍五入/指数变化/改变受保护科学字符串）；JSONL 用 `split("\n")` 而非 `splitlines()`（防字面 U+2028 破坏）。② 角色隔离：`operational_path(exclude_reviews=True)` 从独立 critic 的 source packet 排除历史内部判断与调用信封；`instruction_paths` 除固定文件外还扫描 `program/**.json`，识别 `desired_verdict`/`preferred_verdict`、research_iteration/frontier/search_tree、ccfa_/literature_/figure_ action、task+skill、task+tool_ids+input_bindings、operation+request 等**诱导性/调用性信封**（即使 owner 用自定义文件名）。③ `discovery_navigation_index` 用 `research_artifacts.json_field_spans` 定位 candidates 并 `raw_decode` 逐条校验与原 receipt 一致，明确 `scientific_completeness_verified:False`、"This index does not establish full-text reading, scientific fitness or permission"。
- **依赖**：`research_artifacts`(json_field_spans)；由 G01 的 `api_orchestrator` 用于上下文装配。
- **边界与限制**：文件名正则 `data/discovery-broad-auto-\d{8}T\d{12}Z\.json`、4 MB program 文件大小上限硬编码；这是「无损空白压缩」，不实现语义精简，也不宣称节省比例（README 明说「40–50% 精简是未经证实的历史估计」）。

### 1.17 `contribution_reporting.py`（211 行）

- **职责定位**：`"""Review-ready contributions within the existing paper-facts authority."""` 检查当前定位事实与实际执行器输出，不判断科学价值；无 prose 生成、无模型调用、无实验、无独立 ledger、无批准。
- **对外能力**：`contribution`/`audit`/`feedback`；`ROLES`（empirical/meta-analysis/theoretical/qualitative 各自的 fact roles）、`TEXTS`、`RESULTS`（supported/partially_supported/not_supported/contradicted/inconclusive）。
- **输入输出**：`feedback` 读 `papers/Pxx/reviews/paper-facts.json`；`audit` 输出 status/claims/errors/outcome_binding/implementation_sha256/`paid_model_calls:0`。
- **关键机制**：① 严格字段与身份校验：`research_identity` 的 `design_family`∈PRIMARY|SECONDARY、`research_kind` 一致、reporting `kind` 必须与 design_family 的 `expected_kind` 匹配；fact_roles 精确匹配 `ROLES[kind]`，每个 value 必须出现在绑定事实的 `verbatim_evidence` 中，`_fact` 校验 excerpt 在源文件中且源路径不能是 `state/`/`reviews/`/`reports/`（不得自引审计）。② 执行绑定：`figure_provenance.run_seal` 的 successful outputs；measured roles（finding/magnitude/uncertainty/comparison/proof 等）必须来自 declared sealed outputs。③ 预注册：`expectation_review` 绑定 frozen `preregistration.json` 的 `planned_source`/`planned_quote`，`observed_status` 必须等于 `link["result_status"]`，decision∈{retain,narrow,reframe,unsupported}；**not_supported/contradicted/inconclusive 不得 retain 原成功叙事**（负结果留痕）。④ 创新性：`program/novelty-claim-matrix.json` 的 `closest_work_ids` 必须有完整 3 轴 source-located 比较；schema 1.1 时经 `results_validation.claim_outcomes`/`validate_result_statuses`（"cannot reuse a manuscript's self-reported outcome"）。
- **依赖**：`research_artifacts`、`research_identity`、`figure_provenance`(run_seal)、`research_extensions`(comparison)、`results_validation`。
- **边界与限制**：`semantic_support_verified/scientific_contribution_verified/scientific_completion_verified=False`；4 MB fact 源、50 executions、40 错误截断、5000 字符文本、3 axes 硬编码；`feedback` 的 instruction 明确 "this is not a preferred review verdict"。

### 1.18 `cost_audit.py`（165 行）

- **职责定位**：`"""Deterministic cost diagnostics. Never remove scientific reviews or call models."""`
- **对外能力**：CLI `--project <slug>`（写 `state/cost-audit.json` 并打印）；`_role`/`_amount`/`_recorded_cost`/`_uncertain_billing`/`portfolio_forecast`/`summarize`/`refresh`。
- **输入输出**：读 `model_runtime.ledger_entries` / `budget_status`、`state/run.json`、`state/runs/*/journal.json`；`REPORT="state/cost-audit.json"`。
- **关键机制**：① `_recorded_cost` 把 `zero_cost_not_confirmed`、`cost_status` 以 unknown/accounted_upper 开头的记录视为**未知而非免费**（"A failed controlled request writes a zero placeholder while its real reservation remains outstanding"）。② `summarize` 按 `(stage,paper_id,role,provider,model,endpoint,billing_quote_sha256,billing_identity,cache_key)` 分组找重复付费请求候选，action 恒为 "inspect purpose and receipts; never skip automatically"；`independent-critic`/`endpoint-health` 计为 `fresh`（同输入可合理需要新评估），cache_hit 跳过。③ `portfolio_forecast` 三种场景（few_iterations/planning_example/many_iterations）基于观测 min/median/max，**"never a promise about papers, quality or elapsed days"**；默认 6 篇、每 ordinary cycle 3 calls、每篇额外 5 calls（1 planner + 1 writer + 3 critic）。④ CLI/订阅用量单独记账（"don't report it as free merely because an API usage ledger has no corresponding rows"）。
- **依赖**：`model_runtime`、`research_artifacts`、`api_orchestrator.project_root`(G01)。
- **边界与限制**：`scientific_success_or_acceptance_predicted/duplicate_candidates_prove_waste/savings_or_scientific_equivalence_proven=False`、`no_model_calls=True`、`no_routing_or_approval_changes=True`；场景参数/角色关键词/assumptions 硬编码。

### 1.19 `data_cleaning_runtime.py`（249 行）

- **职责定位**：`"""Standalone offline cleaning command for an already approved cloud run."""` **设计为复制到实验项目内独立运行**（无 `scripts` 包依赖），声明本文件、contract 及所有 contract 源为冻结输入；原生 runner 验证 G3 与精确命令后启动；无原生包依赖、网络、模型调用、自动样本选择或科学批准。
- **对外能力**：CLI `--contract --dataset-id --output --receipt [--dataset-registry]`；`_sha`/`_safe`/`_read`/`_binding`/`_dataset_registry`/`_number`/`_check`/`validate_steps`/`transform`/`execute`。
- **输入输出**：`data/contracts/{id}.json`、`data/manifests/{id}.json`、`data/*.csv`、dataset registry（canonical 或 `experiments/papers/Pxx/datasets.jsonl` 快照）→ `data/processed/*.csv` + `reports/data-cleaning/*.json` receipt。
- **关键机制**：① **自哈希绑定**：`contract["cleaning_runtime_sha256"] == _sha(Path(__file__))`，替换清洗实现即失败。② 三方一致：canonical manifest == registered dataset、input CSV 哈希 == `manifest.download.sha256`。③ 路径 `_safe` 拒绝 `\`/`:`/绝对路径/`..`/symlink/逃逸；≤64 MB、≤1,000,000 行。④ **仅 4 种确定性操作**：`rename`/`normalize_missing`/`linear_unit_conversion`/`exclude_values`，明确 "no arbitrary code or automatic trimming"；steps ≤100、Decimal 512 位精度、拒绝非有限/过长/大指数数值、日期须 canonical ISO、required 列不得缺。⑤ 输出/receipt 与所有输入路径不相交、拒绝覆盖不同已生成产物（幂等）；receipt 含 inputs、`implementation_sha256`、`controller_implementation_sha256`、rows_before/after、每步 history、`raw_input_unchanged:True`、`scientific_validity_verified/data_rights_verified/gate_approved=False`；执行前重校验全部 input binding。⑥ 依赖环境变量 `RESEARCH_OS_RUN_ID`（已批准 executor run）。
- **依赖**：无 scripts 包依赖（标准库）；被 `data_contracts.clean`/`preview` 调用。
- **边界与限制**：64 MB / 1,000,000 行 / 100 steps / 4000 字符 / 128 字符数值 / precision 512 硬编码；这是「冻结 G3 计划内的确定性清洗命令」，不是通用数据工具。

### 1.20 `data_contracts.py`（425 行）

- **职责定位**：`"""Variable dictionaries, bounded CSV diagnostics and approved cleaning steps."""` 审计只读不改数据；清洗复用当前 G3-approved runner contract；不授予访问/批准/样本选择权/科学认证。
- **对外能力**：CLI `{audit|clean|preview} --project-root --dataset-id [--output --receipt]`；`_load`/`audit`/`refresh`/`validate_saved_report`/`_preview`/`preview_cleaning`/`validate_preview`/`clean`；`MAX_BYTES=64MB`、`MAX_ROWS=1,000,000`、`TYPES`。
- **输入输出**：`data/contracts/{id}.json`（schema 1.0，含 manifest/input/variables/joins/cleaning_steps，可选 panel）→ `reports/data-contracts/{id}.json`、`data/processed-preview/{id}.csv`、`reports/data-cleaning/preview-{id}.json`、clean 的 processed CSV + receipt。
- **关键机制**：① **双实现哈希绑定**：`cleaning_implementation_sha256 == sha(data_contracts.py)` 且 `cleaning_runtime_sha256 == sha(data_cleaning_runtime.py)`；canonical manifest == registered dataset、input CSV 哈希 == manifest.download.sha256。② 只读全扫描（`complete_scan:True`/`data_mutated:False`）：列类型/缺失/非法值、`_panel`（unit/time/完整 calendar、`balance_policy`、treatment timing 的 `causal_identification_verified:False`）、`_joins`（one_to_one/many_to_one 基数、match_rate、`join_executed:False`——只诊断不执行）。③ `preview_cleaning` 要求 `GITHUB_ACTIONS`/`DR_OS_CLOUD_EXECUTOR=1`、open G3 `experiment-design`、registry 为空（实验尝试后不能改数据）、保护他人 frozen 输入、旧 recipe 归档到 `preparation-history/` 不覆盖。④ `clean` 要求 `RESEARCH_OS_RUN_ID`、`approved_plan` 中 exact run 的 `expected_outputs == {output, receipt}`、所有 contract 源必须声明在 approved run inputs，然后调 `cleaning.execute`。⑤ `validate_preview`/`validate_saved_report` 复算并校验 `output_provenance.current_origin` 为 `deterministic-control-plane`。
- **依赖**：`research_artifacts`、`data_cleaning_runtime`(cleaning)、`paper_execution`(artifact_path/dataset_snapshot/enabled)、`experiment_runner`(approved_plan)、`output_provenance`；被 `cloud_research_steps.after_write` 的 `data_contract` action 调 `refresh`。
- **边界与限制**：`scientific_validity_verified/data_rights_verified/gate_approved/experiment_executed=False`；30 missing codes / 10000 calendar / 5,000,000 cells / 20 joins / 4000 文本硬编码。

### 1.21 `data_discovery.py`（588 行）

- **职责定位**：`"""Discover public dataset metadata without asserting license or fitness for use."""` 对应 AGENTS 规则 15（发现元数据只是待核验线索）与规则 7（许可/研究用途是可选元数据，非前置门槛）。
- **对外能力**：CLI `<query> [--query ...] [--provider ...] [--limit 15] [--max-candidates 250] [--output] [--project]`；`SEARCHERS` 映射 8 个 provider：`datacite`/`zenodo`/`huggingface`/`openml`/`figshare`/`dryad`/`dataverse`/`datagov`；`discover_many`/`discover`/`save_report`/`append_search_log`。
- **真实公网 API 调用点（8 个，全部 `network_safety.fetch_json`）**：`api.datacite.org/dois`、`zenodo.org/api/records`、`huggingface.co/api/datasets`、`www.openml.org/api/v1/json/data/list`、`api.figshare.com/v2/articles/search`（POST + json_body）、`datadryad.org/api/v2/search`、`dataverse.harvard.edu/api/search`、`catalog.data.gov/api/3/action/package_search`。均非付费、无需密钥。
- **输入输出**：`_candidate` 统一字段，`license_status="unverified_requires_source_evidence"`、`fitness_status="candidate_only"`、URL 必须 https://；`discover_many` 输出 schema 1.1（`providers`/`raw_candidate_count`/`candidates`/`ranking_note`/`warning`），`discover` 输出 schema 1.0；`append_search_log` 写 `evidence/dataset-search-log.jsonl`。
- **关键机制**：`ThreadPoolExecutor(max_workers≤12)` 并发 query×provider；`_dedupe_key`（DOI 或 landing_url）、`also_found_by`；`_rank_candidate` 分数 = 查询词覆盖率×62 + 标题词×4 + 短语 18 + DOI 5 + license 4 + 跨源 6 + version 3（上限 100），**明确"not evidence of scientific fitness, data quality, license validity, novelty"**；单 provider 失败不影响其它（记 status=error）；`--project` slug 校验拒绝 `/ \ ..`。
- **边界与限制**：queries ≤12、limit 1–100、max_candidates 1–2000、250 默认候选硬编码；评分权重全硬编码；README「数据发现与获取」章节示例即此 CLI。

### 1.22 `data_row_provenance.py`（320 行）

- **职责定位**：`"""Complete, source-bound row provenance without changing or exporting raw rows."""` 既有 dataset contract / manifest / owner 授权仍是权威；定位的元数据不是源真相、人工验证或 G3。
- **对外能力**：`prepare`/`build`/`refresh`/`validate_saved_report`/`csv_text`；`REQUEST="program/data-row-provenance.json"`、`OUTPUT="reports/data-row-provenance"`、`STATES={pending,located,disputed}`（**无 verified**）、`ISSUES` 6 种。
- **输入输出**：`program/*.json` 或 `data/row-provenance/*.json` 声明（≤8 MB）→ `reports/data-row-provenance/{dataset_id}/{rows.json,rows.csv,manifest.json}`。
- **关键机制**：① **不导出原始值**：只出 `row_sha256`/`key_sha256`、物理 CSV 行范围（用 `csv.reader.line_num` 保留 quoted multiline rows）、status/sources/issues；`raw_values_exported:False`、`digests_are_not_anonymization:True`。② `_url` 用 `validate_https_url` + 拒绝 query 中凭据参数（api_key/token/key/signature/password/secret/...）+ 拒绝 localhost/.local/.internal/非公网 IP，并**明确不做 DNS 或抓取**（"do not perform DNS or fetch a URL while recording it"）；`source_url_resolved:False`。③ 状态机：located 必须有实际 collection time + bound material + ≥1 source；disputed 必须有 ambiguous/conflict；每个 missing cell 必须显式解释；unresolved 不能标 located；"no automatic verified status"。④ 哈希绑定：`_row_identity`、`declaration_sha256`、`implementation_sha256`、`fingerprint`、`seal_manifest`/`validate_manifest`、全部 inputs 重校验、owner authorization 的 `_digest(permission)` 变化检测。⑤ `_csv_cell` 防 CSV 公式注入。
- **依赖**：`data_contracts`、`dataset_fetch`(validate_manifest)、`network_safety`(validate_https_url)、`research_artifacts`(seal_manifest/validate_manifest/json_digest)、`literature_workbench`(_snapshot/validate_anchor/_json)。
- **边界与限制**：`human_verified/scientific_validity_verified/model_call_made/data_rights_granted/gate_approved=False`；8 MB / 30 sources / 10 key_columns / `issues ≤ len(fields)*4` 硬编码。

### 1.23 `dataset_fetch.py`（279 行）

- **职责定位**：`"""Validate and safely download a source/version-bound public dataset over HTTPS."""`
- **对外能力**：CLI `validate <manifest>` / `download <manifest> <destination> [--accept-license] [--max-bytes] [--overwrite]`；`load_manifest`/`https_url`/`validate_manifest`/`safe_filename`/`file_sha256`/`download_dataset`。
- **输入输出**：manifest 必填 12 字段（schema_version/dataset_id/title/provider/source_url/version/accessed_at/download/provenance/unit_of_analysis/split_strategy/known_limitations）；`download.sha256` 为 64 hex 或 `"pending"`、`expected_bytes` 非负整数或 null、`license` 可选（对象或 null）。输出下载文件 + stdout JSON（path/bytes/sha256/source_url）。
- **关键机制**：① `require_public_https_url`（DNS 解析后拒绝私有地址，防 SSRF）+ `PublicHTTPSRedirectHandler` 校验重定向后 URL 仍公网 HTTPS；`User-Agent: DoctoralResearchOS/0.2`；timeout=60；**无登录凭据**。② 真实网络下载：`urllib.request` 打开公网 HTTPS（`fetch` 非付费 API）；Content-Length 预检 + 流式累计 `total > max_bytes`（默认 5 GiB）拒绝。③ 哈希绑定：下载完校验 SHA-256（`"pending"` 时打印 "record this SHA-256 in a reviewed manifest before G3"）+ expected_bytes；临时文件 + `os.replace` 原子落盘，finally 清理；不覆盖已存在文件（哈希匹配则直接返回）。
- **依赖**：`network_safety`(validate_https_url/require_public_https_url/PublicHTTPSRedirectHandler)；被 `cloud_research_steps.acquire_data`、`data_row_provenance`、`data_contracts` 调用。
- **边界与限制**：**`download_dataset` 的 `accept_license` 参数在函数体内完全未被使用**，`--accept-license` help 自述 "Legacy annotation; licence approval is not required"（占位/遗留）；不绕过付费墙/验证码/访问控制（靠公网 URL 白名单式校验）；原始数据由 `cloud_checkpoint` 排除出 Git。

### 1.24 `detector_feedback.py`（94 行）

- **职责定位**：`"""Optional detector-feedback editing ledger with strict scientific preservation."""` 用户提供的检测器分数可引导有界编辑 pass；不宣称检测器准确；实际来源保持内部；绝不自动改写或认证人工作者身份。对应 AGENTS 规则 25。
- **对外能力**：CLI `--before --after --feedback --output [--prepare]`；`_style`/`prepare_revision`/`evaluate`。
- **输入输出**：feedback JSON（schema 1.0、detector_name/version、direction、before/after 的 `{sha256,score}`）；输出报告 JSON。
- **关键机制**：哈希绑定 before/after 文本、`score` 0–100；`tokens`/`multiset_delta` 检查受保护 token（数字/引用等）变化，`scientific_integrity_review_required = protected`；`improved` 按 lower_is_better/higher_is_better；`new_style_errors`（复用 `academic_style.analyze_text` 行级 findings 前 30 条）；`accept_automatically:False`、`disclosure_must_remain:False`、`human_review_required:True`；warning "Detector score is not a reliable authorship verdict; lower score never overrides G5 evidence, integrity"。
- **依赖**：`revision_integrity`、`manuscript_language`、`academic_style`(G01)。
- **边界与限制**：**不调用任何检测器 API**（分数完全由用户 JSON 提供，代码只记录/比较）；无真实网络/付费调用；0–100 分制/30 findings/instructions 硬编码。

### 1.25 `diagram_mermaid.py`（106 行）

- **职责定位**：`"""Export the existing evidence-bound diagram topology as editable Mermaid."""` 无 prose-to-causal 推断、无 JS renderer、无模型调用、无图批准。
- **对外能力**：`text`/`build`/`refresh`/`validate_saved_report`；`OUTPUT="reports/diagram-mermaid"`；无 CLI / 无 main。
- **输入输出**：request `{schema_version=1.0,id,source{path,sha256},story_ref}`（≤64 KB、`program/` 前缀）→ `reports/diagram-mermaid/{id}/{report.json,diagram.mmd,index.html,manifest.json}`。
- **关键机制**：① 来源绑定：`editable_figures._bound_file`、`output_provenance.current_origin` 要求 `family != "anthropic"`（"diagram source needs current non-Claude author provenance"）、`editable_figures._story_alignment`（story_ref 必须是既有 source-bound figure brief）、`research_diagrams.validate(ir)`。② `text` 生成 `flowchart LR`，causal `==>` / association `-.-` / control `-->`，phase 前缀默认 `"unreviewed"`，HTML 转义。③ `index.html` 用 CSP `default-src 'none'` **不加载 JS 渲染器**，只展示源码文本。④ `seal_manifest`/`validate_manifest` 哈希绑定、`matches_origin` 保护已改动输出。
- **边界与限制**：`mermaid_runtime_validation:"not_rendered"`（**未渲染验证**）、`scientific_approval:False`、`human_visual_review_required:True`、`model_call_made:False`、`paid_calls:0`；`confirmation_required` 每条 edge 需确认科学含义；64 KB / program 前缀 / flowchart LR / marker 映射硬编码。

### 1.26 `direction_evidence.py`（271 行）

- **职责定位**：`"""Collect dated primary-source receipts and recompute the owner's direction rubric."""` 分数只是人工评审辅助；计数描述抽样窗口而非总市场；缺失证据绝不获得编造的中性分数。G1 选题情报。
- **对外能力**：`PageText`(HTMLParser)/`canonical_url`/`primary`/`fetch_sources`/`support`/`band`/`number_supported`/`rank`/`refresh`/`validate_saved`；`DirectionEvidenceError`。
- **输入输出**：`program/direction-assessments.json` → `evidence/direction-sources/{index.json,*.txt,*.html}` → `program/direction-ranking.json`。
- **关键机制**：① **真实网络抓取**：`fetch_sources` 用 `network_safety.fetch_bytes(url,max_bytes=4_000_000)`，要求 HTTP 200、`final_url` 仍在 `config/direction-primary-domains.json` 白名单；7 天缓存 + 提取文本 `.txt` 与原始 `.html` 双哈希；`support` 要求 0–14 天新鲜度、双哈希一致、quote（≥12 字符）在检索页面归一化文本中精确出现。② `number_supported`：薪资/汇率数字必须在引用段落中出现（防编造）。③ `rank`：owner `ranking_weights` 必须精确匹配 `intake_validation.WEIGHT_FIELDS` 且 ∈[0,1] 总和为 1；观察窗口 ≤90 天、结束不晚于今天且距今 ≤14 天；≥3 个候选；`cloud_feasible`/`no_future_lab_dependency`/`authorized_data_plan`/`cloud_compute_plan`；每个 eligible observation 需 kind、eligibility_rationale、`constraints_sha256` 绑定 intake；薪资需 gross/同 career_stage/CNY 或带 dated fx 证据；`band` 分档（[1,5,15,30,60]、薪资 [100000,200000,300000,500000,800000]）。④ 敏感性分析：每 factor 权重 ×0.8/×1.2 重排。⑤ 不宣称：`novelty_is_a_tradeable_score:False`、`human_review_required:True`、status 为 `ready_for_human_review`（非"已完成"）、`salary_limits`/`sample_limits`；`assessment_sha256`/`source_ledger_sha256` 绑定。
- **依赖**：`network_safety`、`cloud_research_steps`(path_in/read/write)、`cloud_checkpoint`(sha)、`intake_validation.WEIGHT_FIELDS`、`config/direction-primary-domains.json`；被 `cloud_research_steps.after_write`（topic-intelligence）调 `refresh`。
- **边界与限制**：80 URLs / 4 MB / 7 天缓存 / 14 天新鲜度 / 90 天窗口 / 3 候选 / bands / multipliers 硬编码；与 `cloud_research_steps` 存在**模块级循环依赖**（本文件顶层 import 其 path_in/read/write，对方在函数内延迟 import 本文件 refresh）。

### 1.27 `docx_revision.py`（387 行）

- **职责定位**：`"""Real OOXML insertions/deletions with verified accept/reject round trips."""` 文本编辑保留未变字段、公式、图片；未变字段/公式可移动；正文与表格单元格增删用段落标记；资源/样式/节边界/表格拓扑不能由此有界工作流修订；复杂对象绝不转纯文本。
- **对外能力**：`canonical`/`neutral_property`/`document_xml`/`resolve`/`inline_units`/`unit_key`/`complex_unit`/`complex_inventory`/`Tracker`(class)/`track`/`build`/`validate_saved_report`；**无 CLI / 无 main**（纯库，被 G5 修订流程调用）。
- **输入输出**：`papers/Pxx/reviews/revision-base/main.docx`(baseline)、`manuscript/main.docx`(current)、`reviews/response-matrix.csv` → `submission-materials/revision/{clean.docx,tracked.docx,response-matrix.csv,changes.md}` + `reviews/docx-revision.json`。
- **关键机制**：① `track` 比较 Word 包全部部件（除 `document.xml` 外必须完全相同）、拒绝已存在 `ins/del/moveFrom/moveTo`、body 用 `SequenceMatcher` on `canonical` 块做 diff、`complex_inventory` 保证复杂字段/公式/图片/范围标记不被扁平化；**accept/reject 往返验证**：`canonical(resolve(new,True)) == canonical(clean)` 且 `canonical(resolve(new,False)) == canonical(old)`，不满足即抛错。② `Tracker.paragraph` 拒绝 drawing 移动导致重复 ID、段落属性变化、pPr 格式变化、**run formatting 变化（rPrChange 未实现，明确 fail 而非伪装成 prose）**、复杂字段跨段落；`Tracker.blocks` 表格拓扑冻结。③ `build` 前置 `revision_integrity.audit(paper)["errors"] + revision_trace.validate_saved_report(paper)`；`record(...)` 登记来源；输出 `accept_equals_clean:True`/`reject_equals_baseline:True`/`visual_review_required:True`。④ `validate_saved_report` 用 `verify_files` 复验全部 inputs/outputs 哈希并再次做 accept/reject 往返。⑤ `document_xml` 用 `resolve_entities=False,no_network=True` 防 XXE。
- **依赖**：`lxml`（第三方）、`research_artifacts`(sha/read/write/record/path_in/verify_files)、`revision_integrity`(word_package/audit)、`revision_trace`。
- **边界与限制**：能力被严格限定（不支持格式/样式/节/表拓扑修订、图片移动若造成重复 drawing ID 会拒绝）；`revision_author="Doctoral Research OS"`、各路径硬编码；文件头明确 "Visual inspection in Word remains required"。

---

## 2. 本组整体归纳

### 2.1 整体能力（6 个能力簇）

1. **云端作业控制面（最核心）**：`cloud_job` 作为 owner-only GitHub issue 单入口，把 `validate-event / execute / schema / comment` 与 20 余种 action 统一到一套 `EXTRA`/`SELECTORS` 校验表；`cloud_continuation` 决定是否继续、`cloud_progress` 防重复、`cloud_checkpoint` 持久化状态、`cloud_retry` 幂等重试、`cloud_runtime` 装配环境——构成「一个串行化云 job 跑一个有界 API 周期」的完整闭环。
2. **人工决定与控制边界**：`cloud_human_controls`（22 类操作、哈希绑定 dossier 含全仓实现哈希）、`cloud_recovery`（有界重试 + AST 窄回滚 + PR 验证合并）、`cloud_human_acceptance`/`cloud_pipeline_acceptance`/`cloud_recovery_acceptance`（纯合成软件验收）。G1/G2 人工闸门、G3/G4 证据确认、预算/约束修订都走「先出 dossier → owner 复核精确哈希 → 执行」。
3. **确定性研究步骤编排**：`cloud_research_steps` 是 `api_orchestrator` 周期前后的「确定性手脚」——`before_cycle`（数据获取、supplemental 审批、实验恢复、统计证据刷新）、`after_write`（20 余种 operation 分派到全仓 builder）。它是本组与几乎全部其它 scripts 模块的**最大扇出点**。
4. **数据供应链**：`data_discovery`（8 家公开元数据 API 线索）→ `dataset_fetch`（清单校验 + 安全 HTTPS 下载）→ `data_contracts`（变量字典/全扫描诊断）→ `data_cleaning_runtime`（冻结计划内确定性清洗）→ `data_row_provenance`（行级溯源）。全程哈希绑定、源/版本三方一致、许可仅作可选元数据、绝不导出原始行。
5. **G5 引用·主张·贡献·成本·修订证据链**：`citation_audit`（引用身份 + 双抽取交叉）、`claim_evidence`（15% 抽检 / 0.85 目标）、`contribution_reporting`（sealed outputs + novelty matrix + 负结果）、`cost_audit`（成本诊断，不预测成功）、`detector_feedback`（可选编辑账本）、`docx_revision`（OOXML 跟踪修订）、`diagram_mermaid`（可编辑拓扑导出）。
6. **上下文与概念插图**：`context_efficiency`（无损压缩 + 独立审查包隔离）、`concept_illustrations`（付费图像路径禁用，仅本地导入）、`direction_evidence`（G1 方向主来源评分）。

### 2.2 在 G0–G5 中的位置

| 阶段 | 本组承担 |
|---|---|
| G0 | `cloud_human_controls`/`cloud_job` 的 `authorize_budget`、`cloud_continuation.evaluate` 的 G0 确认与约束哈希校验；`direction_evidence` 属 G0 之后的「选题情报」支撑 |
| G1 | `direction_evidence.refresh`（带日期主来源 + owner 权重 + 敏感性）、`cloud_research_steps.after_write` 的 `direction_search`/`triage_leads`/`citation_graph`/`read_paper`；人工闸门不自动推进 |
| G2 | `cloud_human_controls` 的 G2 `approve`（须 `paper_id`）、`cloud_continuation` 的 `human_gate_pending`；不代填选题 |
| G3 | `data_contracts.preview_cleaning`/`clean`、`data_cleaning_runtime`、`cloud_human_controls.freeze_preregistration/confirm_data_quality`、`cloud_research_steps.before_cycle` 的数据获取与 `resume_experiments` 前置；计划/预算哈希封存由 G01 组控制 |
| G4 | `cloud_research_steps.resume_experiments`（一次真实 attempt/checkpoint per job）、失败/负结果留痕、`cloud_progress.experiment_attempts`、`confirm_reproduction/confirm_study_validation`、`statistical_evidence` 刷新 |
| G5 | `citation_audit`（引用与数值核验）、`claim_evidence`（逐主张证据）、`contribution_reporting`、`cost_audit`、`detector_feedback`、`docx_revision`、`diagram_mermaid`、`cloud_pipeline_acceptance` 的导出链；`cloud_human_controls` 的 `start_revision`/`confirm_review_packet`；**绝不自动投稿**（`submission_package` 在后续组） |

贯穿全部阶段的横切机制：累计预算（预留/对账/边界）、哈希绑定（稿件树、实现、receipt、输入）、来源校验（`validate_https_url`/SSRF 防护/凭据扫描）、角色隔离（Claude 只读、OpenAI 持久写入、`family != anthropic` 校验、writer 不得自封独立抽取器）、失败与负结果留痕（`failure.json`/`acceptance.json`/`AUDIT`/registry）。

### 2.3 组内调用关系（本组 27 文件之间）

```
cloud_job.py  ──顶层──> cloud_checkpoint / cloud_continuation / cloud_human_controls / cloud_retry
              ──函数内──> cloud_research_steps(acquire_data,authorize_data) / cloud_progress(pause_reason,snapshot,record,resume)
              / cloud_runtime(prepare) / automated_quality(checked_run) / literaturectl / dynamic_routing / model_routing
              / production_readiness / paper_qa / ai4science_evidence / research_operations.FIELDS

cloud_continuation ──函数内──> cloud_job(REPOSITORY,OWNER_ID,validate_request) / cloud_progress(pause_reason)
cloud_progress     ──函数内──> cloud_continuation(STATUS)
cloud_human_controls ──函数内──> cloud_job(authenticated_owner_event) ; 顶层 -> cloud_checkpoint, output_provenance, researchctl, research_quality
cloud_human_acceptance ──> cloud_checkpoint, cloud_human_controls, cloud_job, automated_quality(G01), researchctl, research_quality
cloud_pipeline_acceptance ──> cloud_checkpoint, cloud_research_steps, cloud_runtime, output_provenance
cloud_recovery ──顶层──> cloud_job, cloud_continuation, cloud_progress, cloud_checkpoint, model_spend, researchctl, cloud_retry
cloud_recovery_acceptance ──> (unittest 套件，无本组直接调用)
cloud_retry ──被──> cloud_job.git / cloud_runtime.prepare / cloud_recovery(transient,redact)
cloud_runtime ──顶层──> cloud_research_steps(path_in,write), cloud_checkpoint(sha), experiment_runner ; 函数内 -> cloud_retry, revision_render
cloud_research_steps ──顶层──> cloud_checkpoint, dataset_fetch, experiment_runner, literature_evidence, research_operations
                     ──函数内──> direction_evidence.refresh / data_contracts.refresh / citation_audit.audit /
                                  economic_data.execute / empirical_design / empirical_reporting / research_quality /
                                  figure_provenance / publication_figures / paper_reader / manuscript_docx /
                                  research_increments / incremental_writing / research_extensions / evidence_context /
                                  evidence_retrieval / watermark_cleanup / manuscript_hygiene / ccfa_runtime /
                                  literaturectl / lead_triage / web_research / supplemental_experiments / primary_recovery /
                                  experiment_evidence / empirical_workflow / cloud_runtime(execution_window)
citation_audit ──> research_artifacts, network_safety, tex_sources, literature_evidence, output_provenance,
                   literature_workbench, literature_source_tasks ; 被 claim_evidence 与 cloud_research_steps 调用
claim_evidence ──> citation_audit, literature_workbench, ref_verify_adapter, literature_source_tasks, source_scope
context_efficiency ──> research_artifacts ; 被 G01 的 api_orchestrator 用于上下文装配
contribution_reporting ──> research_identity, figure_provenance(run_seal), research_extensions, results_validation
cost_audit ──> model_runtime, api_orchestrator.project_root(G01)
data_contracts ──顶层──> data_cleaning_runtime(cleaning), research_artifacts ; 被 data_row_provenance 与 cloud_research_steps 调用
data_row_provenance ──顶层──> data_contracts, dataset_fetch, network_safety, research_artifacts, literature_workbench
data_discovery ──> network_safety, research_artifacts(utc_now)
dataset_fetch ──> network_safety ; 被 cloud_research_steps.acquire_data / data_contracts / data_row_provenance 调用
detector_feedback ──> revision_integrity, manuscript_language, academic_style(G01)
diagram_mermaid ──> editable_figures, research_diagrams, literature_workbench, research_artifacts, output_provenance
direction_evidence ──顶层──> cloud_research_steps(path_in,read,write), cloud_checkpoint(sha), network_safety, intake_validation
docx_revision ──> lxml, research_artifacts, revision_integrity(word_package/audit), revision_trace
concept_illustrations ──> output_provenance, publication_figures(PROJECTS_ROOT/safe_file/sha256_file)
```

**值得注意的循环依赖（均为「顶层单向 + 函数内延迟反向」，运行时可工作但耦合高）**：
- `cloud_research_steps` ↔ `direction_evidence`（对方顶层 import 其 `path_in/read/write`，己方在 `after_write` 内延迟 import 对方 `refresh`）。
- `cloud_job` ↔ `cloud_continuation`（前者顶层 import 后者，后者在 `scheduled_request`/`enqueue_followup` 内延迟 import 前者）。
- `cloud_continuation` ↔ `cloud_progress`（互在函数内延迟 import）。

### 2.4 与 G01 及后续组的依赖

- **依赖 G01 已读模块**：`ai_providers`（配置/生产 provider 表）、`api_orchestrator`（`project_root`、被 `cycle_command` 以子进程调用）、`automated_quality`(G01)、`academic_style`(G01)、`acceptance_scope.prepare_scope`(G01)、`research_artifacts`（全组通用）、`output_provenance`/`network_safety`/`tex_sources`/`intake_validation`/`researchctl`/`model_spend`/`model_runtime`（这两个不在本组范围，属后续组字母序之后？实为 `model_*` 在 m 段，属后续组）。
- **被后续组大量依赖**：`cloud_research_steps.after_write` 是全仓 builder 的集中分派点（data/empirical/figure/manuscript/evidence/ccfa/literature/watermark 等）；`citation_audit`、`claim_evidence`、`data_*`、`contribution_reporting`、`cost_audit`、`docx_revision` 又被 G5 的 `manuscript_audit`/`submission_package`/`review_packets` 等引用。
- **本组是「控制面 + 数据供应链 + 证据链」的混合段**，不含模型适配器本体（在 G01）、不含实验运行器本体（`experiment_runner`，后续组）、不含投稿打包（`submission_package`，后续组）。

---

## 3. 特别标注汇总

### 3.1 真实网络 / 付费 API 调用点

| 类型 | 位置 | 说明 |
|---|---|---|
| **真实付费 API 周期（启动点）** | `cloud_job.cycle_command` → `scripts/api_orchestrator.py cycle` | 本组**不直接发 HTTP**，而是生成并执行付费 API 周期命令（planner/writer/critic 三 provider）。`spending_boundary`/`cycle_command` 先检查累计剩余额度并置 `DR_OS_REQUIRE_MODEL_AUTH`/`DR_OS_REQUIRE_REMOTE_RESERVATION`。真正的 Claude/OpenAI 端点在 G01 的 `ai_providers.py` |
| 真实付费/计量动作 | `cloud_job` 的 `paperqa`/`tooluniverse`/`auxiliary`/`literature` action | 各执行对应脚本；`tooluniverse` 注释称 "credential-free UniProt SDK path, zero model/API cost"；`free_jev_probe` 需专用零额度 `OPENROUTER_API_KEY`；`bocha_jev_probe --live` 真实 Bocha 官网传输探针 |
| 真实 live 验收 | `cloud_job` 的 `acceptance` | 跑 `live_acceptance.py literature`（openalex/crossref/arxiv/europe-pmc/dblp/hal）+ `container --engine docker` |
| 真实公网 API（非付费） | `citation_audit.crossref_record` | `https://api.crossref.org/works/{doi}`，24h 哈希缓存，`--offline` 跳过 |
| 真实公网 API（非付费，8 家） | `data_discovery.SEARCHERS` | DataCite/Zenodo/HuggingFace/OpenML/Figshare(POST)/Dryad/Harvard Dataverse/Data.gov，12 线程并发 |
| 真实网络下载（非付费） | `dataset_fetch.download_dataset` | `urllib.request` 打开公网 HTTPS，SSRF 防护 + 5 GiB 上限 + SHA-256 校验 |
| 真实网络抓取（非付费） | `direction_evidence.fetch_sources` | `network_safety.fetch_bytes` 抓白名单 primary-domain 网页，4 MB 上限 |
| 真实网络（builder 触发） | `cloud_research_steps` | `literature_evidence.execute_search`/`execute_citation_graph`、`web_research.search`(direction_search)、`economic_data.execute`、`dataset_fetch.download_dataset` |
| 真实计费查询（可选） | `cloud_job preflight --billing_provider` | `production_readiness.report(check_billing=True)` |
| **真实远端写（git/gh CLI）** | `cloud_checkpoint`(git push / `gh run download`)、`cloud_continuation`(`gh workflow run` / `gh api .../disable`)、`cloud_recovery`(大量 `gh api` GET/POST/PATCH/DELETE)、`cloud_job`(`git ls-remote/fetch/push`、`gh api comments`)、`cloud_pipeline_acceptance`(无) | 全部为 GitHub 远端状态/PR/issue/workflow 操作 |
| 真实本地网络/容器 | `cloud_runtime.prepare`(`pip install .[extras]`)、`compile_tex`(`docker run` + TeXLive 镜像) | 无宿主密钥、无网络容器 |
| **明确禁用/无付费** | `concept_illustrations`(gpt-image-api fail closed)、`cloud_human_acceptance`/`cloud_pipeline_acceptance`/`cloud_recovery_acceptance`(合成夹具)、`claim_evidence`/`cost_audit`/`context_efficiency`/`contribution_reporting`/`data_cleaning_runtime`/`data_contracts`/`data_row_provenance`/`detector_feedback`/`diagram_mermaid`/`docx_revision`/`cloud_progress`/`cloud_retry`/`cloud_human_controls` | 均无模型/付费调用；`data_row_provenance._url` 明确不做 DNS/fetch |

### 3.2 TODO / 占位 / 未实现 / 硬编码

- **未实现 / 占位**：
  - `dataset_fetch.download_dataset(accept_license, ...)`：参数**完全未使用**；`--accept-license` help 自述 "Legacy annotation; licence approval is not required"。
  - `concept_illustrations`：GPT Image 付费路径 `source=="gpt-image-api"` 恒返回 `available:False` / "No paid request sent"，execute=True 直接抛错；`--execute` 是 legacy option。
  - `diagram_mermaid`：`mermaid_runtime_validation:"not_rendered"`，不做 Mermaid 渲染，index.html 用 CSP 禁用 JS。
  - `docx_revision`：`rPrChange`（run 格式变更跟踪）明确未实现，遇之直接 fail。
  - `cloud_human_controls.dossier`：`approval_effect` 为「仅生成 dossier 不记录决定」；`amend_operating_constraints` 的 `prepare` 被调两次。
  - 大量**固定立场占位字段**（全仓风格）：`*_verified=False`、`model_call_made=False`、`paid_calls=0`、`status:"retired"/"pending"/"awaiting_*"`、`scientific_completion_verified=False`、`gate_approved=False`、`data_rights_verified=False`、`human_review_required=True`。
  - 代码中**未见 `TODO`/`FIXME` 字面**，但存在大量「显式禁用/未验证」路径（如上）。
- **硬编码（密集，换环境需改多处）**：
  - 身份/仓库：`OWNER_ID=163310614`、`REPOSITORY="hengyizang/lunwen"`、bot id `41898282`、`project="my-phd"`、`actor="Hengyi Zang"`、分支 `cloud-state/{slug}`、workflow 名 `research-continuation.yml`/`cloud-research.yml`/`cloud-repair-validation.yml`/`validate.yml`、`gh run download --repo` 仓库名。
  - 调度/policy：24 小时/15 分钟/`all_papers_submission_ready`、`max_incident_recoveries=2`、`max_daily_recoveries=4`、`model_calls_allowed=False`、`external_paid_compute_usd=0`、`init paper_count==6`。
  - 阈值：`citation_audit` 相似度 0.75 / 5000 引用 / DOCX 10 MiB / 24h 缓存 / 抽取 2 MB；`claim_evidence` 15% / 0.85；`cloud_checkpoint` 2 MB / 14 MB / 512 MB / 90 天 / 60 天；`cloud_progress` 12 / 2；`cloud_recovery` 12 revisions / 11 个 REQUIRED 检查 / 2 个 ALLOWED 函数 / 64 MB / 50 KB；`cloud_retry` 3 次 /(2,8)s；`cloud_runtime` 镜像 digest / 1200s / 120s margin / 300s / 20000 日志；`data_*` 64 MB / 1,000,000 行 / 100 steps / 8 MB / 30 sources；`data_discovery` 评分权重 / 12 queries / 250 候选；`direction_evidence` bands / 80 URLs / 7·14·90 天；`detector_feedback` 0–100；`cost_audit` 三个 forecast 场景。
  - 版本：`paper-qa 2026.08.12`（cloud_job）vs `paper-qa==2026.8.12`（cloud_retry）字符串不一致；`tooluniverse 1.5.1`、`ref-verify 1.2.0`、`DEFAULT_TEX_IMAGE` 固定 sha256。

### 3.3 安全与数据完整性风险

1. **`cloud_human_controls.execute` 默认未验证身份**：不传 `owner_authorization` 时 `actor_identity={"source":"local_operator_declaration","verified":False}` 仍写入 `AUDIT` 并改变闸门状态。`cloud_job.execute` 对 `review_dossier`/ACTIONS 会传，但任何其它调用路径若漏传即以「未验证本地声明」记录人工决定——**这是本组最值得注意的安全边界**。
2. **硬编码身份/仓库/项目跨多文件重复**：owner id、repo、bot id、`my-phd`、actor 姓名散落于 `cloud_job`/`cloud_continuation`/`cloud_recovery`/`cloud_checkpoint`/`cloud_pipeline_acceptance`，迁移成本与错配风险高。
3. **启发式凭据脱敏**：`cloud_checkpoint.check_file` 只扫描「当前环境变量中 ≥8 字节的已知 SECRET_NAMES 值」，`cloud_retry.redact`/`cloud_job.run_command` 按名称关键字 + 精确值替换——对历史密钥、变体、编码形式不保证覆盖。
4. **自动恢复能力极窄且依赖 CI 检查名**：`cloud_recovery.REQUIRED` 11 个检查名硬编码，任何 CI 改名都会使自动合并永久停摆（fail closed，安全但脆弱）；`ALLOWED` 只允许回滚 2 个函数体。
5. **合成夹具与真实项目混用风险**：`cloud_human_acceptance.run` 临时改写全局 `researchctl.PROJECTS_ROOT`（有 try/finally 恢复，非线程安全）；`cloud_pipeline_acceptance` 直接写 `runner-one/acceptance-fixture`。若误指向真实 `projects/` 会污染状态（代码用 `synthetic_acceptance_only` 标记与临时根目录缓解，但非强制隔离）。
6. **生产控制中混用 `assert`**：`cloud_continuation.startup_report`/`evaluate` 的 `assert control is not None` 在 `python -O` 下被移除，后续 `control[...]` 会抛 `TypeError` 而非受控错误。
7. **健壮性小缺口**：`cloud_checkpoint.prepare` 的 `json.loads(old_path.read_text())` 未捕获解析异常；`cloud_human_controls` G2 approve 的 `next(...)` 无匹配抛 `StopIteration`；`cloud_job.run_job` 的 `except Exception` 宽捕获（但 `finally` 保证 checkpoint）；`cloud_pipeline_acceptance`/`cloud_human_acceptance` 直接索引 `GITHUB_RUN_ID`。
8. **记录 URL 不等于验证来源**：`data_row_provenance._url` 明确不做 DNS/fetch，`source_url_resolved:False`；`citation_audit.provider_identity` 对 provenance 缺失/变更直接失败（fail closed，安全侧）。
9. **延迟循环导入**：`cloud_research_steps ↔ direction_evidence`、`cloud_job ↔ cloud_continuation`、`cloud_continuation ↔ cloud_progress` 互有函数内反向 import，改动导入顺序易触发 `ImportError`。
10. **`cloud_recovery.capability_probe` 真实创建并删除 draft PR**：即使隔离，仍是对远端仓库的真实写操作，依赖 cleanup 成功。
11. **并发与限流**：`data_discovery` 12 线程并发请求 8 家公开 API，单 provider 失败被吞为 `status=error`（有留痕但可能被限流而不易察觉）。

### 3.4 「文档宣称但代码未见实现」处

- AGENTS 规则 10 / README「GPT Image 可作单独标注的概念插图」→ `concept_illustrations` 的 `gpt-image-api` 付费路径**被明确禁用**（"No paid request sent… disabled pending verified route, permission and central billing support"），仅人工导入 chatgpt-web PNG 可用。
- README「40–50% 精简是未经证实的历史估计」→ `context_efficiency` 只实现 **JSON 空白无损压缩**，不实现语义精简，也不宣称节省比例。
- README「真实 0.85 一致性…仍需实际研究验收」→ `claim_evidence` 的 `target_agreement:.85` 只是硬编码目标字段，`scientific_validity_verified:False`，代码不宣称达成。
- README「独立引用差异」→ `citation_audit.crosscheck` 只做两份抽取的机械字段比较，`blindness_verified=False`、`bibliographic_truth_verified=False`、`semantic_support_verified=False`、`model_call_made=False`，明确「不推断互盲与语义正确性」。
- AGENTS 规则 13「Run model orchestration through `api_orchestrator.py`」→ 本组 `cloud_job.cycle_command` 只**生成**该命令，编排器本体在 G01；本组不含模型适配 HTTP 实现。
- `cloud_recovery` 名称/文档暗示「自动恢复」→ 实际只有 `environment_retry`（重置状态）与 2 个函数的 AST 回滚 + PR 合并，其余一律 `alert` 人工；`AUXILIARY_CHECKPOINT_PRESERVED` 明确不自动付费重试辅助任务。
- `cloud_pipeline_acceptance`/`cloud_human_acceptance`/`cloud_recovery_acceptance` 均为软件验收，代码明确 `scientific_completion_verified:False`，不证明科学有效（与 README「工程验收不代表科学有效」一致）。
- `docx_revision` 名为「修订」但**不支持**样式/节/表拓扑/格式修订；`diagram_mermaid` 名为「Mermaid 导出」但**不渲染**。
- `detector_feedback` 名为「检测器反馈」但**不调用任何检测器**（分数完全由用户提供）。

### 3.5 函数名与实际行为不符处

- `dataset_fetch.download_dataset(accept_license, ...)`：参数接收后**完全未使用**；`--accept-license` 是遗留注记（许可不作前置门槛）。
- `cloud_job.PAID`（={`cycle,continuation,paperqa,tooluniverse,auxiliary`}）：名为「付费」，在 `run_job` 中主要用作「需 `restore_state` 的 action 集合」，且与显式列举的非付费 action 混用。
- `output_provenance.record_model_writes`（全仓统一 API）：被 `cloud_human_controls`（人类控制）、`cloud_runtime`（TeX 渲染）、`concept_illustrations`（本地 PNG）、`cloud_pipeline_acceptance`（合成夹具）用于登记**非模型写入**，函数名与语义偏差。
- `citation_audit.crosscheck`：名为交叉核验，实际明确不验证互盲/语义/科学完成。
- `cloud_human_acceptance.quality_fixture(real_power=False)`：手工构造的假 power 报告仍写 `generated_by:"statsmodels"` / `engine_version:"0.15.0"` / `required_sample_size:{64,64}`，元数据声称与实际不符（虽标 `synthetic`）。
- `concept_illustrations.prepare(source="gpt-image-api")`：名为准备，实际恒返回 `available:False` 且 execute=True 抛错。
- `context_efficiency.instruction_paths`：名为「指令路径」，实际是**防诱导性 verdict 注入**的信封识别（含 `desired_verdict`/`preferred_verdict` 检测），语义比名称宽。
- `detector_feedback.evaluate.score_improved`：只是两个用户给定数字的大小比较，与检测器无关。
- `cloud_recovery.checks_pass`：名为「检查通过」，实际要求 11 个**具名** CI job 全部 success，缺一即 False。

---

## 4. 结论

本组 27 文件构成 Doctoral Research OS 的**「云端确定性控制面 + 数据供应链 + G5 证据链」**三大块，是 G01（模型适配器 / API 编排器）与后续组（实验运行器 / 稿件与投稿 / 文献与质量）之间的枢纽。`cloud_job.py` 是唯一 owner 入口，`cloud_human_controls.py` 用「全仓实现哈希 + dossier 精确复核」把人工决定锁死在可验证快照上，`cloud_research_steps.py` 用确定性 builder 分派避免模型输出被当作 receipt，`data_*` 五件套把「发现→获取→契约→清洗→行溯源」做成哈希绑定的不可篡改链，`citation_audit`/`claim_evidence`/`contribution_reporting`/`cost_audit` 则系统性贯彻「不宣称、不自动验证、保留负结果与分歧」。

最需要关注的三类问题：**(1)** `cloud_human_controls.execute` 在缺少 `owner_authorization` 时以「未验证身份」记录人工决定；**(2)** 大量硬编码 owner/repo/项目/阈值/CI 检查名跨文件重复，迁移与错配风险高；**(3)** 多个「文档宣称能力」在代码中被明确禁用或降级为占位（付费图像生成、Mermaid 渲染、检测器、自动恢复范围、0.85 一致性），阅读时必须区分「立场字段」与「已实现能力」。全组未见 TODO 字面，但「显式禁用 / 未验证 / 待人工」的占位设计本身即是最重要的边界声明。
