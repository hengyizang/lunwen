#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate source-aware Obsidian analysis note templates."""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime

logger = logging.getLogger(__name__)

SOURCE_TYPES = (
    "arxiv",
    "pdf_url",
    "local_pdf",
    "project_page",
    "blog",
    "webpage",
    "local_document",
    "title",
)


def get_vault_path(cli_vault=None):
    if cli_vault:
        return cli_vault
    env_path = os.environ.get("OBSIDIAN_VAULT_PATH")
    if env_path:
        return env_path
    logger.error("未指定 vault 路径。请通过 --vault 或 OBSIDIAN_VAULT_PATH 设置。")
    sys.exit(1)


def stable_document_id(paper_id, source_url, title):
    if paper_id:
        return re.sub(r"v\d+$", "", paper_id, flags=re.IGNORECASE)
    basis = source_url or title
    prefix = "url" if source_url else "title"
    return f"{prefix}-{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"


def yaml_scalar(value):
    return json.dumps(str(value or ""), ensure_ascii=False)


def build_frontmatter(
    document_id,
    paper_id,
    source_type,
    source_url,
    title,
    authors,
    published_date,
    domain,
    created,
    tags,
):
    lines = [
        "---",
        f"document_id: {yaml_scalar(document_id)}",
    ]
    if source_type == "arxiv" and paper_id:
        lines.append(f"arxiv_id: {yaml_scalar(paper_id)}")
    lines.extend(
        [
            f"source_type: {yaml_scalar(source_type)}",
            f"source_url: {yaml_scalar(source_url)}",
            f"title: {yaml_scalar(title)}",
            f"authors: {yaml_scalar(authors)}",
            f"published: {yaml_scalar(published_date)}",
            f"domain: {yaml_scalar(domain)}",
            "tags:",
        ]
    )
    lines.extend(f"  - {yaml_scalar(tag)}" for tag in tags)
    lines.extend(
        [
            'quality_score: ""',
            "related_papers: []",
            f"created: {yaml_scalar(created)}",
            f"updated: {yaml_scalar(created)}",
            'status: "analyzed"',
            "---",
        ]
    )
    return "\n".join(lines)


def source_links(source_type, source_url, paper_id, language):
    if source_type == "arxiv" and paper_id:
        abs_url = source_url or f"https://arxiv.org/abs/{paper_id}"
        pdf_url = f"https://arxiv.org/pdf/{paper_id}"
        return f"[arXiv]({abs_url}) | [PDF]({pdf_url})"
    if source_url:
        label = "原始来源" if language == "zh" else "Original source"
        return f"[{label}]({source_url})"
    return "--"


def research_template(
    document_id,
    paper_id,
    source_type,
    source_url,
    title,
    authors,
    published_date,
    venue,
    domain,
    created,
    language,
):
    tags = (["论文笔记", domain, source_type] if language == "zh"
            else ["paper-notes", domain, source_type])
    frontmatter = build_frontmatter(
        document_id,
        paper_id,
        source_type,
        source_url,
        title,
        authors,
        published_date,
        domain,
        created,
        tags,
    )
    links = source_links(source_type, source_url, paper_id, language)
    identifier = paper_id if source_type == "arxiv" and paper_id else document_id

    if language == "zh":
        return f"""{frontmatter}

# {title}

## 核心信息
- **文档 ID**：{identifier or "--"}
- **来源类型**：{source_type}
- **作者**：{authors or "--"}
- **机构**：--
- **发布时间**：{published_date or "--"}
- **会议/期刊/发布方**：{venue or "--"}
- **链接**：{links}
- **引用**：--

## 摘要与核心要点

### 原文摘要
[从原文提取；若文档没有摘要，写 --]

### 中文概述
[准确概括，不增加原文没有的结论]

### 核心要点
- [研究背景或问题]
- [核心方法或主张]
- [主要结果]
- [研究意义]

## 研究背景与问题
[背景、动机、问题定义与适用边界]

## 方法概述

### 核心方法
[组件、流程、训练/推理过程]

### 关键公式
[行内使用 $...$，块级使用 $$...$$]

### 方法架构与图片
[使用 ![[filename.png|800]] 并解释图意]

## 实验与证据
- **数据集/任务**：--
- **基线**：--
- **指标**：--
- **主要结果**：--
- **消融与稳健性**：--

## 深度分析

### 核心贡献与创新
[区分作者主张和基于证据的判断]

### 优势
- [优势]

### 局限与风险
- [作者明确局限]
- [进一步推断，明确标记为分析]

### 适用场景
[何时适用、何时不适用]

## 相关工作与技术路线
- [[相关资料|显示标题]] — [关系]

## 综合评价

| 维度 | 分数 | 理由 |
|---|---:|---|
| 创新性 | --/10 | -- |
| 技术质量 | --/10 | -- |
| 证据充分性 | --/10 | -- |
| 写作质量 | --/10 | -- |
| 实用性 | --/10 | -- |

## 我的笔记

%% 在这里添加个人笔记 %%

## 外部资源
- [代码/项目主页/演示]
"""

    return f"""{frontmatter}

# {title}

## Core Information
- **Document ID**: {identifier or "--"}
- **Source type**: {source_type}
- **Authors**: {authors or "--"}
- **Affiliation**: --
- **Published**: {published_date or "--"}
- **Venue/Publisher**: {venue or "--"}
- **Links**: {links}
- **Citations**: --

## Abstract and Key Points

### Original Abstract
[Extract from the source, or -- if absent]

### Summary
[Faithful summary without unsupported conclusions]

### Key Points
- [Problem]
- [Method or claim]
- [Main result]
- [Significance]

## Background and Problem
[Motivation, problem definition, and scope]

## Method Overview

### Core Method
[Components, workflow, training, and inference]

### Key Formulas
[Use $...$ inline and $$...$$ for blocks]

### Architecture and Figures
[Use ![[filename.png|800]] and explain each figure]

## Experiments and Evidence
- **Datasets/Tasks**: --
- **Baselines**: --
- **Metrics**: --
- **Main results**: --
- **Ablations/Robustness**: --

## In-Depth Analysis

### Contributions and Novelty
[Separate author claims from evidence-based assessment]

### Strengths
- [Strength]

### Limitations and Risks
- [Stated limitation]
- [Inference, clearly labeled]

### Applicability
[When it applies and when it does not]

## Related Work and Roadmap
- [[Related note|Display title]] — [Relationship]

## Assessment

| Dimension | Score | Rationale |
|---|---:|---|
| Novelty | --/10 | -- |
| Technical quality | --/10 | -- |
| Evidence | --/10 | -- |
| Writing | --/10 | -- |
| Practicality | --/10 | -- |

## My Notes

%% Add personal notes here %%

## External Resources
- [Code/project/demo]
"""


def web_template(
    document_id,
    source_type,
    source_url,
    title,
    authors,
    published_date,
    domain,
    created,
    language,
):
    tags = (["资料笔记", domain, source_type] if language == "zh"
            else ["source-notes", domain, source_type])
    frontmatter = build_frontmatter(
        document_id,
        "",
        source_type,
        source_url,
        title,
        authors,
        published_date,
        domain,
        created,
        tags,
    )
    links = source_links(source_type, source_url, "", language)

    if language == "zh":
        return f"""{frontmatter}

# {title}

## 来源信息
- **文档 ID**：{document_id}
- **类型**：{source_type}
- **作者/机构**：{authors or "--"}
- **发布日期**：{published_date or "--"}
- **原始链接**：{links}

## 一句话概述
[用一句话概括文章或页面]

## 核心论点
- [论点 1]
- [论点 2]
- [论点 3]

## 内容脉络
[按文章结构解释论证或技术路线]

## 关键证据与引用
- [证据、数字、案例或引用来源]
- [明确区分作者主张与外部证据]

## 技术细节
[公式、算法、实现方式、实验或工程细节；没有则写 --]

## 可信度与局限
- **证据强度**：--
- **潜在偏差**：--
- **缺失信息**：--
- **适用边界**：--

## 与已有知识的关系
- [[相关资料|显示标题]] — [关系]

## 实践启示
- [可操作启示]
- [需要进一步验证的事项]

## 我的笔记

%% 在这里添加个人笔记 %%
"""

    return f"""{frontmatter}

# {title}

## Source Information
- **Document ID**: {document_id}
- **Type**: {source_type}
- **Author/Organization**: {authors or "--"}
- **Published**: {published_date or "--"}
- **Original link**: {links}

## One-Sentence Summary
[Summarize the source in one sentence]

## Core Claims
- [Claim 1]
- [Claim 2]
- [Claim 3]

## Content Structure
[Explain the argument or technical narrative]

## Key Evidence and Citations
- [Evidence, numbers, examples, or cited sources]
- [Separate author claims from external evidence]

## Technical Details
[Formulas, algorithms, implementation, or experiments; use -- if absent]

## Credibility and Limitations
- **Evidence strength**: --
- **Potential bias**: --
- **Missing information**: --
- **Scope**: --

## Relationship to Existing Knowledge
- [[Related note|Display title]] — [Relationship]

## Practical Takeaways
- [Actionable takeaway]
- [What needs further verification]

## My Notes

%% Add personal notes here %%
"""


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(description="Generate a source-aware Obsidian analysis note")
    parser.add_argument("--paper-id", default="", help="arXiv ID; only for source-type arxiv")
    parser.add_argument("--document-id", default="", help="Stable source identifier")
    parser.add_argument("--source-type", choices=SOURCE_TYPES, default="arxiv")
    parser.add_argument("--source-url", default="", help="Original public source URL")
    parser.add_argument("--title", required=True)
    parser.add_argument("--authors", default="")
    parser.add_argument("--published-date", default="")
    parser.add_argument("--venue", default="")
    parser.add_argument("--domain", default="其他")
    parser.add_argument("--vault", default=None)
    parser.add_argument("--language", choices=["zh", "en"], default="zh")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing generated note")
    args = parser.parse_args()

    if args.source_type != "arxiv" and args.paper_id:
        logger.error("--paper-id 只能用于 source-type arxiv")
        return 2
    if args.source_type == "arxiv" and not args.paper_id:
        logger.error("source-type arxiv 需要 --paper-id")
        return 2

    vault_root = get_vault_path(args.vault)
    created = datetime.now().strftime("%Y-%m-%d")
    domain = args.domain.strip("/\\").replace("..", "") or ("其他" if args.language == "zh" else "Other")
    document_id = args.document_id or stable_document_id(args.paper_id, args.source_url, args.title)
    safe_title = re.sub(r'[ /\\:*?"<>|]+', "_", args.title).strip("_") or document_id

    note_dir = os.path.join(vault_root, "20_Research", "Papers", domain)
    os.makedirs(note_dir, exist_ok=True)
    note_path = os.path.join(note_dir, f"{safe_title}.md")
    if os.path.exists(note_path) and not args.force:
        logger.error("笔记已存在，拒绝覆盖: %s", note_path)
        return 2

    if args.source_type in {"blog", "project_page", "webpage"}:
        content = web_template(
            document_id,
            args.source_type,
            args.source_url,
            args.title,
            args.authors,
            args.published_date,
            domain,
            created,
            args.language,
        )
    else:
        content = research_template(
            document_id,
            args.paper_id,
            args.source_type,
            args.source_url,
            args.title,
            args.authors,
            args.published_date,
            args.venue,
            domain,
            created,
            args.language,
        )

    try:
        with open(note_path, "w", encoding="utf-8") as handle:
            handle.write(content)
    except IOError as exc:
        logger.error("写入笔记失败: %s", exc)
        return 1

    print(f"笔记已生成: {note_path}" if args.language == "zh" else f"Note generated: {note_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
