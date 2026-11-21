# 限制工况与独立力矩基准

本组记录服务于 G1 的闭环执行器辨识。全文中的台架基准、公开文件清单、逐样本数据具有不同的证据用途。该组未验证同时含厂商关节力矩、独立外部测量和试验限幅标签的原始数值记录。

## 检索与复核

2026-11-21 UTC，使用免费网页检索及公开 GitHub 文件接口，从串联弹性执行器试验台、可变阻抗执行器和可穿戴机器人向作者代码及数据记录追踪。以下为实际查询的可复用摘录。

| 检索式或定向复核 | 结果 |
| --- | --- |
| `Chen Casas Lum "5.5 Nm" "5.6 Nm" 0.01 chirp end stops ATI Gamma FE and SP bandwidth` | 追到 PMC 作者稿中外部传感器位置、两个幅值与物理止挡条件。 |
| `"Solidworks model and system identification data" Dyrac Aiple files friction torque 4TU data supplementary zip` | 核对 TU Delft 数据记录的日期、DOI 和原型性能。DOI 落地页和旧 4TU 文件页本轮没有返回文件表。 |
| `Dyrac variable impedance actuator Aiple Schiele physical stiffness damping identification dynamic robotic actuator paper DOI 50 ms rad/s 16 313` | 打开 arXiv v2，核对图 10–14 的输出轴传感器、简化方法与检测量程。 |
| `"10.5281/zenodo.22108526" license Creative Commons data Flack` | 核对 Zenodo 五条文件与发布方 MD5，Rights 栏未显示许可名称。GitHub 固定版 README、配置和分段代码给出处理规则。 |
| PMC11896670 全文内查找 `Data availability statement`，读图 6 与 §§2.3.2–2.3.3 | 回溯输出传感器的独立校准与齿轮箱双传感器试验。原始数据需联系作者。 |
| `ppably/SEA-Testbed` README 及文件史 | 静态刚性连接时使用外部力矩传感器，动态试验会移除它。作者公开论文，未发布其工程源码和 CAD。该仓库不能验证动态双传感器日志。 |

## 使用边界

- `shaft-files.csv` 把 Zenodo 的文件清单与固定版本 MATLAB 配置按文件名连接。两处公布的轴长有差异，因此保留原列名与两个数值。同一数值如 470 mm 也按同样规则记录。自由长度来自配置，MB 是页面显示的近似值。MD5 由发布方提供，本轮未重新计算。[数据](https://zenodo.org/records/22108526) · [配置](https://github.com/J-Flack/Coiling-from-Vicon-Markers/blob/f1fe148f54725211ba5e06b3e60e2907c1b136b9/coiling/coil_config.m)
- Flack 的三次慢速重复和五种轴对应 15 个作者配置的试验单元。代码生成的结果 CSV 与原始 MAT 属于不同层次。此处只保存五个源文件的信息。[处理程序](https://github.com/J-Flack/Coiling-from-Vicon-Markers/blob/f1fe148f54725211ba5e06b3e60e2907c1b136b9/README.md)
- Aiple 的另一数据记录 DOI 10.4121/13625411 研究人通过双边触觉装置操纵虚拟工具，把它排除在物理原型轴台架数据之外。[目录](https://doi.org/10.4121/13625411)
- Pably 还报告驱动轴柔顺性和通信延迟对装置的影响。静、动态配置的差异解释了为什么该试验台的论文不能补齐本次要求的同一动态工况下双路力矩。[固定版作者说明](https://github.com/ppably/SEA-Testbed/blob/49371e92cb68228be8d3fd7aaede526bb4390f18/README.md)

Dyrac 的 CAD 与辨识数据此前已完成 24 个输入文件的校验。本批将目录作为论文交叉引用保存，数据来源计数沿用此前批次。[既有文件证据](https://github.com/hengyizang/lunwen/blob/103ca4b1128171e3b808fe56082bf65630d6ff14/projects/my-phd/evidence/g1-collection/follow-ups/2026-11-21-drive-current-and-feedback/sea/dyrac-source.json)
