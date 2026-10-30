# 四类模型复测与任务分工：2026-10-29 至 2026-10-30

本轮实测尚未全部完成。已取得 21 个身份、完整性和实扣费用均核对的响应；
Argon 原生接口的首个实验设计题返回 HTTP 400，随后无法唯一核对新扣费，原任务已停止。
不能将免费目录成功或这 21 个短题结果表述为正式论文、博士研究或整篇写作质量验收。

## 可复查的原始证据

- [云端原运行 40905696013](https://github.com/hengyizang/lunwen/actions/runs/40905696013)。
- [原账本](https://github.com/hengyizang/lunwen/blob/cloud-state/model-evaluation-20261029/trial-state/ledger.json)，停止时 Git blob：`65406a6cd6344c20ba4ec608ca12b0b8602c1a50`。
- 请求代码：`7ab623c3d1702d03d171bff3309d0b57a3ef87a1`。原计划、价格、六个材料和每次请求上限在账本 scope 内冻结。
- [最新免费元数据](https://github.com/hengyizang/lunwen/blob/cloud-state/model-evaluation-20261029/trial-state/metadata-40910119767.json)：读取目录和费用计数，不生成、不释放任何旧占用。

六个题目为抽取、代码审查、统计解释、区分性实验方案、英文改稿和证据冲突分析。
前 3 个是校准题，后 3 个是留出题；材料明确为合成软件检验样例。
Terra medium 只参加前 3 个题，不能将其三题均值与其他路线六题均值直接排行。
本助手逐条核对内容；没有独立人工盲评，机械关键词也不是科学质量评分。
固定顺序、推理输出量、缓存和单次时延均可能影响成本比较，未验证长期 SLA、真实长 PDF、工具调用或整篇成稿。

## 已完成的三题校准

| 精确路线（均为请求档位） | 有效响应 | 已核实实扣 CNY | 中位响应秒数 | 额外失败 |
| --- | ---: | ---: | ---: | --- |
| argon-native-high | 3/3 | 0.03432240 | 20.08 | 1 次 HTTP 400，费用未知 |
| argon-chat-high | 3/3 | 0.02928240 | 23.84 | 0 |
| terra-high | 3/3 | 0.00126206 | 4.35 | 0 |
| terra-medium | 3/3 | 0.00124506 | 4.93 | 0 |
| deepseek-high | 3/3 | 0.00244566 | 6.99 | 0 |
| kimi-high | 3/3 | 0.02396040 | 28.52 | 0 |
| sol-high | 3/3 | 0.00779800 | 10.86 | 0 |

全部有效抽取保留了负值、区间、缺失 p 值和非因果结论，均未把缺失值补成发现。
代码题均识别了丢弃数值零和空序列除零两个指定缺陷，并标明未执行测试。
统计题均未从跨零区间推断等价，且保留探索性子组的身份。

Terra high/medium 在这三道短题中较快、费用较低，high 的解释简明；
这支持优先验证其常规工程和局部改稿岗位，不能证明所有任务等质或 medium 普遍优于 high。
DeepSeek 的工程初审和来源约束解释有用；Kimi 同样保持核心数值及不确定性，
这次回答的费用没有低于 Terra 或 DeepSeek，不能仅因国产模型而认定更省钱。
Argon 两种接口各完成三题，说明短任务可用；它在统计题更冗长、耗时更多，
且原生接口随后失败，因此本轮不能据此主张 Argon 更适合统一撰写论文。
Argon 对增加种子以缩窄区间的建议还需核对独立统计单位，不能把随机种子自动当作新增独立样本。

## 型号与版本结论

- Argon 请求并返回 `gemini-4-argon`，分别使用原生和显式兼容文本接口；没有静默协议切换。
- Terra 请求并返回 `gpt-6.1-terra`，本轮渠道为 CodeKey Codex Pro。CheapAI Pro 当前目录没有该 ID，不假定不同站点都能调用。
- Kimi 请求并返回 `kimi-k3.1-pro`，使用 high 和原生规定的 `max_completion_tokens`；密钥只从 Actions Secrets 提供。
- DeepSeek 请求并返回中转 ID `deepseek-v4.1-flash`。官方当前 `deepseek-flash` 指向 V4.1-Flash-1017；
  中转未给日期快照或可核实映射，因此只能确认 V4.1 标识可用，不能认证它的底层就是 1017。
  [DeepSeek 官方型号说明](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。
- 严格返回 ID 是追溯条件，不能鉴定任何中转的真实模型权重或是否实际执行了请求档位。
  [Terra 官方接口](https://developers.openai.com/api/docs/models/gpt-6.1-terra)，
  [Kimi 官方接口与档位](https://platform.kimi.com/docs/guide/kimi-k3-1-pro-quickstart)。

## 当前暂停与可审查的隔离续跑

新失败请求为 `argon-native-high|discriminating-experiment`，
项目占用 `f705e87ba4514cb99c961768f59f4278`，全额上界 CNY 0.4321632。
同一 Gemini 密钥的原生和兼容接口均隔离，不能把换协议当作避开未知费用。
其共享活动票据 `381830bce3954c0fbc628b548e2b031e` 和原账本保持原状。

此前明确同意的旧费用例外不自动结清这次新请求。仓库 AGENTS.md 第 23 条规定
“Unknown charges stop new paid work”。原模式不能重开。用户在收到本次费用未核清及
隔离后只继续另外四个模型 12 项的说明后，于 2026-10-30 回复“继续”；该回复授权本次
隔离续跑例外，不释放未知占用，不增加 500 元总上限，不授权 Gemini 重试或其他新任务。

可执行方案只包含原 39 项中从未尝试的 12 项：
Terra high、DeepSeek high、Kimi high、Sol high，各执行实验设计、英文改稿、证据冲突 3 项。
合计预留上界 CNY 17.7485112，仍使用已有项目 CNY 500 上限。
没有 Gemini 请求、失败重发、新案例、付费裁判或扩大原请求总数。
续跑将写独立 continuation-ledger.json，冻结原账本、全部原材料及上限和新代码版本；
每次重新核对历史及本次未知费用的完整占用。另一笔新未知费用会再次停止全部新付费。

首次隔离续跑在 Terra 实验设计题成功后，DeepSeek 共享预留的写后核对读到分支旧版本，
在绑定费用快照和模型传输之前停止。其停止账本 blob 为
`4687efee7987c3ef0bd9749f75e11629555ef2b0`。已改为读取 PUT 返回的不可变 blob。
仅此一个固定的未发送中断可以按原代码位置、活动票据和无费用快照证明，撤销未发送预留；
原记录移入 preflight_events，保留旧 scope 和修复依据，再继续原题目一次。
这不结清任何真实未知费用，也不重发已发送请求。

本轮已核实新支出为 CNY 0.10031598，包含旧运行的项目已核实支出 CNY 0.18764158。
历史 Argon CNY 9.5836104、DeepSeek CNY 0.0625758 和本次 CNY 0.4321632 继续占用，
合计 CNY 10.0783494；它们没有被标为实扣已结清。未使用的 Codex 特惠旧占用也没有被释放。

## 生产分工与管理

[48 类任务分工及正常/突发复评](MODEL-TASK-ASSIGNMENTS-20261029.md) 已接到现有选择器和状态报告。
核心问题、创新、实验、统计结论、核心叙事保持 Astra high / Opus high；
常规工作保留 Sol high，DeepSeek 继续工程只读初审，Luna 保留已接受字段契约，确定性任务先用程序。
Terra、Kimi 和 Argon 兼容文本路线已登记为候选，并接入密钥和保守价格预留。
Terra 常规写入也必须通过原有同类任务、留出材料、独立人工评分及完整费用验收，
不能凭这次短测自动替代 Sol；核心科学下限不变，Kimi 不能成为持久科学文件作者或科学终审人。
本轮没有生成任何正式路由接纳记录，没有批准科研关卡，没有开始正式研究实验。

