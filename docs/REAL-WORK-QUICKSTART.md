# 让真实工作更容易完成：real-work-first 档

> 目的：把「可辩护」优先改回「可完成」优先。**不降低科学诚信，只降低仪式成本。**

## 为什么需要它

改造前，`python -m scripts.researchctl gate-check --project my-phd` 报 **16 组 / 85 条**阻断，其中 70 条是「757 行人工筛选表未填写」，其余是新颖性矩阵字段迁移、假设审计时间戳、可选质量评估、以及 `jsonschema` 未安装导致的「validator unavailable」。而真人其实已经写了 `program/topic-decision.md`（6 KB）、`novelty-claim-matrix.json`（13 KB）、`hypothesis-register.json`（24 KB）。

也就是说：**材料齐了、决定做了，却过不了机器闸门**。这些检查里几乎没有一条在阻止造假，多数是格式、迁移、校准和可选依赖。

## 怎么开

默认**完全不变**（仍是完整协议），必须显式开启：

```bash
export DR_OS_WORK_PROFILE=minimal          # Windows: set DR_OS_WORK_PROFILE=minimal
```

或者直接用下面的 `decide` 命令，它会自动设置该变量。

## 三条硬条件（仍然阻断）

在 G1 下只保留真正防止「伪造博士选题」的检查：

1. `program/topic-decision.md` 非空、且由本人书写（不含 `HUMAN_INPUT_REQUIRED` 占位）；
2. `program/topic-shortlist.json` 列出至少三个真实候选；
3. `program/core-thesis.json` 声明一个 overarching 博士问题。

其余 80+ 条检查降级为**可见的非阻断观察项**，一条都不删除、不伪造、不标记为已验证。想看完整结果：

```bash
python -m scripts.real_work full-check --project my-phd
# 或 unset DR_OS_WORK_PROFILE 后运行原来的 gate-check
```

## 把必须由人做的工作变小

G1 之所以卡住，很大程度是 757 行人工筛选表加上一堆分散材料。两条命令把它们压缩到可操作规模，**但不代替你做任何判断**：

```bash
python -m scripts.real_work prepare-decision --project my-phd
python -m scripts.real_work split-screening --project my-phd --size 50
```

- `prepare-decision` 生成 `reports/G1-DECISION-SHEET.md`：把已有的 3 个候选、博士问题、`selection_decision` 当前状态与待办压到一页，留 3 个空位给你填。内容全部摘自现有文件，无新增断言、无推荐。
- `split-screening` 把 757 行拆成 16 个每批 50 行的 CSV 和 `INDEX.md`。四个 owner 列（`human_decision` / `human_reason` / `screened_by` / `screened_at`）原样留空；不做纳入/排除、不排序、不评分、不代填。

**重要前提**：`projects/my-phd/program/topic-decision.md` 目前是**建议稿、待负责人确认**，其第 7 节明确写「不建议在本轮对 G1 调用 ready 或任何闸门推进」，`program/topic-shortlist.json` 的 `selection_decision` 也是 `null`。也就是说最终选题决定**还没有做出**。因此下面的 `decide` 只能在你本人填完决定之后执行——控制平面负责登记你的决定，绝不替你做决定。

## 一条命令完成 G1 决策

```bash
# 1. 看现在卡在哪（只列 3 条硬条件）
python -m scripts.real_work status --project my-phd

# 2. 本人做出选题决定后，一条命令走完 check -> ready -> approve -> advance
python -m scripts.real_work decide --project my-phd \
  --actor "Hengyi Zang" --note "Selected C1 after reviewing the shortlist"
```

`--actor` 必须是真实人名，不能是 `deterministic-control-plane`；脚本绝不代填任何科学内容。新项目可以先生成**空**骨架：

```bash
python -m scripts.real_work bootstrap-g1 --project new-project
```

它只写三份带 `HUMAN_INPUT_REQUIRED` 的空模板，标题、理由、风险全部留白；若已有材料则不会覆盖（除非显式 `--force`）。

## 让真实模型调用跑得通

仓库里的 `gpt-6.1-sol` / `claude-opus-5-5` 等是固定路由身份，不一定是当前网关可用的型号。把真实型号交给控制平面：

```bash
python -m scripts.real_work configure-models \
  --sol <your-real-openai-model-id> \
  --opus <your-real-anthropic-model-id> \
  --deepseek <your-real-deepseek-id>
```

这会写 `config/model-routing.local.json`（已加入 `.gitignore`），由 `scripts.model_routing._apply_local_model_overrides()` 在加载策略时应用到路由表与 provider 白名单。**不改动仓库里的默认策略文件，也不猜测任何型号名。** 该文件存在时 `production_enabled()` 自动为真，无需再设 `DR_OS_ROUTING_PROFILE`。

检查真实运行还缺什么：

```bash
python -m scripts.real_work check-real --project my-phd
```

它会列出 API key、真实型号、`jsonschema` 等缺口和对应修复命令，只列不报错。

## 没有削弱的部分

- G1/G2 选题仍必须真人 `--actor` 批准，`researchctl approve` 的约束原样保留；
- 绝不自动投稿、不编造引用/数据/结果/审稿意见；
- 来源哈希、累计预算、失败与负结果留痕、角色隔离、输出 provenance 全部保留；
- G2–G5 仍走完整协议（`config/real-work.json` 的 `enabled_gates` 目前只有 `G1`）；
- 现有 195 个测试、69 个 schema、既有 CLI 行为默认完全不变。

## 回滚

改动前已打本地 tag：

```bash
git -C D:/ad/lunwen diff before-real-work-simplify      # 看全部改动
git -C D:/ad/lunwen checkout before-real-work-simplify -- .   # 全部还原
unset DR_OS_WORK_PROFILE                                 # 关闭精简档
rm D:/ad/lunwen/config/model-routing.local.json           # 移除本地真实型号
```

配置见 `config/real-work.json`；实现见 `scripts/real_work.py` 与 `scripts/researchctl.py::gate_errors`。
