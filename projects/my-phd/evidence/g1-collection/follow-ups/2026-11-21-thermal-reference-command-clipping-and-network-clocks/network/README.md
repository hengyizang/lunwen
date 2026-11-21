# 车辆编队接收、控制状态与轴扭矩请求

2026-11-21 检查两个美国交通部免费数据源。IHP2 提供多车 ROS1 原始日志，CARMA2 提供 13 次试验的车辆通道宽表。两者来自不同项目代际、不同年份，本文只在各自原始记录内关联事件。

## IHP2 的应用消息与接收方控制状态

逐块解压原始 ZIP 里的 20 个 ROS1 bag。每个连接解出的消息数均与 bag 索引一致，共 9,894,180 条。归档自带的 Filename_ReportImage_Mapping.xlsx 将 bag 对应至 7 组试验图。逐文件 SHA-256、控制状态发布者、系统版本消息和通道行数见 ihp2-bag-coverage.csv。20 个 bag 的该状态发布者均为 /guidance/platoon_control，13 个 bag 记录了按车区分的 CARMA 4.2.0 版本，另 7 个缺少版本消息。

1. **跨车发送与接收。** 在同一组试验的有向车对上，核对发送者、接收者、动态 BSM ID、计划 ID、消息生成毫秒、策略及完整参数。对广播接收者空串与 UNSET、动态 BSM ID 空串与 00000000 分别统一，保留全部其余字段。要求两边各有唯一出现。38 组有向车对得到 45,873 对，七字段原样完全相同的计数为零。11,474 对的接收方 bag 时刻早于发送方 bag 时刻。ihp2-operation-matches.csv 给出分母与各方向分布。图组 7 与 10 的 Black Pacifica 文件在文件名上显示另一运行编号或日期，与其他车辆的八个方向均无匹配。因此不据此估算丢包率。
2. **接收后软件状态变更。** 两条相邻接收方控制消息都处于 follower 状态，且领车身份均与 STATUS 发送者相同，得到 12,134 对。进一步要求半开时间区间 (前一控制消息，当前控制消息] 内只有同一领车的一条 CMDSPEED 状态消息，保留 11,220 对。其中 2,696 对领车速度字段相较前值发生变化，且新值与收到的 CMDSPEED 转成 float32 后精确相等。同一接收端从消息入 bag 到这条控制状态入 bag 的中位间隔为 61.706 ms，范围 0.031–140.285 ms。
3. **战略输出到控制输出。** CARMA 4.2.0 的 platoonInfo_cb 复制战略状态，将本车命令改写为本地值，并在 actual_gap 大于 5 时减去 5 m。按该映射规整两侧原始负载，对其余全部字节计算 SHA-256。2,696 对都在同车战略与控制输入/输出日志中取得一对一对应；2,629 对按接收、战略输出、控制输出顺序入 bag，另 67 对的控制输出在战略输出之前入 bag。战略到控制的记录时间差中位数 0.061 ms。各行取本车的 ROS bag 记录时钟。车辆时钟校准、操作系统入队时间和无线链路单程时延均不能从该值独立辨识。[CARMA tag carma-system-4.2.0 的回调实现](https://github.com/usdot-fhwa-stol/carma-platform/blob/c3b67662e8a1db655f1d6bdf4c9d1d606402e619/platooning_control/src/platoon_control.cpp#L212-L244)
4. **同车反馈。** ihp2-follower-updates.csv 每行保留状态消息前后的相邻通道观测，前、后各限定 200 ms。ctrl 为控制请求速度，hw_cmd 为硬件接口的仲裁请求速度，measured_speed 为硬件接口发布的 Twist.linear.x，三者以 m/s 表示。两路 pedal feedback 是 0–1 的踏板反馈。对可配对通道，以原始浮点值判断第一条后续读数是否不同于前值。2,570 个可配对样本中，2,372 次随后硬件接口请求速度改变，1,376 次油门踏板读数改变，1,320 次制动踏板读数改变；2,696 次可配对车速中有 2,581 次改变。车辆可能正在跟踪更早的命令，且周期性反馈天然会变化；此列不能单独确定这一次接收触发了踏板或车速变化。
5. **双向协商。** ihp2-four-event-handshakes.csv 给出 86 次按同一非空计划 ID 和反向端点闭合的请求—应答，双方的请求生成时间、策略、类型和应答的已解析业务字段一致。请求方同钟收发差中位数 20.346 ms，范围 0.912–546.554 ms；应答方同钟收发差中位数 0.689 ms，范围 0.006–15.184 ms。23 次接受，63 次拒绝。79 次有至少一个负的跨车单程时间差。请求的全部尾部字节在 20 次中相同，其余记录只按上述可核对字段对应。ihp2-handshake-coverage.csv 给出每个方向的候选和匹配分母。两个同钟指标都是应用层记录间隔。

## CARMA2 的样本清理与扭矩命令边界

官方导出有 254 列、142,274 行。按 RunNo 和 Elapsed_Time 组成 69,613 个时间格。4,203 格被重复记录，每格最多 32 行，这些记录全部属于运行 3、4、6。在每一个重复格内，剔除 5 个 runid_* 标签列后逐单元完全一致，其余包括传感、时间和控制列都相同。使用唯一格后再统计车辆与模式，避免同一时刻被放大。carma2-bin-quality.csv 给出逐次试验分母。

carma2-command-audit.csv 保留所有有数据的车辆，附 Testing Logs 官方角色、应用、路线及程序。分析已列明的参试车应筛选非空 logged_role；聚焦编队时，再按 application 包含 platooning 筛选。这样得到 188,865 个可用的 P29 轴扭矩请求车时刻，其中 70,826 个值为 −500 N·m，63 个值高于 2,000 N·m，最高 2,040 N·m，低于 −500 的值为零。若进一步筛 recorded_command_mode 等于原始代码 2，对应 150,053 个请求值、36,668 个 −500 值和全部 63 个 >2,000 值。数据字典将模式列标作 bool，实测取值为空、0、2，本批保留原码。单一试验报告图 19 所示的上限不能外推至整批数据。大量 −500 样值本身不足以确定饱和持续时间、控制器积分饱和或实际轴端输出。

P29 与 P5 immediate/predicted 都由官方词典标注为轴扭矩命令类量，单位 N·m。injected 的原始字典单位是 none，仅做数值与覆盖核对。GPS 速度来自独立测量系统，单位 m/s；acceleration 为 P29 实车加速度，单位 m/s²。各字段有独立有效计数，缺值不补零。brake 为制动灯标志。表中的 observed_bins 是每车每模式至少一个选定字段有值的格数，跨车累加的分母是车时刻数。

## 来源、许可和复算

sources.json 给出两个 DOI、下载端点、版本、大小、SHA-256 和数据许可。literature.csv 含三份读过全文的技术报告及一篇只核对书目和摘要的同行评审论文。citation-edges.csv 给出年报参考文献 56、57 的出处。search-log.json 保存公用检索接口、查询、结果与历史去重键。

IHP2 的 DataCite 记录标为美国政府公共领域。请引用 Jiaqi Ma 与 Leidos (2024)，Connected Automated Vehicles – Integrated Highway Prototype II (IHP2)，通过 ITS DataHub 获取，访问日期 2026-11-21。[IHP2 源数据](https://doi.org/10.21949/1404196)

CARMA2 来源为 U.S. Department of Transportation (2018)，Cooperative Automated Research Mobility Applications (CARMA) 2，ITS DataHub，访问日期 2026-11-21。本批将原表按时间格去重，与官方角色表关联，并生成两个汇总 CSV。这两个 carma2-*.csv 派生表以 CC BY-SA 3.0 Unported 发布。原始 CSV、工作表、bag 和报告 PDF 均由来源方提供。[CARMA2 源数据](https://doi.org/10.21949/1504485) · [署名—相同方式共享 3.0](https://creativecommons.org/licenses/by-sa/3.0/)

Python 3.11 或更高版本复算示例，IHP2 需要 lz4 和 openpyxl，CARMA2 角色表需要 openpyxl。两个脚本在处理开始前校验原始文件哈希。

```sh
python derive_ihp2.py cavihp.zip OUTPUT_DIR
python derive_carma2.py rows.csv Testing_Logs_-_CARMA_2.xlsx OUTPUT_DIR
```
