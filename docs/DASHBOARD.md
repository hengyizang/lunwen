# 云端控制与旧客户端迁移

项目采用 `cloud_only`。独立本地 HTTP 面板、浏览器密钥表单和重复命令拼装已退休。
原生 CLI 与 GitHub 云端执行器保留；现有研究数据、预算、审批和模型路由不迁移。

| 原面板操作 | 当前入口 |
| --- | --- |
| 配置与状态 | 云端 `preflight` / `status` |
| 创建项目与续跑 | 云端 `init` / `cycle` / `continuation` |
| G1/G2 选题确认 | 云端 `review_dossier` 与实际所有者决定 |
| 数据、实验、写作与打包 | 当前阶段的原生控制与云端任务 |
| 日志与导出 | GitHub Actions 运行记录、状态分支与输出 artifacts |

完整字段及边界见 [CLOUD-RESEARCH.md](CLOUD-RESEARCH.md)，持续运行见
[CONTINUOUS-CLOUD-RESEARCH.md](CONTINUOUS-CLOUD-RESEARCH.md)。
