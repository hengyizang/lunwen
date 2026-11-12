# 让第三方工具真正服务科研：可选工具箱

> **本文件全篇是可选参考，不是流程。** Owner 决定
> `owner-2026-11-09-maximum-flexibility`（`docs/OWNER-DECISION-2026-11-09-MAXIMUM-FLEXIBILITY.md`）
> 明确：工具选择、跑在哪里、调用哪个 GitHub 项目或 skill、先后顺序、运行时长
> 全部自由；决策点映射、对照、采纳台账、`register`/`scaffold`/`wrap`/`compare`/
> `adopt`/`promote` 都是**想用才用**的工具，任何一条都可跳过。
> 想直接跑任意项目或 skill 且不登记，用 `scripts/third_party_runtime.py free`。

Owner 决定 `owner-2026-11-09-effect-first` 之后，接入与运行环境都不再是瓶颈。
下面是**一种**能提高工具产出的思路，供需要时取用：**接进来之后，怎样让工具
真的改变科研结果。**

## 为什么「接了」不等于「用上」

仓库已有 `docs/RESEARCH-AUTOMATION-COVERAGE.md` 与
`integrations/research-automation-coverage.json`，把 11 个上游的**方法**吸收成了
原生脚本与测试。但 `integrations/upstreams.lock.json` 里 46 个登记源只有 10 个
真正执行过。缺的不是接口，是三件事：

1. 工具没有绑定到**具体科研判断**（哪个 G 阶段、哪条 claim、哪张图）。
2. 没有在**同一真实输入**上跑多个工具——单个工具的产出无法判断好坏。
3. 没有**采纳/淘汰记录**，于是不知道哪个工具真改变过结论，只能一直堆。

「最大限度发挥」= 把工具从「可调用的程序」变成「围绕决策、可对照、可淘汰的
证据候选生产者」。

## 五个杠杆

| # | 杠杆 | 做法 |
|---|---|---|
| 1 | **决策点驱动** | 先列出当前要做的判断（选题差异、基线选择、图件论点、期刊范围），再反向选工具。不要按 star 数或工具清单选。 |
| 2 | **同输入对照** | 同一份真实项目输入，跑 2–3 个工具 + 一个原生基线。**分歧就是信息**：新来源、新反证、被忽略的阴性结果。绝不投票、平均或自动合并。 |
| 3 | **输出落字段** | 每个工具事先写明输出进哪个产物（`evidence/candidates/`、差异矩阵、figure spec、venue 匹配表）。没有落点就别跑。 |
| 4 | **常驻重跑** | 用 dots 定时/事件触发重跑：新论文出现、输入哈希变化、工具 ref 变化、证据变化、期刊页面更新。一次性调用的价值最低。 |
| 5 | **采纳台账** | 记录哪个工具在哪个决策上被 `adopted` / `rejected` 及理由。连续两次未产出新信息就停用，保留记录但不再调用。 |

## 决策点 → 工具 → 环境 → 落点 → 有效性判据

| 决策点 | 要改变什么判断 | 候选工具 | 跑在哪 | 输出落到 | 怎么算有效 |
|---|---|---|---|---|---|
| **G1 博士选题** | 最近工作差异、检索饱和、原创性风险 | deer-flow、gpt-researcher、EvoScientist + 原生 `literature_evidence.py` / `research_frontier.py` | **dots 常驻**（浏览器 + 长任务）；纯 CLI 可 Codex Cloud | `evidence/candidates/` → G1 差异矩阵、`research-case.json` | 找到至少一条此前未记录的真实反证或最接近工作，带 URL + 访问日期 |
| **G2 逐篇选题** | 论文独立性、与博士主线映射 | deer-flow 方法/代码审查、AI-Scientist 分支思路 | dots / Codex Cloud | `paper-map.json` 的 `independence_basis`、假设登记 | 出现一个可检验的判别性预测，而非又一个主题标签 |
| **G3 实验设计** | 基线选择、预注册、功效、证伪条件 | statsmodels、RD-Agent、pi-autoresearch、AutoResearchClaw | **Actions Docker job** 或自备 VM | `plan.json`、`budget.json`、预注册与假设登记 | 与原生设计对照后补出缺失基线、泄漏风险或证伪条件 |
| **G4 结果约束** | 哪些结果支持/反驳 claim | RD-Agent、AutoResearchClaw、原生 `research_iteration.py` | Actions（正式实验）/ dots（诊断） | `experiments/archive/`、`claim-evidence.csv` | 发现一个此前被忽略的失败或阴性结果 |
| **G4–G5 图件** | 主图论点、图文数值一致、面板对齐 | PaperBanana、aipoch + 原生 `figure_story.py` / `publication_figures.py` | **dots**（GUI 工作台）/ 本地 | figure spec、`figure_provenance` | 语义/视觉审查指出一个真实不一致，而非只换了配色 |
| **G5 期刊匹配** | 范围、文章类型、模板、当前 AI 政策、分区证据 | dots 浏览器直查官方页 + 原生 `journal_screening.py` / `venue_compliance.py` | **dots 浏览器** | venue 匹配表、投稿前清单、G5 材料包 | 找到官方页上与当前稿件不匹配的硬性要求 |
| **写作与独立批评** | 逐主张证据、术语/符号/数值一致 | 原生 `manuscript_audit.py` / `academic_style.py` + 不同模型家族 critic | Actions / 现有 API cycle | 行级发现、concern cards | 独立批评提出可操作的具体异议 |

> 「有效性」一律按**是否改变了某个判断**衡量，不按运行成功、产出文件大小或
> 工具自评分衡量。工程验收不等于科学有效。

## 对照运行实操

```bash
# 1) 登记两个服务于同一决策点的工具
python3 scripts/third_party_runtime.py register --id deer-flow --repo <url> --ref main --tier network-no-credentials --license MIT
python3 scripts/third_party_runtime.py register --id gpt-researcher --repo <url> --ref main --tier network-no-credentials --license Apache-2.0

# 2) 各自 scaffold，然后用**同一份真实输入**跑
python3 scripts/third_party_runtime.py scaffold --id deer-flow --kind launch
python3 scripts/third_party_runtime.py wrap --id deer-flow --input evidence/query.json --execute
python3 scripts/third_party_runtime.py wrap --id gpt-researcher --input evidence/query.json --execute

# 3) 对照：保留分歧，不投票
python3 scripts/third_party_runtime.py compare \
  --receipt reports/third-party/receipts/<A>.json \
  --receipt reports/third-party/receipts/<B>.json \
  --decision "G1 最接近工作与反证" --stage G1

# 4) 人工看过差异后记录采纳，并把有用的输出推进候选证据
python3 scripts/third_party_runtime.py adopt --comparison reports/third-party/comparisons/<C>.json \
  --tool-id deer-flow --verdict adopted --reason "找到两条未记录的竞争工作" --by Owner
python3 scripts/third_party_runtime.py promote --id deer-flow \
  --receipt reports/third-party/receipts/<A>.json --authorized-by Owner
```

`compare` 报告记录 `same_input`、各回执的 `input_sha256` / `output_sha256`、
输出分组、`agreement_count`、`distinct_output_count`，并固定 `adoption: pending`。
它**不做合并、不打分、不自动采纳**。`adopt` 记录 `verdict`、理由、owner 与对照报告
哈希，形成「哪个工具真有用」的台账。

## 常驻重跑（dots 最该做的部分）

给 dot 设这些触发条件，而不是只跑一次：目标领域新论文出现；任一输入哈希变化；
工具 ref / 版本变化；`claim-evidence.csv` 有新增或撤回；目标期刊官网更新范围或
模板。每次重跑都生成新回执与新对照报告，旧记录保留（规则 9）。dot 的
Activity View 只作观察，回执才是仓库认的东西。

建议给 dot 的 Custom Rule：**只产出候选、对照与回执，不自行批准任何阶段**。

## 三个最快见效的切入点

1. **G1 最接近工作 + 反证检索** — 对创新性影响最大，且只需浏览器 + 检索，
   不需要 Docker/GPU/密钥，dots 立刻能干。
2. **G4–G5 图组论证对照** — 对审稿观感影响最直接，PaperBanana/aipoch 的语义
   审查与原生 `figure_story` 对照，最容易拿到可见改进。
3. **G5 目标刊官方页匹配** — 用 dot 浏览器核对范围/文章类型/模板，
   能直接拦下「写得不错但投错刊」的损失。

如果某次想稳一点，**一个决策点、2–3 个工具、一份真实项目输入**通常更容易看出
效果；但这只是经验建议，不是限制。想一次铺开、临时换工具、换环境、或不记录任何
东西，都按 owner 的最大灵活决定直接做。
