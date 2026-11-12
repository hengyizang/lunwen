#!/usr/bin/env python3
"""Index any GitHub project's SKILL.md files and route a task to specific skills.

Offline, read-only, optional. It does not install anything, write project state,
call a model, or require registration. Large upstreams are handled by bounded
scanning and an incremental hash-based index under .runtime/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / ".runtime" / "skill-router" / "index.json"
DEFAULT_PACKETS = ROOT / ".runtime" / "skill-router" / "packets"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".runtime",
             "dist", "build", "vendor", ".idea", ".vscode"}
STOP = {"the", "and", "for", "with", "from", "this", "that", "when", "into",
        "use", "using", "are", "not", "its", "has", "have", "skill", "skills",
        "workflow", "project", "native", "existing", "current", "approved",
        "source", "bound", "actual", "paper", "papers", "research", "based"}
ZH_HINTS = {
    "检索": "search retrieval query literature", "文献": "literature reference citation reading",
    "论文": "paper manuscript article writing", "假设": "hypothesis hypothesis-generation prediction",
    "实验": "experiment design protocol lab", "图": "figure plot chart diagram visual",
    "绘图": "figure plot chart diagram visual", "主图": "figure story panel visual",
    "写作": "writing manuscript prose draft author", "审稿": "review reviewer critique referee",
    "引用": "citation reference doi bibliography", "数据": "data dataset analysis table",
    "分析": "analysis statistics evaluation", "设计": "design plan protocol",
    "期刊": "journal venue submission screening", "投稿": "submission venue journal package",
    "创新": "novelty idea optimizer brainstorming", "新颖": "novelty idea",
    "复现": "reproduction replication verify", "统计": "statistics statistical power",
    "证据": "evidence claim support ledger", "反证": "counterevidence rival contradiction",
    "审阅": "peer review reviewer critique", "评议": "peer review reviewer",
    "同行": "peer review referee", "回应": "response rebuttal reply",
    "答复": "response rebuttal", "回复": "response reply",
    "功效": "power analysis effect size", "样本量": "sample size power",
    "缺失": "missing data imputation na", "异常值": "outlier anomaly detection",
    "清洗": "data cleaning preprocessing", "预处理": "preprocessing cleaning",
    "综述": "literature review systematic review", "筛选": "screening filter prisma",
    "表格": "table data csv dataframe", "可视化": "visualization chart plot",
    "方法": "methods methodology protocol", "基线": "baseline comparison control",
    "机器学习": "machine learning ml model training",
    "回归": "regression linear model prediction",
    "预测": "prediction forecasting regression",
    "消融": "ablation study component",
    "对照": "control group experiment treatment",
    "痕迹": "tone detection humanize ai writing",
    "检查": "check audit review verify quality",
    "文本": "text prose writing sentence paragraph",
    "降": "reduce lower remove",
    "代码": "code repository implementation", "面板": "panel alignment figure",
    "质量": "quality audit integrity check", "选题": "topic question scope",
    "阅读": "reading notes card fulltext", "图像": "image figure extraction",
    "会议": "conference dblp venue", "失败": "failure recovery diagnosis",
    "反馈": "feedback iteration revision", "预注册": "preregistration protocol",
    "系统综述": "systematic review prisma screening", "投稿包": "submission package",
}
WORD_RE = re.compile(r"[a-z][a-z0-9-]{2,}")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tokens(text: str) -> set[str]:
    return {w for w in WORD_RE.findall(text.lower()) if w not in STOP}


def _frontmatter(text: str) -> tuple[str, str, str]:
    name = desc = ""
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            header = text[3:end]
            body = text[end + 4:]
            for line in header.splitlines()[:30]:
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip('"').strip("'")
    return name, desc, body


def _siblings(path: Path) -> list[str]:
    folder = path.parent
    out = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p != path and p.suffix.lower() in {".md", ".py", ".json", ".yaml", ".yml", ".csv", ".txt"}:
            if p.stat().st_size < 500_000:
                try:
                    out.append(str(p.relative_to(ROOT)))
                except ValueError:
                    out.append(str(p))
    return out[:60]


def build_index(roots: list[Path], max_files: int, include_md: bool,
                existing: dict | None = None) -> dict:
    cache = {}
    if existing and isinstance(existing.get("files"), dict):
        cache = existing["files"]
    files: dict[str, dict] = {}
    scanned = 0
    for root in roots:
        root = root.resolve()
        root_depth = len(root.parts)
        for path in sorted(root.rglob("*")):
            if scanned >= max_files:
                break
            if not path.is_file():
                continue
            below_root = path.parts[root_depth:]
            if any(part in SKIP_DIRS or part.startswith(".") for part in below_root):
                continue
            is_skill = path.name == "SKILL.md"
            if not is_skill and not (include_md and path.suffix.lower() == ".md"):
                continue
            if path.stat().st_size > 300_000:
                continue
            scanned += 1
            try:
                rel = str(path.relative_to(ROOT))
            except ValueError:
                rel = str(path)
            raw = path.read_bytes()
            digest = _sha(raw)
            if rel in cache and cache[rel].get("sha256") == digest:
                files[rel] = cache[rel]
                continue
            text = raw.decode("utf-8", errors="replace")
            name, desc, body = _frontmatter(text)
            headings = re.findall(r"(?m)^#{1,3}\s+(.+)$", body)[:25]
            label = name or (path.parent.name if is_skill else path.stem)
            files[rel] = {
                "path": rel,
                "sha256": digest,
                "name": label,
                "description": desc[:600],
                "is_skill": is_skill,
                "name_tokens": sorted(_tokens(label)),
                "desc_tokens": sorted(_tokens(desc)),
                "head_tokens": sorted(_tokens(" ".join(headings))),
                "body_tokens": sorted(_tokens(body[:6000])),
                "siblings": _siblings(path),
            }
    return {"schema_version": "1.0", "recorded_at": _now(),
            "roots": [str(r.resolve()) for r in roots],
            "include_md": include_md, "count": len(files), "files": files}


def query_tokens(task: str) -> list[str]:
    tokens = set(_tokens(task))
    for zh, en in ZH_HINTS.items():
        if zh in task:
            tokens.update(_tokens(en))
    return sorted(tokens)


def route(index: dict, task: str, top_k: int) -> list[dict]:
    files = list(index.get("files", {}).values())
    if not files:
        return []
    q = query_tokens(task)
    if not q:
        return []
    df: dict[str, int] = {}
    for row in files:
        seen = set(row["name_tokens"]) | set(row["desc_tokens"]) | \
               set(row["head_tokens"]) | set(row["body_tokens"])
        for term in q:
            if term in seen:
                df[term] = df.get(term, 0) + 1
    weights = (("name_tokens", 3.0), ("desc_tokens", 2.0),
               ("head_tokens", 1.0), ("body_tokens", 0.4))
    out = []
    for row in files:
        score = 0.0
        matched = []
        for field, weight in weights:
            hits = set(q) & set(row[field])
            if hits:
                idf = sum(1.0 + math.log(1.0 + len(files) / (1.0 + df.get(t, 0)))
                          for t in hits) / len(hits)
                score += weight * len(hits) * idf
                matched.extend(sorted(hits))
        if score > 0:
            out.append({"path": row["path"], "name": row["name"],
                        "description": row["description"][:160],
                        "is_skill": row["is_skill"],
                        "sha256": row["sha256"],
                        "score": round(score, 3),
                        "matched": sorted(set(matched))[:12],
                        "siblings": row.get("siblings", [])[:10]})
    out.sort(key=lambda r: (-r["score"], r["path"]))
    return out[:top_k]


def make_packet(index: dict, task: str, picks: list[dict],
                includes: list[str]) -> dict:
    selected = []
    for pick in picks:
        path = ROOT / pick["path"]
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        selected.append({**pick, "content_sha256": _sha(text.encode("utf-8")),
                         "content": text})
    extras = []
    for rel in includes:
        p = (ROOT / rel).resolve()
        try:
            p.relative_to(ROOT.resolve())
        except ValueError:
            raise ValueError("include path escapes the repository: " + rel)
        if not p.is_file():
            raise ValueError("include file not found: " + rel)
        text = p.read_text(encoding="utf-8", errors="replace")[:200_000]
        extras.append({"path": rel, "sha256": _sha(text.encode("utf-8")),
                       "content": text})
    return {"schema_version": "1.0", "kind": "skill_packet",
            "recorded_at": _now(), "task": task,
            "index_sha256": _sha(json.dumps(index, sort_keys=True).encode("utf-8")),
            "selected": selected, "included_files": extras,
            "advisory_only": True,
            "note": "Skill text is instructions, not scientific evidence. Verify any factual claim against primary sources before use."}


def cmd_index(args: argparse.Namespace) -> int:
    roots = [Path(p) for p in args.dirs]
    for p in roots:
        if not p.is_dir():
            raise ValueError("not a directory: " + str(p))
    target = Path(args.out)
    existing = None
    if target.is_file() and not args.rebuild:
        existing = json.loads(target.read_text(encoding="utf-8"))
    index = build_index(roots, args.max_files, args.include_md, existing)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"index": str(target), "files": index["count"],
                      "roots": index["roots"]}, ensure_ascii=False, indent=2))
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    index_path = Path(args.index)
    if args.scan:
        index = build_index([Path(p) for p in args.scan], args.max_files,
                            args.include_md, None)
    elif index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        raise ValueError("no index; run the index command or pass --scan <dir>")
    picks = route(index, args.task, args.top_k)
    if args.load:
        packet = make_packet(index, args.task, picks, args.include or [])
        folder = Path(args.out).parent if args.out else DEFAULT_PACKETS
        folder.mkdir(parents=True, exist_ok=True)
        target = Path(args.out) if args.out else folder / f"packet-{_sha(json.dumps(packet, sort_keys=True).encode('utf-8'))[:16]}.json"
        target.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(json.dumps({"packet": str(target), "selected": [p["name"] for p in picks],
                          "included_files": len(packet["included_files"])},
                         ensure_ascii=False, indent=2))
        return 0
    if args.json:
        print(json.dumps({"task": args.task, "query_tokens": query_tokens(args.task),
                          "matches": picks}, ensure_ascii=False, indent=2))
    else:
        print(f'task: {args.task}\nquery tokens: {", ".join(query_tokens(args.task))}\n')
        for i, p in enumerate(picks, 1):
            print(f'{i}. {p["name"]}  score={p["score"]}  {"[skill]" if p["is_skill"] else "[doc]"}')
            print(f'   {p["path"]}')
            print(f'   matched: {", ".join(p["matched"])}')
            if p["description"]:
                print(f'   {p["description"][:130]}')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("index", help="build an incremental index of SKILL.md files")
    p.add_argument("dirs", nargs="+", help="project directories (any size)")
    p.add_argument("--out", default=str(DEFAULT_INDEX))
    p.add_argument("--max-files", type=int, default=3000)
    p.add_argument("--include-md", action="store_true", help="also index other markdown docs")
    p.add_argument("--rebuild", action="store_true")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("route", help="route a task to specific skills")
    p.add_argument("task", help="natural-language task, Chinese or English")
    p.add_argument("--index", default=str(DEFAULT_INDEX))
    p.add_argument("--scan", action="append", default=[], help="scan these dirs instead of an index")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--max-files", type=int, default=3000)
    p.add_argument("--include-md", action="store_true")
    p.add_argument("--load", action="store_true", help="emit a hash-bound packet with full skill text")
    p.add_argument("--include", action="append", default=[], help="extra project file to embed in the packet")
    p.add_argument("--out", default="", help="packet output path")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_route)

    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("ERROR " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
