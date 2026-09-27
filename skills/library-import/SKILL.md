---
name: library-import
description: Index explicitly selected local Zotero exports, Obsidian notes and PDFs into a private hash-bound research wiki before lawful external literature expansion.
---

# Local research library

Ask the user for the exact D-drive/WSL folder and their authorization to read it. Use `--kind folder` for a hash-bound local index or `--kind obsidian` for notes, wiki links, tags, missing links and orphans. Use `--kind zotero-local` only while the desktop Zotero Local API is enabled; it reads the loopback endpoint without a cloud key and never mutates Zotero. Example: `scripts/local_library.py --project <slug> --kind obsidian --source '/mnt/d/ad/lunwen/vault' --actor '<person>'`.

The script creates project-local indexes but does not upload, copy or publish original files. Check malformed entries, license limits and source locations manually. Use PaperQA2 only on authorized local full text and keep its output advisory; DOI and content assertions require source-level validation.
