# G1 持续自动文献与数据检索及清洗目录

- 本目录由本地自动轮询器 (`g1_runner.py`) 以 **CNY 0** 付费调用（仅开放学术/数据集 API）持续维护，严格与基线冻结目录 [2026-11-21](../2026-11-21/README.md) 隔离且跨库去重。
- 原始数据集仅下载至 Git 仓库外的 `raw-staging/` 进行 SHA-256 / MD5 校验与确定性清洗，不向仓库上传原始二进制数据或归档。
- G1 选题仍保持待人工决策状态（`state/run.json` 未被自动推进）。

## 累计产出概览

- **已完成轮次**：1
- **最近更新时间 (UTC)**：2026-11-21T07:31:26Z
- **累计净新增文献** (`literature-new.csv`)：36 条（已与基线 15,910 条去重）
- **累计净新增数据集** (`datasets-new.csv`)：34 个（已与基线 191 个去重）
- **累计开放阅读队列** (`reading-queue-new.csv`)：32 条
- **累计已完成确定性清洗数据集**：0 个
- **云端 `[research-cloud]` 自动调度门禁**：`skipped_baseline_checkpoint_error: unsupported checkpoint file requires an explicit storage plan: evidence/g1-collection/2026-11-21/audit/SHA256SUMS`

## 主要索引文件

- [净新增文献总表 (literature-new.csv)](literature-new.csv)
- [净新增数据集总表 (datasets-new.csv)](datasets-new.csv)
- [净新增开放阅读队列 (reading-queue-new.csv)](reading-queue-new.csv)
- [轮次队列与状态 (queue-state.json)](queue-state.json)

## 已校验并确定性清洗的公开数据集

| Slug | 名称 | DOI / 入口 | 清洗模式 | 行数 | 原始文件 SHA-256 (前12位) | 清洗表 / 来源 / 脚本 |
|---|---|---|---|---:|---|---|

## 最近轮次记录

| 轮次 | UTC 时间 | 主题批次 | 净增文献 | 净增数据集 | 新增清洗表 | 审计文件 |
|---:|---|---|---:|---:|---:|---|
| 1 | 2026-11-21T07:31:26Z | R1/R2/R5 Gap Search + ICRA 2025 | +36 | +34 | +0 | [round-01-audit.json](rounds/round-01-audit.json) |
