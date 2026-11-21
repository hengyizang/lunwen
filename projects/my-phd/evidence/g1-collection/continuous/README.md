# G1 持续自动文献与数据检索及清洗目录（AI + 机械 / 机器人 / 机电一体化 / 智能制造）

- 本目录由本地自动轮询器 (`g1_runner.py`) 以 **CNY 0** 付费调用（仅开放学术/数据集 API）持续维护，严格与基线冻结目录 [2026-11-21](../2026-11-21/README.md) 隔离且跨库去重。
- 覆盖范围：腕部力矩/接触装配（R1）、执行器受限飞行控制（R2）、多机器人协同与通信（R5），以及所有 **AI + 机器人/具身智能、机械工程物理建模/FEM/CFD/PINN、机电一体化与 PHM 故障诊断、智能制造与增材/CNC 加工、数字孪生与智能调度**。
- 原始数据集仅下载至 Git 仓库外的 `raw-staging/` 进行 SHA-256 / MD5 校验与确定性清洗，不向仓库上传原始二进制数据或归档。
- G1 选题仍保持待人工决策状态（`state/run.json` 未被自动推进）。

## 累计产出概览

- **已完成轮次**：52
- **最近更新时间 (UTC)**：2026-11-21T12:49:12Z
- **累计净新增文献** (`literature-new.csv, literature-new-part-02.csv, literature-new-part-03.csv, literature-new-part-04.csv`)：5618 条（已与基线 15,910 条去重）
- **累计净新增数据集** (`datasets-new.csv, datasets-new-part-02.csv`)：1988 个（已与基线 191 个去重）
- **累计开放阅读队列** (`reading-queue-new.csv`)：4632 条
- **累计已完成确定性清洗数据集**：115 个
- **云端 `[research-cloud]` 自动调度门禁**：`skipped_baseline_checkpoint_error: unsupported checkpoint file requires an explicit storage plan: evidence/g1-collection/2026-11-21/audit/SHA256SUMS`

## 学科领域分布（确定性关键词分流，非人工终审）

| 领域标签 | 累计文献数 | 累计数据集数 |
|---|---:|---:|
| `R1_Force_Contact` | 207 | 99 |
| `R2_Aerial_Actuator` | 524 | 119 |
| `R5_MultiRobot_Comm` | 314 | 97 |
| `Robotics_Embodied` | 1610 | 616 |
| `Mechanical_Physics_AI` | 1509 | 901 |
| `Mechatronics_PHM_Control` | 1350 | 680 |
| `Smart_Manufacturing` | 736 | 438 |
| `Smart_Factory_DigitalTwin` | 437 | 90 |
| `R1` | 34 | 0 |
| `Adjacent` | 701 | 0 |
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
| `figshare-32362119-data-sheet-1-optimizing` | Data Sheet 1_Optimizing predictive maintenance with synthetic data:... | 10.3389/fmech.2026.1781598.s005 | `summary_table` | 214 | `4c4a5f96d2e1` | [CSV](data/figshare-32362119-data-sheet-1-optimizing-cleaned.csv) · [JSON](data/figshare-32362119-data-sheet-1-optimizing-provenance.json) · [PY](data/derive_figshare_32362119_data_sheet_1_optimizing.py) |
| `figshare-32362125-data-sheet-3-optimizing` | Data Sheet 3_Optimizing predictive maintenance with synthetic data:... | 10.3389/fmech.2026.1781598.s003 | `cleaned_rows` | 209 | `bcaa8ca93639` | [CSV](data/figshare-32362125-data-sheet-3-optimizing-cleaned.csv) · [JSON](data/figshare-32362125-data-sheet-3-optimizing-provenance.json) · [PY](data/derive_figshare_32362125_data_sheet_3_optimizing.py) |
| `figshare-32362128-data-sheet-4-optimizing` | Data Sheet 4_Optimizing predictive maintenance with synthetic data:... | 10.3389/fmech.2026.1781598.s002 | `cleaned_rows` | 10 | `a8e35125db9c` | [CSV](data/figshare-32362128-data-sheet-4-optimizing-cleaned.csv) · [JSON](data/figshare-32362128-data-sheet-4-optimizing-provenance.json) · [PY](data/derive_figshare_32362128_data_sheet_4_optimizing.py) |
| `dataverse-d0zgsm-acoustic-mems-sensor-arr` | Acoustic MEMS Sensor Array for Quench Detection of CICC Superconduc... | 10.7910/dvn/d0zgsm | `cleaned_rows` | 569 | `ee045c0e8a7d` | [CSV](data/dataverse-d0zgsm-acoustic-mems-sensor-arr-cleaned.csv) · [JSON](data/dataverse-d0zgsm-acoustic-mems-sensor-arr-provenance.json) · [PY](data/derive_dataverse_d0zgsm_acoustic_mems_sensor_arr.py) |
| `figshare-34982740-an-ai-empowered-laser-ga` | An AI-empowered laser-galvanometer contouring system for 3D anomaly... | 10.6084/m9.figshare.34982740.v2 | `cleaned_rows` | 17 | `52c1d4956973` | [CSV](data/figshare-34982740-an-ai-empowered-laser-ga-cleaned.csv) · [JSON](data/figshare-34982740-an-ai-empowered-laser-ga-provenance.json) · [PY](data/derive_figshare_34982740_an_ai_empowered_laser_ga.py) |
| `dataverse-4saz4x-the-effect-of-vibration` | The effect of vibration cycle ergometry on pulmonary VO2 kinetics,... | 10.7910/dvn/4saz4x | `cleaned_rows` | 35 | `ce5db73af5fa` | [CSV](data/dataverse-4saz4x-the-effect-of-vibration-cleaned.csv) · [JSON](data/dataverse-4saz4x-the-effect-of-vibration-provenance.json) · [PY](data/derive_dataverse_4saz4x_the_effect_of_vibration.py) |
| `dataverse-lpnslg-tensile-test-and-finite` | Tensile Test and Finite Element Optimization of the Triple-pipe Reb... | 10.7910/dvn/lpnslg | `summary_table` | 8 | `af22dc85042b` | [CSV](data/dataverse-lpnslg-tensile-test-and-finite-cleaned.csv) · [JSON](data/dataverse-lpnslg-tensile-test-and-finite-provenance.json) · [PY](data/derive_dataverse_lpnslg_tensile_test_and_finite.py) |
| `figshare-32362131-data-sheet-5-optimizing` | Data Sheet 5_Optimizing predictive maintenance with synthetic data:... | 10.3389/fmech.2026.1781598.s001 | `summary_table` | 24 | `21fe3aef7ab0` | [CSV](data/figshare-32362131-data-sheet-5-optimizing-cleaned.csv) · [JSON](data/figshare-32362131-data-sheet-5-optimizing-provenance.json) · [PY](data/derive_figshare_32362131_data_sheet_5_optimizing.py) |
| `figshare-29045729-data-analysis` | Data Analysis | 10.6084/m9.figshare.29045729.v1 | `summary_table` | 15 | `0324671b766c` | [CSV](data/figshare-29045729-data-analysis-cleaned.csv) · [JSON](data/figshare-29045729-data-analysis-provenance.json) · [PY](data/derive_figshare_29045729_data_analysis.py) |
| `figshare-34072891-source-data-for-the-labo` | Source data for the laboratory hydraulic-fracturing tests, acoustic... | 10.1371/journal.pone.0359936.s001 | `cleaned_rows` | 635 | `6448aa3c3b47` | [CSV](data/figshare-34072891-source-data-for-the-labo-cleaned.csv) · [JSON](data/figshare-34072891-source-data-for-the-labo-provenance.json) · [PY](data/derive_figshare_34072891_source_data_for_the_labo.py) |
| `dataverse-xfuwjg-simjeb-simulated-jet-eng` | SimJEB: Simulated Jet Engine Bracket Dataset | 10.7910/dvn/xfuwjg | `cleaned_rows` | 381 | `687a77d3e365` | [CSV](data/dataverse-xfuwjg-simjeb-simulated-jet-eng-cleaned.csv) · [JSON](data/dataverse-xfuwjg-simjeb-simulated-jet-eng-provenance.json) · [PY](data/derive_dataverse_xfuwjg_simjeb_simulated_jet_eng.py) |
| `dataverse-wjgdur-fem-data-for-large-radiu` | FEM data for large radius bending | 10.7910/dvn/wjgdur | `cleaned_rows` | 52 | `9c74ea6f9d84` | [CSV](data/dataverse-wjgdur-fem-data-for-large-radiu-cleaned.csv) · [JSON](data/dataverse-wjgdur-fem-data-for-large-radiu-provenance.json) · [PY](data/derive_dataverse_wjgdur_fem_data_for_large_radiu.py) |
| `figshare-31646617-selective-laser-melting` | Selective laser melting, Ti-6Al-4V, Additive manufacturing, Tensile... | 10.6084/m9.figshare.31646617.v1 | `cleaned_rows` | 129 | `bd1cf54731ed` | [CSV](data/figshare-31646617-selective-laser-melting-cleaned.csv) · [JSON](data/figshare-31646617-selective-laser-melting-provenance.json) · [PY](data/derive_figshare_31646617_selective_laser_melting.py) |
| `figshare-34808832-data-for-piam-a-physics` | Data for: PiAM — A physics-informed adaptive multi-fidelity framewo... | 10.6084/m9.figshare.34808832.v1 | `summary_table` | 42 | `a01434913d7a` | [CSV](data/figshare-34808832-data-for-piam-a-physics-cleaned.csv) · [JSON](data/figshare-34808832-data-for-piam-a-physics-provenance.json) · [PY](data/derive_figshare_34808832_data_for_piam_a_physics.py) |
| `figshare-32789034-observation-of-twofold-d` | Observation of twofold degenerate acoustic Landau levels and pseudo... | 10.6084/m9.figshare.32789034.v2 | `summary_table` | 16 | `838fcd254e07` | [CSV](data/figshare-32789034-observation-of-twofold-d-cleaned.csv) · [JSON](data/figshare-32789034-observation-of-twofold-d-provenance.json) · [PY](data/derive_figshare_32789034_observation_of_twofold_d.py) |
| `dataverse-2svlhs-analysis-of-the-hydrogeo` | Analysis of the Hydrogeological Conditions Affecting Fault Response... | 10.7910/dvn/2svlhs | `cleaned_rows` | 48 | `7cbd9189013d` | [CSV](data/dataverse-2svlhs-analysis-of-the-hydrogeo-cleaned.csv) · [JSON](data/dataverse-2svlhs-analysis-of-the-hydrogeo-provenance.json) · [PY](data/derive_dataverse_2svlhs_analysis_of_the_hydrogeo.py) |
| `dataverse-hfcsqz-cfd-tool-vspaero-actuato` | CFD Tool VSPAERO: Actuator Disk and Flow Visualization | 10.7910/dvn/hfcsqz | `summary_table` | 1012 | `643a2d22f71a` | [CSV](data/dataverse-hfcsqz-cfd-tool-vspaero-actuato-cleaned.csv) · [JSON](data/dataverse-hfcsqz-cfd-tool-vspaero-actuato-provenance.json) · [PY](data/derive_dataverse_hfcsqz_cfd_tool_vspaero_actuato.py) |
| `dataverse-4qhuwx-replication-data-for-hea` | Replication Data for: Heating and Current-Drive Actuator Systems fo... | 10.7910/dvn/4qhuwx | `summary_table` | 15 | `060dbe697f9e` | [CSV](data/dataverse-4qhuwx-replication-data-for-hea-cleaned.csv) · [JSON](data/dataverse-4qhuwx-replication-data-for-hea-provenance.json) · [PY](data/derive_dataverse_4qhuwx_replication_data_for_hea.py) |
| `figshare-24204510-data-of-rapid-phase-curr` | Data of Rapid Phase Current Sampling in a Permanent Magnet Synchron... | 10.6084/m9.figshare.24204510.v1 | `summary_table` | 13 | `d9ca7c67f863` | [CSV](data/figshare-24204510-data-of-rapid-phase-curr-cleaned.csv) · [JSON](data/figshare-24204510-data-of-rapid-phase-curr-provenance.json) · [PY](data/derive_figshare_24204510_data_of_rapid_phase_curr.py) |
| `figshare-32065938-custom-machining-gantry` | Custom Machining Gantry for Hybrid Additive Manufacturing Vibration... | 10.6084/m9.figshare.32065938.v1 | `summary_table` | 16 | `f667d7ae26ae` | [CSV](data/figshare-32065938-custom-machining-gantry-cleaned.csv) · [JSON](data/figshare-32065938-custom-machining-gantry-provenance.json) · [PY](data/derive_figshare_32065938_custom_machining_gantry.py) |
| `dataverse-efnv5j-replication-data-for-hyd` | Replication Data For: Hydraulic Fracturing Chemicals Reporting: Ana... | 10.7910/dvn/efnv5j | `cleaned_rows` | 34 | `81cdd210694d` | [CSV](data/dataverse-efnv5j-replication-data-for-hyd-cleaned.csv) · [JSON](data/dataverse-efnv5j-replication-data-for-hyd-provenance.json) · [PY](data/derive_dataverse_efnv5j_replication_data_for_hyd.py) |
| `dataverse-wohq9f-replication-data-for-mix` | Replication Data for: Mixed hydraulic responses to drought in six c... | 10.7910/dvn/wohq9f | `summary_table` | 37 | `5d1ccf03e688` | [CSV](data/dataverse-wohq9f-replication-data-for-mix-cleaned.csv) · [JSON](data/dataverse-wohq9f-replication-data-for-mix-provenance.json) · [PY](data/derive_dataverse_wohq9f_replication_data_for_mix.py) |
| `dataverse-jzgtxj-peafowl-locomotion` | Peafowl Locomotion | 10.7910/dvn/jzgtxj | `cleaned_rows` | 282 | `a7c4d8841fea` | [CSV](data/dataverse-jzgtxj-peafowl-locomotion-cleaned.csv) · [JSON](data/dataverse-jzgtxj-peafowl-locomotion-provenance.json) · [PY](data/derive_dataverse_jzgtxj_peafowl_locomotion.py) |
| `figshare-24602967-data-a-systematic-review` | Data - A systematic review on uncalibrated visual servoing techniques | 10.6084/m9.figshare.24602967.v1 | `summary_table` | 35 | `533ad76fe1e6` | [CSV](data/figshare-24602967-data-a-systematic-review-cleaned.csv) · [JSON](data/figshare-24602967-data-a-systematic-review-provenance.json) · [PY](data/derive_figshare_24602967_data_a_systematic_review.py) |
| `figshare-31817062-synthetic-pump-predictiv` | Synthetic Pump Predictive Maintenance Dataset with Physics-Based De... | 10.6084/m9.figshare.31817062 | `summary_table` | 35 | `fc69c38645f1` | [CSV](data/figshare-31817062-synthetic-pump-predictiv-cleaned.csv) · [JSON](data/figshare-31817062-synthetic-pump-predictiv-provenance.json) · [PY](data/derive_figshare_31817062_synthetic_pump_predictiv.py) |

## 最近轮次记录（最多显示最近 25 轮）

| 轮次 | UTC 时间 | 主题批次 | 净增文献 | 净增数据集 | 新增清洗表 | 审计文件 |
|---:|---|---|---:|---:|---:|---|
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
| 44 | 2026-11-21T11:59:23Z | Broad Engineering R44: Smart_Manufacturing | +21 | +0 | +1 | [round-44-audit.json](rounds/round-44-audit.json) |
| 45 | 2026-11-21T12:11:35Z | Broad Engineering R45: Smart_Manufacturing | +104 | +13 | +2 | [round-45-audit.json](rounds/round-45-audit.json) |
| 46 | 2026-11-21T12:14:14Z | Broad Engineering R46: Smart_Factory_DigitalTwin | +115 | +10 | +3 | [round-46-audit.json](rounds/round-46-audit.json) |
| 47 | 2026-11-21T12:19:05Z | Broad Engineering R47: Smart_Factory_DigitalTwin | +358 | +6 | +2 | [round-47-audit.json](rounds/round-47-audit.json) |
| 48 | 2026-11-21T12:24:05Z | Broad Engineering R48: R1_Force_Contact / R2_Aerial_Actuator | +174 | +7 | +3 | [round-48-audit.json](rounds/round-48-audit.json) |
| 49 | 2026-11-21T12:29:10Z | Broad Engineering R49: R2_Aerial_Actuator / R5_MultiRobot_Comm | +105 | +15 | +3 | [round-49-audit.json](rounds/round-49-audit.json) |
| 50 | 2026-11-21T12:39:13Z | Broad Engineering R50: R1_Force_Contact (2025) | +52 | +6 | +2 | [round-50-audit.json](rounds/round-50-audit.json) |
| 51 | 2026-11-21T12:44:05Z | Broad Engineering R51: R1_Force_Contact / R2_Aerial_Actuator (2025) | +32 | +2 | +3 | [round-51-audit.json](rounds/round-51-audit.json) |
| 52 | 2026-11-21T12:49:12Z | Broad Engineering R52: R2_Aerial_Actuator / R5_MultiRobot_Comm (2025) | +73 | +15 | +2 | [round-52-audit.json](rounds/round-52-audit.json) |
