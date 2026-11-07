# Source-bound data acquisition

The owner policy of 2026-11-07 removes mandatory licence/research-use verification
before data acquisition. Licence metadata may remain absent or unknown; it is
never fabricated or automatically changed to a permission grant.

The existing acquisition controller checks the declared source, version, current
manifest hash, public HTTPS endpoint, file checksum and size. It records an
explicit technical source binding without claiming human licence confirmation or
verified research-use rights. Privacy and access restrictions remain applicable;
no authentication or access-control bypass is introduced.

The retired Zenodo-only licence/independent-rights-review gate and its unused
implementation have been removed. Historical source/approval receipts remain
unchanged. Discovery metadata still does not prove scientific suitability.

Complete experiment outputs, failed attempts, logs and registered comparisons are
backed up in `experiments/archive/Pxx/` and included in the existing cloud artifact
checkpoint. Backups are outside Git and the default model-writing snapshot.
Manuscripts need not reproduce complete logs; evidence changing a conclusion
belongs in the manuscript or supplements, with selection by scientific relevance.
