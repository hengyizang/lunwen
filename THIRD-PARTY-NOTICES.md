# Selected research-method sources

Selected files are retained unchanged at the commits and hashes listed in
`integrations/vendored-research-methods.json`. Native adaptations and adapters
are separately identified below. This notice does not relicense upstream work.

- K-Dense-AI/scientific-agent-skills: https://github.com/K-Dense-AI/scientific-agent-skills . Two complete selected skill directories and LICENSE.md are in `third_party/kdense/`; the retained MIT notice applies there. The repository-native wrapper skills route to the existing cloud control plane.
- Academic Research Skills and its Codex edition, by Cheng-I Wu: https://github.com/Imbad0202/academic-research-skills and https://github.com/Imbad0202/academic-research-skills-codex . The selected reviewer framework/rubric and evidence protocol are in `third_party/ars-review/` and `third_party/ars-codex/`. Their CC BY-NC 4.0 license is retained in `integrations/licenses/ars-cc-by-nc-4.0.txt`. `config/pre-submission-criteria.json`, `references/research-methods/submission-review.md` and `references/research-methods/evidence-arguments.md` incorporate attributed adaptations; questions are retained, native field contracts and computational criteria added, and numeric scoring is not introduced. These documents/configuration retain the noncommercial license and attribution. The deterministic Python adapters are independently implemented. The full upstream orchestration systems are not installed.
- Yuan1z0825/nature-skills: https://github.com/Yuan1z0825/nature-skills . Two deterministic figure auditors and their dependency declaration are retained in `third_party/nature-figure/`, and selected research/proposal references in `third_party/nature-methods/`. Root Apache 2.0 license text is retained in both directories. Native wrappers bind audit results to the existing renderer and gate; upstream audit files are unmodified. The proposal skill's SKILL frontmatter separately labels that component MIT; we selected its reference file and retained the repository license rather than claiming a uniform license for all upstream components.
- WUBING2023/PaperSpine: https://github.com/WUBING2023/PaperSpine . Selected evidence, citation-support and writing-rationale references are in `third_party/paperspine/`; the MIT copyright/license notice is in `integrations/licenses/paperspine-mit.txt`. Adaptations map these ideas onto existing ledgers rather than installing the standalone workbench.

The Nature collision auditor requires the separately installed PyMuPDF package.
It is a runtime dependency, not vendored source; its own license applies.
Review scope and deployment licensing when changing use. No credentials,
datasets, publisher manuscripts, paid service routes or upstream binaries are
included by this installation.
