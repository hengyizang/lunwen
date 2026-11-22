# R5 检索与去重说明

2026-11-22 UTC，接续父提交 `0b8440df47e480d84147cef4e98151c092f724d2`。先检查以前目录中的 DOI、版本、项目名及文件级结论。复用同一实物的数据论文、机构存档和数据集分别记录关系，提交给项目总表作全历史去重。

| 查询或追查 | 公开来源及实际处理 |
| --- | --- |
| `industrial robot AGV wireless closed loop network latency dataset measurements packet timestamps robot 5G timestamp AGV zenodo industrial`，`physical mobile robots networked control data latency send receive clocks data Zenodo robot command delay` | 找到 Aalto 的 4706065，下载 3 个 SQLite 数据库，检查 MD5 和完整性。作者项目将其与 DOI 10.1109/ETFA46521.2020.9211954 相连。Aalto Pure 的 PDF 直链返回 403 后，Aaltodoc DSpace 题名接口提供了同校存档的两篇 PDF。核对 2021 工作的参考文献 [8] 指向 2020 工作。 |
| `GPS synchronized sender receiver dataset one way delay industrial AGV factory robots packet measurement data`，`robotics 5G latency dataset remote control robot arm timestamp actual actuation` | 追到 5G-SMART D2.3 的 §5.4、§5.5、§6.3 和操作臂验证；由该报告的 [5GS22-22] 核查早期 D2.2。直接从固定 PDF 重算。iV2V/iV2I+ DOI 10.21227/04ta-v128 曾是项目线索。IEEE DataPort 提示登录，Fraunhofer 公开文档可看；不将其计入此次实读数据。 |
| `dataset send receive timestamp real industrial wireless latency one way GNSS PTP`，`time synchronization dataset wireless industrial raw timestamps reference gps synchronized` | HYMN 论文与仓库的概念 DOI 为 17979434，实际 Zenodo 版本为 19566178。核查版本 API、全包 CRC、五种技术的处理后 CSV、合并索引、参考时段、合并代码、许可证。版本 1.0.0、1.1.0、1.2.0 仅核对元数据。 |
| `PTP over wide area networks with offset measurement outlier filtering`，`Clock Synchronization Accuracy over Mobile Networks` | 第一个命中是仍受限的 14231423，查 versions/latest 得到公开 v2.1 16794348。历史 G1 已完整核验 v2.1 的实网 ROA 文件，前批没有发表逐个实验台/训练文件的 t1～t4 栅格、残缺配对、独立时钟差和时间倒退统计。本批保留这项增量。另一个 14230741 移动网络数据已在以前的同目录中处理。SLATE-PTP、Porto 抓包、CARMA、MR.CLAM、MILUV、马拉加遥机器人等系列在旧目录中，不重复建表。 |
| `teleoperation dataset command and feedback time delay master slave timestamps`，`Latency characterization in real-time robot supervision via network camera system` | 对公用 J-STAGE 论文表 2 逐格核对，区别主机日志与高速摄影。沿参考文献到 Das/Dobie 的 Sunderland 接受稿、Kaknjo 等的开放全文、Green 等的书目，以及 Chakraborty 等的公开 arXiv 稿和代码归档。后者的离线 RGB/深度/位姿数据没有核验为双端通信记录。 |
| `Fraunhofer AI4Mobile iV2V iV2I+ dataset AGV NTP`，`5G-SMART industrial robotics completion time` | 核对 DOI 10.1109/MCOM.001.2300494 及作者资料。Fraunhofer 文档 TCP Dump 段明载两端同步曾中断最长 30 min。Kista 的以太网基线与附加 5G 流量实验则有可见实物结局，按不同条件列在派生表。 |

三份实际下载的数据产品保留作者源站的 DOI 和校验和，重新生成的表和脚本均为小文件。HYMN 许可证分层，数据文件按包内 CC BY 4.0 署名，代码按 MIT。Aalto 与 UGR 逐文件派生按各自 CC BY 4.0 署名。AGV 数据采用发布者所列的姓名拼写；发表物采用原稿署名。检索和引用中没有使用付费服务。

- [Aalto 数据记录](https://zenodo.org/records/4706065) · [Aaltodoc 题名检索接口](https://aaltodoc.aalto.fi/server/api/discover/search/objects)
- [HYMN 版本](https://zenodo.org/api/records/19566178/versions) · [TUD 源码](https://github.com/TUD-ITVS/HYMN-dataset/tree/1.3)
- [UGR/ROA 版本及访问状态](https://zenodo.org/api/records/16794348/versions) · [以前的实网审计](https://github.com/hengyizang/lunwen/tree/0b8440df47e480d84147cef4e98151c092f724d2/projects/my-phd/evidence/g1-collection/follow-ups/2026-11-21-radio-clocks-and-control-response/sync)
- [Fraunhofer 公开文档](https://github.com/fraunhoferhhi/ai4mobile-industrial) · [DataPort 记录](https://doi.org/10.21227/04ta-v128)
