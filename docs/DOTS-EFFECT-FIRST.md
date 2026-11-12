# dots 效果优先工作方案

依据 owner 决定 `owner-2026-11-09-effect-first`（`docs/OWNER-DECISION-2026-11-09-EFFECT-FIRST.md`）
与 `AGENTS.md` 第 25 条（2026-11-09 三项 owner 决定的合并条款）。本文只解决
「在哪里跑什么最有效」，不新增限制。

## 一句话结论

**让 dot 当常驻研究大脑 + 桌面操作员，把需要 Docker/GPU/正式实验的重活派给有特权的机器。**
不要在 dot 的沙箱里硬装 Docker 或 WSL——那是物理边界，不是仓库规则能改的束缚。

## 1. 为什么装不了 Docker / WSL

| 事实 | 后果 |
|---|---|
| 无 sudo、无 Linux capabilities、系统目录只读 | 装不了系统级包、内核模块、驱动 |
| Docker 二进制可能存在，但连不上 host socket；rootless 缺所需特权 | **Docker daemon 起不来**，容器类上游仍跑不了 |
| Kata VM + bubblewrap 沙箱，代码环境与协调/安全系统分离 | 不能通过提权绕过；也不该绕过 |
| 出站走 HTTP 代理、拒绝直连与云元数据；入站不对外 | 忽略 proxy 环境变量的工具会连不上；不能对外提供服务端口 |
| 底层是 Debian 13 Linux VM | **WSL 是 Windows 主机特性，在这里概念上不成立** |

试图突破这些是平台安全边界和服务条款问题，改 `AGENTS.md` 无效。正确解法是
**换一台有特权的机器**，而不是删规则。

## 2. 等效方案（按推荐顺序）

**A. 配对本地电脑（最省事）**
dot 可通过 ChatGPT 桌面端连接一台个人电脑（该机需保持在线、一次只能连一台）。
在那台 Windows 机器上装 WSL2 + Docker Desktop，dot 就能在配对会话里使用终端、
文件和 Docker。本机 `wsl.exe` 目前被安全策略黑名单拦截，需先在安全中心解禁；
解禁后这条路完全合规，且能同时解决我们这边无 docker / 无 WSL 的问题。
配对访问仍受 local sandbox 与 action checks 约束，可随时撤销。

**B. 自备一台有 root 的云 VM**
按课题需要选 CPU/GPU 配置，装 Docker、模型权重、Electron/Bun 工作台。dot 通过
SSH / 浏览器 / API 指挥它；`wrap` 的 `tool_root` 可以直接指向仓库外这台机器。
AI-Scientist（CUDA）、MiroThinker（权重）、PaperBanana（图像服务）、RD-Agent
（实验容器）属于这一档。

**C. GitHub Actions 的 Docker job**
需要隔离容器与**正式科研实验**时，走仓库已有的 workflow（`validate.yml` 里的
Docker isolation probe 与 real Docker executor，以及 G3 封存后的
`experiment_runner.py`）。dot 负责准备输入、发起、读回 artifact，
不自己充当实验执行器。

> 分工原则：dot 负责「找、想、写、盯」，有特权的机器负责「算、跑、隔离」。
> 这比在沙箱里硬装 Docker 更快，也更不容易把证据链弄乱。

## 3. dot 该承担的高价值工作

按 owner 的四个目标展开。每一项都必须带**真实来源 URL 与访问日期**，
并落回仓库的候选证据队列。

| 目标 | dot 具体做什么 | 回到仓库的产物 |
|---|---|---|
| 课题创新与价值 | 跨源检索 + 专门找反证；维护「最近工作差异矩阵」；列竞争假设与能区分它们的判别性检验；把「如果结论错了会看到什么」写成可证伪预测；用浏览器直查目标期刊近期录用文章 | 差异矩阵、竞争假设表、待检验预测清单 |
| 成果新颖性 | 维护新颖性候选与「最接近工作」逐条对照；用 proactive research 追踪新论文；双向展开引用链；记录检索饱和与未饱和的真实状态 | 带 receipt 的候选新颖性台账，unknown 如实保留 |
| 论文质量 | 逐主张核对证据；图件与正文数值/术语/符号一致性；不同模型家族的独立批评；按证据重写论证而不是换同义词；按审稿视角列 concern cards | 行级发现、concern cards、待修订清单 |
| 投更好的期刊 | 核对目标刊当前官方页的范围、文章类型、模板、OA 与 AI 政策；来源绑定的分区证据（未知就标 unknown）；按审稿标准倒推证据缺口；准备投稿材料包 | 期刊匹配表、投稿前清单、G5 材料（**不自动投稿**） |

这些工作天然适合常驻、带浏览器、能长时间盯着的 dot，比在一次性会话里做更有效，
也正是「效果优先」该放大的部分。`docs/TOOL-CAPABILITY-MAP.md` 提供逐决策点的
工具选择、有效性判据与对照运行方法，**全部可选**；按 owner 最大灵活决定，
工具选择、顺序与环境随时可换，不必先走任何映射或对照流程。

## 4. 在 dot 云电脑上确实能装 / 能跑的

- **可以**：`pip --user` / venv / conda、预编译用户态二进制、Node / Bun、Python 与 R 包、
  CPU 可跑的小模型（体积允许时）、localhost 服务（仅本环境内）、浏览器自动化、
  长任务与定时任务、无需特权的图形工作台应用。
- **注意**：磁盘/内存看账号实际配额；无 GPU；出站需走代理；入站不对外；
  auto-review 可能拦下动作要求批准；安全监控可暂停/停止；**停止主任务不会自动
  回滚已执行动作**。
- **密钥**：不要把 API key 贴进对话或可读文档（官方明确模型仍可能看到）。
  优先放在 Actions Secrets 侧，或使用按域名白名单注入的 network secrets。

## 5. 与仓库的衔接（已按效果优先放宽）

- 工具输出**不再一律 advisory**：owner 可授权某类输出直接进入候选证据队列
  （`AGENTS.md` 第 25 条）；前提是每条都哈希绑定、并在连到任何 claim 前完成来源核验。
- 用 `scripts/third_party_runtime.py` 的 `wrap` / `bind-output` 生成回执，
  再用 `promote --receipt <回执> --authorized-by Owner` 把哈希绑定的输出放进
  `evidence/candidates/`（状态 `candidate_unverified`，
  `source_verified: false`、`claim_linked: false`）。
  dot 的 Activity View 只作观察，不作证据链。
- dot 不写 `projects/*/state/`、不批 G0–G5、不改 `claim-evidence.csv`、
  不跑 `experiment_runner.py` 之外的正式实验、不自动投稿。保留这一条不是治理洁癖：
  两套状态机会让「哪个结果被登记、哪个主张由谁支持」失去唯一答案，
  反而拖慢投稿准备。把决定权留给 owner 是最快的路径。
- 建议给 dot 设一条 Custom Rule：**只产出候选与回执，不自行批准任何阶段**。

## 6. 立刻可执行的第一步

1. 若走方案 A：在安全中心解禁 `wsl.exe`，本机装 WSL2 + Docker Desktop，
   在 ChatGPT 桌面端把这台机器配给 dot。
2. 让 dot 连接 GitHub 与目标期刊官网，跑一次「当前课题的最接近工作 + 反证检索」，
   要求每条带 URL 与访问日期。
3. 用 `bind-output` 把清单哈希回传仓库，按 owner 决定进入候选证据队列。
4. 需要 Docker / GPU 的实验，派给 Actions 或自备 VM，回执再汇合。
5. 之后再按同样方式接第二个上游，不要一次铺开。

工程验收不等于科学有效。更多算力、更少的流程摩擦能提升产出速度；
能否投到更好的期刊，最终仍取决于证据强度、新颖性论证和独立批评的质量。
