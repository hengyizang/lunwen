# 双臂接收时刻、转向动作与物理时钟校验

三个公开作者仓库提供不同的观测端点。以下目录固定原始版本，逐文件列出来源、字节数和 SHA-256。两个 GitHub 仓库的全部 Results 文件另与固定提交的 Git blob 标识比较。上游仓库未检出适用于原始测量的明确许可。本批提供原创统计和复算代码，原始文件可从各自发布者取得。[来源目录](sources.csv) · [文献与原文定位](literature.csv) · [文献版本校验](source-receipts.csv) · [有向引文](edges.csv)

## 两台机械臂是否按时收到共同动作目标

Aalborg 的两台 UR5e 传递网球。作者的控制器先确定共同的计划时刻，然后先后向两台机械臂发送目标。逐行读取全部 22 个 CSV，共 157,751 个双臂动作行对、315,502 个单臂四时刻记录以及 155,953 条主机时钟偏移估计。行对来自同一实验两台机械臂工作文件的动作序号，两端文件长度一致，且在每对记录中控制器均先发往第一台。文件未给出显式动作 ID。数据还包含按文件夹分开的 12 小时和链路未注明的早期试验，论文指定的图表来自两组 5.5 小时时段。[作者数据版本](https://bitbucket.org/mobiledevaau/grab-demo-1-timestamp/src/a751adce0c7e61b7879cb938749b0d87fcce8038/) · [数据清单](aalborg-file-inventory.csv)

- 论文的 5G 时段包含 21,655 次双臂动作。若以第一台机械臂的控制器发送时刻加上 20 ms 作为共同计划时刻，记录中有 4 次某一台接收超过这个时刻，两台各 2 次。以太网的 21,439 次均在计划时刻内。两臂接收时刻差的绝对值中位数分别为 1.3495 和 0.0932 ms。应用接收、等待目标时刻、向 RTDE 下发和物理动作之间仍有额外环节。[成对接收与期限](aalborg-paired-arrivals.csv) · [单臂四时刻统计](aalborg-arm-timing.csv)
- 论文使用 chronyc tracking 的 Last offset。5G 两臂文件中记录的取值范围分别为 −598.590 至 763.739 µs、−835.666 至 887.658 µs。偏移 CSV 每行只有一个值，没有采样时间戳，不能按行号把各主机偏移分配给具体动作。另一组 12 小时 5G 数据的两臂偏移文件仅有 28 和 20 行。论文 1.6 ms 的数字来自两个时钟估计的极值组合，现有文件无法验证两个机械动作起始时刻相差多少。[时钟表](aalborg-clock-offsets.csv) · [论文 §VI 及表 IV](https://vbn.aau.dk/ws/portalfiles/portal/772202637/synch_robotic_conrol_5G_edgecloud_aau.pdf)

## 车辆转向和视频反馈

卢森堡的两份研究来自同一团队，采用不同传感器、时钟配置和文件。早期研究用霍尔传感器检测两侧转向盘上的磁体通过。后续研究用两只陀螺仪检测转向运动起点，用 LED 与光敏三极管观测视频亮起，并通过 GNSS PPS 辅助对时。[早期数据](https://github.com/sntubix/m2m_latency/tree/0fd1d87fcec67798e0f01c07df3fac5308763e41) · [后续数据](https://github.com/sntubix/e2e_latency/tree/abdde3817cfdcff8818a64b58f437827ec19a599)

- 霍尔实验的 4 个转向文件有 276 对事件。另有两份各 3,599 行的两机时钟标定文件。共同参考模式的最大绝对偏差为 4.446208 ms，两机独立对时模式为 1.052160 ms。最小值依次为 258、256 ns，论文表 I 将这两个最小值依次列为 256、258 ns。文件中的毫秒偏移列取绝对值，另有带符号的纳秒原始列。静止车辆的 Wi-Fi 和 5G 转向时间中位数分别为 874.464977 和 930.607211 ms。[校准](hall-clock-calibration.csv) · [转向](hall-motion-timing.csv) · [清单](hall-file-inventory.csv)
- 陀螺仪实验的基线 100 行中，51 行的车端检测早于站端。动作起点相减时，带符号中位数为 −0.349477 ms；按照作者程序先取绝对值，中位数为 2.432698 ms。两端共置标定时的传感器差异不能直接当作单程网络传输。4G、5G 实测文件分别有 157 和 130 个六事件记录，校正 LED 触发间隔后，站端闭环中位数为 516.461179 和 498.470130 ms。两个文件各有一处站端起点没有递增，均按文件中的原有成对事件计算。[时序统计](vehicle-timing.csv) · [配对与顺序检查](vehicle-quality.csv)
- 后续版本另给出 212 个摄像头和显示器组合延迟，以及两份合计 31,215 帧的网络抓包。包记录仅汇总覆盖率和时长，无法凭这些包的时间戳将每一帧与转向检测一一关联。论文的独立 GNSS 时钟基线为作者报告值，Results 目录未单列逐次 GNSS 标定文件。[文件与摘要](vehicle-file-inventory.csv) · [抓包覆盖率](vehicle-capture-coverage.csv)

## 跨文献对照与复算

Calvo 等用同一示波器观察串口和多个接收端。表 2 的起止时间距离与表 4 的三接收端间离散度来自不同试验，按相同距离生成的 5 行对照保留了两个测量定义。对于 12 m，两个量相差 0.80 ms。Vargas Cruz 用 240 fps 录像另外观察了按键、底层控制器 LED 与轮子运动。在 22 次重复中，三种统计的近似中位数为 55 ms（ROS 命令至里程计）、62 ms（按键至 LED）、82 ms（按键至可见运动）。每个中位数都有自己的端点。[同距离示波器对照](xbee-scope-contrasts.csv) · [机器人试验，§5.2.5](https://essay.utwente.nl/fileshare/file/108544/vargas2025msc.pdf)

三个仓库的脚本按各自 README 下载的数据目录运行。四个脚本只需 Python 标准库。四时刻日志以十进制转换为整数纳秒再作差；Aalborg 的百分位使用最近秩，车辆表使用线性插值。结果中较多小数位用于对照计算，物理时间分辨率需由原始仪器和时钟测量决定。

```sh
python derive_aalborg.py PATH_TO_AALBORG_REPO output
python derive_hall.py PATH_TO_HALL_REPO output
python derive_vehicle.py PATH_TO_GYRO_REPO output
python derive_xbee.py PMC8587709.xml output
```
