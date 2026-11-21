# G1 持续自动文献与数据检索及清洗目录（AI + 机械 / 机器人 / 机电一体化 / 智能制造）

- 本目录由本地自动轮询器 (`g1_runner.py`) 以 **CNY 0** 付费调用（仅开放学术/数据集 API）持续维护，严格与基线冻结目录 [2026-11-21](../2026-11-21/README.md) 隔离且跨库去重。
- 覆盖范围：腕部力矩/接触装配（R1）、执行器受限飞行控制（R2）、多机器人协同与通信（R5），以及所有 **AI + 机器人/具身智能、机械工程物理建模/FEM/CFD/PINN、机电一体化与 PHM 故障诊断、智能制造与增材/CNC 加工、数字孪生与智能调度**。
- 原始数据集仅下载至 Git 仓库外的 `raw-staging/` 进行 SHA-256 / MD5 校验与确定性清洗，不向仓库上传原始二进制数据或归档。
- G1 选题仍保持待人工决策状态（`state/run.json` 未被自动推进）。

## 累计产出概览

- **已完成轮次**：29
- **最近更新时间 (UTC)**：2026-11-21T09:49:01Z
- **累计净新增文献** (`literature-new.csv, literature-new-part-02.csv`)：3149 条（已与基线 15,910 条去重）
- **累计净新增数据集** (`datasets-new.csv`)：1453 个（已与基线 191 个去重）
- **累计开放阅读队列** (`reading-queue-new.csv`)：2737 条
- **累计已完成确定性清洗数据集**：60 个
- **云端 `[research-cloud]` 自动调度门禁**：`skipped_baseline_checkpoint_error: unsupported checkpoint file requires an explicit storage plan: evidence/g1-collection/2026-11-21/audit/SHA256SUMS`

## 学科领域分布（确定性关键词分流，非人工终审）

| 领域标签 | 累计文献数 | 累计数据集数 |
|---|---:|---:|
| `R1_Force_Contact` | 124 | 57 |
| `R2_Aerial_Actuator` | 387 | 50 |
| `R5_MultiRobot_Comm` | 242 | 45 |
| `Robotics_Embodied` | 1044 | 458 |
| `Mechanical_Physics_AI` | 934 | 648 |
| `Mechatronics_PHM_Control` | 755 | 469 |
| `Smart_Manufacturing` | 399 | 284 |
| `Smart_Factory_DigitalTwin` | 155 | 69 |
| `R1` | 34 | 0 |
| `Adjacent` | 246 | 0 |
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
| `dataverse-a9lpy7-urbaning-v2x` | UrbanIng-V2X | 10.7910/dvn/a9lpy7 | `summary_table` | 25 | `a659594d5e30` | [CSV](data/dataverse-a9lpy7-urbaning-v2x-cleaned.csv) · [JSON](data/dataverse-a9lpy7-urbaning-v2x-provenance.json) · [PY](data/derive_dataverse_a9lpy7_urbaning_v2x.py) |
| `dataverse-m6jxed-open-ended-creative-and` | Open-Ended Creative and Tactile Activity in Adult Practice: A Surve... | 10.7910/dvn/m6jxed | `summary_table` | 29 | `a01a6467f93c` | [CSV](data/dataverse-m6jxed-open-ended-creative-and-cleaned.csv) · [JSON](data/dataverse-m6jxed-open-ended-creative-and-provenance.json) · [PY](data/derive_dataverse_m6jxed_open_ended_creative_and.py) |
| `dataverse-ckmbcg-replication-data-for-fee` | Replication Data for: Feedback and Education Improve Human Detectio... | 10.7910/dvn/ckmbcg | `summary_table` | 166 | `f7f3adef2265` | [CSV](data/dataverse-ckmbcg-replication-data-for-fee-cleaned.csv) · [JSON](data/dataverse-ckmbcg-replication-data-for-fee-provenance.json) · [PY](data/derive_dataverse_ckmbcg_replication_data_for_fee.py) |
| `figshare-35071237-supplementary-file-1-phy` | Supplementary file 1_Physiological digital twins require cross-syst... | 10.3389/fphys.2026.1947699.s001 | `summary_table` | 22 | `7560dcee2b21` | [CSV](data/figshare-35071237-supplementary-file-1-phy-cleaned.csv) · [JSON](data/figshare-35071237-supplementary-file-1-phy-provenance.json) · [PY](data/derive_figshare_35071237_supplementary_file_1_phy.py) |
| `dataverse-qpuojh-close-box` | close_box | 10.7910/dvn/qpuojh | `summary_table` | 2 | `552f163cf7c1` | [CSV](data/dataverse-qpuojh-close-box-cleaned.csv) · [JSON](data/dataverse-qpuojh-close-box-provenance.json) · [PY](data/derive_dataverse_qpuojh_close_box.py) |
| `dataverse-dozy6n-eval-dataset` | eval_dataset | 10.7910/dvn/dozy6n | `cleaned_rows` | 200 | `a522bf125f66` | [CSV](data/dataverse-dozy6n-eval-dataset-cleaned.csv) · [JSON](data/dataverse-dozy6n-eval-dataset-provenance.json) · [PY](data/derive_dataverse_dozy6n_eval_dataset.py) |
| `dataverse-epu7uw-scoop-with-spatula` | scoop_with_spatula | 10.7910/dvn/epu7uw | `summary_table` | 2 | `2a2b5622df5f` | [CSV](data/dataverse-epu7uw-scoop-with-spatula-cleaned.csv) · [JSON](data/dataverse-epu7uw-scoop-with-spatula-provenance.json) · [PY](data/derive_dataverse_epu7uw_scoop_with_spatula.py) |
| `figshare-32445474-supplementary-file-1-des` | Supplementary file 1_Design and experimental validation of a soft p... | 10.3389/frobt.2026.1839026.s002 | `summary_table` | 20 | `48dc9db6a962` | [CSV](data/figshare-32445474-supplementary-file-1-des-cleaned.csv) · [JSON](data/figshare-32445474-supplementary-file-1-des-provenance.json) · [PY](data/derive_figshare_32445474_supplementary_file_1_des.py) |
| `figshare-34926150-dataset-for-surgeons-awa` | Dataset for: Surgeons’ Awareness, Attitudes, and Willingness to Ado... | 10.6084/m9.figshare.34926150.v2 | `cleaned_rows` | 408 | `3677633f0aa2` | [CSV](data/figshare-34926150-dataset-for-surgeons-awa-cleaned.csv) · [JSON](data/figshare-34926150-dataset-for-surgeons-awa-provenance.json) · [PY](data/derive_figshare_34926150_dataset_for_surgeons_awa.py) |
| `dataverse-xeaypq-slide-block-to-target` | slide_block_to_target | 10.7910/dvn/xeaypq | `summary_table` | 2 | `7d93310b0f77` | [CSV](data/dataverse-xeaypq-slide-block-to-target-cleaned.csv) · [JSON](data/dataverse-xeaypq-slide-block-to-target-provenance.json) · [PY](data/derive_dataverse_xeaypq_slide_block_to_target.py) |
| `dataverse-0iwofy-replication-data-for-dig` | Replication Data for Digital annexation: How geodata, training corp... | 10.7910/dvn/0iwofy | `summary_table` | 31 | `82250b703876` | [CSV](data/dataverse-0iwofy-replication-data-for-dig-cleaned.csv) · [JSON](data/dataverse-0iwofy-replication-data-for-dig-provenance.json) · [PY](data/derive_dataverse_0iwofy_replication_data_for_dig.py) |
| `dataverse-kb7auc-replication-data-for-a-w` | Replication Data for: A Wearable Wireless Sensor Network for Human... | 10.7910/dvn/kb7auc | `summary_table` | 64 | `f6438da5d84b` | [CSV](data/dataverse-kb7auc-replication-data-for-a-w-cleaned.csv) · [JSON](data/dataverse-kb7auc-replication-data-for-a-w-provenance.json) · [PY](data/derive_dataverse_kb7auc_replication_data_for_a_w.py) |
| `dataverse-xtpysv-light-detection-and-rang` | Light detection and ranging (lidar) point clouds collected from unm... | 10.7910/dvn/xtpysv | `summary_table` | 39 | `0be07b5056c7` | [CSV](data/dataverse-xtpysv-light-detection-and-rang-cleaned.csv) · [JSON](data/dataverse-xtpysv-light-detection-and-rang-provenance.json) · [PY](data/derive_dataverse_xtpysv_light_detection_and_rang.py) |
| `dataverse-4zoizl-replication-data-for-win` | Replication Data for: Wing wear reduces bumblebee flight performanc... | 10.7910/dvn/4zoizl | `summary_table` | 16 | `3ece0c7ef9f4` | [CSV](data/dataverse-4zoizl-replication-data-for-win-cleaned.csv) · [JSON](data/dataverse-4zoizl-replication-data-for-win-provenance.json) · [PY](data/derive_dataverse_4zoizl_replication_data_for_win.py) |
| `dataverse-7iajwu-the-multi-sensor-based-m` | The multi sensor-based machining signal fusion to compare the relat... | 10.7910/dvn/7iajwu | `cleaned_rows` | 48 | `6e2423c31e67` | [CSV](data/dataverse-7iajwu-the-multi-sensor-based-m-cleaned.csv) · [JSON](data/dataverse-7iajwu-the-multi-sensor-based-m-provenance.json) · [PY](data/derive_dataverse_7iajwu_the_multi_sensor_based_m.py) |

## 最近轮次记录（最多显示最近 25 轮）

| 轮次 | UTC 时间 | 主题批次 | 净增文献 | 净增数据集 | 新增清洗表 | 审计文件 |
|---:|---|---|---:|---:|---:|---|
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
| 23 | 2026-11-21T09:19:02Z | Broad Engineering R23: Robotics_Embodied | +202 | +40 | +3 | [round-23-audit.json](rounds/round-23-audit.json) |
| 24 | 2026-11-21T09:24:11Z | Broad Engineering R24: Robotics_Embodied | +157 | +53 | +1 | [round-24-audit.json](rounds/round-24-audit.json) |
| 25 | 2026-11-21T09:29:02Z | Broad Engineering R25: Mechanical_Physics_AI | +117 | +72 | +3 | [round-25-audit.json](rounds/round-25-audit.json) |
| 26 | 2026-11-21T09:34:02Z | Broad Engineering R26: Mechanical_Physics_AI | +202 | +62 | +2 | [round-26-audit.json](rounds/round-26-audit.json) |
| 27 | 2026-11-21T09:39:08Z | Broad Engineering R27: Mechatronics_PHM_Control | +123 | +60 | +3 | [round-27-audit.json](rounds/round-27-audit.json) |
| 28 | 2026-11-21T09:44:03Z | Broad Engineering R28: Mechatronics_PHM_Control | +92 | +37 | +0 | [round-28-audit.json](rounds/round-28-audit.json) |
| 29 | 2026-11-21T09:49:01Z | Broad Engineering R29: Smart_Manufacturing | +155 | +39 | +3 | [round-29-audit.json](rounds/round-29-audit.json) |
