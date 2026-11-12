# Doctoral Research OS v2.3.0 — 第三方组件精读报告

> 精读子智能体：专责第三方组件。
> 只读范围：`D:/ad/lunwen/third_party/`、`D:/ad/lunwen/integrations/`（lock/routes/授权类 `.json` 与 `.md`、`licenses/` 文本）、根目录 `THIRD-PARTY-NOTICES.md`；`AGENTS.md` 与 `README.md` 仅作背景，不计入精读。
> 纪律：未修改仓库内任何文件；唯一写入为本文。全文简体中文。

---

## 0. 范围、方法与统计

### 0.1 实际文件构成（脚本实测）

| 类别 | 数量 | 行数 |
|---|---:|---:|
| `third_party/**/*.py` | 27 | 12,432 |
| `third_party/**/*.md` | 40 | 8,687（题目记 8,688，差 1 行为末行换行口径） |
| 其它 `.json/.yaml/.csv/.txt/LICENSE` | 26 | 1,566 |
| `integrations/` 文件 | 30 | — |
| `THIRD-PARTY-NOTICES.md` | 1 | 50 |

27 个 `.py` 已**逐文件用 Read 完整通读**（大文件分段：`search_arxiv.py` 1213 行、`validate_hypothesis_schema.py` 1078 行、`audit_panel_alignment.py` 933 行、`text_unicode.py` 730 行均分两段读完）；未以 grep 摘要代替通读。40 个 `.md` 已逐份提取完整结构（frontmatter + 全部一/二/三级标题 + 关键声明全文），并对最关键的 `SKILL.md`、协议与评审文档做了正文精读。配置类 `.json/.yaml/.csv/.txt/LICENSE` 全部读取内容。

### 0.2 组件分组（14 个第三方来源）

按上游项目/技能包划分：`evil-read-arxiv`、`codex-skill-installer(openai/skills)`、`K-Dense-AI/scientific-agent-skills`（3 个技能目录）、`Yuan1z0825/nature-skills`（figure / methods）、`WUBING2023/PaperSpine`、`Imbad0202/academic-research-skills(-codex)`、`blader/humanizer`、`Kiterlin/anti-defensive-writing`、`guillaumemeyer/watermarks-remover`、`mikubaka88/CCFA-Skills`。另有 `integrations/codex-research-tools/` 下 11 个研究自动化工具（AI Scientist v1/v2、deer-flow、GPT Researcher、RD-Agent、AutoResearchClaw、MiroThinker、pi-autoresearch、PaperBanana、AIPOCH、EvoScientist、synthetic-openscience）的适配文档。

### 0.3 一句话结论

第三方为系统带来的**真实可执行代码**集中在三处：`evil-read-arxiv` 的 10 个联网文献检索/笔记脚本、`nature-figure` 的 2 个 PDF 几何审计器、`kdense` 的 12 个纯本地确定性校验器，外加 `watermarks-remover` 的 1 个 Unicode 清理库和 `codex-skill-installer` 的 2 个安装器脚本。其余约三分之二的体量（40 份 `.md` 的大部分、CCFA 17 技能、11 个研究自动化工具）是**方法学文档、模板、哈希清单或未部署的适配层**，不是可调用能力。自研控制平面把所有第三方输出统一压到 `advisory-only / 待核验线索` 地位。

---

## 1. 逐组件归纳

### 1.1 evil-read-arxiv（juliye2025/evil-read-arxiv）

- **来源与锁定**：`integrations/evil-read-arxiv.lock.json`，`upstream_commit = ef3a594841081703259545c828c98b52af835817`；27 个文件逐条记录 `canonical_lf_sha256` + `upstream_git_blob_sha`；规范化仅 LF + 末尾一个换行。`THIRD-PARTY-NOTICES.md:4-13` 保留 README 的 MIT 声明与作者署名，**该锁定树无独立 LICENSE 文件**，明确"不虚构上游版权、不宣称本 notice 授予更宽权利"。
- **提供的能力**（5 个技能目录，10 个 `.py`，4,566 行）：
  - `start-my-day/`：`search_arxiv.py`（arXiv API + Semantic Scholar 双源检索、四维启发式评分、日期窗口、去重、输出 `arxiv_filtered.json`）、`common_words.py`、`scan_existing_notes.py`（Obsidian vault 笔记索引）、`link_keywords.py`（wikilink 生成）。`SKILL.md` 753 行。
  - `conf-papers/`：`search_conf_papers.py`（DBLP API 取会议/年份论文 + S2 补引用与摘要 + 三维评分；复用 `search_arxiv.py` 的评分函数，跨目录 `sys.path` 插入）；`conf-papers.yaml`（`default_year: 2025`）。`SKILL.md` 442 行。
  - `paper-analyze/`：`resolve_source.py`（识别 arXiv ID / 公开 PDF URL / 项目页 / 博客 / 本地 PDF，下载并分类）、`generate_note.py`（中英双语 Obsidian 笔记模板，含"准确概括不增加原文没有的结论""区分作者主张和基于证据的判断"）、`update_graph.py`（`graph_data.json` 节点/边）。
  - `extract-paper-images/`：`extract_images.py`（优先 arXiv `e-print` 源码包 `pics/figures/`，回退 PDF，PyMuPDF 提图、尺寸/哈希去重、生成索引）。
  - `paper-search/`：`paper_hunter.py`（`arxiv` 包 + `pymed` 的 PubMed，多源抓取并**直接下载 PDF 到 vault**）。
- **依赖**：`requirements.txt` 为 `PyYAML>=6.0 / requests>=2.28.0 / PyMuPDF>=1.23.0 / arxiv / pymed`，**只有下限，未固定版本或哈希**（与全仓精确锁定风格不一致）。`config.example.yaml` 215 行，含 `vault_path` 占位、注释掉的 `semantic_scholar_api_key`、示例研究领域（计算病理学，与本项目无关）。`OBSIDIAN_VAULT_PATH` 环境变量 + 5 个 `agents/openai.yaml` 接口声明（上游 OpenAI Agents 技能元数据）。
- **真实联网**：是全部第三方中唯一大面积联网的组件（详见 §3.3）。上游 README 另有 v2.0 的 Next.js 16 + React 19 + Anthropic Claude SDK **Web 应用**，需 `ANTHROPIC_API_KEY` 或 `data/api_settings.json` / `OrcaRouter` 网关；`THIRD-PARTY-NOTICES.md:13` 明确 **"The web service and its direct Anthropic/shell execution paths are not installed"**。
- **与自研集成**：`README.md:343-350` 说明"五个 project-native evil-read-arxiv 技能"已适配到既有 cloud/evidence/budget 控制，见 `docs/LITERATURE-WORKBENCH.md`；`THIRD-PARTY-NOTICES.md:11-12` 明确"原生适配，不是直接跑上游研究脚本"。上游 `SKILL.md` 里的启发式评分（相关性 40% / 新近性 20% / 热门度 30% / 质量 10%，`>=7.5` 标"很值得读"）在自研层被降级为检索线索。

### 1.2 codex-skill-installer（openai/skills）

- **来源与锁定**：`integrations/evil-read-arxiv.lock.json` 的 `installer` 段，`source_repository = openai/skills`，`commit = 49f948faa9258a0c61caceaf225e179651397431`，`source_directory = skills/.system/skill-installer`；3 个文件带哈希。许可证 `LICENSE.txt` 为 **Apache-2.0**。
- **能力**：`install-skill-from-github.py`（308 行）从 GitHub 仓库路径安装技能到 `$CODEX_HOME/skills`；`github_utils.py`（21 行）封装 `urllib.request`。支持 `--repo/--url/--path/--ref/--dest/--name/--method`，`auto` 模式先 `https://codeload.github.com/{owner}/{repo}/zip/{ref}` 下载 zip，失败回退 `git clone --filter=blob:none --depth 1 --sparse`（HTTPS，再回退 SSH）。`DEFAULT_REF = "main"`。安全设计：`_safe_extract_zip` 防路径穿越、`_validate_relative_path` 拒绝绝对路径/`..`、`_validate_skill_name` 拒绝多段名、临时目录 `shutil.rmtree` 清理。
- **联网/凭据**：`github_request` 读 `GITHUB_TOKEN`/`GH_TOKEN` 环境变量作可选 `Authorization: token` 头；`subprocess.run(["git", ...])`。**是真实网络调用点**。
- **集成与接线**：`THIRD-PARTY-NOTICES.md:15-20` 说明云端验证仅在**隔离临时目录**执行该 helper 安装 5 个上游技能，随后安装经审查的项目适配，且 **"No upstream research script is executed automatically during installation"**。它是引导工具，不是科研执行器。

### 1.3 K-Dense-AI/scientific-agent-skills — hypothesis-generation

- **来源与锁定**：`integrations/vendored-research-methods.json` 中 39 个 kdense 文件之一部，commit `65d6e786832e2c52832713117bbbf5096b56f77f`（peer-review）、`a92663a0214b3b9fa1ba6b958284ffd919c00a0c`（upstreams 中 sb 1.4）；`LICENSE.md` 为 **MIT**（Copyright 2025 K-Dense Inc.）。`SKILL.md` frontmatter：`license: MIT`、`version: "2.2"`、`last-reviewed: "2026-07-23"`。
- **能力**：8 个纯本地 `.py`（3,378 行）+ `SKILL.md`(281) + 10 份 `references/` + 7 个 `assets/` 模板。
  - `_common.py`：**dependency-free** 安全 I/O（拒绝 URL-like 路径/symlink、后缀白名单、2MB 上限、严格 JSON 重复键检测、CSV 精确表头、原子写入 `chmod 600`、`require_https_url`）。
  - `validate_hypothesis_schema.py`（1078 行）：v2.0 假设记录 schema 与交叉引用校验，含 `ethics_and_feasibility` 六道 gate、`ai_use` 约束（`sensitive_or_unpublished_data_sent_externally=True` 直接报错、`local_policy_checked`/`citation_verification_required`/`human_accountable` 必须为 True）。
  - `validate_prediction_matrix.py`、`check_falsification_controls.py`、`check_operationalization.py`、`lint_causal_claims.py`、`audit_evidence_ledger.py`：分别校验预测/竞争假设矩阵、证伪与阴性对照、测量操作化、因果/相关性措辞、证据台账与检索边界。
  - `generate_preregistration_scaffold.py`：从已验证记录渲染本地 Markdown 预注册草稿，`no upload or registration occurs`。
- **约束**：所有报告只输出 `规则码 + 标识符 + 计数 + notice`，明确 "does not rank or select candidates" / "does not verify evidence, scientific validity, novelty, ethics approval, causal identification" / "does not visit URLs, verify source existence or content, appraise evidence, establish novelty"。`SKILL.md:25-34` 的 Never 清单含"automatically score, rank, select, accept, or reject scientific hypotheses"；`SKILL.md:69` "No script approval is an ethics, safety, regulatory, or scientific approval"。`references/tool_reference.md` 明确"make no network, model, image, subprocess, credential, or environment-variable calls"；`references/security_validation.md` 记录残余 LOW 发现"Neither LOW finding permits data transmission, credential access, scientific scoring, or automatic hypothesis selection"。
- **运行/接线**：**零网络、零第三方依赖、Python 3.11+ 标准库**。`README.md:140-146` 的 `--with-kdense` 只装"锁定提交中的筛选子集，默认不开启"；`upstreams.lock.json` 对应条目 `enabled_by_default: false`、`local_adaptations_enabled: true`。属于"vendored 备用 + 原生 wrapper 路由"，不是自动执行链路。

### 1.4 K-Dense-AI/scientific-agent-skills — scientific-brainstorming

- **来源与锁定**：同仓库，commit `a92663a0214b3b9fa1ba6b958284ffd919c00a0c`，`upstream_version = "scientific-brainstorming 1.4"`，MIT。`SKILL.md` `version: "1.4"`。
- **能力**：4 个纯本地 `.py`（1,754 行）+ `SKILL.md`(304) + 5 份 `references/`。
  - `session_scaffold.py`：生成结构化头脑风暴会话 JSON（10 个 workflow stage、idea/assumption 模板、`information_governance`、`notices`），明确 "No network or LLM calls are made"、"Ideas and scores are not evidence or scientific conclusions"、"Do not store sensitive prompt content or restricted information"；`--date` 可选，**不虚构当前日期**。
  - `validate_register.py`（636 行）：结构/来源/交叉引用校验，记录 `provenance.origin`（human/ai-assisted/literature-inspired/mixed/other）与 `ai_tool`，统计 `ai_assisted_or_mixed_ideas`；limitations 明确 "does not verify claims, citations, novelty, feasibility, or scientific validity"、"A valid register is not ethics, biosafety, regulatory, clinical, or institutional approval"。
  - `evaluate_matrix.py`（553 行）：**唯一做数值评分的第三方脚本**——透明加权矩阵 + 输入区间 + 单权重扰动灵敏度分析，但 `decision: None`、`tie_rule: "Rank is not a decision"`、`notice: "No idea was selected and no scientific conclusion was made"`、limitations "Ratings and weights are judgments, not empirical measurements of scientific truth"。
  - `_common.py`：另一份独立实现的安全 I/O（O_NOFOLLOW、5MB 上限、严格 JSON、0600 原子写入）。
- **运行/接线**：零网络、零依赖、标准库。同样默认不启用。

### 1.5 K-Dense-AI/scientific-agent-skills — peer-review（纯文本）

- 目录内**只有 `SKILL.md`(305 行)，0 个 `.py`、无 assets/references**。`THIRD-PARTY-NOTICES.md:26` 明确 "Peer-review is a source-text selection at commit 65d6e786..., **not an installation of its scripts/assets/references**"；"The native critic prioritizes its scientific passages; native policy supersedes upstream intake, licence/research-use and venue AI-policy gates"。
- `SKILL.md` 自带 "Mandatory safety boundary / Human accountability / Intake gate"，声明 "Bundled CLIs are deterministic and local-only... make no network, model, image, or external-service calls"——但该目录**并未附带那些 CLI**。**属文档选择，非可调用能力**。

### 1.6 Yuan1z0825/nature-skills — nature-figure

- **来源与锁定**：`vendored-research-methods.json` 7 个文件（2 `.py` + `requirements.txt` + `LICENSE` + 2 `nature-methods/*.md` + `LICENSE`），commit 见 `upstreams.lock.json` 的 `nature-skills` 条目。许可证 **Apache-2.0**（`LICENSE` 201 行）。`THIRD-PARTY-NOTICES.md:28` 特别说明：proposal skill 的 SKILL frontmatter 单独标 MIT，但项目"选了它的参考文件并保留仓库许可，**不宣称所有上游组件统一许可**"——组件内许可标注不一致。
- **能力**：`audit_figure_collisions.py`（742 行）——从最终 PDF 几何审计文字-文字碰撞、文字被描边路径穿过、文字超出页边界（FAIL），以及与填充区/位图的部分重叠（WARN，因 in-bar 标签可能是有意的）；输出 `PASS / FIX BEFORE DELIVERY / REVIEW REQUIRED / NOT AUDITABLE`，可生成 QA overlay PDF，`--self-test` 无依赖运行。`audit_panel_alignment.py`（933 行）——backend-neutral JSON layout manifest 审计多面板行/列对齐、等 span 宽度、间距、panel-label 锚点、共享网格边界，支持 exemptions 需记录 reason；提供 `matplotlib_layout_manifest()` / `require_matplotlib_panel_alignment()` 直接 API；文档提到 R/patchwork 的 `panel_alignment.R`（**未 vendored**）。
- **依赖**：`requirements.txt` = `PyMuPDF>=1.24.0,<2.0.0`；`THIRD-PARTY-NOTICES.md:31-32` 明确 PyMuPDF 是**运行时依赖、非 vendored 源码，其自身许可单独适用**。**零网络调用**（`http://www.w3.org/2000/svg` 只是 SVG 命名空间字符串）。
- **接线**：`README.md:267` 提到"原生图表同时检查面板对齐和 PDF 文字碰撞"；`THIRD-PARTY-NOTICES.md:28` "Native wrappers bind audit results to the existing renderer and gate; upstream audit files are unmodified"。是**已接线到自研图件门禁**的少数组件之一。docstring 里 `skills/nature-figure/requirements.txt` 是上游路径，与本仓库 `third_party/nature-figure/` 不一致（路径残留）。

### 1.7 Yuan1z0825/nature-skills — nature-methods（纯文档）

`foundation-files.md`(40) + `research-idea-gates.md`(50) + `LICENSE`(201, Apache-2.0)。定义 `00_scope.md`…`05_style_guide.md` 六个"基础文件"规范（"Rule: writing cannot silently alter canon"、证据表状态 `evidence-backed / plausible-inference / hypothesis / unsupported`）与 6 道研究想法门（可追溯、可证伪、Delta、验证、失败、新颖性语言门，"Do not use `novel`, `first`, `unexplored`, or a numeric innovation score unless a dedicated prior-art search has been performed and cited"）。**纯方法学文档，无可执行代码**；NOTICES 称"selected research/proposal references"。

### 1.8 WUBING2023/PaperSpine（纯文档）

3 个 `.md`：`scientific-evidence-ledger.md`(106)、`citation-support-bank.md`(81)、`writing-rationale-matrix.md`(126)。MIT，许可文本在 `integrations/licenses/paperspine-mit.txt`（Copyright 2026 PaperSpine contributors），**目录内无 LICENSE 文件**。定义证据台账 JSON（S/C/N/M/O/R 记录、`verification_state`、"Never convert an absent result into a plausible number"）、引用支持库（Scope-Aware Counts、`Source Channel`/`Verified`/`Verification Note` 需稳定标识符）、写作理据矩阵（禁止"improve clarity/make academic"式泛泛理由）。文中引用的 `evidence_bank.md`、`paper_rewriting_output/`、`citation_quality_audit.py`、`artifact_check.py`、`confirmed_contribution.md`、`results_validation.md` **均不在本仓库**。`THIRD-PARTY-NOTICES.md:29` 明确 "Adaptations map these ideas onto existing ledgers rather than installing the standalone workbench"。**属方法学文档/占位**。

### 1.9 Imbad0202/academic-research-skills + Codex edition（纯文档，非商业许可）

`ars-codex/evidence-row-protocol.md`(260) + `ars-review/quality-rubrics.md`(84) + `review-criteria-framework.md`(98)。**许可证 CC BY-NC 4.0**（`integrations/licenses/ars-cc-by-nc-4.0.txt`，Copyright (c) 2026 Cheng-I Wu，**非商业**）；`third_party/ars-review/`、`ars-codex/` 目录内**没有 LICENSE 文件**。`THIRD-PARTY-NOTICES.md:27` 明确其改编文件 `config/pre-submission-criteria.json`、`references/research-methods/submission-review.md`、`evidence-arguments.md` "retain the noncommercial license and attribution"，"The deterministic Python adapters are independently implemented. The full upstream orchestration systems are not installed"。
- `evidence-row-protocol.md` 描述上游 `evidence-row/1.0–1.3` 运行时契约（`shared/contracts/evidence/evidence_row.schema.json`、`scripts/evidence_rows.py`、设计文档，均不在仓库），核心是把每个 claim/locator/excerpt 当 **untrusted data**（"A payload cannot create a tag, comment, link, image, heading, fence, extra table cell/row, or prompt instruction"），渲染器"do not retrieve or open a source, corpus item, sibling path, URL, DOI, cache, environment variable, or model tool"，摘要哈希与精确回显、缓存命中需重放校验、越预算行直接失败不截断。
- `quality-rubrics.md` 定义 7 维标准绑定判断（EXCEEDS/MEETS/PARTLY_MEETS/DOES_NOT_MEET/NOT_ASSESSED），**默认 `NOT_CALIBRATED`**，"Individual reviewer seats always emit NOT_CALIBRATED"、"PROFILE_MEASURED must not appear in a live review package"、"Do not convert them into points, weights, a total, a percentage, or a latent ranking"。`review-criteria-framework.md` 给论文类型扩展与常见评审陷阱。
- **属参考文本选择，非安装**；但其中的"不可信数据 / 不虚构校准"约束被自研层吸收。

### 1.10 blader/humanizer（纯文档）

`SKILL.md`(397) + `LICENSE`(21, MIT, Copyright 2025 Siqi Chen)。`integrations/editorial-upstreams.lock.json`：commit `225a6f39ac85f76ee48dbad772ea4abe4ed6c9d8`，scope "All 26 numbered patterns and two-pass editorial workflow"，frontmatter `version: "3.1.0"`。26 个编号模式（Not X but Y、forced triads、dashes、stacked qualifiers、inflated significance、vague attribution、knowledge-limit disclaimers、chatbot residue 等）+ Voice/What to return 两遍编辑流程。**无 `.py`**，是写作规则文本；`README.md` 与 `AGENTS.md` 说明其独立机械扫描/记分卡已退休（见 §4）。

### 1.11 Kiterlin/anti-defensive-writing（纯文档）

`SKILL.md`(578) + `LICENSE`(21, MIT, Copyright 2026 Kiterlin)。`editorial-upstreams.lock.json`：commit `f516147d017a3fe43ae99192cb89d8261b0c8679`，scope "All checklist/procedure/function, expanded academic and technical-plan/SOP rules"。Core Rule "Advance the claim directly"，含 Detection Checklist（不必要免责声明、过度 hedging、防御性开头、自我削弱贡献陈述）、Rewrite Procedure、Preferred/Discouraged Patterns、实验不利结果处理。自带 "Preserve Necessary Precision"：保留影响主张有效性/证据解释/适用范围/研究设计/读者正确使用的必要限定。**无 `.py`**。

### 1.12 guillaumemeyer/watermarks-remover（1 个库 + 大量文档）

- **来源与锁定**：`editorial-upstreams.lock.json` commit `c5297e9e69fec0779c29127c7892427e673fafd9`，**MIT**（Copyright 2026 Guillaume Meyer and contributors），scope 明确 "Actual pinned Unicode cleaner and authorized editorial workflow; **no statistical-watermark verification or media regeneration**"。
- **实际代码**：仅 `scripts/text_unicode.py`（730 行，零依赖，标准库 `unicodedata/difflib`）——"Layer A" 不可见 Unicode / 零宽字符 / bidi 控制 / 同形空格 / 同形字母的 `inspect_text()` 与 `clean_text()`，**是库模块，无 CLI `main()`**。它保守地保留 emoji glue、CJK/蒙古文变体选择符、复杂文字连接符、完整旗帜 tag 序列、RTL 方向标记等"负载性不可见字符"，notes 明确 "Statistical (token-sampling) watermarks are not detectable here"。
- **文档描述的、但未 vendored 的能力**：`SKILL.md`(191) 的工作流调用 `$SCRIPTS/inspect_text.py`、`clean_text.py`、`score_stylometry.py`、`--audit`、`references/watermark-notes.md`——**这些脚本/文件都不在仓库**。因此"stylometry 评分器、Layer B 改写、detect-only 审计"均不可执行。
- **约束**：`SKILL.md:8` "never claim that a rewrite proves human authorship or is undetectable"；`detectors.md`(156) 区分统计型/神经分类器两族检测器、"Not legitimate to claim: Passed GPTZero/Turnitin/Originality… Undetectable… removal of a vendor secret-key watermark… proves human authorship"；`detectors.md:3` 自称 "Current as of mid-2026" 并断言 "Google retired SynthID text watermarking on the Generative Language API (mid-2026)"、"Anthropic's text-watermark detection API is not public"——**未绑定 URL/访问日期的当前事实断言**。`responsible-use.md` 仅 7 行。`writing-in-your-voice.md`(55) 要求不模仿具名他人、不虚构个人经历。

### 1.13 mikubaka88/CCFA-Skills（锁死 / 未 vendored）

- **来源与锁定**：`integrations/ccfa-skills.lock.json`（`schema_version 2.0`，`upstream_commit f157d7ed2777b655809471873b32b9632e784cfa`），**1,349 条 resources**，每条含 `git_blob_sha` / `canonical_lf_sha256` / `size`；`ccfa-skills.routes.json` 定义 17 个技能的 `stages/triggers/native_tools/outcome`，`mandatory: ["ccf-humanization","ccf-common"]`。**MIT**（Copyright (c) 2026 Chaoyue Li）。
- **仓库内实际内容**：`third_party/ccfa-skills/` **只有 `LICENSE`(21) 和 `ccf-project-scaffolder/assets/ccfa.yaml`(30，全空模板 `version: "0.4.0"`)**。1,349 条资源的扩展名分布为 md 316 / bib 152 / dtx 145 / cls 120 / ins 97 / pdf 90 / bst 86 / png 73 / svg 57 / tex 47 / sty 42，含 **19 个 `.py`**；顶层 `ccf-latex-templates` 859 个、`ccf-paper-writer` 231 个等。
- `THIRD-PARTY-NOTICES.md:38` 明确："Setup installs the complete functional text/code/reference inventory into that **ignored dependency cache** rather than duplicating it in Git"；"Binary templates and cached exemplar papers are available by **exact pinned retrieval in cloud storage, not redistributed into this repository**；their individual rights still apply"。
- **接线**：`README.md:30-31` `python -m scripts.ccfa_runtime bootstrap` 按固定 commit + 哈希装到 Git-ignored 缓存，**首次需联网，缓存完整后可离线**；`AGENTS.md:107` "Use the pinned CCFA family through `docs/CCFA-INTEGRATION.md`… All 17 authoritative native entries are under `skills/`; `.agents/skills/` contains generated discovery pointers"。**因此 CCFA 17 技能在本仓库是"锁死/需联网取回"，不是可直接调用的能力**。

### 1.14 integrations/codex-research-tools 的 11 个研究自动化工具（纯适配文档）

- `research-automation-tools.json`：11 个工具全部 `enabled_by_default: False`、`runtime_status: "codex-adapter-available"`、`standalone_runtime_deployed: False`、`paid_services_enabled: False`；`installation_scope` 明确 "Standalone services, inference models, desktop apps and paid providers are not deployed"；`official_installer` 仍是 `openai/skills` 的 skill-installer。
- `research-automation-coverage.json`：`paid_calls: 0`，scope "Selected useful mechanisms implemented in the existing cloud control plane; upstream standalone services are not deployed"，每个工具映射到**自研 scripts/**（如 ai-scientist → `research_search_tree.py`/`research_iteration.py`/`figure_story.py`/`figure_output_qa.py`/`research_toolkit.py`；deer-flow → `literature_reading.py`；pi-autoresearch → `experiment_runner.py`）。
- `research-automation-source-receipts.json`：`local_research_runtime_executed: False`、`paid_calls: 0`，`source_root = D:\ad\codex\research-automation\sources`（**仓库外路径**），仅按 commit + `archive_sha256` + `receipt_sha256` 归档源码 zip 回执。
- 11 个 `SKILL.md` 明确"独立运行时未部署、需额外依赖（Python 3.12+/Node 22/pnpm、Tavily/付费 embedding、Docker 等）、不新增付费调用或模型变更"，输出为方法学指导（如 ai-scientist 的分支/失败恢复/图文一致性、rd-agent 的假设-实验-反馈、gpt-researcher 的有界检索前沿、paperbanana 的参考驱动图件规划）。**无第三方源码 vendored，实际能力由自研 scripts 实现**。
- `AGENTS.md:29`（rule 25，owner decision 2026-11-09）明确：`integrations/upstreams.lock.json` 与 `research-automation-tools.json` "remain **historical snapshots - authorisation is not deployment**"。`upstreams.lock.json` 的 **46 个 source 全部 `enabled_by_default: false`**（25 个 `local_adaptations_enabled: true`），`reviewed_at: 2026-09-30`。

### 1.15 其它 integrations 锁定文件（背景归纳）

| 文件 | 内容 |
|---|---|
| `research-methods-authorization.json` | 2026-09-30 记录，`actor: Hengyi Zang`，`noncommercial_academic_project: true`，`does_not_authorize_paid_calls_or_scientific_gate_approval: true` |
| `third-party-runtime.json` | `scripts/third_party_runtime.py`；risk_tiers 三级（local-readonly / network-no-credentials / credentials-or-paid）；**guardrails 8 项全 `false`**；`output_status: "advisory until hash-bound, independently verified and linked to evidence"`；**`tools: []`（空注册表）**；notes "deployment_authorized is a permission; standalone_runtime_deployed is an observed fact. Never infer one from the other." |
| `editorial-upstreams.lock.json` | humanizer / anti-defensive-writing / watermarks-remover 三个 commit + 文件哈希，MIT |
| `evil-read-arxiv.lock.json` | 27 文件哈希 + installer commit，见 §1.1/1.2 |
| `vendored-research-methods.json` | 54 个"未改动 vendored"文件：K-Dense 39、nature-skills 7、PaperSpine 4（含 licenses）、ARS 4（含 licenses） |
| `literature-semantic.lock.json` | CPU 语义检索：embedding `Xenova/paraphrase-multilingual-MiniLM-L12-v2`（Apache-2.0）+ reranker `Xenova/ms-marco-MiniLM-L-6-v2`（Apache-2.0），`onnxruntime 1.23.2/tokenizers 0.22.1`，权重 sha256；"Explicit cloud CPU retrieval only; no paid API, remote Python code, model route promotion or scientific approval" |
| `figure-gallery-semantic.lock.json` | `Xenova/clip-vit-base-patch32` 量化 ONNX（MIT），3449 行嵌入；"CPU retrieval only; no image copying, paid API or scientific validation" |
| `topconf-figure-gallery.lock.json` + `IMAGES_POLICY.md` + `LICENSE` | 3449 条 `figures.json` 元数据哈希；**MIT 仅覆盖代码**，`image_redistribution: false`，图片版权归原论文作者/出版方，明确"非商业、教育与研究用途"的配图灵感索引 |
| `licenses/ars-cc-by-nc-4.0.txt` | CC BY-NC 4.0 全文 + Copyright (c) 2026 Cheng-I Wu |
| `licenses/paperspine-mit.txt` | MIT，Copyright (c) 2026 PaperSpine contributors |

---

## 2. 集成地图

### 2.1 版本/来源锁定的四种方式

1. **逐文件双哈希**：`evil-read-arxiv.lock.json`（`canonical_lf_sha256` + `upstream_git_blob_sha`）、`editorial-upstreams.lock.json`（`canonical_lf_sha256`）、`vendored-research-methods.json`（`sha256` + `commit` + `source_path`）。
2. **完整上游资源清单**：`ccfa-skills.lock.json` 1,349 条 `git_blob_sha`/`size`，指向被忽略的依赖缓存与云存储。
3. **历史审查快照（非部署）**：`upstreams.lock.json` 46 sources、`research-automation-tools.json` 11 tools、`*-source-receipts.json`。
4. **运行时依赖声明**：`requirements.txt`（只有下限/上界，非哈希）、`literature-semantic.lock.json` 等模型权重 sha256 + revision。

### 2.2 第三方 → 自研 scripts 的映射（由 routes/coverage 定义，均为"方法指导→原生实现"）

- `ccfa-skills.routes.json`：17 个 `ccf-*` 技能映射到 `scripts/cloud_job.py`、`cloud_checkpoint.py`、`ccfa_runtime.py`、`academic_style.py`、`ccfa_science.py`、`researchctl.py`、`research_candidates.py`、`pre_submission_review.py`、`literature_evidence.py`、`literaturectl.py`、`literature_intelligence.py`、`experiment_runner.py`、`experiment_evidence.py`、`literature_reasoning.py`、`manuscript_audit.py`、`citation_audit.py`、`ref_verify_adapter.py`、`api_orchestrator.py`、`incremental_writing.py`、`reviewer_rounds.py`、`revision_trace.py`、`supplemental_experiments.py`、`publication_figures.py`、`venue_compliance.py`、`submission_package.py`、`journal_screening.py`、`literature_workbench.py`、`validate_repo.py`。其中 `ccf-humanization` 的 outcome 明确 "source-bound optional editorial method guidance; **mechanical reports retired and semantic review unclaimed**"，`ccf-project-scaffolder` "native six-paper project structure; **no second state file**"。
- `research-automation-coverage.json`：11 工具 → 自研控制平面 scripts（见 §1.14），`paid_calls: 0`。
- `THIRD-PARTY-NOTICES.md`：K-Dense 的"native wrapper skills route to the existing cloud control plane"；nature-figure 的"Native wrappers bind audit results to the existing renderer and gate"；ARS 的"The deterministic Python adapters are independently implemented"；PaperSpine 的"Adaptations map these ideas onto existing ledgers"。
- README 安装入口：`python -m scripts.ccfa_runtime bootstrap`（CCFA 缓存）、`bash scripts/bootstrap-wsl.sh --with-kdense`（筛选子集，默认不开启）、`--with-figures`（绘图栈）、`--with-ai4science`（`paper-qa==2026.08.12`、`tooluniverse==1.5.1`）、`--with-reference-tools`（`ref-verify==1.2.0`）、`--with-writing-tools`（`proselint v0.16.0`）、`--with-research-quality-tools`（`statsmodels==0.15.0`）。

### 2.3 运行时授权边界

`AGENTS.md` rule 25（2026-11-09 owner decision，effect-first / maximum flexibility）：任何 GitHub 项目、技能或运行时"may be called in any environment, order or duration, with or without registration… `scripts/third_party_runtime.py free` needs no registry entry"，但**section 3 authority boundaries 仍适用**：不写 stage state、不批 gate、不在 `scripts/experiment_runner.py` 之外跑实验、不伪造 provenance、不做稿件作者、不暴露密钥/原始数据、不改模型家族/预算、不自动投稿、不破坏云沙箱。owner 授权的工具输出"may enter the candidate-evidence queue **when hash-bound and source-verified before any claim link**"。`third-party-runtime.json` 的 guardrails 与空 `tools: []` 与之呼应：`deployment_authorized` 只是许可，`standalone_runtime_deployed` 才是事实。

---

## 3. 实际可用能力 vs 文档/占位

### 3.1 第三方真正增加的可执行能力（8 条）

1. **arXiv / Semantic Scholar / DBLP / PubMed 文献检索与推荐**：`search_arxiv.py`（双源 + 四维评分 + 日期窗口 + 去重）、`search_conf_papers.py`（顶会/年份 + S2 补充）、`paper_hunter.py`（多源抓取）。这是唯一具备真实公网检索的第三方能力。
2. **来源解析与全文/图件本地化**：`resolve_source.py`（arXiv ID、公开 PDF URL、项目页、博客、本地 PDF 分类 + 受控下载）、`extract_images.py`（arXiv `e-print` 源码包优先、PDF 回退、PyMuPDF 提图 + 尺寸/哈希去重）。
3. **Obsidian 研究知识库构建**：`generate_note.py`（中英双语笔记模板、frontmatter 含 document_id/source_url）、`update_graph.py`（图谱节点/边）、`scan_existing_notes.py` + `link_keywords.py`（笔记索引 + wikilink）。
4. **Nature 风格图件几何 QA**：`audit_figure_collisions.py`（文字/描边/页边界碰撞）、`audit_panel_alignment.py`（多面板对齐、等宽、间距、label 锚点、exemptions）——已绑定到自研渲染器与门禁。
5. **假设生成/预注册的确定性校验**：kdense hg 8 脚本（v2.0 schema 与交叉引用、预测/竞争假设矩阵、因果措辞 lint、证伪与阴性对照、证据台账+检索边界、操作化清单、预注册草稿生成），含伦理/可行性 gate 与 AI 使用约束。
6. **结构化科学头脑风暴**：kdense sb 4 脚本（会话脚手架、idea/assumption register 结构校验、透明加权矩阵 + 单权重灵敏度分析、不虚构日期）。
7. **不可见 Unicode / 隐写字符检测与清理**：`text_unicode.py`（零宽、bidi、tag、同形空格/字母；保守保留负载性不可见字符）。
8. **按固定 ref 从 GitHub 安装技能**：`install-skill-from-github.py` + `github_utils.py`（供 `ccfa_runtime bootstrap` 与云端隔离验证）。

### 3.2 仅文档 / 占位 / 未部署（清单）

| 项 | 证据 |
|---|---|
| CCFA 17 技能 | 仓库内仅 LICENSE + 空 `ccfa.yaml`；1,349 条哈希在 lock，实体在 ignored 缓存/云存储，首次需联网 |
| 11 个研究自动化工具 | `standalone_runtime_deployed: False` 全部；`local_research_runtime_executed: False`；只有 11 份 `SKILL.md` 适配文档，源码在仓库外 `D:\ad\codex\...` |
| `upstreams.lock.json` 46 sources | `enabled_by_default: false` 全部；owner decision 定性为 historical snapshots |
| kdense `peer-review` | 仅 1 份 SKILL.md，NOTICES 明确不是安装 scripts/assets/references |
| humanizer / anti-defensive-writing | 只有 SKILL.md + LICENSE；`AGENTS.md:107` "their separate mechanical scans and scorecards are retired" |
| watermarks-remover 大部分工作流 | `inspect_text.py`/`clean_text.py`/`score_stylometry.py`/`watermark-notes.md` 未 vendored；`text_unicode.py` 无 CLI |
| ars-codex / ars-review | 3 份 md 引用不存在的 `scripts/evidence_rows.py`、schema、设计文档；NOTICES "full upstream orchestration systems are not installed" |
| paperspine | 3 份 md 引用不存在的 `evidence_bank.md`、`citation_quality_audit.py`、`paper_rewriting_output/` |
| nature-methods | 2 份规范文档，无代码 |
| evil-read-arxiv Web 应用 | Next.js 16 + Anthropic SDK，"not installed" |
| `panel_alignment.R` | `audit_panel_alignment.py` docstring 提及，未 vendored |
| kdense `assets/*` 模板 | 全部标注 "Synthetic demonstration"；`search_boundary_template.json` 自述 "cannot support novelty, priority, or an evidence claim" |
| `third-party-runtime.json` | `tools: []` 空注册表 |

### 3.3 真实网络调用点（逐点核对，含易误判排除）

| 文件:行 | 端点 / 调用 | 说明 |
|---|---|---|
| `codex-skill-installer/github_utils.py:16,21` | `https://api.github.com/repos/{repo}/contents/{path}?ref={ref}` via `urllib.request.urlopen` | 可选 `GITHUB_TOKEN`/`GH_TOKEN` 头 |
| `install-skill-from-github.py:81,84` | `https://codeload.github.com/{owner}/{repo}/zip/{ref}` | 下载仓库 zip |
| `install-skill-from-github.py:100,180,184` | `subprocess.run(["git","clone",...])` → `https://github.com/{owner}/{repo}.git` 或 `git@github.com:...` | 回退稀疏检出 |
| `start-my-day/search_arxiv.py:199,211,272,284` | `https://export.arxiv.org/api/query?...` | arXiv Atom API，`urllib`，3 次重试 |
| `start-my-day/search_arxiv.py:47,344,357` | `https://api.semanticscholar.org/graph/v1/paper/search` | `requests`/`urllib`，可选 `x-api-key`（来自 config 的 `semantic_scholar_api_key`），429 退避 |
| `paper-search/paper_hunter.py:137` | `arxiv.Client(...).results(search)` | `arxiv` 包 |
| `paper-search/paper_hunter.py:93` | `requests.get(paper_data['pdf_url'], timeout=30)` | 直接下载 PDF 写入 vault |
| `paper-search/paper_hunter.py:159` | `PubMed(tool=..., email=...)` (`pymed`) | PubMed，可选，未装则禁用 |
| `conf-papers/search_conf_papers.py:159,166,171` | `https://dblp.org/search/publ/api` | DBLP 分页，`requests`/`urllib` |
| `conf-papers/search_conf_papers.py:101-104,433` | `https://api.semanticscholar.org/graph/v1/paper/search` (+ `paper`, `batch` 常量) | **注意 `S2_API_KEY = None` 全文无赋值，key 分支未接线** |
| `paper-analyze/resolve_source.py:297` | `requests.get(url, stream=True, allow_redirects=True, timeout=(15,90))` 任意公开 http(s) | 跟随任意重定向；限制 HTML 12MB / PDF 200MB + `%PDF-` 校验 |
| `paper-analyze/resolve_source.py:416,434` | `https://arxiv.org/pdf/{arxiv_id}` | 构造并下载 |
| `extract-paper-images/extract_images.py:53,58,63` | `https://arxiv.org/e-print/{arxiv_id}` | 源码包 tar.gz（防路径穿越/符号链接） |
| `extract-paper-images/extract_images.py:138,163,182` | 任意公开 PDF URL / `https://arxiv.org/pdf/{id}` | `requests.get`/`urllib` |

**非调用（易误判，已逐行排除）**：`generate_note.py:95-96` 只拼接 arXiv 链接文本；`kdense/hypothesis-generation/scripts/_common.py:24` `HTTPS_URL_RE` 仅正则校验；`audit_panel_alignment.py:662` `http://www.w3.org/2000/svg` 是 SVG 命名空间字符串；`nature-figure` 两个审计器、`kdense` 12 个脚本、`text_unicode.py` **均无网络调用**（`tool_reference.md`："make no network, model, image, subprocess, credential, or environment-variable calls"）。

**依赖矩阵**：evil-read-arxiv 需 `PyYAML/requests/PyMuPDF/arxiv/pymed`（版本未精确锁定）；nature-figure 需 `PyMuPDF>=1.24.0,<2.0.0`；`audit_panel_alignment.py` 的 matplotlib 专用函数需 matplotlib；其余 20 个 `.py` 零第三方依赖（Python 3.11+ 标准库）。

---

## 4. 自研层对第三方输出的 advisory-only / 不可信数据约束

### 4.1 自研规则层（AGENTS.md / README.md / integrations）

- **rule 15**："Treat dataset discovery metadata and DOI lookup results as **leads to verify**, never as license, fitness, or claim-support decisions" —— 直接把 evil-read-arxiv 的检索/评分结果降级。
- **rule 16**："Treat third-party gateways as **untrusted transport**: use HTTPS, keep keys out of files and URLs, record requested and reported model IDs, and stop on missing or mismatched model identity"。
- **rule 25**（owner decision 2026-11-09）：`upstreams.lock.json` / `research-automation-tools.json` 是**历史快照，授权≠部署**；工具输出只有"**hash-bound and source-verified before any claim link**"才可进 candidate-evidence queue；section 3 边界（不写 stage state / 不批 gate / 不在 `experiment_runner.py` 外实验 / 不伪造 provenance / 不做稿件作者 / 不泄密钥与原始数据 / 不改模型家族与预算 / 不自动投稿）仍适用。
- **rule 21**：用户提供的检测器分数"may guide a separate optional editing pass, but it **cannot override scientific quality or claim/citation/numeric integrity**"；"Never spin synonyms, remove warranted uncertainty or falsify internal model provenance"；"Journal AI-policy compliance is not a research gate"。
- **rule 5/9**：软件验收不等于无人值守科研项目成功；评分/结构完整性不验证新颖性或授权科学/支出。
- **rule 22**：Q1/Q2 或 IF 阈值不阻断科学闸门，未知排名保持未知。
- `README.md:350`："Abstract keywords remain explainable discovery signals; **they do not assess our manuscript's scientific quality**"。
- `third-party-runtime.json`：guardrails 8 项全 false；`output_status = "advisory until hash-bound, independently verified and linked to evidence"`；`tools: []`。
- `research-automation-coverage.json`：`paid_calls: 0`、"upstream standalone services are not deployed"；`source-receipts.json`：`local_research_runtime_executed: False`。
- `ccfa-skills.routes.json` `ccf-humanization` outcome："mechanical reports retired and semantic review unclaimed"；`AGENTS.md:107`："Pinned H/AD/CFH methods remain available within existing writer/review calls; **their separate mechanical scans and scorecards are retired and cannot be imputed as completed**"。
- `literature-semantic.lock.json`："no paid API, remote Python code, model route promotion or scientific approval"；`figure-gallery-semantic.lock.json`："no image copying, paid API or scientific validation"。

### 4.2 第三方输出自带的 advisory 声明（与自研一致，构成双保险）

- kdense hg 全部报告 `notice`：`"does not rank or select candidates"` / `"does not verify evidence..."` / `"does not visit URLs, verify source existence or content..."`；`SKILL.md` Never 清单；`lint_causal_claims.py:154-159` "does not determine whether language is scientifically causal"。
- kdense sb：`evaluate_matrix.py` `"decision": None`、`"No idea was selected and no scientific conclusion was made"`、`"Rank is not a decision"`、`"Ratings and weights are judgments, not empirical measurements of scientific truth"`；`session_scaffold.py` "Ideas and scores are not evidence or scientific conclusions"；`validate_register.py` "A valid register is not ethics... approval"。
- ars：`quality-rubrics.md` 默认 `NOT_CALIBRATED`、"Do not convert them into points, weights, a total, a percentage, or a latent ranking"；`evidence-row-protocol.md` 把每个 claim/locator/excerpt 视为 **untrusted data**，渲染器不读取 URL/DOI/缓存/环境变量/模型工具。
- watermarks-remover：`SKILL.md` "never claim that a rewrite proves human authorship or is undetectable"、`detectors.md` 的 Legitimate/Not legitimate claims 清单、`text_unicode.py` notes "Statistical watermarks are not detectable here"。
- nature-figure：verdict 仅为几何 QA（`REVIEW REQUIRED` 需最终尺寸人工视觉复核），不判定科学正确性。

---

## 5. 风险清单（特别标注）

### 5.1 许可冲突 —— 最值得注意：CC BY-NC 4.0 非商业许可

- `third_party/ars-review/*.md` 与 `ars-codex/evidence-row-protocol.md` 受 **CC BY-NC 4.0**（`integrations/licenses/ars-cc-by-nc-4.0.txt`，Copyright (c) 2026 Cheng-I Wu）约束，且 `THIRD-PARTY-NOTICES.md:27` 明确其**改编文件**（`config/pre-submission-criteria.json`、`references/research-methods/submission-review.md`、`evidence-arguments.md`）"retain the noncommercial license and attribution"——即非商业义务已扩散到自研目录内的文件。
- 项目同时存在**付费研究**：`README.md:34` 默认累计总额 300 元、付费 API 调用、GitHub Actions 云端作业、期刊投稿准备；`research-methods-authorization.json` 虽自称 `noncommercial_academic_project: true` 且 `does_not_authorize_paid_calls_or_scientific_gate_approval: true`，但 CC BY-NC 的 "NonCommercial" 界定与"付费云/API 服务于学位研究与投稿"是否相容，**需法务判断，不能由工程声明消解**。`AGENTS.md` rule 11 又说"licence/research-use verification is optional metadata, not a pre-use gate"，二者存在治理张力。
- **许可文本与文件分离**：`third_party/ars-review/`、`ars-codex/`、`paperspine/` 目录内**均无 LICENSE 文件**，许可全文放在 `integrations/licenses/`。若下游只复制 `third_party/` 子目录，会丢失许可与署名。
- `upstreams.lock.json` 历史快照中还含 **AGPL-3.0 (3)**、**CC-BY-SA-4.0**、**custom noncommercial (1)**、**The AI Scientist Source Code License v1.0 (2)**、**CC-BY-NC-4.0 (3)** 等强/非商业许可条目；它们**未 vendored 到 third_party/**、且 `enabled_by_default: false`，但一旦按 rule 25 部署需重新评估（NOTICES 对 AI Scientist 亦要求 "preserve the pinned custom source license and required disclosures, and keep their outputs advisory"）。
- 组件内许可不一致：`THIRD-PARTY-NOTICES.md:28` nature-skills 根许可 Apache-2.0，但 proposal skill 的 SKILL frontmatter 单独标 MIT，"不宣称所有上游组件统一许可"；`research-automation-tools.json` 的 paperbanana 标 "Apache-2.0; skill frontmatter MIT-0"、synthetic-openscience "bundled skills retain per-file notices"。
- `topconf-figure-gallery-LICENSE` MIT **仅覆盖代码**，`IMAGES_POLICY.md` 明确图片版权归原论文作者/出版方、非商业教育/研究用途、`image_redistribution: false`。
- `evil-read-arxiv` 上游 README 声明 MIT 但锁定树**无独立 LICENSE 文件**（NOTICES 明确不虚构上游版权）；`ccfa-skills.lock.json` 的 90 个 pdf / 73 个 png 二进制模板"their individual rights still apply"。

### 5.2 上游未启用 / 锁死

- `upstreams.lock.json` **46/46 `enabled_by_default: false`**；`research-automation-tools.json` **11/11 `standalone_runtime_deployed: False` / `paid_services_enabled: False` / `enabled_by_default: False`**；`third-party-runtime.json` **`tools: []`**。
- CCFA 17 技能锁在 `f157d7ed...`，实体不在 Git（1,349 条哈希 + Git-ignored 缓存 + 云存储），首次 bootstrap 需联网；`third_party/ccfa-skills/` 只有许可与空模板。
- `README.md:146` `--with-kdense` "只安装锁定提交中的筛选子集，**默认不开启**"；`AGENTS.md:60` AI Scientist "keep their outputs advisory"；`README.md:20` "本轮没有运行付费研究…或宣布这些科研结果已实现"。
- `codex-skill-installer` 仅在隔离临时目录做云端验证，"No upstream research script is executed automatically during installation"；evil-read-arxiv Web 应用 / 直接 Anthropic 执行路径未安装；`panel_alignment.R` 未 vendored；watermarks-remover 的 CLI/评分器未 vendored。

### 5.3 硬编码未来版本 / 过期默认值 / 版本不一致

- `upstreams.lock.json` 的 `paperqa2 => 2026.08.12`（`README.md:120` `paper-qa==2026.08.12`）：以日期作版本号的**未来式硬编码版本**，在 `reviewed_at: 2026-09-30` 语境下需核验其真实存在；同类精确锁定还有 `tooluniverse==1.5.1`、`statsmodels==0.15.0`、`ref-verify==1.2.0`、`proselint v0.16.0`、`lean4-proof-kernel 4.35.0`。
- `conf-papers/conf-papers.yaml` `default_year: 2025`：相对当前（2026-11-09）已过期一年的默认年份，且 `search_conf_papers.py` 无年份时效校验。
- `USER_AGENT = "evil-read-arxiv/3.0"`（`resolve_source.py:26`、`extract_images.py:143`）与上游 README 更新日志最新 **v2.1（2026-07-16）** **版本不一致**；`ConfPapers/1.0`、`StartMyDay-PaperFetcher/1.0` 亦为硬编码 UA。
- SKILL frontmatter 固定版本：humanizer `3.1.0`、hg `2.2`、peer-review `2.2`、sb `1.4`、ccfa.yaml `0.4.0`；`ethics_safety_and_ai.md` "U.S. policy status checked 2026-07-23"、`source_ledger.csv` 多条 `verified_on: 2026-07-23`——**固定审查日期会随时间失效**，与 `AGENTS.md` rule 3（用当前一手来源、记录 URL 与访问日期）冲突。
- `detectors.md:3` "Current as of mid-2026" 且断言 "Google retired SynthID text watermarking… (mid-2026)"、"Anthropic's text-watermark detection API is not public"——**未绑定来源 URL/访问日期的当前事实断言**，属潜在未核实信息。
- kdense `assets/` 全部为 `Synthetic demonstration` 模板且固定日期 2026-07-23；`search_boundary_template.json` 自述 "This is a schema example and cannot support novelty, priority, or an evidence claim"——**不可被当成真实证据记录**。

### 5.4 与自研规则冲突处

- **去 hedging vs 保留必要不确定性**：`anti-defensive-writing` Core Rule 要求删除"unnecessary caveats, disclaimers, hedges"，`humanizer` 26 模式含 "knowledge-limit disclaimers"；而 `AGENTS.md` rule 21 明确 "Never spin synonyms, **remove warranted uncertainty** or falsify internal model provenance"。anti-defensive 自身有 "Preserve Necessary Precision" 兜底，且自研已把 H/AD/CFH 的独立机械扫描/记分卡退休（rule 107）、只保留 writer/review 调用内可选指导——**方向一致但边界需人工把关**。
- **启发式质量评分 vs 分数不作科学判断**：`search_arxiv.py:741-798` `calculate_quality_score` 用摘要里 "state-of-the-art / novel / outperforms / achieves / ablation" 等关键词推断 0–3 分"质量"，`start-my-day/SKILL.md` 输出 `>=7.5` "很值得读"与"整体质量评价"；与 rule 5/9/19、`README.md:350`（"do not assess our manuscript's scientific quality"）冲突。自研层以 rule 15（leads to verify）把这类输出挡在证据链之外；`kdense` 与 `ars` 则反向明确"no automatic quality score / NOT_CALIBRATED"。
- **水印/检测器规避意图 vs 学术诚信**：watermarks-remover 的 "Detector levers / Optional recursive paraphrase / watermark reduction" 与 rule 21（AI 政策合规不是科研闸门、不得掩盖 AI 使用）、rule 22、rule 18（不得用改写掩盖 Anthropic/Claude 来源）存在目的性张力；但 `editorial-upstreams.lock.json` scope 明确 "no statistical-watermark verification or media regeneration"，`detectors.md` 自身否定一切"过检/人类认证"声明，且评分器未 vendored，`AGENTS.md:107` 已把 AD/H 机械处置退休。
- **任意重定向下载 vs 数据获取边界**：`resolve_source.py:297` `allow_redirects=True` 且无 host 白名单，直接把 PDF/HTML 写入本地，和 `README.md:206`（"下载只接受公网 HTTPS，不携带登录凭据，不绕过付费墙、验证码或访问控制"）、rule 11 存在张力；NOTICES 已说明 web service/直接执行路径未安装，项目用原生适配。
- **上游 README 的密钥配置**：`evil-read-arxiv/README.md` 描述 `data/api_settings.json` 明文 `sk-ant-...`、`ANTHROPIC_API_KEY`、修改 `web/src/lib/anthropic.ts` 的 `DEFAULT_API_KEY`、第三方中转站 OrcaRouter 与 infistar.ai 推广链接，与 rule 16（keys out of files and URLs、记录并核对 model IDs）冲突；这些路径未安装，但若照文档操作会直接违规。
- **ccfa.yaml 空模板**：`stage.current: "scaffolded"` / `gate: "not_started"` 若被误当作项目状态，与 `ccfa-skills.routes.json` "no second state file" 及自研六篇单一状态机冲突；它仅是上游 asset 模板。
- **依赖未精确锁定**：`evil-read-arxiv/requirements.txt` 用 `>=` 下限、`nature-figure/requirements.txt` 用 `>=,<`，与全仓"固定 commit + 哈希"证据链风格不一致（`THIRD-PARTY-NOTICES.md:31-33` 也提醒 PyMuPDF 是运行时依赖、自身许可另计、改变用途需复核部署许可）。
- **上游接口元数据过时**：5 个 `agents/openai.yaml` 是 OpenAI Agents 技能接口声明，而 `AGENTS.md:17,79` 明确"local Claude Code/Codex subprocess backend is retired"，属未接线的遗留元数据。

### 5.5 真实网络调用点的额外风险

- 上述 §3.3 的 7 个文件联网，其中 `resolve_source.py`/`extract_images.py`/`paper_hunter.py` 会**把远端字节写入本地 vault/临时目录**；`install-skill-from-github.py` 会执行 `git` 子进程并解压 zip（已有防穿越但仍是外部输入）。
- 密钥面：`github_utils.py` 的 `GITHUB_TOKEN`/`GH_TOKEN`；`search_arxiv.py` 的 `semantic_scholar_api_key`（config）；`config.example.yaml` 注释占位；`paper_hunter.py` 的 `pubmed_email`。`search_conf_papers.py` 的 `S2_API_KEY = None` **恒未赋值**——该分支实际锁死，S2 请求永远不带 key（只靠 1 req/sec 限速）。
- `README.md` 上游 Web 应用还涉及 `ANTHROPIC_API_KEY` / 中转站，但**未安装**。
- 所有联网脚本均为上游 vendored 源；`THIRD-PARTY-NOTICES.md:13,19-20` 与 `AGENTS.md` rule 16 要求自研层把它们当"不可信传输"，走 HTTPS、密钥不落文件/URL、记录模型身份、异常停止。

### 5.6 其它

- `audit_figure_collisions.py` docstring 引用 `skills/nature-figure/requirements.txt`（上游路径），与仓库实际路径 `third_party/nature-figure/` 不符；`audit_panel_alignment.py` docstring 引用未 vendored 的 `panel_alignment.R`。
- `ars-codex/evidence-row-protocol.md`、`paperspine/*.md`、`watermarks-remover/SKILL.md` 大量引用**仓库内不存在**的上游脚本/输出文件，若按文档直接执行会失败——这些是"文本选择"而非安装。
- `kdense/hypothesis-generation/scripts/_common.py` 与 `scientific-brainstorming/scripts/_common.py` 是两份独立实现（不同常量、不同 I/O 策略），维护上需注意差异（前者 2MB/1,000 行/8,000 单元格，后者 5MB/5,000 项/O_NOFOLLOW）。

---

## 6. 结论

第三方层是一个**"少量可执行的联网/几何/校验代码 + 大量方法学文本 + 一批精确锁定但未部署的上游快照"**的混合体：

- 真正能"跑起来产出结果"的只有 `evil-read-arxiv`（10 脚本，联网检索与 Obsidian 笔记/图件）、`nature-figure`（2 个已接线的 PDF 几何审计）、`kdense` 12 个本地校验器、`watermarks-remover` 的 Unicode 清理库、`codex-skill-installer` 的安装器。
- 假设生成、Nature 风格图件 QA、CCFA 写作技能、AI 去味/水印去除等**名义能力**，要么只有文档/模板，要么锁在被忽略缓存/云存储需联网取回，要么其独立扫描/评分已被自研层退休。
- 自研控制平面用 `advisory-only / hash-bound / source-verified / leads to verify / untrusted transport / NOT_CALIBRATED / 分数不作科学放行` 六重约束，把第三方输出统一挡在证据链与闸门之外；`guardrails` 全 false、`tools: []`、46+11 个来源全部默认未启用，进一步说明"授权≠部署"。
- 最需要处置的三个风险：**CC BY-NC 4.0 非商业许可与付费云/投稿准备的潜在冲突（且改编文件在自研目录内、许可文本与文件分离）**、**CCFA/研究自动化工具的锁死与"授权≠部署"误读**、**上游文档里与自研规则冲突的密钥配置/启发式评分/去不确定性/`allow_redirects` 下载，以及未来式版本号与固定审查日期**。

---

## 附：27 个 `.py` 逐文件索引（均已完整通读）

| 组件 | 文件（行数） |
|---|---|
| codex-skill-installer | `github_utils.py`(21)、`install-skill-from-github.py`(308) |
| evil-read-arxiv/start-my-day | `common_words.py`(43)、`scan_existing_notes.py`(260)、`link_keywords.py`(307)、`search_arxiv.py`(1213) |
| evil-read-arxiv/paper-search | `paper_hunter.py`(218) |
| evil-read-arxiv/paper-analyze | `generate_note.py`(510)、`resolve_source.py`(568)、`update_graph.py`(144) |
| evil-read-arxiv/extract-paper-images | `extract_images.py`(504) |
| evil-read-arxiv/conf-papers | `search_conf_papers.py`(799) |
| kdense/hypothesis-generation | `_common.py`(412)、`lint_causal_claims.py`(189)、`check_operationalization.py`(237)、`validate_prediction_matrix.py`(286)、`audit_evidence_ledger.py`(337)、`generate_preregistration_scaffold.py`(384)、`check_falsification_controls.py`(455)、`validate_hypothesis_schema.py`(1078) |
| kdense/scientific-brainstorming | `_common.py`(317)、`session_scaffold.py`(248)、`evaluate_matrix.py`(553)、`validate_register.py`(636) |
| nature-figure | `audit_figure_collisions.py`(742)、`audit_panel_alignment.py`(933) |
| watermarks-remover | `text_unicode.py`(730) |

40 个 `.md` 已逐份提取结构（frontmatter + 全部标题 + 关键声明），其中 `kdense/hypothesis-generation/SKILL.md`、`watermarks-remover/SKILL.md`、`references/detectors.md`、`ars-codex/evidence-row-protocol.md`、`ars-review/*`、`paperspine/*`、`nature-methods/*` 已读正文；配置/模板/许可类文件全部读取内容。
