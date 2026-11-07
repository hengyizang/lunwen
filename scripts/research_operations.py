"""Allowlisted operation metadata shared by cloud transport and execution."""
from dataclasses import dataclass
from importlib import import_module

_REQUIRED = object()


@dataclass(frozen=True)
class Request:
    module: str | None = None
    default: object = _REQUIRED
    keyword: str | None = None
    execute: bool = False
    task: str | None = None

    def __call__(self, project, operation):
        request = operation['request_file'] if self.default is _REQUIRED else operation.get('request_file', self.default)
        keywords = {}
        if self.execute:
            execute = operation.get('execute', False)
            if type(execute) is not bool:
                raise ValueError('execute must be an explicit boolean')
            keywords['execute'] = execute
        refresh = import_module('scripts.' + (self.module or operation['action'])).refresh
        if self.keyword:
            return refresh(project, **{self.keyword: request}, **keywords)
        return refresh(project, *((self.task, request) if self.task else (request,)), **keywords)


OPERATIONS = {
    "scientific_judgment": ({"task", "request_file"}, {"task", "request_file"}),
    "research_case": ({"paper_id", "kind"}, {"paper_id"}),
    "literature_screening_prepare": ({"receipt_id", "question"}, {"receipt_id", "question"}),
    "literature_source_scope": ({"paper_id"}, {"paper_id"}),
    "research_toolkit": ({"request_file"}, {"request_file"}, Request()),
    "research_iteration": ({"request_file"}, {"request_file"}, Request()),
    "research_frontier": ({"request_file"}, {"request_file"}, Request()),
    "research_search_tree": ({"request_file"}, {"request_file"}, Request()),
    "figure_gallery_sync": (set(), set()),
    "figure_gallery_search": ({"query", "top_k", "venues", "years", "tiers", "patterns", "topics", "semantic"}, {"query"}),
    "figure_story": ({"operation", "request_file"}, {"operation", "request_file"}),
    "editable_figure_export": ({"request_file"}, {"request_file"}),
    "editable_figure_verify": ({"receipt"}, {"receipt"}),
    "ccfa_task": ({"request"}, {"request"}),
    "ccfa_task_clear": ({"expected_active_sha256"}, {"expected_active_sha256"}),
    "ccfa_science": ({"operation", "request"}, {"operation", "request"}),
    "ccfa_humanization": ({"paper_id"}, set()),
    "literature_discover": ({"plan", "output"}, set()),
    "literature_resolve": ({"url"}, {"url"}),
    "literature_figures": ({"pdf", "manifest", "figures", "source_receipt", "question", "max_selected", "auto_discover"}, {"pdf", "manifest"}),
    "literature_register": ({"candidate_id", "expected_leads_sha256", "paper_id", "acquisition_receipt", "manifest", "reader", "config"},
                            {"candidate_id", "expected_leads_sha256"}),
    "literature_analyze": ({"paper_id", "config", "execute", "max_output_tokens"}, {"paper_id"}),
    "literature_workbench": ({"config"}, set()),
    "literature_search": ({"query", "paper_id", "topic_id", "limit"}, {"query"}),
    "literature_itinerary": ({"question", "paper_id", "topic_id", "limit", "reasoning", "progress"}, {"question"}),
    "literature_compare": ({"paper_ids", "question", "reasoning"}, {"paper_ids"}),
    "literature_progress": ({"request", "progress"}, {"request"}),
    "literature_retrieve": ({"request_file"}, set(), Request(module='literature_review', default='program/literature-retrieval.json')),
    "literature_reading_index": ({"paper_id", "locate_pdf"}, {"paper_id"}),
    "literature_coverage": ({"request_file"}, set()),
    "literature_matrix": ({"request_file"}, set(), Request(default='program/literature-extraction.json', keyword='request_path')),
    "literature_benchmark": ({"request_file"}, set(), Request(default='program/literature-benchmark.json')),
    "literature_semantic": ({"request_file"}, set(), Request(default='program/literature-semantic.json')),
    "literature_pdf": ({"request_file"}, set(), Request(default='program/literature-pdf.json')),
    "literature_zotero": ({"request_file"}, set(), Request(default='program/literature-zotero.json')),
    "literature_zotero_register": ({"request_file", "item_key", "paper_id"}, {"request_file", "item_key"}),
    "literature_roles": ({"request_file"}, set(), Request(default='program/literature-roles.json')),
    "literature_comparison": ({"request_file", "execute"}, set(), Request(default='program/literature-comparison.json', execute=True)),
    "literature_paperqa": ({"request_file", "execute"}, set(), Request(default='program/literature-paperqa.json', execute=True)),
    "data_row_prepare": ({"dataset_id", "key_columns"}, {"dataset_id"}),
    "data_row_provenance": ({"request_file"}, set(), Request(default='program/data-row-provenance.json')),
    "literature_source_trace": ({"request_file"}, set(), Request(module='literature_source_tasks', default='program/source-trace.json', task='source_trace')),
    "literature_screening_advice": ({"request_file"}, set(), Request(module='literature_source_tasks', default='program/screening-advice.json', task='screening_advice')),
    "literature_search_strategy": ({"request_file"}, set(), Request(default='program/literature-search-strategy.json')),
    "literature_synthesis": ({"request_file"}, set(), Request(default='program/literature-synthesis.json')),
    "diagram_mermaid": ({"request_file"}, set(), Request(default='program/diagram-mermaid.json')),
    "literature_feedback": ({"feedback", "expected_leads_sha256", "plan"}, {"feedback", "expected_leads_sha256"}),
    "literature_feedback_propose": ({"event_ids", "expected_plan_sha256", "proposal", "plan"}, {"event_ids", "expected_plan_sha256"}),
    "literature_feedback_review": ({"proposal_id", "expected_proposal_sha256", "expected_plan_sha256", "decision", "reviewed_by", "reason", "plan"},
                                  {"proposal_id", "expected_proposal_sha256", "expected_plan_sha256", "decision", "reviewed_by", "reason"}),
}

FIELDS = {name: value[:2] for name, value in OPERATIONS.items()}
AUTOMATED_OPERATIONS = set(OPERATIONS) - {'literature_feedback_review'}


def handler(action):
    specification = OPERATIONS.get(action, ())
    return specification[2] if len(specification) == 3 else None


BUILDERS = {
    'supplemental_prepare': (('writing-and-review',), 'supplemental_experiments.prepare', ('paper_id',)),
    'study_prepare': (('experiment-design',), 'study_routes.prepare_runtime', ('paper_id',)),
    'data_cleaning_preview': (('experiment-design',), 'data_contracts.preview_cleaning', ('dataset_id',)),
    'statistical_reporting': (('writing-and-review',), 'statistical_reporting.refresh', ('paper_id',)),
    'docx_revision': (('writing-and-review',), 'docx_revision.build', ('paper_id',)),
    'calibration_analysis': (('experiment-design', 'experiment-execution', 'paper-architecture', 'topic-intelligence', 'writing-and-review'), 'calibration_analysis.refresh', ('packet_id',)),
    'research_notebook': (('experiment-design', 'experiment-execution', 'paper-architecture', 'topic-intelligence', 'writing-and-review'), 'research_notebook.refresh', ()),
    'research_notebook_daily': (('experiment-design', 'experiment-execution', 'paper-architecture', 'topic-intelligence', 'writing-and-review'), 'research_notebook.daily_brief', ()),
    'revision_ledger': (('writing-and-review',), 'revision_ledger.refresh', ('paper_id',)),
    'research_support': (('experiment-design', 'experiment-execution', 'paper-architecture', 'topic-intelligence', 'writing-and-review'), 'research_support.refresh', ()),
    'support_sources': (('experiment-design', 'paper-architecture', 'topic-intelligence', 'writing-and-review'), 'research_support.fetch_sources', ()),
    'review_packets': (('experiment-design', 'experiment-execution', 'paper-architecture', 'topic-intelligence', 'writing-and-review'), 'review_packets.refresh', ()),
    'method_tools': (('experiment-design', 'experiment-execution'), 'method_tools.refresh', ()),
    'journal_dossiers': (('paper-architecture', 'writing-and-review'), 'journal_dossier.refresh', ()),
    'journal_sources': (('paper-architecture', 'writing-and-review'), 'journal_dossier.fetch_sources', ()),
    'compile_tex': (('writing-and-review',), 'cloud_runtime.compile_tex', ('paper_id',)),
}


def run_builder(project, operation, stage):
    specification = BUILDERS.get(operation.get('action'))
    if specification is None or stage not in specification[0]:
        return False
    _, target, fields = specification
    module, name = target.rsplit('.', 1)
    getattr(import_module('scripts.' + module), name)(project, *(operation[field] for field in fields))
    return True
