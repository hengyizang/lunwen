# 将整个运行环境固定到 `D:\ad\lunwen`

本项目的严格 D 盘策略是：仓库、Python 虚拟环境、pip/模型/工具缓存、WSL2 发行版、交换文件、Docker Desktop 磁盘和验收输出都必须位于 `D:\ad\lunwen` 下。安装脚本发现关键路径仍在 C 盘时会停止，不会悄悄继续。

## 仓库与最终安装命令

在管理员或普通 Windows PowerShell（按本机 WSL 安装权限）中运行：

```powershell
New-Item -ItemType Directory -Force D:\ad\lunwen
Set-Location D:\ad\lunwen
git clone https://github.com/hengyizang/lunwen.git .
```

完成下方 WSL2 与 Docker Desktop 设置后，再从该目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-d-drive.ps1
```

脚本只接受仓库根目录正好为 `D:\ad\lunwen`。它会创建 `.runtime`，检查 WSL 发行版注册位置和 Docker Desktop 磁盘位置，写入本机 Docker 位置收据，然后在 WSL 中调用 `scripts/bootstrap-d-drive.sh`。Python 环境和缓存位于仓库内，不写入 C 盘用户缓存。

## WSL2 位于 D 盘

新安装可用当前 WSL 的 `--location`：

```powershell
wsl --update
New-Item -ItemType Directory -Force D:\ad\lunwen\.runtime\wsl\Ubuntu
wsl --install -d Ubuntu --location D:\ad\lunwen\.runtime\wsl\Ubuntu
```

若 `wsl --help` 尚未显示 `--location`，先更新 WSL。已有发行版使用保守的导出/导入路径；验证新实例完整前不要注销旧实例：

```powershell
wsl --shutdown
New-Item -ItemType Directory -Force D:\ad\lunwen\.runtime\wsl\backup
wsl --export Ubuntu D:\ad\lunwen\.runtime\wsl\backup\ubuntu.tar
wsl --import Ubuntu-D D:\ad\lunwen\.runtime\wsl\Ubuntu-D D:\ad\lunwen\.runtime\wsl\backup\ubuntu.tar --version 2
wsl -d Ubuntu-D
```

将 `%UserProfile%\.wslconfig` 中的交换文件设置为：

```ini
[wsl2]
swap=4GB
swapFile=D:\\ad\\lunwen\\.runtime\\wsl\\swap.vhdx

[general]
distributionInstallPath=D:\\ad\\lunwen\\.runtime\\wsl
```

保存后运行 `wsl --shutdown`。此 Windows 配置文件本身很小且由 WSL 固定读取；大体积交换文件仍在 D 盘。

## Docker Desktop 位于 D 盘

在 Docker Desktop 的 **Settings → Resources → Advanced → Disk image location** 中选择：

```text
D:\ad\lunwen\.runtime\docker-desktop
```

等待 Docker Desktop 自己完成迁移，不要手工移动正在使用的 VHDX。重新启动后运行安装脚本；只有设置路径和磁盘文件都指向 D 盘，脚本才写入 `.runtime/docker-location.json`。之后 `run-wsl-acceptance.sh` 会复核该收据。

## WSL 内路径

从 WSL 进入 Windows 仓库：

```bash
cd /mnt/d/ad/lunwen
bash scripts/bootstrap-d-drive.sh
```

这是有意采用的严格物理位置策略。`/mnt/d` 对大量小文件可能慢于 ext4 VHDX，但能最直接保证仓库、环境和缓存都落在指定的 D 盘目录；若性能不足，可把整个 WSL 发行版 VHDX 仍放在 `D:\ad\lunwen\.runtime\wsl`，同时保持脚本要求的项目根目录不变。

安装完成后按 [`LIVE-ACCEPTANCE.md`](LIVE-ACCEPTANCE.md) 在真实 WSL2/Docker 环境验收。

官方参考：

- [Microsoft：安装 WSL](https://learn.microsoft.com/windows/wsl/install)
- [Microsoft：WSL 高级设置](https://learn.microsoft.com/windows/wsl/wsl-config)
- [Docker Desktop：WSL 2 backend](https://docs.docker.com/desktop/features/wsl/)
