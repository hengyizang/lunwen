# CI 验证范围

CI 验证软件行为与可复现的工具执行。科学结论、原文阅读完成度和论文就绪状态要由实际研究证据判断，不能由绿色检查推出。

## 普通提交与 PR

`.github/workflows/validate.yml` 先在 Python 3.12 运行 `scripts/run_tests.py fast`，随后运行 Python 3.12 的 `slow` 分区，以及 Python 3.10、3.13 的 `compat` 分区。周度、手动或指定修复 ref 时，3.10/3.13 改跑 `all`。测试分区由 `scripts/run_tests.py` 管理。

确定性矩阵还执行：

```bash
python -m compileall -q scripts tests
python scripts/validate_repo.py
git diff --check
```

`validate_repo.py` 默认检查核心 JSON、可发现入口、技能指针一致性、实际源文件绑定和插件版本。它不把固定六阶段、固定来源数量、旧 CI 文案、安装全部可选工具当作正确性。需要核对已安装集成时，显式执行 `python scripts/validate_repo.py --integrations`。

`.github/actions/setup-runtime` 安装每个 job 的 `packages` 参数。只有 `ccfa: 'true'` 的 job 恢复并验证完整固定 CCFA 资源；其他 job 不为运行普通脚本拉取整套资源。当前 fast/slow/compat 回归仍使用完整资源，因为其中有相应集成测试。

Windows job 只用 PowerShell AST 解析安装器，不运行安装、不移动磁盘或 Docker 数据。CCFA 和文档打包专项 workflow 按相关路径变更触发；其余专项 workflow 以各自的触发条件为准。

## 周度与显式验收

以下较重的通用验收只在 `schedule` 或 `workflow_dispatch` 运行：Meta/形式理论路线、统计水印 CPU 固件、云端检查点生产与恢复、历史人工控制兼容、网关与费用恢复、故障注入。它们保留原产物和失败诊断。普通 PR 不重复运行这些场景。实验结果与容器复现还在 PR 改动执行器、实验、相关证据实现或测试时运行；`changes` job 比较 PR 的实际 base/head 路径，触发 `Experiment design and statistical evidence` 检查。

`live-literature` 和 `container-isolation` 仍支持周度、手动及有意标注 `[live-acceptance]` 的 main 提交，并遵循可复用 workflow 的 `offline_only`。文献验收每源请求量为 1；未配置的特定凭据按命令明确记录为跳过，配置后的服务按实际响应判断。容器验收检查真实 digest 固定镜像、无网络与只读根目录。Linux runner 成功不能冒充 Windows/WSL2 验收。

手动选择 `install_ai4science` 才安装 PaperQA2、ToolUniverse 与 ref-verify 并检查入口。版本按规范化版本比较，例如 `2026.08.12` 与 `2026.8.12` 等价。安装成功不表示已经进行付费问答，也不表示读过用户语料。

实时服务故障或限流只说明对应验收的当时状态。报告应保留真实请求、环境、输出及未测试范围，不把固件中的合成数据说成科学实验结果，不把 mock HTTP 说成真实付费模型调用。

## 本地开发

先运行受改动影响的测试与核心校验；接口、共享运行时或兼容行为变化后运行相应回归。没有相关改动时，无需反复运行已通过的全套或全部第三方测试。验收需要的外部环境、凭据和预算独立配置，编译与离线测试不会新增支出授权。
