# G1 持续自动文献与数据检索及清洗目录（AI + 机械 / 机器人 / 机电一体化 / 智能制造）

- 本目录由本地自动轮询器 (`g1_runner.py`) 以 **CNY 0** 付费调用（仅开放学术/数据集 API）持续维护，严格与基线冻结目录 [2026-11-21](../2026-11-21/README.md) 隔离且跨库去重。
- 覆盖范围：腕部力矩/接触装配（R1）、执行器受限飞行控制（R2）、多机器人协同与通信（R5），以及所有 **AI + 机器人/具身智能、机械工程物理建模/FEM/CFD/PINN、机电一体化与 PHM 故障诊断、智能制造与增材/CNC 加工、数字孪生与智能调度**。
- 原始数据集仅下载至 Git 仓库外的 `raw-staging/` 进行 SHA-256 / MD5 校验与确定性清洗，不向仓库上传原始二进制数据或归档。
- G1 选题仍保持待人工决策状态（`state/run.json` 未被自动推进）。

## 累计产出概览

- **已完成轮次**：3
- **最近更新时间 (UTC)**：2026-11-21T07:44:04Z
- **累计净新增文献** (`literature-new.csv`)：182 条（已与基线 15,910 条去重）
- **累计净新增数据集** (`datasets-new.csv`)：200 个（已与基线 191 个去重）
- **累计开放阅读队列** (`reading-queue-new.csv`)：150 条
- **累计已完成确定性清洗数据集**：5 个
- **云端 `[research-cloud]` 自动调度门禁**：`skipped_baseline_checkpoint_error: unsupported checkpoint file requires an explicit storage plan: evidence/g1-collection/2026-11-21/audit/SHA256SUMS`

## 学科领域分布（确定性关键词分流，非人工终审）

| 领域标签 | 累计文献数 | 累计数据集数 |
|---|---:|---:|
| `R1_Force_Contact` | 1 | 0 |
| `R2_Aerial_Actuator` | 63 | 0 |
| `R5_MultiRobot_Comm` | 12 | 0 |
| `Robotics_Embodied` | 42 | 3 |
| `Mechanical_Physics_AI` | 7 | 95 |
| `Mechatronics_PHM_Control` | 22 | 29 |
| `Smart_Manufacturing` | 2 | 23 |
| `Smart_Factory_DigitalTwin` | 0 | 0 |
| `R1` | 34 | 0 |
| `Adjacent` | 23 | 0 |
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

## 最近轮次记录（最多显示最近 25 轮）

| 轮次 | UTC 时间 | 主题批次 | 净增文献 | 净增数据集 | 新增清洗表 | 审计文件 |
|---:|---|---|---:|---:|---:|---|
| 1 | 2026-11-21T07:31:26Z | R1/R2/R5 Gap Search + ICRA 2025 | +36 | +34 | +0 | [round-01-audit.json](rounds/round-01-audit.json) |
| 2 | 2026-11-21T07:37:17Z | R1 Contact Assembly & Tactile + AAAI 2025 Robotics + Short Dataset Queries | +52 | +85 | +2 | [round-02-audit.json](rounds/round-02-audit.json) |
| 3 | 2026-11-21T07:44:04Z | Broad Engineering R3: R2_Aerial_Actuator / R5_MultiRobot_Comm | +94 | +107 | +3 | [round-03-audit.json](rounds/round-03-audit.json) |
