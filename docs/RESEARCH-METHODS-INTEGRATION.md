# 研究方法整合：正式云端流程

2026-09-30，经项目所有者明确授权，将五个仓库中补足现有能力的部分接入正式代码。选定原文件已按提交版本固定，文件级来源和 SHA-256 见 `integrations/vendored-research-methods.json`；适配模块见 `config/research-methods.json`。所有执行仍在 GitHub Actions 云端运行。

| 来源 | 吸收内容 | 实际接入点 | 现有能力的处理 |
| --- | --- | --- | --- |
| K-Dense scientific-agent-skills | 具体选题的发散与收敛、竞争假设、区分性预测、证伪与控制；保留两个技能的参考材料、模板及确定性辅助脚本 | `skills/scientific-brainstorming`、`skills/hypothesis-generation`；G1 假设登记与审计 | 原有最近工作检索、新颖性矩阵、实验预注册和统计要求继续作为正式依据 |
| academic-research-skills-codex | 证据行的访问范围、缺失状态与逐阶段验证方法 | API/CLI 分阶段方法提示；证据与论证模块 | 映射到现有 `paper-facts`、claim-evidence、实验和返修台账，不另建结果权威 |
| nature-skills | 先精读论文再提出六项可检验选题要求；先确定论证边界；面板对齐与 PDF 文字/线条碰撞检查 | 可审计论文卡片、PDF 页面来源映射、原生图表渲染器与 G5 图件复查 | 继续使用现有 DOI、引用、数值、Word/PPT、返修与人工图件确认机制 |
| PaperSpine | 全文证据台账、支撑具体主张的引用库、写作理由矩阵 | 现有事实/主张/测量/段落论证台账的明确映射；规划、写作和审查提示 | 不导入其独立桌面工作台，也不复制一套并行数据库 |
| academic-research-skills 原版 | 七个通用 reviewer 维度、按文章类型扩展的检查、证据锚定的分类判断、保留未解决问题与审稿分歧 | `config/pre-submission-criteria.json`、投稿前清单、独立批评提示与 G5 阻断 | 不替代现有两轮独立模型审查、数值/引用/主张强度保护或人工科研批准 |

通用投稿问题覆盖原创性、方法严谨性、证据充分性、论证连贯性、写作质量、文献整合、意义与影响。实证、计算、理论、综述、案例和政策文章各有附加问题；计算研究额外检查计算预算公平性与数据泄漏。每项记录论文位置、证据位置、理由、不确定性、是否影响决定，以及消除疑问所需的检验。`PARTLY_MEETS`、`DOES_NOT_MEET`、`NOT_ASSESSED` 都阻止 G5；不能以别处的优点抵消。该清单不生成总分、排名或录用概率。

## 云端调用与输入

`api_orchestrator.py` 和 `autopilot.py` 会自动将匹配阶段的适配模块提供给规划者、作者和批评者。仅加载短适配模块；上游的完整编排器、额外付费检索、图像服务和领域工具包不会因此启用。原文件按需阅读，辅助脚本只提供规划材料。

在云端任务中运行：

```bash
python3 scripts/research_methods.py --validate
python3 scripts/research_methods.py --stage topic-intelligence --role writer

python3 scripts/research_candidates.py hypotheses --project my-phd \
  --spec program/hypothesis-register.json --output program/hypothesis-audit.json

python3 scripts/research_candidates.py paper-card --project my-phd \
  --spec evidence/paper-cards/paper-001.json --output evidence/paper-cards/paper-001.audit.json

python3 scripts/pre_submission_review.py --project my-phd --paper P01
```

G1 必需输入遵循 `schemas/research-hypotheses.schema.json`：至少三个具体假设，每个包含已定位的来源、精确差异、预测、证伪结果、两个竞争解释及区分检验、失败原因和云端/预算/期限计划。`argument_plan` 先声明允许和禁止的主张、拟需证据与停止条件。估计预算不授权消费。

论文卡片是可选阅读工具，遵循 `schemas/paper-card.schema.json`。摘要、片段和元数据不得评估未见的方法与实验。声称全文范围时，必须引用与当前原文件哈希一致、由控制面保存的具名来源范围确认：

```bash
python3 scripts/source_scope.py --project my-phd --source evidence/sources/paper.pdf \
  --scope full_text --confirmed-by 'actual-human-name'
```

只有真正确认所提供材料范围的人可授权这个记录。它确认提供的是全文，不确认该人读完全文，也不确认科学主张。作者模型不能写入 `evidence/source-scopes/`。在卡片中填入 `primary_source` 和 `scope_record` 的路径及当前哈希。PDF reader 的页面映射仅说明提取覆盖，不能自行提升来源范围。

G5 输入遵循 `schemas/pre-submission-checklist.schema.json`。锚点包括项目相对路径、SHA-256、定位与最多 25 词的原文片段。文本定位使用 `L1` 或 `L1-L3`；PDF 使用真实 `pdf_page`；DOCX 使用 `paragraph 1`。未纳入正式 TeX include 树的草稿不能当作正式稿证据。清单依赖变化后必须重审，不能修改报告的 PASS 字段来过关。

API/CLI 控制面在初次写作和修改后重新生成 G1/G5 审计。科研关卡再次重算当前结果；确定性报告由控制面写入，作者不能伪造。独立 API 批评不接收作者自由文本中的期望结论或此前审查意见，约束来自已记录的 intake、论文契约和期刊信息。

原生图表在输出时生成面板几何和最终 PDF 碰撞审计，并在 G5 重算。只要求 SVG/PNG 时，会另外生成审计用 PDF，存于 reviews，供质量检查；它不作为所声明的最终图件输出。新检查也修复了旧渲染器透明图例被网格线穿过的问题。缺失依赖、过期文件或机械失败均阻断；几何通过仍需人工目视检查。

## 保留的科研与费用边界

方向评分继续使用已确认的资助博士岗位、就业/薪资、发展、博士与就业竞争、背景和申请路线权重。当前论文必须云端可行。新颖性、博士深度和原创贡献是方向筛选之后具体选题的硬要求，不参与方向加权交换。未来实验室拓展不能证明当前论文。

Codex/OpenAI 写持久科学内容，Claude 只规划和独立批评；人工 G0–G5、原始数据权利、预注册、失败/负结果和人工投稿均保留。此次安装没有调用模型 API 或启用新的付费服务，仍使用累计 300 元档位授权。代码安装和测试不意味着任何论文已完成审查或达到投稿条件。

## 版本与许可

| 来源 | 固定版本 | 选定内容许可 |
| --- | --- | --- |
| K-Dense | `65d6e786832e2c52832713117bbbf5096b56f77f` | MIT |
| ARS Codex | `70b412fe69d3b5bf6b16adf64a96160bdd3c2d28` | CC BY-NC 4.0 |
| ARS 原版 | `8120a34368f9f7493ef1ff3fb784b0dc93608be8` | CC BY-NC 4.0 |
| Nature Skills | `84880815fb37317b3766bff2c2abba395b8993c3` | 选定原文件按仓库 Apache 2.0 许可保留 |
| PaperSpine | `f7e3dabaf499b2aef1eabdd1cd5d64f173d7dcc3` | MIT |

保留的 ARS 文本与其适配文档/问题配置用于当前非商业学术研究，保留署名、许可和修改说明。它们的许可不被其他本仓库代码的许可覆盖。来源细目、许可原文与调整边界见 `THIRD-PARTY-NOTICES.md`。现有 K-Dense 通用技能选择保持旧固定版本；新增两个技能独立固定，避免悄然升级其他组件。
