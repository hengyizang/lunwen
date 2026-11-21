# G1 持续自动文献与数据检索及清洗目录（AI + 机械 / 机器人 / 机电一体化 / 智能制造）

- 本目录由本地自动轮询器 (`g1_runner.py`) 以 **CNY 0** 付费调用（仅开放学术/数据集 API）持续维护，严格与基线冻结目录 [2026-11-21](../2026-11-21/README.md) 隔离且跨库去重。
- 覆盖范围：腕部力矩/接触装配（R1）、执行器受限飞行控制（R2）、多机器人协同与通信（R5），以及所有 **AI + 机器人/具身智能、机械工程物理建模/FEM/CFD/PINN、机电一体化与 PHM 故障诊断、智能制造与增材/CNC 加工、数字孪生与智能调度**。
- 原始数据集仅下载至 Git 仓库外的 `raw-staging/` 进行 SHA-256 / MD5 校验与确定性清洗，不向仓库上传原始二进制数据或归档。
- G1 选题仍保持待人工决策状态（`state/run.json` 未被自动推进）。

## 累计产出概览

- **已完成轮次**：22
- **最近更新时间 (UTC)**：2026-11-21T09:14:08Z
- **累计净新增文献** (`literature-new.csv, literature-new-part-02.csv`)：2101 条（已与基线 15,910 条去重）
- **累计净新增数据集** (`datasets-new.csv`)：1090 个（已与基线 191 个去重）
- **累计开放阅读队列** (`reading-queue-new.csv`)：1879 条
- **累计已完成确定性清洗数据集**：45 个
- **云端 `[research-cloud]` 自动调度门禁**：`skipped_baseline_checkpoint_error: unsupported checkpoint file requires an explicit storage plan: evidence/g1-collection/2026-11-21/audit/SHA256SUMS`

## 学科领域分布（确定性关键词分流，非人工终审）

| 领域标签 | 累计文献数 | 累计数据集数 |
|---|---:|---:|
| `R1_Force_Contact` | 119 | 47 |
| `R2_Aerial_Actuator` | 344 | 38 |
| `R5_MultiRobot_Comm` | 239 | 35 |
| `Robotics_Embodied` | 782 | 273 |
| `Mechanical_Physics_AI` | 548 | 521 |
| `Mechatronics_PHM_Control` | 458 | 313 |
| `Smart_Manufacturing` | 212 | 273 |
| `Smart_Factory_DigitalTwin` | 147 | 63 |
| `R1` | 34 | 0 |
| `Adjacent` | 125 | 0 |
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
| `figshare-34476945-data-sheet-2-a-vision-ba` | Data Sheet 2_A vision-based closed-loop framework for adaptive ergo... | 10.3389/frobt.2026.1948863.s002 | `cleaned_rows` | 30 | `8afa86e63d0a` | [CSV](data/figshare-34476945-data-sheet-2-a-vision-ba-cleaned.csv) · [JSON](data/figshare-34476945-data-sheet-2-a-vision-ba-provenance.json) · [PY](data/derive_figshare_34476945_data_sheet_2_a_vision_ba.py) |
| `figshare-34845711-hrc-architecture-3-x-raw` | HRC-Architecture 3.x: Raw, Hash-Manifested Run Records of the Pre-R... | 10.6084/m9.figshare.34845711.v1 | `summary_table` | 20 | `e20d46fa75ac` | [CSV](data/figshare-34845711-hrc-architecture-3-x-raw-cleaned.csv) · [JSON](data/figshare-34845711-hrc-architecture-3-x-raw-provenance.json) · [PY](data/derive_figshare_34845711_hrc_architecture_3_x_raw.py) |
| `dataverse-ueurvw-replication-data-for-mod` | Replication Data for: Modernising tactile acuity assessment; clinim... | 10.7910/dvn/ueurvw | `summary_table` | 150 | `8c989a7068b7` | [CSV](data/dataverse-ueurvw-replication-data-for-mod-cleaned.csv) · [JSON](data/dataverse-ueurvw-replication-data-for-mod-provenance.json) · [PY](data/derive_dataverse_ueurvw_replication_data_for_mod.py) |
| `dataverse-kkejzf-the-event-related-potent` | The event-related potential of tactile stimulus recognition and bra... | 10.7910/dvn/kkejzf | `cleaned_rows` | 57 | `a587c1166093` | [CSV](data/dataverse-kkejzf-the-event-related-potent-cleaned.csv) · [JSON](data/dataverse-kkejzf-the-event-related-potent-provenance.json) · [PY](data/derive_dataverse_kkejzf_the_event_related_potent.py) |
| `figshare-35081113-hrc-architecture-3-1-raw` | HRC-Architecture 3.1: Raw, Hash-Manifested Run Records of the Publi... | 10.6084/m9.figshare.35081113 | `summary_table` | 34 | `4a56e090f3e5` | [CSV](data/figshare-35081113-hrc-architecture-3-1-raw-cleaned.csv) · [JSON](data/figshare-35081113-hrc-architecture-3-1-raw-provenance.json) · [PY](data/derive_figshare_35081113_hrc_architecture_3_1_raw.py) |
| `figshare-31558270-laser-powder-bed-fusion` | Laser Powder Bed Fusion of Carbon Nanotube (CNT)-Reinforced Nickel-... | 10.6084/m9.figshare.31558270.v2 | `summary_table` | 22 | `c6feed0cde5b` | [CSV](data/figshare-31558270-laser-powder-bed-fusion-cleaned.csv) · [JSON](data/figshare-31558270-laser-powder-bed-fusion-provenance.json) · [PY](data/derive_figshare_31558270_laser_powder_bed_fusion.py) |
| `figshare-34748238-temporal-information-con` | Temporal Information Continuity in Industrial Supervisory Robotics:... | 10.6084/m9.figshare.34748238.v1 | `summary_table` | 61 | `5a3d5977d938` | [CSV](data/figshare-34748238-temporal-information-con-cleaned.csv) · [JSON](data/figshare-34748238-temporal-information-con-provenance.json) · [PY](data/derive_figshare_34748238_temporal_information_con.py) |
| `dataverse-j6ktrs-the-role-of-awareness-on` | The role of awareness on motor-sensory temporal recalibration | 10.7910/dvn/j6ktrs | `cleaned_rows` | 14 | `f6308de1e39d` | [CSV](data/dataverse-j6ktrs-the-role-of-awareness-on-cleaned.csv) · [JSON](data/dataverse-j6ktrs-the-role-of-awareness-on-provenance.json) · [PY](data/derive_dataverse_j6ktrs_the_role_of_awareness_on.py) |
| `dataverse-qhfhyc-a-multi-sensory-inertial` | A Multi-Sensory Inertial Measurement Unit Dataset for Fetal Conditi... | 10.7910/dvn/qhfhyc | `summary_table` | 72 | `42a77bddfa85` | [CSV](data/dataverse-qhfhyc-a-multi-sensory-inertial-cleaned.csv) · [JSON](data/dataverse-qhfhyc-a-multi-sensory-inertial-provenance.json) · [PY](data/derive_dataverse_qhfhyc_a_multi_sensory_inertial.py) |
| `dataverse-sgjlza-diodem-a-diverse-inertia` | DIODEM -- A Diverse Inertial and Optical Dataset of kinEmatic chain... | 10.7910/dvn/sgjlza | `cleaned_rows` | 358 | `55f52591a1d0` | [CSV](data/dataverse-sgjlza-diodem-a-diverse-inertia-cleaned.csv) · [JSON](data/dataverse-sgjlza-diodem-a-diverse-inertia-provenance.json) · [PY](data/derive_dataverse_sgjlza_diodem_a_diverse_inertia.py) |
| `figshare-34691808-dataset-of-assessing-the` | Dataset of Assessing the Role of Robotic Process Automation in Buil... | 10.6084/m9.figshare.34691808.v1 | `cleaned_rows` | 146 | `398717537b87` | [CSV](data/figshare-34691808-dataset-of-assessing-the-cleaned.csv) · [JSON](data/figshare-34691808-dataset-of-assessing-the-provenance.json) · [PY](data/derive_figshare_34691808_dataset_of_assessing_the.py) |
| `figshare-35038195-data-sheet-2-multimodal` | Data Sheet 2_Multimodal nondestructive evaluation for structural as... | 10.3389/fmech.2026.2040645.s001 | `summary_table` | 29 | `8d960eeec025` | [CSV](data/figshare-35038195-data-sheet-2-multimodal-cleaned.csv) · [JSON](data/figshare-35038195-data-sheet-2-multimodal-provenance.json) · [PY](data/derive_figshare_35038195_data_sheet_2_multimodal.py) |
| `figshare-33322635-e-t-simulation-dataset` | E-T simulation dataset | 10.6084/m9.figshare.33322635.v1 | `cleaned_rows` | 377 | `a503fccc71a6` | [CSV](data/figshare-33322635-e-t-simulation-dataset-cleaned.csv) · [JSON](data/figshare-33322635-e-t-simulation-dataset-provenance.json) · [PY](data/derive_figshare_33322635_e_t_simulation_dataset.py) |
| `dataverse-kkdxdk-mmwalk-dataset` | mmWalk Dataset | 10.7910/dvn/kkdxdk | `cleaned_rows` | 50 | `82d91d6cf851` | [CSV](data/dataverse-kkdxdk-mmwalk-dataset-cleaned.csv) · [JSON](data/dataverse-kkdxdk-mmwalk-dataset-provenance.json) · [PY](data/derive_dataverse_kkdxdk_mmwalk_dataset.py) |
| `dataverse-lccllw-multisensegolf-a-multimo` | MultiSenseGolf: A Multimodal Sensor-Based Dataset for Golf Swing Mo... | 10.7910/dvn/lccllw | `summary_table` | 42 | `026fcf22978f` | [CSV](data/dataverse-lccllw-multisensegolf-a-multimo-cleaned.csv) · [JSON](data/dataverse-lccllw-multisensegolf-a-multimo-provenance.json) · [PY](data/derive_dataverse_lccllw_multisensegolf_a_multimo.py) |
| `dataverse-qgkeuw-dataset-for-influence-of` | Dataset for Influence of Visual and Haptic Feedback on the Detectio... | 10.7910/dvn/qgkeuw | `summary_table` | 150 | `5a748c1b718e` | [CSV](data/dataverse-qgkeuw-dataset-for-influence-of-cleaned.csv) · [JSON](data/dataverse-qgkeuw-dataset-for-influence-of-provenance.json) · [PY](data/derive_dataverse_qgkeuw_dataset_for_influence_of.py) |
| `figshare-32025606-snu-planetary-gearbox-da` | SNU Planetary Gearbox Dataset | 10.6084/m9.figshare.32025606.v5 | `cleaned_rows` | 28 | `e4e0dcbb38b8` | [CSV](data/figshare-32025606-snu-planetary-gearbox-da-cleaned.csv) · [JSON](data/figshare-32025606-snu-planetary-gearbox-da-provenance.json) · [PY](data/derive_figshare_32025606_snu_planetary_gearbox_da.py) |
| `figshare-34002057-clustering-enhanced-mcnn` | Clustering-Enhanced MCNN-LSTM-Based Control Method for PMSM Under M... | 10.6084/m9.figshare.34002057.v2 | `summary_table` | 20 | `3ae2b31aaf2d` | [CSV](data/figshare-34002057-clustering-enhanced-mcnn-cleaned.csv) · [JSON](data/figshare-34002057-clustering-enhanced-mcnn-provenance.json) · [PY](data/derive_figshare_34002057_clustering_enhanced_mcnn.py) |
| `figshare-26318407-non-muscle-powered-actua` | Non-muscle powered actuation inspired by cellular morphology and hy... | 10.6084/m9.figshare.26318407.v1 | `summary_table` | 20 | `e0f9dedbdb67` | [CSV](data/figshare-26318407-non-muscle-powered-actua-cleaned.csv) · [JSON](data/figshare-26318407-non-muscle-powered-actua-provenance.json) · [PY](data/derive_figshare_26318407_non_muscle_powered_actua.py) |
| `dataverse-cytve5-replication-data-for-fin` | Replication Data for: Fin-fin interactions during locomotion in a s... | 10.7910/dvn/cytve5 | `summary_table` | 20 | `921a4b6940c9` | [CSV](data/dataverse-cytve5-replication-data-for-fin-cleaned.csv) · [JSON](data/dataverse-cytve5-replication-data-for-fin-provenance.json) · [PY](data/derive_dataverse_cytve5_replication_data_for_fin.py) |
| `dataverse-snbqc2-replication-data-for-usi` | Replication Data for "Using TrackMate to Analyze Drosophila Larval... | 10.7910/dvn/snbqc2 | `summary_table` | 30 | `4c66f11347a1` | [CSV](data/dataverse-snbqc2-replication-data-for-usi-cleaned.csv) · [JSON](data/dataverse-snbqc2-replication-data-for-usi-provenance.json) · [PY](data/derive_dataverse_snbqc2_replication_data_for_usi.py) |
| `dataverse-zyqvlr-replication-data-for-dif` | Replication Data for: Differences in thermal tolerance and locomoti... | 10.7910/dvn/zyqvlr | `summary_table` | 23 | `b90d59c6e0ac` | [CSV](data/dataverse-zyqvlr-replication-data-for-dif-cleaned.csv) · [JSON](data/dataverse-zyqvlr-replication-data-for-dif-provenance.json) · [PY](data/derive_dataverse_zyqvlr_replication_data_for_dif.py) |
| `figshare-35049556-data-for-a-four-level-ex` | Data for "A four-level executable validation protocol for evaluatin... | 10.6084/m9.figshare.35049556.v1 | `summary_table` | 35 | `4899442117fd` | [CSV](data/figshare-35049556-data-for-a-four-level-ex-cleaned.csv) · [JSON](data/figshare-35049556-data-for-a-four-level-ex-provenance.json) · [PY](data/derive_figshare_35049556_data_for_a_four_level_ex.py) |
| `figshare-34163973-combined-effects-of-fibe` | Combined effects of fiber length and content on the mechanical and... | 10.6084/m9.figshare.34163973.v1 | `summary_table` | 148 | `bafee8d3ce90` | [CSV](data/figshare-34163973-combined-effects-of-fibe-cleaned.csv) · [JSON](data/figshare-34163973-combined-effects-of-fibe-provenance.json) · [PY](data/derive_figshare_34163973_combined_effects_of_fibe.py) |
| `figshare-32625708-dynamic-flexible-job-sho` | Dynamic flexible job shop scheduling under worker constraints with... | 10.6084/m9.figshare.32625708.v1 | `summary_table` | 130 | `c69c4879f96b` | [CSV](data/figshare-32625708-dynamic-flexible-job-sho-cleaned.csv) · [JSON](data/figshare-32625708-dynamic-flexible-job-sho-provenance.json) · [PY](data/derive_figshare_32625708_dynamic_flexible_job_sho.py) |

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
| 16 | 2026-11-21T08:44:12Z | Broad Engineering R16: R5_MultiRobot_Comm / Robotics_Embodied (2026) | +70 | +0 | +3 | [round-16-audit.json](rounds/round-16-audit.json) |
| 17 | 2026-11-21T08:49:03Z | Broad Engineering R17: Robotics_Embodied (2026) | +48 | +0 | +3 | [round-17-audit.json](rounds/round-17-audit.json) |
| 18 | 2026-11-21T08:54:12Z | Broad Engineering R18: Mechanical_Physics_AI (2026) | +80 | +0 | +3 | [round-18-audit.json](rounds/round-18-audit.json) |
| 19 | 2026-11-21T08:59:01Z | Broad Engineering R19: R1_Force_Contact | +99 | +43 | +3 | [round-19-audit.json](rounds/round-19-audit.json) |
| 20 | 2026-11-21T09:04:03Z | Broad Engineering R20: R1_Force_Contact / R2_Aerial_Actuator | +159 | +45 | +3 | [round-20-audit.json](rounds/round-20-audit.json) |
| 21 | 2026-11-21T09:08:59Z | Broad Engineering R21: R2_Aerial_Actuator / R5_MultiRobot_Comm | +134 | +47 | +3 | [round-21-audit.json](rounds/round-21-audit.json) |
| 22 | 2026-11-21T09:14:08Z | Broad Engineering R22: R5_MultiRobot_Comm / Robotics_Embodied | +106 | +83 | +3 | [round-22-audit.json](rounds/round-22-audit.json) |
