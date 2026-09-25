# 把 WSL2、Docker 与项目放在 D 盘

目标是让发行版虚拟磁盘、WSL 交换文件和 Docker 镜像数据都不占用 C 盘，同时
保持 Linux 工具链的性能和权限语义。以下命令在 Windows PowerShell 中运行；
Linux 命令只在 WSL2 Ubuntu 中运行。

## 新安装：直接指定 D 盘

先创建目录，再安装到指定位置：

```powershell
wsl --update
New-Item -ItemType Directory -Force D:\WSL\Ubuntu
wsl --install -d Ubuntu --location D:\WSL\Ubuntu
```

`--location` 是 WSL 的正式安装位置参数。若本机的 `wsl --help` 尚未显示它，先
更新 WSL；不要继续一个无法确认目标位置的安装。

在 `%UserProfile%\.wslconfig` 中把 WSL2 交换文件也放到 D 盘，并为以后新安装
的发行版指定默认根目录：

```ini
[wsl2]
swap=4GB
swapFile=D:\\WSL\\swap.vhdx

[general]
distributionInstallPath=D:\\WSL
```

保存后执行：

```powershell
wsl --shutdown
```

`distributionInstallPath` 影响之后安装的发行版，不会自动搬迁已经存在的发行版。

## 已有发行版：先导出，再导入 D 盘

这是保守迁移方式；在新实例验证成功前保留旧实例：

```powershell
wsl --shutdown
New-Item -ItemType Directory -Force D:\WSL\backup
wsl --export Ubuntu D:\WSL\backup\ubuntu.tar
wsl --import Ubuntu-D D:\WSL\Ubuntu-D D:\WSL\backup\ubuntu.tar --version 2
wsl -d Ubuntu-D
```

进入 `Ubuntu-D` 后检查用户文件、Git、Python 和网络。只有确认新实例完整、备份
可读且默认用户设置正确后，才考虑自行注销旧实例。注销会删除旧实例，本文不将
它放入自动步骤。

## Docker Desktop 数据

Docker Desktop 默认可能把虚拟磁盘留在 C 盘。在 Docker Desktop 打开
**Settings → Resources → Advanced → Disk image location**，选择例如
`D:\DockerData`，等待迁移完成，再运行：

```powershell
wsl --shutdown
```

重新启动 Docker Desktop，在 WSL2 中验证 `docker info`。不要手工移动 Docker
正在使用的 VHDX。

## 仓库与项目数据

即使发行版物理上位于 D 盘，仓库仍应放在发行版自己的 Linux 文件系统：

```bash
mkdir -p ~/code
cd ~/code
git clone https://github.com/hengyizang/lunwen.git
cd lunwen
bash scripts/bootstrap-wsl.sh --with-ai4science --with-figures
```

`~/code/lunwen` 此时已经实际占用 D 盘发行版虚拟磁盘。不要为了“放到 D 盘”改成
`/mnt/d/lunwen`；Windows 挂载目录通常在大量小文件、权限和文件监控方面更差。
大体积、只读的人工导入数据可以先放在 `D:\Research`，再通过 `/mnt/d/Research`
显式导入到项目受控目录。

完成后按 [`LIVE-ACCEPTANCE.md`](LIVE-ACCEPTANCE.md) 执行真实环境验收。

官方参考：

- [Microsoft：安装 WSL](https://learn.microsoft.com/windows/wsl/install)
- [Microsoft：WSL 高级设置](https://learn.microsoft.com/windows/wsl/wsl-config)
- [Docker Desktop：WSL 2 backend](https://docs.docker.com/desktop/features/wsl/)
