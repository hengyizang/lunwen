# Doctoral Research OS

围绕真实研究问题推进文献、数据、实验、证明、写作与交付。新项目从一个问题和一篇论文开始，证据需要更多独立贡献时再追加论文；已有项目和原始记录继续可读。模型、方法和执行环境按任务选择。

## 开始工作

Python 3.10+，先安装核心依赖：

```bash
python3 -m pip install -e .
python3 -m scripts.researchctl init --project demo --question '当前研究问题'
python3 -m scripts.researchctl work --project demo --paper P01 --task '阅读最近工作，找出最值得检验的差异'
python3 -m scripts.researchctl status --project demo --json
```

这些命令建立或查看工作记录，不调用付费模型。按需要增加论文：

```bash
python3 -m scripts.researchctl add-paper --project demo --question '需要独立研究的新问题'
```

有已配置模型、端点和实际项目预算时，使用同一工作入口计划、开始或继续：

```bash
python3 -m scripts.autopilot plan --project demo --context '比较原始论文证据，确定下一项有区分力的工作'
python3 -m scripts.autopilot start --project demo --context '比较原始论文证据，确定下一项有区分力的工作'
python3 -m scripts.autopilot resume --project demo --paper P01 --context '根据已有结果继续分析和写作'
```

`plan` 展示下一步；`start/resume` 在既有授权和累计额度内执行。创建项目不授予付费额度，配置中的历史默认金额也不是支出许可。未配置付费能力时仍可直接阅读、使用免费工具、编程和整理已有成果。具体运行结果及缺失依赖由命令报告。

## 工作方式

从问题和已有材料选下一项有价值动作，完成后保存实际产物、结果与剩余问题，再继续。检索、试验和写作可以交替；探索结果、确认性结论、原文事实和推断应清楚区分。没有强制候选数量、固定六篇结构、每段台账、厂商写作禁令或固定审稿席位。

- [九条协作原则](AGENTS.md)：授权、真实证据、研究选择与简洁实现。
- [日常工作与旧命令兼容](references/workflow.md)：新任务、续跑、追加论文和实际阻碍。
- [按研究任务选择方法](references/stage-contracts.md)：检索、设计、执行、写作与交付的适用检查。
- [科研诚信](references/research-integrity.md)：来源范围、独立单位、失败及不利证据。
- [重建设计与实施范围](docs/RESEARCH-FIRST-REDESIGN.md)：本轮重建记录、保留能力及验证范围。

## 可用能力

| 任务 | 入口 | 使用重点 |
| --- | --- | --- |
| 文献发现与阅读 | `skills/paper-search`、`skills/paper-reader`、`scripts/literaturectl.py` | 核对原文、日期与阅读范围；元数据只是线索。 |
| 数据与研究设计 | `skills/data`、`skills/experiment` | 保留原始来源、适当分析单位、对照和实际方法假设。 |
| 运行与复现 | `scripts/experiment_runner.py`、现有 Meta/理论工具 | 按实际计划执行并记录失败；引擎支持范围不是科学方法范围。 |
| 图表和写作 | `skills/figures`、`skills/write` | 数据图来自真实数据，围绕证据组织论证；按目标选择语言。 |
| 检查与审稿回复 | `skills/audit`、`skills/review` | 解决有依据的问题；普通修改不要求全量评分表。 |
| 期刊与交付 | `skills/journal`、`skills/package` | 核对实际目标、来源、渲染和文件；整理包不代表已提交。 |
| 第三方方法与工具 | `skills/ccf-*`、`references/upstream-components.md` | 按需要加载；保留原版、归属和实际许可，不要求先登记整套流程。 |

按任务安装可选依赖，例如 `python3 -m pip install -e '.[figures,reader]'`。完整 CCFA 参考需要时用 `python3 -m scripts.ccfa_runtime bootstrap` 恢复。Windows/D盘/WSL安装器、GitHub云作业、现有API和MCP都是可选运行方式；使用当前可用环境，不为普通任务先安装全部工具。

## 已有材料与兼容

旧 `start.sh`、`autopilot`、`researchctl gate-check/ready/approve/advance` 和 G0–G5 项目记录继续用于兼容。日常 `status` 聚焦问题、产物和预算；需要检查历史流程时使用 `--legacy-checks`。历史批准、封存方案和失败记录不批量改写；新工作可以引用旧证据并注明适用范围。

`my-phd` 的历史[数据材料](https://github.com/hengyizang/lunwen/tree/cloud-state/my-phd/projects/my-phd/data)和[文献材料](https://github.com/hengyizang/lunwen/tree/cloud-state/my-phd/projects/my-phd/evidence/literature)保留在云状态分支。该分支仍在更新；文件存在或数量变化不代表全文已读、模型已校准、实验已完成或论文就绪。具体研究状态需要读取实际项目证据，不从旧验收报告推断。

原始文献、`docs/deliveries/` 历史交付、日期验收和第三方源文件保留。历史报告说明其当时范围，不是现行操作规则；旧模型故障、余额和平台能力不能当今日事实。

## 验证

```bash
python3 -m compileall -q scripts
python3 scripts/validate_repo.py
python3 scripts/run_tests.py fast
```

开发检查按改动范围选择；定期或手动运行完整回归和具体工具验收。测试通过说明对应软件行为，不能证明科学结论、期刊录用或无人科研已经成功。CI分层见 [CI-VALIDATION](docs/CI-VALIDATION.md)。

代码在 `scripts/`，任务技能在 `skills/`，机器配置在 `config/`，项目材料在 `projects/`；秘密、原始私有数据和大运行产物不提交到Git。费用、来源与历史结果由实际记录支撑。
