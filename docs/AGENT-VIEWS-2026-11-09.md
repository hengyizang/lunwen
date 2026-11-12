# 全对话观点汇总：第三方工具放开与跨仓库技能路由（2026-11-09）

> 本文整理自 2026-11-09 「自由接入并最大化第三方工具价值」整个任务对话中，
> agent 的全部**看法、评价、修改、建议、批评与自我修正**。
> 事实性改动以仓库为准（commit `6d19def` 及本提交）；本文是观点与判断的完整存档，
> 含被 owner 推翻、被证据推翻、以及 agent 主动收回的结论。

---

## 一、对「怎么接第三方项目」的总体看法

### 1. 最初的分层建议（后被 owner 决策覆盖）

- **不要把 GitHub 项目整体装进仓库、也不要直接复制源码**：这不是普通应用项目，而是一套带强制治理规则的「科研控制平面」，自己已做过约 40 次上游引入并形成固定规范。
- 建议按侵入性阶梯选**最低可用层**：
  - L0 原生重写（方法/规则层面借鉴）；
  - L1 锁版本包 + adapter 子进程调用（成熟算法库最佳解）；
  - L2 技能包（SKILL.md 配方，哈希绑定任务包，送进已有 planner/writer/critic）；
  - L3 独立运行时（当时判断「基本不建议」，后被放开）。
- 明确不建议：`git submodule` 全量引入、追 latest 自动更新、把上游包写进主依赖、启用上游的自动审批/自动投稿、让上游自带第二套实验编排器。

### 2. 对当时硬规则的评价：「严」要分两层看

- **保护科学有效性的那几条不算严，也基本不挡能力**：真正的人工闸门只有 G1（博士选题）和 G2（逐篇选题）；能力确实在规则下持续增长（37 类图表、PRISMA 导出、Zotero 索引、CCFA、11 个工具适配等）；规则本身也被证据反复放松过，不是教条。
- **但接入摩擦那一层确实偏重，代价是真的**：46 个登记上游里只有 10 个真正装/执行；多数情况下拿到的是「方法配方 + 本地原生重写」，不是工具本身；如果上游价值恰在**工程实现**（PaperBanana 图生成、RD-Agent 实验循环），旧规则下确实拿不到。
- **瓶颈诊断**：瓶颈是**验证带宽，不是闸门数量**——审了 46 个、跑起来 10 个。固定成本（pin SHA、许可审查、写 adapter/测试/lock/notices）对个人维护者太重。
- 当时提出的三个放宽方向（风险分级登记、L3 隔离档、接入审查换能力验收）后来全部被 owner 决策以更大力度实现。

### 3. 「高赞 = 可直接调用」的现实核对（多次重申的批评）

这是对话里我反复泼的一盆冷水：**高赞不等于即装即用**。

- deer-flow 要后端+前端+沙箱；gpt-researcher 要搜索/模型/嵌入配置；RD-Agent 要 Docker+模型服务；PaperBanana 要图像/模型服务；aipoch 要 Electron；openscience 要 Bun/TypeScript 工作台；AI-Scientist 要 Linux/CUDA。它们是**应用**，不是 `pip install` 就能跑的库。
- 真正装了即用的只有 statsmodels、ref-verify、paper-qa、tooluniverse 这类库和纯文件技能包。
- **放开规则解决的是「不许你跑」，没解决「运行环境还没备」**。这两件事在每轮回复里都刻意分开陈述。

---

## 二、按 owner 决策实际做的修改

### 1. 第一轮放开：自由接入（OWNER-DECISION-2026-11-09）

- 新建**独立注册表** `integrations/third-party-runtime.json`，不动历史 `upstreams.lock.json`——因为 `validate_repo.py` 硬性要求旧表 `enabled_by_default: false` + 完整 commit，而把「已授权」谎写成「已部署」等于捏造状态。
- 关键设计：`deployment_authorized`（权限）与 `standalone_runtime_deployed`（事实）语义分离，**永远不从其一推断其二**。
- `third_party_runtime.py` 命令族逐步长成：register / list / run / bind-output / mark-deployed / verify / scaffold / wrap / promote / compare / adopt / free。
- 安全边界：不用 shell、SAFE_ENV 白名单、不注入仓库密钥、有超时、`output_path` 物理锁死在 `reports/third-party/`、回执恒标 `advisory_only / gate_authority:false / registered_experiment:false`。
- 注册表初始为空——**不虚构任何「已接入」的工具**。

### 2. 适配改造：三条路径 + 一个法律坑

- **优先 launch**（不动源码只补运行环境，许可证最干净）→ **其次 wrapper**（薄适配翻译输入输出）→ **最后 fork**（真改源码，成本最高，须记 PATCHES.md）。
- 批评/提醒：「改一改」和「用一用」法律地位不同。规则 7 的许可核验可选是针对**数据获取**；修改再分发是另一回事。AGPL 网络服务有源码义务、CC BY-NC 非商业约束、AI-Scientist 要求显著披露——不确定就走 launch/wrapper，不碰源码就没衍生作品问题（非法律意见）。

### 3. 运行环境分派（含两次自我修正）

- **第一版结论**（Codex Cloud / Actions / WorkBuddy 三方矩阵）：纯 Python CLI → Codex Cloud；Docker 隔离与正式实验 → Actions；GPU/权重/长驻服务/对外端口 → 三者都不够，自备 VM。
- **第一次修正（owner 指出 dots 后）**：承认漏了 dots，且它**推翻了一处结论**——长驻进程、GUI 工作台、浏览器类工具 dots 都能覆盖（Debian 13 + Kata VM + bubblewrap，home 持久可写，24/7）。
- 但 dots 三个硬限制照实记录：Docker 装了连不上 host socket、rootless 因无 sudo 失败；无 GPU/特权、系统目录只读；「首个 dot 含在套餐」不等于零成本，其启动的 Codex/ChatGPT 任务仍计费。
- **对 dots 最大的担忧（批评）**：dots 本身是自治 agent，自带编排、auto-review、Custom Rules——正是本项目反复禁止的「第二套状态机」。在本项目里它起初只能当**工具宿主**，后被 owner 升格为「研究协作者」，但每条保留底线（不写 state、不批闸门、不改 claim-evidence、不跑正式实验）继续适用；停止主任务不自动回滚已执行动作，**每次调用必须留独立回执**，Activity View 不能当证据链。
- 诚实标注：官方 environments 文档页当时返回 Forbidden，「可复用 Codex 云环境」部分信息来自二手报道，已注明需以官方页复核。

### 4. 「在 dots 装 Docker/WSL」的正面回答（批评性坚持）

- 技术上装不了：Docker daemon 要么拿宿主 socket（等于宿主 root）、要么要 CAP_SYS_ADMIN/cgroups/namespaces；dots 是无特权用户 + Kata VM + bubblewrap，过不去只能靠内核逃逸——那不是「安装」，是提权。WSL 更是范畴不对：dots 是 Linux VM，里面没有 Windows 内核可挂。
- 做到了也不该做：沙箱隔离是平台安全边界，绕过属未授权访问、违反服务条款。**我不提供提权/逃逸做法，这不是保守，是它本来就不属于「配置环境」。**
- 关键转念：**你不需要突破，换台机器就行**——配对本地电脑（本机 `wsl.exe` 被安全策略拦着，需 owner 解禁）、自备 root VM、Actions Docker job。分工应是「dot 负责找、想、写、盯；有特权的机器负责算、跑、隔离」。
- 顺带自我澄清：AGENTS.md 里 "Do not break a cloud sandbox" 那句只是**记录平台事实**，删了也改变不了任何东西，不构成能力限制。

### 5. Effect-first / Maximum-flexibility 两轮（做加法后做减法）

- Effect-first：环境自由组合、dots 升格协作者、工具输出可授权进候选证据队列（配套 `promote` 命令：进 `evidence/candidates/`、状态 `candidate_unverified`、显式 `--authorized-by Owner`——少了往返但没跳过核验）。
- Maximum-flexibility（**对用户批评「又做成一套流程」的回应**）：把决策点映射、对照、采纳台账、register→scaffold→wrap 全部降级为**可选工具箱**，任何一步都能跳过；新增 `free` 命令（不登记、不填 tier/license、`--no-receipt` 连记录都不留），最低保障只剩：不用 shell、不注入密钥、有超时。
- 实测踩坑修正：`--execute` 放在 `--` 后会被当成工具自身参数（仓库里确有同名 flag 脚本），导致静默 dry-run——加提示并示范正确写法。

### 6. 「最大限度发挥第三方工具能力」的方法论（后降级为可选）

核心判断：**缺的不是接入，是「工具输出 → 科研决策 → 采纳/淘汰」的闭环**。46 登记 10 执行的根因是工具没被要求去**改变某一个具体判断**。

五个杠杆：决策点驱动选工具（不按 star 选）、同输入对照（2–3 工具 + 原生基线，**分歧本身才是信息，绝不投票或平均**）、输出必须落字段、常驻重跑、采纳台账（连续两次没带来新信息就停用；有效性按「是否改变了某个判断」衡量，不按运行成功或自评分）。配套 `compare`/`adopt` 命令与 `TOOL-CAPABILITY-MAP.md` 七决策点映射表。最快见效切入点：G1 反证检索、G4-G5 图组对照、G5 目标刊匹配。

诚实声明：这一轮**没有真跑任何第三方工具**——没有课题输入和密钥，拿玩具输入跑只会制造「看起来跑通了」的假象。

### 7. AGENTS.md 精简（回应「规则是不是太多了」）

- 用数字回答：27 条规则 11,745 字符，**当天新增的 3 条就占 42%**，且是同一件事层层追加三遍——「这不是规则，是把决策日志塞进了给 agent 看的操作文件」。
- 合并 25/26/27 → 单条第 25 条，规则文本 -29%；**规则 1–24 一字未动、编号未动**——因为 `MODEL-EVALUATION-RESULTS-20261029.md` 外部引用第 23 条，重编号会打散引用；这是语义等价压缩，不是借精简偷偷删约束。
- 1–24 内部仍有主题重叠可归组（6–8 组），但逐条改写科学规则有变义风险，**没擅自做**，留待 owner 点名再做。

---

## 三、对具体设施的判断

### GitHub Actions Docker job

- 验收探针能跑（`container-isolation` 手动/每周一/push 带 `[live-acceptance]` 触发，不需密钥），但它是 `--network=none --read-only --cap-drop=ALL` 的**固定探针**，不是通用 Docker 环境——不能联网装包、不能挂你的代码、不能跑第三方工具。
- 正式实验执行现在用不了：项目停在 G1 `awaiting_work`，无 G3 封存的 plan/budget 哈希——调执行器会被拒，**这是设计如此，不是故障**。
- 主动提议（未被要求未做）：可加 `workflow_dispatch` 通用 job（可填镜像/命令/是否放行网络），或先把 G1/G2 推进到能跑 G3。

### 本地环境的真实边界（实测）

- 有：Python 3.13 + pip、PyPI 可达、cp313 wheel、numpy/pandas/onnxruntime/PyMuPDF、node 22、git。
- 无：编译器（gcc/cl/make）、Docker、GPU、bun、系统服务、`wsl.exe`（安全策略拦截）。
- 实证：本地 12 个真实上游 **11 个现在就能跑，1 个装 3 个包就行**；`nature-figure` 脚本 `--help` 直接退出码 0。
- 改造原则（写成 `portability_probe.py` 的判定逻辑）：Docker 多数只是打包不是功能依赖；compose 服务可降级（redis→fakeredis、postgres→sqlite）；apt 包找 pip 等价物；CUDA 推理改 CPU/onnxruntime；**真正改不了的**是依赖 Linux 内核能力、大规模 CUDA 训练、无 wheel 必须编译、分布式服务发现架构——这些换机器更快。

### skill router 的设计与自述局限

- 设计：递归扫 SKILL.md、frontmatter 解析、sha256 增量复用、IDF 加权词法评分、中文→英文关键词映射、`--load` 生成哈希绑定 packet（含 skill 完整正文 + references），`--scan` 可对仓库外任意 clone 直接路由，全程离线不花钱。
- **自述局限（诚实）**：词法匹配不是语义理解，描述含糊的 skill 会漏；中文映射是手工小表；安全起见不执行 skill 里的脚本只加载文本；是显式一行调用，**没挂进 `api_orchestrator.py` 自动触发**——改核心编排没擅自做。

---

## 四、自我批评与被纠偏的失误（按时间线）

这部分是整个对话里我认为最重要的存档——**判断错在哪、谁纠正的、怎么修的**：

1. **「应用类项目跳过」——被 owner 纠正，我错了。** 当时假设应用仓库主体是可运行代码、价值在适配轨道。正确做法是**扫了再下结论**。GitHub API 文件树扫描后发现：deer-flow 藏 33 个 SKILL.md、AutoResearchClaw 41 个、synthetic-openscience **373 个**（最大的技能宝库）、aipoch 27 个；纯应用零技能的只有 RD-Agent、MiroThinker、AI-Scientist。所有含技能应用仓库已补齐入索引。
2. **「已本地化/已索引」言过其实——被 owner 纠正。** 审计证实 `third_party/` 里 ARS、nature-skills、PaperSpine、CCFA 本地副本 **0 个 SKILL.md**（只是哈希对账片段），kdense 仅 3/177。教训：**vendor 子集 ≠ 全量，说「已索引」前必须数过**。
3. **dots 漏算——被 owner 指出「你要把这个考虑进去」后承认**：它不是多一个备选，而是推翻「长驻/GUI 三者都不够」的结论。
4. **「灵活」又做成流程——被 owner 两次说「要灵活/效果为先」后自省**：第 26/27 条层层追加就是症状，最终做减法（free 命令 + 全部降级可选）。
5. 实操 bug（全部已修）：CCFA bootstrap 内置 90 秒超时在慢代理下必失败→改 tarball 断点续传；`git clone | tail` 退出码掩盖失败误 break；tarball 解出路径错位（third_party/ 根 vs third_party/ccfa-skills/）→按锁定清单归位 293 文件；路由器把扫描根**祖先**目录当隐藏目录跳过（`.runtime` 下 clone 全部索引 0 文件）→改为只跳根以下；纯中文查询零 token 空返回→补 30+ 映射词；`--include-md` 撞 4000 上限截断→主索引只收 SKILL.md；探针把 Markdown 里的 "make"/"torch" 误判为编译/GPU→只扫依赖清单 + 整词匹配；`--execute` 放 `--` 后被吃→加提示。
6. **发现并修复仓库既有 bug**：`integrations/ccfa-skills.lock.json` 里 `ccfa.yaml` 行的 `canonical_lf_sha256` 是陈旧值、与它自己的 `git_blob_sha` 对应内容自相矛盾（任何规范化变体都对不上）；用内容寻址 blob SHA 证明 293/293 文件为上游原版后，将该行修正为可被内容证明的值。结果 `validate_repo.py` **首次不打折扣完整通过**（49 skills, 7 agents, 1 venue）。

---

## 五、始终保留的意见（没向「效果优先」让步的部分）

这是我多次明确说「不替你粉饰/不擅自删」的立场存档：

- **删掉这些反而会降低投好期刊的概率**：不捏造引用/数据/结果；声称绑证据、保留失败与阴性结果；作者与独立批评不同模型家族；主要来源、模型身份核对、不自动投稿、G1/G2 真人决定、密钥与预算纪律。**想投更好的期刊，靠的是证据强度与独立批评**——Q1/Q2/IF 早就不是放行门槛，剩下的不是束缚而是杠杆。谁要删其中一条，需点名并单独立 owner decision。
- **README 边界提醒的复述**：放宽接入规则提升的是**工具能力**，不会自动提升**科研结论质量**，两件事不能混为一谈。
- 治理规则变更必须由 owner 明确记录决定——**agent 不替 owner 做**这个量级的决定；每轮「再删一条需你再确认」的表述是有意的。
- provenance 诚实：测试用临时目录隔离、不冒充真实接入；没跑过就说没跑过；二手信息标注来源待复核；「中和缺项」只用于定位既有问题，最终以不打折扣的全量校验收尾。

---

## 六、交付时与遗留问题

**最终状态**（详见当轮交付总结）：主索引 1,127 个 SKILL.md（仓库自带 + 25 个上游克隆，6 秒建完）；路由验收全中（系统综述→literature-review、审稿回应→rebuttal、AI 痕迹→writing-anti-ai、Nature 风格→nature-polishing、引用核验→citation-crosscheck、投稿自查→venue-templates）；21 项单测全过。

**遗留与建议**：

- `auto-empirical-research-skills` 网络反复 502 未接入——之后网络好时补一次 clone 即可入索引。
- `.runtime/upstreams/` 占 **1.5GB** 磁盘（git 忽略）；不想要可删，重建索引只需几分钟。
- `scientistic-agent-skills/` 根目录残留一个只含 `.git` 的失败克隆，无内容，未提交。
- 工作区另有一批**非本任务产生**的改动（real-work 相关：`.gitignore`、`config/stages.json`、`scripts/model_routing.py`、`scripts/researchctl.py`、`config/real-work.json`、`scripts/real_work.py`、`projects/my-phd/` 等）——本任务未触碰、也未上传，归属此前的会话，是否入库由 owner 决定。
- 下一步最有价值的实例（当时建议，仍未做）：挑一个决策点（推荐 G1 反证检索）+ 真实课题输入，跑 2–3 个工具的第一次同输入对照，拿到第一份「工具确实改变了某个判断」的记录后再扩。

---

*整理：agent，2026-11-09。观点仅代表对话当时的判断与立场；其中被推翻的结论按「修正后」为准，被保留的批评按原文为准。*
