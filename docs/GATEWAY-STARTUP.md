# 中转站 API 云端启动

本入口用于 OpenAI 负责写入、Claude 负责只读规划和独立审查的科研流程。运行环境由 GitHub Actions 安装，无需本地 Python、Docker、WSL2 或 CC Switch。已有项目继续读取 `cloud-state/my-phd`，不会重新初始化或重置预算。

## 提供哪些配置

向中转站确认：HTTPS 基础地址、API Key、两个准确模型 ID、OpenAI 支持的协议，以及两个模型实际人民币输入/输出单价（每百万 token）。不能用官方标价猜测中转站价格。密钥只放 GitHub 仓库的 **Settings → Secrets and variables → Actions → Secrets**，其余配置放 **Variables**；不要把密钥写进聊天记录、Issue、代码或运行输入。

两个模型共用一个地址和密钥时，填写 `UUAPI_API_KEY`（Secret）和 `UUAPI_BASE_URL`（Variable）。

如果两个模型使用不同中转站或不同密钥，填写下面两组。每一组的地址和密钥必须同时填写；不完整的独立配置会阻止启动，不会把共用密钥发送到另一站点。

| 用途 | Secret | Variable |
|---|---|---|
| OpenAI 写入与修订 | `UUAPI_OPENAI_API_KEY` | `UUAPI_OPENAI_BASE_URL` |
| Claude 规划与审查 | `UUAPI_ANTHROPIC_API_KEY` | `UUAPI_ANTHROPIC_BASE_URL` |

完整独立配置优先于共用配置。也可让一组使用完整独立配置，另一组使用共用配置。上述 `UUAPI_` 名称沿用历史适配器命名，并不要求购买某一家中转站。

以下 Variables 在两种配置方式下都需要：

| Variable | 填写方式 |
|---|---|
| `UUAPI_OPENAI_MODEL` | 中转站提供的准确 OpenAI 模型 ID |
| `UUAPI_ANTHROPIC_MODEL` | 中转站提供的准确 Claude 模型 ID |
| `UUAPI_OPENAI_PROTOCOL` | `responses`（默认）或 `chat_completions` |
| `UUAPI_OPENAI_CHAT_TOKEN_FIELD` | 仅 Chat Completions 使用；默认 `max_completion_tokens`，旧网关可明确选择 `max_tokens` |
| `DR_OS_MODEL_PRICING_JSON` | 以两个准确模型 ID 为键，每个对象包含数值 `input_per_million`、`output_per_million`；单位是人民币/百万 token |

基础地址可以是 `https://站点`、`https://站点/v1` 或带中转前缀的 `https://站点/前缀/v1`。不要填写完整的 `/responses`、`/chat/completions` 或 `/messages` 请求地址；检查器会明确拒绝。地址不可包含密钥、查询参数或用户名密码。

Claude 使用 Anthropic Messages 协议。OpenAI 的 Responses 请求使用 `max_output_tokens`；Chat Completions 默认使用 `max_completion_tokens`，仅在网关文档明确要求时选旧字段。参数依据 [OpenAI Chat API](https://developers.openai.com/api/reference/resources/chat) 和 [token 计数文档](https://developers.openai.com/api/docs/guides/token-counting)（核对日期 2026-10-02）。不通过重试付费请求来猜协议或参数，也不自动替换模型。

## 检查与立即启动

1. 在仓库 **Actions → Continuous owner-approved research → Run workflow** 中选择 `main`，模式选择 **check**。这是默认选项，不调用模型，不请求新预算，不改变科研审批。
2. 查看运行摘要和产物中的 `gateway-startup.json`。它列出两个实际目标地址、协议、模型 ID、缺失配置、已用/预留/剩余额度，以及当前阶段是否允许继续。它不会展示密钥。
3. 当 `configuration_ready` 和 `ready_to_continue` 都为 `true`，选择同一入口的 **start**。它立即排队执行当前阶段；具体启动时间由 GitHub runner 排队情况决定。后续健康循环自动衔接，无需本地保持在线。

已有持续运行授权时，定时作业也会在配置齐全后继续工作；**check 本身不暂停已授权的定时流程**。`start` 复用已经记录的授权，不能越过累计 300 元及之后每次追加 300 元的边界。尚未获批的项目不会因填入密钥或点击 start 而得到预算或 G0–G5 审批。

`configuration_ready=true` 只说明配置格式和必填项完整；`ready_to_continue=true` 另要求项目、人工审批和预算状态允许当前阶段工作。两者均不证明密钥真实有效、余额充足、站点在线或模型科研质量合格。首次真实运行仍须核对返回的准确模型身份、usage、初次调用收据和费用；站点端鉴权或服务故障无法在收到密钥前验证。

每次请求都先持久化预算预留，再发送一次请求。超时、模型身份不符或费用不明会暂停后续付费步骤，保留预留以供对账，不自动付费重试。科研证据缺失或人工闸门也会正常暂停，按 [云端人工审核](CLOUD-HUMAN-CONTROLS.md) 处理。

## 验证边界

CI 的 `Gateway startup and five-role cycle` 使用模拟 HTTP 响应运行实际适配器、五角色流程、预算模块、独立审查、写入来源记录和隔离 Git 远端预留。覆盖共享/独立中转站、Responses、两种 Chat token 字段；20 次请求全部为合成测试，不联系模型服务。收据包含产物哈希、代码提交和运行编号。

这证明软件配置与控制流程的相应测试通过；不能证明真实中转站已接通，更不能代表六篇论文或任何科研阶段已完成。真实科研依赖当前项目证据和明确人工审核。
