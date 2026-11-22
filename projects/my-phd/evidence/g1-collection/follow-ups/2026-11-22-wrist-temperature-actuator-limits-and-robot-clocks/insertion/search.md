# 装配接触检索记录

检索时间为 2026-11-22 UTC。父状态提交为 `0b8440df47e480d84147cef4e98151c092f724d2`。使用公开网页、论文作者版、Crossref、OSTI、GitHub 和 Hugging Face。按 DOI、arXiv、作者题名、数据仓库和文件内容标识核对父快照。下表列出实际检索词中的关键部分及逐步筛选结果。

| 入口与检索词 | 处理及理由 |
| --- | --- |
| 网页搜索 `robotic connector insertion force position electrical continuity dataset real robot`、`snap-fit robotic assembly click detection force acoustic dataset` | CERTH 1209203、铜环 6364950／7221387、WireFishing-M、Yumbla、电连接器摇摆实验 10.1038/s41467-026-74643-3 均有历史材料，未再采为新来源。 |
| 网页搜索 `robotic USB insertion electrical continuity successful insertion detection data GitHub` 与 `robot connector assembly electrical connection success force insertion` | 检出 Schoettler 等的电气回报、Li 等的部分插合判据和 NTU 实物 USB 项目。打开项目用户资料与 GitHub API，确认 default_branch=IBVS，逐一读取该分支树与 77 个日志，过滤模型训练 CSV。早期 main 分支的 77 个同内容文件逐个核对为相同 blob。 |
| 网页搜索 `photovoltaic connector force resistance mating insertion depth NREL` 和 `CharIN Megawatt Charging System 89238 OSTI` | OSTI 免费下载四次活动报告，阅读其 NOTICE 和 §§3.2.1–3.2.5。只将正文中的实验设计、分母和筛选条件用于证据说明。Mendeley 光伏接头记录 10.17632/y4c8pw8f5n.2 在 DataCite 可见，但测试的公共文件端点返回 400／403，且并非同步装配腕力记录，未计入可用实测文件。 |
| 网页搜索 `contact resistance insertion force force displacement four-wire electrical connector` 与 `heavy duty connector insertion axial force ECR` | 读 Zhang 等 2026 原文 Fig. 10–12、Meng & Ren 2021 Figs. 1–5、Ni 等 2021、Qian 等 2024、Siddaiah 等 2019 的仪器与测量说明。Zhang 引文 [37] 是 2025 年纯模型研究，保留为区分仿真与实测的对照。SAGE 源页在网页检索可核读全文，脚本直接请求其 PDF 时返回 403。仅发布原创注释及按许可计算的摘要。 |
| 网页搜索 `robot connector insertion contact onset 45.8 mm 31.8`、`Three-axis flexible tube sensor LSTM charging ports` | 找到移除了插针的真机试验，核对原文 10 次平均与人工判读起点。沿 [15] 查同一柔性管的校准论文、沿 [16] 查插拔耐久实验。另核对 40 人手动充电接头论文的摘要，分开记录人工和机器人实验。Ultima 论文 DOI 在期刊页和 PDF 对应同一身份，Crossref works 端点未收录。 |
| 网页搜索 `tactile insertion dataset peg gripper ground truth pose force real robot` | 发现 TacRich-Manip 遥操作插柱。公开 API 标为 private=false、gated=false 并实际读取文件。数据卡中保留“采集中为私有”的历史说明。核对真实传感器响应、源时间回退和固定 revision。shu4dev AIC 光纤插接样本的数据卡表明来源是 Gazebo，未纳入实物数据。 |
| Crossref `query.bibliographic` | 用 Schoettler、Li、Silvério、Mayton 的完整题名与三篇插接电阻论文题名分别查前三条，并核对 DOI/作者。一次按柔性腕论文题名的首条匹配为无关作品，采用期刊与 PDF 实际标识。检索中部分 429 后重试，SAGE、IEEE 等采用 DOI 元数据补查。 |
| 历史筛选与外部许可 | 父快照的初筛目录已有 Li 2014。本轮证据推进到正文成功标准，计数交由批次总目录统一排重。原始个人图像、模型权重、NREL 图表及论文全文均留在源站。 |

## 文件核验

- USB 的完整版本为 `05ae5aa8d98ed40d373dba32914fe04d629ab5c8`，树为 `509d97b505017e5f6d7a977af1a62cb26750bcdb`。核对 Git blob 的 77 个文件共 39,766,759 字节。对照早期 main 提交为 `faa3e4b1af72316ff74b94c3ea0af6ad60dce979`。后来的 README、状态机和记录格式不能反推每一份旧实验具体部署了哪次代码。[固定版本](https://github.com/RafieHanania/FYP-RoboticInsertion/tree/05ae5aa8d98ed40d373dba32914fe04d629ab5c8)
- TacRich `meta/episodes/chunk-000/file-000.parquet` 全部读取，实测 SHA-256 为 `8be6e88259cd7a08689b97c6cf62cf70739962939c71d92f090d451fe89527e6`。与逐数据文件计算的 79 个回合长度完全一致。`meta/tasks.parquet` 的单项标签为 `teleoperation/insert_peg_cylinder`，文件 SHA-256 为 `2974128875779cae3bafb7ffd8c0ca0dcd50ac9d6e1942a6b4cbc5e532acaa19`。每个固定数据分片的下载范围和 SHA-256 已写在单独清单中。[数据分片](tacrich-shards.csv)
- 已读取并直接验证内容的 PDF SHA-256 如下。其他论文的网页全文或文摘版本与精确位置见文献目录。Mayton 2010 的 CiteSeerX 全文可在检索索引阅读，直接获取二进制遇到 404，另有完整正文镜像。[文献及证据位置](literature.csv) · [Mayton 镜像](https://www.academia.edu/117411502/Robot_feed_thyself_Plugging_in_to_unmodified_electrical_outlets_by_sensing_emitted_AC_electric_fields)

| 文档版本 | SHA-256 |
| --- | --- |
| OSTI 2367301，NREL/TP-5400-89238 | `e5165d93482684aeccc0d09e2204b118322cd308b0897ea2d2d58a6914cf06ca` |
| Schoettler, arXiv 1906.05841v2 | `9e6381f4925112cefa9bef8b4ef68abacf08da04c77372be897612b9dabeacca` |
| Schoettler，同题 workshop 版 paper/13.pdf | `534caa7a58123aa2dd5921efe1415f7dd196ce161d86ace1d4194717a10e5489` |
| Li 等，2014 作者版 | `7243655353ae724257a8066401e8ad54e22a7ec53b6ff9dbc979211ecb94e146` |
| Silvério 等，2021 作者版，arXiv 2011.01573v2 | `366ef85f254da73c82f9c30cee3324581df0b7823bc70eee122447e67bf85cf3` |
| Siddaiah 等，2019 出版社 PDF | `75d9992694d0ed8d0185e6e08c7d6a83419521c933829188be6f0b36badfc38f` |
