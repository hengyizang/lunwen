# GitHub Actions CI

`.github/workflows/validate.yml` 分成确定性检查与真实外部验收两层。

## 每次 push 和 pull request

`deterministic` job 在 Python 3.10、3.12、3.13 上分别执行：

```bash
python -m pip install ".[figures,reader]" "reportlab>=4,<5"
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
python scripts/validate_repo.py
git diff --check
```

`.[figures,reader]` 是项目已经声明的绘图与文档读取依赖，覆盖 Matplotlib、NumPy、pandas、PDF/DOCX/PPTX 路径；ReportLab 只用于测试中生成真实 PDF 固件。CI 不再依赖 runner 恰好预装这些包。
矩阵覆盖项目声明的最低 Python 3.10，以及当前主要运行版本。单个 job 最长
15 分钟；同一分支有新提交时，旧运行会取消。

独立的 `windows-script-syntax` job 在 `windows-latest` 上用 PowerShell AST 解析 `scripts/install-d-drive.ps1`，但不会在 GitHub runner 上修改磁盘、安装 WSL 或迁移 Docker。

## 每周及手动触发

`schedule` 和 `workflow_dispatch` 额外启动两个 job。维护者也可在一次 push 的
提交信息中加入 `[live-acceptance]`，让该次提交同时运行它们：

- `live-literature`：真实调用全部无凭据接口、已配置凭据的接口及 OpenCitations，上传原始响应、
  规范化结果和验收报告；DBLP 使用官方 SPARQL endpoint，避免把网页端的
  JavaScript 反机器人挑战当成 API；arXiv 使用官方 `id_list` 单记录端点验证
  API 连通性，避免把宽泛检索的公共出口限流误判为适配器故障；
- `container-isolation`：在 GitHub Linux runner 上用 digest 固定镜像实际验证
  无网络、只读根目录和受限 tmpfs。

手动触发时可勾选 `install_ai4science`。`adapter-packages` 会真实安装项目声明的 PaperQA2、ToolUniverse 与 ref-verify 固定版本，核对入口和包身份，再运行适配器契约测试；它不执行付费 PaperQA 问答，也不伪造用户语料。

外部服务限流或停机将使 live job 明确失败，但不会让普通 PR 的确定性回归结果
失真。两个 live job 的证据保留 14 天。

`[live-acceptance]` 只用于有意进行的验收提交，不应加入每次日常提交，以免
反复消耗第三方接口配额和 runner 时间。

Semantic Scholar 和 OpenCitations 都可匿名调用，但共享 runner IP 容易触发限流。
为提高定时验收的稳定性，可分别添加仓库 Actions secrets
`SEMANTIC_SCHOLAR_API_KEY` 和 `OPENCITATIONS_ACCESS_TOKEN`。它们只作为请求头传给
官方 API，不写入 URL、日志、收据或 artifact。GitHub Actions 未配置 Semantic
Scholar key 时会在报告中明确记录该提供商为 `skipped_providers`，其余无凭据核心
来源仍须全部真实通过；一旦配置 key，Semantic Scholar 自动加入严格验收。WSL2
底层命令默认仍是全源严格模式，除非操作者显式传入
`--allow-missing-semantic-scholar-key`。

GitHub runner 的容器 job 证明 Linux/Docker 路径；它不能冒充 WSL2。Windows
本机的 WSL2 验收必须按 [`LIVE-ACCEPTANCE.md`](LIVE-ACCEPTANCE.md) 执行，报告
中的 `environment.is_wsl2` 必须为 `true`。
