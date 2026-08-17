# Doctoral Research OS

这是一个面向个人研究者的、可审计的博士级研究流水线。它把 Claude Code、Claude Science 的证据工作流和 Codex 的独立代码/统计审计组合起来，但不把“生成文字”误当成“完成科研”。

一键启动的含义是：创建研究项目、执行当前阶段并停在下一道人类审批闸门。系统不会自动批准选题、伪造数据、替你确认作者资格，也不会自动向期刊投稿。

## 第一版包含什么

- 选题情报：核心博士命题 A、可独立成立的扩展命题 B、竞争/岗位/可行性分析。
- 论文架构：默认 6 篇论文，每篇有独立贡献、数据、实验和反证条件，同时共同支撑博士主线。
- 数据获取：只获取公开或已获授权的数据，记录版本、许可、来源、校验和与拆分策略；原始数据不进入 Git。
- 实验：预注册式实验合同、计算预算、基线、消融、统计检验、失败实验和复现记录。
- 写作与修改：claim-evidence matrix、引用核验、模拟审稿、逐条回复和版本差异。
- 期刊适配：安全导入官方 Word/LaTeX 模板，将语义稿件映射到模板并进行编译/版式检查。
- 人工闸门：G0–G5。只有你能批准，代理不能替你越过。

## Windows 11 推荐安装

使用 WSL2 Ubuntu，并把仓库放在 Linux 文件系统（例如 `~/code`）而不是 `/mnt/c`。

```powershell
wsl --install -d Ubuntu
```

进入 Ubuntu：

```bash
mkdir -p ~/code
cd ~/code
git clone https://github.com/hengyizang/lunwen.git
cd lunwen
bash scripts/bootstrap-wsl.sh
```

如果希望同时安装经筛选的 K-Dense 通用科研技能子集，可在首次检查时显式启用：

```bash
bash scripts/bootstrap-wsl.sh --with-kdense
```

该选项只安装 `integrations/upstreams.lock.json` 固定提交中的 14 个通用技能，不安装全部 161 个技能。安装内容放在 Git 忽略的本地目录，同时供 Claude Code 与 Codex 发现；脚本不执行这些技能自带的代码。

Claude Code 启动：

```bash
claude --plugin-dir .
```

然后运行：

```text
/doctoral-research-os:start my-phd
```

也可以直接使用启动器：

```bash
bash scripts/start.sh my-phd
```

Codex 在仓库根目录启动后会自动发现 `.agents/skills/doctoral-research`：

```text
$doctoral-research start my-phd
```

Claude Code 会从根目录的 `.mcp.json` 启动 `codex mcp-server`。首次使用项目 MCP 配置时，Claude Code 会要求你确认信任。不要在仓库中保存 API key；使用各工具自己的登录或环境变量。

## 组件组合与许可

核心流水线自身即可运行。外部组件是受控增强，不是把多个“自动写论文”代理同时放开：

| 组件 | 在本系统中的角色 | 第一版策略 |
|---|---|---|
| 本仓库 skills + agents | 选题架构、数据许可、实验合同、闸门与审计 | 默认启用 |
| K-Dense Scientific Agent Skills | 文献、实验设计、统计、可视化、写作和期刊模板的专业方法 | MIT；固定提交；只安装 14 个通用技能 |
| Academic Research Skills | 深度研究、写作、修改和多视角审稿的可选第二套实现 | CC BY-NC；需你确认用途后在 Claude Code 插件管理器中安装 |
| Experiment Agent | 可选实验执行器 | CC BY-NC；第一版不自动安装，避免与本仓库实验状态机重复 |
| Claude Science | 文献与证据包生产者 | 通过稳定的导出合同接入，不猜测未公开 CLI/API |
| Codex | 独立代码、统计、泄漏和复现审计 | 通过本仓库技能与 MCP 接入 |

固定版本、选择理由、许可边界和 Academic Research Skills 的人工安装命令见 `references/upstream-components.md`。第三方技能仍需在首次触发前检查其脚本、网络域名、API 权限和费用。

## Claude Science 的边界

第一版不假设一个尚未公开文档化的 Claude Science CLI/API。Claude Science 可用于文献阅读和证据整理，再把导出的证据包放入：

```text
projects/<project>/evidence/claude-science/
```

`schemas/science-evidence.schema.json` 定义了导入格式。若未来有官方自动化接口，只需替换这一适配层，不需要重写研究流水线。

## 人工闸门

| 闸门 | 你批准的内容 | 系统随后允许 |
|---|---|---|
| G0 | 目标、资源、预算、申请地区和伦理边界 | 开始选题情报 |
| G1 | 核心命题 A、扩展命题 B、淘汰理由 | 拆分论文组合 |
| G2 | 论文地图与每篇 paper contract | 设计数据和实验 |
| G3 | 数据许可、实验方案、统计方案和算力预算 | 执行实验 |
| G4 | 结果、失败实验、claim-evidence matrix | 写作与修改 |
| G5 | 最新期刊资格、最终模板、作者声明和投稿包 | 标记 submission-ready |

查看状态：

```bash
python3 scripts/researchctl.py status --project my-phd
python3 scripts/researchctl.py gate-check --project my-phd
```

批准并推进（只能由你执行或明确授权）：

```bash
python3 scripts/researchctl.py approve --project my-phd --gate G0 --actor "Hengyi" --note "constraints reviewed"
python3 scripts/researchctl.py advance --project my-phd
```

## 试验期刊

首个模板适配目标是 **International Journal of Structural Stability and Dynamics (IJSSD)**。选择它是因为：

- 出版社 World Scientific [总部位于新加坡](https://www.worldscientific.com/page/about/corporate-profile)；
- 期刊官方页面报告 2025 Impact Factor 3.8，并标注为 Engineering, Mechanical Q1；
- 方向覆盖结构稳定性、结构动力学、振动与工程应用，能容纳 AI + 机械/结构健康监测、数字孪生、PINN 等研究；
- [官方投稿指南](https://www.worldscientific.com/page/ijssd/submission-guidelines)提供 LaTeX2e 与 MS Word 模板入口。

这是模板适配测试目标，不代表六篇论文都应投同一期刊。G5 必须重新在 Clarivate JCR 核验当年分区、范围、政策和费用；出版社页面的说明不能替代你所在机构对 JCR 的正式查验。

期刊机器可读清单位于 `venues/ijssd/venue.json`。模板文件不复制到仓库；从官方投稿指南下载后，用：

```bash
python3 scripts/venue_adapter.py inspect ~/Downloads/ijssd-2e.zip
python3 scripts/venue_adapter.py ingest ~/Downloads/ijssd-2e.zip projects/my-phd/papers/P01/venue-template
```

## 数据获取

数据清单必须包含来源 URL、版本、许可证、研究用途许可、再分发许可和 SHA-256。下载器只接受 HTTPS，不携带登录凭据，不绕过付费墙、验证码或访问控制。

```bash
python3 scripts/dataset_fetch.py validate path/to/dataset.json
python3 scripts/dataset_fetch.py download path/to/dataset.json projects/my-phd/data/raw --accept-license
```

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py
```

## 目录

```text
.agents/skills/        Codex 仓库级技能
.claude-plugin/        Claude Code 插件清单
agents/                Claude Code 专职子代理
skills/                Claude Code 分阶段技能
references/            流程、阶段合同和科研诚信规则
schemas/               数据、期刊和证据包格式
scripts/               状态机、数据下载、模板导入与验证
venues/                期刊清单
integrations/           第三方组件固定版本与许可记录
projects/               本地研究项目（原始数据和大输出被忽略）
```
