"""Two-runner cloud acceptance using explicitly synthetic, non-research fixtures."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from scripts import cloud_checkpoint as cp, cloud_research_steps as steps, output_provenance
from scripts.live_acceptance import DEFAULT_IMAGE


def fixture(project: Path) -> None:
    if project.exists():
        raise ValueError('acceptance fixture must start in a fresh directory')
    code = """import json, os, sys
from pathlib import Path
assert not os.environ.get('UUAPI_API_KEY')
try:
    Path('state/run.json').write_text('forbidden')
except OSError:
    pass
else:
    raise RuntimeError('control state was writable')
if sys.argv[1] == 'negative':
    Path('results/negative.csv').write_text('group,effect\\nA,-0.5\\nB,-0.2\\n')
else:
    Path('results/failed.txt').write_text('intentional failure evidence')
    raise RuntimeError('intentional fixture failure; must be retained')
"""
    for rel, content in {'experiments/code/measure.py': code, 'experiments/config.yaml': 'seed: 7\n',
                         'evidence/literature/raw/source.xml': '<feed>synthetic fixture only</feed>',
                         'data/processed/fixture.parquet': 'PAR1synthetic-checkpoint-bytes-not-a-dataset'}.items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    runs = []
    for identifier, output in [('negative','negative.csv'), ('failure','failed.txt')]:
        runs.append({'run_id': identifier, 'paper_id': 'P01', 'argv': ['python3','experiments/code/measure.py',identifier],
                     'cwd': '.', 'seed': 7, 'timeout_seconds': 300, 'estimated_cost_usd': 0,
                     'isolation': {'kind':'container','engine':'docker','image':DEFAULT_IMAGE},
                     'inputs':[{'path':'experiments/code/measure.py','sha256':cp.sha(project/'experiments/code/measure.py')}],
                     'expected_outputs':['results/'+output]})
    steps.write(project/'experiments/plan.json', {'schema_version':'1.0','status':'ready_for_review','runs':runs})
    steps.write(project/'experiments/budget.json', {'schema_version':'1.0','status':'ready_for_review','hard_ceiling_usd':0})
    steps.write(project/'state/run.json', {'stage':'experiment-execution','gate':'G4','status':'awaiting_work',
                 'active_paper':'P01','synthetic_acceptance_only':True,'approvals':[{'gate':'G3',
                 'actor':'synthetic fixture, not a project approval',
                 'experiment_plan_sha256':cp.sha(project/'experiments/plan.json'),
                 'experiment_budget_sha256':cp.sha(project/'experiments/budget.json')}]})


def print_executor_diagnostics(project: Path) -> None:
    """Keep synthetic executor failures visible even before checkpoint creation."""
    for receipt in sorted((project / 'experiments/runs').glob('*/run.json')):
        record = steps.read(receipt)
        logs = {name: (project / record['logs'][name]).read_text(encoding='utf-8')[-12000:]
                for name in ('stdout', 'stderr')}
        print(json.dumps({'executor_receipt': record, 'log_tails': logs}), flush=True)


def produce(directory: Path) -> None:
    directory = directory.resolve()
    project = directory/'runner-one'/'acceptance-fixture'
    fixture(project)
    control_hash = cp.sha(project/'state/run.json')
    first = steps.resume_experiments(project)
    print_executor_diagnostics(project)
    if first.get('blockers') or first.get('pending_runs') != 1:
        raise RuntimeError('first controlled experiment did not succeed: '+json.dumps(first))
    second = steps.resume_experiments(project)
    print_executor_diagnostics(project)
    if not second.get('blockers') or cp.sha(project/'state/run.json') != control_hash:
        raise RuntimeError('failed attempt or immutable control state was not preserved')
    if '-0.5' not in (project/'results/negative.csv').read_text():
        raise RuntimeError('negative result was lost')
    steps.write(project/'api_runs/fixture/claude-plan.json', {'fixture':True,'readonly':True})
    steps.write(project/'.cache/model-responses/fixture.json', {'fixture':True,'cost_cny':0})
    transfer = directory/'transfer'
    manifest = cp.prepare(project, transfer, os.environ['GITHUB_RUN_ID'])
    for source in cp.git_files(project):
        target = transfer/'git'/'acceptance-fixture'/source.relative_to(project)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    hashes = {p.relative_to(project).as_posix():cp.sha(p) for p in project.rglob('*') if p.is_file()}
    steps.write(transfer/'hashes.json', hashes)
    steps.write(transfer/'produce.json', {'status':'passed','synthetic_acceptance_only':True,
                'negative_result_preserved':True,'failed_attempt_preserved':True,'control_state_readonly':True,
                'manifest':manifest,'source_commit':os.environ.get('GITHUB_SHA')})


def consume(directory: Path) -> None:
    directory = directory.resolve()
    transfer = directory/'transfer'
    project = directory/'runner-two'/'acceptance-fixture'
    shutil.copytree(transfer/'git'/'acceptance-fixture',project)
    cp.restore(project, transfer/'checkpoint.zip')
    for rel, digest in steps.read(transfer/'hashes.json').items():
        if cp.sha(project/rel) != digest:
            raise RuntimeError('fresh-runner restoration changed '+rel)
    registry_before = cp.sha(project/'experiments/registry.jsonl')
    decision = steps.resume_experiments(project)
    if not decision.get('blockers') or registry_before != cp.sha(project/'experiments/registry.jsonl'):
        raise RuntimeError('failed experiment was automatically retried')
    from scripts.cloud_runtime import prepare
    prepare(project)
    # Real renderers use executed synthetic values. These artifacts never enter
    # my-phd and cannot satisfy any scientific evidence or human review gate.
    from scripts.publication_figures import render
    spec = {'schema_version':'1.0','data':'results/negative.csv','output_stem':'papers/P01/figures/negative',
            'style':'technical','formats':['png','svg','pdf'],'dpi':300,'caption':'Synthetic negative-effect fixture.',
            'alt_text':'Two synthetic effects below zero.','claim_ids':['SYNTHETIC-ONLY'],
            'panels':[{'kind':'bar','x':'group','y':'effect','xlabel':'Synthetic group','ylabel':'Synthetic effect'}]}
    spec_path = project/'papers/P01/figures/negative.spec.json';steps.write(spec_path,spec);render(project,spec_path)
    from scripts.manuscript_docx import build
    manuscript = project/'papers/P01/manuscript';manuscript.mkdir(parents=True,exist_ok=True)
    source = manuscript/'source.md';source.write_text('# Acceptance fixture\n\nSynthetic values; not scientific findings.\n')
    metadata = manuscript/'metadata.json';steps.write(metadata,{'schema_version':'1.0','title':'Synthetic acceptance',
               'abstract':'This document verifies export only.','authors':[{'name':'Fixture'}],
               'keywords':['synthetic','acceptance','export']})
    tex = manuscript/'main.tex';tex.write_text(r'\documentclass{article}\begin{document}Synthetic acceptance only.\end{document}')
    output_provenance.record_model_writes(project,[source,metadata,tex],family='other',provider='synthetic-fixture',
        model='none',role='acceptance-only',run_id='fixture')
    build(project,source,metadata,manuscript/'main.docx',prefer_pandoc=False)
    from scripts.cloud_runtime import compile_tex
    compile_tex(project,'P01')
    import fitz
    with fitz.open(manuscript/'main.pdf') as document:
        if document.page_count != 1 or 'Synthetic acceptance only' not in document[0].get_text():
            raise RuntimeError('compiled PDF did not preserve fixture content')
    steps.write(directory/'acceptance.json', {'status':'passed','synthetic_acceptance_only':True,
        'requirement_ids':['R25','R26','R31'],'fresh_runner_restoration':True,'failed_attempt_not_retried':True,
        'native_docx':True,'vector_and_raster_figure':True,'isolated_tex_pdf':True,
        'source_commit':os.environ.get('GITHUB_SHA'),
        'workflow_run_url':f"https://github.com/hengyizang/lunwen/actions/runs/{os.environ['GITHUB_RUN_ID']}"})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['produce','consume']);p.add_argument('--directory',type=Path,required=True)
    args=p.parse_args();(produce if args.phase=='produce' else consume)(args.directory)


if __name__=='__main__':
    main()
