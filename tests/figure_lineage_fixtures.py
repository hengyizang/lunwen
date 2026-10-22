"""Synthetic sealed executor fixtures; never scientific evidence or approval."""
from pathlib import Path
import json
from scripts.research_artifacts import write,sha


def sealed_run(project:Path,*,paper_id="P01",run_id="r1",output="results/metrics.csv",body="group,value\nA,2\nA,4\nB,8\n"):
    target=project/output;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.is_file():target.write_text(body,encoding="utf-8")
    code=project/"analysis/executor-fixture.py";code.parent.mkdir(parents=True,exist_ok=True)
    code.write_text("# Synthetic preapproved executor fixture; no research outcome.\n",encoding="utf-8")
    run={"run_id":run_id,"paper_id":paper_id,"argv":["python","analysis/executor-fixture.py"],"cwd":".","seed":0,"timeout_seconds":30,
         "estimated_cost_usd":0,"inputs":[{"path":"analysis/executor-fixture.py","sha256":sha(code)}],"expected_outputs":[output],
         "isolation":{"kind":"container","engine":"docker","image":"python:3.12@sha256:"+"a"*64}}
    plan=project/"experiments/plan.json";write(plan,{"schema_version":"1.0","runs":[run]})
    budget=project/"experiments/budget.json";write(budget,{"status":"ready_for_review","hard_ceiling_usd":0})
    prereg=project/f"papers/{paper_id}/preregistration.json"
    write(prereg,{"status":"frozen","files":[{"path":"experiments/plan.json","sha256":sha(plan)},
        {"path":"experiments/budget.json","sha256":sha(budget)},{"path":"analysis/executor-fixture.py","sha256":sha(code)}]})
    approval={"gate":"G3","actor":"Synthetic Fixture Owner","experiment_plan_sha256":sha(plan),"experiment_budget_sha256":sha(budget),
              "frozen_protocol_sha256":{f"papers/{paper_id}/preregistration.json":sha(prereg)}}
    state=project/"state/run.json";write(state,{"stage":"writing-and-review","gate":"G5","status":"awaiting_work","approved_gates":["G3"],"approvals":[approval]})
    receipt={"schema_version":"1.0","run_id":run_id,"paper_id":paper_id,"attempt_id":run_id+"-attempt-001","status":"succeeded", "argv":run["argv"],
        "cwd":".","seed":0,"timeout_seconds":30,"exit_code":0,"timed_out":False,"approved_plan_sha256":sha(plan),"estimated_cost_usd":0.0,
        "started_at":"2026-10-23T00:00:00Z","finished_at":"2026-10-23T00:00:01Z","runtime_seconds":1.0,"inputs":run["inputs"],
        "input_integrity":{"verified_after_run":True,"passed":True,"mutated_or_missing":[]},"outputs":[{"path":output,"sha256":sha(target)}],"missing_outputs":[],
        "executor_isolation":{"isolated_executor":True,"network_disabled":True,"image":run["isolation"]["image"]}}
    write(project/f"experiments/runs/{receipt['attempt_id']}/run.json",receipt)
    registry=project/"experiments/registry.jsonl";registry.write_text(json.dumps(receipt)+"\n",encoding="utf-8")
    return run,approval,receipt
