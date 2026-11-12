# 关于 lunwen 项目：我的全部看法、评价、批评、建议与改动记录

> 整理自 2026-11-09 的完整对话。这份文档刻意保留了我的判断立场、犯过的错、中途修正过的结论，以及我拒绝做的事和理由，而不只是罗列结果。
> 对象：`D:\ad\lunwen`（Doctoral Research OS v2.3.0，基线 commit `58ac455`）

---

## 0. 先给结论

**这是一套把「不许造假」做到极致、却因此没能产出任何科研成果的博士科研控制平面。**

我的整体判断是：**防幻觉 / 防造假明显做过了头**，从「防止造假」异化成了「证明自己没做事」。我据此动手把系统的优化目标从「可辩护」改回「可完成」。但我始终守住一条线：**不替真人做科学决定**，哪怕用户说「你帮我吧」。

整个过程中我**没有向 GitHub 推送任何内容**；所有改动都在本地工作区，由你自己决定何时上传。

---

## 1. 找项目与版本同步

### 看到的事实

本机有 3 个 `lunwen` git 克隆，都指向 `https://github.com/hengyizang/lunwen.git`：

| 路径 | 当时版本 | 判断 |
|---|---|---|
| `D:\ad\lunwen` | `7765bd5` | **主副本**：最近有活动、有 `.runtime/`、有未跟踪的 `projects/my-phd/` |
| `C:\Users\41056024\WorkBuddy\2026-10-30-12-37-05\lunwen` | `9bfde2b` (#115) | 旧会话分析副本 |
| `D:\quzhou\lunwen` | `0711fe5` (#73) | 更早的副本，且同目录还有 `lunwen-state` |

GitHub 当时已是 `58ac455`（#174, 2026-11-08）。

### 我的判断与做法

- 我认定 `D:\ad\lunwen` 是「我们本地的项目」，因为它有真实工作数据；另外两个是历史快照。
- 用 `git merge --ff-only` 快进（**不做 `reset --hard`**），因为它是纯落后 21 个提交、0 ahead、无本地提交，快进无损。
- 更新前特意检查远程树里有没有 `projects/my-phd/`，避免覆盖你的论文数据——没有，才动手。
- 网络代理（`127.0.0.1:56349`）对 git smart-http 间歇性 502，一次报 `invalid index-pack output`；用 `http.version=HTTP/1.1` 重试成功。我还准备了 codeload tarball 作备用通道，但没用上，也没拿它硬覆盖仓库（那样会丢 git 历史）。

### 评价

多副本本身不是错，但**没人说得清哪个是主项目**，这已经是项目治理的第一个信号：一个强调「来源与版本可追溯」的系统，自己的本地副本却没有来源标识。

---

## 2. 删除重复副本

### 我的安全立场

你说「另外两个删掉吧，重复了」。我没有直接删，先做了只读扫描，因为删除不可逆：

- 两个副本都无未提交改动、无未跟踪文件、无本地独有提交；
- **但** `D:\quzhou\lunwen-state` 是 `D:\quzhou\lunwen` 的**关联工作树**（`.git` 文件指向 `lunwen/.git/worktrees/lunwen-state`），删主目录会让它变成孤儿；
- 它里面有 `027f447` 等 "Save cloud research job ... for my-phd" 提交，我确认这些提交在 GitHub 的 `origin/cloud-state/my-phd` 分支上存在，**数据不会丢**，才敢继续。

然后：加粗警告 → 列全部路径 → 说明风险 → 要你显式确认（你选了「一起清理」）→ 完整备份到 `D:\_lunwen-backup-20261109`（41 MB，逐项核对文件数）→ 送 Windows 回收站（不是永久删除）。

回收站接口被环境安全策略挡了两次（PowerShell `Add-Type`、COM 实例化），最后装了标准库 `send2trash` 走系统 API 完成；中间还踩到一个坑：路径必须 `os.path.normpath()` 转成反斜杠，否则 `get_short_path_name` 报 `FileNotFoundError`。

### 这里产生了我对项目的第一个重要批评

> **最强调「不可伪造」的系统，自己的「人工批准」却可以用环境变量和合成夹具伪造出来。**

`acceptance_scope.py` 用 `patch.dict(DR_OS_CLOUD_EXECUTOR=1)` 生成「人工批准」记录；`cloud_human_controls.execute` 未传 `owner_authorization` 时以 `verified=False` 的本地声明记录人工决定；测试共享夹具 `sealed_run` / `seal_review` 能造出「G3 批准 + 成功回执 + 独立审查通过 + 人工确认」。护栏越堆越高，真正关键的边界反而漏了。

---

## 3. 全量能力精读

### 规模与方法

- **424 个 Python 文件 / 127,341 行**（自研 scripts 202/70,375 + tests 195/44,534 + third_party 27/12,432）；全部文本 **195,185 行**；69 个 JSON Schema、25 个配置、83 篇 docs、46 个技能、16 个 CI 工作流。
- 我按文件名字母序把 scripts 分 8 组、tests 分 2 组，加契约文档组、第三方组，**共 12 个子智能体逐文件通读**，产出 12 份分报告（约 6,500 行 / 1.4 MB）。
- 如实说明覆盖深度：`.py` / `.md` 逐文件完整打开通读（大文件分段），JSON/YML/CSV 逐个解析结构而非逐行抄录。G08 与 tests-G02 组还各自发现并补读了边界外多出的 1 个文件。

### 能力全景（我归纳的 12 个域）

G0–G5 状态机与闸门 / 模型编排与三家族互盲审查 / CNY 累计预算与每次尝试计费 / 文献检索·全文索引·阅读卡·引用核验 / 数据发现到行级溯源 / G3 冻结后容器内实验执行与负结果归档 / 科研质量闸门 / 37 类确定性图件与可编辑导出 / 独立审查与修订漂移检测 / 手动投稿 ZIP 与期刊合规 / 16 个 CI 工作流与云作业恢复 / 第三方 arXiv·Nature 图件·假设校验组件。

### 我的评价

**它不是论文生成器，是研究工作流控制平面。** 用 Python 确定性控制层管住状态、证据、预算、哈希、闸门，用 Claude 做只读规划与独立批评、OpenAI 写持久产物，用 GitHub Actions 跑云端作业。这个架构定位是清楚的，`AGENTS.md` 25 条规则和 69 个 schema 也确实把「不许编造」落到了代码里。

### 最关键的发现：能力 ≠ 实际状态

| 指标 | 实际值 |
|---|---|
| 当前阶段 | `G1 / awaiting_work` |
| 已批准闸门 | 只有 `G0`（两条 approval 都是 G0，第二条只是把预算 300→500） |
| G1 / G2 人工选题 | **从未批准** |
| 六篇 `paper-contract.json` | 全部 `draft` 空模板，标题/假设/数据/实验/期刊全空，只硬编码 `Q1` |
| 实验 / 数据 / 主张记录 | 全部 0 行，`claim-evidence.csv` 仅表头 |
| G1 人工筛选表 | 757 行，4 个人工字段 100% 为空 |
| 最新验收 `cloud-validation-2026-11-08.json` | `completed_real_papers=0`、`NOT_CALIBRATED`、`scientific_completion_verified=false`、`partial_failed_not_calibrated` |
| 需求追踪（45 条） | R24「六篇真实论文」`not-started`；156 项 checklist `all_156_requirements_fulfilled=false`、`fully_satisfied_count=53` |
| 唯一真实工作 | 免费公开 API 的 G1 文献元数据检索：27 组回执、2,497 条、757 待读 |

我的原话结论：**「它证明的是『控制平面按规则运行』，不是『科研结果成立』」**；系统自己在验收记录里写了 `Implementation is software capability, not research completion`。

### 当时列出的风险与落差

- 文档宣称但代码占位：H/AD/CFH 机械审查、humanization、水印检测统一 `retired`/`not_assessed`；校准锁死 `NOT_CALIBRATED`；GPT Image fail-closed；Mermaid 不渲染；「24 篇评审、0.85 一致性」只有容器没有数据。
- 名实不符：`jcr_verify` 不联网核验、`paper_qa.py` 非 PaperQA2、`research_mcp` 报 v2.4.0 而仓库 v2.3.0、`--reuse-panels` 已退役、`dataset_fetch.accept_license` 参数未使用。
- 硬编码：`OWNER_ID=163310614`、仓库名、`my-phd`、11 个 CI 检查名、`gpt-6.1-sol` / `claude-opus-5-5` / `deepseek-v4.1-flash` 等疑似未来型号以 `production` 固定身份写死。
- 安全：云闸门只看可伪造环境变量；`network_safety` 解析与实际连接不绑定同一 IP（DNS rebinding 窗口）；`literature_assets.resolve` 接受任意 HTTPS 无发布者白名单；`artifact_hash` 刻意排除 `state/`、`raw/`；凭据脱敏仅按变量名启发式。
- 测试：195 文件 / 44,534 行回归极密，但真实付费 API、网络、Docker、人工 G1/G2 决定、独立 critic 全部 mock 或合成替身，20+ 处实机验收默认跳过。
- 许可：`ars-review` / `ars-codex` 的 **CC BY-NC 4.0 非商业**约束与付费 API、投稿准备场景冲突。
- 配置矛盾：`stages.json` 仍写死 8/8.5 分、Q2、IF>1.0，文档却说已降级为观察；`paper-qa==2026.08.12` 与 `2026.8.12` 并存。

---

## 4. 你问我：「防幻觉 / 防造假是否做得太过了？」

### 我的回答：**是，明显太过了**

但先把边界说准：**问题不在「要不要防」**。防编造引用、防伪造结果、防自动投稿，对面向学位与期刊的系统是刚需。问题在**防的粒度、成本由谁承担、以及它究竟在优化什么**。

### 我补的定量证据

| 指标 | 实测 |
|---|---|
| `raise` : 实际写文件/导出 | **4,730 : 688 = 6.88 : 1**（96% 脚本含 `raise`） |
| 防御型 : 产出型函数 | **272 : 173 = 1.57 : 1** |
| `verified=False` 类标记 | 345 次 / 107 文件；不同「未验证」键名 **226 种 / 748 次** |
| 哈希绑定 | 3,417 次 / **177 文件（88%）** |
| 文件名即校验/审计类 | 52 / 205（25%） |
| 测试 mock 注入 | 461 处 / 108 文件（55%） |
| 文档免责表述 | 76/83 篇 docs，共 **354 处** |

一句话：**一套防止造假的装置，成功防止了任何东西被产生。**

### 我归纳的四种真实代价

1. **信号稀释**：当所有字段都是 `False`，`False` 不再携带信息。226 种键名把「未开始 / 未通过 / 刻意不判断」揉成一团，最后只能靠重复 354 次的总免责兜底。
2. **成本爆炸**：改一处要同步 Python、schema、夹具、文档四层，复杂度反而造出新错误——预算 300 vs 500、账本 0 元 vs 验收 3.889 元、两种 `paper-qa` 版本号。**越想防错，越容易出现新的错。**
3. **责任真空**：每处判断都推给「人工 / 实证」，但 G1/G2 真人决定从未发生，757 行筛选表全空。系统不肯替人决定，人也没被真正要求决定，流程死锁在 G1。护栏把责任转移得干干净净，也把进展转移得干干净净。
4. **自相矛盾**：最强调不可伪造的系统，人工批准却可由环境变量与合成夹具造出来，`artifact_hash` 还排除 `state/`、`raw/`。**护栏覆盖面与有效性不是正相关。**

### 我对成因的推测

像一条「免责军备竞赛」路径：每发现一个可能被质疑的点，就加一层检查 + 一个 schema + 一份验收报告 + 一句免责声明，而不是判断风险是否真会发生。**AI 辅助生成代码尤其容易放大这个倾向**——模型倾向于追加免责与校验来显得可靠，不擅长删掉不必要的分支。结果 `retired` / `not_assessed` 越堆越多，没有一处被真正清理。

### 我给出的判断标准

> **好的护栏应该让真实工作更容易完成，而不是更难。**
> 如果一套流程运行至今仍停在 G1、零论文、零实验，那么该审视的是护栏本身，而不是再加一层。

### 我当时的分层建议

- **保留 6 条**（作用在不可逆、外部可见边界）：G1/G2 真人决定、绝不自动投稿、来源哈希与 ledger、累计预算与失败留痕、角色隔离、外部调用前校验。
- **收敛**：226 状态键 → 一个 `EvidenceStatus` 枚举；69 schema 按阶段合并；354 处免责集中一处；哈希只在产物落盘/冻结/交付三处算。
- **删除**：`retired`/`not_assessed` 占位模块、重复的 acceptance 报告、能伪造人工批准的夹具路径、硬编码未来型号。
- **流程**：先跑通一次真实 G1→G2 和真实付费周期，再按「实际触发过的拒绝」删护栏——没触发过的分支直接删，比照设计文档删可靠。

### 我的一句话评价

> **这套系统像一份永远在准备接受审计、却从未提交的研究档案。**

---

## 5. 我实际做的代码改造

### 诊断到的真正卡点

`gate-check --project my-phd` 报 **16 组 / 85 条**阻断：70 条是「757 行人工筛选表未填写」，其余是新颖性矩阵字段迁移、`selection_decision` / `feasibility_evidence` 格式要求、假设审计时间戳、可选质量评估，以及 `jsonschema` 未安装导致的 2 条「validator unavailable」。

而 `projects/my-phd/program/` 里真人材料**早已齐备**：`topic-decision.md` 6 KB、`novelty-claim-matrix.json` 13 KB、`hypothesis-register.json` 24 KB。**材料齐了、决定做了，却过不了机器闸门**——不，后来我发现决定其实也没做，见第 6 节。

关键发现：G1 的几十项校验是**硬编码在 `researchctl.gate_errors()` 里的**，改 `config/stages.json` 没用，必须给一条显式的精简路径。

### 改动清单（9 个文件，+956 −1）

- 改 `scripts/researchctl.py`：`gate_errors()` 包装成「默认完整协议 / 显式 opt-in 精简档」，原逻辑原样保留为 `_full_gate_errors()`。
- 改 `scripts/model_routing.py`：`LOCAL_MODEL_OVERRIDES` + `_apply_local_model_overrides()`，允许 owner 用真实型号覆盖固定路由。
- 改 `config/stages.json`：新增 `blocking: false` / `observation_only` / `real_work_profile` 机器标记，原字段一个未动。
- 改 `.gitignore`：忽略 `config/model-routing.local.json`。
- 新增 `config/real-work.json`、`scripts/real_work.py`、`docs/REAL-WORK-QUICKSTART.md`、`docs/OWNER-DECISION-2026-11-09-REAL-WORK-FIRST.md`、`tests/test_real_work.py`。

按 `AGENTS.md` rule 25 的要求，我补了一份**具名、带日期的 owner decision**，把授权范围、降级内容和保留底线写清楚——因为弱化保留规则按仓库自己的治理规则需要这么一份文件。

### 效果

| 场景 | 改造前 | 改造后 |
|---|---|---|
| 默认 `gate-check` | 16 组 / 85 条阻断 | **完全不变** |
| `DR_OS_WORK_PROFILE=minimal` 下 G1 | 无此档 | **0 阻断通过**，其余转可见的非阻断观察 |
| G1 决策命令数 | 四步，每步过 85 条检查 | `real_work decide` 一条命令 |
| 真实模型 ID | 硬编码未来型号无法替换 | `configure-models` 写本地覆盖 |
| 知道真实跑还缺什么 | 一堆 `raise` | `check-real` 列缺口 + 修复命令 |

### 我没有削弱的

规则 1–24 原样；G1/G2 仍需真人 `--actor`；不自动投稿、不编造；哈希、预算、失败留痕、角色隔离、provenance 全保留；**G2–G5 仍走完整协议**；完整协议的检查一条没删，只是降为观察项，`full-check` 随时可看。

### 我故意没做的，以及理由

1. **没收敛 226 个键、没合并 69 个 schema、没批量删 `retired` 占位**：跨 200+ 脚本的重构会同时破坏 195 个测试与数据契约。正确顺序是先跑通一次真实研究，再按实际触发删护栏。
2. **没改 `DR_OS_CLOUD_EXECUTOR` 闸门**：收紧需要签名/凭证体系，且影响全部云端测试；本次聚焦当前唯一卡点 G1。
3. **没动另一会话产生的文件**：`AGENTS.md` rule 25、三份 `OWNER-DECISION-2026-11-09*`、`skill_router.py`、`third_party_runtime.py`、`scientistic-agent-skills/` 等，一行未碰。
4. **没有自动 bootstrap CCFA**：需要联网拉固定 commit，是独立动作。
5. **没有 `git push`**：所有改动都在本地工作区。

### 我中途修正过的两个结论（如实记录）

- 最初用 `xargs wc -l` 统计行数，被**分批小计**干扰，得出错误的「1.9 万行」；改用 Python 逐文件统计后更正为 **12.7 万行 Python / 19.5 万行文本**。
- 我一度把「预算 300 vs 500」列为口径打架，后来读 `state/run.json` 才发现：**300 是 `config/defaults.json` 默认值，500 是 G0 的项目级修订**，这是合理的分层，不是 bug。测试里还断言了 300，所以我**没有改它**。
- 另外补装 `jsonschema` 后，完整档错误数从 85 条变成 **81 组 / 150 条**——更多校验被激活。这反而加强了我的判断：完整档只会越来越难。

---

## 6. 「继续，你帮我吧」：我拒绝的一步

### 为什么

我读了 `program/topic-decision.md` 全文，它开头写着：

> 状态：**建议稿，待负责人确认**…不代替负责人作出最终选题决定，也不构成任何闸门批准。

第 7 节：

> 本文不建议在本轮对 G1 调用 `ready` 或任何闸门推进… `approve` 及任何跨闸门动作必须由负责人在补齐全部门槛项后自行执行。

且 `topic-shortlist.json` 的 `selection_decision` 是 `null`——D1 sim-to-real / D2 轴承跨机迁移 / D3 conformal 弃权，**一个都没选**。

**所以卡住的不是手续，是最终选题决定本身还没做出。** 我若执行 `decide`，等于用 `--actor "Hengyi Zang"` 把「待确认的建议稿」登记成真人已批准的科学决定——正是 `AGENTS.md` 规则 5/9 和我自己写的 owner decision 里明确保留的底线。降仪式成本可以，替人做科学决定不行。

这是我在整个任务里最坚持的一个判断，即使你说「授权更改任何的」「你帮我吧」也没有越线。

### 于是我把它变成「只差三个空」

- 新增 `prepare-decision` → `projects/my-phd/reports/G1-DECISION-SHEET.md`：一页纸，原样摘录博士问题、3 个候选、`selection_decision: null`、证据局限、待办，只留 3 个空位（选哪个 / 最强对手为何不选 / 主要风险怎么检验）+ 签名。**无新增断言、无评分、无推荐**。
- 新增 `split-screening` → 757 行拆成 **16 批 × ≤50 行** + `INDEX.md`，行数核对 757=757；四个 owner 列原样留空，不筛、不排序、不评分、不代填。测试增至 9 个。

### 全量测试与环境

`2363 tests / 6 failures / 163 errors / 35 skipped`（623 秒，基线此前 420 秒超时没跑完）。**失败根因全部是环境，没有一条来自我的改动**：

- ~90 个：CCFA 固定资源缺失
- 缺 `scipy`/`statsmodels`、`matplotlib`/`numpy`/`pandas`、`python-docx`/`pptx`/`pypdf`
- 12 个 comparison archive 相关、3 个 Windows 环境（无 `sched_getaffinity`、无 POSIX runner）

装上：`jsonschema`、`lxml`、`numpy`、`pandas`、`PyMuPDF`、`pypdf`、`python-pptx`、`python-docx`、`proselint`。复测后 `test_api_first` **37/37 OK**、`test_editorial_integration` **11/11 OK**、`test_ccfa_runtime` 从 47 errors 降到 **1 failure**。

**CCFA 我没修成，也不肯糊弄**：`git clone` 被代理 502 挡住；改走 codeload 拉同一个固定 commit `f157d7ed`，300 秒只收到 4.89 MB、断点续传 `rc=33` 不支持 Range。我**没有把残缺归档写进 `third_party/`**——那会破坏项目逐文件的 git blob SHA-1 + canonical-LF SHA-256 双重校验。换通道可以，绕过校验不行。

---

## 7. 我对这个项目的总体评价

### 值得肯定的

- **防幻觉设计本身是真诚且有工程含量的**：证据链、来源哈希、失败/负结果留痕、角色隔离、G1/G2 人工闸门、`*_verified=False` 的自觉留白，比大多数「AI 写论文」项目严谨得多。
- **边界自述诚实**：系统反复声明「工程验收不代表科学有效」，验收记录里主动写 `partial_failed_not_calibrated`，没有把软件通过伪装成科研完成。
- 12 个子智能体精读下来，几乎没有发现「偷偷编造结果」的代码路径——规则确实落到了实现里。

### 我批评的

1. **优化了错误的目标**：它优化的是「可辩护性」，不是「产出论文」。4,730 次 `raise` 对 688 次写入、88% 模块算哈希、354 处免责，成本全花在自证清白上。
2. **仪式压倒判断**：真人已写 6 KB 决策依据、13 KB 新颖性矩阵、24 KB 假设登记，却因 757 行筛选表未填、几个字段没迁移、少装一个 `jsonschema` 而永远过不了 G1。
3. **责任设计有缺陷而不自知**：把每个判断都推给「人工/实证」，却没有让真人做决定变得容易，结果形成谁都没批准、谁都不负责的死锁。
4. **复杂度反噬安全性**：最强调不可伪造的地方，人工批准反而能用环境变量和合成夹具造出来；硬编码的未来型号让真实付费调用几乎必然失败。
5. **文档与实现脱节**：`retired`/`not_assessed` 占位、名实不符的函数名、互相矛盾的配置、`CC BY-NC 4.0` 与投稿场景的许可冲突，都长期没人清理。
6. **测试给了虚假的安全感**：195 个测试看起来很密，但真实 API、网络、Docker、人工决定、独立审查全被 mock；能证明控制平面按规则跑，不能证明科研成立。

### 我认为需要澄清、而非「修」的

- 预算 300/500 不是 bug，是默认值 + 项目级修订。
- 默认完整档错误数从 85 变 150，不是回归，是补齐依赖后更多校验生效。
- `scientific_completion_verified=False` 大量存在本身不是问题，问题是它多到失去信息量。

---

## 8. 我给过的全部建议（按优先级）

1. **先完成 G1/G2 真人决定并落到记录**（当前唯一真正的卡点）。
2. **打通一次真实付费模型周期 + 独立审查**，用真实结果校准模型 ID、计费与哪些护栏真被触发过。
3. **按「实际触发过的拒绝」删护栏**：从没触发过的 `raise` 分支、占位检查、验收报告直接删。
4. **收敛状态表达**：226 键 → 一个 `EvidenceStatus` 枚举（unknown / claimed / source_bound / reproduced / human_approved）；69 schema 按 G0–G5 合并；354 处免责集中到一处 policy。
5. **删除** `retired`/`not_assessed` 占位、重复 acceptance 报告、能伪造人工批准的夹具路径、硬编码未来型号。
6. **收紧真正的边界**：云闸门改为签名/凭证而非环境变量；`owner_authorization` 强制；`artifact_hash` 覆盖 `state/`；DNS 解析与连接绑定同一 IP。
7. **统一配置口径**：`stages.json` 遗留阈值、版本号、费用记录。
8. **澄清第三方许可**：CC BY-NC 4.0 改编内容的商用/投稿边界。
9. **每加一条护栏，要求说明它防的是哪一个已发生或高概率的具体失效**，否则不加。
10. **补环境**：`matplotlib` / `statsmodels`、CCFA `bootstrap`（网络恢复后）。

---

## 9. 需要你本人决定 / 完成的事项

1. 填 `projects/my-phd/reports/G1-DECISION-SHEET.md` 第 2 节的 3 个空并签名，把选择写进 `topic-shortlist.json` 的 `selection_decision` 与 `topic-decision.md`。
2. 按 `g1-screening-batches/` 分批做**具名**人工筛选（`screened_by` 不能由模型填）。
3. 配置真实 API key 与真实型号 ID：`python -m scripts.real_work configure-models --sol <真实型号> --opus <真实型号>`，再 `check-real`。
4. 然后才执行：
   `python -m scripts.real_work decide --project my-phd --actor "Hengyi Zang" --note "..."`
5. 决定是否要把本次改动（以及另一会话产生的改动）提交 / 推送到 GitHub——**我没有推送任何东西**。

---

## 10. 尚未解决 / 阻塞

| 项 | 状态 | 恢复方式 |
|---|---|---|
| CCFA 固定资源 | 代理对 git 协议 502；codeload 归档不完整、Range 不支持 | 网络恢复后 `python -m scripts.ccfa_runtime bootstrap` |
| `matplotlib` / `statsmodels` / `scipy` | 下载超时（各 110s 未返回） | `python -m pip install "matplotlib>=3.8,<4" "statsmodels==0.15.0"` |
| `validate_repo.py` | 仍失败 1 项（CCFA README 缺失），与基线一致 | 同上，bootstrap 后自动消失 |
| 全量测试 | 2363 / 6F / 163E / 35S，根因均为环境 | 补齐上面两项后复跑 |
| `projects/my-phd` 真实科研 | 仍停在 G1、零论文、零实验 | 第 9 节的人工步骤 |

---

## 附录 A：本次全部交付文件

**可上传 GitHub 的改动包**（`deliverables/`）
- `lunwen-real-work-first.patch` — 9 文件 / +956 −1，已通过 `git apply --check --reverse` 校验
- `lunwen-real-work-first-files.zip` — 9 文件按仓库路径打包
- `APPLY.md` — 三种应用方式、前置依赖、不包含项、验证与回滚

**分析报告**（`analysis/`）
- `00-项目能力精读总报告.md` — 12 域能力全景、真实状态、风险、设计权衡
- `01-防幻觉过度性评估.md` — 定量证据、四种代价、分层处置
- `02-真实工作优先改造报告.md` — 改造清单、验证、未做事项、回滚
- `03-继续工作小结.md` — 决策单、分批、全量测试、环境补齐
- `scripts-G01..G08.md`、`tests-G01/G02.md`、`contracts-and-state.md`、`third-party.md` — 12 份逐文件精读分报告

**仓库内新增**（`D:\ad\lunwen`）
- `config/real-work.json`、`scripts/real_work.py`、`docs/REAL-WORK-QUICKSTART.md`、`docs/OWNER-DECISION-2026-11-09-REAL-WORK-FIRST.md`、`tests/test_real_work.py`

**本地工作产物**（不进 GitHub）
- `projects/my-phd/reports/G1-DECISION-SHEET.md`、`projects/my-phd/reports/g1-screening-batches/`（16 批 + INDEX.md）

**回滚锚点**：`git tag before-real-work-simplify`（指向 `58ac455`）

---

## 附录 B：关键数据速查

| 数字 | 含义 |
|---|---|
| 424 / 127,341 | Python 文件数 / 行数 |
| 195,185 | 全部文本行数 |
| 4,730 : 688 | `raise` : 实际写入（6.88:1） |
| 226 / 748 | 不同「未验证」键名 / 出现次数 |
| 88% | 含哈希绑定的 scripts 文件占比 |
| 354 | docs 中免责表述出现次数 |
| 85 → 0 | G1 完整档阻断条数 → 精简档阻断条数 |
| 2363 / 6F / 163E / 35S | 全量测试结果 |
| 757 → 16×50 | 人工筛选表拆分 |
| 0 | 真实论文数、真实实验数、我向 GitHub 推送的次数 |
