# scripts-G01 源码精读报告

> 仓库：`D:/ad/lunwen`（Doctoral Research OS v2.3.0）
> 精读范围：`scripts/` 下按 Python `sorted(*.py)` 字母序，自 `__init__.py` 起至 `check_env.py` 止，含两端，共 **20 个文件 / 8518 行**（实测行数与题面一致）。全部用 `Read` 逐文件完整通读；`api_orchestrator.py`(2054) 分 3 段读完，其余单文件一次读完。
> 背景文档 `AGENTS.md`(107) / `README.md`(353) 已通读，仅作规则参照，**不计入精读范围**。
> 纪律：本次只读仓库，未修改/新建/删除 `D:/ad/lunwen` 下任何文件；唯一写入为本报告。

## 0. 文件清单（字母序，行数为实测）

| # | 文件 | 行数 | 角色一句话 |
|---|---|---|---|
| 1 | `__init__.py` | 2 | 包标记 |
| 2 | `academic_style.py` | 416 | G5 确定性学术风格审计 |
| 3 | `acceptance_scope.py` | 65 | **合成验收夹具**（伪造 G1/G2 人工范围） |
| 4 | `ai4science_evidence.py` | 711 | AI4Science 工具执行 + 哈希绑定 receipt |
| 5 | `ai_providers.py` | 1194 | 依赖无关的模型适配器 / **真实付费 API 出口** |
| 6 | `api_orchestrator.py` | 2054 | **API 周期总枢纽**：planner→writer→critic→remediation |
| 7 | `artifact_ownership.py` | 214 | 路径所有权清单（controller/executor 保护） |
| 8 | `automated_quality.py` | 192 | G3/G4 确定性质量记录刷新 |
| 9 | `automated_visual_review.py` | 345 | 哈希绑定 + 计费回执绑定的多模态视觉检查 |
| 10 | `automatic_data_discovery.py` | 296 | 自动派生查询 / 元数据 shortlist |
| 11 | `autopilot.py` | 271 | `start/resume/plan` 兼容入口 |
| 12 | `auxiliary_job.py` | 364 | 严格 manifest 的云辅助任务入口 |
| 13 | `billing_quotes.py` | 318 | CNY 计费合约 / 预留 / 结算引擎 |
| 14 | `bocha_jev_probe.py` | 152 | Bocha Jev 官网 API 传输探针 |
| 15 | `calibration_analysis.py` | 210 | 盲评校准的**描述性**汇总（认证能力缺失） |
| 16 | `catalog_diagnostic.py` | 131 | Gemini relay 目录只读诊断 |
| 17 | `ccfa_acceptance.py` | 62 | 17 个 CCFA 技能的安装/字节验收 |
| 18 | `ccfa_runtime.py` | 752 | 固定 commit 的 CCFA 技能族运行时 |
| 19 | `ccfa_science.py` | 649 | 5 类 CCFA 科学扩展的确定性报告构建器 |
| 20 | `check_env.py` | 120 | 本地环境/命令/包检查 |

---

## 1. 逐文件精读

### 1.1 `__init__.py`（2 行）
- **职责**：仅一行 docstring `"Deterministic helpers for Doctoral Research OS."`，把 `scripts/` 声明为包，使 `python -m scripts.xxx` 与 `from scripts import ...` 可用。
- **对外能力 / 输入输出 / 机制 / 依赖 / 边界**：无代码、无导入、无副作用。注意全仓库大量模块采用 `if __package__ in {None,""}: sys.path.insert(...)` 的"双模式导入"（既支持 `from scripts import x` 也支持 `cd scripts && python x.py`），本文件不参与该逻辑。

### 1.2 `academic_style.py`（416 行）
- **职责定位**：G5 投稿阶段"真实学术风格与可读性"的**确定性启发式审计**，文件头即声明 `"Audit authentic academic style without scoring or evading AI detectors"`（不评分、不规避 AI 检测器）。对应 AGENTS.md 规则 25、README.md "重新运行表达检查"。
- **对外能力**：
  - CLI：`audit | validate`，均需 `--project <slug>` `--paper Pxx`。`audit` 写报告并打印，退出码 `0/2`（pass/revise）；`validate` 校验已存报告，退出码 `0/2`。
  - 主要函数：`load_style_rules()`、`analyze_text()`、`run_proselint()`/`run_harper()`/`_run_linter()`、`build_audit()`、`write_audit()`、`validate_saved_audit()`、`report_path()`、`_project_path()`。
- **输入与输出**：
  - 输入：`config/academic-style-rules.json`（`schema_version=1.0`、`sources[{id,commit,...}]`、`rules[{id,category,confidence,pattern,message,guidance,source_ids}]`）、`config/proselint-academic.json`、稿件（经 `ref_verify_adapter.canonical_manuscript` 选规范稿件、`manuscript_language.extract_text` 抽文本）。
  - 输出：`papers/Pxx/style/academic-style-audit.json`（`schema_version=1.3`），含 `status(pass/revise)`、`analysis.formulaic_pattern_findings`（行级：line/column/matched_text/excerpt/message/guidance/source_ids）、`duplicate_sentences`、`reviewed_rule_sources`、`external_linters`、`manuscript.source_tree_sha256`、`errors/warnings`。
- **关键实现机制**：
  - 规则加载强校验：必填字段集合、confidence∈{high,moderate}、source_ids 必须引用已声明 source、正则可编译。
  - `analyze_text()`：正则匹配生成行级 findings，**每条规则最多取 20 个匹配**；`category=="research_integrity"` 的命中升级为 `error` 并令 `status=revise`，其余仅 `review`/warnings；另做归一化重复句检测（≥10 词句子）。
  - 两个**可选本地** linter：proselint（BSD-3-Clause，仓库配置）+ harper-cli（Apache-2.0）。经 `subprocess.run` 调本地 CLI，tempfile 写 `manuscript.txt`，30s 超时，诊断上限 100，结果仅 `advisory`→warnings，不阻断。字段固定 `detector:False, local_only:True, required:False`。
  - **哈希绑定**：`manuscript.source_tree_sha256`（来自 `venue_compliance.manuscript_tree_sha256`）；`validate_saved_audit()` 重算当前稿件树哈希，不一致即 "stale for the manuscript source tree"。
  - `validate_saved_audit()` 还校验：schema、finding 计数一致性、`reviewed_rule_sources` 的 `{id:commit}` 与当前规则锁一致、两个 linter 的 source/license 固定值、diagnostic 计数一致性、`status=="pass"` 且无 errors。
- **依赖的其它 scripts 模块/外部服务**：`research_artifacts`(schema_errors/write/utc_now)、`ref_verify_adapter`(canonical_manuscript)、`manuscript_language`(extract_text)、`venue_compliance`(manuscript_tree_sha256)；外部可执行 proselint/harper-cli。均有 `ImportError` fallback 支持从 `scripts/` 直接运行。
- **边界与限制**：明确 `"Heuristic writing-quality audit only. It does not estimate human authorship, predict an AI detector, justify nondisclosure, or guarantee journal acceptance."`；`SLUG_RE`/`PAPER_RE` 防路径穿越。**占位**：`analysis["editorial_methods"] = {"status":"retired","mechanical_review_performed":False,"semantic_review_status":"unknown"}` 为硬编码；`detector_score_used=False`、`detector_evasion_prohibited=True`、`disclosure_must_be_preserved=False`、`human_review_required=False` 均为固定立场字段。

### 1.3 `acceptance_scope.py`（65 行）
- **职责定位**：**"Explicitly synthetic scope setup for temporary cloud acceptance fixtures. Not a production migration or approval API. Real project directories are refused."** —— 纯测试夹具，为临时云验收构造合成的科学范围与 G1/G2 批准记录。
- **对外能力**：唯一函数 `prepare_scope(project, state)`（无 CLI、无 main）。
- **输入与输出**：输入项目路径 `project` 与可变 `state` 字典；写出 `program/core-thesis.json`、`program/extension-thesis.json`、`papers/Pxx/paper-contract.json`、`program/paper-map.json`、`state/run.json`；并调用 `scientific_scope.seal_approval` 生成 G1/G2 封存批准。硬编码 `doctoral_question="Synthetic fixture doctoral question?"`、`target_jcr_quartile="Q1"`、actor `"Synthetic fixture human"`、`unique_claim_ids=["SYNTHETIC_Pxx"]`。
- **关键实现机制**：
  - 前置保护：`project.resolve().is_relative_to(ROOT/"projects")` 为真则抛 `ValueError("synthetic acceptance scopes cannot approve a real repository project")`。
  - 若目标已有 `state/scientific-scope/G2.json`，改为 `scientific_scope.validate(project,"G3")` 校验，失败则要求重建夹具。
  - 用 `unittest.mock.patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR":"1"})` 临时设置环境变量，循环 gate `("G1","G2")` 构造 `approval`（含 `artifact_sha256 = sha(...)`）写入 `state["approvals"]/["approved_gates"]` 并 `seal_approval`。
- **依赖**：`scripts.scientific_scope`、`scripts.research_artifacts`(read/write/sha)。
- **边界与风险（重点标注）**：这是**伪造 G1/G2 人工决定的可执行路径**——`DR_OS_CLOUD_EXECUTOR=1` 是解锁 `seal_approval` 的开关，actor 是写死的 `"Synthetic fixture human"`。保护仅依赖"项目在仓库 `projects/` 目录内"这一路径判断；若真实项目被放到其它路径，检查即失效。虽为测试夹具且自我声明非生产 API，但它演示了系统里"人工批准记录"可被环境变量+函数生成，属于**数据完整性/诚信敏感点**。同时 `ccfa_runtime.cloud()`、`ccfa_science.execute()` 也接受 `DR_OS_CLOUD_EXECUTOR=1` 作为云环境等价物。

### 1.4 `ai4science_evidence.py`（711 行）
- **职责定位**：执行并**哈希绑定**"经审查的 AI4Science 工具"与"原生来源问答"。文件头明确："deliberately does not make an AI-generated answer authoritative"、"standalone PaperQA2 agent is never launched"、"Results remain advisory"。对应 AGENTS.md 规则 50–61（AI4Science / PaperQA2 / ToolUniverse 边界）。
- **对外能力**：CLI 子命令 `record | paperqa | tooluniverse | validate`；核心函数 `run_process()`、`_finish_execution()`、`execute_paperqa()`、`execute_tooluniverse()`、`public_tooluniverse_request()`、`record()`、`read_ledger()`、`validate()`、`file_record()`、`directory_records()`、`package_version()`、`safe_environment()`。
- **输入与输出**：
  - 输入：项目内语料目录（`--corpus`）、请求文件（`--request`）、`--question/--actor/--purpose`、输出文件路径（`--output`，record 用）。
  - 输出：`evidence/ai4science/<receipt_id>/{stdout.log,stderr.log,result.json}` 与追加式台账 `evidence/ai4science-ledger.jsonl`；receipt `schema_version` 1.0(record) / 1.1(执行类)。
- **关键实现机制**：
  - **输入完整性与哈希绑定**：`file_record()` 记 `path/sha256/bytes`；`directory_records()` 遍历语料，拒绝 symlink 与 `.env*` 凭据文件、空目录；`_unchanged_inputs()` 运行后重算哈希，任一变化即 `status=failed`（"AI4Science input files changed during execution"）。
  - **受控子进程**：`run_process()` 用 `subprocess.Popen(shell=False, stdin=DEVNULL, start_new_session=非Windows)`，环境仅保留 `BASE_ENV_NAMES` 白名单（PATH/LANG/TZ/代理/CA 等）+ `HOME`/`XDG_CACHE_HOME` 指向 `project/.cache/ai4science`；**显式不传任何 provider key**（`SECRET_ENV_NAMES` 仅用于历史 receipt 校验）；输出 NamedTemporaryFile 捕获，8 MiB 截断上限，保留 `stdout_full_sha256`/`stderr_full_sha256`，超时 SIGKILL 进程组，timeout 上限 24h。
  - **失败留痕**：`_finish_execution()` 把 stdout/stderr 落盘、成功时解析 stdout JSON 写 `result.json`、生成 receipt 追加台账；截断/输入变更/非法 JSON 一律 `failed` 且 **先保留 receipt 再抛错**。`cost_accounting` 对 tooluniverse 记 `adapter_attempts=1` 与 `http_attempts`（从 worker stdout 取，取不到为 `None`，注释明确"保留不确定性，不宣称没有 HTTP 请求"）。
  - **版本锁**：`PACKAGES` 映射 4 类工具；`package_version("native-source-qa")` 返回 `paper_qa.__file__` 的 SHA-256；ToolUniverse 必须等于 `tooluniverse_worker.SDK_VERSION`。
  - **中央运行时约束**：`execute_paperqa()` 是兼容入口，强制 `settings=="native"`、无 `executable`、`timeout==1800`，否则拒绝并提示走 `literaturectl request` / `literature_paperqa`；还要求 `DR_OS_ROUTING_PROFILE=="production"` 与 `GITHUB_ACTIONS=="true"`；先查 `model_spend` 累计预算（`authorized_ceiling_cny - spent_cny - reserved <= 0` 拒绝）；返回 `not_paperqa2_sdk=True, legacy_pqa_agent_called=False`。
  - **receipt 校验**：`validate()` 检查 receipt_id 格式/唯一、tool/package、`advisory_only is True`、`human_verification_required is True`、status、成功后必须有 output、`input_integrity.passed`、`secret_environment_names` ⊆ `SECRET_ENV_NAMES` 且 ⊆ `environment_names`、成功状态一致性、stdout/stderr 全量哈希、所有文件记录当前哈希/bytes 未 stale。
- **依赖**：`research_artifacts`(sha/regular_file/utc_now)、`model_spend`、`paper_qa`、`tooluniverse_worker`；子进程 `scripts/tooluniverse_worker.py`；`literaturectl`/`literature_paperqa` 仅文档指引不 import。
- **边界与风险**：`record` 子命令**不经执行即可写入一条 hash 绑定的 receipt**（只校验路径/哈希/schema，不验证 output 真由该工具产生），存在人工伪造 advisory 证据的空间；`execute_tooluniverse` 经 worker 访问**公开数据 API（真实网络）**；`execute_paperqa` 间接走中央模型运行时（**真实付费**）。所有 receipt 恒 `advisory_only=True, human_verification_required=True`。硬编码：8 MiB、24h、`SECRET_ENV_NAMES` 集合、`PACKAGES`、native Q&A 的 1800s/生产 profile。

### 1.5 `ai_providers.py`（1194 行）★关键文件
- **职责定位**：**"Dependency-free model adapters"**——只用标准库（`urllib`/`http.client`）的模型适配层，返回 `ModelResult`（文本 + 可审计请求元数据）；文件头声明 "never execute model-produced commands"。**全系统真实付费/网络 API 的底层出口**。
- **对外能力**：统一入口 `call(provider, prompt, **kwargs)`；官方直连 `call_openai`/`call_anthropic`；UUAPI 兼容 `call_uuapi_openai`/`call_uuapi_anthropic`/`uuapi_usage`；生产 `call_production`/`production_endpoint`/`production_supported_efforts`；配置 `configuration()`；家族 `provider_family()`；附件 `validate_attachments()`；完成态 `require_complete()`/`completion_status()`。
- **输入与输出**：`ModelResult`（dataclass）字段：provider/model/text/usage/request_id/reported_model/protocol/endpoint/gateway/cache_hit/cache_key/completion_status/requested_effort/attachment_sha256/route_id/dynamic_candidate_id/routing_policy_sha256/response_metadata。`configuration()` 返回脱敏的配置描述（含 `billing_identity{plan,group,mode}`、`allowed_models`、`allowed_reasoning_efforts`、`strict_model_id`）。
- **关键实现机制**：
  - `PROVIDERS`(17) 与 `PRODUCTION_PROVIDERS`(12)：**硬编码** 12 条生产路由，每条含 `family/root/path/key_setting/model/protocol/models`；域名固定 `cheapai.info`、`codekey.ai`；模型 ID 如 `gpt-6.1-sol`、`gpt-6-astra`、`claude-sonnet-5-5`、`deepseek-v4.1-flash`、`gemini-4-argon`、`kimi-k3.1-pro`（均为 2026 未来型号）。注释坦承 "Exact transport routes, **not assertions about gateway authenticity or quality**"；`UUAPI` 标注 "deprecated compatibility adapter for historical run receipts"。
  - **单次 reservation 单次 POST**：`_request()` 与 `_production_request()` 注释明确"生成 POST 在响应丢失时可能已计费、无幂等契约，因此一次预留只允许一次传输尝试；任何歧义失败保留 reservation 供对账，绝不自动重试、无协议回退、无付费预热"。错误统一带 "reconcile billing"。
  - **模型身份核查**（AGENTS 规则 16/17）：`_strict_model_check()`（UUAPI，默认 `UUAPI_STRICT_MODEL_ID=true`）、`_production_identity()` 要求 reported == requested，否则 "quarantine route and reconcile billing"；注释承认 "An exact echo is a traceability condition, **not proof of genuine weights**"。`provider_family()` 用于独立性判断（不同家族才算独立）。
  - **失败留痕 + 脱敏**：`_response_evidence()` 从 `cloud_retry.redact` 导入脱敏，敏感键集合（authorization/apikey/token/secret/email/thinking/reasoning/signature…），Bearer key 字符串替换 `[REDACTED]`、thinking/reasoning 内容打码、非有限 float→`[NONFINITE]`；产出 `canonical_json_sha256`、`raw_http_body_sha256`、`stored_body_is_redacted:True`、`not_scientific_evidence:True`、`diagnostics`（model/usage/token 计数/content_block_types/finish_reasons）。**原始响应体不落盘**（`original_response_body_retained=False, metadata_only=True`）。
  - **传输安全**：`_validated_https_root()` 严格 HTTPS（拒绝空白/控制字符/凭据/query/fragment/full endpoint）；`_uuapi_setting_names()` 密钥与 base URL 原子对（"Never send a shared key to a new host"）；`_safe_endpoint_for_audit()` 持久化前剥凭据与 query；`_NoGenerationRedirect` 拒绝生成 POST 重定向（防凭据转发/重放计费）；`_production_request()` 强制 `GITHUB_ACTIONS=="true"`、netloc ∈ {cheapai.info, codekey.ai}、无凭据/query/fragment，并调 `relay_guard.authorize_transport(url, headers, payload)`；响应体 ≤4 MiB、记录 `raw_http_body_sha256`、无重定向。
  - **SSE 严格解析**：`_responses_sse()` 只接受权威事件（response.created/in_progress/completed/failed/incomplete），校验 response 对象形状、model/id 身份跨事件一致、序列、终止状态，拒绝 `[DONE]` 作为终止、拒绝终端后事件、用完整 `response.completed` 而非拼装 delta；流式仅允许 `codekey.ai/v1/responses` + `gpt-6-astra` + `g1_response_streaming_active()` 的 Astra G1 验证样本。
  - **usage 归一化与计费校验**：`_production_usage()` 按 family/protocol（openai_responses / chat_completions / deepseek / google usageMetadata）严格校验 token 数合法性、cache hit/miss 与 total 一致、reasoning 不重复计数、thoughts 计入 output；缺失或冲突即 "reconcile billing"。
  - **附件校验**：`_validated_attachments()` 最多 5 个、MIME 白名单（pdf/text/png/jpeg/webp）、base64 ≤14 MiB、解码后总 ≤10 MiB、SHA-256 与声明一致、文件魔数校验、UTF-8 文本、filename 无路径；`_google_text()` 只取**非 thought** parts 作正文（"Internal thought parts never become persistent scientific prose"）。
  - `call_production()` 按 family 构造 payload：openai_responses（reasoning.effort/store=False/tools=[]/service_tier）、anthropic（thinking adaptive + output_config.effort）、chat（reasoning_effort，deepseek thinking enabled，moonshot 用 max_completion_tokens）、google（thinkingConfig.thinkingLevel + systemInstruction）；校验 max_output_tokens 1..32768、timeout 1..600、effort 白名单、key 配置。
- **依赖**：`cloud_retry`(redact)、`model_routing`(g1_response_streaming_active)、`relay_guard`(authorize_transport) —— 均为函数内延迟 import；其余纯标准库。
- **边界与限制**：`production_supported_efforts()` 注释承认 "Optional groups are transport candidates only. Catalog access, a known model ID and this effort allowlist **cannot authorize spending or establish that a relay actually honors the requested effort**"；`require_complete()` 在 `DR_OS_REQUIRE_MODEL_AUTH=1` 时更严格；非生产路由传 `reasoning_effort/attachments` 会被 `call()` 拒绝。**风险**：全部模型 ID/网关域名/密钥变量名硬编码且为未来型号，代码只能验证"网关回显的 ID 是否等于请求"，无法验证网关真实性与实际权重。

### 1.6 `api_orchestrator.py`（2054 行）★最关键文件
- **职责定位**：API-first 总枢纽。docstring："Claude is a read-only planner and independent critic. A non-Anthropic writer (normally Codex/GPT) creates every persistent project artifact. The control plane validates paths, tracks writer provenance, and blocks Claude-authored files from final packaging. **No model can approve or advance a gate.**" 对应 AGENTS 规则 13/17/18/22、README 推荐架构。
- **对外能力**：
  - CLI：`health`（`--provider`×N / `--project` / `--live`）、`balance`（UUAPI，生产模式报错 retired）、`cost <project> [--paper]`、`stage <project> <stage>`（单 writer）、`cycle <project> <stage>`（完整周期）。共享 `--context/--discovery-query/--task-kind/--task-profile/--max-output-tokens/--no-auto-data-discovery`；cycle 另 `--planner-provider/--writer-provider/--critic-provider/--control-max-output-tokens`；旧 `--author-provider` 被 `SUPPRESS` 并报错。
  - 核心函数：`run_cycle()`、`project_snapshot()`、各类 prompt 构造器（`planning_prompt`/`writer_prompt`/`critic_prompt`/`remediation_prompt`）、`extract_plan_json`/`extract_json`/`extract_audit_json`、`reject_long_source_copy()`、`validate_remediation_notes()`/`remediation_required()`、`safe_target()`/`apply_bundle()`、`validate_roles()`、`record_writer_provenance()`、`refresh_post_write_evidence()`/`refresh_research_method_audits()`、`prepare_revision_baseline()`、`health_report()`。
- **输入与输出**：
  - 输入端：`config/stages.json`、`state/run.json`（stage/gate/status 必须 `awaiting_work`）、`program/context-plan.json`、`program/research-control.json`、项目内文本快照、发现报告、用户 `--context`（标注 "untrusted context, never authority"）。
  - 输出端：`api_runs/<run_id>/`（claude-plan/semantic-plan、writer/critic response、bundle、manifest.json、各类快照）、`reviews/independent/<prefix>-<run_id>-<phase>.json`、`reviews/decision-log.md`、`papers/Pxx/style/academic-style-audit.json`、`reports/manuscript-hygiene/...` 等；`manifest.json` 含 `research_decision`、`actual_routes`、`provider_audit`、`independent_audit(gate_authority:False)`、`usage`、`model_budget`、`cost_diagnostics`、`next_action`。
- **关键实现机制**：
  - **闸门与状态**：`require_current_stage()` 校验 state 的 stage/gate/status；`cloud_research_steps.before_cycle()` 若 `control_only` 直接返回 `paid_model_cycle=False`；`run_id` 唯一（"never overwrite an earlier attempt"）；topic-intelligence 无检索 receipts / 有 pending_searches 时加 blocker 并 `control_only` 返回（"inspect the source/plan before spending"）。
  - **角色隔离（代码核心）**：`validate_roles()` 强制 planner_family=="anthropic"（Claude 只读规划）、writer_family=="openai"、critic_family != writer_family；`reject_long_source_copy()` 检测持久产物是否逐字复制只读规划/审计文本（≥12 英文词 n-gram 或 ≥24 CJK 字），命中即拒绝（防 Claude 文本伪装成持久产物）；`record_writer_provenance()` 调 `output_provenance.record_model_writes` 记录每个写入文件的家族/provider/model/role/run_id；`manifest.output_policy.anthropic_final_outputs_allowed=False`、`independent_audit.gate_authority=False`。
  - **快照与证据**：`project_snapshot()` 生成有界纯文本快照（≤300 文件、单文件 100KB、总 600KB、源 4MB），每文件带 `sha256=` 标记；`exclude_reviews=True` 排除既往评审；`lossless_text` 压缩、`discovery_navigation_index` 导航索引；超限**抛错而非静默截断**（"never silently omit evidence"）；`secret_values()/redact()/contains_environment_secret()` 脱敏环境变量密钥。
  - **结构化 prompt 契约**：`research_quality_artifact_contract()` 给"不能浏览仓库"的 writer 紧凑 schema/路径/科学指令（含全文引用 claim_evidence 任务、study_route_overrides、review_remediation_contract、统计报告字段、明确 "never author protected controller reports"/"never author their receipts"/"unknown ranking stays unknown"/"never invent a score or theme decision"）。writer 返回 `{schema_version,stage,artifacts[{path,content}],notes}`，critic 返回 `AUDIT_FIELDS`（verdict/fatal/major/minor/missing_evidence/remediation_steps/uncertainty，可选 novelty_assessment）。所有 JSON 经严格字段集合/类型/长度校验。
  - **产物写入保护**：`safe_target()` 拒绝绝对路径/反斜杠/控制字符/`..`、FORBIDDEN_PARTS(.git/.env/api_runs/credentials/private/raw/secrets)、FORBIDDEN_NAMES(run.json/state.json)、符号链接、`artifact_ownership.executor_owned` / `controller_owned`（state/、academic-style-audit.json 等）。`apply_bundle()`：≤80 artifacts、单文件 ≤1MB、拒绝含环境变量密钥的内容、拒绝写 plan 声明的 `expected_outputs`、tempfile+`os.replace` 原子写、失败回滚、**精确 no-op 不重写**（"must not churn files or overwrite their authorship ancestry"）。
  - **修复触发**：`remediation_required()` 只由真实 findings 触发（"verdict labels and style coverage do not"）；`validate_remediation_notes()` 要求 `fixed:/rejected:/unresolved:` 前缀与 novelty claim_id 逐条 disposition；`review_cycle`/`submission_cycle`（`research_cycle` 模块）驱动 critic→repair→final critic，`use_cache=False`（"scientific_reviews_always_fresh"）。
  - **写后确定性步骤**：`refresh_post_write_evidence()` 调 `manuscript_hygiene`、`cloud_research_steps.after_write`、`revision_integrity`、`automated_visual_review.run`（final+production）、`reviewer_rounds`/`publication_disclosure`/`statistical_watermarks.refresh`、`research_increments.refresh`、`academic_style.write_audit`，全部 `paid_calls:0`；`refresh_research_method_audits()` 产出方法审计报告并登记 deterministic provenance；`prepare_revision_baseline()` 在 G5 修订前快照稿件源（含 `manuscript_digest` 源树哈希）。
  - **G5 三家族互盲**：`requires_submission()` 分支走 `submission_cycle` + `model_routing.PANEL_MODELS` preflight，manifest 提示 "three mutually blind source views; recorded opinions grant no scientific clearance"。
  - **预算/路由**：`model_routing.cycle_routes(stage, task_kind)` + `dynamic_routing.validate_profile`，task_kind 强制 `science_risk="critical"`；付费前 `route_preflight` 检查所有角色配置；`cost_audit.refresh()`、`model_runtime.budget_status()`、`after_reviews()`、`researchctl.gate_errors("G5")` 收尾。
- **依赖**：本组 `ai_providers`、`academic_style`、`automated_visual_review`、`automatic_data_discovery`、`artifact_ownership`、`autopilot`(反向)、`auxiliary_job`(反向)；组外极多：`model_runtime`/`model_routing`/`dynamic_routing`/`output_provenance`/`research_methods`/`research_phase`/`research_artifacts`/`context_efficiency`/`evidence_context`/`paper_execution`/`scientific_scope`/`cloud_research_steps`/`cloud_checkpoint`/`manuscript_hygiene`/`revision_integrity`/`reviewer_rounds`/`publication_disclosure`/`statistical_watermarks`/`research_increments`/`empirical_workflow`/`research_candidates`/`pre_submission_review`/`manuscript_audit`/`figure_layout`/`citation_audit`/`ref_verify_adapter`/`supplemental_experiments`/`review_panel`/`review_receipts`/`research_cycle`/`research_notebook`/`literature_model_screening`/`cost_audit`/`researchctl`/`data_discovery`/`figure_reference_context`/`research_case`/`literature_source_tasks` 等。外部服务经 `model_runtime`→`ai_providers`（付费 LLM）、Tavily（可选检索）、GitHub Actions。
- **边界与限制**：模型输出全部经 Python 控制平面落地；`--context` 标注 untrusted；G1/G2 由真实人工决定（`next_action` 明确）；从未自动投稿。**占位/缺口**：`editorial_feedback()` 固定 `editorial_methods={"status":"retired","mechanical_review_performed":False,"semantic_review_status":"unknown"}`；`hygiene_feedback()` 固定 `statistical_watermarks:"not_assessed"`、`watermark_absence_verified:False`；多个 prompt 明说 "Retired H/AD/CFH scorecards supply no completed review"。**风险**：`validate_roles()` 存在 `g1_sample` 例外——当 `model_routing.g1_transport_validation_roster()=="astra-argon"` 且三 provider 恰为 `("codekey-codex-pro","codekey-codex-pro","codekey-gemini")` 时，允许 planner 为 openai 家族、planner 与 writer 同 provider，临时弱化"planner 必须 Claude / 三家族隔离"（虽限定为传输验证样本）。`redact()` 仅覆盖环境变量里匹配 `API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|WATERMARK_KEY` 且长度≥8 的值。

### 1.7 `artifact_ownership.py`（214 行）
- **职责定位**：控制平面对"已执行事实、计划声明输出"的**路径所有权清单**；被 `api_orchestrator.safe_target()` 调用以阻止 writer 写受保护文件，也被 CLI 快照/恢复复用。纯静态字符串匹配，无哈希/密码学。
- **对外能力**：`controller_owned(relative)`、`executor_owned(root, relative, outputs=None)`、`declared_outputs(root)`、`paper_observation_path(relative)`、`control_roots(root)`、`control_files(root)`。
- **输入与输出**：输入项目相对路径与 `root`；输出 bool 或路径集合/清单。`declared_outputs()` 汇集 `experiments/plan.json` / `experiments/papers/Pxx/plan.json` 的 `runs[].expected_outputs`、`registry.jsonl` 的 `outputs`，锁定态还纳入 plan/budget.json、inputs、preregistration 的 files（均大小写折叠）。
- **关键实现机制**：`EXECUTOR_ROOTS`/`EXECUTOR_FILES`/`CONTROL_ROOTS`/`CONTROL_FILES`/`CONTROL_PATTERNS` 为大量硬编码路径（experiments/archive、results、data/raw、reports/*、state、reviews/codex、reviews/independent、各 ledger、decision-log.md、ai4science-ledger.jsonl…）；`_controlled_paper_record()` 对嵌套 study 的 paper 记录应用作者边界；`executor_owned()` 处理 `paper_execution` 别名/其它 paper 路径、G0 批准后 `intake/constraints.json`（"approved owner's constraints can change only through the authenticated operating-amendment controller"）、`experiments/supplemental/` 子范围递归、editable 图件后缀、figure/source-data、citation-audit/manuscript-audit/empirical-design 等。
- **依赖**：`scripts.paper_execution`(enabled/selected/ALIASES/refreshable_preregistration)。
- **边界与限制**：`declared_outputs()` 对草案异常静默放过（"A draft plan can be repaired; it grants no execution authority"），对无效 registry 抛错要求控制平面检查；`paper_observation_path()` 标记 C 类记录 "excluded from scientific decision fingerprints"。全文件硬编码路径极多，属"白名单式"保护，新增路径需同步维护。

### 1.8 `automated_quality.py`（192 行）
- **职责定位**：在原生阶段产出"明确自动化、证据绑定"的质量记录；文件头声明 "performs no acquisition, model call, approval, or experiment. It never substitutes a machine record for permission to use restricted data"。
- **对外能力**：CLI `--project`；`checked_run(project, stage)`、`run(project)`、内部 `ensure()`/`_store()`/`_target()`。
- **输入与输出**：读 `state/run.json`；输出 `data/quality/<dataset>-confirmation.json`、`papers/Pxx/preregistration.json`、`papers/Pxx/reproduction-confirmation.json` 或 study-validation-confirmation，以及归档 `state/automated-quality-history/<sha256>.json`；结果 dict 含 `created/refreshed/existing/blockers/paid_calls:0`。
- **关键实现机制**：`checked_run()` 仅 G3/G4 开放阶段、校验 state stage/gate/status 且经 `scientific_scope.validate`；`ensure()` 对每条已存记录校验 `output_provenance.current_origin` 必须为 `tracked` + `provider="automated-quality-control"` + `model="scripts/automated_quality.py"`，`confirmation_kind=="automated"` 的记录必须有该 provenance；刷新时若已冻结/执行（registry.jsonl 非空、approved_gates、plan/budget 哈希与 approvals 中 `experiment_plan_sha256`/`experiment_budget_sha256` 比对）则 blocker；旧记录按 sha256 归档，"unknown origins cannot be replaced"。G3 调 `paper_execution.prepare_datasets`、`research_quality.create_data_quality_confirmation`、`validate_g3_quality(require_preregistration=False)`、`create_preregistration`；G4 调 `validate_g4_quality(require_confirmation=False)`，exploratory 直接返回，非 empirical 走 `study_routes.create_confirmation`。所有 `_store` 登记 `family="other"` provenance。
- **依赖**：`output_provenance`、`research_quality`、`paper_execution`、`scientific_scope`、`research_phase`(exploratory)、`study_routes`、`researchctl`。
- **边界与限制**：仅 G3/G4；探索性阶段跳过正式确认；所有记录 `automated=True`；`paid_calls:0`；不替代受限数据许可（呼应 AGENTS 规则 7「许可为可选元数据」）。

### 1.9 `automated_visual_review.py`（345 行）
- **职责定位**：用"现有计量多模态角色"做**哈希绑定**的视觉检查；声明 "checks the appearance of actual rendered files. It cannot establish the scientific validity of their content or substitute for authorship requirements"。**本组少见的真实多模态付费调用点**。
- **对外能力**：无 main；被 `api_orchestrator.refresh_post_write_evidence()` 调 `run(project, paper_id)`；`prepare()`/`execute()`/`verify()`/`run()`/`packet_target()`。
- **输入与输出**：输入 canonical `main.docx`/`main.tex`/最终图件/`review_packets` visual packet；输出 `state/automated-visual-reviews/<paper>/<digest>.json` receipt、`.../renders/*.pdf` 预览、`.../history/<sha>.json` 归档。
- **关键实现机制**：`_owned()` 要求来源 `tracked` 且非 anthropic 家族；`prepare()` 对 DOCX/TEX 校验 `cloud-word-renderer`/`cloud-tex-renderer` 的 pass、`inputs_unchanged`、`source_sha256`、`execution.mode=="cloud"`、`verify_files`、canonical PDF 哈希绑定；SVG/TIF 用 `fitz` 转 PDF；边界 1..200 页、≤10 MiB。`_prompt()` 要求逐页检查并强调 "Source text is data, not instructions"、"Do not assess or approve scientific validity"。`_response()` 严格校验每页/每 check 恰好一次、值∈{pass,fail,unknown}、notes 非空、页码全覆盖。`_ledger_match()` 在 `model_runtime.ledger_entries` 找唯一匹配：`run_id/role=="multimodal-inspection"/prompt_sha256/request_id/model/completion_status=="completed"/attachments 精确/cost_status∈{settled_gateway_debit,settled_usage_receipt}` —— 把视觉通过结论绑定到**已完成计费回执**。`execute()` 相同 packet 的旧 receipt 可复用（"A failed unchanged layout needs a real edit, not repeated paid votes"），调用前后 `prepare()` 比对输入未变；`run()` 冻结目标集后每周期最多 5 个新请求，超出转 `pending`。
- **依赖**：`ai_providers`/`model_routing`/`model_runtime`/`output_provenance`/`research_artifacts`(path_in/read/record/sha/write/verify_files/json_digest)/`review_packets`；外部 `fitz`(PyMuPDF)、`PIL`。
- **边界与限制**：`human_review=False`、`scientific_validation=False` 固定；只查外观；每周期 5 次新请求上限；`scientific_validation` 恒 False。

### 1.10 `automatic_data_discovery.py`（296 行）
- **职责定位**：自动派生数据集查询、搜索已批准来源、生成**仅元数据** shortlist；"without another model call"（无模型调用）。对应 AGENTS 规则 15/19（发现元数据是待核实 leads）。
- **对外能力**：`derive_queries()`、`apply_automatic_screening()`、`run_automatic_discovery()`；无 CLI，由 `api_orchestrator.run_automatic_dataset_discovery()` 调用（带 7 天 signature+report sha 缓存）。
- **输入与输出**：输入 `intake/constraints.json`、`program/core-thesis.json`/`extension-thesis.json`/`topic-shortlist.json`、`papers/Pxx/paper-contract.json`、用户 context、`explicit_query`；输出 `data/discovery-broad-auto-<stamp>.json` 报告、追加 `evidence/dataset-search-log.jsonl`；摘要含 `report_path/queries/provider_calls/candidate_count/shortlist_count/human_review_required/scientific_review_required`。
- **关键实现机制**：`_goal_scope()` 用正则剔除"发表/撰写/产出/投稿/完成…论文/博士/期刊"及英文等价交付/排名指令句（"Delivery/ranking instructions are not a scientific search scope"）——把用户 context 当非权威范围过滤；`derive_queries()` 去停用词、≤10 词、自动补 `dataset` 后缀及 `public dataset`/`benchmark dataset` 变体，最多 8–12 条；`apply_automatic_screening()` 阈值 `minimum_metadata_score=25`、`maximum_shortlist=80`，**保留全部 retrieved candidates**，每条打 `automatic_screening`（含 `scientific_fitness_assessed:False`、`license_metadata_present_unverified`）；summary 的 `not_automatically_decided` 列出许可/研究用途、隐私伦理、科学适用性、样本/偏差、泄漏、最终采用；固定 `human_review_required:False, scientific_review_required:True`。`run_automatic_discovery()` 调 `data_discovery.discover_many`（`network_safety.fetch_json`，**真实公开 HTTP**），0 个成功来源则抛错 "the model cycle was stopped before paid calls"（在付费模型周期前阻断），并 `record()` provenance。
- **依赖**：`data_discovery`、`network_safety`(fetch_json)、`paper_execution`(papers)、`research_artifacts`(record)。
- **边界与限制**：只做元数据 shortlist，不评估科学适用性、不验证许可（`unverified`）、不作最终采用决定；`human_review_required=False` 但 `scientific_review_required=True`。硬编码阈值 25/80、7 天缓存、`MAX_QUERY_LENGTH=240`。

### 1.11 `autopilot.py`（271 行）
- **职责定位**：canonical API 周期的**兼容命令**（`start/resume/plan`）；docstring "The local Claude Code/Codex subprocess backend is retired"。对应 AGENTS 规则 13。
- **对外能力**：CLI `start|resume|plan --project [--context] [--planner/writer/critic-provider] [--max-output-tokens] [--control-max-output-tokens]`，start 另 `--paper-count/--venue`；`show_plan()`、`run_stage()`。
- **输入与输出**：输出 JSON（预览或 manifest 派生结果）；`show_plan()` 零请求/零花费/零状态变更。
- **关键实现机制**：`show_plan()` 按状态返回：gate None→`submission_ready`；G1/G2 `awaiting_approval`→`awaiting_human_topic_approval`；`approved/awaiting_approval`→`control_pending`（`planned_model_calls:None` "successor calls are unknown here"）；否则列出 steps（read-only semantic plan + non-Anthropic writer；G5 提交阶段加 blind domain/editorial/statistics 三视图 `three_blind_submission_views`；有 critic 加 `fresh source-bound independent critique` + conditional repair/re-review，`scientific_review`；否则 `administrative_intake`），`repair_trigger:"actual actionable findings"`，`paid_model_calls:0`。`run_stage()` 先 `scientific_scope.validate`，approved/非 G1G2 awaiting_approval 先 `cloud_continuation.transition_ready_gate`；G1/G2 awaiting_approval 直接返回不跑模型；否则在 `model_runtime.authorized_calls(...)` 内调 `api_orchestrator.run_cycle(...)`，按 manifest 处理 `controlled_step`/`submission_preparation`/`protocol_retired_to_G3`/`needs_work`，通过后 `transition_ready_gate(reason="automatic_gate_ready")`，若非 G1/G2 仍 awaiting_approval 则抛错 "did not record its automatic decision"。
- **依赖**：`ai_providers`、`api_orchestrator`、`model_runtime`、`researchctl`、`cloud_continuation`、`research_cycle`、`research_phase`、`scientific_scope`、`supplemental_experiments`。
- **边界与限制**：本地进程选项（`--claude-mode/--timeout/--max-output-bytes/--claude-max-budget-usd`）被 `argparse.SUPPRESS` 隐藏，传入即报 "Local process options are retired"；不自动推进 G1/G2；真实付费经 `api_orchestrator.run_cycle` 间接发生（在授权预算上下文内）。

### 1.12 `auxiliary_job.py`（364 行）
- **职责定位**：云 runner 上生产辅助任务的**严格 manifest 入口**；"No HTTP adapter or spending grant lives here. Model selection and execution go through task_router and the central runtime; **outputs remain internal candidates**"。
- **对外能力**：CLI `--project --manifest --output [--execute]`；`load()`、`run()`、`run_g1_transport_validation()`、`_check_inputs()`。
- **输入与输出**：manifest 字段集合 `FIELDS`（schema_version/kind/prompt_file/source_contract_file/attachments/max_output_tokens/task_profile/calibration_seat/source_task_file/validation_roster/response_streaming），必填 `REQUIRED`；输出 `evidence/auxiliary/*.json` 诊断（不可覆盖）。
- **关键实现机制**：严格路径 `_relative`/`_path`（拒绝绝对/Windows 路径、`..`、以点开头、私有目录名 state/api_runs/private/raw/secrets/credentials/keys/auth/tokens、symlink 含父链、escaping），字节上限 2MB/48KB/10MiB；`load()` 要求 `DR_OS_ROUTING_PROFILE=="production"` 且 `model_routing.production_enabled()` 并 `load_policy()` 复核实际策略；`strict_json` 拒绝重复字段/非有限数；`dynamic_routing.validate_profile`；特殊 kind 约束（public-review-calibration/citation-crosscheck/g1-transport-validation 需 `task_class==kind 且 science_risk=="critical"`；calibration_seat∈{domain,editorial,statistics}；`validation_roster` 仅 `astra-argon`；`response_streaming` 仅该样本 true）；输入 receipts（path+sha256），执行前后 `_check_inputs()` 重算哈希。按 kind 分发：`g1-transport-validation`→`run_g1_transport_validation`、`citation-crosscheck`→`literature_source_tasks.run_citation_crosscheck`、`public-review-calibration`→`public_review_anchors.run_calibration`、其余→`task_router.plan/run`（provider 为 "internal family placeholder"）。报告固定 `budget_granted_cny:0`、`not_manuscript_or_evidence:True`、`automatic_acceptance:False`、`model_output_accepted_for_science:False`；execute 时 `internal_candidate_requires_review`，否则 `dry_run_no_model_call`。
  - `run_g1_transport_validation()`：默认 dry-run（`calls_planned:3, maximum_calls:5, budget_granted_cny:0, topic_approval_granted:False, scientific_completion_verified:False, not_manuscript_or_evidence:True`）；execute 需 `DR_OS_REQUIRE_REMOTE_RESERVATION=="1"` + owner cloud project；调 `api_orchestrator.run_cycle(..., task_kind="scientific-judgment")`（**真实付费**），校验 before/after 的 stage/gate/approved_gates/paper_count 未变（"changed a protected scientific scope"），finally 记 ledger 新行/cache_hits/attempt_receipts/accounting/discovery_operations/budget_before&after/`cumulative_budget_consumption_change_cny`/duration；失败 `partial_failed_no_retry` 不重试。
- **依赖**：`research_artifacts`(strict_json)、`ai_providers`、`metadata_contract`、`model_routing`、`task_router`、`engineering_contract`、`publication_figures`(PROJECTS_ROOT)、`dynamic_routing`、`billing_quotes`、`public_review_anchors`、`literature_evidence`、`literature_source_tasks`、`api_orchestrator`、`model_runtime`。
- **边界与限制**：输出仅内部候选，不自动采纳为科学证据；dry-run 默认；硬编码 `calls_planned=3`、`maximum_calls=5`、"At most twelve new literature search operations"、`astra-argon` roster、validation caps 4000/12000。

### 1.13 `billing_quotes.py`（318 行）★计费核心
- **职责定位**："Explicit CNY billing contracts; **never select models or execute tools**"。V2 报价把传输路由与计费 `plan/group/mode` 与推理设置分开绑定；上下文分档"两端闭区间且恰好覆盖每个非负长度一次"；工具费需有界授权与完整 typed provider/gateway usage receipt。对应 AGENTS 规则 23（累计总额、全部尝试计费、verified charges 优先否则保守上界）。
- **对外能力**：纯函数库（无 main/CLI）：`select()`、`reserve_cost()`、`bill()`、`token_parts()`、`tool_limits()`、`number()/count()/identity()/quote_digest()`。
- **输入与输出**：输入条件报价文档 `{"schema_version":"2.0","quotes":[...]}` 与 usage receipt；输出规范化 quote（含 `quote_sha256`）、预留金额、`(total, unknown_cache_price, details)`。
- **关键实现机制**：`_normalize()` 强校验：字段白名单、必须显式声明 `IDENTITY_FIELDS`、currency 必须 `CNY`、`price_version` 显式、`context_brackets` 从 0 起有序连续无重叠且仅末档开放上界、`context_basis∈CONTEXT_BASES`、条件报价必须显式给出 cache read/write 费率（含零）、TTL 费率成对、tool_fees 的 billing∈{flat_per_call,per_unit}；末尾算 `quote_sha256`。`select()` 必须精确匹配 `(provider,endpoint,model)` 且 `billing_identity==requested`，"no price fallback"，并拒绝重复 route/identity 报价。`reserve_cost()` 取所有 tier 中最大 input rate（含 cache/TTL）与最大 output rate + 工具费，注释 "Reserving every declared tier is intentionally conservative when tokenization and gateway context accounting cannot be known exactly before transport"。`token_parts()` 从 usage 解析 ordinary/cache_read/cache_write/5m/1h/unclassified/full_request_input/uncached_input/output_including_reasoning，校验冲突 receipts、TTL 分解、cache 不超 input、reasoning 不超 output（"no guessed surcharge"）。`_tool_charge()` 要求完整 typed receipt（schema 1.0/complete/source∈{provider_usage,gateway_billing}/receipt_id/request_id 匹配响应/items 精确字段），units≤授权上限。`bill()` 按 context_basis 选唯一档，算 token_cost + tool_cost，返回 `unknown_cache_price` 标志。
- **依赖**：无其它 scripts 模块（纯标准库）。
- **边界与限制**：价格全部来自外部报价文档，代码不硬编码单价；唯一硬编码保守回退是未分类 cache write 按 `2 * input_per_million` 估计；`unknown_cache_price=True` 时上层应诚实标注上界估计；无网络/无模型选择/无工具执行。

### 1.14 `bocha_jev_probe.py`（152 行）
- **职责定位**：检查官方 Bocha Jev API 并可做一次"免费策略"试验；"Only synthetic public metadata is sent. This is a transport check, not a scientific decision or a replacement for a human research gate"。
- **对外能力**：CLI `--output PATH [--live] [--free-policy-checked-on YYYY-MM-DD]`；`connectivity()`、`trial()`、`http_json()`。
- **输入与输出**：`BASE="https://jev.bocha.cn"`、`MODEL="bocha-jev-v1"`、`LABELS={prioritize,ordinary_review,uncertain}`；输出 JSON 报告（status/http_status/model_call_made/cost_cny 或 triage_label/usage/probabilities）。
- **关键实现机制**：`NoRedirect` 拒绝重定向（"Never forward an Authorization header to another host"）；`http_json()` 路径白名单仅 `("GET","/v1/models")` 与 `("POST","/v1/systemone")`，错误体不进日志、≤64 KiB、20s 超时、密钥不反射到错误；`connectivity()` 不带 key 探 /v1/models，期望 200/401/403（`model_call_made:False, cost_cny:0`）；`trial()` 要求 `policy_checked_on == today.isoformat()`（"the official no-charge Jev policy must be checked again today"）、key≥8 字符、先校验 exact model 在认证模型列表、POST 一个 choice triage、校验 actual model、choice∈LABELS、usage（input_tokens≥0、output_tokens==0）、probabilities（有限、0..1、和≈1 容差 0.02），返回 `billing_receipt_available:False` 且 note 明说 "usage is not a billing receipt. This label has no scientific evidentiary value"。
- **依赖**：无其它 scripts 模块（纯标准库 urllib）。
- **边界与风险**：**真实网络调用点**（GET/POST jev.bocha.cn），但独立于主生产网关/预算控制（`cost_cny=0`、`billing_receipt_available=False`），不走 `model_runtime` 累计预算与身份核查；`policy_checked_on` 只是把传入日期字符串与"今天"比较，**代码不联网核实免费政策本身**；note 反复声明无科学证据价值。

### 1.15 `calibration_analysis.py`（210 行）★"宣称缺口"典型
- **职责定位**："Summarize frozen blinded judgments and recorded costs **without certifying quality**"。对应 README「真实 0.85 一致性、领域校准仍需实际研究验收」。
- **对外能力**：`summarize(project, packet_id)`、`refresh(project, packet_id)`、`protocol(packet)`、`settled_cost(row)`、`cost_summary(...)`；无 CLI。
- **输入与输出**：输入 calibration packet（`review_packets.plan`）、`reports/review-packets/<id>/answer-key.json`、`state/model-usage.jsonl`、owner confirmations；输出 `reports/review-packets/<id>/analysis.json`。
- **关键实现机制**：`protocol()` 校验冻结分析协议：minimum_raters 2..20、qualification_thresholds 覆盖每个 rubric dimension 且在 min..max、case_partitions 每 case 必须 calibration/holdout、**同一 source sha256 不得跨 calibration/holdout 泄漏**、cost_run_ids 唯一、candidate run_ids 唯一、additional_cost_receipts≤200。`settled_cost()` 只接受已结算费用（拒绝 `usage_estimated`、未对账 hold）：`settled_usage_receipt` 或（cache_hit 且 value==0），或 `settled_gateway_debit` 且 `billing.independent_gateway_debit.actual_cost_cny` 与 value 误差≤1e-9、`debit_evidence.source` 必须是硬编码的官方 usage URL（`https://cheapai.info/api/log/token` / `https://codekey.ai/v1/usage`）且 `exactly_one_new_gateway_request is True`。`cost_summary()` 按 cost_run_ids 选 ledger 行、处理零成本 `source_contract_failed_no_retry` 诊断行、校验 additional receipts provenance、要求 owner 的 `cost_scope_confirmation` 精确匹配（analysis_sha256/ledger_sha256/no_double_counting）才给 `total_recorded_cash_cost_cny`。`summarize()` 收集 raters（每个 rater 只能一个 owner record）、rater 不足返回 awaiting_ratings，否则算各 candidate 的 critical_errors、各 dimension mean/min/max、qualified、exact_pairwise_rating_agreement。
- **依赖**：`research_artifacts`(path_in/read/record/sha/write/bound_source)、`review_packets`、`ai_providers`(函数内)、`output_provenance.current_origin`。
- **边界与限制（重点）**：base 恒为 `calibration_status:"NOT_CALIBRATED"`、`gate_approved:False`、`scientific_completion_verified:False`、`model_routing_changed:False`、`blindness_and_qualifications_verified:False`、`identities_revealed:False`；`agreement_is_not_chance_corrected:True`（不是 chance-corrected kappa）；`human_effort_priced:False`；`total_cost_status` 只能 `owner_reconciled_cash_scope` 或 `cost_scope_needs_reconciliation`；inference 明说 "Descriptive candidate-level summaries only; cases and repeated candidates are not independent sample-size units"。**代码只做描述性汇总，没有"校准通过/质量认证/放行/改路由"的任何实现，且被显式否定**——这是"文档宣称但代码里看不到实现"的最典型处。硬编码网关 usage URL。

### 1.16 `catalog_diagnostic.py`（131 行）
- **职责定位**："Cloud-only, read-only diagnostics for the configured Gemini relay catalog. No inference, pagination, redirect, spending grant, reservation, or project edit"。
- **对外能力**：CLI `--output [--include-us-host]`；`report(environment, include_us_host)`、`_inspect()`、`_model_id()`。
- **输入与输出**：`CATALOG_ROOTS=frozenset({"https://codekey.ai","https://api.codekey.ai"})`（注释：US host 仅诊断传输，不成为生产路由）；输出 `endpoints[]`（root/path/method/http_status/metadata_access_verified/model_ids/additional_pages_advertised）。
- **关键实现机制**：`report()` 要求 `GITHUB_ACTIONS=="true"` 且 `GITHUB_REPOSITORY=="hengyizang/lunwen"`（**硬编码仓库名**）、校验 codekey-gemini 的 root/family、从 `spec["key_setting"]` 取密钥；`_inspect()` 路径白名单（openai-list `/v1/models`、google-list `/v1beta/models`、google-model `/v1beta/models/<model>`）、`NoRedirect`、GET、≤2 MB、30s、envelope 校验、≤10000 行、收集 model_ids，只记录 `nextPageToken` 不翻页。返回 `model_generation_calls:0, new_spending_authority:False, inference_access_verified:False, scientific_completion:False`。
- **依赖**：`ai_providers`、`production_readiness.NoRedirect`。
- **边界与限制**：**真实网络 GET 调用点**（只读元数据，无推理、无分页、无重定向、无花费）；`inference_access_verified=False` 明确只验证元数据访问；硬编码 `GITHUB_REPOSITORY` 与两个 root。

### 1.17 `ccfa_acceptance.py`（62 行）
- **职责定位**："Cloud-only, no-provider acceptance of all seventeen installed CCFA skills" —— 纯软件安装/字节验收。
- **对外能力**：CLI `--installed PATH --output PATH`；`acceptance(installed, output)`。
- **输入与输出**：输入已安装目录、`ccfa_runtime.lock()/registry()/guidance()/model_contract()/reference_paths()/source()`；输出验收 JSON（status/skills/installed_skill_count/verified_original_files/...）。
- **关键实现机制**：`runtime.cloud()` 云门禁、`installation_errors()` 安装完整性；对 lock 中每个 resource 做 **git blob SHA-1**（`sha1("blob "+len+"\0"+data)`）+ size 与 pin 比对（"Official installation differs from pin"）；对每条 route 校验 `guidance(id,detailed=True)["text"]` 出现在 `model_contract(...,skill=id)` 中、`reference_paths` 对应 source 也在 contract 中（完整上游条目/引用体必须进入实际模型 guidance）。
- **依赖**：`ccfa_runtime`、`research_artifacts.write`。
- **边界与限制**：报告固定 `model_calls:0, paid_calls:0, scientific_completion_verified:False`，每行 skill `scientific_outcome_verified:False`，scope 明说 "no real-topic/model-quality claim"；呼应 AGENTS 规则 9「软件验收不等于成功无人值守科研项目」。

### 1.18 `ccfa_runtime.py`（752 行）★CCFA 运行时
- **职责定位**："Pinned, complete CCFA skill family adapted to the native cloud control plane. Reading instructions or preparing a task never calls a model or grants execution. The same approved models consume stage/task-selected guidance in existing roles."
- **对外能力**：CLI `bootstrap|verify|install|resource|request [--project --request-file --resource]`；`execute(project, operation)`（action `ccfa_task`/`ccfa_task_clear`/`ccfa_science`/`ccfa_humanization`）；`prepare()`/`model_contract()`/`guidance()`/`source()`/`bootstrap()`/`resource()`/`install()`/`registry()`/`lock()`/`task_context()`。
- **输入与输出**：`COMMIT="f157d7ed..."`（硬编码上游 commit）、`VENDOR="third_party/ccfa-skills"`、`LOCK/ROUTES` 于 `integrations/`；`STAGE_DEFAULTS`/`ROLE_DEFAULTS`/`REFERENCE_DEFAULTS`/`REFERENCE_CROSS`/`REFERENCE_MODES`（中英关键词正则→引用）为硬编码映射，17 个 `ccf-*` 技能、mandatory `["ccf-humanization","ccf-common"]`。输出 `reports/ccfa-tasks/<id>/<packet_id>.json` + `active.json`（不可变 packet）。
- **关键实现机制**：
  - **哈希/pin 绑定**：`source()` 校验 `sha256(canonical(data)) == canonical_lf_sha256`；`installation_errors()` 全量校验 + native adapter SKILL.md + `skill_discovery.current` + native_tools；`registry()` 强制 schema 1.0/commit==COMMIT/恰好 17 个唯一 id/mandatory 顺序；`lock()` 强制 repository=="mikubaka88/CCFA-Skills" 与 commit。
  - **任务包不可变**：`prepare()` 校验 request schema、stage 与 state 一致、paper_id∈P01–P06、inputs≤40 且公共语料白名单（path+sha256、`safe_text` 拒绝密钥）、editable_inputs 必须是当前 paper 的 manuscript、references≤30 且属选中技能；packet 含 `request_sha256`、`implementation_sha256`（本文件 SHA）、`core_thesis_sha256`、`packet_id=digest(result)`、`model_calls:0/experiment_executed:False/scientific_completion_verified:False/gate_approved:False`；写后 `record()` provenance。`_task_packet()` 重验 executor provenance、sha、packet_id digest、stage、active_paper、core_thesis_sha256、implementation_sha256、guidance、selected skill 身份、inputs 哈希（editable 仅允许非 anthropic 的 writer/remediator 改动）、references 未变。
  - **角色隔离**：`_task_sources()` 对 critic 隐藏 "Author instructions and preferred verdicts are withheld"；`model_contract()` 的 boundary 明说 "Upstream names and examples do not authorize a new ccfa.yaml, another runner, shell commands, paid requests, model changes, automatic submission, human approvals, or fabrication"，并重申 Claude planner/critic 只读、非 Claude writer 写持久、G0 planner→writer、G1+ planner→writer→critic、G5 三家族互盲、"Generic scores never establish JCR status or acceptance probability"；`MAX_PACKET=2MB`。
  - **真实网络**：`bootstrap()` 经 `git clone/fetch --filter=blob:none --depth=1` 固定 COMMIT + sparse checkout + `cat-file --batch` 校验 git_blob_sha/canonical_lf_sha256 后补齐缺失资源；`resource()` 经 `network_safety.fetch_bytes` 从 `raw.githubusercontent.com/<owner>/<repo>/<COMMIT>/<path>` 拉取精确资源并校验 size+git blob SHA-1，缓存于 `.runtime/ccfa/resources/<COMMIT>/`，`research_data_authorization:False`。
  - `cloud()` 要求 `GITHUB_ACTIONS=="true"` 或 `DR_OS_CLOUD_EXECUTOR=="1"`。
- **依赖**：`research_artifacts`、`api_orchestrator.contains_environment_secret`、`skill_discovery`、`network_safety`(fetch_bytes)、`output_provenance.current_origin`、`cloud_job.literature_operation`、`ccfa_science.execute`；外部 git CLI / GitHub。
- **边界与限制（重点占位）**：`humanization_policy_receipt()` 固定 `mechanical_review:"retired"`；`editorial_method_guidance()` 明说 "Mechanical H/AD/CFH scans and independent scorecards are **retired**; semantic results stay unknown. No per-ID notes, extra calls or gates are required"；`execute("ccfa_humanization")` 直接返回 `{"status":"retired","mechanical_review_performed":False,"semantic_review_status":"unknown","model_calls":0,"manuscripts_modified":False}`；`install()`/`bootstrap()`/`resource()` 均 `model_calls:0`。**退休方法在本文件里是空占位，没有任何实际审查执行**。`DR_OS_CLOUD_EXECUTOR=1` 可绕过云检查（与 `acceptance_scope.py` 同源）。

### 1.19 `ccfa_science.py`（649 行）
- **职责定位**："Source-bound CCFA scientific extensions ... These are **deterministic report builders, not another runner, approval system, research-state store, model evaluator or scientific acceptance score**."
- **对外能力**：`execute(project, operation, request)`、`current(project, operation, identifier)`；`OPERATIONS={continuity,lineage,novelty_watch,exemplar,internal_review}` 五类构建器 `_continuity/_lineage/_novelty_watch/_exemplar/_internal_review`。无 CLI（经 `ccfa_runtime.execute("ccfa_science")`）。
- **输入与输出**：request `{schema_version,id,source,expected_source_sha256,expected_previous_sha256}`，source 必须 `program/ccfa-inputs/<id>.json`（≤2MB）；输出 `reports/ccfa-science/<operation>/<id>.json` + `history/<sha>.json` 不可变归档。
- **关键实现机制**：
  - `LIMITS` 固定 `paid_calls:0, experiments_executed:0, gate_approved:False, scientific_completion_verified:False, human_scientific_review_required:True, ongoing_monitoring_installed:False`。
  - `_text()` 明确拒绝 `"todo"/"tbd"/"unknown"/"n/a"` 作为具体输入文本（**防占位**）；`_bind()` 路径白名单 + 排除 state/raw/private/secrets/credentials/.git/submission + 校验当前 sha256 + `current_origin` 非 anthropic（"requires current non-Claude writer provenance"）；`_anchor()` 经 `research_candidates.anchor_errors` 校验 located evidence；`_scope()` 博士问题必须与 `program/core-thesis.json` 一致，默认 `status="proposed_requires_G1_G2_human_review"`。
  - `_check()`：只有"当前原生确定性通过报告"能背书 verification（origin family=other、provider=deterministic-control-plane、model∈固定白名单，报告 `pass/passed` 为 True 且绑定当前 artifact 哈希）。
  - `_continuity()`：goal revision 单调递增、material transition 需 basis/reason/evidence anchors、verified artifacts 需通过 `_check`、禁止静默移除已 verified artifacts；返回 `semantic_goal_preservation_verified:False, replaces_existing_project_state:False`。
  - `_lineage()`：候选 DAG（seed/refine/combine/transfer/invert/instrument）有序无环；`measured` 状态必须绑定成功且精确注册的原生实验 receipt（run.json status succeeded、approved_plan_sha256、registry 唯一、configuration.candidate_id）；保留旧分支/负结果；返回 `best_measured_candidate:None, best_requires_frozen_metric_and_comparable_experiment_audit:True, conceptual_lineage_is_not_novelty_proof:True, novelty_verified:False`。
  - `_novelty_watch()`：时间窗口、claim_source 必须 `program/novelty-claim-matrix.json`、coverage 必须 `evidence/literature-api-ledger.jsonl` 里唯一 `status=="success" && mode=="live_search"` 的 receipt、时间落窗、raw_response 哈希校验；返回 `empty_scan_proves_novelty:False, search_coverage_independently_verified:False, actions_are_proposals_only:True, semantic_overlap_verified:False`。
  - `_exemplar()`：需 current 且 full_text 源 + `source_scope.verify`；7 类 moves；返回 `human_reading_verified:False, scientific_quality_verified:False, global_defaults_changed:False, interpretation_is_not_source_claim:True`。
  - `_internal_review()`：冻结 criteria/readiness_criteria、稳定 issue ID/状态/origin/severity、evidence 必须锚定每个适用稿件版本、`writing_review_actions.assess`、不得静默删除/降级 inherited issues；`current_readiness` 最高只到 `ready_for_human_review`，`acceptance_probability:None, external_reviewer_round_created:False, categorical_findings_require_independent_scientific_review:True, semantic_resolution_verified:False`。
  - `execute()`：需 `DR_OS_CLOUD_EXECUTOR=="1"` 或 `GITHUB_ACTIONS=="true"`；`_stored()` 校验报告 provenance；**CAS 语义**（`expected_previous_sha256` 与当前 output sha 比对）、`exact_request_replay` 复用、fingerprint（operation/id/scope/inputs/implementation/result）决定复用；`current()` 重放输入新鲜度（implementation_sha256、scope、所有 inputs 哈希/provenance、writing_action 实现）"a report is not a scientific certificate"。
- **依赖**：`output_provenance`、`research_artifacts`、`paper_execution`(experiment_path)、`research_candidates`(anchor_errors)、`literature_workbench`(_snapshot/_json)、`source_scope`、`writing_review_actions`。
- **边界与限制**：无网络、无模型、无实验、无闸门；全部 `*_verified:False`/`None`；`ready_for_human_review`（非 ready）；所有结论是 proposals。硬编码路径模式、白名单 model 集合、P01–P06。

### 1.20 `check_env.py`（120 行）
- **职责定位**："Report the local environment needed by the research workflow" —— 本地环境/命令/包检查。
- **对外能力**：CLI `--soft`（总返回 0）、`--mode api|cli|all`（默认 api）、`--install-root`；`version_output()`、`package_version()`、`main()`。
- **输入与输出**：输出 JSON 报告（python 版本/ok≥3.10、platform、wsl、mode、repository_root、install_root_ok、docker_root、docker 位置回执、required/optional_commands、optional_ai4science_packages〔paper-qa/tooluniverse〕、optional_reference_packages〔ref-verify〕、recommendations）。
- **关键实现机制**：WSL 检测（platform.release/version 含 microsoft 或 `/proc/sys/fs/binfmt_misc/WSLInterop`）；required = git +（cli/all 时 claude/codex）；optional = latexmk/pandoc/docker/podman/quarto/Rscript/pqa/tu/ref-verify（只查 `shutil.which`）；`install_root_ok` 比较 repository_root 与 `--install-root`；`docker info --format` 子进程（15s 超时）取 DockerRootDir；读 `.runtime/docker-location.json` 回执，硬编码期望 `r"d:\ad\lunwen\.runtime\docker-desktop"`；`api/all` 模式检查 `UUAPI_API_KEY/UUAPI_BASE_URL/UUAPI_ANTHROPIC_MODEL/UUAPI_OPENAI_MODEL` 四个变量；`okay = python.ok && all(required) && install_root_ok`。
- **依赖**：无其它 scripts 模块（标准库 + 本地 `docker` 子进程）。
- **边界与限制（重点标注）**：**`version_output(command)` 名实不符**——函数返回 `shutil.which(command)`（可执行文件路径），不是版本输出；`required_commands`/`optional_commands` 的值也都是路径而非版本。**默认 mode=api 仍把 UUAPI_* 四个变量当作 API 模式推荐配置**，与 AGENTS.md「UUAPI 为 deprecated compatibility adapter」、`api_orchestrator.py balance` 的 "UUAPI is retired in production"、生产路由（CheapAI/CodeKey + `DR_OS_*` keys）**不一致**，属遗留默认。硬编码 Windows D 盘路径。纯本地检查，无网络、无付费、无项目状态修改。

---

## 2. 本组整体能力归纳与 G0–G5 位置

本组 20 个文件是系统的**"确定性控制平面 + 计费/身份/证据底座 + 入口层"**，不是科研执行器，也不产出科学结论。整体实现 8 类能力：

1. **模型传输与身份/计费底座**：`ai_providers.py`（17 provider、12 生产路由、单次 reservation 单次 POST、模型 ID 精确回显校验、响应脱敏留痕、SSE 严格解析、usage 归一化）+ `billing_quotes.py`（CNY 报价/保守预留/结算/工具费回执）+ `api_orchestrator.health/cost` 与 `autopilot`/`auxiliary_job` 的预算门。承载"累计预算、全部尝试计费、身份核查、失败/歧义失败留痕"。
2. **API 周期总编排与角色隔离**：`api_orchestrator.run_cycle()` 实现 planner(Claude 只读)→writer(非 Claude 写持久)→一次独立 critic→实际问题触发 remediation + 复审；G5 提交阶段三家族互盲 panel；`validate_roles`/`reject_long_source_copy`/`record_writer_provenance`/`safe_target`/`apply_bundle` 把"Claude 不得写持久产物"落成 Python 硬约束。
3. **阶段闸门与状态推进**：`require_current_stage`、`scientific_scope.validate`、`autopilot.run_stage`→`transition_ready_gate`、`api_orchestrator.after_reviews`/`researchctl.gate_errors`；`manifest.gate_authority=False`、`next_action` 明确 G1/G2 等人工决定，其他阶段自动检查续跑，**绝不自动投稿**。
4. **证据/来源/哈希绑定与失败留痕**：`project_snapshot`(逐文件 sha256)、`prepare_revision_baseline`(源树哈希)、`ai4science_evidence`(输入/输出/stdout 全量哈希 receipt、advisory)、`automated_visual_review`(packet+prompt+计费回执哈希)、`artifact_ownership`(路径所有权)、`ccfa_runtime`/`ccfa_science`(git blob SHA-1 + canonical LF SHA-256 + packet digest + CAS + 不可变历史)。
5. **G3/G4 确定性质量与 G5 风格/视觉/合规检查**：`automated_quality`(G3/G4 confirmation/preregistration/reproduction)、`academic_style`(行级风格审计 + 两个可选 linter + 稿件树哈希)、`automated_visual_review`(多模态逐页检查)、`api_orchestrator.refresh_post_write_evidence` 串起 hygiene/revision_integrity/publication controls。
6. **数据发现（仅 leads）**：`automatic_data_discovery` + `api_orchestrator.latest_dataset_discovery`，明确"元数据 shortlist 不是许可/适用性/主张决定"；所有来源失败时在**付费模型调用前**阻断。
7. **CCFA 技能族接入与确定性科学扩展**：`ccfa_runtime`(固定 commit、17 技能、任务包、guidance 注入既有角色) + `ccfa_science`(5 类来源绑定报告) + `ccfa_acceptance`(安装/字节验收)；全部 `model_calls=0`、`scientific_completion_verified=False`。
8. **外部工具/环境诊断与兼容入口**：`ai4science_evidence`(ToolUniverse/原生 Q&A、永不启动 standalone PaperQA2 agent)、`bocha_jev_probe`、`catalog_diagnostic`、`check_env`、`acceptance_scope`(测试夹具)、`autopilot`(start/resume/plan)、`auxiliary_job`(严格 manifest 辅助任务)。

**在 G0–G5 中的位置**：`check_env`/`ai_providers.configuration`/`catalog_diagnostic`/`bocha_jev_probe`/`ccfa_acceptance` 属 **G0 就绪/环境/安装验收**；`automatic_data_discovery`/`ai4science_evidence`/`api_orchestrator` 的 topic-intelligence 与 paper-architecture 服务 **G1/G2 情报与架构**（人工决定仍由外部 `scientific_scope`/`researchctl` 控制）；`automated_quality`/`artifact_ownership`/G3 契约服务 **G3 封存**；`ai4science_evidence`/实验 receipt 绑定服务 **G4 结果证据**；`academic_style`/`automated_visual_review`/`api_orchestrator` 的 submission_cycle/`ccfa_science.internal_review`/`refresh_post_write_evidence` 服务 **G5 独立审查与投稿包**（本组不含 `submission_package.py`，范围外）；`billing_quotes`/`model_spend`/`cost_audit` 贯穿全程累计预算。本组**没有** G1/G2 人工批准、`experiment_runner` 执行、真正投稿的实现。

**组内调用关系（直接 import/调用，仅本组 20 文件内）**：
```
autopilot.py ──────────────► api_orchestrator.run_cycle / redact / stage_config
auxiliary_job.py ──────────► api_orchestrator.run_cycle / project_root / redact
                          ├─► billing_quotes.tool_limits
                          └─► ai_providers（family/config/validate_attachments）
api_orchestrator.py ───────► ai_providers, academic_style, automated_visual_review,
                             automatic_data_discovery, artifact_ownership
automated_visual_review.py ► ai_providers
automated_quality.py ──────► (经 researchctl/其它组外模块)
automatic_data_discovery.py► (经 network_safety / data_discovery)
acceptance_scope.py ───────► (经 scientific_scope)
academic_style.py ─────────► (经 research_artifacts / ref_verify_adapter / ...)
billing_quotes.py ─────────► ai_providers（函数内 import，取 PRODUCTION_PROVIDERS.root）
calibration_analysis.py ───► ai_providers（函数内 import）
catalog_diagnostic.py ─────► ai_providers
ccfa_acceptance.py ────────► ccfa_runtime
ccfa_runtime.py ───────────► api_orchestrator.contains_environment_secret
                          └─► ccfa_science.execute（action=ccfa_science）
ccfa_science.py ───────────► (经 output_provenance / literature_workbench / ...)
ai4science_evidence.py ────► (经 model_spend / paper_qa / tooluniverse_worker)
bocha_jev_probe.py ────────► 独立（urllib → jev.bocha.cn）
check_env.py ──────────────► 独立（标准库 + docker 子进程）
__init__.py ───────────────► 独立
```
枢纽：`ai_providers.py`（被 6+ 文件依赖，是所有付费与身份判断的底层）、`api_orchestrator.py`（编排枢纽）、`ccfa_runtime.py → ccfa_science.py`（CCFA 链）。`autopilot`/`auxiliary_job` 是同一 `run_cycle` 的两个上层入口。

---

## 3. 特别标注汇总

### 3.1 TODO / 占位 / 未实现 / 硬编码
- **退休方法空占位（多处）**：`academic_style.analysis.editorial_methods = {"status":"retired","mechanical_review_performed":False,"semantic_review_status":"unknown"}`；`api_orchestrator.editorial_feedback()` 同款 retired 字典；`ccfa_runtime.editorial_method_guidance()` 明说 H/AD/CFH 机械扫描/scorecard retired、`semantic results stay unknown`；`ccfa_runtime.execute("ccfa_humanization")` 直接返回 `retired` 且不改稿；`humanization_policy_receipt()` 固定 `mechanical_review:"retired"`；api_orchestrator 多个 prompt 写 "Retired H/AD/CFH scorecards supply no completed review"。
- **统计水印/检测类占位**：`api_orchestrator.hygiene_feedback()` 固定 `statistical_watermarks:"not_assessed"`、`watermark_absence_verified:False`、`protected_findings_require_contextual_review:True`；`academic_style` 固定 `detector_score_used:False`、`human_review_required:False`、`disclosure_must_be_preserved:False`。
- **校准能力缺失（显式否定）**：`calibration_analysis` 恒 `calibration_status:"NOT_CALIBRATED"`、`gate_approved:False`、`scientific_completion_verified:False`、`model_routing_changed:False`、`blindness_and_qualifications_verified:False`、`identities_revealed:False`、`agreement_is_not_chance_corrected:True`、`human_effort_priced:False`。**没有"校准通过/认证/放行/改路由"实现**。
- **ccfa_science 全部 LIMITS 为否定/零**：`paid_calls:0, experiments_executed:0, gate_approved:False, scientific_completion_verified:False, human_scientific_review_required:True, ongoing_monitoring_installed:False`；`best_measured_candidate:None`、`acceptance_probability:None`、`current_readiness` 上限 `ready_for_human_review`、大量 `*_verified:False`。
- **固定立场字段**：`ai4science_evidence` receipt 恒 `advisory_only:True, human_verification_required:True`；`automated_visual_review` 恒 `human_review:False, scientific_validation:False`；`auxiliary_job` 恒 `not_manuscript_or_evidence:True, automatic_acceptance:False, model_output_accepted_for_science:False`。
- **硬编码清单（择要）**：`ai_providers` 的 12 条生产路由（域名 `cheapai.info`/`codekey.ai`、未来型号 `gpt-6.1-sol`/`claude-sonnet-5-5`/`gemini-4-argon`/`kimi-k3.1-pro` 等、`DR_OS_*_KEY` 变量名）、4 MiB/14 MiB/10 MiB 与 32768/600s 上限；`ccfa_runtime` 的 `COMMIT`、17 技能/映射、GitHub URL；`catalog_diagnostic` 的 `GITHUB_REPOSITORY=="hengyizang/lunwen"` 与两个 root；`check_env` 的 `d:\ad\lunwen\.runtime\docker-desktop`；`bocha_jev_probe` 的 `BASE/MODEL/LABELS`；`calibration_analysis` 的网关 usage URL；`billing_quotes` 的 `2*input_per_million` 保守回退；`auxiliary_job` 的 `calls_planned=3/maximum_calls=5/"At most twelve..."/astra-argon`；`automatic_data_discovery` 的 25/80 阈值；`automated_visual_review` 的每周期 5 次/200 页/10 MiB；`acceptance_scope` 的 `"Synthetic fixture human"`/`target_jcr_quartile="Q1"`。
- **默认参数硬编码**：`api_orchestrator`/`autopilot` 的 `max_output_tokens=12000`、`control_max_output_tokens=4000`（可由 `DR_OS_MAX_OUTPUT_TOKENS`/`DR_OS_CONTROL_MAX_OUTPUT_TOKENS` 覆盖）。

### 3.2 真实网络 / 付费 API 调用点
| 文件 | 调用点 | 性质 |
|---|---|---|
| `ai_providers.py` | `_request`/`_production_request`（urllib POST）、`_get_json`（GET usage）、UUAPI 兼容调用 | **真实付费生成**；`GITHUB_ACTIONS=="true"` + 白名单域名 + `relay_guard.authorize_transport` + 单次 POST |
| `api_orchestrator.py` | `health --live` 探针（"Reply with exactly: OK"）、`run_cycle`/`stage`→`model_runtime.call` | **真实付费**（`live_probe_is_billable`）；在 `authorized_calls` 预算上下文内 |
| `automated_visual_review.py` | `model_runtime.call(role="multimodal-inspection", attachments=[...])` | **真实多模态付费**，且必须匹配 settled 计费回执 |
| `auxiliary_job.py` | `run_g1_transport_validation(execute=True)`→`api_orchestrator.run_cycle`；其它 kind→`task_router.run(execute)` | 真实付费（需 `DR_OS_REQUIRE_REMOTE_RESERVATION=1`）；默认 dry_run |
| `ai4science_evidence.py` | `execute_paperqa`→`paper_qa.answer(execute=True)`（中央运行时）；`execute_tooluniverse`→`tooluniverse_worker.py` 子进程 | 前者付费 LLM；后者公开数据 API |
| `automatic_data_discovery.py` | `data_discovery.discover_many`→`network_safety.fetch_json` | 公开元数据 HTTP（非 LLM 付费）；失败在付费周期前阻断 |
| `bocha_jev_probe.py` | `--live`：GET `/v1/models` + POST `/v1/systemone`（jev.bocha.cn） | 独立第三方 API，宣称免费策略，`billing_receipt_available:False` |
| `catalog_diagnostic.py` | GET `/v1/models`、`/v1beta/models`（codekey.ai / api.codekey.ai） | 只读元数据，`model_generation_calls:0` |
| `ccfa_runtime.py` | `bootstrap`（git clone/fetch GitHub 固定 commit）、`resource`（raw.githubusercontent.com `fetch_bytes`） | 网络下载（非付费），带 git blob SHA-1 校验 |
| `autopilot.py` | 经 `api_orchestrator.run_cycle` 间接 | 真实付费（在 `model_runtime.authorized_calls` 内） |
| `check_env.py` | `docker info` 子进程 | 本地，无网络 |

`calibration_analysis` / `ccfa_science` / `ccfa_acceptance` / `billing_quotes` / `academic_style`（本地 linter 子进程）/ `automated_quality` / `artifact_ownership` / `acceptance_scope` / `__init__.py` 无真实网络或付费模型调用。

### 3.3 安全与数据完整性风险
1. **伪造 G1/G2 人工决定的机制可见**：`acceptance_scope.prepare_scope()` 用 `DR_OS_CLOUD_EXECUTOR=1` + `scientific_scope.seal_approval` 生成 actor 为 `"Synthetic fixture human"` 的批准记录；保护仅靠"项目在仓库 `projects/` 内"的路径判断，其它路径项目不受保护。同一环境变量也是 `ccfa_runtime.cloud()`/`ccfa_science.execute()` 的云门禁等价物。
2. **角色隔离存在例外**：`api_orchestrator.validate_roles()` 的 `g1_sample`（astra-argon + 三元组 `("codekey-codex-pro","codekey-codex-pro","codekey-gemini")`）允许 planner 为 openai 家族且与 writer 同 provider，临时弱化"planner 必须 Claude、不同家族独立"的约束。
3. **网关真实性/权重不可证**：`ai_providers` 注释自认 "not assertions about gateway authenticity or quality"、"exact echo is a traceability condition, not proof of genuine weights"、"effort allowlist cannot establish that a relay actually honors the requested effort"。全部模型 ID 为硬编码未来型号，代码只能验证"回显 ID==请求 ID"。
4. **advisory receipt 可被人工登记**：`ai4science_evidence record` 不经执行即可写入 hash 绑定 receipt，`validate()` 只校验哈希/字段，不验证 output 真由该工具产生（已用 `advisory_only`/`human_verification_required` 缓解但仍是证据链弱环）。
5. **脱敏覆盖有限**：`api_orchestrator.redact()`/`secret_values()` 只处理环境变量中匹配 `API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|WATERMARK_KEY` 且长度≥8 的值；其它形式的密钥泄露（硬编码串、文件内容）不在保护范围。
6. **白名单式路径保护**：`artifact_ownership` 全靠硬编码路径清单，新增受保护路径需同步维护；`declared_outputs()` 对草案异常静默放过。
7. **校准/一致性可被误读**：`calibration_analysis` 的 exact pairwise agreement 明确 `agreement_is_not_chance_corrected:True`、样本非独立单位；`settled_cost` 硬编码网关 usage URL；若上层把 `NOT_CALIBRATED` 报告当放行依据会出错（代码已用 `gate_approved:False` 等防住）。
8. **第三方探针绕过预算控制**：`bocha_jev_probe --live` 直接 urllib 访问外部 API，不走 `model_runtime` 累计预算/身份核查（`cost_cny=0`、无 billing receipt）；`policy_checked_on` 仅比较日期字符串，不核实免费政策。
9. **check_env 遗留默认**：api 模式仍推荐 UUAPI_* 变量，与生产路由（CheapAI/CodeKey）及 "UUAPI is retired in production" 不一致，可能误导配置。

### 3.4 "文档宣称但代码里看不到实现"
- **H/AD/CFH 机械扫描与 scorecard**：README/AGENTS 提及的编辑/去 AI 味方法，在 `academic_style`、`api_orchestrator`、`ccfa_runtime` 里统一是 `retired`/`mechanical_review_performed:False`/`semantic_review_status:unknown`，**没有执行实现**。
- **领域校准 / 0.85 一致性 / 质量认证 / 改路由**：`calibration_analysis` 只有描述性汇总，`NOT_CALIBRATED`、`gate_approved:False`、`model_routing_changed:False`，README 自己也声明"仍需实际研究验收"。
- **统计水印检测**：hygiene 只做字符级清理，`statistical_watermarks:"not_assessed"`、`watermark_absence_verified:False`。
- **独立 PaperQA2 agent / AI4Science 作为权威答案**：`ai4science_evidence` 明确 `legacy_pqa_agent_called:False`、`not_paperqa2_sdk:True`、结果 `advisory_only`；有界 SDK bridge 在范围外的 `literature_paperqa`。
- **三家族互盲 panel 的"通过即科学有效"**：`api_orchestrator` manifest 明确 `gate_authority:False`、"recorded opinions grant no scientific clearance"。
- **自动投稿**：全流程无实现；`submission_package.py` 不在本范围，本组所有 manifest 的 `next_action` 都是人工 G1/G2 或自动检查续跑。
- **CCFA 科学扩展作为验收**：`ccfa_science` 自述 "not ... scientific acceptance score"，`acceptance_probability:None`、`ready_for_human_review`、全部 `*_verified:False`；`ccfa_acceptance` 明说 "no real-topic/model-quality claim"。
- **G1/G2 人工批准**：真实路径由范围外 `scientific_scope`/`researchctl` 控制；本组可见的 `seal_approval` 调用只出现在合成夹具里。

### 3.5 函数名与实际行为不符 / 需留意
- **`check_env.version_output(command)`**：返回 `shutil.which(command)`（可执行文件路径），不是版本字符串；`required_commands`/`optional_commands` 的值亦为路径。
- **`ai_providers.production_supported_efforts` / `configuration`**：前者返回"已实现的原生 payload 档位"（注释明确不是 relay 质量/验收），后者主动不暴露凭据（`configured` 仅 bool），都与名字的直觉有偏差。
- **`autopilot.show_plan`**：名为 plan 但零请求/零花费/零状态变更；`approved/awaiting_approval` 时 `planned_model_calls:None`（诚实标注未知）。
- **`auxiliary_job.run`** 中 `provider = task_router.PROFILES[kind][0]`：注释自称 "internal family placeholder"，不是真实 provider 选择（真实由生产策略决定）。
- **`academic_style.analyze_text`** 文档写 "word/phrase ratios never decide readiness"，但 `research_integrity` 类规则命中会进 `errors` 并令 `status=revise`——严格说是"词频比率不决定、规则匹配决定"，措辞易误解。
- **`bocha_jev_probe.trial`**：确实做一次模型调用（`model_call_made:True`），但反复声明 "has no scientific evidentiary value"、"not a billing receipt"。
- **`calibration_analysis.settled_cost`**：只接受已结算费用，估计/未对账 hold 一律返回 `None`（比名字暗示更严格）。

---

## 4. 结论：最关键文件与最值得注意的缺口

**最关键 5 个文件**：`api_orchestrator.py`（编排与角色隔离总枢纽）、`ai_providers.py`（唯一付费出口与身份/失败留痕底座）、`billing_quotes.py`（累计预算/保守预留/结算）、`ccfa_runtime.py`（技能族 pin 与任务包不可变性）、`automated_visual_review.py`（把"通过"绑定到已完成计费回执的范例）。

**最值得注意的缺口/风险**：① 多个"已退休"方法（H/AD/CFH、机械审查、humanization action、统计水印）在代码里是**空占位**，与文档措辞存在落差；② `calibration_analysis` 把校准能力整体锁定为 `NOT_CALIBRATED`，没有任何认证/放行实现；③ `acceptance_scope` 展示了用 `DR_OS_CLOUD_EXECUTOR=1` + `seal_approval` 生成"人工批准"记录的可行路径，`validate_roles` 的 `g1_sample` 又开了一个角色隔离例外；④ `ai_providers` 全部模型 ID/网关为硬编码未来型号，代码明确无法证明网关真实性与实际权重；⑤ `ai4science_evidence record` 允许不经执行登记 advisory receipt、`check_env.version_output` 名实不符且 api 模式仍推荐已退休的 UUAPI 变量。所有"诚实否定字段"（`*_verified:False`、`advisory_only`、`gate_authority:False`、`not_scientific_evidence`）整体上是正确的防幻觉设计，但需要上层严格尊重，否则易被误当放行依据。
