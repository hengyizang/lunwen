"""Advisory anti-defensive review with explicit scientific preservation.

The eight categories are local groups, not a claimed upstream enumeration.
Patterns identify review candidates; necessity, logic, novelty and evidence
adequacy require contextual scientific judgment. No rewriting or calls occur.
"""
from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/anti-defensive-rules.json"
HIGH_IMPACT = {"abstract", "introduction", "contribution", "contributions", "conclusion", "conclusions", "摘要", "引言", "贡献", "结论"}
PROTECTED_PATTERNS = {
    "statistical_uncertainty": r"\b(?:confidence|credible|prediction) intervals?\b|\b(?:standard error|statistical power|underpowered|precision|multiplicity|false discovery|non[- ]?significant|null hypothesis|CI)\b|\b(?:n\s*=\s*\d+|p\s*[<=>])|置信区间|可信区间|统计功效|标准误|不显著|多重比较",
    "design_and_causal_boundary": r"\b(?:observational|confounding|confounded|causal identification|causal inference|causality|association|randomi[sz]ed|censoring|selection bias|measurement bias|independent units?|leakage)\b|观察性|混杂|因果|相关关系|随机对照|选择偏差|测量偏差|独立样本|数据泄漏",
    "application_and_population_boundary": r"\b(?:external validity|generaliz(?:e|ation|ability)|out[- ]of[- ]distribution|unseen populations?|tested populations?|tested settings?|validated settings?|clinical use|deployment safety)\b|外部效度|泛化|分布外|未验证人群|已测试(?:人群|场景)|临床使用|部署安全",
    "ethics_law_and_safety": r"\b(?:ethic(?:s|al)|informed consent|IRB|privacy|identifiable|licen[cs]e|copyright|legal|safety|harm|AI[- ]use disclosure|conflict of interest)\b|伦理|知情同意|隐私|可识别|许可证|版权|法律|安全|利益冲突|AI使用披露",
    "registered_controls_and_adverse_evidence": r"\b(?:preregistered|preregistration|pre[- ]registered|negative control|positive control|control group|placebo|failed runs?|failed experiments?|adverse events?|null results?|negative results?|falsification|ablation|baseline|replication|counterevidence)\b|预注册|阴性对照|阳性对照|对照组|安慰剂|失败实验|失败运行|阴性结果|负面结果|消融|基线|反证|复现",
    "quantified_scope_or_tradeoff": r"\b(?:sample|cohort|dataset|sites?|participants?|patients?|subjects?|cases?|seeds?)\b[^.!?。！？\n]{0,55}\b\d|\b\d+[ -](?:site|dataset|participant|patient|case|seed)\b|\b(?:accuracy|latency|effect|improvement|difference|reduction|increase|decrease)\b[^.!?。！？\n]{0,35}\d|(?:样本|数据集|患者|参与者|准确率|延迟|差异|效应|提高|下降|降低)[^。！？\n]{0,25}[0-9一二三四五六七八九十两]",
    "evidence_based_rebuttal_or_distinction": r"\b(?:reviewer|response|rebuttal|contrary to)\b[^.!?。！？\n]{0,90}\b(?:Table|Figure|Eq(?:uation)?|Appendix|Supplement|evidence)\b|\b(?:conceptual distinction|distinguish(?:es)? between|alternative explanations?|counterfactual|identification assumption)\b|(?:审稿|反驳|回复)[^。！？\n]{0,45}(?:图|表|公式|证据)|概念区分|竞争解释|替代解释|识别假设"
}


def _configuration() -> dict:
    value = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise ValueError("anti-defensive rules need schema 1.0")
    groups = value.get("groups", [])
    if len(groups) != 8 or len({row["id"] for row in groups}) != 8:
        raise ValueError("anti-defensive coverage needs eight distinct local review groups")
    if [row.get("review_id") for row in groups] != [f"AD{i:02d}" for i in range(1, 9)]:
        raise ValueError("anti-defensive groups must retain stable AD01-AD08 coverage IDs")
    ids = {row["id"] for row in groups}
    if len(value.get("checklist", [])) != 10 or any(row["group"] not in ids for row in value["checklist"]):
        raise ValueError("all ten upstream checklist items must be mapped")
    if len(value.get("rewrite_procedure", [])) != 5 or len(value.get("function_classes", [])) != 6:
        raise ValueError("all upstream rewrite steps and sentence functions must be retained")
    for rule in value["rules"]:
        if rule["group"] not in ids:
            raise ValueError("unmapped anti-defensive rule")
        re.compile(rule["pattern"], re.I)
    return value


def load_rules() -> dict:
    """Public validated configuration for repository coverage checks."""
    return _configuration()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mask(text: str) -> str:
    """Keep offsets while excluding code/math and explicitly quoted examples."""
    pattern = re.compile(r"```.*?```|~~~.*?~~~|\\\[.*?\\\]|\$\$.*?\$\$|(?<!\\)\$(?!\$).*?(?<!\\)\$|^\s*>[^\n]*", re.S | re.M)
    def blank(match):
        return "".join("\n" if char == "\n" else " " for char in match.group())
    return pattern.sub(blank, text)


def _sections(text: str) -> list[tuple[int, str]]:
    result = [(0, "unspecified")]
    offset = 0
    names = HIGH_IMPACT | {"methods", "method", "results", "discussion", "limitations", "ethics", "方法", "结果", "讨论", "局限", "伦理"}
    for line in text.splitlines(keepends=True):
        value = line.strip()
        heading = re.match(r"#{1,6}\s+(.+?)\s*#*$", value)
        latex = re.match(r"\\(?:sub)*section\*?\{([^}]+)\}", value)
        title = (heading.group(1) if heading else latex.group(1) if latex else value).strip().strip(":：").casefold()
        title = re.sub(r"^\d+(?:\.\d+)*[.)]?\s+", "", title)
        if heading or latex or title in names:
            result.append((offset, title))
        offset += len(line)
    return result


def _section_at(sections, offset):
    return sections[max(0, bisect_right([item[0] for item in sections], offset) - 1)][1]


def _units(masked: str):
    boundaries = [0, *[match.end() for match in re.finditer(r"\n[ \t]*\n", masked)], len(masked)]
    paragraph = 0
    for start, end in zip(boundaries, boundaries[1:]):
        raw = masked[start:end]
        if not raw.strip():
            continue
        paragraph += 1
        first_content = len(raw) - len(raw.lstrip())
        first_line = raw[first_content:].splitlines()[0]
        if re.match(r"#{1,6}\s|\\(?:sub)*section", first_line) or first_line.strip().casefold() in HIGH_IMPACT:
            first_content += len(first_line)
            while first_content < len(raw) and raw[first_content].isspace():
                first_content += 1
        previous = first_content
        stops = [match.end() for match in re.finditer(r"[。！？]+|[.!?]+(?=\s|$)", raw[first_content:])]
        for stop in [*[first_content + value for value in stops], len(raw)]:
            unit = raw[previous:stop]
            left = len(unit) - len(unit.lstrip())
            if unit.strip():
                yield start + previous + left, unit.strip(), paragraph, previous == first_content, start + first_content
            previous = stop


def _position(text, start, end):
    line = text.count("\n", 0, start) + 1
    return {"start": start, "end": end, "line": line, "column": start - text.rfind("\n", 0, start), "basis": "analyzed_text"}


def _raw_position(text, raw, start, end):
    if raw == text:
        return {**_position(raw, start, end), "basis": "raw_text", "status": "same_input"}
    fragment = text[start:end]
    matches = list(re.finditer(re.escape(fragment), raw)) if fragment else []
    if len(matches) == 1:
        return {**_position(raw, matches[0].start(), matches[0].end()), "basis": "raw_text", "status": "unique_exact_match"}
    return {"status": "ambiguous" if matches else "not_found", "basis": "raw_text", "line": None, "column": None}


def audit_text(text: str, raw_text: str | None = None) -> dict:
    """Return located advisory findings, protected signals and honest coverage."""
    if not isinstance(text, str) or (raw_text is not None and not isinstance(raw_text, str)):
        raise ValueError("anti-defensive audit needs text strings")
    raw = text if raw_text is None else raw_text
    rules = _configuration()
    masked = _mask(text)
    sections, raw_sections = _sections(text), _sections(raw)
    findings, protected, nonclaims, limitation_sentences = [], [], [], {}

    def emit(rule, start, end, sentence, paragraph, reasons):
        location = _position(text, start, end)
        raw_location = _raw_position(text, raw, start, end)
        section = _section_at(raw_sections, raw_location["start"]) if "start" in raw_location else _section_at(sections, start)
        row = {"id": hashlib.sha256(f"{rule['id']}|{start}|{end}".encode()).hexdigest()[:20],
               "rule_id": rule["id"], "group": rule["group"], "checklist_id": rule.get("checklist"),
               **location, "raw_location": raw_location, "match": text[start:end], "context": sentence[:600],
               "paragraph": paragraph, "section": section, "message": rule["message"], "guidance": rule["guidance"],
               "confidence": "advisory", "automatic_edit_allowed": False,
               "protected_context": reasons, "scientific_judgment_required": True}
        if rule.get("protect_context") and reasons:
            row["disposition"] = "retain_evidence_boundary_and_review_context"
            protected.append(row)
        else:
            row["disposition"] = "review_framing_preserve_all_scientific_content"
            row["integrity_review_required"] = bool(rule.get("integrity_review"))
            findings.append(row)
        return row

    for start, sentence, paragraph, paragraph_start, _ in _units(masked):
        reasons = [name for name, pattern in PROTECTED_PATTERNS.items() if re.search(pattern, sentence, re.I)]
        for rule in rules["rules"]:
            if rule.get("paragraph_start") and not paragraph_start:
                continue
            for match in re.finditer(rule["pattern"], sentence, re.I):
                row = emit(rule, start + match.start(), start + match.end(), sentence, paragraph, reasons)
                if rule["id"] == "preemptive-nonclaim":
                    nonclaims.append((start, sentence, paragraph, reasons))
                if rule["id"] == "caveat-led-point" and row["section"] in HIGH_IMPACT:
                    emit({**rule, "id": "high-impact-caveat", "checklist": "high-impact-caveats",
                          "message": "A high-impact sentence leads with a caveat; determine whether that boundary is essential here."},
                         start + match.start(), start + match.end(), sentence, paragraph, reasons)
        if re.search(r"\b(?:limitation|limited|cannot|does not claim|do not claim)\b|局限|限制|不能|并不声称", sentence, re.I):
            normalized = re.sub(r"\s+", " ", sentence.casefold())
            if normalized in limitation_sentences:
                emit({"id": "repeated-limitation", "group": "paragraphs-and-position", "protect_context": True,
                      "message": "A limitation sentence recurs; assess whether each occurrence qualifies a different claim.",
                      "guidance": "Consolidate only scientifically redundant presentation. Preserve essential Abstract/Conclusion boundaries and cross-references."},
                     start, start + len(sentence), sentence, paragraph, reasons)
            limitation_sentences[normalized] = start
    for start, sentence, paragraph, reasons in nonclaims[1:]:
        emit({"id": "repeated-negative-claims", "group": "direct-claim-and-scope", "checklist": "repeated-nonclaims", "protect_context": True,
              "message": "Multiple nonclaims occur; distinguish separate necessary boundaries from repeated defensive framing.",
              "guidance": "Keep scientifically distinct boundaries. Replace only redundant nonclaims with exact positive scope when equivalent."},
             start, start + len(sentence), sentence, paragraph, reasons)
    findings.sort(key=lambda row: (row["start"], row["rule_id"]))
    protected.sort(key=lambda row: (row["start"], row["rule_id"]))
    coverage = []
    for group in rules["groups"]:
        found = [row for row in findings if row["group"] == group["id"]]
        kept = [row for row in protected if row["group"] == group["id"]]
        full_paper = group["id"] in {"contribution-and-coherence", "experiments-metrics-and-adverse-results", "reviews-and-example-integrity"}
        coverage.append({**group, "applicability": "context_dependent" if full_paper else "applicable" if text.strip() else "not_applicable",
                         "applicability_reason": "Needs manuscript, evidence/design/review context; an excerpt alone cannot settle this category." if full_paper else "Textual framing can be inspected; necessity remains a contextual judgment." if text.strip() else "No prose supplied.",
                         "automatic_status": "advisory_findings" if found else "protected_context_review" if kept else "no_pattern_found",
                         "finding_count": len(found), "protected_signal_count": len(kept), "semantic_verification": "not_performed"})
    source = rules["source"]
    return {"schema_version": "1.0", "status": "needs_context_review" if findings else "no_pattern_findings",
            "findings": findings, "protected_signals": protected, "coverage": coverage,
            "checklist_coverage": [{**item, "automatic_verification": "signals_only", "context_review_required": True} for item in rules["checklist"]],
            "function_classes": rules["function_classes"], "rewrite_procedure": rules["rewrite_procedure"],
            "context_guidance": rules["semantic_only_checks"], "rules_sha256": _hash_file(CONFIG),
            "source": {**source, "skill_sha256": _hash_file(ROOT / source["skill_path"]), "license_sha256": _hash_file(ROOT / source["license_path"])},
            "automatic_rewrite": False, "scientific_equivalence_verified": False, "full_semantic_review_verified": False,
            "manuscript_language_requirement": "English", "inspection_languages": rules["policy"]["inspection_languages"]}


def prompt_contract() -> str:
    """Instructions for the existing bounded author/critic pass, not a new call."""
    rules = _configuration()
    sections = [
        "ANTI-DEFENSIVE WRITING: apply within the existing authorized task and model roles; do not start another model/tool call.",
        "Understand the requested language, passage, main claim, evidence and intended reader before editing. Keep local edits local. All manuscript-bound outputs in this project remain English; Chinese planning text may be reviewed in Chinese.",
        "Lead with a direct, evidence-bounded main point and exact positive scope. One paragraph has one main job. Use contrast only when it distinguishes concepts, controls, mechanisms, alternatives or an evidenced reviewer position.",
        "Keep every necessary limitation affecting validity, interpretation, application, design or safe/legal/ethical use. State it calmly where needed, usually Methods/Discussion/Limitations. Retain a qualifier in Abstract/Conclusion whenever removing it would mislead; do not mechanically delete may, suggests, preliminary, not, however or under these conditions.",
        "Never change numbers, units, formulas, citations, confidence intervals, sample/group bindings, negative/null/adverse results, failed runs, controls, preregistration, ethics or AI-use disclosure for rhetorical strength. Do not turn association into causation or add significant/comprehensive superiority. Examples provide wording, never new facts, mechanisms, data or advantages.",
        "Identify the central capability/mechanism/cost/scalability contribution and connect Abstract, Introduction, Experiments and Conclusion to it, retaining supporting contributions. Narrow or withdraw unsupported claims; a generic caveat does not repair absent evidence.",
        "For every experiment state whether it tests effectiveness, mechanism, alternative explanations or applicability. A missing experiment identifies a specific unsupported claim, not a blanket verdict that experiments are insufficient.",
        "For an unfavorable finding: assess its effect on the central conclusion; state conditions/metric/comparison/uncertainty; leave the cause unknown if unknown; narrow unsupported claims; avoid turning one local weaker metric into a global defect. Preserve both improving and worsening metrics and fixed evaluation criteria. Combine only redundant presentation; supplement placement follows predeclared role/relevance/adequacy, never outcome direction.",
        "Triage reviewer comments as demonstrated problems, unresolved verification questions or optional additional experiments. Preserve necessary rebuttals. Do not insert every imagined objection into manuscript limitations. Chinese modesty such as 仅仅做了初步尝试/只能提供有限参考/仍有很大提升空间 needs exact facts instead; keep 初步/可能/提示 when justified.",
        "Classify each candidate sentence using these six functions: " + ", ".join(rules["function_classes"]) + "."
    ]
    sections.extend(f"Rewrite step {row['step']}: {row['task']}" for row in rules["rewrite_procedure"])
    sections.append("Full upstream checklist: " + "; ".join(row["text"] for row in rules["checklist"]) + ".")
    sections.append("Record a disposition for every local review group: " + "; ".join(row["review_id"] + " " + row["id"] for row in rules["groups"]) + ". Each needs fixed/rejected/unresolved and an evidence-bound reason. Coverage is a review record, never proof of scientific adequacy or a replacement for independent/human review.")
    sections.append("Before returning, perform a second self-review of every revision against the source and scientific boundaries. Record an itemized change log: original text, revised text, sentence function, rationale, protected facts, exact evidence locations and unresolved questions. Pattern flags are advisory; do not auto-delete results or assert semantic/scientific completion. Existing Claude plans/criticism stay read-only internal; the existing authorized non-Claude writer authors persistent text.")
    return "\n\n".join(sections)
