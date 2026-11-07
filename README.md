# Doctoral Research OS v2.3.0

项目把宽领域探索、博士选题、六篇独立论文和投稿准备接入同一证据与费用记录。
G1 博士选题、G2 逐篇选题由您决定；之后新组合按 P01 的 G3→G4→G5、P02 的 G3→G4→G5 推进。
计划、数据快照和运行登记使用 `experiments/papers/Pxx/`，主张使用 `claims/papers/Pxx/claim-evidence.csv`。
已执行或封存的旧协议保留原记录；真实来源、权利、冻结输入、失败和阴性结果、累计费用及写入权限继续适用。

普通周期为只读规划→写入→一次独立批评；实际问题才触发修订与复审。最终投稿检查使用三个不同模型家族的互盲来源视图，
冻结各自意见后综合，保留分歧。A 科学完整性失败阻断；B 期刊/模板/导出检查在最终准备时完成并绑定未变快照；
C 分数、编辑、语言和格式观察显示为警告。没有强制两轮模拟审稿、全量 CFH/H/AD 处置表、固定证据过期日、
期刊 AI 政策门禁或 Q1/Q2/IF 放行门槛。原有期刊目标仍为规划目标；实际分区不能伪造，已有披露不能偷偷删除。

探索如实保留未饱和、未知和反证，正式选题仍须真实比较与博士贡献依据。有限探索仍走封存 G3 和原执行器，
结果回同篇 G3；正式验证另立协议并记录已见结果。科学写作与最终投稿准备分流，不把软件检查或模型同意当科学有效。
具体权威规则见[工作流](references/workflow.md)、[阶段契约](references/stage-contracts.md)和[需求追踪](config/requirements-traceability.json)。

附件要求已合并到既有记录：逐主张全文证据三态、15% 抽检、独立引用差异、创新性比较、失败记忆，以及渐进式
`research-case.json` 的贡献、关键检验、图件、期刊匹配、复现、预印本/返修/改投准备。它们不自动发布或投稿。
已取得 24 篇有独立许可证据的真实公开评审论文，云端可重放。真实 0.85 一致性、领域校准和六篇博士质量论文仍需实际研究验收；40–50% 精简是未经证实的历史估计。
本轮没有运行付费研究、切换既有模型/档位或宣布这些科研结果已实现。

模型与通道见[正式路由](docs/PRODUCTION-MODEL-ROUTING.md)，累计总额与全部尝试计费见[费用政策](docs/TOTAL-COST-POLICY.md)。
按当前任务加载[CCFA 指导](docs/CCFA-INTEGRATION.md)，完整原版仍可按需读取；检索与[科学推理](docs/SCIENTIFIC-REASONING.md)
服务于证据决策，既有[编辑工具](docs/EDITORIAL-SKILLS.md)服务于针对性改善，不新增付费审查层。

## 云端运行（无需本地科研运行环境）

Codex Cloud 的可复用开发环境使用 [`docs/CODEX-CLOUD.md`](docs/CODEX-CLOUD.md) 和
`bash scripts/bootstrap-codex-cloud.sh`。它安装代码维护、文献处理、绘图和文档导出工具；
正式科研作业继续使用下述 GitHub Actions 入口与既有证据、预算和实验控制。

通过 Codex 管理仓库所有者授权的 GitHub 云端作业。GitHub Actions 完成依赖安装、受控文献检索、许可检查后的数据获取、G3 封存后的 Docker 实验、检查点恢复和论文导出。API 使用当前配置的项目累计总额度，默认 300 元；不再设单篇额度或固定追加阶梯。持续运行在总额度不足、G1/G2 选题决定或实际资料缺失时暂停；待核对费用有可计算上限且总额仍足够时可继续。

中转站密钥到位后的配置清单、免费启动检查和立即启动入口见 [`docs/GATEWAY-STARTUP.md`](docs/GATEWAY-STARTUP.md)，支持 OpenAI 与 Claude 使用独立地址和密钥。

入口与配置见 [`docs/CLOUD-RESEARCH.md`](docs/CLOUD-RESEARCH.md)，本轮修复、验收与仍需真实配置的项目见 [`docs/CLOUD-READINESS-REPAIRS-2026-10-01.md`](docs/CLOUD-READINESS-REPAIRS-2026-10-01.md)，模型可请求的云端操作见 [`references/cloud-operations.md`](references/cloud-operations.md)。下面的 D 盘/WSL2 安装是可选旧入口，不是本项目的前置条件。

新增的 37 类科研绘图、类型化研究架构图、协议/双人筛选/偏倚风险/PRISMA 导出、Zotero Local API 与 Obsidian 图、本地 PDF/PPT、paper-facts/测量/段落/符号审查、审稿 concern cards 与编辑摘要、健康感知分层模型路由、真实 DOCX 和独立 Skill/MCP 管理，见 [`docs/NEW-CAPABILITIES.md`](docs/NEW-CAPABILITIES.md)。均为现有 G0–G5 控制层的增量能力；未运行的真实 API、用户账号、人工筛选和六篇实际论文不会被宣称为已完成。

P0/P1 的已实现项、实机验收项和仍需实际科研执行的边界见 [`docs/P0-P1-COMPLETION.md`](docs/P0-P1-COMPLETION.md)，机器可读追踪表见 `config/requirements-traceability.json`。

面向个人研究者的、可审计且有人类闸门的博士研究流水线。Claude/OpenAI API 是可选的模型层，Claude Code/Codex CLI 是可选的本地 Agent Runtime，本地 Python 控制层负责状态、许可、预算、哈希、实验登记、引用与期刊合规检查。

“一键”指：创建或恢复项目，运行当前阶段的 只读规划 → Codex写入 → 一次独立批评流程；实际问题触发修订/复审，最终投稿使用三家族互盲 panel，通过检查后自动推进；G1 博士选题、G2 逐篇论文选题等待真实人工决定。数据许可、费用或实验事实缺证据时保持阻塞，不凭空补齐，也不自动投稿。既有逐任务模型、路由和推理档位保持原样。

## 能力与规则

- [阶段与论文执行](references/workflow.md)：正式流程保留六篇共同博士问题与逐篇价值，G2 完成整体架构及各篇选题决定后，逐篇推进 G3–G5；低层少量论文测试夹具不扩大正式支持范围。
- [科研质量与证据](references/stage-contracts.md)：探索、正式验证、科学写作与投稿的适用要求；G1/G2 人工选题，其他阶段以当前证据和自动检查决定。
- [创新性与审查依据](docs/REVIEW-REMEDIATION.md)：1.1 来源绑定比较、真实检索处置、当前独立创新性判断与 1.2 逐项事实判断；未知或科学异议不能靠自评分消除。
- [数据使用权](docs/AUTOMATED-DATA-RIGHTS.md)与[研究质量工具](docs/RESEARCH-QUALITY.md)：实际来源、哈希、功效、预注册和复现。
- [正式模型与费用](docs/PRODUCTION-MODEL-ROUTING.md)：既有模型分工、身份核查、累计总额及全部尝试。
- [写作与图件](docs/NEW-CAPABILITIES.md)：真实结果、英文正文、可编辑图件、引用、修订和视觉检查。
- [投稿准备](docs/PUBLICATION-DISCLOSURE.md)：真实作者/伦理记录、已有披露保全和外部提交边界。

工程验收不代表科学有效、博士资格或期刊录用；当前状态与缺项以项目证据为准。

## 推荐架构

```text
                    Doctoral Research OS
                             |
                 Python deterministic control plane
                             |
       +---------------------+---------------------+
       |                     |                     |
   Claude API            OpenAI API          Local deterministic tools
   plan/audit only       persistent writing   experiments + chart rendering
       |                     |                     |
       +---------------------+---------------------+
                             |
             state / evidence / hashes / gates
                             |
                venue compliance / submission ZIP
```

Claude Code 和 Codex CLI 保留为可选高级接口；系统的科研状态和安全边界不依赖某一个 CLI。

## 安装

Windows 11 推荐 WSL2 Ubuntu。本项目按用户要求采用严格 D 盘策略：仓库、虚拟环境、缓存、WSL2、交换文件与 Docker 数据都位于 `D:\ad\lunwen`。先按 [`docs/WSL2-D-DRIVE.md`](docs/WSL2-D-DRIVE.md) 设置 WSL/Docker，再运行安装脚本。

```powershell
New-Item -ItemType Directory -Force D:\ad\lunwen
Set-Location D:\ad\lunwen
git clone https://github.com/hengyizang/lunwen.git .
powershell -ExecutionPolicy Bypass -File .\scripts\install-d-drive.ps1
```

```bash
cd /mnt/d/ad/lunwen
bash scripts/bootstrap-d-drive.sh
```

可选安装本地英文 prose linter（BSD-3-Clause，精确锁定 v0.16.0）：

```bash
cd /mnt/d/ad/lunwen
bash scripts/bootstrap-wsl.sh --with-writing-tools
```

它会把固定版本的 `proselint` 放入仓库自己的 `.venv`，控制层会自动发现，无需每次手工激活。若系统中另有 `harper-cli`，控制层也会自动调用。未安装任一可选工具都不影响内置审计或 G5；系统会在界面分别显示状态。

在 G3 前安装可执行统计功效工具：

```bash
bash scripts/bootstrap-wsl.sh --with-research-quality-tools
```

该选项把固定版本 `statsmodels==0.15.0` 安装到仓库 `.venv`。数据哈希、缺失、重复、类别失衡和跨划分泄漏检查由无依赖本地核心完成；`fg-data-profiling`、Pandera、Evidently 和 DVC 是经过固定提交审查的可选增强层，不替代核心闸门。

按课题启用 PaperQA2 与 ToolUniverse 实际执行适配器：

```bash
bash scripts/bootstrap-wsl.sh --with-ai4science
```

该选项安装锁定的 `paper-qa==2026.08.12` 与 `tooluniverse==1.5.1`，要求 Python 3.11+。公开文献 API、WSL2、Docker 真实验收和两个适配器的命令、证据位置与失败语义见 [`docs/LIVE-ACCEPTANCE.md`](docs/LIVE-ACCEPTANCE.md)。GitHub Actions 的确定性与 live job 边界见 [`docs/CI-VALIDATION.md`](docs/CI-VALIDATION.md)。

安装确定性高级科研绘图栈：

```bash
bash scripts/bootstrap-wsl.sh --with-figures
```

图表由 `scripts/publication_figures.py` 从 CSV/TSV/JSON 实验表渲染，默认同时输出 SVG、PDF 和高分辨率 PNG。完整命令、SciencePro 导入、开放全文解析和模型成本控制见 [`docs/RESEARCH-CAPABILITIES.md`](docs/RESEARCH-CAPABILITIES.md)。

安装摘要级 DOI claim 核验器：

```bash
bash scripts/bootstrap-wsl.sh --with-reference-tools
```

它固定安装 `ref-verify==1.2.0`。使用 `scripts/ref_verify_adapter.py` 生成哈希绑定报告；该报告不会把摘要核验夸大为全文核验。

CLI 模式需要分别安装并登录 `claude` 与 `codex`。API-first 模式不需要它们；只需要相应 API key。仓库不保存 API key。

可选的 K-Dense 通用科研技能子集：

```bash
bash scripts/bootstrap-wsl.sh --with-kdense
```

该选项只安装锁定提交中的筛选子集，默认不开启。许可、固定版本和边界见 `references/upstream-components.md`。

## 本地可视化客户端（新手推荐）

无需安装 Node、数据库或桌面框架。在 WSL2 项目目录运行：

```bash
bash scripts/start-dashboard.sh
```

客户端默认只监听本机 `127.0.0.1:8765`，并尝试自动打开 Windows 浏览器。若浏览器没有自动打开，请访问：

```text
http://127.0.0.1:8765
```

在“API 设置”中输入 UUAPI 地址、Key、Claude 模型 ID 和 GPT/Codex 模型 ID。Key 只保存在当前 Python 进程内存中，页面不会读回密钥，关闭终端即清除。客户端覆盖：

- API 配置检查、计费探针与余额查询；
- 项目创建、阶段运行、闸门检查、`ready/reopen/approve/advance`；
- G1/G3 自动执行八类数据源的多查询并行检索与候选排序，页面仍可手动补充搜索；
- 数据清单验证、许可证确认后的安全下载；
- 已批准实验执行、实时日志、Token 与完成度监控；
- 新颖性矩阵、数据质量及来源绑定确认、统计功效、预注册、强基线复现和隔离复现状态；
- 六篇论文的顺序状态和本地投稿 ZIP。

完整说明、安全边界和故障处理见 [`docs/DASHBOARD.md`](docs/DASHBOARD.md)。CLI 仍然保留，并与客户端共享完全相同的项目状态。

新颖性、数据质量、可执行功效、预注册、基线复现和隔离复现的完整操作见 [`docs/RESEARCH-QUALITY.md`](docs/RESEARCH-QUALITY.md)。

## 入口与恢复

正式云端入口、既有模型与推理档位以 [正式路由配置](docs/PRODUCTION-MODEL-ROUTING.md) 和 [持续云端研究](docs/CONTINUOUS-CLOUD-RESEARCH.md) 为准。运行前后可用零模型调用的状态命令查看当前篇与缺口：

```bash
python3 scripts/researchctl.py status --project my-phd --json
python3 scripts/researchctl.py gate-check --project my-phd
```

独立配置的 API-first 兼容入口见 [API-FIRST.md](docs/API-FIRST.md)；`scripts/start.sh` 当前兼容默认仍使用 UUAPI，不是正式 CheapAI＋CodeKey 云端入口。只有明确选择本地 CLI 时才用 `scripts/start.sh --cli` 或 `autopilot.py`，命令和限制见 [CHAT-USAGE.md](docs/CHAT-USAGE.md)。这些入口共用同一状态、权利、累计预算、实验执行器和独立审查，不会提供额外额度或代填 G1/G2 选题决定。

## 阶段决定

| 闸门 | 决定方式 | 通过后允许 |
|---|---|---|
| G0 | 系统检查已提供的目标、时间、预算和资源；金额授权独立保留 | 选题情报 |
| G1 | 人工确认博士选题；系统检查三个以上候选、最近工作差异、检索饱和、原创性风险、A/B 命题和博士论证 | 论文组合架构 |
| G2 | 人工逐篇确认选题；系统仍检查独立性、博士主线和期刊组合 | 数据与实验设计 |
| G3 | 系统检查当前篇的许可、质量、设计、适用功效、预注册和累计预算，封存方案 | 执行该篇锁定计划 |
| G4 | 系统核验当前篇全部尝试、负结果、主张证据、基线和隔离复现 | 该篇结果约束写作 |
| G5 | 独立模型审计、引用和数值核验、实际渲染视觉检查、披露和期刊规则检查 | 标记该篇就绪；下一篇进入 G3 |

查看状态和精确缺口：

```bash
python3 scripts/researchctl.py status --project my-phd --json
python3 scripts/researchctl.py gate-check --project my-phd
```

`approve` 只用于 G1/G2 选题。G2 必须传入具体论文，例如
`python3 scripts/researchctl.py approve --project my-phd --gate G2 --paper P01 --actor "Owner"`。
其他阶段 `ready` 通过检查后产生机器决定，由既有续跑执行 `advance`。系统不自动投稿。

## 数据发现与获取

公开元数据发现：

```bash
python3 scripts/data_discovery.py "structural vibration anomaly detection" \
  --limit 10 \
  --project my-phd \
  --output projects/my-phd/data/discovery-vibration.json
```

发现报告不是许可结论。选中数据后，按官方记录、研究用途、隐私、版本、来源与泄漏风险创建符合 `schemas/dataset-manifest.schema.json` 的清单，并通过受保护的权利证据检查；缺证据时停止获取。

```bash
python3 scripts/dataset_fetch.py validate path/to/dataset.json
python3 scripts/dataset_fetch.py download \
  path/to/dataset.json projects/my-phd/data/raw --accept-license
```

下载只接受公网 HTTPS，不携带登录凭据，不绕过付费墙、验证码或访问控制；原始数据不进入 Git。

## 实验执行

当前论文在 `papers/Pxx/experiments/` 下建立一份或多份 JSON 设计文件，均符合 `schemas/paper-experiment-design.schema.json`；其中的假设、数据集、设计 ID、种子和运行 ID 必须分别与论文 contract、源数据清单快照及 `experiments/papers/Pxx/plan.json` 完整对上，不允许遗漏或重复分配运行。每个基线还要记录原始来源、年份、实现版本、许可和调参预算，并说明公平比较协议。当前计划与 `experiments/papers/Pxx/budget.json` 一起通过 G3 自动检查并封存；预算声明不增加项目总额度，也不形成单篇金额限制。已封存或执行的旧批量项目继续使用原 `experiments/plan.json` 与 `experiments/budget.json`。示例单次运行：

```json
{
  "run_id": "P01-baseline-seed-7",
  "paper_id": "P01",
  "argv": ["python3", "experiments/code/train.py", "--seed", "7"],
  "cwd": ".",
  "seed": 7,
  "timeout_seconds": 7200,
  "estimated_cost_usd": 0,
  "inputs": [{"path": "data/processed/split.parquet", "sha256": "<64 hex>"}],
  "expected_outputs": ["results/P01/P01-baseline-seed-7.json"]
}
```

执行全部或指定运行：

```bash
python3 scripts/experiment_runner.py --project my-phd
python3 scripts/experiment_runner.py --project my-phd --run P01-baseline-seed-7
```

计划或预算在 G3 后被修改会被拒绝。运行器不是恶意代码沙箱：它只执行你已经批准的本地研究代码，并通过无 shell 调用、可执行文件白名单、项目内路径、精简环境、超时和预算减少误操作。

G4 的 `claims/papers/Pxx/claim-evidence.csv` 必须逐项覆盖当前篇 `paper-contract.json` 中的唯一 claim ID；标记为 `supported` 或 `partially_supported` 的主张必须引用至少一个成功的 `analysis_ids`，且对应输出文件的当前哈希必须与该篇实验登记一致。旧批量协议沿用其原主张矩阵和范围。

## 确定性图表与来源

Codex 可以编写绘图脚本，但 Claude 不得写最终图、图中文字或图注。用本地脚本从已登记结果生成图后，登记其输入、运行和渲染器：

```bash
python3 scripts/figure_provenance.py record \
  --project my-phd --paper P01 \
  --figure papers/P01/figures/result.png \
  --type data_chart \
  --renderer experiments/code/render_p01.py \
  --input results/P01/P01-metrics.csv \
  --run P01-primary-seed-7 \
  --language-checked-by 'your-name'

python3 scripts/figure_provenance.py validate --project my-phd --paper P01
```

`--language-checked-by` 兼容历史真实人工英文检查记录；主流程使用基于实际渲染的自动视觉检查。人工名字或模型断言均不能替代当前文件、逐页观察及对应来源和费用回执。

渲染脚本也必须有当前非 Claude 来源。若是你独立编写或彻底独立改写的文件，可作具名人工证明（这不是密码学证明，责任由证明者承担）：

```bash
python3 scripts/output_provenance.py attest \
  --project my-phd --actor 'your-name' \
  --note 'Independently authored/reviewed; not derived from Claude text' \
  --path experiments/code/render_p01.py
```

## 引用与期刊合规

2026-09-30 新增的云端研究方法包括：先精读论文再生成候选假设、比较竞争解释与证伪检验、明确允许/禁止的论证边界，以及按研究类型逐项追问的投稿前清单。它们已接入 API/CLI 规划、写作、审查与 G1/G5 验收；原生图表同时检查面板对齐和 PDF 文字碰撞。安装范围、调用方式、来源与许可证见 [研究方法整合说明](docs/RESEARCH-METHODS-INTEGRATION.md)。

```bash
python3 scripts/citation_audit.py \
  projects/my-phd/papers/P01/manuscript/references.bib \
  --output projects/my-phd/papers/P01/reviews/citation-audit.json
```

无 DOI 的来源优先复用实际检索回执比对书目身份；缺证据时保持未核验。历史真实人工核验 JSON 仍可通过 `--manual-verifications` 传入，每条包含 `verified_by`、`verified_at`、`source_url` 和 `title`，不新增人工审核要求。
DOCX 无法像 TeX 一样自动解析引用键，审阅者逐条核对正文引用与文末记录后还必须传入 `--docx-citations-verified-by 'your-name'`；否则 G5 保持关闭。

从期刊官方页面下载模板 ZIP 后：

```bash
python3 scripts/venue_adapter.py inspect ~/Downloads/ijssd-2e.zip
python3 scripts/venue_adapter.py ingest \
  ~/Downloads/ijssd-2e.zip projects/my-phd/papers/P01/venue-template
python3 scripts/venue_compliance.py projects/my-phd/papers/P01
python3 scripts/manuscript_language.py projects/my-phd/papers/P01/manuscript/main.tex
python3 scripts/academic_style.py audit --project my-phd --paper P01
```

最后一条命令也可以在本地客户端 G5 区域点击“重新运行表达检查”。
它生成 `papers/P01/style/academic-style-audit.json`。状态为 `revise` 时，查看
`errors` 和 `warnings` 后让 Codex 依据真实论证重新修改；不要机械替换同义词。
内置 GitHub 来源规则的行级结果位于
`analysis.formulaic_pattern_findings`；若安装了 `proselint` 或 Harper，其建议位于
`external_linters[].diagnostics`。所有结果只作证据约束下的定向修改，不作为
通用同义词替换；本项目关闭了 proselint 中可能压掉科学不确定性的 `hedging`
检查。
任何稿件源文件变化都会使旧报告失效。报告不预测 Turnitin、GPTZero 或其他
检测器，也不能证明文本由人独立撰写。

首个适配样例是 IJSSD，但只是模板试验目标，不代表所有论文都应投稿该刊。仓库中的指标明确标记为出版社报告；当前分区/指标须由合法实际来源支持，缺则 unknown，不作为放行门槛；最终 B 检查绑定真实期刊范围、文章类型、模板与导出来源，不设期刊 AI 政策关卡。最终正文及所有投稿相关文本必须为英文。

## 人工投稿包

当某篇论文已经通过其 G5 自动检查并在状态中标记为 `submission_ready` 后，可生成本地投稿材料包：

```bash
python3 scripts/submission_package.py --project my-phd --paper P01
```

默认输出为 `projects/my-phd/papers/P01/submission/manual-upload.zip`。其中只包含稿件、参考文献、最终图表、补充材料和你放入 `submission-materials/` 的真实门户文件；内部 paper contract、JCR 证明、披露工作表、模拟审稿、回复矩阵、引用审计与合规报告不会混入期刊上传包。同时生成逐文件 SHA-256、写入来源摘要的 `SUBMISSION-MANIFEST.json` 和 `MANUAL-CHECKLIST.md`。每个文件必须有当前非 Claude 来源；影响已绑定科学材料或投稿来源的变化会使旧检查失效并要求重算，不新增人工审批。

打包器拒绝符号链接、隐藏文件和密钥类文件，不包含原始数据、期刊模板归档、运行日志或实验原始产物。ZIP 只是整理工具；作者仍需逐项核对、手动上传、预览门户生成稿并最终确认提交。

## 验证

新增的八组增量覆盖段落论证计划、证据来源链、研究 Gap、文献接收凭证、
失败规则验证与人工采用、跨论文依赖、最小必要编辑与授权写作样本、章节上下文和成本交接。
使用方式与边界见 [八组科研增量](docs/RESEARCH-INCREMENTS.md)。
所有运行和验证继续在授权云端执行；模型分工与推理档位保持不变，
不新增付费轮次，也不将工程检查通过等同于科研完成。

```bash
python3 -m compileall -q scripts
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
```

CI 同时执行编译、单元测试和仓库结构验证。

## 目录

```text
.agents/skills/       Codex 仓库技能
.claude-plugin/       Claude Code 插件清单
agents/               有边界的专职代理
config/               默认值与机器可读阶段任务
docs/                 API-first 架构和操作说明
references/           流程、阶段合同与科研诚信规则
schemas/              数据、实验、审核、期刊与证据格式
scripts/              API/CLI 编排器、状态机、发现、执行与审计工具
venues/               期刊清单（需在 G5 复核）
```
# Literature discovery and reading

The five project-native evil-read-arxiv skills provide public literature discovery,
provisional topic leads, authorized full-text cards, original figure extraction,
existing-note search and linked reading views. See
[the cloud literature workbench](docs/LITERATURE-WORKBENCH.md) for installation,
inputs and the evidence/budget boundaries. Abstract keywords remain explainable
discovery signals; they do not assess our manuscript's scientific quality.

