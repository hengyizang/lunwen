# 检索和核验记录

访问日期为 2026-11-22 UTC。起点为前一轮公开材料中仍缺失的腕部传感器本体温度，以及可区分已知外载、参考传感器和模型真值的试验数据。

| 检索路径或输入词 | 检索与处理结果 |
|---|---|
| 公开搜索，`"force torque" "temperature" sensor dataset calibration robot Zenodo thermistor`、`six axis force torque sensor temperature compensation calibration dataset strain temperature applied load robot` | 找到 Kim 预印本、iCub 方法、热箱试验、openFT 仓库。后两类机器人校准数据已有历史记录；本批只对 Kim 已收论文补做两张表的交叉比较。 |
| `temperature compensation six-axis force torque sensor temperature experiment temperature sensor force moment strain gauge raw data robot`、`robot force sensor dataset drift temperature load cell thermal balance calibration known force` | 新增 Zhang 等模块关节转矩热实验。在线出版者正文可读；Hindawi 旧 PDF 入口返回 403。加热曲线与单独的制动器载荷标定分项登记。 |
| DataCite `10.48577/jpl.wbf9x6`，JPL API `/api/datasets/:persistentId/?persistentId=doi:10.48577/jpl.WBF9X6`，检索 `"Calibration of a 6-Axis Force-Torque Sensor" Mars 2020 calibration temperature load bias` | 核对唯一存档文件 81216 的版本、5,920,271 字节、MD5、题名和作者。确认原件是 Schaler 等 2021 论文作者稿、图 7 为矢量柱。此前项目中的期刊 DOI 曾出现在早期 R1 目录，此次新增数值和文件清单。 |
| `temperature compensated six-component force balance raw calibration data public calibration data temperature`、`"temperature-dependent" RUAG strain-gage balance Ulbrich Zimmermann` | 在 NTRS、Crossref 题名比对后下载 2018、2019、2020 年的三份公开稿件。2019 年报告表 2 和不同温度模型对同一核查集的差异可核；2020 年文末 1、2 及 2019 年文末 1 的来源沿引文登记。 |
| `"temperature and force" "Source data" force temperature tactile robot pressure strain gauges`、`"six-axis" "temperature" "dataset" force sensor calibration tactile board` | 核对 Liu 等的 Nature Communications 论文、出版者 Source Data 的 OOXML 各工作表实际对应关系。筛取 Fig 4d、5b、5c、5d、5e。其余图页没有计入此次测量条数。 |
| `tactile "temperature" "weights" force tactile calibration raw data`、`pressure load cell board data source supplementary tactile force temperature weights` | 阅读 Hou 等出版者全文、Feng 等 EPMC 全文和 Zhou 等作者稿；分记环境温度、本体热电偶与有限的固定质量对照。Feng 论文的文末第 50 条引向 Liu 论文。 |
| `robotics 3-axis tactile sensor "temperature" "dataset" force measurements repository`、`"curvature-aware" "tactile" "calibration" Cornell Haptics 2026` | 获取 Cornell 官方仓库及 IEEE 摘要。GitHub 默认分支为 master；按提交 7d321a0d…重新取 commit 所指的 tree，相应 41 个下载文件的 blob SHA-1 均与清单一致。直接取 main 或 README.md 大写均不适用于该版本。 |
| 历史近邻与排除 | 过往已分析 iRonCub、openFT、EventTouch及前一轮 Hamburg BioTac。公开网页命中未能证实含本体温度的候选（如只列六轴力和姿态的 Zenodo 数据）未登记作热漂移测量。未向作者发起私下申请。 |
 
GitHub 检索以项目父提交 `0b8440df47e480d84147cef4e98151c092f724d2` 为边界，正式跨轮判定见本批根目录的历史排重记录。出版物和其仓储对象按不同证据层级登记。JPL 和 Kim 的既有论文从来源版本延伸；三篇天平论文与同名台架并不构成三次独立实测。

原始数字对象的 SHA-256 及固定地址见 [获取记录](source-receipts.csv)。版权和可分享范围按具体材料标在 [数据目录](sources.csv)。JPL 无独立数据许可证，原稿标有保留所有权利。Liu 论文标注 CC BY-NC-ND 4.0，原工作簿和图请循出版者链接读取；仓库中的计算结果为自算的误差、组数、范围和一致性检验。Cornell 仓库根许可证为 MIT，数据文件未另附专门许可，仓库只提供派生的文件／步／窗口汇总。
