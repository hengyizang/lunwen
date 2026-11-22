# R5 检索和筛选记录

检索日期为 2026-11-22 UTC。目标为验证一个通信事件在不同节点的观测、两端各自的本地时钟和独立测量运动的传感器。优先保留有原始字段、可区分试验层级并留有固定版本的材料。

| 入口 | 实际查询或查找位置 | 筛选 |
| --- | --- | --- |
| 网络检索与大学目录 | real world vehicle to vehicle wireless packet data trace both sender receiver timestamps measurement IEEE 802.11p VANET public dataset pcap；vehicle to vehicle communication dataset both TX RX packet data timestamp field DSRC | CooperScene、CICV5G、Bristol ITS-G5、SEE-V2X 已在历史批次涉及。UCI 415 的变量说明主要是端点编号和信号质量，未据此断定有原始双钟。Katagiri 等论文作为成功解码才记入接收端的反例 |
| 机器人无线测距 | UWB mobile ground robot dataset raw timestamps poll response ranging ground truth DW1000；inter robot UWB ranging dataset raw timestamps multiple robots motion capture TWR；UWB timestamps dataset two-way timestamps raw TWR DS-TWR packets localization | 排除已登记的 MILUV、Bern TWR-CLOUD、Hanyang 与 RoboLoc-G。跟进 Ghent 硬件实验数据卡、JKU 静态测距库 |
| Ghent 官方数据卡 | 快照 d813ce72783241142102723b77c09c0f5fa165d1 中的 Two-way Ranging Correction Dataset 与 UWB CIR Dataset for TDoA Correction and Fingerprinting，依次追查 refs. [4], [5], [8], [9], [10] | 取 Random 和两个 ADS-TWR 目录的光学与无线诊断文件，先测试 HTTP 字节范围，然后核完整表与摘要。单记卡片与原表数量差异。Racks 较大，本轮只探查文件大小。Grid 下小写 processed_full.csv 地址返回 404 |
| Linz 两套存储库及项目出版物 | 精确题名 Labeling for UWB Ranging in Weak NLOS Conditions、Data Trustworthiness for UWB Ranging in IoT；UWB-AEC-trust-dataset model railway Peterseil | 论文参考文献给出静态转台库，项目白皮书 §§2.1–2.2 分别列出两套存储库。转台全部 36 个文件均验证固定提交的 blob。动态铁路只统计 dyn_nlos、dyn_nlos2、dyn_person 三条行驶记录 |
| 引文与版本 | Crossref /works/{doi}、OpenAlex /works/https://doi.org/{doi}、Ghent 与 JKU 官方仓库、MDPI 正文、InSecTT 白皮书 | 确认期刊版与预印本别名，依据实际打开的 PDF 判定全文。论文引用边依据 Crossref 返回的 reference key 或 PDF 明确编号定位 |

固定源树 ppeterseil/UWB-weak-NLOS-structured-dataset@fc165c5a68c95a0cfc80729905081654737842ad 和 ppeterseil/UWB-AEC-trust-dataset@12f631086eaf1f6510e5feb98627a6aefa8b1feb 均允许公开读取，树中没有许可文件。Ghent 数据卡标记 Apache-2.0，外链 Nextcloud CSV 没有单独的许可字段。只提交原始汇总与元数据，论文 PDF 只留来源、定位和哈希。

基线取自 cloud-state/my-phd@49343b1f18874eaade2caa56c6cea4908e5dcaf3。使用 DOI、arXiv 编号、题名和两个机构的库名、共享标识逐一匹配历史项目快照。统一大小写，去除重音、空格、标点以识别常见题名变体，参照原论文核实作者与题名。卡片的两个 ADS-TWR 入口合并为一个来源。JKU 两个数据集由项目白皮书分别列出，转台与铁路各自只计一次。

本轮对历史快照 1,727 个文件均作标识与规范化题名匹配，包含 7 个 gzip 文件解压后的内容；14 条文献和 4 项来源在此项检查中均无历史同键命中。文献中 12 条有全文定位，2 条为书目初筛；共保存 30 条引用或目录链接关系。
