# WSL2、公开文献 API 与 Docker 真实验收

本页定义 v2.1 的可重复真实验收。验收脚本不会把网络可达性、模型回答或
数据库返回结果当成科学结论；它只证明接口和隔离执行路径在指定环境中确实
运行，并保存原始响应、哈希和失败原因。

## 1. WSL2 前置条件

在 Windows 11 的 WSL2 Ubuntu 中把仓库放在 Linux 文件系统（例如
`~/code/lunwen`），启用 Docker Desktop 的 WSL integration，并确认：

```bash
uname -r
docker version
```

`uname -r` 必须包含 `microsoft-standard-WSL2` 或 `WSL2`。只安装 Docker CLI、
但 daemon 不可访问，不算通过。

若 Windows C 盘空间紧张，先按 [`WSL2-D-DRIVE.md`](WSL2-D-DRIVE.md) 把新发行版、
交换文件和 Docker 数据放到 D 盘；仓库仍应克隆到该发行版内部的 `~/code`，而
不是 `/mnt/c` 或 `/mnt/d`。

安装可选 AI4Science 运行时：

```bash
bash scripts/bootstrap-wsl.sh --with-ai4science
```

该选项在仓库 `.venv` 中安装锁定的 `paper-qa==2026.08.12` 与
`tooluniverse==1.5.1`。PaperQA2 要求 Python 3.11+。

## 2. 一次完成 WSL2 真实验收

推荐的一键命令会依次验证 WSL2、锁定包版本、API 配置和 Docker daemon，然后
真实运行公开文献接口、隔离容器、PaperQA2、ToolUniverse，并校验收据：

```bash
bash scripts/run-wsl-acceptance.sh \
  --project my-phd \
  --corpus literature/papers \
  --tool-request evidence/requests/uniprot-p12345.json \
  --actor 'Hengyi Zang'
```

PaperQA2 可能触发一次真实的计费模型调用；脚本会在调用前明确提示。必须由研究者
提供有权使用的本地语料和一个经过检查的 ToolUniverse 请求。任一环节失败都会
以非零状态退出，不会把部分通过写成“完整通过”。

只验收公开文献接口与容器时，可直接运行底层命令：

```bash
mkdir -p artifacts/acceptance
.venv/bin/python scripts/live_acceptance.py wsl \
  --output artifacts/acceptance/wsl2.json
```

该命令实际调用 OpenAlex、Crossref、Semantic Scholar、arXiv、Europe PMC、
DBLP、HAL 和 OpenCitations，每个检索接口至少规范化一条记录；随后实际启动
Docker/Podman 容器，验证：

- 镜像由完整 SHA-256 digest 固定；
- 容器无网络；
- 根文件系统只读；
- 仅 `/tmp` 的受限 tmpfs 可写；
- capabilities 被移除，`no-new-privileges` 已启用。

默认 amd64 镜像是：

```text
python:3.10.21-slim-bookworm@sha256:54b4fc9408ea4f5d1b1b9c63c7ef1968d46d3b927e00df8ab1f09364593f979f
```

ARM64 主机必须用 Docker Hub 对应平台的完整 manifest digest，通过 `--image`
显式替换；禁止改成浮动 tag。

状态语义：`passed` 表示所有真实调用通过；`failed` 表示调用已经发生但响应、
解析或隔离探针失败；`blocked` 表示不是 WSL2、容器引擎缺失或镜像没有 digest。
脚本分别返回 0、1、2。报告及原始响应位于 `artifacts/acceptance/`，不提交 Git。
公开接口只对明确的 429/5xx 临时错误进行有限重试。Semantic Scholar 可选读取
`SEMANTIC_SCHOLAR_API_KEY`，OpenCitations 可选读取
`OPENCITATIONS_ACCESS_TOKEN`；请求头中的值从不进入收据。

若只排查单一层，可以分别运行：

```bash
python3 scripts/live_acceptance.py literature \
  --output artifacts/acceptance/literature.json
python3 scripts/live_acceptance.py container --require-wsl2 \
  --output artifacts/acceptance/container.json
```

验收检索不等于 G1 文献筛选。它生成的 `search-log.jsonl` 故意保持“待具名人工
筛选”，不能直接用于关闭科研质量闸门。

## 3. PaperQA2 实际执行适配器

把研究者有权使用的本地论文放入项目内目录，然后运行：

```bash
.venv/bin/python scripts/ai4science_evidence.py paperqa \
  --project my-phd \
  --corpus literature/papers \
  --settings fast \
  --question 'Which evidence contradicts the proposed mechanism?' \
  --actor 'Hengyi Zang' \
  --purpose 'Contradiction scan over the human-owned corpus.'
```

适配器用 argv 直接启动官方 `pqa -s fast ask ...`，不经过 shell。`PQA_HOME`、
HOME 和缓存被限制在项目 `.cache/ai4science/`；语料目录执行前后逐文件复核
SHA-256。OpenAI、Anthropic 等 key 只从允许的环境变量传入，收据只记录变量
名，不记录值。

## 4. ToolUniverse 实际执行适配器

先创建一个项目内 JSON 请求，且只包含官方 dictionary API 的 `name` 和
`arguments`：

```json
{
  "name": "UniProt_get_entry_by_accession",
  "arguments": {"accession": "P12345"}
}
```

然后运行：

```bash
.venv/bin/python scripts/ai4science_evidence.py tooluniverse \
  --project my-phd \
  --request evidence/requests/uniprot-p12345.json \
  --actor 'Hengyi Zang' \
  --purpose 'Retrieve an advisory public database record.'
```

窄化 worker 只加载请求中的一个工具，并调用官方
`ToolUniverse.run({"name": ..., "arguments": ...})`。请求文件、结果、stdout、
stderr、包版本、退出码、超时和输入完整性全部写入
`evidence/ai4science-ledger.jsonl`。失败和超时同样保留，但没有可用 `output`。

最后检查全部收据：

```bash
.venv/bin/python scripts/ai4science_evidence.py validate --project my-phd
```

两类结果始终是 `advisory_only: true` 且
`human_verification_required: true`；任何引用和科学主张仍须回到原始来源人工核验。
