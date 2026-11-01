# Automated data-rights evidence

`scripts/data_rights.py` implements one limited source adapter. It does not turn
dataset discovery metadata into authorization. `cloud_research_steps.acquire_data`
invokes it when an exact manifest lacks existing authorization.

The automatic route requires an exact published Zenodo record URL, an open
dataset declaration, explicit CC BY 4.0 or CC0 identity, matching title/version,
one exact provider file URL/size and a predeclared file SHA-256. The official
response is bounded, retained with its original bytes/hash, and protected from
model writes under `evidence/data-rights/<dataset_id>/metadata.json`.

The existing authorized writer supplies `provenance.rights_assessment` inside
the manifest, with the current metadata file hash, `personal_data: "none"`,
`cloud_use_allowed: true`, `additional_restrictions: false`, and substantive
`privacy_basis` and `terms_basis` strings. These are assessments, not provider
facts. The manifest needs current OpenAI writer provenance and the existing
G1 or G3 initial/final independent review must pass on the current inputs before
the controller records automatic authorization. No additional model call is
created by this adapter. The saved receipt identifies the original independent
review and explicitly records that no human confirmation or scientific
validity certification occurred.

A first pass may save the official metadata and stop with an unresolved
assessment. The normal writer/critic cycle can then prepare and inspect that
assessment. Unknown licenses, restricted records, personal/unknown data,
unsupported providers, changed inputs or missing independent reviews remain
data-rights evidence blockers. The controller never invents a permission or
requests a human signature as a substitute for missing evidence. Additional
providers need reviewed source-specific adapters.

Legacy authenticated owner authorizations remain readable. New automated
records never set `confirmed_by_human` to true.

The economic API path uses this same protected rights verifier instead of
requiring a new human licence signature. FRED and World Bank metadata alone
still do not supply an automatic rights adapter; until a source-specific adapter
exists, unresolved economic API rights remain an evidence blocker. This change
does not grant new provider permissions.

Primary references, accessed 2026-10-30:

- [Zenodo REST API and metadata fields](https://developers.zenodo.org/)
- [CC BY 4.0 terms and notices](https://creativecommons.org/licenses/by/4.0/)
- [CC0 1.0 terms and notices](https://creativecommons.org/publicdomain/zero/1.0/)

CC licensing concerns copyright permissions; privacy and other rights require
their own source-bound assessment. A successful software test does not verify
an actual dataset's rights or suitability.
