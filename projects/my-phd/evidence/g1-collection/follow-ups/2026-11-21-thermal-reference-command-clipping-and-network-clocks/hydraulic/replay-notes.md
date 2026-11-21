# 液压与气动试验的复核记录

2026-11-21 UTC，用 Python 3.12.14、NumPy 2.3.5 和 SciPy 1.17.0，从四个公开数据记录重新生成 5 张 CSV，与本目录中的文件逐字节一致。以下数量分别以文件、工况、采样行及通道为单位，三轴和重复运行分别列出。

## Dresden 三轴伺服液压试验台

OPARA 的完整 ZIP 条目大小为 554,952,233 字节，提供者记录的完整文件 MD5 为 `aa502a9116b2bfe2cf555d8f01b9d015`。本次以 HTTP Range 获取偏移 554,379,274 至 554,952,232（含首尾）的中央目录和 ZIP 结束记录。572,959 字节的 SHA-256 为 `6b0a20001ddb9596460e35cc9c87fbae13158d79969f47bbf095bf6cea0fedf5`。更新后的下载脚本在写入前检查此摘要，并验证每个 Range 的首尾和长度。随后以 21 个区间读取了 120,099,246 字节。测试数据和说明共 558 个非目录成员，逐成员解压读取并通过 ZIP CRC32，合计未压缩 375,073,096 字节。未获取的训练或验证数据保留为空洞，完整 ZIP 的 MD5 仅转录自仓储。[仓储条目](https://opara.zih.tu-dresden.de/handle/123456789/2557) · [位流元数据](https://opara.zih.tu-dresden.de/server/api/core/bitstreams/2ce1e46d-3017-4426-9487-f775c15b2e54)

中央目录共 2,888 个成员，其中 2,854 个是文件。已核验的 558 个文件包括 456 个小端 float32 通道、98 个 JSON 通道说明、1 个读取脚本、2 个 FRF 说明及 1 个总说明。98 个 JSON 对应 36 组实测输出、8 组已提供的驱动信号、36 组由位移预测力的结果和 18 组由驱动预测传感器的结果。每个通道的名义采样间隔为 1 ms。作者说明实测信号经过 80 Hz 低通处理，三个力通道已经作惯性补偿。

力与位移的实测输出均有两次独立采集。18 个工况各自对应三轴，产生 54 个比较行。按每个工况每次重复只计一次时间序列，合计 3,771,530 个时间点，两次共 7,543,060 个时间点。按下表先判断相应数组长度能否匹配；未对齐的项目在 CSV 中留空。两个长度相同的数组依同文件名、同轴和同采样序号配对，未另行估计延时。

| 工况 | 数量 | 每次实测样本数 | 驱动样本数 | 正向 FRF 样本数 | 长度匹配结果 |
|---|---:|---:|---:|---:|---|
| Noise | 2 | 180,000 | 179,999 | 179,999 | 驱动及正向预测均少 1 |
| Noise | 2 | 120,000 | 119,999 | 119,999 | 驱动及正向预测均少 1 |
| Sinus、Sweep | 各 2 | 120,000 | 120,000 | 120,000 | 三者相等 |
| Serviceload | 5 | 268,351 | 未收录 | 268,351 | 正向预测相等 |
| Serviceload | 3 | 268,351 | 未收录 | 268,288 | 正向预测少 63 |
| Serviceload | 2 | 272,361 | 未收录 | 272,348 | 正向预测少 13 |

总说明指出服务载荷驱动由 CARLOS 标准载荷经变换得到，作者省略了这些驱动文件。CSV 中 `drive_rows=0` 表示没有相应文件。每个工况两次实测的同轴力及位移长度均一致，36 组由位移预测力的结果也均与相应实测系列等长。独立按通道名解码原始 float32，用平方和除以长度后开方，核对所有已填 RMSE 的九位小数及所有应留空的单元格。具体比较数为：

- 两次实测之间有 54 项力和 54 项位移差值 RMS，范围分别为 0.003917355–0.036493556 kN 和 0.014090891–0.080056721 mm。
- 位移推算力的 FRF 预测对实测力共有 54 个工况轴 × 2 次重复，即 108 项，RMSE 为 0.015180322–1.041122365 kN。
- 驱动推算传感器的正向 FRF 有 27 个等长工况轴。两次重复共 54 项力比较和 54 项位移比较，RMSE 分别为 0.050235794–0.695666269 kN 和 0.118298519–1.403780195 mm。
- 已发布驱动力与实测力等长的有 12 个工况轴。两次重复共 24 项，差值 RMS 为 0.448363346–2.987009146 kN。驱动信号与实测力之间的差值尚不能定位阀门或执行器限幅。

## 三份 Zenodo 记录

下载文件按“记录 ID-原文件名”存放。复核时对 13 + 3 + 2 共 18 个原始文件逐个计算 MD5，全部匹配 Zenodo 文件清单。两份同名的 `Table_1.pdf` 属于不同记录。包含数据的四个 ZIP 还逐成员解压通过 CRC 检查。

| 记录 | 实读文件与计数 | 使用边界 |
|---|---|---|
| [Belgrade 集中控制](https://doi.org/10.5281/zenodo.4556924) | 12 个电压文本及 1 份 PDF。7 套轨迹、4 种采样率，共 3,878,500 个样本。低于 0 V 的有 170 个，等于 0 V 的有 0 个，超过 10 V 的有 242,080 个，恰好 10 V 的有 9,317 个；实测范围 −3.5419 至 10.214 V。 | 阈值按文件中记录的调压器电信号计算。12 个文件均出现大于 10 V 的值，最长连续 18 个样本。5 个文件出现低于 0 V 的值，最长连续 1 个样本。超出标称范围不能单独证明压力或机械力受到削顶。 |
| [软执行器负载测量](https://doi.org/10.5281/zenodo.3627901) | 3 个 ZIP，共 102 个成员，含 93 个试验 CSV、3 个轨迹 CSV、3 个 MAT、3 个 MATLAB 脚本。末端力 36、三点弯曲 27、拉力 30 个试验。574,561 个原始行中有 63 个初始异常行，筛后保留 574,498 行；90 个 CSV 与同档 MAT 中一个完整矩阵精确匹配。 | 筛除标准是首列等于 0 且六个负载通道的最大绝对值超过 1,000,000，所有命中均为各文件首行。三份未匹配文件为 P0_1、P0_2、P0_3。P200_2 保留一个时间倒退（原值由 7,993 变为 64），无需按时间差计算的峰值可以复核。输出对每对负载通道取向量范数并乘以 9.81/1000。 |
| [平面定位与分布控制](https://doi.org/10.5281/zenodo.6399688) | 1 个 ZIP 及 1 份 PDF。ZIP 含 60 个双轴试验文本（30 次运行，每次两轴）和 2 个公共参考轴文本，总共 3,790,047 个数值。各实际轴有 61,000 行。x/y 参考轴分别有 64,759/65,288 行。 | 60 项同序号前缀比较共 3,660,000 个轴样本。每个比较均省去参考末尾的 3,759 或 4,288 行。前缀 RMSE 为 3.730822–5.260493，保留原生计数单位；这个对照并未独立测定端到端通信延迟。 |

## 复现

在本目录运行以下命令。约 121 MB 的 Dresden 网络传输可生成逻辑大小约 555 MB 的稀疏 ZIP。也可向 `derive_dresden.py` 传入仓储提供的完整 ZIP。Zenodo 下载示例用仓储给出的文件摘要逐项验证。

```sh
mkdir -p replay/input replay/output
python fetch_dresden.py replay/input/Heindel-test.zip
python derive_dresden.py replay/input/Heindel-test.zip replay/output
python - <<'PY'
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

target = Path("replay/input")
for record in ("4556924", "3627901", "6399688"):
    with urlopen(f"https://zenodo.org/api/records/{record}") as response:
        files = json.load(response)["files"]
    for item in files:
        with urlopen(item["links"]["self"]) as response:
            content = response.read()
        if "md5:" + hashlib.md5(content).hexdigest() != item["checksum"]:
            raise ValueError(item["key"])
        (target / (record + "-" + item["key"])).write_bytes(content)
PY
python derive_pneumatic.py replay/input replay/output
sha256sum replay/output/*.csv
```

| 派生文件 | 独立重跑的 SHA-256 |
|---|---|
| belgrade-regulator-voltage.csv | `5b8ab6706449faa4a3500968bd089de7657a14e98a7243cc715644fcda101db0` |
| dresden-force-repeats.csv | `de4077348f895e40742bba4f149d559d8927ccad7744e5160218679a7534fd1e` |
| planar-file-inventory.csv | `43e1b151e0e6f57bd4092b92760b2de9a9d71b1d42d22993e602bbd7c06c98e9` |
| planar-reference-overlap.csv | `c3a13bbfb811ac536872febf4c8fa7f7a73a792b718b4a92a6a27e24ba0d4fdc` |
| soft-loadcell-files.csv | `725a1c367a90855321a181650b67d4681bcea80a5864ee2cc7d4accbd21b4972` |

