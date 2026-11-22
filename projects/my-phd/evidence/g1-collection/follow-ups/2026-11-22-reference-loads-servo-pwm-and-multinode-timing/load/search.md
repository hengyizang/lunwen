# 检索与筛选记录

2026-11-22 UTC，公开免费检索。主题是驱动器电流或扭矩之外的机械参照，及力/力矩接触探头与模型估计之间的区分。

| 服务与查询 | 初筛及追查结果 |
|---|---|
| DataCite，types.resourceTypeGeneral:Dataset 与 (titles.title:actuator OR titles.title:actuation) AND (descriptions.description:"load cell" OR descriptions.description:"dynamometer" OR descriptions.description:"torque sensor")，最多 75 条 | 2 条为同一 Zenodo 记录的概念 DOI 与版本 DOI。选定 10.5281/zenodo.23769731，下载元数据、数据说明、M0–M3 脚本与完整原始 ZIP。核对 MD5、9 个已文档化通道及 8 种工况。 |
| DataCite，同样的类型过滤，titles.title:("series elastic" OR "quasi-direct drive" OR "actuator characterization" OR "robot actuator") | 6 行含多个版本。10.6084/m9.figshare.34743448.v1 在既有 continuous/datasets-new.csv。Figshare 显示唯一文件为 2,793 字节的 TeX。10.15480/882.18053 是振动触觉器件频响库，未列入当前机器人传动批次。10.25384/sage.14778903 的供应商 Figshare 标准 API 查无此号，未验证原始数据。 |
| DataCite，exoskeleton/exosuit 题名 + 描述中 torque control / torque tracking / torque sensor；ankle/prosthesis 题名 + torque tracking / torque control / benchtop | 两次组合查询返回零行。所查字段和拼写限制召回率。 |
| DataCite，creators.name:"De Smedt, Nathan"；creators.name:"Verstraten, Tom" AND types.resourceTypeGeneral:Dataset | 后者返回 7 行（含不同版本），由合作者找到 10.6084/m9.figshare.30023476.v1。10.48804/OWJOID 是用于步行识别的 IMU、眼镜摄像等数据，无相应台架反力。 |
| Crossref、公开网页，精确题名 Partial Parallel Elastic Actuation: A Novel Actuation Paradigm for Mechanical Energy Recycling 及作者/驱动/反驱术语 | 核实 Zenodo 发布者给出的论文题名，未找到可独立验证的配套论文版本，未把该题名单列为已发表论文。相邻作者工作转向 VUB 开放稿件。 |
| 公开网页、VUB、Crossref，De Smedt Roozing Vanderborght Verstraten spring efficiency parallel elastic backdriving transmission measurement；Modeling and dimensioning of geared DC motors Verstraten torque sensor；Dual-variable Ballen Moreno Ferrentino force torque indentation phantom | 阅读四篇弹性执行器稿件、被引的齿轮电机损耗实验稿及一篇六轴仿体接触实验稿。资源页面题名有 design/dimensioning 两种拼写，按 DOI、作者及试验装置合并。Beckerle 使用 2017 卷期，Calanca 使用 2022 卷期，另记在线年份。 |
| 全文引文 | Calanca/Verstraten 的 [4]、[49]，Beckerle 的 [19]、[21] 和 Verstraten 2016 的 [32] 均已按参考文献核对。仿体论文 Supplementary data 明引 Figshare 的概念 DOI。去重后保留六条关系。 |
| Figshare REST v2 的 articles/30023476，版本文件 57562576 | 中央目录共 5,970 个条目（含目录项），分为 Neo-Hookean、Ogden、Yeoh 三种模型。逐一检验 Neo-Hookean 四个位置的候选 1、2，并抽查一个 FEBio 力、位移、扭矩文本组确认是仿真输出。只纳入同一候选的有限实测插值曲线。 |
| 历史回查 | 在状态分支快照的整个 projects/my-phd 下用六个文献 DOI、两个资源的概念/版本 DOI、来源 ID、主要题名/作者拼写做大小写无关的检索。历史已有的 flexible-link Figshare 项排除。新增文献和来源在本地快照未命中，提交前以合并后的最终去重为准。 |

DataCite 查询可在 https://api.datacite.org/dois 的 query 参数中复现。DOI 登记信息可在 Crossref Works API 依 DOI 核验。对象版本与所读范围见 sources.csv、literature.csv 和 verified_objects.csv。
