# 默认按研究任务工作

研究优先现在是默认路径，不需要启用一个“精简档”。从一个问题和一篇论文开始，记录下一项有用工作，然后读取证据、执行、分析或写作。先前的三候选、六篇论文、G1/G2 人工批准和全部阶段评分不再是普通工作的前置条件。

```bash
python3 -m scripts.researchctl init --project demo --question '当前研究问题'
python3 -m scripts.researchctl work --project demo --paper P01 --task '完成下一项有区分力的工作'
python3 -m scripts.researchctl status --project demo --json
python3 -m scripts.autopilot plan --project demo
```

这些命令不进行付费调用。实际模型与额度准备好后，用 `autopilot start` 或 `autopilot resume` 执行；新项目额度初始为零，必须沿用真实已授权额度。按研究需要追加论文：

```bash
python3 -m scripts.researchctl add-paper --project demo --question '另一个有独立证据的问题'
python3 -m scripts.autopilot resume --project demo --paper P01 --context '核对原文并完善当前结果'
```

## 已有项目与旧工具

已有材料和历史记录保持原样。`--stage` 可指定兼容任务标签；`status --legacy-checks` 或 `gate-check` 用来查看旧诊断，诊断结果不替代科学判断，也不是新工作要先凑齐的表格。

`scripts.real_work` 保留以下实用命令：

| 命令 | 实际用途 |
| --- | --- |
| `status --project demo` | 查看当前研究任务与真实阻碍。 |
| `check-real --project demo` | 查看当前配置、凭据与预算缺口，不调用模型。 |
| `configure-models --sol <实际模型ID>` | 保存明确提供的真实模型映射到已忽略的本地配置；不猜测可用性。其他路由参数见 `--help`。 |
| `prepare-decision --project demo` | 汇集已有方向材料，帮助形成或记录选择。 |
| `split-screening --project demo --size 50` | 分批查看大筛选表，保留原数据和实际判断者。 |
| `decide --project demo --actor '实际决定者' --note '实际选择'` | 记录已作出的选择，不伪造科学批准。 |
| `bootstrap-g1`、`full-check` | 兼容旧骨架和诊断；新项目用 `researchctl init/work`。 |

新任务可以由模型协助阅读、筛选、分析和写作。实际动作主体、来源、执行结果与费用必须如实记录；生成模板不是科学内容，模型判断不是人的批准。

## 实施与历史范围

旧版本文中“16组/85条阻断”“757行筛选表”、当时的选题状态、测试数量和本地 tag，只描述某次历史快照，不能据此判断当前 `my-phd` 云项目。这里不再提供把整个工作区回退到该 tag 的命令。需要恢复具体文件时，先审阅对应版本与当前改动。

当前入口见 [README](../README.md)，设计与实施边界见 [RESEARCH-FIRST-REDESIGN](RESEARCH-FIRST-REDESIGN.md)。
