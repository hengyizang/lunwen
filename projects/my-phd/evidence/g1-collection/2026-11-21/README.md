# G1 文献与数据 · 2026-11-21

本批收录 **15,910 条**完成初筛和跨库排重的书目记录、**191 个**数据发布记录。**31 项**重点来源另附原文位置、可观察结果和使用限制。文献总表覆盖三个优先问题及其相邻方法，适合筛选下一批要读的论文。G1 仍处于选题阶段。

| 要找的材料 | 从这里开始 |
|---|---|
| 原文中的方法、直接先例和反例 | [31 项重点来源的阅读表](reading-guide.csv) |
| 可检索的完整书目 | [下载文献 CSV](https://raw.githubusercontent.com/hengyizang/lunwen/refs/heads/cloud-state/my-phd/projects/my-phd/evidence/g1-collection/2026-11-21/literature.csv)，按 priority、streams、year 或 registry_check 筛选 |
| 实体数据与仿真基准 | [191 个数据发布记录](datasets.csv)，含访问方式、限制、别名与历史匹配 |
| 已实取并清洗的数值数据 | [逐测点数据、汇总、许可与来源](data/README.md) |
| 来源之间的引用关系 | [引用关系表](citation-edges.csv) 与 [追踪方法](audit/citation-search.json) |

## 三个优先问题

| 问题 | 已有工作与可检验的边界 | 初筛队列 |
|---|---|---|
| R1 · 装配接触时，何时应冻结腕部传感器偏置更新？ | Nadeau 等已提出连续估计偏置与漂移，假设末端夹具惯性参数已知。Skrede 发布了基线、振动与人工接触数据；说明中的补偿状态有歧义，独立接触力真值仍缺失。[原文](https://arxiv.org/abs/2403.01068v1) · [数据](https://zenodo.org/records/11096791) | [44 条](r1-reading-queue.csv) |
| R2 · 执行器受限时，修正参考轨迹与继续适配可如何区分？ | 已有期刊研究在仿真中比较受限条件下的参考修正。IDSIA 实飞发布提供电机转速和状态，可检查动力学辨识与跨轨迹误差；饱和标签和逐桨力仍需另找。[论文](https://doi.org/10.1038/s41598-026-65823-8) · [实飞数据](https://www.nonlinearbenchmark.org/benchmarks/nano-drone) | [408 条](r2-reading-queue.csv) |
| R5 · 时钟不同步时，如何判断邻机状态是否仍可用？ | 实车协同定位论文分别测量过钟差和网络延迟。CooperScene 的节点元数据可核对吞吐与缺失；RoboLoc-G 的测距握手可核对时戳单位。应用消息年龄仍需对应的发送、接收及对钟记录。[实车论文](https://tisl.cs.toronto.edu/publication/201910-itsc-cooperative_localization/itsc19-cooperative_localization.pdf) · [测距数据](https://doi.org/10.5281/zenodo.15989282) | [70 条](r5-reading-queue.csv) |

## 筛选与核验

- 检索覆盖 Crossref、OpenAlex、arXiv、CoRL 和 RSS 的会议目录、相关研究的引文以及一手数据发布页。邻域包括导航、定位、操作学习、系统辨识、制造与结构力学。各路查询条件、日期、原始响应指纹、限流与恢复情况见 [检索记录](audit/)。
- 标签命中或来源核读后进入优先队列的共有 522 条，各队列可以重叠。部分条目只有题名和书目信息，单凭这些字段不能判断实验成效。语言和数据库覆盖偏向英文，预印本、会议短文及期刊扩展版仍可能存在未识别的版本关系。
- 排重使用 DOI、arXiv 编号、相同来源 URL 或相同规范题名加作者。对另有一手依据的版本关系进行合并，并保存各版本入口。与运行前固定快照对照，25 条稳定标识匹配、3 条仅题名可能匹配、15,882 条未在已核快照中匹配。数据目录含 58 个 Open X-Embodiment 子发布，多个发布可以来自同一原始采集。[排重与历史基线](audit/literature-merge.json) · [数据目录比对](audit/dataset-merge.json)
- 对合并前快照中的 14,002 个 DOI 均发起注册查询，取得 13,995 条注册题录。最终表中 13,987 条有主 DOI，其中 13,959 条的题名原样或规范化匹配。跨语言、改题、未返回题名和确定错配分别处置。HRP-4 曾被索引错绑到一篇视觉跟踪论文，该绑定已从书目中排除。[逐 DOI 结果](audit/doi-validation.csv.gz) · [例外处置](audit/doi-decisions.json)
- 引文追踪有 622 条按种子和方向登记的观测，对应 621 个不同的有向标识对。保留源索引的错误观测并标记；1 条带有已确认的目标 DOI 错配，已依据原文参考文献第 8 项补注正确的目标。双向引文取自开放索引，索引未识别的种子另查原文参考文献。DOI 可解析及存在引用关系都不等于论文支持某个主张。
- 早期四层抽查共 48 条，发现将普通网络方法、一般力传感器校准归入优先问题会扩大范围。随后收紧了 R1、R5 的题名条件，并复查同题版本。抽查基于较早的固定快照。[抽查表](audit/catalog-spotcheck.csv) · [同题版本处置](audit/confirmed-aliases.json)
- 三个优先问题分别在项目原生 GitHub Actions 中取得代表性原文 PDF，并记录实际来源、字节数和 SHA-256。方法和实验边界集中在重点阅读表。后续增量优先追踪具备独立接触参照、实际执行器受限记录和经对钟的多机器人逐包记录的数据。[三次云端回执](audit/cloud-jobs.json)
