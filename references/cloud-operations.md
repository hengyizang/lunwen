# Cloud and local research operations

The same research task can use local tools, a managed cloud environment or the existing GitHub job transport. Choose available capabilities and preserve sources, actual outputs and cumulative costs. See [workflow.md](workflow.md) for the normal `autopilot` and `researchctl work` commands. G0–G5 labels in older adapters identify task context, not mandatory approvals.

## Existing operation queue

For an adapter that uses it, `program/cloud-operations.json` contains `{"schema_version":"1.0","operations":[...]}`. Each operation supplies the action and the fields required by that adapter; existing queue batches accept up to 16 operations. Results and failures are recorded in `state/research-steps.json`. Reuse unchanged results, and never write a fictional executor receipt yourself.

| Task | Available actions | Useful evidence |
| --- | --- | --- |
| Find sources | `direction_search`, `citation_graph`, `literature_discover`, `literature_search`, `literature_resolve` | Actual query/source and returned records; a lead is not scientific support. |
| Read and compare | `read_paper`, `literature_analyze`, `literature_reading_index`, `literature_progress`, `literature_compare` | Original page/text scope, attributed answers and unresolved questions. |
| Retrieve and synthesize | `retrieve_evidence`, `literature_semantic`, `literature_matrix`, `literature_synthesis` | Relevant supporting/contrary passages; ranking and OCR are navigation aids. |
| Work with data | `data_quality`, `data_contract`, `data_cleaning_preview`, `economic_data`, `empirical_design` | Source/version, actual acquired observations, transformations and method assumptions. |
| Execute | `run_experiments`, `run_supplemental` | Actual selected protocol, inputs and budget; retain outputs and all attempts. |
| Analyze | `power`, `method_tools`, `study_prepare`, `empirical_reporting`, `statistical_reporting` | Actual numerical execution with suitable units and uncertainty. |
| Figure and document | `render_figure`, `figure_gallery_search`, `figure_story`, `editable_figure_export`, `docx`, `compile_tex`, `word_render` | Actual data, editable source and rendered output. |
| Review and deliver | `citation_audit`, `journal_sources`, `journal_dossiers`, `docx_revision` | Relevant sources, current manuscript and actual target requirements. |

Read the selected command's `--help`, schema and method documentation for its concrete input shape. The queue's compatibility format does not require completing unrelated operations or documents. Invoke a suitable direct tool when a legacy adapter does not fit the research task.

## Acquisition and execution

Use actual public sources or already authorized material. Preserve original files and recorded privacy/access restrictions. Source/version/byte checks are useful; a generic licence-signature ceremony is not a prerequisite. Full-text extraction does not establish that a human or model read or understood the whole paper.

For an actual computational run, specify inputs, command, expected outputs and available resources. The existing runner can retain container isolation and detailed receipts. Use actual CPU/GPU/memory availability; a missing GPU or an unsupported engine limits that execution path, not every independent research task. Preserve prior attempts when changing a protocol or fixing engineering failures.

Use the project's authorized cumulative budget. Unknown charges with a conservative upper bound remain reserved; other affordable work may proceed. Do not reset a ledger, silently rent hardware, substitute claimed execution, or describe a failed response as a completed result.

## Search refinement and optional checks

Routine keyword, query and relevance adjustments may proceed within the authorized question. Keep the actual reason and changed sources; a new owner issue or approval is not required merely to refine a search. Topic, budget and external publication changes follow the user's actual instructions.

Paragraph plans, review packets, innovation matrices, benchmarking, three-view review and voice/lesson tools remain available when useful. Their administrative completion does not establish science and is not required for ordinary work. Historical owner-control requests remain compatible for reading or correcting older records; do not fabricate a human identity.
