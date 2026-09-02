#!/usr/bin/env python3
"""Local-only visual control center for the Doctoral Research OS.

The dashboard never persists API keys. It binds to loopback, delegates every
research mutation to the existing command-line control plane, and keeps human
approval gates intact.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import researchctl  # noqa: E402
from scripts.data_discovery import PROVIDERS as DATA_PROVIDERS  # noqa: E402
from scripts.network_safety import NetworkSafetyError, validate_https_url  # noqa: E402


ASSET_ROOT = ROOT / "dashboard"
PROJECTS_ROOT = ROOT / "projects"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
PAPER_RE = re.compile(r"^P[0-9]{2}$")
RUN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*[^\s,;]+")
MAX_BODY_BYTES = 128 * 1024
MAX_LOG_LINES = 1200

PROVIDER_INFO = {
    "datacite": ("DataCite", "跨机构 DOI 元数据聚合"),
    "zenodo": ("Zenodo", "科研数据与可复现档案"),
    "huggingface": ("Hugging Face", "机器学习与多模态数据"),
    "openml": ("OpenML", "机器学习基准与任务"),
    "figshare": ("Figshare", "通用研究数据仓储"),
    "dryad": ("Dryad", "同行评审论文关联数据"),
    "dataverse": ("Harvard Dataverse", "大学与社会科学数据"),
    "datagov": ("Data.gov", "美国政府及 NASA 等机构元数据"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def bounded_text(value: Any, field_name: str, maximum: int, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是文本")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{field_name} 不能为空")
    if len(value) > maximum:
        raise ValueError(f"{field_name} 最多允许 {maximum} 个字符")
    return value


def validate_slug(value: Any) -> str:
    slug = bounded_text(value, "项目名", 63, required=True)
    if not SLUG_RE.fullmatch(slug):
        raise ValueError("项目名只能使用 2–63 位小写字母、数字和连字符")
    return slug


def safe_project_path(slug: str, value: Any, suffix: str | None = None) -> Path:
    relative = Path(bounded_text(value, "项目文件路径", 300, required=True))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("项目文件路径必须是项目内的相对路径")
    target = (PROJECTS_ROOT / slug / relative).resolve()
    project = (PROJECTS_ROOT / slug).resolve()
    if target != project and project not in target.parents:
        raise ValueError("项目文件路径超出项目目录")
    if suffix and target.suffix.lower() != suffix:
        raise ValueError(f"项目文件必须使用 {suffix} 扩展名")
    return target


@dataclass
class SessionConfig:
    api_key: str = field(default_factory=lambda: os.environ.get("UUAPI_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.environ.get("UUAPI_BASE_URL", ""))
    anthropic_model: str = field(
        default_factory=lambda: os.environ.get("UUAPI_ANTHROPIC_MODEL", "")
    )
    openai_model: str = field(
        default_factory=lambda: os.environ.get("UUAPI_OPENAI_MODEL", "")
    )
    tavily_key: str = field(default_factory=lambda: os.environ.get("TAVILY_API_KEY", ""))
    strict_model_id: bool = field(
        default_factory=lambda: os.environ.get("UUAPI_STRICT_MODEL_ID", "true").lower()
        not in {"0", "false", "no"}
    )

    def public(self) -> dict[str, Any]:
        return {
            "key_configured": bool(self.api_key),
            "base_url": self.base_url,
            "anthropic_model": self.anthropic_model,
            "openai_model": self.openai_model,
            "tavily_configured": bool(self.tavily_key),
            "strict_model_id": self.strict_model_id,
            "ready": all(
                (self.api_key, self.base_url, self.anthropic_model, self.openai_model)
            ),
            "storage": "仅当前客户端进程内存",
        }

    def child_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        values = {
            "UUAPI_API_KEY": self.api_key,
            "UUAPI_BASE_URL": self.base_url,
            "UUAPI_ANTHROPIC_MODEL": self.anthropic_model,
            "UUAPI_OPENAI_MODEL": self.openai_model,
            "UUAPI_STRICT_MODEL_ID": "true" if self.strict_model_id else "false",
            "TAVILY_API_KEY": self.tavily_key,
            "PYTHONUNBUFFERED": "1",
        }
        for name, value in values.items():
            if value:
                env[name] = value
            else:
                env.pop(name, None)
        return env

    def secrets(self) -> list[str]:
        return [item for item in (self.api_key, self.tavily_key) if item]


def update_config(config: SessionConfig, payload: dict[str, Any]) -> None:
    api_key = bounded_text(payload.get("api_key", ""), "API Key", 4096)
    tavily_key = bounded_text(payload.get("tavily_key", ""), "Tavily Key", 4096)
    base_url = bounded_text(payload.get("base_url", config.base_url), "Base URL", 500)
    anthropic = bounded_text(
        payload.get("anthropic_model", config.anthropic_model), "Claude 模型", 200
    )
    openai = bounded_text(
        payload.get("openai_model", config.openai_model), "Codex/OpenAI 模型", 200
    )
    if base_url:
        try:
            base_url = validate_https_url(base_url, "UUAPI Base URL").rstrip("/")
        except NetworkSafetyError as exc:
            raise ValueError(str(exc)) from exc
    if payload.get("clear_api_key") is True:
        config.api_key = ""
    elif api_key:
        config.api_key = api_key
    if payload.get("clear_tavily_key") is True:
        config.tavily_key = ""
    elif tavily_key:
        config.tavily_key = tavily_key
    config.base_url = base_url
    config.anthropic_model = anthropic
    config.openai_model = openai
    config.strict_model_id = payload.get("strict_model_id", True) is not False


@dataclass
class Job:
    job_id: str
    action: str
    label: str
    project: str | None
    command: list[str]
    status: str = "queued"
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    completed_at: str | None = None
    return_code: int | None = None
    lines: list[str] = field(default_factory=list)
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    cancel_requested: bool = False

    def append(self, line: str) -> None:
        self.lines.append(line.rstrip("\n"))
        if len(self.lines) > MAX_LOG_LINES:
            del self.lines[: len(self.lines) - MAX_LOG_LINES]

    def public(self, include_log: bool = False) -> dict[str, Any]:
        value = {
            "job_id": self.job_id,
            "action": self.action,
            "label": self.label,
            "project": self.project,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "return_code": self.return_code,
            "cancel_requested": self.cancel_requested,
        }
        if include_log:
            value["log"] = "\n".join(self.lines)
        else:
            value["tail"] = self.lines[-8:]
        return value


class JobManager:
    def __init__(self, config: SessionConfig) -> None:
        self.config = config
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()
        self.capacity = threading.BoundedSemaphore(3)

    def redact(self, text: str) -> str:
        for secret in self.config.secrets():
            text = text.replace(secret, "[REDACTED]")
        return SECRET_PATTERN.sub(lambda match: match.group(1) + "=[REDACTED]", text)

    def start(
        self,
        action: str,
        label: str,
        command: list[str],
        project: str | None,
    ) -> Job:
        with self.lock:
            if project:
                conflict = next(
                    (
                        item
                        for item in self.jobs.values()
                        if item.project == project and item.status in {"queued", "running"}
                    ),
                    None,
                )
                if conflict:
                    raise ValueError(
                        f"项目 {project} 已有任务正在运行：{conflict.label}"
                    )
            job = Job(uuid4().hex[:12], action, label, project, command)
            self.jobs[job.job_id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
        with self.capacity:
            with self.lock:
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.completed_at = utc_now()
                    return
                job.status = "running"
                job.started_at = utc_now()
            try:
                process = subprocess.Popen(
                    job.command,
                    cwd=ROOT,
                    env=self.config.child_environment(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                job.process = process
                assert process.stdout is not None
                for line in process.stdout:
                    with self.lock:
                        job.append(self.redact(line))
                return_code = process.wait()
                with self.lock:
                    job.return_code = return_code
                    if job.cancel_requested:
                        job.status = "cancelled"
                    else:
                        job.status = "succeeded" if return_code == 0 else "failed"
            except Exception as exc:  # Keep the dashboard alive around child failures.
                with self.lock:
                    job.append(self.redact(f"dashboard error: {exc}"))
                    job.return_code = -1
                    job.status = "failed"
            finally:
                with self.lock:
                    job.completed_at = utc_now()
                    job.process = None

    def cancel(self, job_id: str) -> Job:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise ValueError("任务不存在")
            if job.status not in {"queued", "running"}:
                raise ValueError("任务已经结束")
            job.cancel_requested = True
            process = job.process
        if process and process.poll() is None:
            process.terminate()
        return job

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            ordered = sorted(self.jobs.values(), key=lambda item: item.created_at, reverse=True)
            return [item.public() for item in ordered[:60]]

    def get(self, job_id: str) -> Job:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise ValueError("任务不存在")
            return job


def project_state(slug: str) -> dict[str, Any]:
    try:
        state = researchctl.load_state(slug)
        errors = researchctl.gate_errors(slug, state.get("gate"))
    except Exception as exc:
        return {
            "project": slug,
            "status": "invalid",
            "stage": "unknown",
            "gate": None,
            "gate_ready": False,
            "gate_errors": [str(exc)],
            "gate_error_count": 1,
            "next_action": "修复项目状态文件",
            "risk": "high",
        }
    status = state.get("status")
    if status == "awaiting_work":
        next_action = "运行当前阶段" if errors else "检查产物并标记 ready"
    elif status == "awaiting_approval":
        next_action = "人工审批，或 reopen 后修改"
    elif status == "approved":
        next_action = "advance 进入下一阶段"
    elif status == "submission_ready":
        next_action = "逐篇生成并人工检查投稿包"
    else:
        next_action = "检查项目状态"
    risk = "attention" if errors else "clear"
    if status == "awaiting_approval":
        risk = "decision"
    return {
        **state,
        "gate_ready": bool(state.get("gate")) and not errors,
        "gate_errors": errors[:40],
        "gate_error_count": len(errors),
        "next_action": next_action,
        "risk": risk,
    }


def project_summaries() -> list[dict[str, Any]]:
    if not PROJECTS_ROOT.is_dir():
        return []
    summaries = []
    for path in sorted(PROJECTS_ROOT.iterdir()):
        if (
            path.is_dir()
            and SLUG_RE.fullmatch(path.name)
            and (path / "state" / "run.json").is_file()
        ):
            summaries.append(project_state(path.name))
    return summaries


def _token_totals(project: Path) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "api_runs": 0}
    manifests = list((project / "api_runs").glob("*/manifest.json"))
    totals["api_runs"] = len(manifests)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = key.lower()
                if isinstance(item, int) and lowered in {"input_tokens", "prompt_tokens"}:
                    totals["input_tokens"] += item
                elif isinstance(item, int) and lowered in {"output_tokens", "completion_tokens"}:
                    totals["output_tokens"] += item
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for manifest in manifests:
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        visit(payload.get("usage", {}))
    return totals


def project_detail(slug: str) -> dict[str, Any]:
    slug = validate_slug(slug)
    project = PROJECTS_ROOT / slug
    if not project.is_dir():
        raise ValueError("项目不存在")
    state = project_state(slug)
    reports: list[dict[str, Any]] = []
    for path in sorted((project / "data").glob("discovery-*.json"), reverse=True)[:12]:
        try:
            if path.stat().st_size > 8 * 1024 * 1024:
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        reports.append(
            {
                "path": path.relative_to(project).as_posix(),
                "created_at": report.get("created_at"),
                "queries": report.get("queries") or [report.get("query")],
                "provider_count": report.get("provider_count", len(report.get("providers", []))),
                "candidate_count": report.get("candidate_count", 0),
                "candidates": report.get("candidates", [])[:100],
                "ranking_note": report.get("ranking_note"),
            }
        )
    registry = project / "experiments" / "registry.jsonl"
    attempts = 0
    if registry.is_file():
        attempts = sum(1 for line in registry.read_text(encoding="utf-8").splitlines() if line.strip())
    datasets = project / "data" / "datasets.jsonl"
    dataset_count = 0
    if datasets.is_file():
        dataset_count = sum(1 for line in datasets.read_text(encoding="utf-8").splitlines() if line.strip())
    venues = sorted(path.parent.name for path in (ROOT / "venues").glob("*/venue.json"))
    return {
        "state": state,
        "history": list(reversed(state.get("history", [])))[:30],
        "data_reports": reports,
        "metrics": {
            **_token_totals(project),
            "dataset_manifests": dataset_count,
            "experiment_attempts": attempts,
            "papers_ready": sum(
                1 for value in state.get("paper_statuses", {}).values() if value == "submission_ready"
            ),
            "paper_count": state.get("paper_count", 0),
        },
        "venues": venues,
    }


def build_command(action: str, payload: dict[str, Any]) -> tuple[list[str], str, str | None]:
    python = sys.executable
    if action == "health":
        command = [python, "scripts/api_orchestrator.py", "health", "--provider", "uuapi-anthropic", "--provider", "uuapi-openai"]
        if payload.get("live") is True:
            command.append("--live")
        return command, "模型连接检查" + ("（计费探针）" if payload.get("live") is True else ""), None
    if action == "balance":
        return [python, "scripts/api_orchestrator.py", "balance"], "查询 UUAPI 余额", None

    slug = validate_slug(payload.get("project"))
    project = PROJECTS_ROOT / slug
    if action == "start":
        if project.exists():
            raise ValueError("项目已经存在；请选择项目后运行当前阶段")
        context = bounded_text(payload.get("context"), "研究背景与约束", 30_000, required=True)
        return ["bash", "scripts/start.sh", slug, context], "创建项目并运行 G0", slug
    if not project.is_dir():
        raise ValueError("项目不存在")
    state = researchctl.load_state(slug)

    if action == "cycle":
        if state.get("status") != "awaiting_work":
            raise ValueError("只有 awaiting_work 状态可以运行模型；请先完成当前审批动作")
        stage = str(state["stage"])
        context = bounded_text(payload.get("context"), "阶段补充说明", 30_000)
        query = bounded_text(payload.get("discovery_query"), "检索词", 3000)
        try:
            tokens = int(payload.get("max_output_tokens", 12000))
        except (TypeError, ValueError) as exc:
            raise ValueError("最大输出 Token 必须是整数") from exc
        if not 1000 <= tokens <= 100_000:
            raise ValueError("最大输出 Token 必须在 1000–100000 之间")
        command = [
            python,
            "scripts/api_orchestrator.py",
            "cycle",
            slug,
            stage,
            "--planner-provider",
            "uuapi-anthropic",
            "--writer-provider",
            "uuapi-openai",
            "--critic-provider",
            "uuapi-anthropic",
            "--max-output-tokens",
            str(tokens),
        ]
        if context:
            command.extend(["--context", context])
        if query:
            command.extend(["--discovery-query", query])
        return command, f"运行 {stage} / {state.get('gate')}", slug

    if action == "data_search":
        raw_queries = payload.get("queries")
        if isinstance(raw_queries, str):
            queries = [line.strip() for line in raw_queries.splitlines() if line.strip()]
        elif isinstance(raw_queries, list):
            queries = [bounded_text(item, "数据检索词", 500, required=True) for item in raw_queries]
        else:
            queries = []
        queries = list(dict.fromkeys(queries))
        if not 1 <= len(queries) <= 12:
            raise ValueError("请输入 1–12 行不同的数据检索词")
        selected = payload.get("providers") or list(DATA_PROVIDERS)
        if not isinstance(selected, list) or not selected:
            raise ValueError("至少选择一个数据源")
        selected = list(dict.fromkeys(str(item) for item in selected))
        unknown = sorted(set(selected) - set(DATA_PROVIDERS))
        if unknown:
            raise ValueError("未知数据源：" + ", ".join(unknown))
        try:
            limit = int(payload.get("limit", 20))
        except (TypeError, ValueError) as exc:
            raise ValueError("每个来源的结果数必须是整数") from exc
        if not 1 <= limit <= 50:
            raise ValueError("每个来源的结果数必须在 1–50 之间")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = project / "data" / f"discovery-broad-{stamp}.json"
        command = [python, "scripts/data_discovery.py", queries[0]]
        for query in queries[1:]:
            command.extend(["--query", query])
        for provider in selected:
            command.extend(["--provider", provider])
        command.extend(
            ["--limit", str(limit), "--max-candidates", "500", "--project", slug, "--output", str(output)]
        )
        return command, f"广域数据搜索（{len(queries)} 查询 × {len(selected)} 来源）", slug

    note = bounded_text(payload.get("note"), "说明", 2000)
    if action == "gate_check":
        return [python, "scripts/researchctl.py", "gate-check", "--project", slug], "检查当前闸门", slug
    if action == "ready":
        if not note:
            raise ValueError("标记 ready 前必须填写人工检查说明")
        return [python, "scripts/researchctl.py", "ready", "--project", slug, "--note", note], "锁定当前闸门产物", slug
    if action == "reopen":
        if not note:
            raise ValueError("重新打开闸门必须填写原因")
        return [python, "scripts/researchctl.py", "reopen", "--project", slug, "--note", note], "重新打开当前闸门", slug
    if action == "approve":
        actor = bounded_text(payload.get("actor"), "审批人", 200, required=True)
        gate = state.get("gate")
        if not gate:
            raise ValueError("项目已经没有待审批闸门")
        return [python, "scripts/researchctl.py", "approve", "--project", slug, "--gate", str(gate), "--actor", actor, "--note", note], f"人工批准 {gate}", slug
    if action == "advance":
        return [python, "scripts/researchctl.py", "advance", "--project", slug], "进入下一阶段", slug
    if action == "experiment":
        command = [python, "scripts/experiment_runner.py", "--project", slug]
        run_id = bounded_text(payload.get("run_id"), "运行 ID", 128)
        if run_id:
            if not RUN_RE.fullmatch(run_id):
                raise ValueError("运行 ID 含有不安全字符")
            command.extend(["--run", run_id])
        return command, "执行已批准实验" + (f"：{run_id}" if run_id else ""), slug
    if action in {"dataset_validate", "dataset_download"}:
        manifest = safe_project_path(slug, payload.get("manifest"), ".json")
        command = [python, "scripts/dataset_fetch.py", "validate", str(manifest)]
        label = "验证数据清单"
        if action == "dataset_download":
            if payload.get("accept_license") is not True:
                raise ValueError("下载前必须确认你已经核验许可证")
            command = [python, "scripts/dataset_fetch.py", "download", str(manifest), str(project / "data" / "raw"), "--accept-license"]
            label = "下载并校验已批准数据"
        return command, label, slug
    if action == "set_venue":
        paper = bounded_text(payload.get("paper"), "论文编号", 3, required=True)
        venue = bounded_text(payload.get("venue"), "期刊配置", 80, required=True)
        if not PAPER_RE.fullmatch(paper) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", venue):
            raise ValueError("论文编号或期刊配置无效")
        return [python, "scripts/researchctl.py", "set-venue", "--project", slug, "--paper", paper, "--venue", venue], f"设置 {paper} 期刊", slug
    if action == "package":
        paper = bounded_text(payload.get("paper"), "论文编号", 3, required=True)
        if not PAPER_RE.fullmatch(paper):
            raise ValueError("论文编号必须类似 P01")
        output = project / "exports" / f"{paper}-submission.zip"
        return [python, "scripts/submission_package.py", "--project", slug, "--paper", paper, "--output", str(output)], f"生成 {paper} 手工投稿包", slug
    raise ValueError("不支持的操作")


class DashboardState:
    def __init__(self) -> None:
        self.config = SessionConfig()
        self.jobs = JobManager(self.config)
        self.csrf = secrets.token_urlsafe(32)
        self.config_lock = threading.RLock()


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: DashboardState) -> None:
        self.dashboard_state = state
        super().__init__(address, DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("dashboard: " + format % args + "\n")

    def _allowed_host(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    def _headers(self, content_type: str, length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()

    def send_json(self, value: Any, status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._headers("application/json; charset=utf-8", len(payload))
        self.wfile.write(payload)

    def send_asset(self, name: str, content_type: str) -> None:
        path = ASSET_ROOT / name
        try:
            payload = path.read_bytes()
        except OSError:
            self.send_json({"error": "客户端资源不存在"}, 404)
            return
        self.send_response(200)
        self._headers(content_type, len(payload))
        self.wfile.write(payload)

    def read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("无效的请求长度") from exc
        if not 0 < length <= MAX_BODY_BYTES:
            raise ValueError("请求为空或过大")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("请求不是有效 JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("请求必须是 JSON 对象")
        return value

    def require_write_access(self) -> None:
        if self.headers.get("X-Research-CSRF") != self.server.dashboard_state.csrf:
            raise PermissionError("安全令牌缺失或已经失效，请刷新页面")
        origin = self.headers.get("Origin")
        if origin:
            parsed = urllib.parse.urlsplit(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise PermissionError("拒绝非本地页面发起的操作")

    def do_GET(self) -> None:  # noqa: N802
        if not self._allowed_host():
            self.send_json({"error": "仅允许本机访问"}, 403)
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/":
                self.send_asset("index.html", "text/html; charset=utf-8")
            elif path == "/app.css":
                self.send_asset("app.css", "text/css; charset=utf-8")
            elif path == "/app.js":
                self.send_asset("app.js", "text/javascript; charset=utf-8")
            elif path == "/api/overview":
                version_match = re.search(
                    r'^version\s*=\s*"([^"]+)"',
                    (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
                    re.MULTILINE,
                )
                self.send_json(
                    {
                        "version": version_match.group(1) if version_match else "unknown",
                        "csrf": self.server.dashboard_state.csrf,
                        "configuration": self.server.dashboard_state.config.public(),
                        "projects": project_summaries(),
                        "jobs": self.server.dashboard_state.jobs.list(),
                        "data_providers": [
                            {"id": key, "name": PROVIDER_INFO[key][0], "description": PROVIDER_INFO[key][1]}
                            for key in DATA_PROVIDERS
                        ],
                        "stages": researchctl.STAGES,
                    }
                )
            elif path.startswith("/api/projects/"):
                slug = urllib.parse.unquote(path.removeprefix("/api/projects/"))
                self.send_json(project_detail(slug))
            elif path.startswith("/api/jobs/"):
                job_id = path.removeprefix("/api/jobs/")
                self.send_json(self.server.dashboard_state.jobs.get(job_id).public(include_log=True))
            else:
                self.send_json({"error": "页面不存在"}, 404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": f"客户端内部错误：{exc}"}, 500)

    def do_POST(self) -> None:  # noqa: N802
        if not self._allowed_host():
            self.send_json({"error": "仅允许本机访问"}, 403)
            return
        path = urllib.parse.urlsplit(self.path).path
        try:
            self.require_write_access()
            payload = self.read_json()
            if path == "/api/config":
                with self.server.dashboard_state.config_lock:
                    update_config(self.server.dashboard_state.config, payload)
                self.send_json({"configuration": self.server.dashboard_state.config.public()})
                return
            if path == "/api/jobs":
                action = bounded_text(payload.get("action"), "操作", 80, required=True)
                command, label, project = build_command(action, payload)
                job = self.server.dashboard_state.jobs.start(action, label, command, project)
                self.send_json({"job": job.public(include_log=True)}, HTTPStatus.ACCEPTED)
                return
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                job_id = path.removeprefix("/api/jobs/").removesuffix("/cancel").strip("/")
                job = self.server.dashboard_state.jobs.cancel(job_id)
                self.send_json({"job": job.public(include_log=True)})
                return
            self.send_json({"error": "操作不存在"}, 404)
        except PermissionError as exc:
            self.send_json({"error": str(exc)}, 403)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": f"客户端内部错误：{exc}"}, 500)


def open_local_browser(url: str) -> None:
    time.sleep(0.8)
    try:
        if Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists() and shutil_which("cmd.exe"):
            subprocess.Popen(["cmd.exe", "/c", "start", "", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open(url)
    except OSError:
        pass


def shutil_which(command: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / command
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser automatically")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    state = DashboardState()
    server = DashboardServer((args.host, args.port), state)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Doctoral Research OS dashboard: {url}")
    print("API keys remain in this process memory and are never returned to the browser.")
    print("Press Ctrl+C to stop the dashboard and clear in-memory credentials.")
    if not args.no_open:
        threading.Thread(target=open_local_browser, args=(url,), daemon=True).start()

    def stop(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever(poll_interval=0.4)
    finally:
        server.server_close()
        state.config.api_key = ""
        state.config.tavily_key = ""
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
