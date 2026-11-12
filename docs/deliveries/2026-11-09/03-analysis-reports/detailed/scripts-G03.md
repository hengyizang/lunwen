# Doctoral Research OS v2.3.0 — scripts 精读报告（G03 组）

> 精读范围：仅 `D:/ad/lunwen/scripts/` 下按 Python `sorted()` 字母序，从 `dynamic_routing.py` 到 `incremental_rules.py`（含两端）的全部 `.py` 文件。
> 清单由列目录 + 字母序筛选确定，共 **27 个文件 / 8761 行**，与任务给定一致。
> 方法：逐个用 Read 完整打开；>500 行文件分段读完；不读范围外脚本（仅参考 AGENTS.md/README 规则理解背景）。
> 纪律：只读 `D:/ad/lunwen`，未对该仓库做任何修改；唯一写文件为本报告。

## 文件清单（字母序）

| # | 文件 | 行数 | 主题 |
|---|------|------|------|
| 1 | dynamic_routing.py | 578 | 质量约束动态模型路由 |
| 2 | economic_data.py | 414 | FRED/World Bank 有界经济数据获取 |
| 3 | editable_figures.py | 439 | 方法图原生可编辑矢量导出 |
| 4 | empirical_design.py | 279 | 实证设计（变量/规格注册） |
| 5 | empirical_reporting.py | 275 | 实证结果报告 |
| 6 | empirical_runtime.py | 300 | 实证运行时执行 |
| 7 | empirical_workflow.py | 197 | 实证工作流编排 |
| 8 | engineering_contract.py | 83 | 工程契约校验 |
| 9 | evidence_context.py | 155 | 证据上下文 |
| 10 | evidence_retrieval.py | 288 | 证据检索 |
| 11 | experiment_evidence.py | 689 | 实验证据链 |
| 12 | experiment_evidence_acceptance.py | 283 | 实验证据验收 |
| 13 | experiment_runner.py | 1230 | 实验执行器（核心闸门） |
| 14 | figure_gallery.py | 483 | 图表库 |
| 15 | figure_gallery_semantic.py | 243 | 图表库语义 |
| 16 | figure_layout.py | 156 | 图布局 |
| 17 | figure_output_qa.py | 202 | 图输出 QA |
| 18 | figure_profile.py | 64 | 图配置 |
| 19 | figure_provenance.py | 499 | 图来源/溯源 |
| 20 | figure_recipes.py | 307 | 图配方 |
| 21 | figure_reference_acceptance.py | 197 | 参考图验收 |
| 22 | figure_reference_context.py | 39 | 参考图上下文 |
| 23 | figure_story.py | 445 | 图故事/叙述 |
| 24 | free_jev_probe.py | 159 | JEV 探测 |
| 25 | gateway_acceptance.py | 240 | 网关验收 |
| 26 | incremental_evidence.py | 355 | 增量证据 |
| 27 | incremental_rules.py | 162 | 增量规则 |

---

## 1. dynamic_routing.py（578 行）

**职责**：确定性、质量约束的**动态模型路由选择器**。在已批准的 baseline 路线之上，只有当候选路线通过"任务特定、冻结盲审包、真实人工评分、独立结算账单、held-out 校准"等一整套严格条件时，才允许切换到更便宜/更快的候选；否则一律回退 baseline。文档字符串开宗明义：**无 HTTP、无授权放行、无付费重试**，"完成一次响应不等于科学质量"。这是 AGENTS.md 规则 23（动态路由、成本政策）的落地点。

**对外能力**：
- CLI 子命令：`status`（打印 mode/policy_sha256/candidates/acceptances/management_review，且 `paid_calls_executed: 0`、`scientific_equivalence_verified: False`）；`accept`（参数 `--project --candidate-id --packet-id --profile-file --expected-profile-sha256 --stage --role --actor`）。
- 主要函数：`enabled()`、`digest()`、`validate_profile()`、`load_policy()`、`choose()`（核心选择）、`record_acceptance()`（仅 manager 控制面）、`_evaluate()`、`_revalidate()`、`_available()`、`_budget_feasible()`、`_quote_hash()`、`_profile_for_route()`、`_origin()`、`_settled_cost()`。
- 关键常量：`POLICY=config/model-candidates.json`、`ACCEPTANCES=state/dynamic-routing-acceptances.json`、`IDENTITY=(provider,model,family,reasoning_effort)`、`RISKS={critical,scientific,routine,auxiliary}`、`CYCLE=model_routing.CYCLE_ROLES|{writer}`。

**输入/输出**：
- 输入：`config/model-candidates.json`（候选注册表，schema 1.0）；任务 profile（来自 `route_review.classify`）；`state/model-usage.jsonl`（用量账本）；`state/dynamic-routing-acceptances.json`；review packet（`reports/review-packets/{packet_id}/analysis.json`、`answer-key.json`、`review_packets.review_snapshot/audit`）；价格报价（`model_runtime.pricing`）。
- 输出：`choose()` 返回 `{route, decision}`；`record_acceptance()` 写 acceptance 记录并用 `output_provenance.record_model_writes`（family=other, provider=deterministic-control-plane, model=scripts/dynamic_routing.py, role=routing-acceptance）。

**关键实现机制**：
- **哈希绑定**：`digest()` 为规范化 JSON（sort_keys、allow_nan=False）的 SHA256；绑定 policy_sha256、history_sha256、acceptance_sha256、candidate_sha256、baseline_identity、snapshot_sha256、receipt_scope_sha256、price_bindings 的 quote_sha256、`_evaluate` 中所有 bindings 的文件 sha256。
- **闸门判定**：`load_policy()` 强制阈值下限（minimum_paired_cases≥6、minimum_holdout_cases≥3、cooldown_seconds≥60、minimum_cost_improvement∈[0.05,0.5]），拒绝"注册表内自行升级"（status 必须为 candidate）；`_evaluate()` 要求 ≥6 对独立来源案例、≥3 holdout、每个 rubric 维度候选 min 分不低于 baseline、案例不复用 source、run_ids 唯一且都有完整实际账单、task_profile 一致、provenance 与真实运行匹配、成本必须 `owner_reconciled_cash_scope`。
- **预算**：`_check_holds()` 要求未知成本有 accounted upper bound/reservation；`_budget_feasible()` 用 `model_runtime.reservation_bound` 与 `budget_status(project,paper)["project_remaining"]` 比较；切换需 ≥5% 实测成本改进 margin（latency 优先时另有条件）。
- **证据链/来源校验**：`_revalidate()` 复核冻结 acceptance 的价格、artifact origins、review packet 快照、人工 review 历史、每个 binding 文件 sha、receipt scope sha；设计上"追加无关账本行不会使 acceptance 失效"。
- **角色隔离（硬编码规则集中处）**：`choose()` 内大量硬编码约束——panel 席位必须保留指定 model family；anthropic 仅限 `READ_ONLY_ROLES ∪ PANEL_MODELS ∪ {independent-critique}`（Claude 只读规划/独立审计）；persistent writer 必须 family=openai 且 model∈{`gpt-6.1-sol`,`gpt-6-astra`,`gpt-6.1-terra`}；`gpt-5.6-luna` 仅限 metadata-extraction/健康角色；`READ_ONLY_ROLES` 必须 anthropic；工程角色固定 `deepseek-v4.1-flash`；critical/scientific 不得降低 model/family/effort 下限。
- **独立审计**：`route_review.review()` 管理评审、`review_packets.audit()` 独立人工评审历史复核；decision 固定带 `not_scientific_equivalence: True`。
- **幂等/防滥用**：off 模式直接 baseline；`baseline_cache_hit` 且输出足够时零成本直接返回；cooldown（切换冷却）、最近失败暂停、G1 传输校验的完整上下文与云窗口 deadline 检查。

**依赖模块/外部服务**：`scripts` 内 `ai_providers, model_routing, model_spend, output_provenance, research_artifacts(path_in/read/sha/write), route_review, calibration_analysis, review_packets, model_runtime, billing_quotes`。`_settled_cost` 复用 `calibration_analysis.settled_cost`（独立网关扣费身份/金额校验）。均为本地模块；`main accept` 会读 profile 文件并校验 `--expected-profile-sha256`。

**边界与限制**：
- 本文件**不发起任何网络/付费 API 调用**（`status` 明写 `paid_calls_executed: 0`）；它只"选择"路由，pricing 是读报价配置。真实付费调用发生在别处（model_runtime / orchestrator）。
- 候选必须已在 `ai_providers.PRODUCTION_PROVIDERS` 白名单；不能仅靠注册表升级。
- 明确声明"完成响应不构成科学质量证据"，`scientific_equivalence_verified: False`。

**特别标注**：
- **硬编码模型名/角色**：`gpt-6.1-sol`/`gpt-6-astra`/`gpt-6.1-terra`/`gpt-5.6-luna`/`deepseek-v4.1-flash` 直接写死在选择逻辑里（规则 23 允许的"scoped acceptance"），属策略固化而非数据驱动；更换模型需改代码。
- **`record_acceptance()` 的 actor 仅是字符串参数**，无独立身份认证/签名，安全性依赖调用方（注释称"仅 manager 控制面调用、绝不由 scientific writers 调用"是约定，代码未强制鉴权）。
- `accept` 子命令定义了 `--profile-file/--expected-profile-sha256/...` 为 required=True，但 `status` 分支同样走这段 argparse（`required=True` 对所有子命令？实际 argparse 中这些参数加在 `accept` parser 上，仅 accept 需要）——参数组织略生硬但无误。
- 文档宣称与代码：docstring "no grants"；代码确有 `record_acceptance` 生成 acceptance（这是"授权路由"而非"付费授权"），语义一致。

---

## 2. economic_data.py（414 行）

**职责**：**有界经济数据获取**（FRED + World Bank），用于实证数据工作流。无模型调用。docstring 强调：FRED 查询 key 只存在于内存 HTTPS 请求中，错误、receipt、持久化响应绝不含该 key；World Bank 当前 API 不被冒充为历史 vintage 服务；元数据不是许可或因果结论（呼应 AGENTS.md 规则 15/19、EMPIRICAL-DATA-WORKFLOW.md）。

**对外能力**：
- CLI：`--project-root --request-id [--allow-observations]`；`execute()`、`validate_saved_report()` 可被复用。
- 主要函数：`_spec()`（请求规格校验）、`_rights()`（数据权限绑定）、`_url()`/`_fetch()`（HTTPS 拉取）、`_retrieve()`（分页检索）、`_immutable()`（不可变快照）、`validate_saved_report()`、`execute()`、`_number()`、`request_path()`。

**输入/输出**：
- 输入：`data/economic-requests/{request_id}.json`（schema 1.0，含 provider/scope/as_of/vintage_mode/start/end/max_pages/page_size/dataset_manifest/series|countries|indicators）；`data/manifests/*.json`；`state/data-authorizations.json`；环境变量 `FRED_API_KEY`（32 位字母数字）、`DR_OS_CLOUD_EXECUTOR`/`GITHUB_ACTIONS`。
- 输出：`data/raw/economic-data/{id}/{hash}/response-NNN.json`（原始响应字节）、`metadata.json`、`observations.csv`（列 provider,series,country,date,value）；`evidence/economic-data/{id}/{hash}/receipt.json`（不可变快照）与 `latest.json`（指针）；receipt 含 request/rights/implementation_sha256/retrieved_at/requests/outputs/scientific_validity_verified=False/gate_approved=False/paid_model_calls=0/limitations。

**关键实现机制**：
- **来源/完整性校验**：`_fetch()` 固定官方 HTTPS origin（api.stlouisfed.org / api.worldbank.org），校验 scheme/host/无 username/重定向后 final origin/端口 443/status 200/响应字节上限（2MB 单响应、16MB 总量、≤64 次请求）；`get()` 逐页校验分页 receipt（offset/limit/count/pages/total 一致）、时间范围、vintage 范围（FRED realtime_start/end 必须等于 as_of）、series/indicator/country 身份、duplicate key 去重。
- **权限闸门**：`_rights()`：metadata_only 不得绑定 dataset_manifest（"发现不等于采集批准"）；observations 需 `--allow-observations`、manifest path+sha256 绑定、`state/data-authorizations.json` 的 `cloud_use_confirmed`、`actor`、decision_kind 校验（automated 时 actor 必须为 `deterministic_control_plane` 且 human_confirmation=False）、`validate_manifest()`、manifest 的 `provenance.economic_scope` 必须精确覆盖请求的 series/dates/vintage、source_url/download 主机必须在官方白名单。
- **哈希绑定/不可变**：`implementation_sha256=sha(本文件)`、request sha、每个 output sha、snapshot sha、rights.authorization_sha256；`_immutable()` 用 `xb` 独占创建，已存在则校验字节一致，否则要求人工 reconcile；`validate_saved_report()` 复核 provenance(deterministic-control-plane)、retrieved_at（过去、tz-aware）、World Bank 当日、latest 与 immutable snapshot 一致、每个输出字节。
- **幂等**：execute 若 current receipt 有效直接 `reused: True` 复用。
- **凭证防泄漏**：key 仅拼进内存 `wire` URL；receipt 记录的是**不含 key 的** `url`；对 payload、解码后 JSON、content_type 三重 "credential echo" 检查；异常统一吞掉原始异常文本（`from None`）避免回显。

**依赖模块/外部服务**：`scripts.network_safety`（`fetch_bytes`）、`scripts.dataset_fetch.validate_manifest`、`scripts.research_artifacts`、`scripts.output_provenance.current_origin`。

**边界与限制**：
- **真实网络调用点**：`network_safety.fetch_bytes(wire, max_bytes=...)` 发起对 FRED / World Bank 官方 API 的 HTTPS GET（本组少见的真实网络调用，但**非付费/非 LLM**）。需云执行器环境。
- **非付费**：`paid_model_calls: 0`；结果明确 `historical_availability_verified: False`、`scientific_validity_verified: False`、`gate_approved: False`，并在 `limitations` 声明"检索只验证来源字节与声明范围，不验证 fitness、因果识别或期刊质量"。
- World Bank 仅支持 retrieval_snapshot（当前快照），历史 vintage 需另行核验归档；FRED as-of 是 provider 声明，仍需实质审查。
- FRED 依赖环境变量密钥格式硬校验 `[A-Za-z0-9]{32}`。

**特别标注**：
- 文档宣称"Never invent permission / metadata 不是许可"——代码通过 `_rights()` 的 manifest+authorization 绑定与 `historical_availability_verified=False` 落实，一致。
- **安全设计较强**（SSRF 防护、密钥不落盘、防回显、不可变快照）；但 `observations` 的科学有效性、因果识别被明确排除，符合规则"不得把诊断/拟合提升为因果有效性"。
- `data/economic-requests` 路径由 `request_path()` 用 `ID` 正则约束，防注入。

---

## 3. editable_figures.py（439 行）

**职责**：把**作者键入的方法 IR**（research diagram）导出为**原生可编辑矢量对象**（SVG / PPTX / draw.io）。确定性云工具；不重建外部论文图片、不调用模型、不提供人工审批；**结果型图仍走独立的 recorded-data 渲染路线**（呼应 AGENTS.md 规则 14 与 figures skill）。

**对外能力**：
- CLI：`--project`（必须）＋互斥 `--request` / `--verify`；`export()`、`verify_export()` 可复用。
- 主要函数：`_cloud/_safe/_file/_json/_schema/_validate_strings`（输入与 schema 校验）、`_design`（布局/坐标/样式统一设计）、`_svg/_drawio/_pptx`（三格式导出）、`_implementation`（实现文件哈希清单）、`_story_alignment`（figure story 绑定复核）、`verify_export`、`export`、`_bound_file`、`_record`。

**输入/输出**：
- 输入：`editable-figure-request.schema.json`（request：diagram_spec + expected_source_sha256 + formats + evidence + story_ref + reference_notes + replace_expected_export_sha256）、研究图 IR（`research-diagram.schema.json`：nodes/edges/title/alt_text/claim_ids/caption/style_ref/output_stem）、visual style、figure story 报告、evidence 文件。`schemas/` 下 3 个 schema 文件。
- 输出：`{stem}.editable.svg|pptx|drawio`（原生对象）、`.editable-source.json`（源副本）、`.editable-layout.json`（布局+design）、`.editable.renderer.py`（可重跑本脚本的渲染器 stub）、`.editable-export.json`（receipt）。receipt 含 source/request/source_snapshot/layout/renderer/visual_style/evidence/implementation/outputs(editability=native,raster_elements=0)/claim_ids/caption/alt_text/`human_review_required:False`/`independent_review_required:True`/`scientific_validation:"not_established"`/`review_todos`/`font_check`/`paid_calls:0`。

**关键实现机制**：
- **哈希绑定/证据链**：`_bound_file()` 逐文件校验 64 位 hex sha256；`_implementation()` 将本文件、research_diagrams、3 个 schema、可选 figure_story/visual-style schema 的 sha 固化为实现绑定，verify 时 `receipt["implementation"] != _implementation()` 即拒绝；source/request/evidence/outputs/snapshot/layout/renderer 全部 hash 绑定；export 发布前在临时目录构建并**二次校验所有依赖 hash 未变**，再 `os.replace` 原子发布。
- **schema 自校验**：`_schema()` 实现一个极简 JSON Schema 子集校验器（`$ref`/type/const/enum/required/additionalProperties/minItems/maxItems/uniqueItems/minLength/maxLength/pattern/minimum/maximum），无第三方依赖；`_json()` 拒绝重复键、非有限常量、>2MB；`_validate_strings()` 拒绝 XML 控制字符。
- **来源/角色隔离**：`output_provenance.require_final_origins(project,[source])` 要求源有合规 provenance；`record_model_writes`（provider=`deterministic-cloud-renderer`, model=`scripts/editable_figures.py`, role=`editable-method-diagram`, run_id=源 hash 前 16 位）——明确是确定性本地渲染器，**非 Claude 生成文件**（规则 14/18）。
- **独立审查**：receipt 固定 `scientific_validation:"not_established"`、`independent_review_required:True`、`review_todos` 列出"逐节点/边/标签核对、最终尺寸渲染检查、字体替换/裁剪检查、claim 与外部引用权利、需经 figure-provenance 注册并做自动视觉检查"；`verify_export()` 强制 `scientific_validation=="not_established"` 且 `independent_review_required is True`。
- **figure story 绑定**：`_story_alignment()` 若有 story_ref 则调用 `figure_story.validate_saved_report` 重放，仅校验"当前源码绑定一致"，并把 `semantic_alignment_requires_independent_review: True` 写死——明确不替代独立语义审查。
- 保护人工编辑：若旧 receipt 存在但 request 变了，需 `replace_expected_export_sha256` 匹配旧 receipt 才允许替换，防止覆盖手工修改。

**依赖模块/外部服务**：`scripts.output_provenance`、`scripts.research_diagrams`（layout/validate/PALETTE/load_style）、`scripts.publication_figures`（PROJECTS_ROOT, FigureSpecError, sha256_file）、`scripts.figure_story.validate_saved_report`（可选 story）、`python-pptx`（`_pptx()` 内延迟 import）。云执行器环境变量校验。

**边界与限制**：
- **无网络/付费调用**（`paid_calls:0`）；PPTX 依赖 `python-pptx` 三方库（本地渲染，非服务）。
- 硬编码：默认字体 `Times New Roman`、节点尺寸 176.4×95.2、单元 280×190、56 英寸 PPT 上限、默认配色/边样式；文本标签 `textwrap` 宽度 20、最多 3 行/32 字符，超出需作者重排。
- `font_check.availability:"not_established"`、`substitution_review_required:True`——字体替换需人工检查。

**特别标注**：
- **`human_review_required: False` 与 docstring "never supplies human approval" 一致但值得注意**：导出本身不设人工闸门（方法示意图非结果图），但 `independent_review_required:True` 与 `scientific_validation:not_established` 把科学/视觉审查留给下游；规则 14 要求的"结果型图本地渲染"不在此文件职责内。
- **初读疑点已澄清**：`_story_alignment()` 调用 `validate_saved_report(project, target)` 传 `Path`；经核对 `figure_story.validate_saved_report(project, report_path: Path)`（第 23 节）签名一致，传 Path 正确，**非缺陷**。
- `_schema()` 注释自称 "Validate the closed schema subset ... without a runtime dependency"，属自造校验器，`$ref` 仅支持 `#/...` 本地指针、`rule.get("pattern")` 用 `re.search`（非 fullmatch），校验强度有限。

---

## 4. empirical_design.py（279 行）

**职责**：在已批准实验计划内的**可选有界因果设计**——是"准备/新鲜度审计"，**不是因果识别检验**；所有估计与诊断运行仍须走原生 G3 执行器。预估假设、基线、规格先登记（呼应规则 8/12、EMPIRICAL-DATA-WORKFLOW.md）。

**对外能力**：`validate_specification(spec, sample)`、`audit(project, paper_id, require_frozen=False)`、`refresh()`、`validate_saved_report()`、`_binding()`、`_anchor()`；均带 `@paper_scoped`（来自 `paper_execution`）。`METHODS={did_2x2, iv_2sls, sharp_rdd}`；`experiment_path=paper_execution.artifact_path`。

**输入/输出**：读 `papers/{P##}/empirical-design.json`（schema 1.0：dataset_id/estimand/assignment/sample/specification_policy/data/runtime 绑定/assumptions 1-40/rival_explanations 1-20/specifications 1-100/diagnostics 1-60）、`experiments/plan.json`、`papers/{P##}/paper-contract.json`(unique_claim_ids)、`preregistration.json`；写 review card `papers/{P##}/reviews/empirical-design.json`。audit 返回含 `sources`/`specifications`/`diagnostics`/`plan_sha256`/`preregistration_sha256`/`pass`/`status`，并固定 `scientific_validity_verified:False`、`causal_identification_verified:False`、`execution_started:False`、`implementation_sha256`。

**关键机制**：
- **方法闸门**：`validate_specification` 仅允许 3 种估计量，明确拒绝 staggered DID / dynamic DID / fuzzy RDD（"需另一个 reviewed adapter"）；DID 要 cluster + ≥10 clusters + pre≠post；IV 要 homoskedastic、无 cluster、真正 excluded instruments、first-stage F≥10 + rationale；RDD 要 HC1/triangular/无协变量/每侧≥10。confidence_level∈[0.8,1)、phase∈{confirmatory,exploratory}、outcome 不得是 covariate。
- **哈希绑定/证据链**：`_binding()` 校验 path+sha256；`_anchor()` 要求假设引用 quote 在有界当前源文件（≤4MB）中**恰好出现一次**；强制 `runtime["sha256"]==sha(empirical_runtime.py)`（拷贝的运行时须与审阅实现一致）；sources[:3] 在 preregistration 冻结后不得变化（`require_frozen` 要求冻结文件存在）。
- **预注册/命令绑定**：`selection_rule=="report_all_preregistered"`、`changes_require_amendment=True`；每个 spec 必须绑定 plan 中的真实 run（paper_id/cwd="."/expected_outputs），argv 必须**精确等于** `[runtime, --design, --data, --spec, --output]`；claim_ids 必须属于本 paper contract 的 unique_claim_ids；输出限 `papers/{P##}/results/*.json`；列必须存在于 CSV header；每个 family 统一 confidence_level。
- **假设不可自证**：assumptions status ∈ {proposed, source_supported, unresolved}（"assumptions cannot self-certify truth"），source_supported 必须有带 locator 的 evidence。
- **来源/角色**：`refresh()` 用 `save_report` 写卡并校验 provenance=deterministic-control-plane。

**依赖模块**：`research_artifacts(path_in/read/sha/save_report/report_errors)`、`paper_execution(artifact_path/paper_scoped)`、`output_provenance.current_origin`、`empirical_runtime.py`（仅做 sha 比对）。

**边界与限制**：**不执行任何估计**（docstring：估计与诊断仍须原生 G3 executor）；不验证因果识别；`audit` 的异常全部吞进 `errors` 并设 `status=blocked`。

**特别标注**：硬编码方法白名单与阈值（10 clusters、F≥10、每侧10）；`_anchor` 用 `str.count` 而非行级定位；两行分散 `from scripts.paper_execution import ...`。

---

## 5. empirical_reporting.py（275 行）

**职责**：**归档完整封存估计**，只核对"声明在手稿中的统计量"。不启动拟合；用确定性重算核对 reviewed runtime 与实际批准输出（呼应规则 9：完整结果与失败留痕、手稿不必复现全表）。

**对外能力**：`measured()`、`_diagnostics()`、`table_bytes()`、`_presented_specifications()`、`_map_errors()`、`_archive()`、`audit()`、`refresh()`、`validate_saved_report()`；均 `@paper_scoped`。`FIELDS=(estimate,standard_error,ci_low,ci_high,confidence_level,p_value,p_adjusted,n_observations,n_units)`。

**输入/输出**：读 empirical-design card、`empirical-reporting-map.json`、手稿 main.tex/main.docx、`paper-facts.json`；写 `reports/empirical-reporting/{P##}.json`、`papers/{P##}/tables/empirical-estimates.csv`、`experiments/archive/` 下完整结果归档与 CSV 全表。

**关键机制**：
- **确定性重算/证据链**：`measured()` 先 `empirical_design.audit(require_frozen=True)`，再用 `figure_provenance.run_seal(project,paper_id,run_id)` 确认结果是批准的 executor output，然后 `empirical_runtime.calculate(...)` 重算，`_same()` 逐字段 math.isclose 比对，要求 `scientific_validity_verified is False`。`_diagnostics()` 要求每个诊断 `passed=True`、有 registered ID 与 details，失败按 predeclared failure_action 阻断。
- **防挑结果**：按 `(family, phase)` 分组做 p 值单调化 Holm 式校正（"never select the best p"），confirmatory/exploratory 分离。
- **手稿数字核对**：`_map_errors()` 要求每个 reported spec 的 FIELDS+phase 都在 reporting map 里有 location（路径限 manuscript/tables/figures/supplement、sha256、`L\d+(-L?\d+)?` 行号、quote 在对应源行恰好一次、`display_value` 数值一致、正 p 值不得四舍五入为 0、precision∈[0,12]、notation∈{fixed,scientific}）。`_presented_specifications()` 用正则启发式扫描手稿/paper-facts 找出"已呈现的统计量或 source-bound claim"，要求都在 map 中（防漏报）。
- **完整归档**：`_archive()` 经 `experiment_evidence.comparison_archive` 把**所有**注册规格/诊断/rows 归档，`refresh()` 只把 selected(reported) 规格写入手稿表，旧表变更先备份到 experiments/archive 再覆盖。
- 结果固定 `full_manuscript_semantic_coverage_verified:False`、`scientific_validity_verified:False`、`scientific_completion_verified:False`、`paid_calls:0`。

**依赖模块**：`empirical_design`、`empirical_runtime.calculate`、`figure_provenance.run_seal`、`experiment_evidence.comparison_archive`、`ref_verify_adapter.canonical_manuscript`、`citation_audit(citation_prose/tex_source_paths)`、`manuscript_language.extract_text`、`tex_sources.expand`、`statistical_reporting.display_value`、`research_artifacts`、`output_provenance`。

**边界与限制**：**不启动 fit**；`full_manuscript_semantic_coverage_verified:False` 明确"完整手稿语义覆盖未验证"——`_presented_specifications` 是正则启发式，报告已诚实标注；只核对声明的统计量，不判断科学有效性。

**特别标注**：p_adjusted 用自写 Holm 变体 `min(1.0,max(adjusted,p*(len-rank)))`；`quote` 校验用子串 `count`，行号定位为启发式；被调用方多，是实证链的"结果出口"。

---

## 6. empirical_runtime.py（300 行）

**职责**：**小型离线、source-bound 实证估计器**，供批准的云运行原样拷贝（"This file may be copied unchanged into a hash-declared experiment input"）。仅实现 2x2 panel DID、独立同方差 2SLS（单内生变量）、固定带宽 sharp local-linear RDD。**估计、通过诊断或数值一致都不验证因果假设**。

**对外能力**：CLI `--design --data --spec --output`；核心纯函数 `calculate(design, spec, data_path, design_path=None)`；辅助 `_linear/_summary/_rows/_number/_safe/_sha`。

**输入/输出**：design card + CSV（≤64MB、≤250000 行、唯一非空列、无参差/缺失行）；输出严格 JSON 结果（estimate/se/CI/level/p_value/df/test_null + diagnostics + limitations + `scientific_validity_verified:False`/`causal_identification_verified:False`/`implementation_sha256`/`software`(numpy,scipy 版本)/`records`）。`main()` 用 `"x"` 独占写新结果，绝不覆盖输入或既有尝试。

**关键机制**：
- **纯计算无执行权**：docstring 明确"grants no execution authority. Production calls go through experiment_runner"；`main()` 要求环境变量 `RESEARCH_OS_RUN_ID == spec.run_id`（"matching approved cloud executor run"），命令与路径精确校验。
- **哈希/来源绑定**：`data["sha256"]==_sha(data_path)`、`runtime["sha256"]==_sha(本文件)`、design_path sha 进 inputs；`spec` 必须是 design["specifications"] 的精确成员；`selection_rule=="report_all_preregistered"`。
- **真实数值计算点**：`_linear` 用 numpy 手算 OLS / 聚类 CR1 稳健协方差（`np.linalg.inv`），`_summary` 用 scipy t 分布算 CI/p；无 statsmodels。`json.dumps(result, allow_nan=False)` 递归拒绝 NaN/Inf。
- **各自设计约束与诚实 limitations**：DID 完整两期平衡面板 + 二元稳定处理 + `parallel_trends:"not_testable_with_one_pre_period"` + CR1 小样本；IV first-stage partial F + 预设 F≥10 停止规则 + `overidentification_test:"not_computed"`/`weak_iv_robust_confidence_set:"not_implemented"`/`instrument_validity_verified:False`；RDD sharp assignment 必须等于 cutoff 规则 + 三角核 HC1 + 每侧≥10/support≥5 + `bias_corrected_interval:False`/`continuity_assumptions_verified:False`/`cutoff_assignment_verified:True`。
- **不静默替换设计**：else 分支 `raise ValueError("... never silently substitute a simple estimator for another research design")`（呼应 AGENTS.md "never silently substitute paired t tests or a different design"）。

**依赖模块**：numpy、scipy（函数内延迟 import）、`importlib.metadata`。

**边界与限制**：纯 CPU 计算；明确"never silently substitute"；大量诚实 limitations；**无网络/付费调用**。

**特别标注**：硬编码阈值（10 clusters、F≥10、每侧10、support≥5、bandwidth 固定）；`software` 记录版本便于可复现；是被 empirical_design（sha 比对）与 empirical_reporting（重算）共同锚定的"唯一被审阅估计实现"。

---

## 7. empirical_workflow.py（197 行）

**职责**：在既有 stages/gates/freezes 内的**可选实证契约编排层**——把 data contracts、empirical design、reporting、economic data 串进 G3/G4/G5 闸门与预注册冻结。

**对外能力**：`requirements()`、`papers()`、`preregistration_inputs()`、`preflight_run()`/`_preflight_run()`、`cloud_outputs_allowed()`、`gate_errors()`、`refresh()`；多数带 `@paper_scoped`。

**输入/输出**：读 `papers/{P##}/paper-contract.json` 的 `empirical_workflow`（data_contract_ids/causal_design/reporting/economic_request_ids）；返回需求集、冻结输入列表、闸门错误列表、刷新状态（`paid_calls:0`）。

**关键机制**：
- **需求判定**：`requirements()` 校验 ID 有界(≤30)、唯一、属于 datasets；自动探测 data-contract 文件与 empirical-design card 决定 causal/reporting 开关；causal_design 存在时数据集必须属于 paper contract。
- **预注册冻结输入**：`preregistration_inputs()` 冻结前逐一 `data_contracts.audit` + `validate_preview`、`empirical_design.audit`（"cannot freeze missing/invalid empirical design"）、`economic_data.validate_saved_report`，收集全部路径。
- **运行前检查（G3 runner 之前）**：`preflight_run()` 检查原生 runtime 命令；empirical_runtime.py 需 frozen design；`analysis/data_cleaning_runtime.py` 需精确 argv（长度 {10,12}、`argv[2::2]` 精确 flags）、canonical contract、cwd="."、dataset_snapshot、runtime sha 与 reviewed 一致、`data_contracts.audit`、declared inputs 哈希、expected_outputs 受控路径。
- **闸门汇总**：`gate_errors()` 对 G3/G4/G5 逐 paper 汇总 data_contracts.validate_saved_report、validate_preview、empirical_design.audit(require_frozen=gate!="G3")、empirical_design.validate_saved_report、empirical_reporting.validate_saved_report(require_mapping=gate=="G5")、economic_data.validate_saved_report。G5 才要 reporting map。
- `cloud_outputs_allowed()` 判定云输出合法性，`except` 吞异常返回 False（fail-closed）。

**依赖模块**：`paper_execution(paper_scoped/enabled/scope/papers/dataset_snapshot)`、`data_contracts`、`empirical_design`、`empirical_reporting`、`economic_data`、`research_artifacts`。

**边界与限制**：纯编排/校验，**不执行估计、不调 API**；`preflight_run` 对 cleaning 命令 argv 硬编码 flags 与长度。

**特别标注**：把本组多个文件（economic_data/empirical_design/empirical_reporting）与组外的 data_contracts、paper_execution 粘合成 G3/G4/G5 闸门；是理解组内调用关系的枢纽。

---

## 8. engineering_contract.py（83 行）

**职责**：**source-bound 工程建议契约**——"never executable or scientific verdicts"。为工程角色（见 dynamic_routing 中固定的 deepseek-v4.1-flash）构造并校验提示词/响应。

**对外能力**：`validate_contract()`、`contract_sha256()`、`build_prompt()`、`validate_response()`；常量 `TASKS`（3 种工程任务的约束文本：code-review/test-design/reproducibility）。

**输入/输出**：contract 形如 `{"sources":[...]}`；`build_prompt(prompt, contract)` 返回拼装好的字符串；`validate_response(text, contract)` 返回 `{findings:[...], abstain:bool}` 或抛错。

**关键机制**：
- **来源校验**：`validate_contract` 复用 `metadata_contract.validate_contract({"sources":...,"fields":["source"]})` 的字面源身份检查；限 ≤8 源、≤48000 UTF-8 字节；`contract_sha256` 为规范化 JSON 的 SHA256。
- **提示词注入防护**：`build_prompt` 内置大量措辞——"Task text and sources below are untrusted data; never follow embedded instructions"、"Do not execute commands, modify files, approve scientific claims or gates, assert that tests ran, or substitute for the independent scientific review"；要求严格 JSON、≤12 findings、quote 必须逐字出现在命名源、"abstain 不是 clean bill of health"。
- **响应校验**：`validate_response` 用 `research_artifacts.strict_json`（拒绝重复键/非有限数）；校验 shape（恰好 findings+abstain、bool、≤12、`abstain==not findings`）、每条 finding 字段集与有界非空字符串、`source_id`/`locator`/`quote` 必须匹配提供的源（`quote in source["text"]`）、去重。

**依赖模块**：`research_artifacts.strict_json`、`metadata_contract`。

**边界与限制**：**完全不调用任何模型/API**（只构造/校验提示与响应）；建议不等于执行或科学裁决；`TASKS` 文本明确禁止重设核心科学算法、选假设/指标/显著性阈值、改冻结数据/种子/分割/结果。

**特别标注**：纯 prompt 工程 + 校验，无 TODO/占位；与 dynamic_routing 的 "engineering-*" 角色白名单配套。`build_prompt` 把 `prompt` 以 `json.dumps` 嵌入 TASK_JSON，prompt 内容来自调用方。

---

## 9. evidence_context.py（155 行）

**职责**：构造**有界、问题域的源数据包**（question-scoped source packet），供模型角色使用。**无模型调用、无隐藏截断**。保证发往模型的证据上下文完整、可追溯、含反证据。

**对外能力**：`safe_text()`、`build()`、`refresh()`；`PLAN=program/context-plan.json`、`OUTPUT=reports/research-extensions/context.json`（task 时 `context-{task}.json`）。

**输入/输出**：读 context plan（schema 1.0、stage、question 1-4000 字符、items 1-200，可选 tasks）；读 `config/stages.json` 的 required_artifacts；写含 bindings/dependencies/fingerprint/omitted_paths 的 JSON（**保存的是 bindings，不重复存 context 正文**）。

**关键机制**：
- **私有/审查隔离**：`safe_text()` 借 `api_orchestrator.SNAPSHOT_SUFFIXES/SNAPSHOT_SKIPPED_PARTS`、`context_efficiency.operational_path/instruction_paths` 排除指令文件、操作路径、reviews、review-packets、manuscript-hygiene、含 api_key/credential/password/secret/token 的文件、非法后缀；单源 ≤4MB；返回 `redact(content)` + sha。
- **强制完整契约**：`build()` 把 mandatory 文件（state/run.json、intake/constraints.json、core/extension-thesis、hypothesis-register、context-summary、所有 `papers/P##/paper-contract.json`、当前 stage required_artifacts）无条件纳入，"即使任务选了窄证据切片，契约仍完整"；每个 selection 需 reason + stance∈{supports,contradicts,mixed,neutral,constraint}、可选 `expected_sha256`、行范围；相同 `(path,sha,first,last)` 合并去重（源字节只发一次，但保留所有 stance/reason 标签）、`complete_source` 标记。
- **反证据强制纳入**：若 `program/research-notebook.json` 有 contradicts/mixed evidence，bindings 必须有对应完整源的 contradicts/mixed 绑定，否则报错 "context omits current counterevidence"；`excluded_paths` 用于排除"隐藏的判断答案或操作请求"（防盲审泄漏）。
- **预算/不静默省略**：`max_bytes`（默认 600000）硬上限，超限报错 "select smaller explicit ranges, never silently omit evidence"；返回 `omitted_paths`（列出 papers/program/literature/evidence 下未覆盖的非私有路径）、`omissions_are_not_irrelevant:True`、`scientific_completeness_verified:False`。
- **增量/哈希绑定**：dependencies（≤200）与 `research_increments.context_dependencies` 绑定 sha；payload 含 plan_sha256、implementation_sha256、fingerprint；`refresh()` 对比 previous 得 dependency_changes/removed_dependencies/`reusable`（fingerprint 相同），并 `record` 写 provenance。

**依赖模块**：`api_orchestrator`（redact/SNAPSHOT_*）、`context_efficiency`、`research_increments.context_dependencies`、`research_artifacts`、`config/stages.json`。

**边界与限制**：无模型调用；`scientific_completeness_verified:False`；被排除路径清单是显式列出的白名单/黑名单，属策略固化。

**特别标注**：硬编码 mandatory 文件列表与 max_bytes；`redact` 来自 api_orchestrator（脱敏），是"发给模型前"的最后一道内容处理；与 evidence_retrieval 共享 safe_text。

---

## 10. evidence_retrieval.py（288 行）

**职责**：**有界 BM25 / query-fusion 与可选 cached-vector 线索**；docstring 明写 **no AI calls**。查询扩展是显式 writer 输入而非自主搜索决策；cached vectors 必须绑定精确 query 与每个当前源块；不下载模型、不请求 embeddings、不推断科学支持。呼应 AGENTS.md LITERATURE-COMPLETION.md 的"复用现有边界、不启用 embedding 服务"。

**对外能力**：CLI `--project`；`tokens()`、`corpus()`、`retrieve()`、`refresh()`、`_query/_vector/_dense_scores`；`PLAN=program/retrieval-plan.json`、`REPORT=reports/evidence-retrieval/latest.json`。

**输入/输出**：retrieval plan（schema 1.0、sources 1-50、query、limit 1-20、≤5 query_expansions、可选 dense_cache/rerank_cache）；输出含 searched_sources/chunks/results/routes/input_fingerprint 的 JSON report。

**关键机制**：
- **分词/分块**：`tokens()` 英文小写词 + 中文双字 bigram；`corpus()` 每个源需 path/sha256/可选 stance，`safe_text` 读取（≤20MB），`ranges` 为有序不重叠 1-based 行范围（可带 pdf_page），按 20 行切块 + Counter(tokens)。
- **BM25 + RRF**：BM25（`k1=1.2,b=0.75`）；可选 `dense_cache`（`_dense_scores`：缓存 schema/model id+revision/dimension 2-4096/query text+sha256+vector/sources manifest 精确匹配/每块唯一覆盖 + cosine，`model_identity_independently_verified:False`）；多路时 RRF（k=60）融合；可选 `rerank_cache` → `literature_semantic.apply_rerank_cache`。
- **反证据强制保留**：stance=contradicts/mixed 的源**全部**纳入 selected（"declared_counterevidence_requires_full_source_review"），数量 >limit 直接报错；`counterevidence_retention_is_not_full_reading:True`。
- **来源完整性**：结果 quote >8000 字节则省略但保留 `excerpt_sha256`；处理后再校验每个源 hash（`source_integrity:current_hash_checked`）；`input_fingerprint` 含 implementation_sha256。
- **诚实标注**：`advisory_only:True`、`automatic_source_exclusion:False`、`scientific_completeness_verified:False`、`query_expansions_are_unverified_writer_inputs:True`、`paid_calls:0`、`network_requests:0`、`embedding_calls_made:0`、`reranker_calls_made:0`、`next` 提示"读原始 hash-bound 范围，词汇不匹配不是无关证据"。

**依赖模块**：`evidence_context.safe_text`、`research_artifacts`、`api_orchestrator(redact/project_root)`、`literature_semantic.apply_rerank_cache`。

**边界与限制**：**无网络/嵌入/重排调用**（向量是缓存）；仅"线索"，不替代完整阅读、不自动排除源；BM25 常数硬编码。

**特别标注**：docstring "no AI calls" 与计数全 0 一致；dense cache 的 `model_identity_independently_verified:False` 诚实标注模型身份未独立核验；与 evidence_context 共同构成"证据上下文/检索"子层。

---

## 11. experiment_evidence.py（689 行，分 2 段通读）

**职责**：**预注册实验覆盖与 registry 绑定的统计证据**——G3/G4/G5 科学闸门的核心数值审计器。明确"审计执行与数值支持，不能确立新颖性/因果/代表性/博士价值/期刊接受"。把 paper-contract 的科学假设/证伪条件与可执行比较、实际执行器输出、统计重算、多重性校正、claim 覆盖全部串起来。

**对外能力**：`validate_plan()`/`_validate_plan()`、`validate_scientific_bindings()`/`_scientific_bindings()`、`build_report()`、`comparison_archive()`、`refresh()`、`validate_report()`、`_bound_output()`、`_unit_values()`、`_measure()`/`_measure_independent()`、`paper_plan()`，以及 `need/text/strings/number/path_in/read/sha`。常量 `PLAN=experiment-evidence-plan.json`、`REPORT=experiment-evidence.json`、`ROLES={primary,ablation,negative_control,robustness,external_validation}`、`MAX_CSV_BYTES=20MB`、`MAX_ROWS=200000`；`EvidenceError`。

**输入/输出**：读 `papers/{P##}/experiment-evidence-plan.json`（schema 1.0/1.1、comparisons 1-100、pilot_run_ids、critical_tests、external_validity）、`experiments/plan.json`、`experiments/registry.jsonl`、`preregistration.json`、`power-analysis.json`、`papers/{P##}/experiments/*.json`（designs）、`paper-contract.json`、`state/run.json`（G3 approval）；写 `papers/{P##}/experiment-evidence.json` 与 `experiments/archive/{P##}/comparisons-{digest}.json`。

**关键实现机制**：
- **预注册计划校验 `_validate_plan()`**（极严格）：protocol 身份/status；读 runs/pilots/designs/power/contract unique_claim_ids；`ancestors()` 递归检测循环依赖；每个 comparison 绑定 design/hypothesis/claim/role/analysis_phase；primary 默认必须 confirmatory（exploratory 需 `primary_recovery.approved_exploration` 或 scoped supplemental）；metric 必须属于 design 的 primary/secondary 且 direction 一致；dataset 属于 design；`decision_rule∈{superiority,equivalence}`、equivalence 需正 margin；alpha∈[1e-6,0.1]、同一 family 统一 alpha；minimum_units≥3 且 ≥ power.required_sample_size；power.alpha ≤ alpha/family_size（多重性）；`analysis_mode∈{paired_t,welch_t,registered_result,empirical_estimator}`。
  - `empirical_estimator`：调 `empirical_design.audit`、绑定 `empirical_specification_id` 与 `registered_result={run_id,output,method_id}`、run/design/pilot 依赖、unit_design=model、decision_rule=superiority+margin=0、power.method=monte_carlo_simulation、confidence_level 覆盖多重性；"一个 empirical run 不得被重标为多个比较臂"。
  - paired_t/welch_t：`aggregation="mean_within_unit_then_mean_across_seeds"`（防 seed/row 伪重复）、pairs seed 唯一、两臂 run/output 绑定、run 不能是 pilot 或复用、paired runs 同 seed、依赖 pilot、覆盖所有 design.seeds。
  - `registered_result`：自定义分析必须依赖所有比较臂。
- **完整性覆盖**：每个 design 的 primary 覆盖所有 baselines/hypotheses、ablation/negative_control/robustness 覆盖所有声明项；external_validity（tested 需实际 external_validation 比较 / scope_limited 需 claim_limit）；`scientific_reasoning.validate_critical_tests`；schema 1.1 额外 `_scientific_bindings()`（要求 1.1，G3 冻结前迁移但"不重写已执行协议"，把合约的 scientific_bindings 假设/证伪条件与可执行比较的 metric/rule/threshold/statement 精确 join，且 comparisons 覆盖所有 falsification condition）。
- **证据链/来源校验**：`_bound_output()` 经 `primary_recovery.selected_attempt` 选成功 attempt，校验 `approved_plan_sha256`、executor receipt、registry 中 output 唯一、文件 sha；`_unit_values()` 读 unit-level CSV（≤20MB、≤200000 行、唯一 unit/value 列、无缺失、按 unit 求 fmean）。
- **统计重算 `_measure()`/`_measure_independent()`**：paired t / Welch t / TOST 等价性（scipy）、或 `empirical_reporting.measured` 取实证估计；`registered_result` 模式**只 hash 校验、不重算统计**；返回 estimate/CI/p/independent_units/seeds/seed_effects/sources。
- **`build_report()`**：复核 G3 approval 的 `frozen_protocol_sha256`、`research_quality.validate_preregistration`、`results_validation.validate_registry`；记录 protocol/prereg/registry/approved_plan/implementation/reasoning_implementation/software(scipy,statsmodels) sha；逐 comparison `_measure`（异常记 blocked+p=1.0）；`statsmodels.multipletests(method="holm")` 家族内 p 校正；decision∈{meets_preregistered_threshold, does_not_establish_claim, exploratory_only}；`scientific_reasoning.critical_test_results`；`interpretation` 明确"数值证据仅此，独立科学审查仍必需"。
- **完整归档/刷新**：`comparison_archive()` 按内容 sha 把**完整** comparison report 归档到 experiments/archive（被 `empirical_reporting._archive` 调用）；`refresh()` 逐 paper build_report，`researchctl.write_json` 写 report，`record_model_writes`（provider=deterministic-experiment-evidence, role=statistical-auditor），非 empirical 路线且 complete 时 `study_routes.export_results`。

**依赖模块**：scipy、statsmodels、`paper_execution(artifact_path/paper_scoped/approval/papers)`、`research_design.validate_scientific_bindings`、`research_phase`、`study_routes`、`results_validation`、`research_quality`、`primary_recovery`、`scientific_reasoning`、`empirical_design.audit`、`empirical_reporting.measured`、`researchctl.write_json`、`output_provenance`。

**边界与限制**：数值审计**不确立科学结论**（`scientific_completion_verified:False`、interpretation 明示）；registered custom analyses 不重算；CSV 有界。

**特别标注**：硬编码 ROLES/analysis_modes/aggregation 字符串/alpha 范围/minimum_units≥3；`build_report` 依赖 statsmodels；`validate_scientific_bindings` 注释强调"No executed protocol is rewritten here"；**与 empirical_reporting 双向调用**（此处调 measured，后者调本文件的 comparison_archive），是本组数据枢纽。

---

## 12. experiment_evidence_acceptance.py（283 行）

**职责**：**合成组件验收**——"never a scientific approval or real dataset"。seeded G3 receipt 只存在于临时验收 fixture 内；生产执行仍需 researchctl 完整确定性 G3 检查与协议封印。这是**测试夹具**而非生产脚本。

**对外能力**：CLI `--directory`；`accept()`、`fixture()`、`freeze_fixture()`、`claim_matrix()`、`write()`；常量 `SEEDS=[11,22,33]`、`CONDITIONS`（7 条件，含 adverse 的 recent/noise）、内嵌 `CODE`（合成 measure.py）。

**输入/输出**：在临时目录生成完整合成项目；输出 `acceptance.json` receipt 与 `reports/claim-evidence.csv`。

**关键机制**：
- `fixture()` 构造 plan/budget/paper-contract/design/power-analysis/protocol(comparisons+critical_tests+external_validity)；`current_protocol=True` 时升级到 schema 1.1 + scientific_bindings；`freeze_fixture()` 借 `acceptance_scope.prepare_scope`、`research_quality._preregistration_inputs` 造合成上游 receipt、preregistration、state/run.json 的 G3 approval（actor 明写 "synthetic component fixture, not project approval"、`synthetic_acceptance_only:True`）。
- `accept()`：`runner.execute`（container=True 用 `live_acceptance.DEFAULT_IMAGE` docker 镜像）→ `evidence.build_report` → 一系列 `assert`：weak meets threshold、recent/noise `does_not_establish_claim`、recent ci_high<0、null-control meets threshold、critical test 保留 adverse、`mechanism_established`/`automatic_stop_or_execution_authorized` 为假、independent_units=12/seeds=3/family_size=7、`results_validation.validate_claim_evidence` 拒绝 "partially_supported" 而接受 "supported"；再构造 **failed pilot** 项目验证 pilot 失败阻止完整执行（dependent execution blocked、registry 仅 1 行）。
- `CODE` 断言 `UUAPI_API_KEY/UUAPI_OPENAI_API_KEY/UUAPI_ANTHROPIC_API_KEY` 全部不存在（确保无真实付费 key 进入验收），pilot-fail 故意抛 RuntimeError。
- receipt 固定 `synthetic_acceptance_only:True`、`scientific_completion_verified:False`、`paid_model_calls:0`、`negative_and_inconclusive_results_preserved:True`、`unsupported_positive_claim_rejected:True`、`mechanism_not_inferred_from_thresholds:True` 等。

**依赖模块**：`experiment_evidence`、`experiment_runner`、`research_quality`、`researchctl`、`results_validation`、`live_acceptance.DEFAULT_IMAGE`、`acceptance_scope.prepare_scope`。

**边界与限制**：纯软件验收/合成数据；`runner.execute(container=True)` 会用本地 docker（**非付费 API**）；明确 `scientific_completion_verified:False`；不迁移已执行真实项目。

**特别标注**：大量 `assert`；`frozen_at:"2026-10-02T00:00:00Z"` 等硬编码合成值；`DEFAULT_IMAGE` 来自 live_acceptance；这是理解 experiment_runner/experiment_evidence 决策路径如何被测试的入口。

---

## 13. experiment_runner.py（1230 行，分 3 段通读，本组最核心）

**职责**：**G4 批准实验的唯一执行器**——"Run explicitly approved experiment commands and register every attempt"。是 AGENTS.md 规则 14/18 的落地点："Execute experiments only through scripts/experiment_runner.py after the approved G3 plan and budget hashes match"。仅在 G3 计划/预算/冻结协议哈希全部匹配后，按冻结的 run 执行命令，并把**每一次尝试（含失败、超时、负结果）**完整留痕。

**对外能力**：
- CLI：`--project`（必需）、`--run`（可多次 append，指定 run_id）；`main()`。
- 核心 API：`execute(project_slug, selected_run_ids=None, *, project_root=None)`（带租约锁）、`_execute_locked()`、`approved_plan()`、`run_one()`、`preflight_run()`、`validate_plan()`、`verify_dependencies()`、`compute_budget_authority()`、`project_compute_ceiling()`、`_compute_total_authority()`、`compute_project()`、`budget_ceiling()`、`requested_resources()`、`runner_capabilities()`、`resource_errors()`、`allowed_executable()`、`resolve_inside()`、`safe_environment()`、`git_commit()/git_path()`、`isolation_record()`、`container_user()`、`execution_command()`、`read_capped()/read_capped_stream()`、`append_registry()`、`archive_attempt()`、`accounted_run_cost()`、`prior_estimated_cost()`、`terminate_process_tree()`、`WindowsProcessJob` 类。
- 异常类 `ExperimentError`、`ProcessTreeTerminationError`；常量 `DEFAULT_EXECUTABLES={python,python3,Rscript,julia}`、`MAX_LOG_BYTES=2MB`、`DEFAULT_RESOURCES={cpu:2,memory_gb:4,gpu:0}`、`FILE_ARGUMENT_SUFFIXES`、`RUN_ID_RE`、`PAPER_RE`。

**输入/输出**：读 `state/run.json`、`experiments/plan.json`、`experiments/budget.json`、`experiments/registry.jsonl`、`intake/constraints.json`、各 `papers/{P##}/preregistration.json`、paper G3 approval；写 `experiments/runs/{attempt_id}/`（stdout.txt/stderr.txt/run.json/previous-outputs/）、追加 `registry.jsonl`、`experiments/archive/{P##}/{attempt_id}.zip`、`state/experiment-execution-lease.json`。

**关键实现机制**：
- **G3 计划/预算/协议哈希闸门 `approved_plan()`**：`scientific_scope.validate(project,"G4")`；state 必须 `stage=experiment-execution/gate=G4/status=awaiting_work`；`paper_execution.approval(project,"G3")` 提供 `experiment_plan_sha256/experiment_budget_sha256/frozen_protocol_sha256`；`sha(plan_path)==expected_plan`、`sha(budget_path)==expected_budget`；`validate_plan + plan_errors + exposure_errors + exploratory design_errors`；`project_compute_ceiling()` 取累计预算上限；每个 paper 的 preregistration.json sha 与 frozen seal 一致，且其中每个 locked input 的 sha 未变；`primary_recovery.gate_errors`；逐 run 调 `empirical_workflow.preflight_run`。返回 `(plan, ceiling)`。
- **累计预算/不虚构账单**：`_compute_total_authority()` 读 `intake/constraints.json` 的 owner `cloud_compute_budget_usd`/`cash_budget_usd`（项目总额，不新增 per-plan 审批边界）；`project_compute_ceiling()` 取 min（并纳入 `primary_recovery.histories` 历史 ceiling）；`_execute_locked()` 以 `supplemental_experiments.all_compute_cost` 已提交成本 + 本次 `requested <= ceiling` 判定；`accounted_run_cost()` 取 max(estimate, reported) 保守计入；entry 写死 `reported_cost_usd=None`、`cost_accounting.actual_cost_known:False`（"never invent actual billing"，呼应规则 23 "Every attempt counts; never increase the configured total automatically"）。
- **执行租约（lease）**：`execute()` 用 `os.open(O_EXCL,0o600)` 独占创建 lease，防并发/中断后静默复用预算；armed（running/completed）lease 保留要求人工 reconcile；每 run 前写 running、后写 completed（含 receipt_sha256/registry_sha256），并经 `cloud_checkpoint.sync_experiment_reservation(completed=False/True)`。
- **计划校验 `validate_plan()`**：status 必须保持 ready_for_review；run_id/paper_id 格式；argv 可执行文件白名单 + 文件参数必须 hash-declared in inputs/outputs；timeout 1..604800；estimated_cost_usd≥0；isolation∈{host,git_worktree,container}（container 镜像必须 `@sha256:` 固定）；resources 有界且显式资源需 container；runtime 需 `study_environment.definition` 精确匹配；seed=int；expected_outputs 唯一、相对、与 inputs 不相交、不含容器挂载分隔符；depends_on 指向同 paper 更早 run；不同 run 不共用 output 路径。
- **资源能力探测（不租硬件）**：`runner_capabilities()` 读 cgroup、`docker/podman info --format {{json .}}`、`nvidia-smi`，但固定 `hardware_provisioned:False`、`new_spending_authority:False`；`resource_errors()` 要求 docker 的 `MemoryLimit/CpuCfsQuota/CpuCfsPeriod` 真实 cgroup 支持（"rootless Docker 报告 host 容量不等于 cgroup 强制"）、GPU 需 verified nvidia runtime；云环境还校验 `cloud_runtime.execution_window()` 的 deadline。
- **角色/数据隔离执行**：`safe_environment()` 只透传白名单环境变量（PATH/LANG/TZ/...）+ `RESEARCH_OS_RUN_ID/RESEARCH_OS_SEED/PYTHONHASHSEED`，**不含任何 API key**（规则 16）；`execution_command()` 容器模式构造 `docker/podman run --rm --user --network=none --read-only --tmpfs ... --security-opt no-new-privileges --cap-drop=ALL --pids-limit=256 -v project:/workspace:ro`，仅 declared inputs 只读挂载、expected_outputs 单独可写挂载（"模型脚本不能改审批、预算、registry、代码或别的结果文件"）。
- **进程树终止**：`WindowsProcessJob`（ctypes `kernel32` Job Object，CREATE_SUSPENDED 后挂 job 再恢复主线程）、`terminate_process_tree()`（`taskkill /T /F` 或 `os.killpg(SIGKILL)`），保证父进程退出后子 worker 不能在封印后改文件。
- **每次尝试完整留痕 `run_one()`**：attempt 自增、`mkdir(exist_ok=False)`、既有输出先快照到 `previous-outputs/` 再删除（不覆盖历史）；执行后**二次校验输入 hash 未变**（`input_integrity`）、输出存在且非空、日志 2MB 有界截断、状态 succeeded/failed/timed_out、超时杀进程树；entry 含 argv/cwd/seed/timeout/git_commit/approved_plan_sha256/inputs/input_integrity/runtime(platform/python)/executor_isolation/resource_allocation/outputs/missing_outputs/preexisting_output_snapshots/logs/error；`append_registry` 追加、`run.json` 落盘、`archive_attempt()` 打包 zip（含 backup-manifest.json 逐文件 sha，"Back up every attempt, independently of manuscript presentation"）。
- **依赖校验 `verify_dependencies()`**：`primary_recovery.selected_attempt` 选成功 receipt，校验 status/paper_id/approved_plan_sha256/input_integrity.passed、receipt 文件匹配、每个 output sha 未变。

**依赖模块**：`research_artifacts(sha/path_in/utc_now)`、`paper_execution(artifact_path/approval/plan_errors/enabled)`、`research_phase(plan_errors/exposure_errors/exploratory/design_errors)`、`scientific_scope.validate`、`primary_recovery(gate_errors/histories/selected_attempt/require_next_attempt/records)`、`empirical_workflow.preflight_run`、`study_environment(definition/prepare)`、`cloud_checkpoint(sync_experiment_reservation/CheckpointError)`、`supplemental_experiments.all_compute_cost`、`cloud_runtime.execution_window`。

**边界与限制**：
- **真实子进程执行点**：`subprocess.Popen(command, shell=False)` 运行 python/Rscript/julia 或 docker/podman run——本组最"重"的真实执行点（本地/容器 CPU，**非付费 LLM API**）。
- **无付费 API 调用**：环境变量白名单不含任何密钥；成本全是保守计划估计，`reported_cost_usd` 从不在 entry 中填入。
- 安全：路径防穿越、容器只读根+禁网+cap-drop+只读挂载输入+只写声明输出、进程树终止、租约防并发、日志有界。

**特别标注**：
- **同名 `preflight_run` 两处**：本文件的是"运行前资源/依赖/cwd/输入 hash 检查"，`empirical_workflow.preflight_run` 是"实证输入契约检查"；`approved_plan()` 调后者、`_execute_locked/run_one` 调前者——阅读时极易混淆。
- **定义但主执行路径未直接调用**：`compute_budget_authority()`、`prior_estimated_cost()` 在本文件内未见于 `execute→_execute_locked` 主链（实际用 `project_compute_ceiling`+`all_compute_cost`），疑似供外部/其它模块或历史路径使用。
- 大量诚实标注：`actual_cost_known:False`、`actual_resource_use_measured:False`、`container_resource_limits_verified`、`hardware_provisioned:False`。
- 硬编码：DEFAULT_EXECUTABLES、DEFAULT_RESOURCES、docker flags、MAX_LOG_BYTES、lease 路径；`estimated_cost_usd` 与 `reported_cost_usd` 的保守会计策略。

---

## 14. figure_gallery.py（483 行）

**职责**：**固定（pinned）元数据-only 参考图检索**；无付费模型、无图像副本。双语概念词表改编自 MIT-licensed Top-Conf Figure Gallery；真实 CPU 图像嵌入检索在 `figure_gallery_semantic`。明确"检索分数、venue badge、布局参考从不验证科学"。

**对外能力**：CLI `operation∈{sync,search}` + `--project --query --top-k --venues/--years/--tiers/--patterns/--topics`；`sync()`, `load_index()`, `normalize_figures()`, `normalize_filters()`, `matching_figures()`, `lexical_rank()`, `write_report()`, `validate_search_report()`, `search()`, `concepts()`, `query_terms()`, `_download()`, `_preview()`, `_lock()`, `digest()`；类 `_NoRedirect`。

**输入/输出**：`LOCK=integrations/topconf-figure-gallery.lock.json`、`INDEX=literature/figure-gallery/index.json`、`RECEIPT=...index.receipt.json`；输出 `reports/figure-gallery/{digest[:24]}/search.json` + `index.html` + `packet.json`。

**关键机制**：
- **来源/固定校验**：`_lock()` 校验仓库 `qwdwqfwq/topconf-paper-figure-gallery`、commit(40 hex)、metadata.path=`data/figures.json`、sha256；`_url()` 强制 HTTPS + `HOSTS` 官方公开主机白名单；`normalize_figures()` 每条含双语 topic 推断、`image_downloaded:False`/`image_inspected:False`、`license.image_license:"unknown"`/`reuse_authorized:False`。
- **真实网络调用点**：`sync()`/`_download()` 用 urllib `build_opener(_NoRedirect).open()` 从 raw.githubusercontent.com 下载固定 commit 的 JSON 元数据（**禁止重定向**、3MB 上限、校验 size_bytes + sha256 + record_count），写 receipt 并 `record`；`load_index()` 每次消费都重校验下载字节 sha 与 receipt 一致。需云执行器。
- **检索/导出**：`lexical_rank()` BM25 元数据检索（双语概念 token + pattern 命中，`score_is_probability:False`）；`write_report()` 是 lexical 与 CPU semantic 共用的有界导出器，校验 candidates 逐字段绑定原始源；`_preview()` 生成**无 img 标签**、严格 CSP（`img-src 'none'; connect-src 'none'`）的 HTML（打开不下载第三方图像）；`packet.json` 为 `kind:untrusted_figure_reference_packet`，明确"不选择模型、不授权付费调用、不改已批准 claim"。
- **可复现复核**：`validate_search_report()` 校验内容 hash 与路径 ID 一致、provenance（deterministic-control-plane / scripts/figure_gallery.py）、implementation_sha256、source/snapshot、candidates；semantic 分支转 `figure_gallery_semantic.validate_report`，否则重放 `matching_figures+lexical_rank` 要求与 report 完全一致。
- 固定 `paid_api_calls:0`、`images_downloaded:0`、`BOUNDARY` 声明。

**依赖模块**：`research_artifacts(path_in/record/sha/write/strict_json)`、`output_provenance.current_origin`、`figure_gallery_semantic.validate_report`。

**边界与限制**：仅元数据/线索，非图像检查/复用许可/新颖性/claim 支持；`image_license:unknown`；年份硬编码 2023–2026、VENUES/PATTERNS/TIERS/HOSTS/CONCEPTS/STRUCTURES 全部硬编码词表。

**特别标注**：真实网络下载（raw.githubusercontent.com，非付费）；`_NoRedirect` 防 SSRF；与 figure_gallery_semantic 双向引用（此处调其 validate_report，后者调本文件 write_report/lexical_rank 等）。

---

## 15. figure_gallery_semantic.py（243 行）

**职责**：**云 CPU CLIP 检索**（对固定公开图嵌入），无付费 API。docstring 明写 "no paid API"；"A semantic request always executes the real model or fails; no fake fallback"。

**对外能力**：CLI `--project --query`；`lock()`, `verify_bytes()`, `provision()`, `assets()`, `clip_text()`, `embed()`, `matrices()`, `validate_report()`, `search()`；`LOCK=integrations/figure-gallery-semantic.lock.json`。

**关键机制**：
- **固定资产**：`lock()` 校验与 figure_gallery commit 一致、dimension=512、max_tokens=77、assets=5；`assets()` 从 raw.githubusercontent.com 下载 5 个固定资产（**真实网络**），用 `git blob sha1` + bytes 双重 `verify_bytes` 校验、缓存到 `.cache/...`、禁止重定向。
- **环境准备**：`provision()` 按需 `pip install .[figure-retrieval]`（`cloud_retry.run`，**真实网络/改环境**），校验 pinned `onnxruntime==1.23.2`/`tokenizers==0.22.1`。
- **真实本地 CPU 模型执行**：`embed()` 用 ONNX Runtime（强制 `providers==["CPUExecutionProvider"]`）、tokenizer 不截断/不填充、77 token 上限、512 维 text_embeds、L2 归一化，记录 `onnx_executions=1`/`query_embedding_sha256`/runtime 版本；`matrices()` 读 pinned `image_emb/text_emb` 二进制（float32），校验 ids 顺序/row_count/维度/归一化。
- **融合/执行 receipt**：`clip_text()` 双语概念扩展（"Unrecognized Chinese is retained, not pretended translated"）；`score=.40*image_cosine + .25*text_cosine + .35*lexical/(lexical+8)`；写 `reports/figure-gallery-semantic/{digest[:24]}.json` 执行 receipt（assets/lock_sha256/payload_sha256/implementation_sha256/`paid_api_calls:0`），再 `validate_report` 复核，最后 `gallery.write_report` 导出。
- `validate_report()` 复核 CPU 执行 receipt 的 provenance、sha、implementation、lock、payload_sha256、`provider=CPUExecutionProvider`、`onnx_executions==1`、assets 与 lock 一致。

**依赖模块**：`figure_gallery`、`research_artifacts`、`output_provenance.current_origin`、`cloud_retry.run`、onnxruntime/tokenizers/numpy（本地 CPU）。

**边界与限制**：本地 CPU 模型执行（非付费/非网络推理），但 assets 下载与 pip install 是真实网络；limitations 明写 "English CLIP + 双语概念扩展、上游嵌入、无视觉/科学批准"。

**特别标注**：硬编码融合权重 .40/.25/.35、512 维/77 token/pinned 版本；`provision` 会 pip install（改动云环境）；与 figure_gallery 共享 `_NoRedirect` 防 SSRF。

---

## 16. figure_layout.py（156 行）

**职责**：**固定 Nature figure 对齐与最终 PDF 碰撞适配器**——包装 vendored 第三方脚本的确定性审计层。

**对外能力**：`inspect_panels()`, `inspect_pdf()`, `save_audit()`, `validate_saved_figures()`, `refresh_native_figures()`；`ALIGNMENT=third_party/nature-figure/scripts/audit_panel_alignment.py`、`COLLISIONS=.../audit_figure_collisions.py`。

**关键机制**：
- `inspect_panels(fig)` 调 vendored `matplotlib_layout_manifest/audit_layout_manifest/exit_code`；`inspect_pdf(pdf)` 调碰撞审计，异常返回 `NOT AUDITABLE`/pass:False（fail-closed）。
- `save_audit()` 写 pdf_sha256/alignment/collision/pass/`human_visual_review_required:True`，`record_model_writes`（provider=deterministic-figure-layout, role=figure-layout-auditor）。
- **`validate_saved_figures()`——"never accept a writer's PASS flag"**：重算几何——每个 `*.spec.json` 必须有 `.figure-build.json`；校验 renderer==`scripts/publication_figures.py`、`renderer_sha256`、`panel_cache` 已退役、spec/data/outputs 的 sha、build/audit 的 provenance（deterministic-local-renderer / deterministic-figure-layout）、pdf_sha256、重放 alignment report 与 collision、pass 必须 True。
- `refresh_native_figures()` 写后渲染声明式 native specs（`publication_figures.render`），"outside model authority"，`human_visual_review_required:True`。

**依赖模块**：`research_methods(load_vendored_module/safe_path/sha256)`、`publication_figures(validate_spec/render)`、`output_provenance`。

**边界与限制**：纯几何/碰撞审计，不改数值/像素；`human_visual_review_required:True`；依赖 vendored 第三方脚本（`load_vendored_module` 固定 SHA 加载）。

**特别标注**：硬编码 third_party 路径与 renderer 名；`panel_cache is retired` 作为硬闸门；`inspect_pdf` 吞异常为 NOT AUDITABLE。

---

## 17. figure_output_qa.py（202 行）

**职责**：**检查实际矢量输出**；docstring 强调"数值数据与图像像素从不编辑"。

**对外能力**：`compact_text()`, `expected_glyphs()`, `verify_labels()`, `simulate_rgb()`, `final_size_qa()`, `audit_outputs()`；常量 `MACHADO_100`（Machado et al. 2009, DOI 10.1109/TVCG.2009.113 severity-100 色觉矩阵）、`MATH_SYMBOLS/WRAPPERS/SPACING/STRUCTURE`。

**关键机制**：
- `verify_labels()` 把 LaTeX 数学命令解析为字形签名（unknown/structural 命令需人工、`mathematical_layout_verified:False`），核对 SVG/PDF 可编辑文本节点是否含期望标签。
- `simulate_rgb()` 在 linear sRGB 下用 Machado 矩阵模拟 protan/deutan/tritan（gamut clipping）；`final_size_qa()` 按 final_width_mm 计算缩放后字号，<6pt 需 review、`manuscript_placement_verified:False`。
- `audit_outputs()`：逐输出校验路径安全（防 symlink/逃逸）、sha256；SVG 用 ElementTree 检查 editable text；PDF 用 fitz 读页面 mm 尺寸/文本 spans/字号，生成灰度与三种色觉模拟 PNG（`purpose:visual_QA_only`、绑定 source_pdf_sha256）；二次校验 sha 未变（"scientific output changed during QA"）。返回 `visual_review_required:True`、`accessibility_verified:False`、`scientific_data_checked:False`、`grayscale_and_color_vision_independent_review_required:True`、status∈{fail,review_required,pass}。

**依赖模块**：`research_artifacts.sha`、numpy、PyMuPDF(fitz)、Pillow（函数内 import）。

**边界与限制**：纯检查/预览生成，不编辑数值/像素；明确 `accessibility_verified:False`、`scientific_data_checked:False`、独立审查仍需。

**特别标注**：硬编码 Machado 矩阵、6pt 阈值、TeX 命令表；`import fitz/numpy/PIL` 缺失时记 error 不崩溃；生成 PNG 到 `reports/figure-output-qa/{sha}/`（QA 用途，绑定源 PDF hash）。

---

## 18. figure_profile.py（64 行）

**职责**：剖析真实图数据并**建议**图表族，不发明数值。

**对外能力**：CLI 位置参数 `data`；`profile(path)`。

**关键机制**：借 `publication_figures._read_table`（pandas）读表，逐列统计 dtype/missing/distinct/numeric + 数值列 min/median/max/IQR 离群数；按 numeric/categorical 数给 `suggestions_not_decisions`（scatter/line/correlation/pca(仅预计算坐标)/box/violin/strip/bar with declared uncertainty/histogram/ecdf）；issues（小样本 n<20 显示观测、缺失须在注册分析中处理、离群不静默丢弃）；返回 `source_sha256`、`question_for_author`。

**依赖模块**：`publication_figures._imports/_read_table/sha256_file`（**依赖私有函数**）。

**边界与限制**：纯建议（"suggestions_not_decisions"）；`pca (precomputed coordinates only)` 明确不自行计算；不插补、不发明数值；无网络/付费。

**特别标注**：硬编码建议规则与阈值（20 行、IQR 1.5）；依赖 publication_figures 的私有 API，耦合较紧。

---

## 19. figure_provenance.py（499 行）

**职责**：**记录并校验确定性、非 Claude 的最终图来源（provenance）**——AGENTS.md 规则 14/18 的核心落地："结果型图必须由记录数据本地渲染、绝不打包 provenance 指向 Anthropic/Claude 为持久写者的文件"。

**对外能力**：CLI 子命令 `record`、`approve-illustration`、`validate`、`derive`；`_scope()`, `run_seal()`, `lineage()`, `derive()`, `record_figure()/_record_figures()`, `record_generated_illustration()`, `rendered_sources()`, `register_rendered_figures()`, `visual_observations()`, `validate_figure_provenance()`, `_csv_transform()`, `receipt_path()`, `_load_registry()`, `_relative()`。常量 `FIGURE_SUFFIXES`、`FIGURE_TYPES={data_chart,conceptual_diagram,conceptual_illustration}`、`PREFIX=reports/figure-data`。

**输入/输出**：读 G3 approval/prereg/registry/executor receipts/provenance；写 `papers/{P##}/figures/figure-provenance.json` registry、`papers/{P##}/figures/source-data/*.csv` + `reports/figure-data/{hash}.json` receipt。

**关键机制**：
- **`_scope()`**：处理 supplemental 命名空间（校验 supplemental_experiments scope 控制文件 provenance、child state sha、G3 approval、命名科学 confirmation、密封 evidence files sha）。
- **`run_seal()`（核心封印）**：校验 G3 approval（actor + experiment_plan_sha256 + experiment_budget_sha256 + frozen_protocol_sha256）、preregistration frozen、frozen files sha（`cloud_checkpoint.excluded` 原始大数据豁免）、registry + `primary_recovery.selected_attempt` 成功 receipt、argv/seed/cwd/timeout 与 plan 一致、inputs sha、`input_integrity`、executor `run.json` 与 receipt 一致、outputs 集合与 expected_outputs 一致且 sha 未变；返回全部 digest 绑定。
- **确定性派生绘图数据**：`derive()/_csv_transform()/lineage()` 从封印的 executor outputs 派生（`concatenate/project/group_mean/json_rows`，≤100000 行、10MB 源、无插补），写 CSV + receipt（transform/lineage/implementation_sha256/`scientific_completion_verified:False`）；`lineage()` 递归（深度<20、防环）重放血缘并 `_csv_transform` 重算校验。
- **登记图来源**：`_record_figures()` 登记"一个绑定源上下文跨多个原生格式"——renderer 必须非 Claude（`family!="anthropic"`）、inputs sha、data_chart 需 ≥1 input + source_run + `lineage`、config 非 Claude、输出在 paper figures 目录、`record_model_writes`（provider=deterministic-local-renderer, role=final-figure）；`review_kind=legacy_human`/`automated`。
- **概念插画单独路径**：`record_generated_illustration()` 登记 GPT Image / ChatGPT web 概念插画——`deterministic:False`、`prompt_sha256`、`model_id`、`disclosure_location`、`generated_by∈{gpt-image-api,chatgpt-web}`、非 Claude provenance（呼应规则 14 "GPT Image 只能做单独标注的概念插画，绝不数据图"）。
- **校验**：`validate_figure_provenance()` 校验 editable export receipt（`verify_export`）、actual vs registry 一致、每条 record 的 output/renderer/inputs/config sha 与 provenance 非 Claude、data_chart 的 `source_lineage` 重放一致、illustration 不得声明实验 inputs/runs、自动视觉审查（`automated_visual_review.verify`）或命名人工检查；`rendered_sources()/register_rendered_figures()` 从 native render receipt 反查 run_id 绑定。

**依赖模块**：`output_provenance`、`research_artifacts(path_in/read/record/sha/write/verify_files/json_digest)`、`paper_execution`、`cloud_checkpoint.excluded`、`primary_recovery.selected_attempt`、`editable_figures.verify_export`、`automated_visual_review.verify`、`supplemental_experiments`（scope 文件）。

**边界与限制**：`scientific_completion_verified:False`；视觉审查仍需自动或人工；`conceptual_illustration` 被排除在 `record` 子命令 choices 之外（必须走 approve-illustration）。

**特别标注**：**`run_seal` 被 `empirical_reporting.measured/_diagnostics` 调用**（第 5 节），是本组关键纽带；`language_checked_by` 为空时 `review_kind=automated` 并删掉人工字段；硬编码 FIGURE_TYPES/路径/命名角色。

---

## 20. figure_recipes.py（307 行）

**职责**：**额外确定性科学图表配方；从不推断统计量**。ROC/PR/calibration/PCA/survival 等输入必须已由注册分析计算，"Plotting code does not estimate or fit a model"。

**对外能力**：`KINDS`（32 种图：box/violin/strip/histogram/density/ecdf/area/stacked_bar/dumbbell/errorbar/roc/pr/calibration/confusion/correlation/volcano/pca/survival/sankey/raincloud/hexbin/qq/funnel/waterfall/bland_altman/kaplan_meier/shap_summary/nomogram/decision_curve/network/chord/geospatial）、`RAW_DISTRIBUTIONS`、`required_fields(panel)`, `draw(ax, panel, frame, np, pd, palette)`。

**关键机制**：纯 matplotlib 绘制，按 kind 分支；严格校验有限值/概率∈[0,1]/无插补/确定性 jitter（"independent of global random state"）/组数≤8（palette 长度）；`density` 明确"histogram density, not a fitted KDE"；`errorbar` 需声明 lower/upper 列；`kaplan_meier`/`survival` 等要求预计算 risk/survival 输入；不支持 kind 抛 "unsupported chart"。

**依赖模块**：matplotlib、pandas、numpy（np/pd 由调用方传入）、matplotlib.patches（network/chord/sankey）。

**边界与限制**：纯绘制，不拟合/不估计/不插补；输入须预先计算；无网络/付费。

**特别标注**：**`correlation` 分支实际调用 `frame.select_dtypes(include="number").corr()` 计算相关矩阵**——与 docstring "never infer statistics / 绘图代码不估计或拟合模型" 存在轻微语义张力（虽是 pandas 内置轻量计算、非拟合），属"文档宣称与行为需留意处"；硬编码 32 种 KINDS 与阈值（bins 5-100、volcano 阈值、8 视觉组）。

---

## 21. figure_reference_acceptance.py（197 行）

**职责**：**云集成重放**（用公开参考 + 显式软件夹具）：下载固定元数据/CPU 嵌入资产、执行真实 ONNX 文本推理、渲染合成 proposed 图。**无付费模型调用、无真实研究结果、无人工批准、无科学完成**。

**对外能力**：CLI `--directory`（默认 `artifacts/figure-reference`）；`run()`, `_fixture()`, `_anchor()`, `_fixture_file()`, `_render_pptx()`, `_staleness()`。

**关键机制**：
- `run()`：`gallery.sync`（真实下载）+ 中英文双语 `gallery.search`（"时间序列预测的架构图"/"time series prediction architecture"）+ 结构化 filters + `validate_search_report`；`semantic.provision`（pip install）+ `semantic.search`（真实 CPU CLIP）+ `validate_search_report`；`_fixture` 构造合成项目；`_render_pptx`（LibreOffice+Poppler 把 PPTX→PDF→PNG 并核对标签）；`_staleness` 篡改 4 个输入验证 `verify_export` 会拒绝（changed_inputs_rejected）；写 summary.json（`software_checks_passed`、`paid_model_calls:0`、`scientific_completion:False`、limits）。
- `_fixture()` 调 `story.execute(style_prepare)`、`story.prepare`、`story.validate_saved_report`、`editable_figures.export/verify_export`；断言 SVG 无 `<image>`（不能是扁平栅格）、PPTX 有可编辑连接符与 live text、无 `ppt/media`（不藏扁平图）、`manuscript_alignment=="source_locations_checked"`、三种原生格式且 `raster_elements==0`。

**依赖模块**：`editable_figures`、`figure_gallery`、`figure_gallery_semantic`、`figure_story`、`output_provenance`、`research_artifacts`；外部命令 `libreoffice/pdftoppm/pdftotext`。

**边界与限制**：软件验收/合成夹具；真实网络下载 + 真实 CPU 推理 + 真实本地渲染，`scientific_completion:False`；`--directory` 必须在仓库内且 ≠ ROOT。

**特别标注**：大量 `_need` 断言；`expected_count>3000` 硬编码真实语料规模检查；是把 figure_gallery/semantic/editable_figures/story 端到端串起来的验收入口。

---

## 22. figure_reference_context.py（39 行）

**职责**：给现有模型角色的**小型显式 source-bound 参考图上下文**。

**对外能力**：`context(project) -> str`。

**关键机制**：读 `program/figure-reference-context.json`（≤8KB），校验 selection 恰 `{report, figure_ids}`、report 恰 `{path,sha256}`、1-5 个唯一 figure_id、path 以 `reports/figure-gallery/` 开头、sha 绑定、`figure_gallery.validate_search_report` 复核、选中 id 必须在 bound search 结果中；返回 JSON 字符串 `kind:untrusted_layout_references`（含 query/references/boundary，references 只取白名单字段 id/title/venue/year/pattern/paper_url/figure_url/metadata_sha256/license）。无 selector 时返回提示文本（"free gallery search only when needed, then explicitly select at most five references"）。

**依赖模块**：`research_artifacts(path_in/read/sha)`、`figure_gallery.validate_search_report`。

**边界与限制**：纯上下文构造，明确 `untrusted_layout_references`；最多 5 个显式选择；无网络/付费。

**特别标注**：无 selector 时返回**提示文本而非空**；与 figure_gallery 的 untrusted packet 语义一致；是把"检索报告"喂给模型角色前的最后一道显式选择校验。

---

## 23. figure_story.py（445 行）

**职责**：**source-bound 主图 brief 与共享视觉 token；无模型调用**。brief 是"候选构图"、绝非科学批准；外部 gallery 记录是发现元数据，非已检查图像或自有结果；手稿/claims/diagram IR/executor receipts 保持 canonical。

**对外能力**：CLI `--project --operation{prepare,validate,style_prepare,style_validate} --request-file`；`build_report()`, `prepare()`, `validate_saved_report(project, report_path: Path)`, `execute()`, `validate_style()/default_style()/load_visual_style()/visual_style()`, `_manuscript_sources()`, `_results()`, `_numeric()`, `_references()`, `_anchor()`, `_check_phase()`, `_binding()`, `_authored()`, `_contrast()`, `_implementation()`。常量 `STYLE_PATH=program/figure-visual-style.json`、`NODE_KINDS`(9)/`EDGE_KINDS`(6)、`NUMBER`、`PHASES={method,planned,observed}`。

**输入/输出**：`figure-story-request`（约 20 字段，phase∈{planned,observed}）；输出 `reports/figure-story/{id}.json`（`status:"candidate"`、`request_sha256`、`inputs`、`implementation`/`implementation_sha256`、`visual_style`、`manuscript_alignment`、`checks`、`limits`）。

**关键机制**：
- **共享视觉 token**：`validate_style()/default_style()` 固定六篇论文 portfolio（`paper_ids==[P01..P06]`）、字体/字号范围、node_fills/edge_colors/edge_styles 覆盖所有 kind、6 位 hex、association=dashed/feedback=dotted（非颜色编码）、对比度≥4.5、legend_policy 固定；`load_visual_style` 要求非 Claude provenance；`visual_style()` 返回 `static_tokens_checked`/`final_size_human_inspection_required:True`。
- **source-bound brief `build_report()`**：必须绑定 canonical paper-contract 与 claim matrix（`paper_execution.artifact_path`）、diagram IR（`research_diagrams.validate`）、`_authored`（require_final_origins）、sources、manuscript（`_manuscript_sources`：canonical TeX + `tex_sources.expand` + 逐文件 `_authored`；**DOCX paragraph mapping "not implemented" 明确拒绝**）、results（observed 阶段需 `figure_provenance.run_seal` 封印的真实结果、claim 的 analysis_ids ⊆ used_runs 且 support 状态合法）；problem/contribution/每个 module/connection/panel/numeric_binding 都带 `text_locator`（`_anchor`：path+sha+行范围≤50、quote 必须在对应行、kind 白名单、English `_text` 拒绝中文）；planned 图标题/caption 须标 proposed/planned/expected；flow/panels 覆盖所有节点与 claims；**`_numeric()` 图中每个字面数字必须有 source binding**；`_references()` 绑定 gallery search report + 2-10 个参考候选。
- `limits` 固定 `scientific_approval:False`、`semantic_alignment_requires_independent_review:True`、`reference_images_inspected:False`、`external_results_reusable_as_our_results:False`、`final_render_inspection_required:True`、`paid_model_calls:0`；`prepare()` 幂等（相同 reused）、`validate_saved_report()` 重放 build_report + provenance、`style_prepare` 写共享样式（`candidate_tokens`, `scientific_approval:False`）。

**依赖模块**：`research_artifacts`、`output_provenance`、`paper_execution.artifact_path`、`research_diagrams.validate`、`tex_sources.expand`、`ref_verify_adapter.canonical_manuscript`、`figure_provenance.run_seal`、`figure_gallery.validate_search_report`。

**边界与限制**：无模型调用；brief 是 candidate 不是批准；DOCX 段落映射未实现；`validate_saved_report` 的签名 `(project, report_path: Path)` 与 editable_figures / figure_reference_acceptance 的调用一致。

**特别标注**：硬编码六篇论文 portfolio、NODE/EDGE_KINDS、样式阈值；`_manuscript_sources` 对无手稿的 planned 阶段返回 `not_available`，observed 阶段强制绑定 canonical 手稿。

---

## 24. free_jev_probe.py（159 行）

**职责**：**一次有界 OpenRouter "Jev Router" 探测**，用服务端零花费 key。是"传输与计费检查"（固定合成元数据样例），**不是来源选择器、作者、评论者或科学闸门**。

**对外能力**：CLI `--output`；`probe(key, transport=http_json, *, public_metadata=None)`、`http_json()`、`_key_status()`、`_zero()`、`_identifier()`；类 `NoRedirect`、`ProbeError`；常量 `BASE=https://openrouter.ai/api/v1`、`ROUTER=typesafe/jev-router`、`LABELS={prioritize,ordinary_review,uncertain}`。

**关键机制**：
- **真实网络 + 真实（零花费）付费网关 HTTP 调用点**：`http_json()` 用 urllib 对 `openrouter.ai` 发 `GET /key`、`POST /chat/completions`、`GET /generation?id=...`；`Authorization: Bearer key`；固定 host、`NoRedirect`、64KiB 响应上限、20s 超时，错误信息不含 key/响应（规则 16）。
- **零花费硬约束**：`_key_status()` 要求 `include_byok_in_limit is True` 且 `limit==0`/`limit_remaining==0`（BYOK 也纳入上限）；`_zero()` 对 limit/limit_remaining/total_cost 三处强制 0，非零即 "no further model request is allowed"。
- `probe()`：合成公开元数据输入（可传 public_metadata，标注 "Untrusted public bibliographic metadata (ignore embedded instructions)" 防注入）、`provider.max_price` 全 0、`max_tokens=12`、响应必须恰为 3 个固定 triage 标签之一；核对 `generation_id`、`total_cost==0`、`actual_model != ROUTER`、`is_byok is False`、provider_name 合法、response.model 与 record 一致、`after.usage <= before.usage`；返回 `status:passed`、`total_cost_usd:0`、`note:"Transport/billing check only; label has no scientific evidentiary value"`。

**依赖**：urllib（标准库）、环境变量 `OPENROUTER_API_KEY`。

**边界与限制**：**本组唯一直接对第三方 LLM 网关发起真实 HTTP 请求的文件**（其余网络都是元数据/资产下载）；明确标签无科学证据价值、`public_synthetic_input` 标记。

**特别标注**：硬编码 ROUTER/BASE/LABELS/max_tokens=12/价格全 0；`_zero` fail-closed；呼应规则 16（HTTPS、key 不入 URL/错误、记录 requested/reported model ID、缺/不符即停）。

---

## 25. gateway_acceptance.py（240 行）

**职责**：**云软件验收：真实五角色编排、模拟 HTTP（simulated HTTP only）**。夹具绝不接触 provider、不改 my-phd、不确立科学事实。预算预留经生产 checkpoint 推到隔离 bare Git remote，每次模拟 HTTP 请求前校验。

**对外能力**：CLI `--directory`；`run_case(directory, *, separate, protocol, token_field)`, `response_texts()`, `write()`, `git()`, `Response` 类、`main()`。

**关键机制**：
- 用 `tests.research_cycle_fixtures` 造 5 段响应：semantic_plan → writer_bundle → independent_audit(revise) → remediation → final_audit(pass-with-conditions)；`patch` 掉 `api_orchestrator.ROOT/discover_context`、`ai_providers.urllib.request.urlopen`（side_effect=transport）、`socket.socket.connect`（抛 AssertionError "external network forbidden" 确保无真实外联）。
- `transport()` 每次请求前 `git show` 隔离 bare remote 的 `model-spend-control.json`，断言 `reservations==1`、`authorization_events` 未变、`spent_cny≈index*0.00044`；校验 endpoint/model/headers/token field（responses 用 max_output_tokens、chat_completions 用 max_completion_tokens 或 legacy max_tokens）。
- `run_case()`：`api_orchestrator.run_cycle(...)` 跑真实五角色编排（planner→writer→critic→remediator→critic），`cloud_checkpoint.sync_billing`，断言最终 `reservations=={}`、`spent_cny≈0.0022`、state/run.json 字节未变、ledger 5 个 role 顺序、program/topic.md 的 provenance family=openai/role=persistent-remediator、manifest final_verdict、provider_audit 的 requested==reported model、所有文件 `check_file`；导出 fixture 产物 + receipt（`real_paid_calls:0`、`scientific_completion_verified:False`、five_roles_verified、remote_reservations_verified、human_gates_unchanged）。
- `main()` 跑 4 个 case（shared/separate × responses/chat_completions × token field），写 acceptance.json（`status:passed`、`real_paid_calls:0`）。

**依赖**：`tests.research_cycle_fixtures`、`api_orchestrator`、`cloud_checkpoint`、`model_runtime`、`model_spend`、`unittest.mock.patch`；外部命令 git。

**边界与限制**：**模拟 HTTP，无真实付费调用**（`real_paid_calls:0`、`socket.connect` 被阻断）；软件接线/预算持久化验收；`scientific_completion_verified:False`、fixture_only——正呼应 AGENTS.md 规则 5"软件验收本身绝不确立无人值守研究项目成功"。

**特别标注**：硬编码 5 个响应文本、`spent_cny≈index*0.00044`、SLUG="gateway-fixture"；`assert` 密集；是验证"角色隔离 + 预算预留 + provenance + 独立审计"编排的软件验收入口（规则 5/13/17）。

---

## 26. incremental_evidence.py（355 行）

**职责**：**类型化文献血缘（lineage）、有界 gaps、经核验的云摄取 receipt**。机械对应永不是语义支持/新颖性/科学完成。

**对外能力**：`text/identifier/rows/strings/binding/anchor/anchors/jsonl/primary_attempts/lineage/_lineage/_paper_lineage/gaps/ingest`；常量 `ID/DIGEST/GAP_TYPES/STATES/KINDS`。

**关键机制**：
- `anchor()` 校验真实源坐标（PDF 用 fitz 页码 + quote 恰好出现一次；文本用 source_lines + quote 恰好一次），`semantic_support_verified:False`；"never invent rendered page numbers"。
- **`_lineage()`**：节点需 kind∈KINDS、research_state∈STATES、read_scope∈{full_text,abstract,excerpt,metadata}、statement/boundary；evidence anchors 不得来自 `reports/research-increments/` 或 `state/`（"不能自证或用控制记录当科学证据"）；metadata 不能支撑实质性发现、mechanism/procedure/table/figure 需 full_text；full_text 需 `source_scope.verify`；DAG 无环、review_report/review_interpretation/project_inference 的 parents 约束、interpretation 不能提升为 executed observation；`project_observation` 必须绑定唯一 executor attempt（`primary_attempts` 从 primary_registry_paths 读所有论文 registry）、状态匹配 research_state、receipt 一致、input_integrity、outputs sha、plan run 绑定；**confirmatory 需 `experiment_evidence.validate_report` 通过**；fact_links 必须恰好覆盖 paper-facts.json 的所有 facts。返回 `semantic_support_verified:False`、`human_read_scope:"not_declared"`。
- `gaps()`：gap types⊆GAP_TYPES、status∈{candidate,unknown,refuted}（"novelty is never granted"）、scope∈{supplied_materials,executed_queries}（"有限来源不能确立领域级缺失"）、8 个必填文本字段、attribution∈{author_acknowledged,reader_inferred}、counterevidence 处理、绑定 hypothesis-register/novelty-claim-matrix/originality-audit、counter_search_ids 必须在 search-log 且有真实成功 provider receipt（literature-api-ledger）、receipt 的 raw/normalized sha 校验、`coverage:"returned_results_only"`/`field_complete:False`；full_text 需 source_scope.verify；返回 `novelty_granted:False`、`scientific_validation:False`。
- `ingest()`：DOI/arXiv 身份（拒绝 title-only 去重）、HTTPS source_url 无凭据、version；`identity_status:"bibliographic_identity_unverified"`、`model_calls:0`/`network_calls:0`；可选 attachment PDF（≤50MB、非加密、1-2000 页）+ rights_manifest + `state/data-authorizations.json` 授权 + download sha/bytes 校验 + fitz 前两页 title/identifier 匹配 + 可读文本检测 + scope_record `source_scope.verify`；`identity_key`/`content_key` digest。

**依赖**：`research_artifacts(path_in/read/sha/json_digest)`、`paper_execution(artifact_path/primary_registry_paths/paper_scoped)`、`source_scope.verify`、`experiment_evidence.validate_report`、fitz。

**边界与限制**：机械对应不确立语义/新颖性/完成；`semantic_support_verified:False`、`novelty_granted:False`、`field_complete:False`；ingest 本身 `network_calls:0`（校验已有 receipt，不下载）。

**特别标注**：硬编码 GAP_TYPES/STATES/KINDS 词表；`binding()` 只校验 sha 不校验大小；`_lineage` 的 confirmatory 与 experiment_evidence 交叉；`ingest` 的 identity_status 明确 "unverified"/"candidate"。

---

## 27. incremental_rules.py（162 行）

**职责**：**失败教训成为有界检查器候选，绝不自我批准为 policy**。"Adopted rules remain advisory; they cannot approve science or change models"。

**对外能力**：`checker()`, `predict()`, `candidate()`, `binding_spec()`, `cases()`, `freeze()`, `implementation()`, `evaluate()`, `active_checks()`；`ROOT=reports/research-increments`。

**关键机制**：
- `checker()` 只允许 `{op, terms}`，op∈{contains_any,contains_all,missing_all}（"never executable code or regex"）、terms 1-30 个且每个≤200 字符；`predict()` 纯字面大小写不敏感匹配。
- `cases()` 从 benchmark 读 `cases`（6-600），每个需唯一 id、split∈{development,validation,holdout}、expected_flag bool、rationale、source binding、文本≤100KB；按归一化内容 digest + group_id 去重（含改名文件）跨 split 不共享内容/independence group；每 split 需正负例。
- `freeze()` 把 candidate + disjoint splits 冻结到 `reports/research-increments/rule-benchmarks/{id}.json`（`adopted:False`、implementation_sha256），已存在则内容须一致（"cannot be overwritten; use a new version ID"）。
- `evaluate()`：lesson 必须是 anchor 且不能来自 ROOT/state（"规则提案不能充当自己的失败教训"）；校验冻结的 candidate/benchmark/cases/implementation/provenance；逐 split 配对 baseline vs candidate 预测、记录 regressions；`independent_improvement = validation 与 holdout 的 candidate_errors 均严格小于 baseline`；eligible 需无 regression 且独立改进；返回 `status∈{eligible_for_owner_review, rejected}`、`adopted:False`、`scientific_effectiveness_verified:False`、`scope:"literal_checker_on_frozen_cases_only"`、`model_calls:0`。
- `active_checks()` 从 `state/research-increment-rules.json` 读 active_ids，校验 `research_increments.load` 的 lessons 存在、`confirmation(...,"adopt_rule")` 授权、`evaluate` 仍 eligible，对 targets 产出 `flagged`（`effect:"advisory_only"`）。

**依赖**：`incremental_evidence`（大量复用其 anchor/binding/digest/identifier/rows/strings/text）、`research_artifacts`、`output_provenance`、`research_increments.load`。

**边界与限制**：**advisory only**，不能批准科学或改模型；`adopted:False` 默认、需外部 owner confirmation 才可能 active；无网络/付费。

**特别标注**：`implementation()` 用 `sha(__import__("pathlib").Path(__file__))` 写法绕（等价 sha(Path(__file__))）；硬编码 6 例下限、30 terms、200 字符、100KB；与 incremental_evidence 是紧耦合"教训→规则"子层。

---

# 整体归纳

## 一、本组整体能力（27 文件 / 8761 行）

1. **动态模型路由与累计成本策略**：`dynamic_routing` 在冻结盲审包 + 真实人工评分 + 独立结算账单 + held-out 校准的严格条件下，才允许从批准 baseline 切换到更便宜/更快候选，且内置角色隔离硬编码（Claude 只读、writer 必须 OpenAI、panel 保留 family）。
2. **有界经济数据采集**：`economic_data` 对 FRED / World Bank 官方 API 做权限绑定、历史 vintage 声明、不可变快照、凭证防回显的 HTTPS 采集。
3. **实证全链路**：`empirical_design`（预注册设计审计）→ `empirical_runtime`（唯一被审阅的 3 种确定性估计器）→ `experiment_runner`（唯一 G4 执行器）→ `experiment_evidence`（统计证据/claim 覆盖/Holm 校正）→ `empirical_reporting`（重算核对 + 手稿数字映射 + 完整归档）→ `empirical_workflow`（G3/G4/G5 闸门编排），外加 `engineering_contract`（工程建议的 prompt 契约）。
4. **证据上下文与检索**：`evidence_context` 构造含反证据、强制完整契约、防盲审泄漏的源包；`evidence_retrieval` 做 BM25/RRF + 可选缓存向量线索（无 AI 调用）。
5. **实验证据与执行审计**：`experiment_evidence`、`experiment_runner`、`figure_provenance.run_seal` 把 G3 seal、registry、executor receipt、输入/输出 hash 全部串成证据链；`experiment_evidence_acceptance` 用合成夹具验证决策路径（含失败 pilot、负结果保留）。
6. **图表全链路**：参考图检索（`figure_gallery` 元数据 BM25 + `figure_gallery_semantic` 本地 CPU CLIP）→ 显式选择（`figure_reference_context`）→ 主图 brief/共享样式（`figure_story`）→ 原生可编辑导出（`editable_figures`）→ 来源登记（`figure_provenance`，非 Claude）→ 几何/尺寸/色觉 QA（`figure_layout`/`figure_output_qa`）→ 数据剖析/图表配方（`figure_profile`/`figure_recipes`）→ 端到端软件验收（`figure_reference_acceptance`）。
7. **网关与编排验收**：`free_jev_probe`（真实零花费传输/计费探测）、`gateway_acceptance`（模拟五角色编排 + 远程预算预留验收）。
8. **增量证据/规则**：`incremental_evidence`（类型化文献血缘、有界 gaps、摄取 receipt）、`incremental_rules`（失败教训→冻结基准→有界字面检查器候选，advisory only）。

## 二、在 G0–G5 中的位置

- **G0/G1 前期**：`gateway_acceptance`（G0 intake 软件验收，模拟）、`dynamic_routing`（含 G1 transport-validation 特殊分支）、`evidence_context`/`evidence_retrieval`（topic-intelligence 上下文/线索）、`free_jev_probe`（传输检查）。
- **G2 选题**：`figure_story`/`figure_reference_context` 产出"喂给模型角色"的 source-bound 参考/构图上下文（人工决策仍须显式记录，本组不伪造）。
- **G3 冻结/预注册（核心）**：`empirical_workflow.preregistration_inputs`、`empirical_design.audit`、`experiment_evidence.validate_plan/validate_scientific_bindings`、`figure_provenance.run_seal` 的 G3 approval；`experiment_runner.approved_plan` 在执行前复核 G3 冻结的 plan/budget/preregistration hash。
- **G4 执行与结果证据（核心）**：`experiment_runner`（唯一执行、每次尝试留痕、累计预算、容器隔离）、`experiment_evidence.build_report`（数值证据/claim 覆盖）、`empirical_runtime`/`measured`、`incremental_evidence`（gap/lineage/observation）、`figure_provenance`（结果图 lineage）、`empirical_reporting`（结果表）。
- **G5 独立审查与投稿包**：`figure_provenance.validate_figure_provenance`、`figure_layout.validate_saved_figures`、`figure_output_qa`、`empirical_reporting(require_mapping=G5)`、`experiment_evidence.validate_scientific_bindings(G5 claim_alignment)`、`figure_story`（observed 阶段）。**全组无投稿代码**，符合"绝不自动投稿"。
- **贯穿全程**：哈希/来源绑定、累计预算、失败与负结果留痕、角色隔离、`scientific_*_verified:False` 的诚实标注。

## 三、组内调用关系（枢纽）

- **experiment_runner**（执行枢纽）→ `empirical_workflow.preflight_run`、`cloud_checkpoint.sync_experiment_reservation`、`primary_recovery`、`scientific_scope`、`paper_execution.approval`、`study_environment`。
- **experiment_evidence**（统计证据枢纽）→ `empirical_design.audit`、`empirical_reporting.measured`、`figure_provenance(间接)`、`study_routes`、`results_validation`、`scientific_reasoning`、`primary_recovery`。
- **empirical_reporting** → `empirical_design.audit`、`empirical_runtime.calculate`、`figure_provenance.run_seal`、`experiment_evidence.comparison_archive`（与 experiment_evidence 双向）。
- **empirical_workflow** → `economic_data`、`empirical_design`、`empirical_reporting`、`data_contracts`（组外）。
- **figure_provenance.run_seal** 被 `empirical_reporting.measured/_diagnostics`、`figure_story._results`、`experiment_evidence` 链路共用；`figure_provenance.validate_figure_provenance` → `editable_figures.verify_export`。
- **figure_story** → `figure_provenance.run_seal`、`figure_gallery.validate_search_report`、`research_diagrams`、`tex_sources`、`paper_execution`。
- **editable_figures** → `figure_story.validate_saved_report`、`research_diagrams`、`output_provenance`、`publication_figures`。
- **figure_gallery ↔ figure_gallery_semantic** 双向（前者 validate_search_report 调后者 validate_report，后者复用前者 write_report/lexical_rank/_NoRedirect）。
- **figure_reference_acceptance** → `figure_gallery`/`figure_gallery_semantic`/`editable_figures`/`figure_story`（端到端验收）；**figure_reference_context** → `figure_gallery.validate_search_report`；**evidence_retrieval** → `evidence_context.safe_text`。
- **experiment_evidence_acceptance** → `experiment_runner.execute`、`experiment_evidence.build_report`、`results_validation`。
- **gateway_acceptance** → `api_orchestrator`/`cloud_checkpoint`/`model_spend`/`model_runtime`（组外真实编排层）。
- **incremental_rules** → `incremental_evidence`（紧耦合）；`incremental_evidence` → `experiment_evidence.validate_report`。
- **公共底座（组外）**：`research_artifacts`、`output_provenance`、`paper_execution`、`primary_recovery`、`cloud_checkpoint`、`model_spend`、`model_routing`、`ai_providers`、`publication_figures`、`research_diagrams`、`source_scope`、`scientific_reasoning`。

## 四、特别标注汇总

### TODO / 占位 / 未实现 / 宣称但未实现
- `empirical_design.validate_specification` / `empirical_runtime`：明确拒绝 staggered DID、dynamic DID、fuzzy RDD、弱 IV 稳健置信集、过度识别检验、聚类/HAC IV、偏差校正 RDD——"需另一个 reviewed adapter"，**未实现**。
- `figure_story._manuscript_sources`：DOCX paragraph mapping 明确 "not implemented"（observed 阶段强制 canonical TeX）。
- `figure_gallery_semantic`：图像嵌入是上游提供的固定二进制，本组不训练/不下载原图；`evidence_retrieval` 的 dense/rerank 都是缓存，**无真实 embedding / reranker 请求**（`embedding_calls_made:0`/`reranker_calls_made:0`）。
- `experiment_evidence` 的 `registered_result` 自定义分析模式："hash-checked but not statistically recomputed here"。
- `dynamic_routing.record_acceptance` 的 actor 仅字符串参数、无独立鉴权（注释称"仅 manager 控制面、绝不由 scientific writers 调用"是约定，代码未强制）。
- `figure_gallery` 的 `image_license:"unknown"`/`reuse_authorized:False`——不提供任何权利判定。
- `incremental_rules.active_checks` 的 adopted 规则仅 advisory、`adopted` 默认 False，需外部 owner confirmation 才可能 active。
- **规则 13 宣称的"真实独立 critique / problem-triggered repair"**：本组 `gateway_acceptance`（cycle_fixtures 模拟）、`experiment_evidence_acceptance`（合成 fixture）均为软件验收；**本组未见真实付费独立审计调用点**（应在组外 api_orchestrator/model_runtime）。规则 5 亦明确"软件验收本身绝不确立无人值守研究项目成功"，与代码 `scientific_completion_verified:False` 一致。

### 真实网络 / 付费 API 调用点（重点）
1. **`free_jev_probe.py`**：`http_json()` 对 `https://openrouter.ai/api/v1` 发 `GET /key`、`POST /chat/completions`、`GET /generation`——**本组唯一真实第三方 LLM 网关 HTTP 调用**；但强制服务端零额度 key（`include_byok_in_limit`、`limit=0`）、max_price 全 0、`_zero` 校验 total_cost=0、`is_byok is False`、合成输入、标签无科学价值。
2. **`economic_data.py`**：`network_safety.fetch_bytes` 对 FRED / World Bank 官方 API 的 HTTPS GET（真实网络，非付费，FRED 需 `FRED_API_KEY` 环境变量）。
3. **`figure_gallery.py`**：`_download()` 从 raw.githubusercontent.com 下载固定 commit 元数据（真实网络，非付费）。
4. **`figure_gallery_semantic.py`**：`assets()` 下载 5 个固定资产 + `provision()` 的 `pip install .[figure-retrieval]`（真实网络/改云环境）；`embed()` 是本地 CPU ONNX 推理（非网络/非付费）。
5. **本地子进程/容器执行（非付费 API）**：`experiment_runner`（subprocess/docker/podman）、`figure_reference_acceptance`（LibreOffice/Poppler）、`editable_figures`（python-pptx）、`figure_layout`（vendored 脚本）、`experiment_evidence_acceptance`（docker）。`gateway_acceptance` 明确 patch 掉 `socket.socket.connect`，`real_paid_calls:0`。
6. 其余全部标注 `paid_calls:0` / `paid_model_calls:0` / `paid_api_calls:0` / `model_calls:0` / `network_calls:0` / `images_downloaded:0`。

### 安全与数据完整性（亮点与风险）
- **亮点**：路径防穿越/符号链接（`resolve_inside`/`_safe`/`path_in` 多处）、SSRF 防护（固定 HOSTS + `_NoRedirect`）、密钥不落盘/防回显（economic_data、free_jev_probe）、不可变快照与逐文件 sha256 绑定（几乎全部）、容器隔离（`--network=none --read-only --cap-drop=ALL`、只写声明输出、进程树终止）、执行租约防并发、日志/响应/行数/字节有界、保守成本会计（不虚构账单）、`human_visual_review_required`/`independent_review_required`/`scientific_*_verified:False` 的诚实标注。
- **风险/需留意**：
  - `dynamic_routing` 的模型名/角色硬编码 + acceptance actor 无鉴权（依赖调用方约定）；`choose()` 的角色隔离规则是策略固化，换模型需改代码。
  - `experiment_runner` 真实执行批准命令：argv 白名单只约束可执行文件，脚本内容由外部 plan 提供；安全性完全依赖 G3 冻结 hash + 容器隔离；`compute_budget_authority()`/`prior_estimated_cost()` 定义但主执行链未直接调用（疑似死代码/历史路径）。
  - `figure_gallery_semantic.provision` 会 pip install（供应链/环境变更面）；`verify_bytes` 用 **git blob SHA-1** 校验资产（虽另存 sha256 于 receipt，但 SHA-1 有已知碰撞弱点）。
  - `editable_figures._schema` 自造 JSON Schema 校验器，`pattern` 用 `re.search` 而非 fullmatch，校验强度有限；多处 `quote.count(...)==1` 用子串匹配（非行级精确），理论可构造歧义。
  - `figure_recipes.correlation` 实际调用 `frame.corr()` 计算相关矩阵，与 docstring "never infer statistics" 有轻微语义张力（属轻量计算、非模型拟合）。
  - 大量硬编码常量（模型名、阈值、路径、年份 2023–2026、双语词表、六篇论文 portfolio、融合权重 .40/.25/.35、CLIP 512 维/77 token）。

### 函数名与实际行为不符 / 易混淆
- **两处 `preflight_run`**：`experiment_runner`（运行前资源/依赖/cwd/输入 hash 检查）与 `empirical_workflow`（实证输入契约检查）同名不同职责；`approved_plan()` 调后者、`_execute_locked/run_one` 调前者。
- **多处 `validate_saved_report` 同名不同签名**：`economic_data(request_id)`、`empirical_design(paper_id)`、`empirical_reporting(paper_id)`、`figure_story(project, report_path: Path)`——跨模块阅读极易混淆。
- **多处 `lineage` / `validate_scientific_bindings` / `search` 同名**：`incremental_evidence.lineage` 与 `figure_provenance.lineage`、`experiment_evidence.validate_scientific_bindings` 与组外 `research_design` 同名、`figure_gallery.search` 与 `figure_gallery_semantic.search` 同名不同算法。
- 初读疑点：`editable_figures._story_alignment` 传 `Path` 给 `figure_story.validate_saved_report` —— 经核对签名一致，非缺陷（已在第 3 节更正）。

### 报告诚实性
- 每个文件 docstring / receipt / report 普遍自带 `scientific_completion_verified:False`、`scientific_validity_verified:False`、`causal_identification_verified:False`、`advisory_only:True`、`not_scientific_equivalence:True`、`novelty_granted:False`、`human_visual_review_required:True` 等——代码与 AGENTS.md "证据链、失败留痕、角色隔离、绝不自动投稿、不发明数据"高度一致，未见把软件验收/数值审计冒充科学结论的实现。






