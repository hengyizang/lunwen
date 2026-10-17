"""Offline Lean kernel checks for preregistered formal proof obligations.

Numerical examples and symbolic simplification are never promoted to proofs.
The natural-language interpretation and originality still require human review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

LEAN_VERSION = "4.35.0"
TRUSTED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
FORBIDDEN = re.compile(r"\b(?:sorry|admit|axiom|unsafe|macro|syntax|elab|initialize|set_option|implemented_by|native_decide)\b|#|@\[")
NAME = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*$")


def normalized(value):
    return " ".join(value.split())


def verify(protocol, root):
    version = subprocess.run(["lean", "--version"], check=True, capture_output=True, text=True, timeout=20).stdout.strip()
    if not re.search(r"\b" + re.escape(LEAN_VERSION) + r"\b", version):
        raise ValueError("reviewed Lean " + LEAN_VERSION + " required")
    obligations = protocol.get("theorems")
    if not isinstance(obligations, list) or not 1 <= len(obligations) <= 100:
        raise ValueError("1-100 declared proof obligations required")
    results = []
    for item in obligations:
        name = item.get("declaration")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError("unsafe or missing Lean declaration")
        formal_type = item.get("formal_type")
        if (not isinstance(formal_type, str) or not formal_type.strip()
                or any(token in formal_type for token in ("\n", "\r", "#", ":=", "--", "/-", '"', "?"))
                or re.search(r"(?<!\w)_(?!\w)", formal_type)):
            raise ValueError("formal type must be an explicit bounded proposition without commands or metavariables")
        relative = Path(item["source"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("proof source must be project-relative")
        source = root / relative
        code = source.read_text(encoding="utf-8")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if source_hash != item["sha256"] or len(code.encode()) > 1_000_000:
            raise ValueError("proof source changed or exceeds bounds")
        # An intentionally conservative proof-only surface. Trusted pinned
        # libraries provide tactics; manuscript code cannot redefine commands,
        # skip kernel checking, inject output, or execute native evaluations.
        if FORBIDDEN.search(code):
            raise ValueError("proof source contains an unfinished proof, custom axiom or executable metaprogram")
        imports = re.findall(r"(?m)^\s*import\s+([^\n]+)", code)
        if any(module not in {"Init", "Std", "Mathlib"} for line in imports for module in line.split()):
            raise ValueError("only pinned Init/Std/Mathlib imports are supported")
        # Let Lean's kernel compare the actual proposition. Pretty-printer
        # binder layout is not a sound type-equivalence test.
        audit_code = code + '\nexample : Prop := (' + formal_type + ')\nexample : (' + formal_type + ') := @' + name
        audit_code += '\n#eval IO.println "AUDIT_AXIOMS_BEGIN"\n#print axioms ' + name
        audit_code += '\n#eval IO.println "AUDIT_TYPE_BEGIN"\n#check @' + name + '\n#eval IO.println "AUDIT_END"\n'
        with tempfile.TemporaryDirectory(prefix="proof-audit-") as directory:
            path = Path(directory) / "Audit.lean"
            path.write_text(audit_code, encoding="utf-8")
            checked = subprocess.run(["lean", str(path)], check=False, capture_output=True, text=True, timeout=protocol["proof_timeout_seconds"])
        if checked.returncode or checked.stderr.strip() or len(checked.stdout.encode()) > 1_000_000:
            raise ValueError("Lean kernel/type checking failed: " + (checked.stdout + checked.stderr)[-2000:])
        output = checked.stdout
        if any(output.count(marker) != 1 for marker in ("AUDIT_AXIOMS_BEGIN", "AUDIT_TYPE_BEGIN", "AUDIT_END")):
            raise ValueError("proof audit output is missing or ambiguous")
        axioms_text = output.split("AUDIT_AXIOMS_BEGIN", 1)[1].split("AUDIT_TYPE_BEGIN", 1)[0].strip()
        no_axioms = re.fullmatch("'" + re.escape(name) + "' does not depend on any axioms", axioms_text)
        matched = re.fullmatch("'" + re.escape(name) + r"' depends on axioms:\s*\[([^\]]*)\]", axioms_text)
        if not no_axioms and not matched:
            raise ValueError("Lean's transitive axiom audit could not be parsed")
        axioms = [] if no_axioms else [a.strip() for a in matched.group(1).split(",") if a.strip()]
        if not set(axioms) <= TRUSTED_AXIOMS:
            raise ValueError("proof depends on unapproved axioms: " + ", ".join(axioms))
        actual_type = normalized(output.split("AUDIT_TYPE_BEGIN", 1)[1].split("AUDIT_END", 1)[0])
        results.append({"id": item["id"], "claim_ids": item["claim_ids"], "declaration": name,
                        "checked_type": normalized(name + " : " + formal_type), "kernel_inferred_type": actual_type,
                        "source_sha256": source_hash, "axioms": axioms,
                        "status": "kernel_checked", "assumptions": item["assumptions"],
                        "scope": item["scope"], "natural_language_statement": item["statement"]})
    return {"schema_version": "1.0", "route": "theory", "paper_id": protocol["paper_id"],
            "lean_version": version, "theorems": results, "scientific_completion_verified": False,
            "interpretation": "Kernel checking applies to these exact formal types and assumptions. Human review must verify their correspondence to the manuscript, non-vacuity, originality and scope."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("protocol"); parser.add_argument("output")
    args = parser.parse_args()
    path = Path(args.protocol)
    result = verify(json.loads(path.read_text(encoding="utf-8")), Path.cwd())
    result.update(protocol_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
