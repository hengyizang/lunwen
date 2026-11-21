# 机器人实测数据的派生表

这些文件记录本次实际读取和校验的数据。表中的时间点、事件、飞行、链路位置和实验配置各有自己的计数单位。

| 派生表 | 观察单位与来源 | 如何使用 |
|---|---|---|
| [腕部工况与通道](wrist-conditions-channels.csv) | Aleksander Skrede 的 KUKA、ATI 腕部六轴传感器与 IMU。固定版本 12 个 CSV，包含 24 个校准姿态，以及基线、振动、振动加人工接触三条测试轨迹。[Zenodo](https://zenodo.org/records/11096791) | 按文件及通道给出样点数、范围、中位数和时间戳异常。发布说明同时使用了 biased 和 unbiased 两种说法。逐时真实外力和偏置补偿状态需要额外证据。 |
| [轻重载与不同速度](r1-offset-sample.csv) | KU Leuven 四个文件，76,519 行；轻载、重载为人工示教，常速、慢速为机器人执行。记录传感通道、六维测量有效性及力和力矩的模长统计。[原数据](https://zenodo.org/records/17376427) · [许可及算法](r1-offset-provenance.json) | 比较前需核对工况、采样周期和传感器类型；模长同时包含负载等影响。 |
| [操作事件](uci-failure-episodes.csv) | Luis Lopes 与 Luis Camarinha-Matos 的 UCI 数据。五项任务合计 463 个事件，每个事件 15 个六轴样点，保留 normal、ok 和各类失败标签。[原数据](https://doi.org/10.24432/C5M89N) | 每轴给出事件内中位数和峰峰值，字段保留原单位。按任务及其标签解释。原始窗口始于检测时刻，不能从中恢复故障前因果序列。 |
| [IDSIA 实飞记录](nano-drone-runs.csv) | 固定版 v1.0 的 15 段飞行、75,096 个时间点。4 路电机转速、13 个状态输出。[发布版](https://github.com/idsia-robotics/nanodrone-sysid-benchmark/releases/tag/v1.0) | 表中保留官方训练／测试划分、时间跨度及采样间隔；电机转速本身无法给出饱和指令或逐桨推力真值。 |
| [NanoBench 实飞记录](nanobench-runs.csv) | 抽查 4 个完整实机 CSV、17,118 行，包含两份多正弦激励记录。锁定版本主目录可逐文件列出 107 个 CSV，项目 README 报告 172 次飞行。[文件清单与哈希](nanobench-provenance.json) | 一段椭圆轨迹配置 30 秒，实际文件仅覆盖约 2.10 秒，211 行的四路 PWM 指令均为零。两个多正弦文件的元数据都标为 repetition 1 且来自同一架飞行器。 |
| [CooperScene 通信覆盖](r5-cooperscene-link-coverage.csv) | 14 个真实场景、56 份节点元数据，三车和一路侧节点。119,688 个有向链路与帧的组合中，118,524 个有吞吐观测，33,359 个为零，1,164 个缺失。[作者、许可与计算方法](r5-cooperscene-provenance.json) | 按方向与帧比较缺失和零值。已核文件缺少逐包丢包率、时延与抖动字段；由零吞吐推算这些量会引入错误。派生表遵循来源说明的 CC BY-NC-SA 4.0。 |
| [MILUV 实验配置](r5-miluv-experiment-groups.csv) | 按官方配置登记的 36 次实验，其中 16 次三机、20 次单机。表内有固定版本及哈希。 | 可筛选多机、有障碍、启用信道脉冲响应的实验组合。配置计数不提供每包时钟误差或收发时延。 |
| [RoboLoc-G 测距时戳](r5-ftm-coverage.csv) | 8 段轨迹、15,152 帧，单台龙门机器人与固定锚点。15,150 帧的 RTT 原值精确等于四时间戳算出的皮秒差，另两帧原值为零且差值为负。[原数据](https://doi.org/10.5281/zenodo.15989282) · [文件指纹与单位核对](r5-ftm-provenance.json) | 数据卡与设备文档对单帧 RTT 的单位有冲突，表内保留两种口径。这是测距握手，不可直接当作多机器人应用消息的年龄。 |

[derive.py](derive.py) 可重算腕部工况与通道、UCI 操作事件及 IDSIA 实飞记录三张表。[sources.json](sources.json) 列出发布者、取得地址和 SHA-256。将两个 ZIP 按 local_name 保存，Zenodo 的 12 个 CSV 放入同一输入目录下的 zenodo/，执行 `python derive.py 输入目录 输出目录`。脚本校验来源、行列和时间顺序。KU Leuven、CooperScene 及 RoboLoc-G 的文件级处理记录见各表同行的来源说明。

## 可直接分析的逐测点表

- [R1 力和力矩模长时间序列](r1-offset-timeseries.csv.gz) 包含四段记录的 76,519 个测点。每个测点有试次内序号、相对秒、采样间隔以及两个向量的模长；两种采集装置分列。归档文件与四条汇总记录交叉核对通过。[字段、来源与许可](r1-offset-timeseries.json) · [重算脚本](r1-offset-derive.py)
- [R5 测距帧时差](r5-ftm-frame-derived.csv.gz) 包含八段轨迹的 15,152 个帧记录，组内保留设备各自的时钟差及双差。15,150 个发布 RTT 原值在数字上等于皮秒双差，另两个 RTT 原值为零，对应 −7,812 和 −9,374 皮秒的双差。两份原始文档对帧 RTT 的单位有分歧，数据表保留原值和核对状态。[字段、来源与许可](r5-ftm-frame-derived.json) · [重算脚本](r5-ftm-frame-derive.py)

NanoBench 的[逐测点派生表](r2-nanobench-derived.csv.gz)保留 17,118 行相对时间、电机指令均值与极差、Vicon 与机载 EKF 的位置差和质量标记。机载 EKF 融合 Vicon 观测，位置差衡量两者一致性。[重算脚本](r2-nanobench-derive.py) · [来源、许可与字段定义](r2-nanobench-derived.json)
