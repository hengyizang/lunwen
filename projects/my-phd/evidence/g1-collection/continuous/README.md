# G1 持续自动文献与数据检索及清洗目录（AI + 机械 / 机器人 / 机电一体化 / 智能制造）

- 本目录由本地自动轮询器 (`g1_runner.py`) 以 **CNY 0** 付费调用（仅开放学术/数据集 API）持续维护，严格与基线冻结目录 [2026-11-21](../2026-11-21/README.md) 隔离且跨库去重。
- 覆盖范围：腕部力矩/接触装配（R1）、执行器受限飞行控制（R2）、多机器人协同与通信（R5），以及所有 **AI + 机器人/具身智能、机械工程物理建模/FEM/CFD/PINN、机电一体化与 PHM 故障诊断、智能制造与增材/CNC 加工、数字孪生与智能调度**。
- 原始数据集仅下载至 Git 仓库外的 `raw-staging/` 进行 SHA-256 / MD5 校验与确定性清洗，不向仓库上传原始二进制数据或归档。
- G1 选题仍保持待人工决策状态（`state/run.json` 未被自动推进）。

## 累计产出概览

- **已完成轮次**：15
- **最近更新时间 (UTC)**：2026-11-21T08:39:11Z
- **累计净新增文献** (`literature-new.csv`)：1405 条（已与基线 15,910 条去重）
- **累计净新增数据集** (`datasets-new.csv`)：872 个（已与基线 191 个去重）
- **累计开放阅读队列** (`reading-queue-new.csv`)：1275 条
- **累计已完成确定性清洗数据集**：24 个
- **云端 `[research-cloud]` 自动调度门禁**：`skipped_baseline_checkpoint_error: unsupported checkpoint file requires an explicit storage plan: evidence/g1-collection/2026-11-21/audit/SHA256SUMS`

## 学科领域分布（确定性关键词分流，非人工终审）

| 领域标签 | 累计文献数 | 累计数据集数 |
|---|---:|---:|
| `R1_Force_Contact` | 64 | 47 |
| `R2_Aerial_Actuator` | 169 | 37 |
| `R5_MultiRobot_Comm` | 116 | 32 |
| `Robotics_Embodied` | 423 | 266 |
| `Mechanical_Physics_AI` | 413 | 370 |
| `Mechatronics_PHM_Control` | 353 | 274 |
| `Smart_Manufacturing` | 196 | 198 |
| `Smart_Factory_DigitalTwin` | 139 | 62 |
| `R1` | 34 | 0 |
| `Adjacent` | 54 | 0 |
| `R2` | 37 | 0 |
| `R5` | 5 | 0 |
| `R1_force_truth` | 0 | 83 |
| `R5_packet_timing_aoi` | 0 | 69 |
| `R2_actuator_saturation` | 0 | 16 |

## 主要索引文件

- [净新增文献总表 (literature-new.csv)](literature-new.csv)
- [净新增数据集总表 (datasets-new.csv)](datasets-new.csv)
- [净新增开放阅读队列 (reading-queue-new.csv)](reading-queue-new.csv)
- [轮次队列与状态 (queue-state.json)](queue-state.json)

## 最近已校验并确定性清洗的公开数据集（最多显示最近 25 个）

| Slug | 名称 | DOI / 入口 | 清洗模式 | 行数 | 原始文件 SHA-256 (前12位) | 清洗表 / 来源 / 脚本 |
|---|---|---|---|---:|---|---|
| `figshare-31990188-multi-sensor-dataset-of` | Multi-sensor dataset of a tendon-driven continuum robot in dynamic... | 10.6084/m9.figshare.31990188.v3 | `summary_table` | 16 | `4e491bf194da` | [CSV](data/figshare-31990188-multi-sensor-dataset-of-cleaned.csv) · [JSON](data/figshare-31990188-multi-sensor-dataset-of-provenance.json) · [PY](data/derive_figshare_31990188_multi_sensor_dataset_of.py) |
| `figshare-32221713-quip-experimental-design` | QuIP: Experimental Design for Expensive Simulators with Many Qualit... | 10.6084/m9.figshare.32221713.v2 | `summary_table` | 42 | `bf8eb4a184c2` | [CSV](data/figshare-32221713-quip-experimental-design-cleaned.csv) · [JSON](data/figshare-32221713-quip-experimental-design-provenance.json) · [PY](data/derive_figshare_32221713_quip_experimental_design.py) |
| `dataverse-cc355j-experiment-dataset-for-t` | Experiment dataset for the journal - "A Robot for Overground Physic... | 10.7910/dvn/cc355j | `summary_table` | 44 | `416df3a23bd6` | [CSV](data/dataverse-cc355j-experiment-dataset-for-t-cleaned.csv) · [JSON](data/dataverse-cc355j-experiment-dataset-for-t-provenance.json) · [PY](data/derive_dataverse_cc355j_experiment_dataset_for_t.py) |
| `dataverse-idxscu-replication-data-for-old` | Replication Data for: Older Adults' Acceptance of a Robot for Partn... | 10.7910/dvn/idxscu | `summary_table` | 27 | `c473e00f7672` | [CSV](data/dataverse-idxscu-replication-data-for-old-cleaned.csv) · [JSON](data/dataverse-idxscu-replication-data-for-old-provenance.json) · [PY](data/derive_dataverse_idxscu_replication_data_for_old.py) |
| `dataverse-r0ozel-when-travel-meets-robots` | When travel meets robots: The role of embedding trust | 10.7910/dvn/r0ozel | `cleaned_rows` | 402 | `5dfc576eab09` | [CSV](data/dataverse-r0ozel-when-travel-meets-robots-cleaned.csv) · [JSON](data/dataverse-r0ozel-when-travel-meets-robots-provenance.json) · [PY](data/derive_dataverse_r0ozel_when_travel_meets_robots.py) |
| `figshare-32308911-paper-information-fault` | Paper information: Fault Severity Classification in Gearboxes Using... | 10.6084/m9.figshare.32308911.v2 | `cleaned_rows` | 83 | `08e6e869500f` | [CSV](data/figshare-32308911-paper-information-fault-cleaned.csv) · [JSON](data/figshare-32308911-paper-information-fault-provenance.json) · [PY](data/derive_figshare_32308911_paper_information_fault.py) |
| `figshare-32141986-brac-act-supporting-data` | BRAC-ACT Supporting Data and Scripts for Long-Horizon Traditional T... | 10.6084/m9.figshare.32141986.v1 | `summary_table` | 14 | `acedb8161340` | [CSV](data/figshare-32141986-brac-act-supporting-data-cleaned.csv) · [JSON](data/figshare-32141986-brac-act-supporting-data-provenance.json) · [PY](data/derive_figshare_32141986_brac_act_supporting_data.py) |
| `dataverse-c4ydif-results-of-the-graph-and` | Results of the graph and heuristic based topology optimization for... | 10.7910/dvn/c4ydif | `cleaned_rows` | 179 | `3d87bd2f2e3f` | [CSV](data/dataverse-c4ydif-results-of-the-graph-and-cleaned.csv) · [JSON](data/dataverse-c4ydif-results-of-the-graph-and-provenance.json) · [PY](data/derive_dataverse_c4ydif_results_of_the_graph_and.py) |
| `dataverse-ifhd40-replication-data-for-qua` | Replication Data for: Quantum Optimization and Reinforcement Learni... | 10.7910/dvn/ifhd40 | `summary_table` | 13 | `127ac1e02665` | [CSV](data/dataverse-ifhd40-replication-data-for-qua-cleaned.csv) · [JSON](data/dataverse-ifhd40-replication-data-for-qua-provenance.json) · [PY](data/derive_dataverse_ifhd40_replication_data_for_qua.py) |
| `dataverse-ud54yb-moon-wreckers-planetary` | Moon Wreckers Planetary Rover Driving Status Anomaly Detection Dataset | 10.7910/dvn/ud54yb | `summary_table` | 84 | `a86c89f00174` | [CSV](data/dataverse-ud54yb-moon-wreckers-planetary-cleaned.csv) · [JSON](data/dataverse-ud54yb-moon-wreckers-planetary-provenance.json) · [PY](data/derive_dataverse_ud54yb_moon_wreckers_planetary.py) |
| `figshare-35055502-processed-data-supportin` | Processed data supporting “Complex Damage Identification of Jacket... | 10.6084/m9.figshare.35055502.v1 | `summary_table` | 37 | `d46a127a1fb7` | [CSV](data/figshare-35055502-processed-data-supportin-cleaned.csv) · [JSON](data/figshare-35055502-processed-data-supportin-provenance.json) · [PY](data/derive_figshare_35055502_processed_data_supportin.py) |
| `figshare-33578671-source-data-for-tecobot` | Source data for TeCoBot, A Tensegrity-based modular Continuum robot | 10.6084/m9.figshare.33578671.v2 | `summary_table` | 11 | `db4cd6087b1a` | [CSV](data/figshare-33578671-source-data-for-tecobot-cleaned.csv) · [JSON](data/figshare-33578671-source-data-for-tecobot-provenance.json) · [PY](data/derive_figshare_33578671_source_data_for_tecobot.py) |
| `dataverse-gddmsa-enlarging-error-detectio` | Enlarging Error Detection Threshold of IMU-based Hand Tracking in V... | 10.7910/dvn/gddmsa | `summary_table` | 30 | `5bcde499216d` | [CSV](data/dataverse-gddmsa-enlarging-error-detectio-cleaned.csv) · [JSON](data/dataverse-gddmsa-enlarging-error-detectio-provenance.json) · [PY](data/derive_dataverse_gddmsa_enlarging_error_detectio.py) |
| `dataverse-wrctu4-soil-hydraulic-parameter` | Soil hydraulic parameters for "Analyzing dual porosity in soil hydr... | 10.7910/dvn/wrctu4 | `cleaned_rows` | 211 | `4310d567b54e` | [CSV](data/dataverse-wrctu4-soil-hydraulic-parameter-cleaned.csv) · [JSON](data/dataverse-wrctu4-soil-hydraulic-parameter-provenance.json) · [PY](data/derive_dataverse_wrctu4_soil_hydraulic_parameter.py) |
| `dataverse-ckliy1-perception-and-acoustic` | Perception and acoustic data with R scripts | 10.7910/dvn/ckliy1 | `summary_table` | 77 | `408482190050` | [CSV](data/dataverse-ckliy1-perception-and-acoustic-cleaned.csv) · [JSON](data/dataverse-ckliy1-perception-and-acoustic-provenance.json) · [PY](data/derive_dataverse_ckliy1_perception_and_acoustic.py) |
| `dataverse-myrxr8-autonomous-integrated-sy` | Autonomous Integrated Systems in Archaeology | 10.7910/dvn/myrxr8 | `summary_table` | 9 | `5749db2a529a` | [CSV](data/dataverse-myrxr8-autonomous-integrated-sy-cleaned.csv) · [JSON](data/dataverse-myrxr8-autonomous-integrated-sy-provenance.json) · [PY](data/derive_dataverse_myrxr8_autonomous_integrated_sy.py) |
| `dataverse-z1ohnl-replication-data-for-rol` | Replication Data for: Role of single chemical heterogeneities in ge... | 10.7910/dvn/z1ohnl | `summary_table` | 12 | `ff5918e2ede4` | [CSV](data/dataverse-z1ohnl-replication-data-for-rol-cleaned.csv) · [JSON](data/dataverse-z1ohnl-replication-data-for-rol-provenance.json) · [PY](data/derive_dataverse_z1ohnl_replication_data_for_rol.py) |
| `dataverse-ekpfj2-replication-data-for-art` | Replication Data for: Artificial tactile and proprioceptive feedbac... | 10.7910/dvn/ekpfj2 | `cleaned_rows` | 14 | `24d19e803082` | [CSV](data/dataverse-ekpfj2-replication-data-for-art-cleaned.csv) · [JSON](data/dataverse-ekpfj2-replication-data-for-art-provenance.json) · [PY](data/derive_dataverse_ekpfj2_replication_data_for_art.py) |
| `dataverse-k7igab-replication-data-for-ear` | Replication Data for: Early attentional processing and cortical rem... | 10.7910/dvn/k7igab | `summary_table` | 14 | `e3205034d9b3` | [CSV](data/dataverse-k7igab-replication-data-for-ear-cleaned.csv) · [JSON](data/dataverse-k7igab-replication-data-for-ear-provenance.json) · [PY](data/derive_dataverse_k7igab_replication_data_for_ear.py) |
| `figshare-34476927-data-sheet-1-a-vision-ba` | Data Sheet 1_A vision-based closed-loop framework for adaptive ergo... | 10.3389/frobt.2026.1948863.s003 | `cleaned_rows` | 30 | `45ac02efcb33` | [CSV](data/figshare-34476927-data-sheet-1-a-vision-ba-cleaned.csv) · [JSON](data/figshare-34476927-data-sheet-1-a-vision-ba-provenance.json) · [PY](data/derive_figshare_34476927_data_sheet_1_a_vision_ba.py) |
| `figshare-34476945-data-sheet-2-a-vision-ba` | Data Sheet 2_A vision-based closed-loop framework for adaptive ergo... | 10.3389/frobt.2026.1948863.s002 | `cleaned_rows` | 30 | `8afa86e63d0a` | [CSV](data/figshare-34476945-data-sheet-2-a-vision-ba-cleaned.csv) · [JSON](data/figshare-34476945-data-sheet-2-a-vision-ba-provenance.json) · [PY](data/derive_figshare_34476945_data_sheet_2_a_vision_ba.py) |
| `figshare-34845711-hrc-architecture-3-x-raw` | HRC-Architecture 3.x: Raw, Hash-Manifested Run Records of the Pre-R... | 10.6084/m9.figshare.34845711.v1 | `summary_table` | 20 | `e20d46fa75ac` | [CSV](data/figshare-34845711-hrc-architecture-3-x-raw-cleaned.csv) · [JSON](data/figshare-34845711-hrc-architecture-3-x-raw-provenance.json) · [PY](data/derive_figshare_34845711_hrc_architecture_3_x_raw.py) |
| `dataverse-ueurvw-replication-data-for-mod` | Replication Data for: Modernising tactile acuity assessment; clinim... | 10.7910/dvn/ueurvw | `summary_table` | 150 | `8c989a7068b7` | [CSV](data/dataverse-ueurvw-replication-data-for-mod-cleaned.csv) · [JSON](data/dataverse-ueurvw-replication-data-for-mod-provenance.json) · [PY](data/derive_dataverse_ueurvw_replication_data_for_mod.py) |
| `dataverse-kkejzf-the-event-related-potent` | The event-related potential of tactile stimulus recognition and bra... | 10.7910/dvn/kkejzf | `cleaned_rows` | 57 | `a587c1166093` | [CSV](data/dataverse-kkejzf-the-event-related-potent-cleaned.csv) · [JSON](data/dataverse-kkejzf-the-event-related-potent-provenance.json) · [PY](data/derive_dataverse_kkejzf_the_event_related_potent.py) |

## 最近轮次记录（最多显示最近 25 轮）

| 轮次 | UTC 时间 | 主题批次 | 净增文献 | 净增数据集 | 新增清洗表 | 审计文件 |
|---:|---|---|---:|---:|---:|---|
| 1 | 2026-11-21T07:31:26Z | R1/R2/R5 Gap Search + ICRA 2025 | +36 | +34 | +0 | [round-01-audit.json](rounds/round-01-audit.json) |
| 2 | 2026-11-21T07:37:17Z | R1 Contact Assembly & Tactile + AAAI 2025 Robotics + Short Dataset Queries | +52 | +85 | +2 | [round-02-audit.json](rounds/round-02-audit.json) |
| 3 | 2026-11-21T07:44:04Z | Broad Engineering R3: R2_Aerial_Actuator / R5_MultiRobot_Comm | +94 | +107 | +3 | [round-03-audit.json](rounds/round-03-audit.json) |
| 4 | 2026-11-21T07:45:57Z | Broad Engineering R4: R5_MultiRobot_Comm | +93 | +92 | +2 | [round-04-audit.json](rounds/round-04-audit.json) |
| 5 | 2026-11-21T07:49:14Z | Broad Engineering R5: Robotics_Embodied | +118 | +112 | +3 | [round-05-audit.json](rounds/round-05-audit.json) |
| 6 | 2026-11-21T07:54:02Z | Broad Engineering R6: Robotics_Embodied / Mechanical_Physics_AI | +111 | +67 | +2 | [round-06-audit.json](rounds/round-06-audit.json) |
| 7 | 2026-11-21T07:59:03Z | Broad Engineering R7: Mechanical_Physics_AI | +119 | +57 | +2 | [round-07-audit.json](rounds/round-07-audit.json) |
| 8 | 2026-11-21T08:04:25Z | Broad Engineering R8: Mechanical_Physics_AI / Mechatronics_PHM_Control | +144 | +84 | +0 | [round-08-audit.json](rounds/round-08-audit.json) |
| 9 | 2026-11-21T08:09:11Z | Broad Engineering R9: Mechatronics_PHM_Control | +97 | +42 | +1 | [round-09-audit.json](rounds/round-09-audit.json) |
| 10 | 2026-11-21T08:15:25Z | Broad Engineering R10: Smart_Manufacturing | +106 | +75 | +0 | [round-10-audit.json](rounds/round-10-audit.json) |
| 11 | 2026-11-21T08:19:12Z | Broad Engineering R11: Smart_Manufacturing / Smart_Factory_DigitalTwin | +148 | +38 | +1 | [round-11-audit.json](rounds/round-11-audit.json) |
| 12 | 2026-11-21T08:24:12Z | Broad Engineering R12: Smart_Factory_DigitalTwin / R1_Force_Contact | +91 | +59 | +0 | [round-12-audit.json](rounds/round-12-audit.json) |
| 13 | 2026-11-21T08:29:10Z | Broad Engineering R13: R1_Force_Contact (2026) | +59 | +46 | +3 | [round-13-audit.json](rounds/round-13-audit.json) |
| 14 | 2026-11-21T08:34:04Z | Broad Engineering R14: R2_Aerial_Actuator (2026) | +85 | +0 | +3 | [round-14-audit.json](rounds/round-14-audit.json) |
| 15 | 2026-11-21T08:39:11Z | Broad Engineering R15: R2_Aerial_Actuator / R5_MultiRobot_Comm (2026) | +52 | +0 | +2 | [round-15-audit.json](rounds/round-15-audit.json) |
