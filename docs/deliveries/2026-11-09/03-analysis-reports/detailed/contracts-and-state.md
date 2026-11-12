# Doctoral Research OS v2.3.0 精读报告：能力契约 / 配置 / 真实项目状态

> 精读角色：代码/文档精读子智能体，专责「能力契约 + 配置 + 真实项目状态」
> 目标仓库：`D:/ad/lunwen`（只读，未修改任何仓库内文件）
> 精读日期：2026-11-09
> 唯一输出：本报告

---

## 0. 精读范围、方法与口径

### 0.1 覆盖范围

按指令排除 `scripts/`、`tests/`、`third_party/`、`.git/`、`.runtime/`、`__pycache__/` 后，实际遍历到 **533 个文本文件**，按顶层目录分布如下（与目录统计一致，可加总核对）：

| 目录 | 文件数 | 主要内容 |
|---|---:|---|
| `projects/` | 185 | `projects/my-phd/` 184 个 + `projects/.gitkeep`，**真实项目状态数据** |
| `docs/` | 101 | 90 个 `.md` + `docs/acceptance/` 9 个验收记录 + `docs/audits/` 1 个 + `docs/writing-comparison-results-20261028.json` |
| `schemas/` | 69 | 全部 `*.schema.json` 数据契约 |
| `skills/` | 46 | 46 个 `SKILL.md` |
| `integrations/` | 29 | 13 个 `.json` + 11 个 codex-research-tools `SKILL.md` + 3 个策略/许可 `.md` + 2 个许可文本 |
| `.agents/` | 26 | 26 个 `SKILL.md` / `openai.yaml`（生成式指针） |
| `config/` | 25 | 全部配置 `.json` |
| `references/` | 18 | 11 个根目录 `.md` + `research-methods/` 7 个 |
| `.github/` | 16 | `workflows/` 15 个 `.yml` + `actions/setup-runtime/action.yml` 1 个 |
| 根目录 | 8 | `README.md`、`AGENTS.md`、`CLAUDE.md`、`pyproject.toml`、`.mcp.json`、`.gitattributes`、`.gitignore`、`THIRD-PARTY-NOTICES.md` |
| 其它 | 3 | `venues/ijssd/venue.json`、`.claude-plugin/plugin.json`、`.workbuddy/memory/2026-11-09.md` |

> 说明一：用户给出的参考规模（docs 83 个 .md / 9376 行、references 18 个 / 1655 行、skills 46 个 / 830 行、config 25 个 / 7129 行、schemas 69 个 / 11259 行、projects 约 11892 行）与当前工作树基本一致；`docs/` 的 `.md` 实测为 90 个而非 83 个，原因是 2026-11-09 当天新增了 `OWNER-DECISION-*.md` 三份、`DOTS-EFFECT-FIRST.md`、`THIRD-PARTY-RUNTIME-POLICY.md` 等文档。本报告一律以**当前工作树实测**为准。
>
> 说明二：另发现 `scientistic-agent-skills/.git/` 下 18 个嵌套第三方 git 内部文件（`HEAD`、`config`、`objects` 等），按排除 `.git/` 的规则未纳入；该目录本身是 vendored 第三方仓库，非本系统自有内容。

### 0.2 方法

- **所有 `.md`**：对契约类、所有者决策类、状态类、验收结论类文档用 `Read` 逐份完整精读（含分段）；对其余文档用 Python 逐份提取「全部标题 + 正文首段 + 含关键结论/矛盾词的行」，确保 218 个 `.md` 无遗漏；`skills/`、`agents/`、`.agents/`、`integrations/` 的 91 个 `SKILL.md`/`.md` 逐份提取 frontmatter 的 `name`/`description` 与正文首段。
- **所有 `.json`/`.yml`/`.csv`/`.jsonl`/`.toml`**：用 Python 逐个解析结构，提取顶层键、`required`、枚举、阈值、布尔状态、触发条件、步骤名；对超长文件（`cloud-validation-2026-11-08.json` 1155 行、`ccfa-skills.lock.json` 7045 行、`model-candidates.json` 1701 行等）提取关键字段而非逐行抄录，但**不跳过任何一个文件**。
- **交叉核对**：把文档宣称、配置、状态数据、验收记录四方对齐，标注落差与矛盾；所有结论均给出文件路径或字段名以便复核。

---

## 1. 能力契约

### 1.1 权威契约来源与优先级

| 层级 | 文件 | 作用 |
|---|---|---|
| 最高操作规则 | `AGENTS.md`（25 条规则，113 行） | 开头即定位「**This repository is a research workflow, not a publication generator**」；rule 25 明确 2026-11-09 三份 owner decision 为**当前政策** |
| 当前所有者决策 | `docs/OWNER-DECISION-2026-11-09.md` / `-EFFECT-FIRST.md` / `-MAXIMUM-FLEXIBILITY.md` | 「效果优先、最大灵活性」：自由集成任何第三方工具/运行时，工具输出经哈希绑定、来源核验后可直入候选证据队列；非 G1/G2 阶段尽量自动化 |
| 阶段契约（权威正文） | `references/stage-contracts.md`（320 行） | G0–G5 每阶段 `Required:` 清单与边界 |
| 阶段契约（机器可读） | `config/stages.json`（schema 1.2，73 行） | 6 阶段 `gate`/`contract`/`hard_floor`/`author_task` + `quality_policy` |
| 流程与分类 | `references/workflow.md`（224 行） | A/B/C 分类、三调用周期、三席位互盲终审、完成边界 |
| 财务 | `docs/TOTAL-COST-POLICY.md`（35 行） | 只做两件事：计算成本 + 强制配置的累计项目总额 |
| 投稿边界 | `docs/PUBLICATION-DISCLOSURE.md`（26 行）、`CLAUDE.md`、`config/defaults.json` | 「**The software never submits a manuscript**」 |
| 需求追踪 | `config/requirements-traceability.json`（850 行，v2.0，2026-11-08） | 45 条 R01–R45 + 156 项 owner checklist |
| 版本定位 | `README.md`、`pyproject.toml`（`version = "2.3.0"`）、`.claude-plugin/plugin.json` | 对外宣称的「G0–G5 全流程、六篇博士论文」能力 |

**契约的诚实自我定位**（`config/requirements-traceability.json` 的 `interpretation` 原文）：
> "Implementation is software capability, not research completion. A blocks scientific-integrity failures; B binds final submission sources once per unchanged snapshot; C observations do not create gates."

即：系统自己把「软件能力」与「研究完成」明确切开，这是理解全项目所有落差的总钥匙。

### 1.2 G0–G5 阶段契约逐段要求

依据 `config/stages.json` + `references/stage-contracts.md`，六阶段如下：

| Gate | 阶段 | 关键必需产物 | 硬性下限 / 决策性质 |
|---|---|---|---|
| **G0** | `intake` | `intake/constraints.json`（status `ready_for_review`）、目标申请路径与时间跨度、可用技能/时间/预算/算力/数据、**七项方向权重**、排除领域与伦理边界、`cloud_only` 执行模式、六篇当前论文的云可行性（无实验室/本地硬件依赖） | 材料事实必须显式，未知保持未知；CNY 300 为**默认**总额，配置总额不得自动增加；G0 用记录化的自动检查，**不预批准 G1–G5** |
| **G1** | `topic-intelligence` | `evidence/search-log.jsonl`、≥3 个严肃候选的 `program/topic-shortlist.json` 及拒绝理由、`program/hypothesis-register.json`（≥3 假设、每假设 2 个竞争解释、判别检验、证伪、云/预算/期限估计）、`hypothesis-audit.json`（须由 `scripts/research_candidates.py` 生成）、`core-thesis.json`（命题 A）、`extension-thesis.json`（独立拓展 B）、`originality-audit.json`（≥5 最近一手工作、3 相邻领域、3 查询族、反证、残余风险）、`novelty-claim-matrix.json`（schema 1.1）、`topic-decision.md`、`selected_direction_cloud_feasibility` | 一个贯穿六篇的博士总问题；A 与 B 同题且 B 独立成立；「未找到」≠「新颖」；检索饱和/空缺口/两轮零新作不得编造；**最终 G1 必须有 owner 的实际博士选题决定**；探索期允许 `in_progress` / `exploring` / `reopened` |
| **G2** | `paper-architecture` | `program/paper-map.json`（`independence_basis: cumulative`，每篇一条 `cumulative_contributions` 行）、P01–P06 六份 `paper-contract`、每篇 `research-identity.json`、`journal-screening.json`、来源绑定的 venue 候选与 scope/article-type/audience 契合证据、fallback venue、依赖图 | 每篇独立可证伪主张、独立充分的一手证据、独立成篇价值；禁止 salami slicing；**每篇 G2 需人工选题决定**；G2 后按「P01 的 G3→G4→G5，再 P02 的 G3→G4→G5」逐篇推进；不得要求 G2 阶段就凑齐六篇实验/结果 |
| **G3** | `experiment-design` | `experiments/papers/Pxx/plan.json`、`budget.json`（`hard_ceiling_usd`）、`datasets.jsonl`、每篇 `design` 文件、`power-analysis.json`（pinned statsmodels 或 ≥1000 次 Monte Carlo + 两次控制平面重跑）、`preregistration.json`、baseline/clean-room 复现计划、`experiment-evidence-plan.json` | 来源/版本/隐私/已知访问控制、当前数据哈希、**原始累计项目总额**、冻结协议、独立科学批评、原生 `experiment_runner.py`；确认性实证需 ≥3 seeds、基线/消融/泄漏/多重性/效应量/区间/负对照/外部效度；`research_phase: exploratory` 必须显式声明且**不能充当 G5 证据**；不得编造数据、功效或基线 |
| **G4** | `experiment-execution` | `experiments/registry.jsonl`（含失败运行）、不可变配置/代码 commit/环境摘要/种子、`claims/claim-evidence.csv`、`reports/reproducibility.md`、`baseline-reproduction.json`、`clean-room-reproduction.json`、受保护的 `reproduction-confirmation.json` | 只能执行「G3 封存的精确计划」，输出哈希、失败留痕、累积成本记账；探索性 G4 归档后**退回 G3**；确认性需 disjoint 隔离重放与数值容差；确定性检查不认证科学意义 |
| **G5** | `writing-and-review` | 当前稿件/图表/表/补充材料、完整注册结果与统计映射、`panel-inputs.json`（三份互盲、不同家族来源视图）、B 类 venue/article-type/template/export/reporting 检查、`submission_checks_sha256` 绑定未变快照 | A 类（来源/事实/引用/数值/主张完整性）失败阻断；C 类（风格/分数/版式/审读行政）只是警告；**无 Q1/Q2/IF 门槛、无 AI 政策关卡、无自动人工签名**；只产出本地 `manual-upload.zip` 供人工投稿；「**A deterministic local ZIP is preparation, never actual publisher submission**」 |

**`config/stages.json` 的 `quality_policy` 硬编码值**（务必与文档对照读）：

| 字段 | 值 |
|---|---|
| `score_scale` / `minimum_dimension_score` / `minimum_overall_score` | `0-10` / `8` / `8.5` |
| `novelty_evidence_minimum` | `5` |
| `minimum_publication_level` / `preferred_publication_level` / `impact_factor_floor` | `JCR Q2 SCI/SCIE` / `≥3 of 6 Q1，其余 ≥Q2` / `>1.0` |
| `human_review_required` | `false` |
| `human_review_gates` | `["G1","G2"]` |
| `acceptance_guarantee` | `false` |

但同一文件的 `quality_policy.note` 明确写道：
> "Existing score and Q1/Q2/IF values are **legacy planning observations, not clearance thresholds** ... No software guarantees scientific validity, acceptance or admission."

即**阈值仍留在配置里，却被文档自身降级为 C 类观察**——详见 §5.2。

### 1.3 人工 / 自动决策边界与角色隔离

- **人工只管两处**：G1 博士选题、G2 每篇选题（`AGENTS.md` rule 5/24、`config/stages.json` `human_review_gates`、`docs/OWNER-DECISION-2026-11-09-EFFECT-FIRST.md` 的 retained 表）。G3/G4/G5 用「证据绑定的自动记录」，且「Never label an automated decision as human」（`references/workflow.md`）。
- **绝不自动投稿**：`AGENTS.md` rule 11、`docs/PUBLICATION-DISCLOSURE.md`、`docs/V1-COMPLETE.md` 末行、`config/defaults.json` `integrity.automatic_submission = false`、`references/stage-contracts.md` G5 段，五处一致。
- **角色隔离**：`CLAUDE.md` + `AGENTS.md` rule 10/17/18 + `config/defaults.json` `integrity` + `config/model-routing.json` `quality_policy`：Claude/Anthropic 仅只读语义规划与独立批评，**不得写任何持久科研产物**；Codex/OpenAI 写入与修复；最终图表必须由本地确定性渲染器从已登记数据生成；作者与独立批评者必须不同模型家族；`claude_persistent_outputs_allowed = false`、`claude_persistent_artifacts_allowed = false`。
- **证据链纪律**（`references/research-integrity.md`、`AGENTS.md` rule 1/2/9）：不捏造引用/数据/结果/评审/期刊指标/投稿状态；主张在绑定 `claim-evidence` 前皆为暂定；失败与不利结果单独归档且不得隐藏；来源 URL + 访问日期 + SHA-256；未知保持未知。

### 1.4 需求追踪表：哪些已实现 / 待验收

`config/requirements-traceability.json`（v2.0，`updated_at: 2026-11-08`，`execution_mode: cloud_only`）：

- **45 条需求 R01–R45**，`implementation` 字段取值：
  - **`implemented`**：绝大多数（R01、R03–R16、R18–R23、R25–R43、R45）。但**几乎每一条的 `remaining` 都写着**「Run the bound tests on the exact merged commit; validate with actual project evidence before claiming completion」——即「已实现」= 软件代码路径存在，**不等于**真实科研验收。
  - **`not-started`**：**R24「Six actual submission-ready doctoral-quality papers」**，evidence 仅为 `projects/.gitkeep` + `references/doctoral-q1-readiness.md`。
  - **`partial`**：**R44「Empirical claim-label agreement target of 0.85 and 20–30 real public review anchors」**，`remaining` 记载 CodeKey Opus #134/#142/#146 返回空文本、试验未完成。
  - **`optional`**：R02（用户机器包/缓存固定到 D 盘）、R17（Zotero Local API / Obsidian），注明「Legacy local functionality is outside the cloud-only project」。
  - 值得单独点名：R27「CNY 300 cumulative boundaries」标 `implemented`，但 `remaining` 写「Actual gateway acceptance is blocked on configured credentials/rates; ambiguous charges require reconciliation」；R32/R33 的 `remaining` 明确「Historical synthetic owner-boundary receipt is retained at its original commit/scope. Revalidate current G1/G2…」，即**历史合成回执不代表当前能力**。
- **`owner_checklist`（156 项，来自 `docs/acceptance/eight-aspects-2026-11-07.csv`）**：
  - `status_counts`：`research-evidence-missing 60`、`software-verified 56`、`partially-implemented 8`、`historical-source-missing 10`、`not-achieved 5`、`optional-alternative 17`
  - **`all_156_requirements_fulfilled = false`**、**`fully_satisfied_count = 53`**、`last_reviewed_at = 2026-11-08`
  - CSV 实测 156 行：`fully_satisfied` = true 53 / false 103；`software_status` = `software-verified 126` / `software-gap 10` / `partially-implemented 3` / `optional-alternative 17`；`actual_research_status` = `research-evidence-missing 81` / `not-applicable 63` / `historical-source-missing 11` / `verified-source-corpus-only 1`
  - 八方面分组：①不足与批评 26、②代码流程精简 22、③科学判定层与量化指标 13、④22 项正向能力 22、⑤三模型面板 15、⑥十项目精读 25、⑦必须保留的底线 21、⑧自我批评与资料缺口 12

**结论**：软件能力自评大体完成（126/156 `software-verified`），但真实科研证据 81 项缺失、5 项数量目标未达；系统自己明确否认 156 条全部满足，并要求把「已测量」与「已达成数值目标」分开。

### 1.5 预算 / 费用契约

| 来源 | 值 |
|---|---|
| `config/defaults.json` | `model_budget.project_hard_limit = 300.0 CNY`、`compute.default_cloud_budget_usd = 100`、`hard_budget_gate = "G3"` |
| `docs/TOTAL-COST-POLICY.md` | 「The default model project total remains CNY 300; a configured total may be changed to an explicit amount」；取消 per-paper 硬上限、per-call 许可、固定分档、人工对账关卡；未知费用按保守上界标注为 estimated |
| `projects/my-phd/state/model-spend-control.json` | `authorized_ceiling_cny = 500`（2026-10-23 由 300 修订）、`tranche_cny = 300`（遗留字段仍在）、`spent_cny = 0.0` |
| `intake/constraints.json` | `model_api_budget_cny = 500`、`cloud_compute_budget_usd = 0`、`cash_budget_usd = null` |
| `config/model-pricing.json` | 30 条 quotes，CNY/百万 token，覆盖 cheapai-*/codekey-* 多个网关 |
| 历史试验 | `luna-auxiliary-selection-20261019.json`：`all_trials_gateway_verified_debit_cny = 0.11601088`；`luna-supplement-20261019.json`：`original_committed_cny = 0.11246048`；`docs/writing-comparison-results-20261028.json`：`settled_cost_cny = 0.0873256` |

---

## 2. 真实项目状态（最关键）

### 2.1 状态主文件 `projects/my-phd/state/run.json`

| 字段 | 实测值 |
|---|---|
| `project` / `created_at` / `updated_at` | `my-phd` / `2026-09-28` / **`2026-10-23T18:19:38+00:00`** |
| **`stage_index` / `stage` / `gate` / `status`** | **`1` / `topic-intelligence` / `G1` / `awaiting_work`** |
| `active_paper` / `paper_count` | `P01` / `6` |
| `paper_statuses` | `P01: active`，`P02–P06: planned` |
| **`approved_gates`** | **`["G0"]`** |
| `approvals` | 两条，**都是 G0**：①2026-09-30 初始确认；②2026-10-23 `operating_constraints_amendment` |
| 修订②的 `note` | 「…将累计模型 API 上限改为 500 元、目标投稿就绪日期改为 2026-10-26；**保留历史费用、待结算隔离、单篇限制和 G1-G5 人工审批，不启动付费研究**」；`scientific_approval_granted = false` |
| `history` 最后一条 | `owner_operating_constraints_amended`，`new_ceiling_cny: 500`，`target_submission_ready_date: "2026-10-26"`，`paid_calls: 0` |

**直接结论：项目停在 G1（选题情报）阶段、`awaiting_work` 待办状态；只有 G0 被批准；G1、G2 均无任何人工批准记录。** 目标投稿就绪日期 2026-10-26 已过（今天 2026-11-09），`run.json` 未再更新。

佐证：
- `state/human-confirmation-20261001.json`：`not_approved = ["unseen G1-G5 dossiers", "future budget tranches", "automatic submission"]`，`paid_model_call_made = false`。
- `intake/continuation-dossier.md`：原始确认语「我确认，改成每天24小时不停，直到满足论文要求」只覆盖已呈现的 G0，**不预批准尚未形成的 G1–G5 结果**；并记载「当时所有被检查的提供商密钥、网关地址、模型标识和价格均未配置」。
- `docs/CODEBASE-AUDIT-2026-11-07.md:107`：「只读核验 `cloud-state/my-phd` 的真实记录仍为 G1 `awaiting_work`，只有 G0 已批准，未形成候选短名单或完成的真实论文；24 篇公开锚集的模型预测仍为零。」同文件 :132「真实研究仍在 G1；未运行真实模型校准、人工抽检或完整论文，不能称 156 条全部完成。」
- `docs/CODE-READINESS-AUDIT-2026-10-01.md`：表格「当前关卡 | G0 已批准；G1 `topic-intelligence`，状态 `awaiting_work`；P01 active，P02–P06 planned」。

### 2.2 系统自己的验收自证（决定性证据）

`docs/acceptance/cloud-validation-2026-11-08.json`（1155 行，2026-11-08 最新验收）中的 `native_research_completion` 字段，是系统对自身真实状态最权威的陈述：

```json
{
  "stage": "topic-intelligence",
  "gate": "G1",
  "approved_gates": ["G0"],
  "completed_real_papers": 0,
  "actual_native_scientific_artifacts_from_failed_trials": 0,
  "native_public_review_predictions": 0,
  "calibration_status": "NOT_CALIBRATED",
  "remaining_dependencies": [
    "A concrete owner-approved G1 topic and subsequent G2 decisions",
    "A working native writer and independent critic",
    "Actual experiments, long manuscript, human claim labels and scientific validation"
  ]
}
```

同一文件其余关键字段：

| 字段 | 值 |
|---|---|
| `status` | **`partial_failed_not_calibrated`** |
| `scientific_completion_verified` / `numeric_score_calibration_verified` / `three_view_panel_effectiveness_verified` | 全部 **`false`** |
| `human_claim_sample_agreement` / `should_merge_detection` | **`null`** / **`null`** |
| `all_156_requirements_fulfilled` | **`false`** |
| `current_session_blind_pilot.exact_agreement` | **0.375**（目标 0.85），`reported_api_model = null`，`project_gateway_calls = 0` |
| `next_native_G1_roster_validation` | `status = partial_failed_no_retry`、`actual_calls = 1`、**`writer_called = false`**、**`critic_called = false`**、`topic_approval_granted = false`、`actual_fee_cny = 0.440235` |
| `g1_native_validation_attempts[0]` | `status = "native_cycle_returned_without_topic_approval"`、`control_only = true`、**`model_calls = 0`**、`model_fee_cny = 0` |
| `production_readiness` | **`model_generation_calls = 0`**、`cheapai_gpt_pro_and_discount = "HTTP 401; deferred by owner"`、`deepseek_requested_model = "deepseek-v4.1-flash"` 但 `deepseek_advertised_models = ["deepseek-v4-pro"]` → **`deepseek_requested_model_available = false`**、`catalog_proves_actual_model_quality = false`、`configuration_preflight_is_live_readiness = false` |

其它验收记录同样自我否定（**全部 `status = passed` 但 scope 明确是合成/软件验收**）：

| 文件 | 关键否定字段 |
|---|---|
| `cloud-human-controls-2026-10-02.json` | `scope = "synthetic cloud software controls only"`、`scientific_completion_verified = false`、`remaining` 写明「No actual my-p…」 |
| `cloud-pipeline-2026-10-02.json` | **`synthetic_acceptance_only = true`** |
| `experiment-evidence-2026-10-03.json` | `real_paid_model_calls = 0`、`experiment_acceptance.synthetic_acceptance_only = true`、`scope = "…synthetic statistical evidence only"` |
| `gateway-startup-2026-10-02.json` | `real_paid_calls = 0`、**`provider_authentication_verified = false`**、`scope = "…HTTP model responses and discovery are simulated"`、`remaining` 写明「Real authentication, availability and billing remain unverified」 |
| `elife-public-anchors-2026-11-07.json` | `status = passed` 但 `calibration_status = NOT_CALIBRATED`、`human_claim_sample_agreement = null` |
| `docs/audits/2026-10-01/offline-reproductions.json` | `scope = "…offline fixtures only"`、`real_network_requests = 0`、`real_paid_calls = 0`、`real_research_state_modified = false` |
| `reports/cloud-preflight-20261001.json` / `cloud-status-20261001.json` | `record_type = "read-only cloud receipt copy; no scientific gate or paid approval"`；`observed.configured` 中 `UUAPI_API_KEY`、`UUAPI_BASE_URL`、`UUAPI_ANTHROPIC_MODEL`、`UUAPI_OPENAI_MODEL`、`DR_OS_MODEL_PRICING_JSON` **全部 `false`**；`allow_paid = false` |

### 2.3 论文：6 份全是空模板

`projects/my-phd/papers/P01`–`P06` 各只有 3 个文件。6 份 `paper-contract.json`（各 39 行）除 `paper_id` 外内容完全一致，均为空模板（以 P01 为例）：

```json
{
  "schema_version": "2.0", "paper_id": "P01", "writing_language": "en",
  "target_jcr_quartile": "Q1",
  "working_title": "", "research_question": "", "distinct_contribution": "",
  "relationship_to_core": "", "relationship_to_extension": "",
  "originality_boundary": {"novel_elements": [], "reused_elements": [], "closest_prior_work_ids": [], "differentiation": "", "claim_limitations": ""},
  "hypotheses": [], "datasets": [],
  "planned_experiments": {"design_ids": [], "baseline_classes": [], "ablations": [], "primary_evaluation": "", "statistical_plan": "", "external_validity_plan": "", "reproducibility_plan": ""},
  "falsification_conditions": [], "dependencies": [],
  "independence": {"unique_claim_ids": [], "shared_assets": [], "overlap_with_other_papers": [], "why_not_merge": ""},
  "target_venues": [], "status": "draft"
}
```

- **唯一非空实质值**是硬编码的 `target_jcr_quartile: "Q1"`；其余全部为空串 / 空数组 / `draft`。
- 每篇 `reviews/citation-claims.jsonl` **均为 0 行**；每篇 `reviews/response-matrix.csv` **只有表头 1 行**；`claims/claim-evidence.csv` **只有表头 1 行**。
- **没有任何论文正文、结果、图表、引用、评审记录、投稿材料包**。
- `papers/P01/venue.json`：`selection_status = "trial"`、`trial_only = true`、`selected_at` 与项目创建同刻（2026-09-28）；整个 `venues/` 只有 `ijssd/venue.json` 一个期刊，且其 `jcr.evidence_status = "publisher-reported"`、`direct_clarivate_recheck_required = true`、`reverification.required_at_gate = "G5"`。

### 2.4 实验 / 数据 / 证据链：全空或仅表头

| 文件 | 状态 |
|---|---|
| `experiments/registry.jsonl` | **0 行**（无任何实验运行、成功或失败记录） |
| `data/datasets.jsonl` | **0 行**（无任何数据集） |
| `evidence/ai4science-ledger.jsonl` | **0 行** |
| `papers/P0x/reviews/citation-claims.jsonl`（×6） | **0 行** |
| `papers/P0x/reviews/response-matrix.csv`（×6） | 仅表头 |
| `claims/claim-evidence.csv` | 仅表头 `claim_id,paper_id,claim,evidence_ids,analysis_ids,support,uncertainty,status` |
| `state/cloud-checkpoint.json` | `archive_sha256 = null`、`files = []` |
| `state/cloud-recovery.json` | `events = []`、`alerts = {}` |
| `evidence/literature/raw/20261026t070945z-openalex-057231e0c8.json` | 0 行（失败回执保留，符合「失败留痕」） |

### 2.5 G1 阶段真实做过的唯一实质工作：免费公开文献检索

这是全场唯一有真实数据产出的环节，且**完全不涉及付费模型生成或实验**：

- `evidence/search-log.jsonl` **48 行**、`evidence/literature-api-ledger.jsonl` **57 行**（含失败回执，如 arXiv 请求失败、Crossref 超时、OpenAlex 非 JSON 响应均保留）。
- `reports/g1-broad-search-audit.md`：2026-10-26 扩大检索，18 组英文技术查询 + 7 组补充；**25 组 OpenAlex + 2 组 Crossref 共 27 组成功回执**，返回 2,497 条记录，保守去重得 **2,158 个键**（`evidence/literature/g1-broad-index.jsonl`，2158 行）；政策排除 MDPI（`10.3390/`）与来源不符项后得 **757 行待读队列**（`g1-machine-reading-queue.jsonl` 758 行含 1 行表头）。
- 2026-11-05 又执行 12 组 OpenAlex 补检（`reports/g1-research-20261105.md`），`output-provenance.json` 记录 23 个 `literature-metadata-acquisition` 文件的 SHA-256。
- `evidence/direction-sources/` 抓取了 EURAXESS 博士岗位页等 8 个来源（HTTP 200、raw/html 与 txt 双份、SHA-256 绑定，`index.json` 记录 status=`retrieved`）。
- 大量 `evidence/literature/raw/` + `normalized/` 成对回执均标注 `"No API key, so this request shares one free daily budget ($0.10) with everyone on your network's IP"`，**是免费公开 API**。

**但人工筛选从未发生**：`reports/g1-human-screening-sheet.csv` 757 行的 4 个命名字段 `human_decision` / `human_reason` / `screened_by` / `screened_at` **全部为空（757/757）**；`g1-assisted-screening-proposals.jsonl`（757 行）与 `g1-assisted-all-index-proposals.jsonl`（2158 行）里 `human_decision` 全为 `null`。`g1-screening-instructions.md` 明确要求「a real reviewer should fill… never an AI agent posing as a person」。

**G1 程序产物全部是「待审建议稿」，无一是批准态**：

| 文件 | 状态 | 关键信号 |
|---|---|---|
| `program/topic-shortlist.json` | `ready_for_review`，`human_review_required: true` | 3 候选，预选 `D1-sim-to-real-policy-ranking` |
| `program/direction-ranking.json` | **`ready_for_human_review`** | 七项权重（0.25/0.25/0.15/0.075/0.075/0.1/0.1），3 候选，`errors: []` |
| `program/hypothesis-register.json` | — | 3 条假设 |
| `program/hypothesis-audit.json` | `pass: true` 但 **`scientific_validation: false`、`novelty_granted: false`、`human_review_required: true`** | 确定性审计通过 ≠ 科学性 |
| `program/novelty-claim-matrix.json` | `ready_for_review` | 5 条 claim，`search_saturation` 标记 `backward/forward_chaining_complete: true`，仍 `human_review_required: true` |
| `program/originality-audit.json` | `ready_for_review` | 11 条 closest prior work、5 条 novelty claim、2 条专利检索 |
| `program/core-thesis.json` / `extension-thesis.json` | 均 `ready_for_review` | 有具体的博士问题文本（仿真到真实策略排序 / 保形部署弃权） |
| `program/topic-decision.md` | 建议稿 | 自述「建议稿，待负责人确认」 |

多份 G1 报告自述「**不含任何闸门批准，未写入 GitHub**」（`g1-local-progress-20261028.md`、`g1-research-20261105.md`、`g1-local-preflight.md`）；`g1-research-20261105.md` 还说明 `projects/my-phd/` 因 `.gitignore:62` 未被云端触及——即这些 G1 成果是**本地写入、未同步进云端正式状态**（这也解释了 §5.2 中 CODEBASE-AUDIT「未形成候选短名单」的措辞差异）。

### 2.6 累计费用：口径互相矛盾，但都在「几元」量级

| 来源 | 说法 |
|---|---|
| `state/model-spend-control.json` | **`spent_cny = 0.0`**、`paper_spent_cny = {}`、`reservations = {}`、`reconciliation_events = []`、`authorized_ceiling_cny = 500` |
| `state/continuation-status.json` | `spent_cny = 0.0`、`remaining_cny = 500.0`、**`should_run = false`**、`reason = "production_configured_automatic_research_not_started"` |
| `state/human-confirmation-20261001.json` | `paid_model_call_made = false` |
| `docs/acceptance/cloud-validation-2026-11-08.json` `budget` | `spent_before_cny = 0.24538256` → **`spent_after_cny = 3.88897004`**，`attempts_since_initial_spent_cny = 3.64358748`，`existing_unknown_holds_cny = 10.0783494`，`total_reserved_cny = 10.0783494`，`remaining_after_spent_and_reservations_cny = 486.03268056`，`new_spending_authority_granted = false` |
| `docs/writing-comparison-results-20261028.json` | `settled_cost_cny = 0.0873256`、`retained_old_reservation_cny = 9.5836104`、`remaining_cny = 490.329064`、`status = closed_with_argon_quality_unverified` |
| `config/luna-auxiliary-selection-20261019.json` | `all_trials_gateway_verified_debit_cny = 0.11601088`、`all_trials_committed_upper_cny_including_unknown_reservation = 0.21601088` |

**判定**：项目控制账本记「0 花费、0 付费调用」，而验收/试验记录记「已花约 3.89 元、另有约 10.08 元未核销预留、单次 G1 传输验证花费 0.44 元」。两者口径不一致（前者可能是正式科研账本，后者含工程验证与历史试验）。**无论按哪个口径，累计真实费用都在几元到十几元量级，远低于 500 元上限，且没有任何一次成功的完整付费科研周期**。

### 2.7 「24 小时不停」的自动云研究从未启动

- `state/continuation.json`：`enabled = true`、`system_execution_hours_per_day = 24`、`resume_interval_minutes = 15`、`stop_when = "all_papers_submission_ready"`，绑定 G0 工件哈希。
- **但** `state/continuation-status.json`：`should_run = false`、`reason = "production_configured_automatic_research_not_started"`、`spent_cny = 0.0`。
- `production_readiness.model_generation_calls = 0`；`g1_native_validation_attempts[0].model_calls = 0`；`next_native_G1_roster_validation` 只实际调用 1 次且 writer/critic 均未调用、状态 `partial_failed_no_retry`。
- `state/output-provenance.json` 共 34 个文件：`family` = `other` 31 / `openai` 3；`model` 分布为 `scripts/literature_evidence.py` 23、`Codex session (GPT-6 family; exact API m…)` 3、`scripts/operating_constraints.py` 5、`Python 3; no model API call` 3；`role` 以 `literature-metadata-acquisition` 23 为主——**全部是元数据检索与 intake 文本，没有一件科学产物**。
- `integrations/third-party-runtime.json` 的 `tools` 为**空数组（0 条）**：2026-11-09 owner 已授权自由接入第三方运行时，但注册表为空，`.workbuddy/memory/2026-11-09.md` 明确设计原则是「**授权 ≠ 已部署**」。

### 2.8 本节结论（最关键的落差）

> **这套系统实际跑到了「G1 选题情报的公开文献检索与本地建议稿生成」，然后就停住了。**
> 状态机停在 `G1 / awaiting_work`，`approved_gates = ["G0"]`；G1/G2 从未人工批准；6 篇论文是 6 份 `status: draft` 的空模板；0 次注册实验、0 个数据集、0 条 claim-evidence 绑定、0 行人工筛选、0 篇完成论文、0 次成功的付费模型科研周期；累计费用约几元且账本口径打架；自动研究循环配置好了但 `should_run = false`。
> 系统自己在最新验收记录里写下 `completed_real_papers: 0`、`calibration_status: NOT_CALIBRATED`、`scientific_completion_verified: false`——**这不是外部质疑，是仓库自证**。
> 与之相对，软件控制平面、69 个 schema、16 个 CI 工作流、46 个技能入口、25 份配置、101 份文档与需求追踪表确实非常完备：**「能做什么」的脚手架做完了，「做出来了什么」几乎为零**。

---

## 3. CI 与云入口

### 3.1 16 个工作流全表（`.github/workflows/*.yml` + 1 个 composite action）

| 工作流 | 触发条件 | 性质 | 是否真跑 |
|---|---|---|---|
| **`validate.yml`**（407 行，14 个 job） | `pull_request`、`push(main)`、`workflow_dispatch`、`schedule("17 3 * * 1"` 每周一 3:17)、`workflow_call`（被修复验收复用） | 主验证入口 | **真跑**（每次 push/PR + 每周） |
| `research-continuation.yml`（111 行） | **`schedule("7,22,37,52 * * * *")` 每 15 分钟**、`workflow_dispatch`（`mode: check/start`，默认 `check`） | 持续云研究主循环 | 定时器真跑，但 `if: github.repository == 'hengyizang/lunwen'` + `vars.DR_OS_AUTOMATIC_RESEARCH_ENABLED` + `continuation-status.should_run=false`；默认 `check` 不产生模型调用 |
| `cloud-research.yml`（141 行） | **`issues: [opened]`** | **核心人工云作业入口**：通过新建 GitHub Issue 提交 `cloud-job` 动作 | 需人工建 issue；作业步骤含 `python -m scripts.literaturectl install`、`ccfa_runtime install`、13 个 `run`、多组 `vars`/`secrets` 条件 |
| `cloud-recovery.yml`（61 行） | `workflow_run`（依赖 3 个云工作流 completed）、`schedule("4,19,34,49 * * * *")`、`workflow_dispatch`（`mode: inspect/recover/probe`） | 自动恢复 | 定时真跑（恢复控制器） |
| `cloud-repair-validation.yml`（47 行） | **仅 `workflow_dispatch`**（`repair_ref` 必填） | 修复 PR 校验，复用 `validate.yml` | 人工触发 |
| `production-readiness.yml`（54 行） | `push(main, codex/relay-acceptance-20261019)`、`workflow_dispatch` | 生产就绪检查（含 4 个付费网关 secrets） | 自动 + 人工 |
| `codex-cloud.yml`（76 行） | `push`/`pull_request`（限定 paths）、`workflow_dispatch` | Codex Cloud 引导（`linux-bootstrap`） | 自动 + 人工 |
| `ccfa-skills.yml`（60 行） | `pull_request`、`push(main)`、`workflow_dispatch` | CCFA 17 技能验收 | 自动 |
| `completeness-repairs.yml`（32 行） | `pull_request`、`push(main)`、`workflow_dispatch` | `test_tex_sources` 等 | 自动 |
| `figure-reference-workbench.yml`（75 行） | `pull_request`/`push(main)`（figure 相关 paths）、`workflow_dispatch` | 图件工作台验收 | 自动（路径触发） |
| `literature-completion.yml`（55 行） | `pull_request`（限定 paths）、`workflow_dispatch` | 文献补全验收 | 自动（路径触发） |
| `literature-evidence.yml`（89 行） | `pull_request`（限定 paths）、`workflow_dispatch` | `public-review-anchors` + `source-evidence` | 自动（路径触发） |
| `literature-workbench.yml`（79 行） | `pull_request`/`push(main)`（限定 paths）、`workflow_dispatch` | 文献工作台（含 `third_party/evil-read-arxiv`） | 自动（路径触发） |
| `research-automation-toolkit.yml`（134 行） | `pull_request`（限定 paths） | 10 个研究自动化工具 + Windows 安装器语法 | 自动（路径触发） |
| `research-task-scenarios.yml`（63 行） | `pull_request`（限定 paths）、`workflow_dispatch` | 7 类研究任务契约（含 mermaid） | 自动（路径触发） |
| `.github/actions/setup-runtime/action.yml`（36 行） | 被各 job 复用 | composite：`setup-python@v7` + `actions/cache@v4` + `python -m scripts.ccfa_runtime bootstrap` + 按 JSON 参数 `pip install` | 随调用 |

### 3.2 `validate.yml` 的 14 个 job 与「真跑」的真实性分层

`docs/CI-VALIDATION.md` 明确分两层：**确定性检查**（每次 push/PR）与**真实外部验收**（每周 / 手动 / 提交信息含 `[live-acceptance]`）。14 个 job 名为：
`fast-tests`、`study-routes`、`statistical-watermark-cpu`、`cloud-produce`、`cloud-restore`、`cloud-human-controls`、`experiment-evidence`、`gateway-startup`、`cloud-recovery`、`deterministic`、`windows-script-syntax`、`live-literature`、`adapter-packages`、`container-isolation`。

步骤名本身就标注了合成性质，例如：
- `cloud-produce`：「Execute **synthetic** negative and failed runs with the real Docker executor」
- `experiment-evidence`：「Execute **synthetic** paired studies and failed pilot with the real Docker executor」
- `gateway-startup`：「Exercise production routing and durable budgets with **synthetic HTTP**」「…**without model credentials**」
- `cloud-recovery`：「Inject engineering faults **without paid calls or production state**」
- `cloud-human-controls`：「Exercise actual human control functions on **synthetic evidence**」
- `study-routes`：「Run actual isolated Meta calculations and Lean kernel checks」（这一项是真实计算）
- `live-literature`：「Exercise credential-free providers and configured keyed providers」（**真调公开 API**，只在 schedule/dispatch/`[live-acceptance]` 触发）
- `container-isolation`：「Run digest-pinned no-network read-only container」（**真 Docker**）
- `adapter-packages`：「真实安装 PaperQA2 / ToolUniverse / ref-verify 固定版本」，但「不执行付费 PaperQA 问答」

即：**CI 控制器与软件验收确实在 GitHub Actions 上真跑**（`cloud-validation-2026-11-08.json` 保留了真实 run URL，如 `actions/runs/42461197332`、`42457860489`、`42475094823`，以及 artifact_id），但跑的是**单元测试、合成夹具、Docker 隔离、公开元数据 API、包身份校验**，不是付费模型科研与真实实验。

### 3.3 云端作业入口与凭据边界

- **人工入口**：`cloud-research.yml` 由 `issues: opened` 触发，即 owner 通过新建 Issue 提交云作业；动作集合由 `schemas/cloud-job.schema.json` 定义（`action` 枚举含 `accept_route`、`acceptance`、`advance`、`amend_operating_constraints`、`approve` 等，`stage` 枚举含 6 阶段，`settings` 含 fast/…）。`references/cloud-operations.md`（225 行）定义请求格式。
- **定时入口**：`research-continuation.yml` 每 15 分钟 + `cloud-recovery.yml` 每 15 分钟（错开 3 分钟）+ `validate.yml` 每周一。
- **变量/机密**：`vars.DR_OS_AUTOMATIC_RESEARCH_ENABLED`、`DR_OS_DYNAMIC_ROUTING`（默认 `production`）、`DR_OS_TEX_IMAGE`、`DR_OS_ENABLE_WATERMARK_DETECTOR`；`secrets` 含 `DR_OS_CHEAPAI_KIRO_DISCOUNT_KEY`、`DR_OS_CHEAPAI_CCMAX_KEY`、`DR_OS_CODEKEY_CODEX_PRO_KEY`、`DR_OS_CODEKEY_CODEX_DISCOUNT_KEY`；`validate.yml` 另用 `SEMANTIC_SCHOLAR_API_KEY`、`OPENALEX_API_KEY`、`SERPAPI_API_KEY`、`OPENCITATIONS_ACCESS_TOKEN`。
- 所有含付费/科研语义的作业都带 `if: github.repository == 'hengyizang/lunwen'`，即 fork 上不会真跑。
- `.mcp.json` 定义两个 stdio MCP server：`doctoral-research-os`（`scripts/research_mcp.py`）与 `codex-review`（`codex mcp-server`）；`CLAUDE.md` 指定技能入口 `/doctoral-research-os:start` 与 `/continue`。
- **WSL2 本机验收无法由 CI 代替**：`docs/CI-VALIDATION.md` 明确「GitHub runner 的容器 job 证明 Linux/Docker 路径；它不能冒充 WSL2」，须人工按 `docs/LIVE-ACCEPTANCE.md` 执行且报告 `environment.is_wsl2 = true`。

### 3.4 本节结论

**真跑**：16 个工作流中的绝大多数在 push/PR/定时上自动执行（软件回归、合成夹具、Docker 隔离、公开文献 API、包身份校验）；`cloud-research.yml` 与 `cloud-repair-validation.yml`、`research-continuation.yml` 的 `mode: start` 需人工触发；凭据与 `DR_OS_AUTOMATIC_RESEARCH_ENABLED` 未就绪 + `should_run=false` 使得**付费科研循环从未真正启动**。

---

## 4. schema 地图（69 个数据契约）

69 个 `*.schema.json` 覆盖「立项 → 选题 → 架构 → 设计 → 执行 → 写作/投稿准备 → 云作业/第三方」全链路。按环节分组（括号内为 `required` 数量或特征）：

**① 质量门与独立审计（8）**
`quality-gate`（gate 枚举 G1–G5、status `ready_for_review`/`approved`、schema 1.1/1.2）、`codex-audit` / `model-audit`（verdict `block`/`revise`/`pass-with-conditions`）、`academic-style-audit`、`ai4science-evidence-receipt`（tool 枚举 `tooluniverse`/`paperqa2`/`kdense-scientific-agent-skills`）、`science-evidence`、`sciencepro-import`、`api-artifact-bundle`。

**② G0 立项与来源/权利（9）**
`intake-constraints`（status `needs_user_input`/`ready_for_review`、execution_mode `cloud_only`/`hybrid`/`local`、human_review_mode `weekly_hours`/`on_request`）、`research-identity`（research_kind `unassigned`/`primary`/`secondary_quantitative`）、`venue-candidates`、`venue-manifest`、`jcr-verification`（quartile Q1–Q4、indexing SCI/SCIE）、`data-contract`、`dataset-manifest`、`dataset-discovery`、`economic-data-request`（provider `fred`/`worldbank`）。

**③ G1 选题 / 新颖性 / 文献证据（15）**
`topic-shortlist`、`core-thesis` / `extension-thesis`（status `ready_for_review`/`approved`）、`research-hypotheses`（1298 行，最大之一；status `in_progress`/`ready_for_review`）、`originality-audit`、`novelty-claim-matrix`（schema 1.0/1.1）、`search-record`（16 必填，含数据库/查询族/回执/日期窗）、`literature-evidence-receipt`（mode `live_search`/`citation_graph`/`licensed_local_export`）、`literature-plan`、`literature-feedback`、`closest-work-comparison`、`paper-card`（source_scope `full_text`/`abstract`/`excerpt`/`metadata`）、`open-fulltext-resolution`、`semantic-plan`、`research-diagram`。

**④ G2 论文架构与写作准备（8）**
`paper-map`（`independence_basis: cumulative|legacy_pairwise`）、`paper-contract`（682 行，25 props/21 required；`writing_phase` scientific/submission、`status` draft/ready_for_review/approved/retired、`study_route` empirical/meta_analysis/theory）、`paper-facts`、`paper-map`、`research-case`、`research-increments`、`manual-citation-verifications`、`writing-review-action`、`contribution-reporting`（kind `empirical`/`meta-analysis`/`theoretical`/`qualitative`）。

**⑤ G3 实验设计 / 预注册 / 功效 / 数据质量（15）**
`experiment-plan`（`research_phase: exploratory|confirmatory`）、`experiment-budget`、`experiment-evidence-plan`（506 行）、`empirical-design`、`paper-experiment-design`（606 行，22 必填）、`power-analysis`（`generated_by: statsmodels|simulation_rerun`）、`power-simulation-evidence`、`preregistration`（hash-frozen，`confirmatory_lock`）、`study-protocol`（route `meta_analysis`/`theory`）、`supplemental-experiment-proposal`、`data-quality-report`、`data-quality-confirmation`、`baseline-reproduction`、`clean-room-reproduction`、`reproduction-confirmation`。

**⑥ G4/G5 执行与投稿准备 / 图件（12）**
`cloud-job.schema.json`（**1439 行、44 props**，最大的传输契约；`action`/`stage`/`settings`/human selectors）、`continuation-policy`（10 必填，含 `constraints_sha256`、`g0_approval_artifact_sha256`）、`live-acceptance-report`、`pre-submission-checklist`、`docx-manuscript-metadata`、`publication-figure-spec`、`figure-gallery-request/report`、`figure-provenance`、`figure-story-request/report`、`figure-visual-style`、`editable-figure-request/export`、`research-diagram`。

**⑦ 其它（2）**
`figure-story-*`、`figure-*` 已含；`manual-citation-verifications`（0 required，纯人工记录容器）、`writing-review-action`。

**关键枚举与共性**：
- `schema_version` 多为双版本（`1.0/1.1` 或 `1.1/1.2`），体现契约演进（novelty 矩阵 1.1、quality-gate 1.2）。
- `human_review_required` 是 G0/G1/G2 类 schema 的普遍必填字段；`status` 大量使用 `ready_for_review` / `in_progress`，`approved` 只在少数枚举里出现——**schema 设计本身就预留了「待人工批准」态**。
- `CODEBASE-AUDIT-2026-11-07.md` 记载 schema 67→69 个、递归 `required` 声明 2077→2199。
- **契约定义齐全 ≠ 有实例数据**：69 个 schema 中绝大多数（尤其 G3–G5 的实验设计、预注册、复现、面板、投稿检查类）在 `projects/my-phd/` 里**没有任何对应的实例文件**；实际存在的实例集中在 G1 的选题/假设/检索与 G2 的空 `paper-contract`。

---

## 5. 风险与矛盾

### 5.1 文档中宣称、但配置/状态数据里找不到证据的能力

| 宣称（来源） | 配置/状态实测 |
|---|---|
| 「驱动博士论文 G0–G5 全流程」「六篇投稿就绪论文」（`README.md`、`pyproject.toml` description、`.claude-plugin/plugin.json`） | `run.json` 停在 `G1/awaiting_work`；`approved_gates=["G0"]`；`completed_real_papers=0`；R24 = `not-started`；6 份 `paper-contract` 全 `draft` 空模板 |
| 「真实实验、结果、claim-evidence 证据链、失败留痕」 | `experiments/registry.jsonl`、`data/datasets.jsonl`、`ai4science-ledger.jsonl`、6 份 `citation-claims.jsonl` 全 0 行；`claims/claim-evidence.csv` 仅表头 |
| 「37 类确定性科研绘图 / PaperQA2 / ToolUniverse / Zotero / Obsidian / 真实 DOCX / PRISMA 导出 / 动态模型路由」（`README.md`、`docs/NEW-CAPABILITIES.md`、R01–R23） | 均为软件适配器 + 合成验收；R01–R23 的 `remaining` 几乎都要求「在精确合并提交上跑绑定测试、用真实项目证据验证后才可宣称完成」；项目里无实例文件 |
| 「每天 24 小时不停，直到满足论文要求」（`continuation.json`、G0 确认语） | `continuation-status.should_run=false`、`reason="production_configured_automatic_research_not_started"`、`model_generation_calls=0` |
| 「健康感知分层生产路由 / 已验证科学等价」（`docs/PRODUCTION-MODEL-ROUTING.md`、`config/model-routing.json` profile `production`） | `quality_policy.scientific_equivalence_verified=false`、`automatic_paid_fallback=false`；`luna-auxiliary-selection-20261019.json` `production_routing_activated=false`、`scientific_completion=false`；`production_readiness` 记 cheapai HTTP 401、deepseek 请求型号不可用 |
| 「≥0.85 claim-label 一致率、20–30 真实公开评审锚、三模型盲面板有效性」（R44、`docs/MODEL-EVALUATION-RESULTS-20261029.md`） | `exact_agreement=0.375`；`native_public_review_predictions=0`；`three_view_panel_effectiveness_verified=false`；R44 = `partial` |
| 「真实云验收通过」（多份 `docs/acceptance/*.json` 的 `status=passed`） | 每一份都在 `scope` 里写明 `synthetic` / `software only` / `scientific_completion_verified=false` / `real_paid_calls=0` / `NOT_CALIBRATED`；`cloud-validation-2026-11-08.json` 状态是 `partial_failed_not_calibrated` |
| 「第三方工具自由接入并直接产出研究协作」（2026-11-09 owner decision） | `integrations/third-party-runtime.json` 的 `tools=[]`（0 条注册）；`.workbuddy/memory/2026-11-09.md` 自述「真正跑这些上游仍需自备运行时、模型端点与密钥」 |

### 5.2 相互矛盾的声明

1. **硬编码阈值「配置里还在、文档里已废」**。`config/stages.json` 仍写 `minimum_dimension_score=8`、`minimum_overall_score=8.5`、`novelty_evidence_minimum=5`、`minimum_publication_level="JCR Q2 SCI/SCIE"`、`impact_factor_floor=">1.0"`；`docs/V1-COMPLETE.md` 仍以「Hard floors」列出 8.0/8.5/Q1/Q2/IF>1.0。但同一 `stages.json` 的 `note`、`references/stage-contracts.md`、`AGENTS.md` rule 19、`docs/RESEARCH-CAPABILITIES.md`、`references/doctoral-q1-readiness.md` 及 2026-11-09 owner decision 一致声明这些是 **"legacy planning observations, not clearance thresholds"**、"superseded"、"Neither ranking nor IF blocks scientific gates or packaging"。`docs/V1-COMPLETE.md` 标题下也自标「Historical v1.4 policy, retained for provenance… This document adds no current gate」。→ 读阈值时若不看 note 会得出完全相反的结论。

2. **预算 300 vs 500**。`config/defaults.json`（`project_hard_limit=300`）、`docs/TOTAL-COST-POLICY.md`（"The default model project total remains CNY 300"）、`R27`（"CNY 300 cumulative boundaries"）、`references/stage-contracts.md`（"the model default is CNY 300"）、`intake/continuation-dossier.md`（"首期累计 API 上限 300 元"）对比 `run.json` / `model-spend-control.json` / `continuation-status.json` / `intake/constraints.json` / `config/model-evaluation-20261029.json` / `cloud-validation-2026-11-08.json`（全部 500）。实质是「默认值 vs 2026-10-23 已修订配置」的演进，但**多份文档未同步**；且 `model-spend-control.json` 仍保留 `tranche_cny=300`，与 `TOTAL-COST-POLICY.md`「Remove… fixed tranche increments」冲突（文档解释为「遗留字段可读但不生效」）。

3. **费用 0 vs 数元**。`model-spend-control.spent_cny=0.0`、`paid_model_call_made=false`、`real_paid_calls=0`、`model_generation_calls=0`、`model_calls=0` 对比 `cloud-validation` 的 `spent_after_cny=3.88897004`、`existing_unknown_holds_cny=10.0783494`、`next_native_G1_roster_validation.actual_fee_cny=0.440235`，以及 luna/writing-comparison 的历史扣费。属于**正式科研账本 vs 工程验证/历史试验账本口径不一致**，且没有任何一处做显式对账说明。

4. **人工审批标志不一致**。`config/stages.json` `quality_policy.human_review_required=false` 对比同文件 `human_review_gates=["G1","G2"]`、`config/model-routing.json` `human_gate_approval_required=true`、`AGENTS.md` rule 5/24、`intake/constraints.json` `human_review_required=true`、各 G1 schema 的 `human_review_required=true`。整体布尔是「非每关都要人」，不是「不需要人」，但字面易误读。

5. **G1 是否有候选短名单**。`docs/CODEBASE-AUDIT-2026-11-07.md:107` 说「未形成候选短名单」，而 `program/topic-shortlist.json` 确有 3 个候选。原因是云端 `cloud-state` 快照与 2026-10-28 本地写入未同步（`g1-research-20261105.md` 明说 `projects/my-phd/` 被 `.gitignore` 排除、未写入 GitHub）。两者都指向「未批准」，但措辞冲突，需区分「云端正式状态」与「本地建议稿」。

6. **政策层两套相反规则并存**。早期 `docs/RESEARCH-AUTOMATION-TOOLKIT.md`（`standalone_runtime_deployed: false`）、`integrations/upstreams.lock.json` / `research-automation-tools.json` 的 `enabled_by_default:false` + 强制 pin 完整 commit + 逐文件审查 + 「输出仅 advisory」，被 2026-11-09 三份 owner decision 与 `AGENTS.md` rule 25 大幅放宽（任何工具/运行时、任意顺序、可无 receipt、输出可直入候选证据队列）。owner decision 明确「历史快照字段**故意不改写**」，于是仓库内同时存在两套相反约束，只能靠「最新 dated owner decision 优先」消解。

7. **选题方向与唯一试投期刊不匹配**。G1 预选 `D1-sim-to-real-policy-ranking`（机器人操作策略的仿真到真实排序），核心/拓展命题都是机器人 AI / 保形弃权；而 `venues/ijssd/venue.json`（`International Journal of Structural Stability and Dynamics`）的 `scope.fit_notes` 明确写「**Not a default target for papers whose primary contribution is generic AI, robotics control or manufacturing rather than structural dynamics**」。该 venue 还是 `trial_only=true` / `selection_status=trial`，且 JCR 数据为 `publisher-reported`、要求 G5 通过 Clarivate 复核。

8. **`docs/acceptance/eight-aspects-2026-11-07.csv`（156 项）与 `requirements-traceability.json` 的 `status_counts`（合计 156）一致，但 `CODEBASE-AUDIT` 第 71 行给出的 PR#131/132 主分类（58/60/10/5/5/18）与 CSV 的 `overall_status`（56/60/8/10/5/17）不同**——审计文档自己说明「2026-11-08 的重新判定列于文末」，属版本差异而非错误，但引用时需注明口径。

### 5.3 硬编码阈值与「未来型号」

**硬编码阈值/常量清单**（配置中直接写死、未在运行时由证据推导）：

| 值 | 位置 |
|---|---|
| `8` / `8.5` / `5` 分、Q2 下限、3/6 篇 Q1、IF>1.0 | `config/stages.json` `quality_policy`（已被文档降级为观察值） |
| `paper_count=6`、`minimum_q1_papers=3`、`minimum_impact_factor=1.0` | `config/defaults.json` |
| CNY `300`（默认）/ `500`（当前配置）、USD `100` 云预算、`0` 外部算力、`G3` 硬预算门 | `defaults.json`、`run.json`、`model-spend-control.json` |
| `max_single_download_bytes=5368709120`（5 GiB） | `defaults.json` |
| `max_errors=250`（proselint） | `config/proselint-academic.json` |
| `minimum_paired_cases=6`、`minimum_holdout_cases=3`、`cooldown_seconds=600`、`minimum_cost_improvement=0.1` | `config/model-candidates.json` |
| `max_calls=40`、`max_output_tokens=8192`、`project_ceiling_cny=500`、`retained_legacy_hold_cny=9.5836104` | `config/model-evaluation-20261029.json` |
| `normal_review_hours=24`、`acceptance_review_days=7`、`latency_regression_ratio=1.5`、`cost_regression_ratio=1.25` | `config/task-model-policy.json` |
| `minimum_screen_score=85`、`phases[].budget_ceiling_cny=18/30` | `config/model-comparison-20261020.json` |
| `≥1000` Monte Carlo 模拟、`≥3` stochastic seeds、`≥5` closest works、`≥3` adjacent fields / query families、`0.85` 一致率、`20–30` 评审锚 | `references/stage-contracts.md`、`docs/RESEARCH-QUALITY.md`、R44 |
| `24` h/day、`15` min resume、`90` 天 checkpoint 保留、`14` 天 CI 证据保留、`3600` 秒云作业 deadline | `continuation.json`、`cloud-checkpoint.json`、`docs/CI-VALIDATION.md`、workflows 的 `DR_OS_CLOUD_JOB_DEADLINE_EPOCH` |

**未来/未验证型号**（`config/model-routing.json` 的 7 个 `models` 与 `config/model-candidates.json` 的 102 个候选、`config/model-pricing.json` 的 30 条报价）：

`gpt-6.1-sol`、`gpt-6-astra`、`gpt-5.6-luna`、`gpt-6.1-terra`、`claude-sonnet-5-5`、`claude-opus-5-5`、`deepseek-v4.1-flash`、`gemini-4-argon` / `gemini-4-argon-high`、`kimi-k3.1-pro`，provider 为 `cheapai-*`、`codekey-*` 等第三方中转网关。

- `config/luna-auxiliary-selection-20261019.json` 明写 **`unavailable_dependency: "gpt-6-luna"`**（型号根本不存在，需替换）、`production_routing_activated=false`、`core_scientific_roles_changed=false`、`scientific_completion=false`。
- `cloud-validation-2026-11-08.json` `production_readiness`：`deepseek_requested_model="deepseek-v4.1-flash"` 而 `deepseek_advertised_models=["deepseek-v4-pro"]` → `deepseek_requested_model_available=false`、`different_model_ids_treated_as_aliases=false`；`cheapai_gpt_pro_and_discount="HTTP 401; deferred by owner"`；`catalog_proves_actual_model_quality=false`。
- `config/model-routing.json` `quality_policy`：`scientific_equivalence_verified=false`、`unknown_cost_stops_execution=true`、`automatic_paid_fallback=false`。
- `state/output-provenance.json` 里 3 个 openai 条目的 model 记为「`Codex session (GPT-6 family; exact API m…)`」——**连精确 API 型号都未确定**。

→ 这些型号是「未来/网关别名/未验证」标识，以 `profile: production` 写死在配置里，但从未在真实科研中成功调用（`model_generation_calls=0`）。

### 5.4 许可与第三方边界

| 来源 | 许可 | 边界 |
|---|---|---|
| Academic Research Skills / ARS Codex（Cheng-I Wu） | **CC BY-NC 4.0（非商业）** | `integrations/licenses/ars-cc-by-nc-4.0.txt`（417 行）；`config/pre-submission-criteria.json` 亦带 `license: CC-BY-NC-4.0` 且 `calibration_status: NOT_CALIBRATED`；`references/research-methods/evidence-arguments.md`、`submission-review.md` 为署名改编 |
| K-Dense-AI/scientific-agent-skills | MIT | `third_party/kdense/`，peer-review 为固定 commit 的源文本选段 |
| juliye2025/evil-read-arxiv | MIT（**仅上游 README 声明，该 revision 无单独 LICENSE 文件**） | `THIRD-PARTY-NOTICES.md` 明确「不臆造上游版权、不宣称本声明授予更广权利」 |
| WUBING2023/PaperSpine | MIT | `integrations/licenses/paperspine-mit.txt` |
| Yuan1z0825/nature-skills | Apache 2.0（其中 proposal skill frontmatter 另标 MIT，文档特意声明「不宣称统一许可」） | 两个确定性图件审计器 |
| Top-Conf Figure Gallery | **MIT（仅代码）** | `integrations/topconf-figure-gallery-LICENSE`；`lock.json` 的 `license = "MIT for code only; original paper figures retain their own copyright and licensing"`；`IMAGES_POLICY.md` 声明「非商业、教育与研究用途」、图片版权归原论文作者/出版方、含下架政策 |

**边界风险**：
- **CC BY-NC 4.0 的非商业条款**与「博士论文投稿 / 期刊发表」场景的兼容性需人工确认；`config/pre-submission-criteria.json` 直接以未校准（`NOT_CALIBRATED`）状态引入该署名体系。
- `integrations/third-party-runtime.json` 的 `guardrails` 明确禁止第三方运行时：写 stage state、批准 G0–G5 关卡、在 `scripts/experiment_runner.py` 之外跑注册实验、伪造 provenance、成为稿件持久作者、接触 secrets / 原始数据、**auto-submit manuscripts**。owner decision 同时把接入自由度放到最大（可无 registry、可无 receipt、`--no-receipt`），二者存在张力，靠 guardrails 兜底；注册表当前为 0 条。
- `.gitignore` 把 `projects/**/data/raw|processed|private`、`experiments/runs|archive`、`papers/**/build`、`state/model-usage.jsonl`、`*.zip`、以及 16 组可选第三方技能目录排除在 Git 外。因此「仓库里看不到」不等于「不存在」，但也意味着**证据链的关键部分对版本库不可见**，验收只能依赖 `docs/acceptance/` 的回执副本与哈希。
- `docs/THIRD-PARTY-NOTICES.md` 与 `references/upstream-components.md` 反复强调「不安装完整上游编排系统、上游 web 服务与直连 Anthropic/shell 路径不安装」；而 2026-11-09 新政策允许直接启动上游独立运行时——历史文档与当前政策需以 owner decision 为准重新解读。

### 5.5 结构性观察

- 整个 `docs/` 里 `synthetic`、`not establish`、`no guarantee`、`unknown`、`placeholder`、`scientific completion` 等免责词高频出现（几乎每份能力文档都有），这是系统**诚实**的一面：它把「软件验收」与「科研完成」切得很清楚。副作用是**任何 `status: passed` 都必须连同其 `scope` / `scientific_completion_verified` 字段一起读**，否则会严重高估完成度。
- `README.md` 作为对外门面宣称 v2.3.0「驱动博士论文 G0–G5 全流程、六篇论文」，与 `projects/my-phd` 的真实状态构成全项目最大落差；而 `AGENTS.md` 开头「not a publication generator」与 `requirements-traceability.json` 的 interpretation 才是准确的自我定位。
- `intake/constraints.json` 的 `target_submission_ready_date = "2026-10-26"` 已过期 14 天，`run.json` 自 2026-10-23 起未更新；`continuation.json` 仍以 `stop_when = all_papers_submission_ready` 挂着，`should_run` 却为 false——**时间目标、状态推进、自动循环三者脱节**。

---

## 6. 结论速览

1. **能力契约**完整且分层清晰：`AGENTS.md` 25 条 + 2026-11-09 三份 owner decision > `references/stage-contracts.md` / `config/stages.json`（G0–G5）> `workflow.md` A/B/C 分类 > 69 个 schema > 25 份配置 > 46 技能入口。硬底线是「证据链、来源哈希、累计预算、失败留痕、角色隔离、人工只管 G1/G2、**绝不自动投稿**」。
2. **需求追踪**自评：45 条需求中 R24（六篇真实论文）`not-started`、R44（0.85 一致率/20–30 锚）`partial`、R02/R17 `optional`，其余 `implemented` 但都附「需真实项目证据验证」的 remaining；156 项 owner checklist `all_156_requirements_fulfilled=false`、`fully_satisfied_count=53`、81 项真实科研证据缺失。
3. **真实项目状态（最关键）**：`my-phd` 停在 **G1 / `awaiting_work`**，只有 **G0** 批准；G1/G2 无人工批准；6 篇论文全是 `draft` 空模板；0 实验、0 数据集、0 claim-evidence 绑定、757 行人工筛选表全空、`completed_real_papers=0`、`NOT_CALIBRATED`；累计费用账本记 0、验收记录记约 3.89 元 + 约 10 元未知预留；`should_run=false`，自动云研究从未启动。**唯一真实科研工作是基于免费公开 API 的 G1 文献元数据检索（27 组成功回执 / 2497 条 / 2158 去重键 / 757 待读）与本地生成的待审建议稿。**
4. **CI/云入口**：16 个工作流，绝大多数在 push/PR/定时上真跑（软件回归、合成夹具、Docker 隔离、公开 API），核心人工入口是 `cloud-research.yml` 的 `issues: opened` 与 `research-continuation.yml` 的 `mode: start`；付费科研受 `github.repository`、`DR_OS_AUTOMATIC_RESEARCH_ENABLED`、凭据与 `should_run` 四重约束，实际未启动。
5. **最大落差**：一个工程上相当完备、自我审计极其诚实的**控制平面与脚手架**（69 schema / 16 工作流 / 46 技能 / 25 配置 / 101 文档 / 156 项验收清单 / 2500+ 行阶段契约），对应一个几乎空白的**科研产出**；且「8/8.5/Q1/Q2/IF 阈值」「300 vs 500 预算」「0 vs 数元费用」「gpt-6.1 / claude-opus-5-5 等未来型号」「CC BY-NC 非商业许可」「机器人选题 vs 结构动力学期刊」等多处配置与文档互相打架。系统自己已在 `cloud-validation-2026-11-08.json` 与 `CODEBASE-AUDIT-2026-11-07.md` 中写下这一结论——**「Implementation is software capability, not research completion」**。
