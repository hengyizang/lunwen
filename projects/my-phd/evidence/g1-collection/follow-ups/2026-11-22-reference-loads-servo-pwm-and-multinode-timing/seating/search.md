# 装配资料检索与筛选日志

2026-11-22 01:07–01:24 UTC，通过公开网页搜索、DataCite、Zenodo、DaRUS、Mendeley Data、OpenAlex、Crossref、Europe PMC 和大学资料库检索。将来源 DOI、概念 DOI、历史版本、完整题名和第一作者同本轮父快照核对。若历史库已保存论文或数据，仅作关联或筛除。文献表收录期刊论文、会议章节、技术报告、学生论文和预印本，其证据等级逐项标明。[书目信息](literature.csv) · [数据版本与许可](sources.csv)

| 检索式或入口 | 筛选和实读结果 |
| --- | --- |
| 网页搜索 `dataset recorded force displacement press fitting interference fit snap fit assembly`，以及 DataCite 标题全文 `clinching OR riveting`、`peg-in-hole OR contact-rich assembly`、`press fit OR interference fit`、`robotic assembly` | 已有的 CERTH 卡扣、铜环、PiH、线束压接等条目保留在历史批次。Zenodo 2633157 是过盈配合计算表。Mendeley ty3dbg3vjs.1 的摘要只列视频。已入历史的 CE-PKSN 概念记录 24331002 对应版本 24331003；本轮不计新增。自冲铆接拆后拉伸数据可用作强度对照，未作为装配过程的力参考。 |
| 网页搜索 `robotic assembly force data HARTU learning from demonstration`、`HARTU D4.1 assembly dataset Tofas Philips KUKA force sensor` | 从 HARTU 第一版追至 v1.1，按工件和完整／分步操作分层选四份完整 HDF5。D4.1 §3 引出独立的 ABB 工具端力和贴片试验，三个 tactileFingers 子目录的六个测量文件均读取。吸盘文件未计入贴片核验。 |
| 网页搜索 `experimental data robotic adhesive application and joint pressing`、`Opgenorth pressure film pressing torque on-site timber bonding` | DaRUS 6450 发布页标注数据文件 unrestricted，完整 ZIP 的 MD5 与 Dataverse 一致。逐列读取压力机构 CSV，目检压力膜和剖面示意图。预印本 SSRN 7619696 直接取 PDF 遇到 HTTP 403，仅作书目初筛；2024 年论文与该预印本分开列出。硬件 CAD 和控制软件不当作测量数据。 |
| 网页搜索 `click event automotive connector locking sound ground truth dataset`、`acoustic validation snap fit shaver proof`、`click sounds automotive dataset Espinosa Mendeley` | 经大学资料库找到 Mendeley 数据 DOI。文件详情列单一 DataSet.csv，公网整包下载后按发布者 SHA-256核验。重复定义为 213 个按原次序转为 little-endian binary64 的数值全部相等，分类标签不参与指纹。对 PMID 33752578 只读取文摘，对 2020 年论文读取全文 XML 核对视频标注。 |
| Rouwhorst 文献 [1]–[3]、原作者 PDF 与布尔诺大学书目 | [1] Doltsinis 等是已收材料。对 [2] Radil 等 2022 章作书目初筛。另查到的 Radil 2026 博士论文属于以往批次。Rojas 2013 作者 PDF 可通过网页索引读取，普通二进制请求返回 403；该研究的所述实验为仿真。 |
| 标题与作者检索 `Bricher optical microphone connector`、`Opgenorth local robots adhesive bonding`、`Radil robotic snap-fit` 等 | 对照 DOI 和机构资料库。Crossref 部分请求返回 429，改用 OpenAlex DOI 对照及出版页。未向作者申请非公开数据。 |

## 文件与范围核验

- HARTU 装配 ZIP 发布者列 19,040,656,534 字节，MD5 为 `24721f4717f54012b72eaf2e4e2664f5`。通过 HTTP 206 读取完整 ZIP 中央目录，逐份完整解压选定的四个 HDF5，核对 CRC 并计算 SHA-256；未对 19 GB 整包计算 MD5。第二版 README 为 4,185 字节。D4.1 公共 PDF 的 SHA-256 为 `f7d1b09d684d10e2b461d257cb38ceaf87085b7bde710cad4c76d58ae55be2d8`。[版本 API](https://zenodo.org/api/records/12513790) · [实读成员](hartu-members.csv)
- HARTU 贴片 ZIP 发布者列 575,024,126 字节。三个子目录的六个文件在内存解压、CRC 核验和 SHA-256 计算。SCHUNK 文本每行有一列序号及 SI 六轴力矩；FBG 的通道数和时间列取自 HDF5。表只汇总原始值，未把同一行号当作两台仪器相同时间。[来源 API](https://zenodo.org/api/records/11387093) · [六个实测摘要](patch-tests.csv)
- DaRUS ZIP 文件编号 657027，98,847,740 字节，整包 SHA-256 为 `126505afc1eddc6fda35ecf353af2cbb671b1129ec276a3f93652ff6aac58fec`。压力膜图 `opgenorth - pressure_application.jpg` 的 SHA-256 为 `b3b0a3bfc0213d38abd9b4431d578bc79b8b28d5e8e542bb10d8a8c529f1588b`，成品剖面图 `section_cut_results.jpg` 为 `b6f807dd21face4157ae67afcca0e2440a3e9196a3e6af1aa1055c95b95f5b69`。CSV 有一个约 1 ms 的时间间隔，中位间隔为 0.2 s，依源时间计算。[版本页](https://doi.org/10.18419/DARUS-6450)
- Mendeley v1 的 `DataSet.csv` 为 178,167,682 字节。版本 API 只列该文件，发布者 SHA-256 与实读一致，即 `3fee0517e19f88099c46b4fc3f381e726b78cb0b4563b3322847c69a24163746`。单文件端点直连曾返回 403，官方版本压缩包可读。零非有限特征值，未将类别码外推为独立验证的锁止事件。[版本压缩包](https://data.mendeley.com/public-api/zip/2p4ng7zz3s/download/1)
- 铆接工作簿 LAP 与 PEEL 的体积分别为 8,585,816 和 26,864,305 字节，发布者 MD5 与实读一致。逐曲线抽取带有三项数值的行，不对不同步的曲线按行拼接。峰值为第一处达到最大载荷时的位移与时间。[来源 API](https://zenodo.org/api/records/12741922) · [原始文件 SHA-256 和派生量](rivet-tests.csv)
- Rouwhorst 原始 PDF 的 SHA-256 为 `711d86a418e3f7a77c7cc1d717f76c3e40d4608e62e8598daa1635a015e8ec35`，Bricher 2020 全文 XML 为 `203c3ae4ae17d9e3a72068b11eadc6af347f8c53f1ee042f08953f8926f32999`。文章全文、视频、图像和原始声学特征矩阵均留在各自原始来源。[声学全文](https://europepmc.org/articles/PMC7256605) · [剃须刀论文](https://fse.studenttheses.ub.rug.nl/31249/1/mME_2023_RouwhorstE.pdf)
