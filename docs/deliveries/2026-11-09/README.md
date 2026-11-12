# lunwen 交付包（2026-11-09）

一个自包含压缩包，含本轮任务的**全部**产物：可直接上传 GitHub 的代码改动、应用说明、我的完整看法与改动记录、以及 16 份分析原始报告。

> 基线 commit：`58ac455`（Doctoral Research OS v2.3.0，#174）
> **我没有向 GitHub 推送任何内容，也没有创建 PR。** 所有改动都在本地工作区，上传与否由你决定。

---

## 目录结构

```
README.md                          本文件
MANIFEST.txt                       包内文件清单与大小
01-upload-to-github/                ← 传到 GitHub 用这个
│   ├── lunwen-real-work-first.patch        标准 git patch（9 文件 / +956 −1）
│   ├── APPLY.md                            三种应用方式、依赖、验证、回滚
│   └── repo-files/                         9 个改动文件，按仓库原路径展开
│       ├── .gitignore
│       ├── config/  stages.json, real-work.json
│       ├── scripts/ model_routing.py, researchctl.py, real_work.py
│       ├── docs/    REAL-WORK-QUICKSTART.md, OWNER-DECISION-2026-11-09-REAL-WORK-FIRST.md
│       └── tests/   test_real_work.py
02-opinion-record/
│   └── lunwen-全部看法与改动记录.md       整个对话里我的全部看法/评价/批评/建议/改动/自我修正
03-analysis-reports/
│   ├── 00-项目能力精读总报告.md          12 域能力全景、真实项目状态、风险、设计权衡
│   ├── 01-防幻觉过度性评估.md            定量证据、四种代价、分层处置建议
│   ├── 02-真实工作优先改造报告.md        改造清单、验证结果、未做事项、回滚
│   ├── 03-继续工作小结.md                决策单、757 行分批、全量测试、环境补齐
│   └── detailed/                        12 份逐文件精读分报告（约 1.4 MB）
│       ├── scripts-G01..G08.md
│       ├── tests-G01.md / tests-G02.md
│       ├── contracts-and-state.md
│       └── third-party.md
```

## 最快用法

**方式 A — 本地应用并推送（推荐）**

```bash
cd /d/ad/lunwen                                  # 或你 clone 下来的任意一份
git apply --check 01-upload-to-github/lunwen-real-work-first.patch
git apply 01-upload-to-github/lunwen-real-work-first.patch
git add -A && git commit -m "Add opt-in real-work-first profile"
git push origin main
```

**方式 B — GitHub 网页上传**

把 `01-upload-to-github/repo-files/` 里的 9 个文件按相同路径上传到仓库（根目录 / `config/` / `scripts/` / `docs/` / `tests/`），一次 commit。

**方式 C — 只想看结论**

直接读 `02-opinion-record/lunwen-全部看法与改动记录.md`。

## 应用后验证

```bash
python -m compileall -q scripts tests
python -m unittest discover -s tests -p "test_real_work.py" -q      # 期望 9 tests OK
python -m scripts.researchctl gate-check --project my-phd             # 默认完整协议，行为不变
DR_OS_WORK_PROFILE=minimal python -m scripts.researchctl gate-check --project my-phd
# 期望：G1 artifact and quality checks passed.
```

**默认行为完全不变**：不设置 `DR_OS_WORK_PROFILE`、且不存在 `config/model-routing.local.json` 时，仓库与改造前一致。精简档是显式 opt-in。

## 包里**没有**的东西（刻意的）

- 另一会话产生的改动：`AGENTS.md` rule 25、`docs/CODEX-CLOUD.md`、`docs/RESEARCH-AUTOMATION-TOOLKIT.md`、三份 `OWNER-DECISION-2026-11-09*` 其它文档、`skill_router.py`、`third_party_runtime.py`、`portability_probe.py`、`scientistic-agent-skills/` 等。我一行未碰，请单独处理。
- `projects/my-phd/` 下的本地数据（决策单、16 批筛选表、选题材料）。按项目约定不进 GitHub。
- Python 依赖（不是仓库文件）：`jsonschema`, `lxml`, `numpy`, `pandas`, `PyMuPDF`, `pypdf`, `python-pptx`, `python-docx`, `proselint`, `matplotlib`, `statsmodels`。安装命令见 `APPLY.md`。
- CCFA 固定资源：由 `python -m scripts.ccfa_runtime bootstrap` 联网生成（本次因代理 502 未完成）。

## 回滚

```bash
git apply --reverse 01-upload-to-github/lunwen-real-work-first.patch
# 或回到基线 tag： git checkout before-real-work-simplify -- .
unset DR_OS_WORK_PROFILE
rm -f config/model-routing.local.json
```

## 一句话背景

这套系统把「不许造假」做到了极致，却因此没能产出任何科研成果（G1 未批准、六篇空模板、零实验）。本轮改造给出一个**显式开启**的精简档，把 G1 从 85 条仪式性阻断降到 3 条真正防造假的硬条件；规则 1–24、真人 G1/G2 决定、绝不自动投稿、证据链与预算全部保留。我拒绝替真人做 G1 选题决定——理由详见观点记录第 6 节。
