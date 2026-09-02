# Doctoral Research OS v1.5.1

面向个人研究者的、可审计且有人类闸门的博士研究流水线。Claude/OpenAI API 是可选的模型层，Claude Code/Codex CLI 是可选的本地 Agent Runtime，本地 Python 控制层负责状态、许可、预算、哈希、实验登记、引用与期刊合规检查。

“一键”指：创建或恢复项目，运行当前阶段的 Claude只读规划 → Codex写入 → Claude独立审查 → Codex修订 → Claude终审流程，通过确定性检查后停在下一道人类审批闸门。它不代表自动批准选题、自动确认数据许可、自动产出真实实验结果或自动投稿。

## 已实现的闭环

- G0–G5 状态机和显式人类审批；G0 不允许把未知时间、预算和设备仅改成 `ready` 后通过；`ready` 与 `approve` 之间以及批准后的任何产物变化都会由哈希锁检测。
- 默认 6 篇论文；G5 按 P01 → P06 逐篇完成，全部通过后才进入 `submission-ready`。
- G1 强制最接近的 5 项既有研究、3 个相邻领域、反证与剩余原创性风险；G2 对全部论文两两检查，六篇时必须覆盖 15 组比较，阻止“切香肠”。
- G3 要求每篇论文单独提交实验设计：简单/领域标准/强近期基线、消融、泄漏控制、效应量与区间、多重性、功效或精度、随机种子、稳健性、负对照、外部有效性、停止和证伪规则。
- 候选与最终期刊均要求当前 JCR Q1 SCI/SCIE；JCR 分区必须按年份和类别人工核验。
- 最终题目、摘要、正文、图表标题、补充材料、回复信和投稿材料必须使用英文；G5 对主稿和全部投稿目录文本执行确定性语言检查。
- Claude Code 只有只读规划/审查权限；不可写项目产物。Codex 负责持久文本、修订和绘图代码；本地确定性工具从真实数据渲染图表。
- 每个模型调用都有超时、输出上限、断点日志和敏感环境值脱敏；独立终审未通过时闸门保持关闭。
- API-first 模式：无需 Claude Code/Codex CLI 即可运行 Claude语义计划与OpenAI/Codex持久写入；模型生成文件受路径、大小、状态文件、审稿文件和凭据保护约束。
- 输出来源登记：控制层保存文件哈希、写入模型家族、供应商和角色；程序拒绝Codex持久产物中复制Claude计划/审查的长原文片段。每个最终上传文件必须有当前 Codex、本地工具或明确人工证明的来源；未登记、登记后修改或Claude/Anthropic来源都会阻止 G5 与打包。
- UUAPI 原生适配：Anthropic Messages 只读规划/审查与 OpenAI Responses 持久写作角色、HTTPS/路径保护、外部调用 User-Agent、余额查询、模型 ID 严格核对和可审计运行清单；CC Switch 可作为可选可视化管理面板。
- DataCite、Zenodo、Hugging Face、OpenML、Figshare、Dryad、Harvard Dataverse、Data.gov/CKAN 八类官方数据接口的并行检索、跨查询去重和元数据相关度初筛；候选许可和科学适用性始终标记为需要人工核验。
- 本地可视化研究驾驶舱：浏览器内配置临时 API 会话、创建项目、运行 G0–G5、监控任务/Token/实验/缺项、搜索数据、执行人工闸门和生成投稿包；密钥不写入仓库或客户端存储。
- 数据清单验证、人工许可确认、SHA-256，以及对私网/回环/带凭据 URL 和不安全重定向的拒绝。
- G3 批准后的实验计划哈希锁定、无 shell 命令执行、预算硬上限、超时、输出哈希，以及成功/失败/超时的统一登记。G4 会复核每次运行与批准计划、种子、论文、输出文件和当前哈希，并要求 claim matrix 精确覆盖全部论文 contract claim。
- BibTeX DOI 的 Crossref 核验、重复 DOI、标题和年份不一致检查；无 DOI 来源必须有人类核验记录。
- 出版商模板 ZIP 安全导入、文件完整性复核、稿件占位符/章节/篇幅检查，以及可用时的 `latexmk` 无 shell-escape 编译。
- 已通过单篇 G5 后生成确定性的人工投稿 ZIP、逐文件 SHA-256 清单和人工检查表；不访问期刊门户。

系统不会把模型一致意见当作科学验证。最终 PDF/DOCX、作者资格、伦理、数据权利、当年 JCR 信息和投稿门户仍由人确认。

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

Windows 11 推荐 WSL2 Ubuntu，并把仓库放在 Linux 文件系统（如 `~/code`），不要放在 `/mnt/c`。

```powershell
wsl --install -d Ubuntu
```

```bash
mkdir -p ~/code
cd ~/code
git clone https://github.com/hengyizang/lunwen.git
cd lunwen
bash scripts/bootstrap-wsl.sh
```

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
- 八类数据源的多查询并行检索与候选排序；
- 数据清单验证、许可证确认后的安全下载；
- 已批准实验执行、实时日志、Token 与完成度监控；
- 六篇论文的顺序状态和本地投稿 ZIP。

完整说明、安全边界和故障处理见 [`docs/DASHBOARD.md`](docs/DASHBOARD.md)。CLI 仍然保留，并与客户端共享完全相同的项目状态。

## API-first 模式（推荐长期使用）

配置环境变量：

```bash
export ANTHROPIC_API_KEY='...'
export ANTHROPIC_MODEL='你的当前Anthropic模型ID'
export OPENAI_API_KEY='...'
export OPENAI_MODEL='gpt-5.6'
```

检查：

```bash
python3 scripts/api_orchestrator.py health
```

执行阶段：

```bash
python3 scripts/researchctl.py init --project my-phd --paper-count 6
python3 scripts/api_orchestrator.py cycle my-phd intake \
  --planner-provider anthropic \
  --writer-provider openai \
  --critic-provider anthropic \
  --context 'AI + robotics/mechanical engineering; no laboratory; limited GPU.'
```

API 模式会把 Claude 语义计划、原始响应、结构化 bundle 和写入清单放在本地且被 Git 忽略的 `projects/<project>/api_runs/<run-id>/`。Claude计划不会写进普通科研文件；只有非Anthropic writer可以写项目产物。模型不能修改 `state/`、`api_runs/`、独立审稿记录、凭据、`.env`、隐藏文件，不能批准/推进闸门，也不能执行任意 shell 命令。

完整说明见 [`docs/API-FIRST.md`](docs/API-FIRST.md)。
v1.4 全链路要求追踪与剩余人工边界见 [`docs/AUDIT-V1.4.md`](docs/AUDIT-V1.4.md)。

使用 UUAPI + CC Switch 时，先阅读
[`docs/UUAPI-CC-SWITCH.md`](docs/UUAPI-CC-SWITCH.md)，完成非计费配置检查、余额查询和两次最小实时探针后，再运行真实研究项目。

## API 一键首次试跑

```bash
bash scripts/start.sh my-phd "目标、已有背景、每周时间、预算和设备条件"
```

该命令默认初始化 6 篇论文并用 `uuapi-anthropic` 只读规划/审查、`uuapi-openai` 持久写入。项目已存在时不会覆盖；按 `status` 显示的当前阶段手动运行 `api_orchestrator.py cycle`。

## 可选 CLI 启动与恢复

只有已经安装并配置 Claude Code 与 Codex CLI 时才使用：

```bash
bash scripts/start.sh --cli my-phd "目标、已有背景、每周时间、预算和设备条件"
```

预览下一次动作，不调用模型：

```bash
python3 scripts/autopilot.py plan --project my-phd
```

人类批准并继续：

```bash
python3 scripts/researchctl.py approve \
  --project my-phd --gate G0 --actor "Hengyi" --note "constraints reviewed"
python3 scripts/autopilot.py resume --project my-phd
```

批准前必须先运行 `gate-check` 和 `ready`；`ready` 后若修改任何工件，必须重新检查和 `ready`。
若 `ready` 后决定让模型继续修改，先显式退回并记录原因：

```bash
python3 scripts/researchctl.py reopen --project my-phd \
  --note 'Human review found issues requiring another model revision'
```

`resume` 只会跨越已经记录批准的闸门。若当前阶段仍缺证据或许可，它会保留检查错误并停下。运行日志在本地 `projects/<slug>/state/runs/`；最新断点摘要在 `state/autopilot.json`。

默认每次 Claude 调用上限为 5 美元，可显式下调：

```bash
python3 scripts/autopilot.py resume \
  --project my-phd --claude-max-budget-usd 2.00 --timeout 1800
```

`--claude-mode minimal` 使用 Claude Code 的 bare/minimal 模式；默认 `standard` 会加载仓库配置。Claude命令不开放 Write/Edit；Codex写入使用临时会话和 workspace-write，并由控制层检查受保护状态、审稿文件和输出来源哈希。

也可在 Claude Code 交互模式使用插件：

```bash
claude --plugin-dir .
```

```text
/doctoral-research-os:start my-phd
```

Codex 会发现 `.agents/skills/doctoral-research`。

## 人工闸门

| 闸门 | 人类批准的内容 | 通过后允许 |
|---|---|---|
| G0 | 目标、时间、预算、设备、地区、伦理边界 | 选题情报 |
| G1 | 三个以上候选、最近工作对照、原创性风险、核心命题 A、扩展命题 B、博士论证 | 论文组合架构 |
| G2 | 完整 paper map、全部论文两两独立性比较、每篇可证伪 contract 与两个当前 JCR Q1 候选 | 数据与实验设计 |
| G3 | 数据许可、SHA、每篇独立实验设计、可执行计划、统计功效/精度与预算 | 执行锁定计划 |
| G4 | 全部尝试、负结果、claim-evidence matrix、复现报告 | 结果约束写作 |
| G5 | 当前论文的引用、两轮审稿、模板、披露、当年期刊复核 | 标记该篇就绪；转下一篇 |

查看状态和精确缺口：

```bash
python3 scripts/researchctl.py status --project my-phd --json
python3 scripts/researchctl.py gate-check --project my-phd
```

代理只能调用 `ready`，不能替人调用 `approve`。系统永不自动投稿。

## 数据发现与获取

公开元数据发现：

```bash
python3 scripts/data_discovery.py "structural vibration anomaly detection" \
  --limit 10 \
  --project my-phd \
  --output projects/my-phd/data/discovery-vibration.json
```

发现报告不是许可结论。选中数据后，人工核验官方记录、研究用途、隐私、版本、来源与泄漏风险，再创建符合 `schemas/dataset-manifest.schema.json` 的清单。

```bash
python3 scripts/dataset_fetch.py validate path/to/dataset.json
python3 scripts/dataset_fetch.py download \
  path/to/dataset.json projects/my-phd/data/raw --accept-license
```

下载只接受公网 HTTPS，不携带登录凭据，不绕过付费墙、验证码或访问控制；原始数据不进入 Git。

## 实验执行

每篇论文在 `papers/Pxx/experiments/` 下建立一份或多份 JSON 设计文件，均符合 `schemas/paper-experiment-design.schema.json`；其中的假设、数据集、设计 ID、种子和运行 ID 必须分别与论文 contract、数据清单及全局 `experiments/plan.json` 完整对上，不允许遗漏或重复分配运行。每个基线还要记录原始来源、年份、实现版本、许可和调参预算，并说明公平比较协议。全局计划与 `experiments/budget.json` 一起通过 G3 人工批准。示例单次运行：

```json
{
  "run_id": "p01-baseline-seed-7",
  "paper_id": "P01",
  "argv": ["python3", "experiments/code/train.py", "--seed", "7"],
  "cwd": ".",
  "seed": 7,
  "timeout_seconds": 7200,
  "estimated_cost_usd": 0,
  "inputs": [{"path": "data/processed/split.parquet", "sha256": "<64 hex>"}],
  "expected_outputs": ["experiments/results/p01-baseline-seed-7.json"]
}
```

执行全部或指定运行：

```bash
python3 scripts/experiment_runner.py --project my-phd
python3 scripts/experiment_runner.py --project my-phd --run p01-baseline-seed-7
```

计划或预算在 G3 后被修改会被拒绝。运行器不是恶意代码沙箱：它只执行你已经批准的本地研究代码，并通过无 shell 调用、可执行文件白名单、项目内路径、精简环境、超时和预算减少误操作。

G4 的 `claims/claim-evidence.csv` 必须逐项覆盖每篇 `paper-contract.json` 中的唯一 claim ID；标记为 `supported` 或 `partially_supported` 的主张必须引用至少一个成功的 `analysis_ids`，且对应输出文件的当前哈希必须与实验登记一致。

## 确定性图表与来源

Codex 可以编写绘图脚本，但 Claude 不得写最终图、图中文字或图注。用本地脚本从已登记结果生成图后，登记其输入、运行和渲染器：

```bash
python3 scripts/figure_provenance.py record \
  --project my-phd --paper P01 \
  --figure papers/P01/figures/result.png \
  --type data_chart \
  --renderer experiments/code/render_p01.py \
  --input experiments/results/p01-metrics.csv \
  --run p01-primary-seed-7 \
  --language-checked-by 'your-name'

python3 scripts/figure_provenance.py validate --project my-phd --paper P01
```

`--language-checked-by` 是对 PNG/PDF 等无法可靠自动读取的图内标签所作的具名英文确认；SVG 与文本型投稿材料仍会自动检查。它不能替代你对最终 PDF 的目视复核。

渲染脚本也必须有当前非 Claude 来源。若是你独立编写或彻底独立改写的文件，可作具名人工证明（这不是密码学证明，责任由证明者承担）：

```bash
python3 scripts/output_provenance.py attest \
  --project my-phd --actor 'your-name' \
  --note 'Independently authored/reviewed; not derived from Claude text' \
  --path experiments/code/render_p01.py
```

## 引用与期刊合规

```bash
python3 scripts/citation_audit.py \
  projects/my-phd/papers/P01/manuscript/references.bib \
  --output projects/my-phd/papers/P01/reviews/citation-audit.json
```

无 DOI 的书籍、标准等可使用人工核验 JSON；每条必须包含 `verified_by`、`verified_at`、`source_url` 和 `title`，通过 `--manual-verifications` 传入。
DOCX 无法像 TeX 一样自动解析引用键，审阅者逐条核对正文引用与文末记录后还必须传入 `--docx-citations-verified-by 'your-name'`；否则 G5 保持关闭。

从期刊官方页面下载模板 ZIP 后：

```bash
python3 scripts/venue_adapter.py inspect ~/Downloads/ijssd-2e.zip
python3 scripts/venue_adapter.py ingest \
  ~/Downloads/ijssd-2e.zip projects/my-phd/papers/P01/venue-template
python3 scripts/venue_compliance.py projects/my-phd/papers/P01
python3 scripts/manuscript_language.py projects/my-phd/papers/P01/manuscript/main.tex
```

首个适配样例是 IJSSD，但只是模板试验目标，不代表所有论文都应投稿该刊。仓库中的指标明确标记为出版社报告；G5 必须通过 Clarivate 或机构 JCR 权限重新核验当年分类、Q1 分区和指标，且重新检查范围、费用、AI/数据政策与模板版本。最终正文及所有投稿相关文本必须为英文。

## 人工投稿包

当某篇论文已经通过其 G5 人类审批并在状态中标记为 `submission_ready` 后，可生成本地投稿材料包：

```bash
python3 scripts/submission_package.py --project my-phd --paper P01
```

默认输出为 `projects/my-phd/papers/P01/submission/manual-upload.zip`。其中只包含稿件、参考文献、最终图表、补充材料和你放入 `submission-materials/` 的真实门户文件；内部 paper contract、JCR 证明、披露工作表、模拟审稿、回复矩阵、引用审计与合规报告不会混入期刊上传包。同时生成逐文件 SHA-256、写入来源摘要的 `SUBMISSION-MANIFEST.json` 和 `MANUAL-CHECKLIST.md`。每个文件必须有当前非 Claude 来源；该篇在 G5 批准后发生任何变化也会阻止打包并要求重新审批。

打包器拒绝符号链接、隐藏文件和密钥类文件，不包含原始数据、期刊模板归档、运行日志或实验原始产物。ZIP 只是整理工具；作者仍需逐项核对、手动上传、预览门户生成稿并最终确认提交。

## 验证

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
