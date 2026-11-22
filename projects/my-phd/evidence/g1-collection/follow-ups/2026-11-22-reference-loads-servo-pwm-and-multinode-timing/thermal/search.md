# 检索与筛选记录

2026-11-22 UTC。范围为实验室标定、腕部力及力矩、温度和装配接触参照。检索通过公开搜索、Europe PMC JATS、出版社数字附件、Figshare 和 Crossref 完成。论文附录和工作簿均在公开入口读取。未取得的原始传感器流不列为可用文件。

| 查询或追查入口 | 保留材料与判断 |
|---|---|
| `strain gauge six-axis force torque calibration dataset sensors temperature load robot tactile`、`six axis force torque wind tunnel calibration data machine readable temperature` | 查询六轴力矩测量与空载热漂。Gong 等已在历史书目，将其数字工作簿作为该文的证据升级。直接检查 Methods 中的校准机构、温控说明及补充说明 4–6。对 S24、S34–S36、S39b 做可重复的配对与端点复算。 |
| `Monolithic 6-Axis Force/Torque Sensing by a Single data source repository calibration temperature` | 从出版社和 Europe PMC JATS 确认同一 DOI 与附件文件名，沿正文第 22 条参考文献连回项目已有 Mao 等 2025 六轴指尖研究。串联 ATI 传感器用于台架，另有便携轮询电路；用于动态负载测量的设置不能直接等同机器人在位静载。 |
| `calibration robot force torque dataset temperature sensor robot assembly raw rosbag wrist force temperature` | 检得 Dong 等六轴检测系统。历史日志曾在装配独立数据筛选中以电子学研究排除。本批重新阅读全文，作为热箱/六轴检测系统方法对照入书目，保留电子学适用边界。沿文末第 4、15、19 条核对两个已列六轴研究及 Long 等三轴协作腕部研究。 |
| `Ultrathin Three-Axis FBG Wrist Force Sensor for Collaborative Robots temperature calibration`、`fiber Bragg grating wrist force sensor calibration temperature weights` | Long 等仅验香港理工大学研究库摘要及 DOI。另查 Jiang 等图 13–15、表 3，确认实物砝码和三个方向的重复加载。 |
| `pressure temperature Source data tactile sensor independent force pressure cross-talk Nature Communications calibration workbook decoupled`、`pressure temperature source data flexible decoupled multimodal tactile thermal pressure force sensor` | Zhu 等工况交叉；Yu 等的两个标定量各有单独的横轴；Mao 等将法向力计和恒温箱分别标定；Bai 等有压力与热梯度交叉刺激；光学触觉实验支持加卸载回线对照。均查阅 JATS、Methods 和实际工作表，不从学习输出推断参照真值。 |
| Zhu 等文末 42、43、50；Yu 等文末 45、52 | Gao 等同一 ACS Nano 论文出现在两个引文表，只保留一条书目与两条边。其余光热压力近邻仅按 Crossref 元数据初筛。Yu 数据第 52 条为 Figshare；API 给出 2,240,767 字节、MD5 `18bcf507cb654580ea766064a800ac31`，与出版社已取回文件逐字节摘要一致。数据集版本标识、概念 DOI 及出版社文件名合为一条。[Figshare API](https://api.figshare.com/v2/articles/25133534) |
| `open source six axis force torque calibration measured data load cell calibration csv public github`、`Fingertip-scale six-axis tactile interface dataset github raw data` | 校准教程里展示的字段例子不足以证实实测文件；HexaTouch 的可读附录以说明与视频为主，论文说明其他资料可向作者索取。现有腕部质量/质心 Zenodo、Mao 指尖和上轮 JPL、Cornell、Kim、Liu 研究没有重复计入本批新文献。 |

## 去重、复核与限制

使用 DOI 的小写形式、可识别的作者和题名、PMC 编号、Figshare 版本及文件名，逐项比对状态分支历史证据。Gong 等和早期六轴研究只作为历史锚点。Dong 等的 DOI 曾出现在筛除说明，现明确登记为初次形成全文条目的比较研究。新收的书目没有单独发现可确认的 arXiv 别名。数值源文件的大小与 SHA-256 记录在输入清单，原始文件留在出版者。[来源输入](inputs.csv) · [有向引文](edges.csv)

压电壳实验可同时提供台架独立六轴参照与温度分组证据。S24 和 S34–36 的列和记录单位不同，仍缺少逐试次同步的传感器本体实测温度、工件载荷、姿态和装配接触事件。八台样机对应同一实验室，不增加独立实验室数量。跨领域的贴片和光纤研究保留比较所需的读数单位、参考器件与仪器条件，汇总值无法推出腕部的热漂系数。
