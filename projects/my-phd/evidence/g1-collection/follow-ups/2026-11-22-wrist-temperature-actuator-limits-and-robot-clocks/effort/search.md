# R2 检索与版本核验

检索日期为 2026-11-22 UTC。检索以能区分参考、限幅后命令与独立物理反馈为优先，其次检查采样时钟、重复试验、文件实际内容和数据许可。全文引证和文件清单分别在 [书目](literature.csv) 和 [数据目录](sources.csv) 内，逐项关系见 [引文表](edges.csv)。

| 检索式或入口 | 跟踪与筛选 |
| --- | --- |
| `robot electric actuator closed loop actuator torque command reference measured torque load cell open dataset online current command saturation gearbox`；`motor torque controller anti windup experimental torque transducer dynamometer current voltage saturated torque data` | 得到腕部 Nussbaum 论文、发电机、电动汽车转台和开源 BLDC 测试台线索。早先已核验的 Lizarraga、PMSG 和 20035899 作为背景。本轮进入 Nussbaum 作者仓库逐个区分时序、搜索结果和代码占位文件。 |
| `servo actuator anti-windup experimental data saturation measured torque dataset`；`servo pneumatic hydraulic controller valve command pressure force sensor closed loop force tracking dataset` | 命中原始数据集 Delta 21233963、Belgrade 4556924 和液压缸安全约束 zg97984dmy。后两项已在前批采集；Delta 附件是特征表。源站预处理段落一处提到 “steam chamber”，同页其他描述和论文 3.1 节指向 Delta 伺服平台。保留此元数据不一致，不据此新增第二套设备。 |
| `direct current geared motor data voltage current speed PWM measured`；追查数据论文中 Data accessibility 与参考文献 1 | 论文指向 Mendeley 2rkpsss6fd 第 2 版的实验工作簿和另一个 Arduino 程序版本。Zenodo 5737539 中实际仅有一份程序压缩包，不计作另一数据源。Mendeley 的公开文件目录给出 SHA-256、下载文件 ID 和长度，加文件名参数的官方端点返回完整原始表。 |
| `data underlying the publication novel tribometer torque-mode traction tests braking torque speed traction force`；`A Novel Tribometer two roller torque control MDPI electromagnetic brake` | 从 University of Twente 出版物索引追至 4TU 版本 DOI。档案 119,605,044 字节，原发布处标示 MD5 3ef6ba6ac4df826ab876b66ad8009337。实验说明给出六列位置，自带处理脚本给出半径与制动符号。已读取全部 139 个测量文件，其他成员用于判断资料类型。 |
| `CREATOR induction machine measured drive cycle speed torque reference datasets`；原始论文引文 Heidarikani 2024 和 Dhakal 2024 | 区分同篇论文的感应与永磁两台实物。先前已保存版本 sns1d-77m43 为永磁电机。本轮的 kh3v7-dhn98 为感应电机，公开包内六组 × 四列数据文件均已核验；其他材料设计参数不计作新的试次。|
| `industrial motor torque reference measured torque shaft sensor command data controller limits`；`A Reference Value Calculation Scheme for Torque and Flux anti-windup` | 找到 NASA HyPER 实测报告和 J-STAGE 全文。HyPER 的外部扭矩仪以 50 微秒采样；论文图中为与 15 毫秒的逆变器遥测同步而每 300 点保留一点。报告与 2023 AIAA 版本属同一研究。不同限幅补偿文献中的实验与仿真图均按图号定位。 |
| `Nussbaum Function Based PID Approach for Tracking Control of Robot Manipulators`；跟踪 2026 作者参考文献 3、4、5、6、8 | 2024 年前驱的 ORBilu 作者 PDF 第 IV 节为两连杆仿真，另两篇 MDPI 原文明确在数值仿真环境中评价。1983 和 2020 条目标注为书目级。作者仓库轨迹采用固定提交，未从第三方复制程序或原始日志。|
| `open exoskeleton motor controllers torque sensor open loop regression recorded current`；`hybrid physics-informed data-driven torque estimation ultrasonic motors torque sensor` | 通过 PMC 核对踝部外骨骼采集与比较结果。超声电机论文只计书目和可见实验仪器描述，本轮没有认证可下载的测量档案。 |

对来源文件的读取分别核验了 Git blob ID、Zenodo MD5、Graz ZIP CRC、4TU 文件 SHA-256/MD5 或 Mendeley SHA-256；这些标识对应各自版本。论文 PDF 与 XML 的本轮输入哈希在 [核验回执](source-receipts.csv)。ORBilu 原始二进制在部分访问端返回 503，通过公开 PDF 阅读器核读作者版第 IV 节（全文共 341 行，数值模拟在第 237–246 行），无本地 PDF 哈希。采取了保守的归属口径，传感器实测电流、机械轴矩、对照系统中的负载设定值以及分类标签按实际通道分别记录。

与历史补充目录作过标识和题名初筛。CREATOR 论文、2002 和 2013 年的 IEEJ 补偿器已有既往证据。它们作为本轮文件或对照方法的锚点，不能另算三个新增研究。全项目归档和跨主题匹配由本批总索引给出。
