# R2 检索、取舍与版本核验

2026-11-22 UTC。首先检索闭环电机指令、限幅与独立测量的组合，再从技术邻居、参考文献和作者提供的数据入口追查。出发查询包括以下字符串。

- `"dataset" motor actuator "anti-windup" servo experimental data Zenodo`
- `series elastic actuator torque tracking experiments step measured torque reference dataset zenodo csv robotics torque bench`
- `data closed loop DC motor voltage speed PID setpoint saturation dataset Mendeley data experimental`
- `BAM backdrivability actuator model sim2real BAM robot actuators testbench motor identification Feetech open dataset Placo Rhoban motor test bench PWM load`
- `"Dynaban" open source alternative firmware Dynamixel PDF torque tracking feed forward Fabre 2016`
- `"torque tracking" "dataset" robot actuator series elastic measured torque figshare zenodo Dryad prosthesis exoskeleton motor torque reference open dataset`

Mendeley 5xvg43r9r8、2rkpsss6fd，Zenodo 17688566、21233963、3627901、7240050，以及 Neural Actuation Dataset、Dryad z34tmpgks 和 UART 回差试验文章均已出现在 G1。它们未作为本批新增。BAM 命中后，核对了公开作者文档、Crossref 记录和正式论文参考文献。向后追查到 Fabre、Wang、Sihite、Zhu、Ponce Quiroga；通过 Sihite 追查到 RAPID。Sun 等引用的 Malzahn 等力矩带宽论文已在历史中，有向边保留，未新增书目。正式论文和 arXiv v1–v4 合并为一条。子目录预检针对 1,374 个明文文件，以 DOI、arXiv、规范化题名、仓库和文件别名检索 14 条入选记录，未命中。批次总表递归解开历史提供方 JSON 后找到了 BAM 论文的 DOI；该文属于历史已发现、本次首次单独列项并核读全文的文献。Dynaban 的 “RoboCup 2016” 别名命中通用会议名，经题名和 DOI 核对，所命中条目属于其他作品。

## 可复查的来源路径

- BAM 官方文档给出物料、作者和原始数据入口，目录快照固定至 `b9e11118e17fe8ec803d430202f6fcf31d57901e`。桶 API 还列出文档表格未链接的 XL320 实测文件，已打开并纳入。该桶的五个压缩文件按各自 SHA-256 固定，并作为同一数据来源计数。对全部十个压缩包中保留的 1,912 个原始轨迹 JSON 逐文件计算 SHA-256，共有 1,912 个不同摘要。[官方目录](https://github.com/Rhoban/bam/blob/b9e11118e17fe8ec803d430202f6fcf31d57901e/docs/usage/actuators.rst) · [桶清单](https://huggingface.co/api/buckets/Gregwar/bam_data/tree)
- XL330 的 `convert_xl330_pwm_to_duty` 及记录循环将 Present PWM 保存在 `load`。MX 的同名字段读取 Present Load；STS3215 记录程序将其置零。对照生产商手册区分寄存器语义。[XL330 记录程序](https://github.com/Rhoban/bam/blob/b9e11118e17fe8ec803d430202f6fcf31d57901e/bam/dynamixel/record.py#L44-L48) · [Feetech 记录程序](https://github.com/Rhoban/bam/blob/b9e11118e17fe8ec803d430202f6fcf31d57901e/bam/feetech/record.py#L91-L104) · [ROBOTIS Present PWM](https://emanual.robotis.com/docs/en/dxl/x/xl330-m288/#present-pwm124) · [MX Present Load](https://emanual.robotis.com/docs/en/dxl/mx/mx-64/#present-load)
- 顺着作者实现与贡献者的独立发布逐项核验。ST3025 的采集程序读回扭矩限值，未将标题里的扭矩指标赋给逐行 `load`。STS3215-12V 的发布描述、97 个轨迹文件及固件加速度设置说明，与主桶 7.4 V 版本分开登记。[ST3025 采集器](https://github.com/i1Cps/duck_mini_pro_headless/blob/7a91e209bce7a698e2bce1bcc77b97b9d84d917f/bam_bench/record.py) · [12 V 独立采集及说明](https://github.com/Rhoban/bam/pull/20)
- HLS2915 的 PR 正文保留旧的单一负载/电流控制说明，正文指向的旧压缩文件名返回 404。通过同一贡献者的数据分支树找到实际发布的 `feetech_hls2915_raw.zip`。对应版本 README、全部 64 个记录中的 `control_mode` 和采集程序一致，实际是四种物理摆载、位置模式。证据等级只按已打开的版本登记。[旧说明](https://github.com/Rhoban/bam/pull/15) · [不可变数据分支](https://github.com/Seamus-Z/bam/tree/9b4342661ce56e7ddb9c5331d2a1091434c35fcd) · [换算逻辑](https://github.com/Seamus-Z/bam/blob/77cb5528630df8cd7d75c4a01a4d1088d047609b/bam/feetech_hls/record.py#L172-L185) · [电流单位与标定](https://github.com/Seamus-Z/bam/blob/77cb5528630df8cd7d75c4a01a4d1088d047609b/bam/feetech_hls/driver.py#L69-L88)
- MD300 原始包内 README 定义电流、供电设置以及 raw/processed 关系。记录程序把计算得到的占空比写入 `duty_cycle` 并允许选择性额外读取实时 PWM。J288 的开发者明确说明回报力矩来自电流。[MD300 记录源代码](https://github.com/mangdangroboticsclub/bam/blob/2d1688ac59f3f3d0276ab4ff1645c93439394c8e/bam/mangdang/record.py#L24-L38) · [J288 测试条件](https://github.com/Rhoban/bam/pull/21)
- 按 DOI 从 Crossref 核对书目、引文与版本，再通过研究者/机构提供的 PDF 阅读方法、结果及限制。全文 SHA-256 为 BAM v4 `e549e0668e183c5a19cc89a638df111e292cb9e2a31442ad1c90b38f0d9774c9`、Dynaban `bfe9f8198e2a0bc7699c1a2d31f0481142d168278ffdc2855bef7a79b88bbedf`、drive/coast `6905984d9f126a7c8b5e7593a3c77d4446003e21d95b6542132dbe35686be71f`、Sun 等机构存本 `8e8bec17d4d3b57a3540a43cb139b1e97f9059ee796b919ae2eacc6855232957`。Sun 等论文页脚载明 CC BY 4.0 并给出 2025 年 2 月上线和 5 月期号；Crossref 的线上日期误差单独记于书目。可复查的全文 URL 列于 `literature.csv`。
