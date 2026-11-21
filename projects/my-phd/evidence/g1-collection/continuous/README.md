# G1 持续自动文献与数据检索及清洗目录（AI + 机械 / 机器人 / 机电一体化 / 智能制造）

- 本目录由本地自动轮询器 (`g1_runner.py`) 以 **CNY 0** 付费调用（仅开放学术/数据集 API）持续维护，严格与基线冻结目录 [2026-11-21](../2026-11-21/README.md) 隔离且跨库去重。
- 覆盖范围：腕部力矩/接触装配（R1）、执行器受限飞行控制（R2）、多机器人协同与通信（R5），以及所有 **AI + 机器人/具身智能、机械工程物理建模/FEM/CFD/PINN、机电一体化与 PHM 故障诊断、智能制造与增材/CNC 加工、数字孪生与智能调度**。
- 原始数据集仅下载至 Git 仓库外的 `raw-staging/` 进行 SHA-256 / MD5 校验与确定性清洗，不向仓库上传原始二进制数据或归档。
- G1 选题仍保持待人工决策状态（`state/run.json` 未被自动推进）。

## 累计产出概览

- **已完成轮次**：43
- **最近更新时间 (UTC)**：2026-11-21T11:12:53Z
- **累计净新增文献** (`literature-new.csv, literature-new-part-02.csv, literature-new-part-03.csv`)：4584 条（已与基线 15,910 条去重）
- **累计净新增数据集** (`datasets-new.csv, datasets-new-part-02.csv`)：1914 个（已与基线 191 个去重）
- **累计开放阅读队列** (`reading-queue-new.csv`)：3966 条
- **累计已完成确定性清洗数据集**：94 个
- **云端 `[research-cloud]` 自动调度门禁**：`skipped_baseline_checkpoint_error: unsupported checkpoint file requires an explicit storage plan: evidence/g1-collection/2026-11-21/audit/SHA256SUMS`

## 学科领域分布（确定性关键词分流，非人工终审）

| 领域标签 | 累计文献数 | 累计数据集数 |
|---|---:|---:|
| `R1_Force_Contact` | 148 | 99 |
| `R2_Aerial_Actuator` | 402 | 111 |
| `R5_MultiRobot_Comm` | 253 | 90 |
| `Robotics_Embodied` | 1380 | 588 |
| `Mechanical_Physics_AI` | 1449 | 873 |
| `Mechatronics_PHM_Control` | 1251 | 660 |
| `Smart_Manufacturing` | 603 | 381 |
| `Smart_Factory_DigitalTwin` | 220 | 75 |
| `R1` | 34 | 0 |
| `Adjacent` | 366 | 0 |
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
| `dataverse-getyap-drone-medical-package-de` | Drone Medical Package Delivery for Improved Transportation and Bett... | 10.7910/dvn/getyap | `cleaned_rows` | 202 | `ebb7e13fb595` | [CSV](data/dataverse-getyap-drone-medical-package-de-cleaned.csv) · [JSON](data/dataverse-getyap-drone-medical-package-de-provenance.json) · [PY](data/derive_dataverse_getyap_drone_medical_package_de.py) |
| `dataverse-fs95y3-gomezmurillotarwater-ant` | GomezMurilloTarwater_Antswarmmechs_Biotropica | 10.7910/dvn/fs95y3 | `cleaned_rows` | 133 | `3cc853cf2fb0` | [CSV](data/dataverse-fs95y3-gomezmurillotarwater-ant-cleaned.csv) · [JSON](data/dataverse-fs95y3-gomezmurillotarwater-ant-provenance.json) · [PY](data/derive_dataverse_fs95y3_gomezmurillotarwater_ant.py) |
| `dataverse-yuiynm-replication-data-for-com` | Replication Data for: Community perceptions of the use of drone map... | 10.7910/dvn/yuiynm | `summary_table` | 87 | `d35d03d5c6fa` | [CSV](data/dataverse-yuiynm-replication-data-for-com-cleaned.csv) · [JSON](data/dataverse-yuiynm-replication-data-for-com-provenance.json) · [PY](data/derive_dataverse_yuiynm_replication_data_for_com.py) |
| `figshare-34950610-dataset-robotic-sanding` | Dataset: Robotic Sanding Chilean Oak End-Grain Roughness | 10.6084/m9.figshare.34950610.v1 | `summary_table` | 14 | `8ce7afdc0306` | [CSV](data/figshare-34950610-dataset-robotic-sanding-cleaned.csv) · [JSON](data/figshare-34950610-dataset-robotic-sanding-provenance.json) · [PY](data/derive_figshare_34950610_dataset_robotic_sanding.py) |
| `figshare-24116583-dataset-robotic-sanding` | Dataset: Robotic Sanding MDF Roughness | 10.6084/m9.figshare.24116583.v1 | `summary_table` | 33 | `551d8bbee4ba` | [CSV](data/figshare-24116583-dataset-robotic-sanding-cleaned.csv) · [JSON](data/figshare-24116583-dataset-robotic-sanding-provenance.json) · [PY](data/derive_figshare_24116583_dataset_robotic_sanding.py) |
| `figshare-25024495-optimization-of-a-hydrog` | Optimization of a Hydrogen Exchange-Mass Spectrometry Robotic Liqui... | 10.1021/acs.analchem.3c04186.s006 | `cleaned_rows` | 88 | `9d05e14cdbec` | [CSV](data/figshare-25024495-optimization-of-a-hydrog-cleaned.csv) · [JSON](data/figshare-25024495-optimization-of-a-hydrog-provenance.json) · [PY](data/derive_figshare_25024495_optimization_of_a_hydrog.py) |
| `dataverse-cfzwvn-rural-donegal-drone-imag` | Rural Donegal Drone Images | 10.7910/dvn/cfzwvn | `summary_table` | 12 | `fa833327bc62` | [CSV](data/dataverse-cfzwvn-rural-donegal-drone-imag-cleaned.csv) · [JSON](data/dataverse-cfzwvn-rural-donegal-drone-imag-provenance.json) · [PY](data/derive_dataverse_cfzwvn_rural_donegal_drone_imag.py) |
| `dataverse-itfa7o-replication-data-for-ind` | Replication Data for: Individual vulnerability to industrial robot... | 10.7910/dvn/itfa7o | `summary_table` | 10 | `6160be0c6072` | [CSV](data/dataverse-itfa7o-replication-data-for-ind-cleaned.csv) · [JSON](data/dataverse-itfa7o-replication-data-for-ind-provenance.json) · [PY](data/derive_dataverse_itfa7o_replication_data_for_ind.py) |
| `dataverse-0wb6z1-the-replication-material` | The replication materials for the paper titled "Industrial Robots,... | 10.7910/dvn/0wb6z1 | `summary_table` | 30 | `24a008db25af` | [CSV](data/dataverse-0wb6z1-the-replication-material-cleaned.csv) · [JSON](data/dataverse-0wb6z1-the-replication-material-provenance.json) · [PY](data/derive_dataverse_0wb6z1_the_replication_material.py) |
| `dataverse-lznnl1-characteristics-of-the-s` | Characteristics of the Specific Fuel Consumption for Jet Engines | 10.7910/dvn/lznnl1 | `cleaned_rows` | 386 | `a6a3c87d20b1` | [CSV](data/dataverse-lznnl1-characteristics-of-the-s-cleaned.csv) · [JSON](data/dataverse-lznnl1-characteristics-of-the-s-provenance.json) · [PY](data/derive_dataverse_lznnl1_characteristics_of_the_s.py) |
| `dataverse-brzhhg-comparison-of-urethral-s` | Comparison of urethral sling surgery and vaginal non-ablative erbiu... | 10.7910/dvn/brzhhg | `cleaned_rows` | 334 | `70ce2b39da49` | [CSV](data/dataverse-brzhhg-comparison-of-urethral-s-cleaned.csv) · [JSON](data/dataverse-brzhhg-comparison-of-urethral-s-provenance.json) · [PY](data/derive_dataverse_brzhhg_comparison_of_urethral_s.py) |
| `figshare-34013343-code-and-data-for-a-unif` | Code and data for "A Unified Receding-Horizon Controller for Safe M... | 10.6084/m9.figshare.34013343.v2 | `summary_table` | 100 | `b2dc655e5a34` | [CSV](data/figshare-34013343-code-and-data-for-a-unif-cleaned.csv) · [JSON](data/figshare-34013343-code-and-data-for-a-unif-provenance.json) · [PY](data/derive_figshare_34013343_code_and_data_for_a_unif.py) |
| `figshare-27988055-experimental-data-for-mm` | Experimental Data for MMAM Gripper | 10.6084/m9.figshare.27988055.v4 | `summary_table` | 10 | `e3012d302b20` | [CSV](data/figshare-27988055-experimental-data-for-mm-cleaned.csv) · [JSON](data/figshare-27988055-experimental-data-for-mm-provenance.json) · [PY](data/derive_figshare_27988055_experimental_data_for_mm.py) |
| `dataverse-25880-annual-behavioral-tracki` | Annual Behavioral Tracking Survey (FSW & High Risk MSM)-I (2008) (B... | 10.7910/dvn/25880 | `summary_table` | 890 | `4e2b18c6ac70` | [CSV](data/dataverse-25880-annual-behavioral-tracki-cleaned.csv) · [JSON](data/dataverse-25880-annual-behavioral-tracki-provenance.json) · [PY](data/derive_dataverse_25880_annual_behavioral_tracki.py) |
| `dataverse-25901-annual-behavioral-tracki` | Annual Behavioral Tracking Survey (FSW & High risk MSM)-II -2011 (B... | 10.7910/dvn/25901 | `summary_table` | 1054 | `da8e9bebe528` | [CSV](data/dataverse-25901-annual-behavioral-tracki-cleaned.csv) · [JSON](data/dataverse-25901-annual-behavioral-tracki-provenance.json) · [PY](data/derive_dataverse_25901_annual_behavioral_tracki.py) |
| `dataverse-ombstn-a-sound-dataset-of-vario` | A Sound Dataset of Various Discrete Manufacturing Operations on Rea... | 10.7910/dvn/ombstn | `cleaned_rows` | 40 | `f7a279a1337b` | [CSV](data/dataverse-ombstn-a-sound-dataset-of-vario-cleaned.csv) · [JSON](data/dataverse-ombstn-a-sound-dataset-of-vario-provenance.json) · [PY](data/derive_dataverse_ombstn_a_sound_dataset_of_vario.py) |
| `figshare-32308917-dataset-for-laser-weldin` | Dataset for Laser Welding Deformation Prediction of TC4 Titanium Al... | 10.6084/m9.figshare.32308917.v1 | `summary_table` | 63 | `8202e327786d` | [CSV](data/figshare-32308917-dataset-for-laser-weldin-cleaned.csv) · [JSON](data/figshare-32308917-dataset-for-laser-weldin-provenance.json) · [PY](data/derive_figshare_32308917_dataset_for_laser_weldin.py) |
| `figshare-32095810-quantitative-prediction` | Quantitative prediction errors of the radial basis function neural... | 10.6084/m9.figshare.32095810.v1 | `cleaned_rows` | 100 | `130c154ee177` | [CSV](data/figshare-32095810-quantitative-prediction-cleaned.csv) · [JSON](data/figshare-32095810-quantitative-prediction-provenance.json) · [PY](data/derive_figshare_32095810_quantitative_prediction.py) |
| `dataverse-nssigl-date-stamping-us-housing` | Date-stamping US housing market explosivity | 10.7910/dvn/nssigl | `summary_table` | 30 | `0ba1e5896d69` | [CSV](data/dataverse-nssigl-date-stamping-us-housing-cleaned.csv) · [JSON](data/dataverse-nssigl-date-stamping-us-housing-provenance.json) · [PY](data/derive_dataverse_nssigl_date_stamping_us_housing.py) |
| `dataverse-sqs8my-replication-data-for-tur` | Replication Data for: "Turning on Those Who Turn to the Courts: Exp... | 10.7910/dvn/sqs8my | `summary_table` | 190 | `200f97378710` | [CSV](data/dataverse-sqs8my-replication-data-for-tur-cleaned.csv) · [JSON](data/dataverse-sqs8my-replication-data-for-tur-provenance.json) · [PY](data/derive_dataverse_sqs8my_replication_data_for_tur.py) |
| `dataverse-mygsyo-replication-data-for-foo` | Replication Data for: Foot-propelled swimming kinematics and turnin... | 10.7910/dvn/mygsyo | `summary_table` | 24 | `b5455e1580d1` | [CSV](data/dataverse-mygsyo-replication-data-for-foo-cleaned.csv) · [JSON](data/dataverse-mygsyo-replication-data-for-foo-provenance.json) · [PY](data/derive_dataverse_mygsyo_replication_data_for_foo.py) |
| `figshare-32362119-data-sheet-1-optimizing` | Data Sheet 1_Optimizing predictive maintenance with synthetic data:... | 10.3389/fmech.2026.1781598.s005 | `summary_table` | 214 | `4c4a5f96d2e1` | [CSV](data/figshare-32362119-data-sheet-1-optimizing-cleaned.csv) · [JSON](data/figshare-32362119-data-sheet-1-optimizing-provenance.json) · [PY](data/derive_figshare_32362119_data_sheet_1_optimizing.py) |
| `figshare-32362125-data-sheet-3-optimizing` | Data Sheet 3_Optimizing predictive maintenance with synthetic data:... | 10.3389/fmech.2026.1781598.s003 | `cleaned_rows` | 209 | `bcaa8ca93639` | [CSV](data/figshare-32362125-data-sheet-3-optimizing-cleaned.csv) · [JSON](data/figshare-32362125-data-sheet-3-optimizing-provenance.json) · [PY](data/derive_figshare_32362125_data_sheet_3_optimizing.py) |
| `figshare-32362128-data-sheet-4-optimizing` | Data Sheet 4_Optimizing predictive maintenance with synthetic data:... | 10.3389/fmech.2026.1781598.s002 | `cleaned_rows` | 10 | `a8e35125db9c` | [CSV](data/figshare-32362128-data-sheet-4-optimizing-cleaned.csv) · [JSON](data/figshare-32362128-data-sheet-4-optimizing-provenance.json) · [PY](data/derive_figshare_32362128_data_sheet_4_optimizing.py) |
| `dataverse-d0zgsm-acoustic-mems-sensor-arr` | Acoustic MEMS Sensor Array for Quench Detection of CICC Superconduc... | 10.7910/dvn/d0zgsm | `cleaned_rows` | 569 | `ee045c0e8a7d` | [CSV](data/dataverse-d0zgsm-acoustic-mems-sensor-arr-cleaned.csv) · [JSON](data/dataverse-d0zgsm-acoustic-mems-sensor-arr-provenance.json) · [PY](data/derive_dataverse_d0zgsm_acoustic_mems_sensor_arr.py) |

## 最近轮次记录（最多显示最近 25 轮）

| 轮次 | UTC 时间 | 主题批次 | 净增文献 | 净增数据集 | 新增清洗表 | 审计文件 |
|---:|---|---|---:|---:|---:|---|
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
| 30 | 2026-11-21T09:54:02Z | Broad Engineering R30: Smart_Manufacturing / Smart_Factory_DigitalTwin | +180 | +54 | +3 | [round-30-audit.json](rounds/round-30-audit.json) |
| 31 | 2026-11-21T09:59:10Z | Broad Engineering R31: Smart_Factory_DigitalTwin / R1_Force_Contact | +54 | +32 | +3 | [round-31-audit.json](rounds/round-31-audit.json) |
| 32 | 2026-11-21T10:04:00Z | Broad Engineering R32: R1_Force_Contact (2026) | +20 | +32 | +3 | [round-32-audit.json](rounds/round-32-audit.json) |
| 33 | 2026-11-21T10:09:02Z | Broad Engineering R33: R2_Aerial_Actuator (2026) | +0 | +28 | +3 | [round-33-audit.json](rounds/round-33-audit.json) |
| 34 | 2026-11-21T10:14:04Z | Broad Engineering R34: Mechanical_Physics_AI | +108 | +30 | +3 | [round-34-audit.json](rounds/round-34-audit.json) |
| 35 | 2026-11-21T10:19:03Z | Broad Engineering R35: Mechanical_Physics_AI | +141 | +43 | +3 | [round-35-audit.json](rounds/round-35-audit.json) |
| 36 | 2026-11-21T10:24:02Z | Broad Engineering R36: Mechanical_Physics_AI | +127 | +38 | +0 | [round-36-audit.json](rounds/round-36-audit.json) |
| 37 | 2026-11-21T10:29:02Z | Broad Engineering R37: Robotics_Embodied | +75 | +30 | +2 | [round-37-audit.json](rounds/round-37-audit.json) |
| 38 | 2026-11-21T10:34:04Z | Broad Engineering R38: Robotics_Embodied | +145 | +52 | +2 | [round-38-audit.json](rounds/round-38-audit.json) |
| 39 | 2026-11-21T10:39:02Z | Broad Engineering R39: Robotics_Embodied | +92 | +32 | +3 | [round-39-audit.json](rounds/round-39-audit.json) |
| 40 | 2026-11-21T10:44:10Z | Broad Engineering R40: Mechatronics_PHM_Control | +111 | +12 | +2 | [round-40-audit.json](rounds/round-40-audit.json) |
| 41 | 2026-11-21T10:49:08Z | Broad Engineering R41: Mechatronics_PHM_Control | +140 | +29 | +3 | [round-41-audit.json](rounds/round-41-audit.json) |
| 42 | 2026-11-21T10:54:08Z | Broad Engineering R42: Mechatronics_PHM_Control | +150 | +25 | +3 | [round-42-audit.json](rounds/round-42-audit.json) |
| 43 | 2026-11-21T11:12:53Z | Broad Engineering R43: Smart_Manufacturing | +92 | +24 | +1 | [round-43-audit.json](rounds/round-43-audit.json) |
