# Codex Cloud 环境

这个入口为 Codex Cloud 准备仓库开发、文献读取、绘图、统计和文档导出依赖。
Codex Cloud 负责代码工作；项目既有 GitHub Actions 继续负责受控科研运行、状态
恢复和实验。安装依赖不会启动研究，也不会授予实验执行权限。

## 保存并发布环境

在 Codex 的 **Settings → Codex Cloud → Environments** 中编辑 `lunwen` 环境，
仓库选择 `hengyizang/lunwen`，分支选择 `main`。推荐 Ubuntu/Debian Linux 和
Python 3.12；核心安装支持 Python 3.10 及以上。不使用只适合本机 D 盘的
`bootstrap-d-drive.sh`，也不在云端创建 Windows 路径。

在 **Install script** 中填写：

```bash
bash scripts/bootstrap-codex-cloud.sh
```

在 **Start skill** 中保存这些启动说明：

```text
Work from the checked-out hengyizang/lunwen repository root. Before running Python
commands in each new shell, source .runtime/codex-cloud-env.sh. Follow AGENTS.md
and the current research workflow. Use Python from .venv. If the environment
file is missing, run bash scripts/bootstrap-codex-cloud.sh and inspect its result.
Use the existing GitHub Actions controls for scientific execution; do not set
DR_OS_CLOUD_EXECUTOR or GITHUB_ACTIONS to bypass runner checks. Never start a paid
model call, research cycle or experiment merely to test environment startup.
```

让环境准备过程完成，检查报告，保存后选择 **Publish**；编辑已有环境时选择
**Republish**。发布后，新建一个使用 `lunwen` 的云端任务进行验收。已有任务保留
自己的状态，不能用它证明新发布的环境已生效。

2026-11-06 的账号查询发现已有名为 `lunwen` 的可运行环境；名称相同的其他配置
版本未必可运行。本地仓库中的安装脚本不等于账号中的环境已经更新、发布或验收，
只有实际保存、发布和新任务检查才确定生效。

## 默认安装内容

脚本从自身位置定位仓库，不依赖 `/workspace` 下的特定文件夹名。Python 虚拟
环境位于 `.venv`，缓存、临时文件和启动文件位于 `.runtime`，均已排除在 Git 外。
启动文件只保存路径和非敏感设置，不复制凭据。

默认安装项目声明的 `reader`、`figures`、`research-quality`、`writing-tools`、
`reference-tools` 依赖，以及用于 PDF 固件、图像、YAML、可视化和 schema 检查的
ReportLab、Pillow、PyYAML、seaborn、jsonschema。系统工具包括 Poppler、英文及
简体中文 OCR、Pandoc、TeX Live/latexmk、LibreOffice Writer/Impress 和常用字体。
首次准备完整导出工具需要较多下载和磁盘空间；以后复用已发布环境的准备状态。
脚本只安装缺少的系统包，不升级整个系统，不安装或启动 Docker。

安装结束核对实际模块导入、系统命令、Python 编译和仓库结构。检查不会发起模型
生成、付费问答、课题推进或科研实验，不下载模型权重。

按实际任务安装较重的可选依赖：

```bash
# PaperQA2、ToolUniverse 的固定版本 SDK；需要 Python 3.11+
bash scripts/bootstrap-codex-cloud.sh --with-ai4science

# 声明的 ONNX/tokenizers 语义检索运行时
bash scripts/bootstrap-codex-cloud.sh --with-semantic-retrieval
```

两个选项可以组合使用。安装 SDK 或运行时不代表检索模型、索引、来源权利、独立
审查或计费接入已验证，也不启用上游自治 agent。

## 网络和凭据

在环境中允许访问依赖软件源、GitHub 和当前任务需要的官方文献/API 服务。准备
阶段实际测试这些访问。若采用受限网络，先允许包管理器，再补充实际需要的域名；
允许域名不会提供该服务的凭据。不要通过关闭来源和模型身份检查处理网络错误。

GitHub Actions Secrets 不会自动成为 Codex Cloud 环境变量。继续通过既有 Actions
入口执行科研时，让凭据留在原来的服务中；如果确有直接调用需要，在 Codex 环境
配置中添加对应变量或限定 HTTPS 目的域名的网络密钥，不把值放入安装脚本、启动
说明、仓库或聊天记录。费用继续按 [总额度政策](TOTAL-COST-POLICY.md) 计算并受
既有项目累计额度约束，不能因换环境清零。

此前 CheapAI 通道的 HTTP 401 是该服务凭据问题，安装 Python 依赖不会修复它。
需要在实际调用服务的凭据设置中更新相应密钥，再进行不生成模型内容的就绪检查。

## 新任务验收

在新建的 `lunwen` 云端任务中运行：

```bash
source .runtime/codex-cloud-env.sh
python scripts/check_env.py --mode api
python -m compileall -q scripts
python scripts/validate_repo.py
python -m unittest discover -s tests -v
```

报告应区分通过、失败和环境条件跳过。`check_env.py` 的 API 变量配置提示不代表
真实调用已成功；结构检查和测试也不证明论文的科学有效性。实际数据权利、创新性
硬门槛、G1/G2 人工选题、模型家族分离、预算和 G3 执行封存仍按原流程执行。

官方配置、发布及环境状态说明：
[OpenAI：Cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environments)
（访问日期：2026-11-06）。
