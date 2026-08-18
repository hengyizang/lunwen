# Doctoral Research OS v1.0

面向个人研究者的、可审计且有人类闸门的博士研究流水线。Claude/OpenAI API 是可选的模型层，Claude Code/Codex CLI 是可选的本地 Agent Runtime，本地 Python 控制层负责状态、许可、预算、哈希、实验登记、引用与期刊合规检查。

“一键”指：创建或恢复项目，运行当前阶段的 author → critic → remediation → final critic 流程，通过确定性检查后停在下一道人类审批闸门。它不代表自动批准选题、自动确认数据许可、自动产出真实实验结果或自动投稿。

## 已实现的闭环

- G0–G5 状态机和显式人类审批；审批包含产物哈希。
- 默认 6 篇论文；G5 按 P01 → P06 逐篇完成，全部通过后才进入 `submission-ready`。
- Claude Code 非交互执行、每次调用预算上限、超时、输出上限、断点日志和敏感环境值脱敏。
- Codex 只读、临时、JSON Schema 约束的初审和终审；终审未通过时闸门保持关闭。
- API-first 模式：无需 Claude Code/Codex CLI 即可调用 Claude/OpenAI API 生成结构化阶段产物；模型生成的文件受路径、大小、状态文件和凭据保护约束。
- DataCite、Zenodo、Hugging Face、OpenML 的公开数据元数据发现；候选许可始终标记为未核验。
- 数据清单验证、人工许可确认、SHA-256，以及对私网/回环/带凭据 URL 和不安全重定向的拒绝。
- G3 批准后的实验计划哈希锁定、无 shell 命令执行、预算硬上限、超时、输出哈希，以及成功/失败/超时的统一登记。
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
   Claude API            OpenAI API          Local experiments
   research/writing      critique/audit       after G3 approval
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
python3 scripts/api_orchestrator.py stage my-phd intake --provider anthropic \
  --context 'AI + robotics/mechanical engineering; no laboratory; limited GPU.'
```

API 模式会把原始响应、结构化 bundle 和写入清单放在 `projects/<project>/api_runs/<run-id>/`。模型只能生成项目内普通科研文件，不能修改 `state/run.json`、凭据、`.env`、隐藏文件，不能批准/推进闸门，也不能执行任意 shell 命令。

完整说明见 [`docs/API-FIRST.md`](docs/API-FIRST.md)。

## CLI 一键启动与恢复

```bash
bash scripts/start.sh my-phd "目标、已有背景、每周时间、预算和设备条件"
```

等价命令：

```bash
python3 scripts/autopilot.py start \
  --project my-phd \
  --context "目标、已有背景、每周时间、预算和设备条件"
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

`resume` 只会跨越已经记录批准的闸门。若当前阶段仍缺证据或许可，它会保留检查错误并停下。运行日志在本地 `projects/<slug>/state/runs/`；最新断点摘要在 `state/autopilot.json`。

默认每次 Claude 调用上限为 5 美元，可显式下调：

```bash
python3 scripts/autopilot.py resume \
  --project my-phd --claude-max-budget-usd 2.00 --timeout 1800
```

`--claude-mode minimal` 使用 Claude Code 的 bare/minimal 模式；默认 `standard` 会加载仓库配置。Codex 审核固定使用 `codex exec --ephemeral --sandbox read-only --json`。

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
| G1 | 三个以上候选、核心命题 A、扩展命题 B、淘汰理由 | 论文组合架构 |
| G2 | 完整 paper map 与每篇可证伪 contract | 数据与实验设计 |
| G3 | 数据许可、SHA、可执行实验计划、统计方案、预算 | 执行锁定计划 |
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

`experiments/plan.json` 必须符合 `schemas/experiment-plan.schema.json`，并和 `experiments/budget.json` 一起通过 G3 人工批准。示例单次运行：

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

## 引用与期刊合规

```bash
python3 scripts/citation_audit.py \
  projects/my-phd/papers/P01/manuscript/references.bib \
  --output projects/my-phd/papers/P01/reviews/citation-audit.json
```

无 DOI 的书籍、标准等可使用人工核验 JSON；每条必须包含 `verified_by`、`verified_at`、`source_url` 和 `title`，通过 `--manual-verifications` 传入。

从期刊官方页面下载模板 ZIP 后：

```bash
python3 scripts/venue_adapter.py inspect ~/Downloads/ijssd-2e.zip
python3 scripts/venue_adapter.py ingest \
  ~/Downloads/ijssd-2e.zip projects/my-phd/papers/P01/venue-template
python3 scripts/venue_compliance.py projects/my-phd/papers/P01
```

首个适配样例是 IJSSD，但只是模板试验目标，不代表所有论文都应投稿该刊。仓库中的指标明确标记为出版社报告；G5 必须通过 Clarivate 或机构 JCR 权限重新核验当年分类、分区和指标，且重新检查范围、费用、AI/数据政策与模板版本。

## 人工投稿包

当某篇论文已经通过其 G5 人类审批并在状态中标记为 `submission_ready` 后，可生成本地投稿材料包：

```bash
python3 scripts/submission_package.py --project my-phd --paper P01
```

默认输出为 `projects/my-phd/papers/P01/submission/manual-upload.zip`。其中包含稿件、参考文献、图表、补充材料、披露、两轮审稿与回复、期刊合规报告，以及可选的 `submission-materials/`。同时生成逐文件 SHA-256 的 `SUBMISSION-MANIFEST.json` 和 `MANUAL-CHECKLIST.md`。

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
