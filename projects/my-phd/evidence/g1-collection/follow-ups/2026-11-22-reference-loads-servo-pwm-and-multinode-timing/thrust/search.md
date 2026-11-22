# 公开检索记录 · 2026-11-22 UTC

从前序 R2 的“指令与独立负载测量”缺口出发，限定水池与民用 ROV 实验，分别核查台架静态、台架动态、装机载荷与自由运动记录。用下列查询检索公开网页、DataCite、Crossref，并读取作者或厂商原始入口。

| 查询或路径 | 来源与处理 |
|---|---|
| `public dataset underwater robot thruster transient thrust PWM load cell raw data csv bench step response system identification underwater T200`；`underwater thruster dynamics experimental dataset load cell step input forward reverse` | 找到 Edinburgh DataShare、Khanmeh 等的 Zenodo 和 Ocean Systems Lab 的水池轨迹。DataShare 的数据论文与 2021 年研究论文对应一个试验系列。 |
| `Blue Robotics T200 T500 official performance data xlsx forward reverse` | 通过两个产品页的 Performance Charts 链接读取 2019/2022 工作簿。读取 XLSX 绘图层中的 READ ME FIRST 试验说明，确认采样、力传感器、平均方式与低转速归零规则。[T200](https://bluerobotics.com/store/thrusters/t100-t200-thrusters/t200-thruster-r2-rp/) · [T500](https://bluerobotics.com/store/thrusters/t100-t200-thrusters/t500-thruster/) |
| `"A Low-Cost Test Bench for Underwater Thruster Identification"`；`"Propeller Characterization Testing of a Blue Robotics T200 Thruster"` | Crossref 题名与参考文献匹配。Laidani 仅按书目与后向引文入表，Lam 另有作者页面。相同出版物的不同搜索页面合并。[Crossref](https://api.crossref.org/works/10.1016/j.ifacol.2019.12.316) · [作者实验说明](https://www.jessica-lam.com/blue-robotics.html) |
| DataCite `titles.title:"underwater thruster"` 与 `titles.title:BlueROV2 AND types.resourceTypeGeneral:Dataset` | 第一式返回的 Newcastle 条目是论文贡献及其版本，不作原始测量数据；第二式未命中。只有在正向搜索或论文数据声明中找到并读取文件才登记可用材料。[DataCite](https://api.datacite.org/dois) |
| von Benzon 等 §4.1、文献 4/32；`"MATLAB and Simulink Robotics Arena" "From Data to Model"` | 读论文 XML，回溯 Pedersen 原学术论文 PDF 和 File Exchange 65919。版本 1 和版本 2 压缩字节 SHA-256 不同，23 个对应成员的解压字节一致，仅计一个发布。18 个数据文件已逐表读入。[控制论文 XML](https://mdpi-res.com/d_attachment/jmse/jmse-10-01898/article_deploy/jmse-10-01898.xml) · [Pedersen PDF](https://vbn.aau.dk/ws/files/335391959/1_s2.0_S2405896319309723_main.pdf) · [文件包 v2](https://www.mathworks.com/matlabcentral/mlc-downloads/downloads/submissions/65919/versions/2/download/zip) |
| 安装条件的近邻与反例 | 阅读数字孪生论文 §4.2.1、图 3 和参考文献 46。作者用三轴测力台检查装机后的合推力，特别指出大 PWM 时水平向实测与单推进器外推的差距。图未作为原始数据重复纳入。[出版者全文](https://mdpi-res.com/d_attachment/applsci/applsci-15-07085/article_deploy/applsci-15-07085.xml) |
| Edinburgh DataShare `10.7488/ds/2835`，Zenodo `15976877` | 前者对照数据说明表 5、7–9、发布者 XML 与归档目录；后者读取 Zenodo v1.1 元数据、Europe PMC 全文及归档目录。完整读取并校验 36 + 4 个选中成员；其余成员只查文件目录。[Edinburgh 数据](https://doi.org/10.7488/ds/2835) · [Edinburgh 论文 XML](https://mdpi-res.com/d_attachment/data/data-05-00057/article_deploy/data-05-00057.xml) · [Zenodo 版本](https://zenodo.org/records/15976877) · [同行评审文章 XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12808086/fullTextXML) |
| `"Bluerov2_trajectory_dataset" trajectories` | 读取作者 README、完整 Git 树与 39 个不同 CSV，以 Git blob 与 SHA-256 校验。README 未指明记录的独立推力计；不以同表的 `thrust` 列标注实际电机推力。[固定版本](https://github.com/oceansystemslab/Bluerov2_trajectory_dataset/tree/5104d15d2f9756ff45b4b0ed2b95d284a6e30e43) |

Edinburgh 数据与 Khanmeh 数据各有 CC BY 4.0 声明。MathWorks 文件包附带三条款 BSD 形式的许可证。制造商数据与水池 Git 库的再分发许可未核实，本次保存来源、验证摘要及汇总指标。[逐来源权限和别名](sources.csv) · [引文与数据关联](edges.csv)
