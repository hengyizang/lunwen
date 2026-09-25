# GitHub Actions CI

`.github/workflows/validate.yml` 分成确定性检查与真实外部验收两层。

## 每次 push 和 pull request

`deterministic` job 在 Python 3.10、3.12、3.13 上分别执行：

```bash
python -m pip install ".[figures]"
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
python scripts/validate_repo.py
git diff --check
```

`.[figures]` 是项目已经声明的可选依赖组，包含科研绘图测试实际使用的
Matplotlib、NumPy 和 pandas。CI 不再依赖 runner 恰好预装这些包。
矩阵覆盖项目声明的最低 Python 3.10，以及当前主要运行版本。单个 job 最长
15 分钟；同一分支有新提交时，旧运行会取消。

## 每周及手动触发

`schedule` 和 `workflow_dispatch` 额外启动两个 job。维护者也可在一次 push 的
提交信息中加入 `[live-acceptance]`，让该次提交同时运行它们：

- `live-literature`：真实调用全部公开文献接口及 OpenCitations，上传原始响应、
  规范化结果和验收报告；
- `container-isolation`：在 GitHub Linux runner 上用 digest 固定镜像实际验证
  无网络、只读根目录和受限 tmpfs。

外部服务限流或停机将使 live job 明确失败，但不会让普通 PR 的确定性回归结果
失真。两个 live job 的证据保留 14 天。

`[live-acceptance]` 只用于有意进行的验收提交，不应加入每次日常提交，以免
反复消耗第三方接口配额和 runner 时间。

GitHub runner 的容器 job 证明 Linux/Docker 路径；它不能冒充 WSL2。Windows
本机的 WSL2 验收必须按 [`LIVE-ACCEPTANCE.md`](LIVE-ACCEPTANCE.md) 执行，报告
中的 `environment.is_wsl2` 必须为 `true`。
