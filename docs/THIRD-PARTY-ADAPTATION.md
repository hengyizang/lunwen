# 改一改再调用：第三方工具适配指南

Owner 决定 `owner-2026-11-09-third-party-runtime` 已放开接入限制。本文回答一个
具体问题：**上游不能开箱即用地调用时，怎么改、改哪里、改完怎么接进本仓库。**

配套：`docs/THIRD-PARTY-RUNTIME-POLICY.md`、`scripts/third_party_runtime.py`。

## 1. 三种「改法」，成本差一个数量级

| 路径 | 改什么 | 适用情况 | 代价与风险 |
|---|---|---|---|
| `launch` **补运行环境** | 完全不改上游源码；只写启动配置、装依赖、起服务、填模型端点 | 上游本来就有 CLI / HTTP 入口，只是缺后端、Docker、依赖或配置 | 最低。没有衍生作品，许可证最干净。优先选这条 |
| `wrapper` **写薄适配层** | 不改上游源码；加一层把项目输入翻译成上游参数、把上游输出规范成本地结构，并用开关关掉危险默认值 | 上游能跑，但参数/输出格式不兼容，或默认会自动审批、自动投稿、只挑最高分 | 中。需记录上游版本和所有开关 |
| `fork` **改上游源码** | 直接 patch 上游（去掉硬编码、拆掉第二套状态机、去掉静默 provenance 改写等） | 前两条都做不到，且这个能力确实值得 | 最高。许可证义务、升级 rebase 成本、长期维护负担。最后手段 |

**建议顺序：先 `launch`，不行再 `wrapper`，最后才 `fork`。** 仓库历史上大量上游只被
「借鉴概念后原生重写」，那属于第四条路；owner 决定之后不必再默认走它。

## 2. 落地步骤

```bash
# 1) 登记（不再需要逐文件审查或 pin 完整 commit）
python3 scripts/third_party_runtime.py register --id deer-flow \
  --repo https://github.com/bytedance/deer-flow --ref main \
  --tier network-no-credentials --license MIT

# 2) 生成适配骨架：launch / wrapper / fork 三选一
python3 scripts/third_party_runtime.py scaffold --id deer-flow --kind launch

# 3) 编辑 adapters/deer-flow/launch.json
#    - tool_root：改过的上游目录（可在仓库外）
#    - argv：真实入口；可用 {tool_root} {input} {output} 占位符
#    - output_path：必须留在 reports/third-party/ 下
#    - env_keys：环境变量白名单，密钥一律不在这里
#    - disabled_upstream_behaviors：你关掉了上游哪些默认行为

# 4) 先 dry-run 看展开后的命令，再真跑
python3 scripts/third_party_runtime.py wrap --id deer-flow --input evidence/query.json
python3 scripts/third_party_runtime.py wrap --id deer-flow --input evidence/query.json --execute

# 5) 检查注册表与所有适配配置
python3 scripts/third_party_runtime.py verify
```

`wrap` 不用 shell、不注入仓库密钥、有超时；自动记录 `adapter_config_sha256`、
`input_sha256`、`output_sha256`、argv、退出码、stdout/stderr 哈希，并生成
`advisory_only: true` / `registered_experiment: false` 的回执。输出文件路径被强制
限制在 `reports/third-party/`，适配层因此无法写 state、稿件或闸门文件。

`scaffold --kind fork` 额外生成 `PATCHES.md`，要求记录基底 ref、保留的许可声明、
改动文件与原因、移除的上游行为、升级计划。

## 3. 必须关掉的上游行为

这些是本项目真正不能让渡的东西，与「用哪个工具」无关。改造时通过配置开关或
patch 明确禁用，并在 `disabled_upstream_behaviors` 里如实记录：

- 自动批准 G0–G5、自动投稿、自动改写实验计划或冻结结果；
- 自带第二套状态机 / 项目状态目录，与本地控制平面争权；
- 只保留最高分结果、丢弃失败与阴性结果、选择性报告；
- 静默改写 provenance、伪造来源哈希、冒充持久化写作者；
- 把密钥写进文件、URL 或日志，或把原始研究数据上传到外部端点。

输出始终是 **候选材料**。要变成科学主张，仍须走：主要来源核验 → 已批准的 G3
计划 → `scripts/experiment_runner.py` → `claim-evidence.csv` 绑定。适配回执不能
替代任何一步。

## 4. 改造前先核对许可证（最容易踩的坑）

规则 7 把「许可/研究用途核验」设为可选元数据、不作**数据获取**前置门槛；但
**修改上游源码并再分发**是另一回事，义务不因该规则消失。以下只是核对清单，
不是法律意见；请以仓库内实际 LICENSE 与你自己的使用场景为准。

`integrations/upstreams.lock.json` 和 `THIRD-PARTY-NOTICES.md` 是本仓库已有的
权威记录。已登记上游的许可分布大致如下：

| 类型 | 已登记示例 | 改造时通常要留意 |
|---|---|---|
| MIT / Apache-2.0 / BSD-3-Clause | deer-flow、gpt-researcher、PaperBanana、RD-Agent、PaperSpine、CCFA、ToolUniverse、PaperQA2、proselint、statsmodels | 一般允许修改与再分发，通常需保留版权与许可声明、注明改动；Apache-2.0 另有专利与 NOTICE 条款 |
| AGPL-3.0 | llm-for-zotero、beaver-zotero、openpaper | 若把改后的版本作为网络服务提供，通常触发源码提供义务；这三项目前在本仓库只登记了「借鉴概念」，未部署代码 |
| CC BY-NC 4.0 | academic-research-skills、ars-codex、experiment-agent | 非商业限制、署名、相同许可与改编标注；`experiment-agent` 因与本地实验状态机重复被明确标为「not installed」 |
| 自定义源码许可 | AI-Scientist v1/v2（The AI Scientist Source Code License 1.0） | lock 的 `selection_note` 已记录：上游软件生成科学手稿时要求显著披露，并保留下游条件 |
| 自定义非商业 / CC-BY-SA-4.0 / CC0 | PaperLens、Auto-Empirical-Research-Skills、awesome-econ-ai-stuff | 分别核对非商业、相同方式共享与署名要求 |
| 审查时无 LICENSE 文件 | journal-recommender | 默认「保留所有权利」，`third_party/` 里一行代码都没拷；改造或复制前应先取得明确许可 |

改造前建议做三件事：确认该 commit/tag 上的 LICENSE 原文；把许可标识与
`license_source_url` 写进 `register`；`fork` 时在 `PATCHES.md` 里记录保留的声明。
不确定时优先选 `launch` 或 `wrapper` —— 不动源码就没有衍生作品问题。

## 5. 运行环境从哪来：三种云端/本地的边界

`scaffold` / `wrap` 解决的是**接口**。运行环境要另外解决，而且候选环境
能力差别很大。以下为 2026-11-09 核对结果。

> **2026-11-09 修正：**下表是未计入 OpenAI **dots 云电脑**的初版核对。
> dots 的常驻云电脑改变了「长驻服务 / 后台进程」一档的结论，也覆盖了需要
> GUI 工作台的上游；详见下方 §5.1。表中其余结论仍然成立。

| 能力 | Codex Cloud 环境 | GitHub Actions runner（正式执行环境） | WorkBuddy 本地会话 |
|---|---|---|---|
| pip / apt 装依赖 | 支持，已有 `scripts/bootstrap-codex-cloud.sh`（含 `--with-ai4science`） | 支持，各 workflow 自行安装 | 支持；实测 Python 3.13.14 / pip 26.1.2，github.com 可达 |
| Docker daemon | **不支持**：bootstrap 脚本明确「不安装或启动 Docker」 | 支持，`validate.yml` 已有 Docker isolation probe 与 real Docker executor | **无**：实测 `docker: command not found` |
| WSL2 | 不适用（Linux 容器） | 不适用 | **被本机安全策略拦截**，需使用者自行在安全中心解禁或换机器 |
| GPU / CUDA | 未提供 | 标准 `ubuntu-latest` 无 GPU；GPU 属于付费 larger runner（Team/Enterprise） | 无 `nvidia-smi` |
| 长驻服务 / 对外监听端口 | 任务式容器，缓存最多约 12 小时，产出 diff/PR，不是服务主机 | 每个 job 一台临时 VM，出站开放、**入站被封**、job 结束即销毁 | 会话内可起进程，但会话结束不保证保活 |
| 密钥 | Actions Secrets **不会自动注入**；环境 Secrets 仅在 setup 阶段可见，agent 阶段前被移除；需另配环境变量 | Actions Secrets 在 job 内可用 | 不持有使用者密钥 |
| 网络 | setup 阶段有；**agent 阶段默认关闭**，需按环境开启并设域名/HTTP 方法白名单；出站走代理 | 出站开放 | 出站可达 |
| 科研执行权限 | **不是科研执行器**；Start skill 明确不得用 `DR_OS_CLOUD_EXECUTOR` / `GITHUB_ACTIONS` 绕过 runner 检查 | 正式唯一入口（G3 封存 + `experiment_runner.py`） | 只能做工具与探索运行 |

核对来源：`docs/CODEX-CLOUD.md`、`scripts/bootstrap-codex-cloud.sh`、
`docs/CI-VALIDATION.md`、`.github/workflows/validate.yml`；
GitHub 托管 runner 规格 https://docs.github.com/en/actions/reference/runners/github-hosted-runners
（公开仓库 `ubuntu-latest` 为 4 vCPU / 16 GB RAM / 14 GB SSD，私有仓库为
2 vCPU / 8 GB，均为 14 GB SSD；访问日期 2026-11-09）；
Codex 云环境与网络/机密说明 https://developers.openai.com/codex/cloud/environments
 与 https://developers.openai.com/codex/cloud/internet-access
（访问日期 2026-11-09；仓库 `docs/CODEX-CLOUD.md` 另记录 2026-11-06 的官方页核对）。

### 5.1 补充：OpenAI dots 云电脑（owner 于 2026-11-09 指出）

dots 是 always-on 代理，**每个 dot 配一台自己的云电脑和云浏览器**，可 24/7
工作，用户可随时打开这台电脑检查。这不是上表里的「任务式容器」：

| 方面 | dots 云电脑的实际情况 | 依据 |
|---|---|---|
| 常驻与持久 | always-on、24/7、跨会话继续；可写 home 与 workspace 且持久 | 官方产品页；第三方实测：Debian 13 + XFCE/X11 + Chrome + 终端，无特权用户 `agent`，Kata VM + bubblewrap 沙箱 |
| **GUI / 浏览器类上游** | **真正新增的能力**：有桌面、Chrome、屏幕截图与 computer use，可操作图形工作台 | 官方页「own browser」「可以打开 dot 的电脑检查」；仓库内亦有 Codex 截图说明 |
| Docker | **不可用**：实测 Debian 13 无 sudo，Docker 装了但连不上 host socket，rootless 也因权限失败 | OpenAI 开发者论坛实测，经第三方评测转述 |
| GPU / 特权 | 无证据支持；无特权、无 Linux capabilities、系统目录只读、出站走 HTTP 代理 | 官方安全文档 + 第三方实测 |
| 密钥 | **secure sign-in** 让浏览器登录的密码不进入模型上下文；但官方明确「机密若单独放在可读消息或文档中，模型仍可能看到」 | 官方 dots 安全文档 |
| 自治与审批 | 自带 auto-review、Custom Rules、Activity View；动作可能被拦或要求批准，安全监控可暂停/停止；proactive research 只读且不能控制浏览器或电脑 | 官方产品页与安全文档 |
| 计费 | 首个 dot 含在 Pro / Business Premium 套餐；与 dot 对话不占 ChatGPT 用量，但**它启动/管理的 Codex 或 ChatGPT Work 任务按常规计入用量** | 官方产品页 |

核对来源（访问日期均为 2026-11-09）：
https://openai.com/index/introducing-dots/ 、
https://openai.com/index/how-we-build-safety-security-and-privacy-into-dots/ 、
https://www.cyera.com/research/dots-a-double-edged-sword-in-the-workplace 、
https://www.theslidefactory.com/?p=2692 。
后两者为第三方实测，Docker/GPU/沙箱细节以官方环境页与实际账号为准。
同期 DevDay 还发布了**可复用的 Codex 云环境**（专用 VM、合上笔记本仍继续、
任务恢复窗口约 7 天、支持按域名白名单注入 network secrets），但
`developers.openai.com/codex/cloud/environments` 本次返回 Forbidden，该段为
二手报道，需以官方页与账号实际配置复核；`docs/CODEX-CLOUD.md` 仍按原有
环境模型描述，不回溯改写。

**这条修正了什么**：初版结论「长驻服务 / 后台进程 / 图形工作台三者都不够」
不再成立——dots 云电脑可覆盖常驻进程与 GUI 类上游。**没有改变的**：Docker
daemon、GPU/CUDA、对外入站端口、以及正式科研执行权（仍只在 GitHub Actions）。

**角色已按效果优先决定升级**：`docs/OWNER-DECISION-2026-11-09-EFFECT-FIRST.md`
把 dots 从「仅第三方工具宿主」提升为**研究协作者**，可承担反证检索、创新候选、
实验代码迭代、稿件打磨与期刊匹配；输出也不再一律 advisory，可由 owner 授权
进入候选证据队列。具体分工见 `docs/DOTS-EFFECT-FIRST.md`。

**仍需保留的一条边界**：dot 不写 `projects/*/state/`、不批 G0–G5、不改
`claim-evidence.csv`、不跑 `experiment_runner.py` 之外的正式实验、不自动投稿。
理由不是治理洁癖，而是两套状态机会让「哪个结果被登记、哪个主张由谁支持」
失去唯一答案，反而拖慢投稿准备。此外，停止 dot 的主任务不会自动回滚已执行
动作，长任务也可能被 auto-review 打断——因此**每次工具调用都留独立回执**，
dot 自己的 Activity View 只作观察，不作证据链。

### 按上游需求分派（含 dots）

1. **只要 Python 包 + 一次性 CLI** → Codex Cloud 最省事。发布 `lunwen` 环境后跑
   `bash scripts/bootstrap-codex-cloud.sh --with-ai4science`，再按 `docs/CODEX-CLOUD.md`
   在新任务里验收。PaperQA2、ToolUniverse、ref-verify、statsmodels 以及大量文献
   读取/绘图类工具属于这一档。
2. **需要 Docker 隔离容器 / 正式科研执行** → 走 GitHub Actions。仓库已有可复用的
   docker job 模式；它仍是唯一被授权执行正式实验的环境。
3. **需要常驻后台进程或 GUI 工作台** → **dots 云电脑**。aipoch（Electron/CLI）、
   synthetic-openscience（Bun 工作台）、需要浏览器操作或人工可查看桌面的工具
   属于这一档。把改好的上游放在 dot 的 workspace，用 `wrap` 生成回执；
   dot 的 Activity View 只作观察，不作证据。
4. **需要 GPU / CUDA / 模型权重 / Docker daemon / 对外入站端口** → 仍然都不够。
   AI-Scientist（Linux/CUDA）、MiroThinker（权重）、PaperBanana（图像/模型服务）、
   RD-Agent 的实验容器属于这一档。需要自备云 VM、付费 larger runner，或本地
   WSL2 + Docker Desktop，再用 `wrap` 的 `tool_root` 指向仓库外环境调用。
   dots 还可**配对一台本地电脑**（需 ChatGPT 桌面端保持在线、一次一台），
   这是把本机 Docker/WSL 能力接给 dot 的一条路径，但需你单独授权。
5. **WorkBuddy 本地**适合做验证与编排：clone、装纯 Python 依赖、跑一次性命令、
   生成适配回执、把结果写回仓库；不适合承载服务或算力。

### 容易忽略的坑

- **换环境不会清零费用**。`docs/CODEX-CLOUD.md` 明确：费用继续按
  `docs/TOTAL-COST-POLICY.md` 计入既有项目累计额度。owner 决定里的
  `credentials-or-paid` 档同样规定每次尝试都计数。dots 的套餐订阅费是另一笔账，
  不能因为「含在套餐内」就当作零成本；它启动的 Codex / ChatGPT Work 任务另计用量。
- **Codex Cloud 的 Secrets 进不了 agent 阶段**。上游若在运行时需要模型 API key，
  必须改用环境变量并自行承担暴露面，或在 Actions Secrets 侧调用；不能靠把
  密钥写进 setup 脚本解决。
- **不要把 API key 贴进 dot 的对话或文档**。secure sign-in 只保护浏览器登录流程，
  官方明确其余可读消息/文档中的机密仍可能被模型看到。需要密钥的工具优先放在
  Actions Secrets 侧，或走按域名白名单注入的 network secrets。

## 6. 一个现实提醒

「高赞」不说明可运行性，也不说明适配成本。`docs/RESEARCH-AUTOMATION-TOOLKIT.md`
逐项列出了 11 个上游仍需要的后端、Docker、模型服务、Electron/CLI、Bun 工作台或
CUDA 环境。适配层解决的是**接口**，不解决**运行环境**：那些依赖仍要你自己装、
自己配、自己承担费用。建议一次只接一个工具，先跑到产出真实回执，再接第二个。

工程验收不等于科学有效。放开工具接入提升的是工具能力，不自动提升结论质量。
