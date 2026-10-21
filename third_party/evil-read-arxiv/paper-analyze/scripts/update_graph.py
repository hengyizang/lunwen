#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Update the Obsidian research graph for arXiv and non-arXiv sources."""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime

logger = logging.getLogger(__name__)


def get_vault_path(cli_vault=None):
    if cli_vault:
        return cli_vault
    env_path = os.environ.get("OBSIDIAN_VAULT_PATH")
    if env_path:
        return env_path
    logger.error("未指定 vault 路径。请通过 --vault 或 OBSIDIAN_VAULT_PATH 设置。")
    sys.exit(1)


def stable_document_id(document_id, paper_id, source_url, title):
    if document_id:
        return document_id
    if paper_id:
        return re.sub(r"v\d+$", "", paper_id, flags=re.IGNORECASE)
    basis = source_url or title
    prefix = "url" if source_url else "title"
    return f"{prefix}-{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(description="Update the research knowledge graph")
    parser.add_argument("--document-id", default="")
    parser.add_argument("--paper-id", default="", help="arXiv ID; only for arxiv sources")
    parser.add_argument("--source-type", default="arxiv")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--title", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--score", type=float, default=0.0)
    parser.add_argument("--related", nargs="*", default=[])
    parser.add_argument("--vault", default=None)
    parser.add_argument("--language", choices=["zh", "en"], default="zh")
    args = parser.parse_args()

    if args.source_type != "arxiv" and args.paper_id:
        logger.error("--paper-id 只能用于 source-type arxiv")
        return 2

    vault_root = get_vault_path(args.vault)
    date = datetime.now().strftime("%Y-%m-%d")
    node_id = stable_document_id(
        args.document_id,
        args.paper_id,
        args.source_url,
        args.title,
    )
    graph_dir = os.path.join(vault_root, "20_Research", "PaperGraph")
    os.makedirs(graph_dir, exist_ok=True)
    graph_path = os.path.join(graph_dir, "graph_data.json")

    try:
        with open(graph_path, "r", encoding="utf-8") as handle:
            graph = json.load(handle)
    except FileNotFoundError:
        graph = {"nodes": [], "edges": [], "last_updated": date}
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("读取图谱失败: %s", exc)
        return 1

    graph.setdefault("nodes", [])
    graph.setdefault("edges", [])
    tags = (
        ["论文笔记" if args.source_type in {"arxiv", "pdf_url", "local_pdf"} else "资料笔记",
         args.domain, args.source_type]
        if args.language == "zh"
        else ["paper-notes" if args.source_type in {"arxiv", "pdf_url", "local_pdf"} else "source-notes",
              args.domain, args.source_type]
    )
    node = {
        "id": node_id,
        "title": args.title,
        "domain": args.domain,
        "source_type": args.source_type,
        "source_url": args.source_url,
        "arxiv_id": args.paper_id if args.source_type == "arxiv" else "",
        "quality_score": args.score,
        "tags": tags,
        "analyzed": True,
        "updated": date,
    }

    existing_nodes = {
        item.get("id"): index
        for index, item in enumerate(graph["nodes"])
        if item.get("id")
    }
    if node_id in existing_nodes:
        graph["nodes"][existing_nodes[node_id]].update(node)
    else:
        graph["nodes"].append(node)

    existing_edges = {
        (edge.get("source"), edge.get("target"))
        for edge in graph["edges"]
        if edge.get("source") and edge.get("target")
    }
    for related_id in args.related:
        if related_id and related_id != node_id and (node_id, related_id) not in existing_edges:
            graph["edges"].append(
                {
                    "source": node_id,
                    "target": related_id,
                    "type": "related",
                    "weight": 0.7,
                }
            )

    graph["last_updated"] = date
    try:
        with open(graph_path, "w", encoding="utf-8") as handle:
            json.dump(graph, handle, ensure_ascii=False, indent=2)
    except (OSError, TypeError) as exc:
        logger.error("写入图谱失败: %s", exc)
        return 1

    print(f"图谱已更新: {graph_path}" if args.language == "zh" else f"Graph updated: {graph_path}")
    print(f"节点数: {len(graph['nodes'])}" if args.language == "zh" else f"Nodes: {len(graph['nodes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
