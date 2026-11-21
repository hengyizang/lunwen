# 在聊天中推进研究

在 Codex、Claude 或当前可用的助手中打开仓库，直接给出研究问题、已有材料和希望得到的成果。助手读取相关证据，选择工具，完成实际工作并继续；模型品牌不限制谁能写正文。需要独立复核时再安排相应任务。

## 可以直接这样说

- “从这个问题开始一个项目，先读最接近的原始工作，形成可检验的研究问题。”
- “继续 P01，核对已有结果，完成能被证据支持的结果与讨论部分。”
- “比较这两种解释，找一个成本合适、能区分它们的试验。”
- “审查这组实验的独立单位、数据泄漏和不确定性；保留失败与不利结果。”
- “把已有结果做成图表并检查实际渲染，给我可编辑源文件。”
- “按这个目标期刊整理投稿包，核对文件和引用。”

候选数、论文数、方法、语言和交付格式由课题与用户目标决定。可以边读、边试、边写；探索、确认性检验、原文事实与推断应如实区分。未读的全文、尚未运行的实验和缺失结果不能写成已完成。

## 对应命令

```bash
python3 -m scripts.researchctl init --project my-research --question '当前研究问题'
python3 -m scripts.researchctl work --project my-research --paper P01 --task '核对最近工作并设计下一项检验'
python3 -m scripts.researchctl status --project my-research --json
python3 -m scripts.autopilot plan --project my-research --context '根据现有证据继续'
```

以上用于建立、记录或查看任务，不调用付费模型。配置了可用端点、模型与实际项目额度后，可以运行：

```bash
python3 -m scripts.autopilot start --project my-research --context '根据现有证据继续'
python3 -m scripts.autopilot resume --project my-research --paper P01 --context '完成当前任务'
```

`start` 兼容已有项目；`resume` 接续当前工作。`--stage` 是兼容任务标签，不是必须先通过的科研审批。新项目默认一篇；新证据形成独立贡献时，用 `researchctl add-paper --project my-research --question '新问题'` 追加。

普通工作无需切换 `DR_OS_WORK_PROFILE`，也不要求先执行 G0–G5。`gate-check/ready/approve/advance` 和 `real_work` 工具保留用于旧记录与特定操作，见[兼容说明](REAL-WORK-QUICKSTART.md)。

## 材料、工具和费用

提供当前任务所需的原文、数据或准确路径即可。项目中的其他文件不会因存在而自动算作已读。大材料应按科学问题选取完整相关部分，记录范围并保留原始材料；不能为节省上下文删去改变解释的反证。

MCP 的 `research_context`、`research_projects`、`research_route`、`research_status` 可用于发现项目和查看下一步；它们本身不启动付费模型。确定性脚本负责可复现的计算、解析、绘图与文件转换，模型用于需要判断的工作。选择当前可用的本地或云环境；D 盘、WSL2、GitHub runner 和全部可选包都不是聊天前提。

沿用实际授权和累计额度，不为每个已授权步骤重新询问。创建项目不授予支出，历史默认金额不是余额。计费凭据和未知费用状态按真实账本处理，失败调用也保留；额度不足时继续可完成的免费工作。费用查看不调用模型：

```bash
python3 -m scripts.api_orchestrator cost my-research
python3 -m scripts.api_orchestrator cost my-research --paper P01
```

密钥通过实际运行环境提供，不写入论文或 Git。已有会话授权不会由技能文本扩张；代外部发布或提交需要实际用户授权。生成本地包、完成软件测试、模型给出好评，分别只说明相应工作完成。

常用方法见 [skills](../skills/)、[工作流程](../references/workflow.md)和[科研诚信](../references/research-integrity.md)。历史日期文档保留其当时的事实，不用于推断今日服务状态或新增审批。
