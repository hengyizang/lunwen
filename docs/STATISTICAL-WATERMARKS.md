# Configured statistical watermark assessment

Unicode hygiene runs before and after writing. It removes supported character
carriers; it cannot establish whether token choices contain a statistical
watermark. This separate adapter runs after each existing G5 writer/remediator
pass and is recomputed at G5 approval and packaging. No extra model call, paid
detector, GPU, model switch or repeated rewrite loop is introduced.

Without an applicable configuration the result is `unknown`. Unknown is visible
coverage, never an absence certificate. The supported optional detector is the
Hugging Face CPU `WatermarkDetector` greenlist implementation, pinned to
transformers 4.57.1, torch 2.8.0 (CPU build allowed), and tokenizers 0.22.1.
Installation requires a reviewed cloud runtime change; the adapter never installs
packages or downloads a model/tokenizer. It loads no model weights.

The owner supplies `papers/P01/watermark-assessment.json` with these exact fields:

- `schema_version: "1.0"`, `detector: "hf-greenlist-v1"`;
- `applicability`: `scheme: "hf-greenlist"`, `generation_device: "cpu"`,
  `tokenizer_and_config_match: true`, and a current human-attested evidence
  `{path, sha256, locator}` for the actual generating scheme/configuration;
- `assets_dir`: a dedicated project-local directory with only supported tokenizer
  and config JSON files; `asset_sha256` maps every filename to its actual hash;
- `key_env`: a dedicated secret `DR_OS_WATERMARK_KEY_*` variable, with a
  non-secret `key_version` label. Never place the key in source or reports;
- `watermark`: explicit `greenlist_ratio`, `bias`, `seeding_scheme: "lefthash"`
  and `context_width` matching generation;
- `z_threshold` (2–10), `min_scored_tokens` (100–8192), and `sources` covering
  every canonical main.tex/include source or the canonical main.docx.

The author cannot change the profile. The complete text is assessed without
truncation, within 8192 tokens and 45 CPU seconds. Cached files must match their
hashes; remote code, executables, unsupported schemes and mismatched vocabularies
are refused. The subprocess uses offline mode and has no GPU visibility. Keys
and third-party exception messages are excluded from results and model context.

Configured positive results, insufficient independent tokens, missing keys,
missing dependencies and invalid caches block release. Supported safe character
cleanup remains automatic. A statistical positive is sent to the existing
evidence-preserving writer/remediator for a justified revision and a new scan;
the system cannot claim deterministic statistical removal or add paid retries.
Preserved originals, numeric/citation integrity and required disclosures remain.
`not_detected` means only that this detector, key, configuration, threshold and
extracted text did not produce a positive result. It does not prove absence,
human authorship or equivalence of scientific meaning.

SynthID, unknown vendor schemes, image watermarks, C2PA/EXIF, invisible PDF objects
and text outside the configured extraction scope remain explicitly unassessed.
The public SynthID reference implementation does not establish applicability to
a vendor's private watermark. Default/demo keys cannot substitute for that proof.
See the [official detector documentation](https://huggingface.co/docs/transformers/v4.57.1/en/internal/generation_utils#transformers.WatermarkDetector)
and [official SynthID Text implementation](https://github.com/google-deepmind/synthid-text).

Protected assessments live under `reports/statistical-watermarks/P01/`. Current
source/provenance/config/cache/implementation hashes enter human G5 approval.
The separate cloud CPU regression creates a tiny tokenizer and known marked and
unmarked token sequences using the actual library, without weights or provider
calls. These are engineering fixtures, not calibration on a research manuscript
or proof that an unknown intermediary's watermarks have been removed.
