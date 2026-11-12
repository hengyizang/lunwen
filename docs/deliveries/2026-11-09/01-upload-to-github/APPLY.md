# 如何把本次改动放到 GitHub

三个文件，按你的使用场景挑一个即可：

| 文件 | 用途 |
|---|---|
| `lunwen-real-work-first.patch` | **推荐**。标准 git patch，9 个文件 / +956 −1 行，可 `git apply`，也可贴进 PR |
| `lunwen-real-work-first-files.zip` | 9 个文件按仓库原路径打包，适合在 GitHub 网页上逐个上传 |
| `APPLY.md` | 本说明 |

已在 `D:\ad\lunwen` 上验证：`git apply --check --reverse lunwen-real-work-first.patch` 返回 0，即 patch 与当前工作区状态完全一致。

---

## 方式 A：本地 git apply（最省事）

```bash
cd /d/ad/lunwen                       # 或你 clone 下来的任意一份
git apply --check lunwen-real-work-first.patch   # 先检查
git apply lunwen-real-work-first.patch           # 应用
git diff --stat                                  # 应看到 9 个文件
git add -A && git commit -m "Add opt-in real-work-first profile"
git push origin main
```

如果目标仓库不是 `58ac455`（本次基线），`git apply` 可能因上下文不匹配而失败。此时用 `git apply --3way` 或改用方式 B。

## 方式 B：GitHub 网页上传

1. 解压 `lunwen-real-work-first-files.zip`，得到 `lunwen-real-work-first/` 目录，结构与仓库一致。
2. 在 GitHub 仓库页面进入对应目录（`config/`、`scripts/`、`docs/`、`tests/`、根目录），用 **Add file → Upload files** 上传：
   - 根目录：`.gitignore`（覆盖）
   - `config/`：`stages.json`（覆盖）、`real-work.json`（新增）
   - `scripts/`：`model_routing.py`、`researchctl.py`（覆盖）、`real_work.py`（新增）
   - `docs/`：`REAL-WORK-QUICKSTART.md`、`OWNER-DECISION-2026-11-09-REAL-WORK-FIRST.md`（新增）
   - `tests/`：`test_real_work.py`（新增）
3. 一次 commit 提交即可。

## 方式 C：作为 PR 内容

`.patch` 文件本身是纯文本，可以直接作为 PR 附件/描述贴上去，或发给协作者 `git am`（若改成 mailbox 格式）/`git apply`。

---

## 这 9 个文件分别是什么

| 文件 | 类型 | 作用 |
|---|---|---|
| `.gitignore` | 改 | 忽略 `config/model-routing.local.json` |
| `config/stages.json` | 改 | 新增 `blocking: false`、`observation_only`、`real_work_profile` 机器标记（原有字段未动） |
| `scripts/researchctl.py` | 改 | `gate_errors()` 包装为「默认完整协议 / 显式 opt-in 精简档」，原逻辑保留为 `_full_gate_errors()` |
| `scripts/model_routing.py` | 改 | 真实型号覆盖 `_apply_local_model_overrides()` + `production_enabled()` |
| `config/real-work.json` | 新 | 精简档配置：仅 `enabled_gates: ["G1"]`、3 条硬条件、非阻断清单、回滚 tag |
| `scripts/real_work.py` | 新 | 统一入口：`status` / `bootstrap-g1` / `decide` / `check-real` / `configure-models` / `split-screening` / `prepare-decision` / `full-check` |
| `docs/REAL-WORK-QUICKSTART.md` | 新 | 一页纸操作说明 |
| `docs/OWNER-DECISION-2026-11-09-REAL-WORK-FIRST.md` | 新 | 按 `AGENTS.md` rule 25 要求，具名记录授权、降级范围与保留底线 |
| `tests/test_real_work.py` | 新 | 9 个回归测试 |

---

## 不包含的内容（重要）

- **不包含** `AGENTS.md` rule 25、`docs/CODEX-CLOUD.md`、`docs/RESEARCH-AUTOMATION-TOOLKIT.md`、三份 `OWNER-DECISION-2026-11-09*` 其它文档、`skill_router.py`、`third_party_runtime.py`、`portability_probe.py`、`scientistic-agent-skills/` 等——这些是**另一个会话**产生的改动，我没有碰，也没有打进包里。如果你也要提交它们，请单独处理。
- **不包含** `projects/my-phd/` 下的本地数据（`reports/G1-DECISION-SHEET.md`、`reports/g1-screening-batches/`、选题材料等）。它们是本地工作产物，按项目约定不应进 GitHub。
- **不包含** Python 环境依赖（不是仓库文件）：
  ```bash
  python -m pip install "jsonschema>=4.23,<5" lxml \
      "numpy>=1.26,<3" "pandas>=2.1,<3" "PyMuPDF>=1.24,<2" \
      "pypdf>=5,<7" "python-pptx>=1.0,<2" "python-docx>=1.1,<2" "proselint==0.16.0" \
      "matplotlib>=3.8,<4" "statsmodels==0.15.0"
  ```
- **不包含** CCFA 固定资源（`third_party/ccfa-skills/`），它由 `python -m scripts.ccfa_runtime bootstrap` 联网生成。

---

## 应用后验证

```bash
python -m compileall -q scripts tests
python -m unittest discover -s tests -p "test_real_work.py" -q      # 期望 9 tests OK
python -m scripts.researchctl gate-check --project my-phd             # 默认完整协议，行为不变
DR_OS_WORK_PROFILE=minimal python -m scripts.researchctl gate-check --project my-phd
# 期望：G1 artifact and quality checks passed.
```

**默认行为完全不变**：不设置 `DR_OS_WORK_PROFILE`、且不存在 `config/model-routing.local.json` 时，仓库与改造前一致。

## 回滚

```bash
git apply --reverse lunwen-real-work-first.patch
# 或回到基线 tag： git checkout before-real-work-simplify -- .
unset DR_OS_WORK_PROFILE
rm -f config/model-routing.local.json
```
