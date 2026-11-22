# 检索与筛选记录

2026-11-22 UTC 检索。主题为机器人、触觉外围设备及自主感知中可观察的物理输出时延。检索从工况与信号定义入手，优先选择不同于已有车体霍尔/陀螺仪、手部 IMU 及 UR5e 网络日志的实物证据。检索系统使用英文原词。链接均为公开、无需账号的页面或文件。

| 查询或检索操作（同义长查询保留下列主要检索串） | 实际筛选与追踪 |
| --- | --- |
| `robot actuator latency measurement physical motion end-to-end real robot control latency high-speed camera`；`robot teleoperation command to motion latency measurement open source real robot` | 对命中 UR3 以题名回查 Crossref、arXiv，合并书章和预印本，下载 v1，核查图 4、表 1。历史 IMU 手、Vargas 和高车体时延条目排除。[arXiv](https://arxiv.org/abs/2407.11560v1) |
| `Measuring and Modelling Delays in Robot Manipulators for Temporally Precise Control`；`UR10 Performance Analysis`；`New method to measure end-to-end delay of virtual reality` | 查两臂实验、设备、采样与引文 6、13；DTU 报告和作者方法全文可读。原文 ref. 1 的 http://aut.elektro.dtu.dk/staff/ttan/delay.html 在本次访问返回 HTTP 403，HTTPS 也未能取回，未据此声称 67,000 次试验原始文件可下载。[DTU](https://orbit.dtu.dk/en/publications/measuring-and-modelling-delays-in-robot-manipulators-for-temporal/) |
| `robot low latency event camera robotic goalie physical latency actuator measurement`；`Fast sensory motor control based on event-based hybrid`；`An embedded AER dynamic vision sensor for low-latency pole balancing` | 读 2013 论文和 2007 实验室 PDF，核对 GPIO、供电下降和到位的差别。2009 条目按 DOI 及 2013 原文引文入书目，旧 Wiki 直链没有传回有效 PDF。[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC3836084/) |
| `Development of a High-Speed, Low-Latency Telemanipulated Robot Hand System`；`Development of fast-response master-slave system Katsuki`；`Super-Low-Latency Telemanipulation Katsuki` | 读 2021 论文脚注、公式和图片出处，Crossref 核对两篇早期报告的 DOI、作者。2022 Yoshida/Yamakawa 后续在历史综表已有，未重复加入。[期刊](https://www.mdpi.com/2218-6581/10/1/41) |
| `Kroep haptic teleoperation latency measurement dataset`；`Breaking the Latency Barrier Kroep 5G`；`Kroep 5G bilateral teleoperation 4tu data` | 读 ICCPS 全文并提取图中 CDF。DataCite 搜 `Kroep teleoperation` 未给出原始时延数据，论文的 SURFdrive 公开目录列有一段 48,504,158 字节演示视频，不计为原始试次。[作者资料库](https://surfdrive.surf.nl/files/index.php/s/qrVIfA4SLLoFyIg) |
| `ExtremControl latency real world robot hand motion measured actuator motion`；`ExtremControl github optical flow latency estimator` | 按 arXiv 同号合并新旧题名，以 v4 的以太网 MoCap、VR 和公开光流演示为准。GitHub 树固定提交后，读取实际视频并校验 Git blob 和下载文件 SHA。其他系统只在对照图中出现，不将其估计值归为独立数据集。[项目](https://extremcontrol.github.io/) |
| `haptic interface latency physical output measurement motor vibration sensor real feedback`；`haptic device physical force feedback latency accelerometer dataset` | 追查 Estelle 等两篇全文的 Data Availability 和设计文件 URL。OSF Waterbutler 根目录列出 `Data Set Validation` 和 `Validation from Matlab`；逐档下载，检查 OSF 发布的 SHA-256 及日期、版本，并实际解析控制器 CSV/记录器标记。OSF node_license 字段均为空，目录只发派生数值。[PCD](https://osf.io/9ecxu/) · [Torch](https://osf.io/vrsya/) |

在本批次对 DOI、arXiv 号、同题名和项目代码比对已下载的 G1 历史总表、连续采集及分项证据。Enactive Torch 在 `continuous/literature-new-part-03.csv` 已有书目初筛，移至升级表。UMI 原论文、Warburton 的 VR 论文及既有带双 IMU 的手部示范均不计新增。未取得实际输出记录或评估终点以计算耗时为止的候选（如单独的数据集传感器刷新率）未作为本批机械动作实测。PCD 的 4 个 ZIP 与 Torch 的 5 份 .vmrk、4 份 MATLAB 文件均有匹配校验；只给出方法脚本的检查范围，不将算法文件计为试验次数。
