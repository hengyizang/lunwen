"""Self-contained search viewer for an already authorized cloud-built snapshot.

The browser filters that snapshot only. It cannot call providers, save scientific
records, grant permissions, or fetch an external service.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json

SCRIPT = r"""'use strict';
(() => {
  const data = JSON.parse(document.getElementById('literature-search-data').textContent);
  const form = document.getElementById('literature-search');
  const query = document.getElementById('reading-query');
  const topic = document.getElementById('reading-topic');
  const paper = document.getElementById('reading-paper');
  const kind = document.getElementById('reading-kind');
  const results = document.getElementById('reading-results');
  const status = document.getElementById('reading-status');
  const words = text => {
    const value = String(text).toLocaleLowerCase();
    const found = value.match(/[\p{L}\p{N}_]{2,}/gu) || [];
    for (const sequence of value.match(/[\u3400-\u9fff]+/g) || []) {
      for (let i = 0; i < sequence.length - 1; i++) found.push(sequence.slice(i, i + 2));
    }
    return found;
  };
  function option(select, value, label) {
    const item = document.createElement('option');
    item.value = value; item.textContent = label; select.append(item);
  }
  for (const value of data.topics) option(topic, value, value);
  for (const value of data.paperMappings) option(paper, value, value);
  const docs = data.documents.map(row => {
    const tokens = words(row.text + ' ' + row.title);
    const frequency = new Map();
    for (const token of tokens) frequency.set(token, (frequency.get(token) || 0) + 1);
    return {...row, frequency, length: Math.max(1, tokens.length)};
  });
  const average = docs.reduce((n, d) => n + d.length, 0) / Math.max(1, docs.length);
  function search() {
    const terms = [...new Set(words(query.value.slice(0, 500)))];
    const df = new Map(terms.map(t => [t, docs.filter(d => d.frequency.has(t)).length]));
    const matches = [];
    for (const row of docs) {
      if (topic.value && row.topic_id !== topic.value) continue;
      if (paper.value && !row.paper_ids.includes(paper.value)) continue;
      if (kind.value && row.kind !== kind.value) continue;
      let score = 0;
      for (const term of terms) {
        const frequency = row.frequency.get(term) || 0;
        if (!frequency) continue;
        const idf = Math.log(1 + (docs.length - df.get(term) + 0.5) / (df.get(term) + 0.5));
        score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * row.length / average));
      }
      if (!terms.length || score > 0) matches.push({row, score});
    }
    matches.sort((a, b) => b.score - a.score || a.row.key.localeCompare(b.row.key));
    results.replaceChildren();
    status.textContent = matches.length + ' matching source blocks; showing up to 50. Search is a reading aid, not a scientific verdict.';
    for (const {row} of matches.slice(0, 50)) {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = row.href; link.textContent = row.title + ' · ' + row.locator;
      const meta = document.createElement('p');
      meta.textContent = row.kind + ' · ' + (row.read_scope || 'Scope pending') + ' · ' + (row.topic_id || 'Topic pending') + ' · ' + row.paper_ids.join(', ');
      const snippet = document.createElement('pre');
      const lower = row.text.toLocaleLowerCase();
      const positions = terms.map(t => lower.indexOf(t)).filter(n => n >= 0);
      const start = positions.length ? Math.max(0, Math.min(...positions) - 100) : 0;
      snippet.textContent = (start ? '…' : '') + row.text.slice(start, start + 900);
      const identity = document.createElement('small');
      identity.textContent = row.path + ' · SHA-256 ' + row.sha256;
      item.append(link, meta, snippet, identity); results.append(item);
    }
  }
  form.addEventListener('submit', event => {event.preventDefault(); search();});
  for (const select of [topic, paper, kind]) select.addEventListener('change', search);
  const parameters = new URLSearchParams(location.search);
  const initial = parameters.get('q');
  if (initial) query.value = initial.slice(0, 500);
  for (const [select, key] of [[topic, 'topic'], [paper, 'paper'], [kind, 'material']]) {
    if ([...select.options].some(option => option.value === parameters.get(key))) select.value = parameters.get(key);
  }
  search();
})();
"""


def script_hash() -> str:
    return base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()


def payload(library: dict, index: dict, link) -> dict:
    papers = {p["id"]: p for p in library["papers"] if p["status"] == "current"}
    documents = []
    for number, row in enumerate(index["documents"]):
        paper = papers.get(row["paper_id"])
        if not paper:
            continue
        documents.append({"key": f"text-{number}", "paper_id": paper["id"], "title": paper["title"],
            "topic_id": paper.get("topic_id"), "paper_ids": paper["paper_ids"],
            "kind": "metadata" if paper.get("source_scope") == "metadata_only" else "fulltext",
            "read_scope": paper.get("read_scope"),
            "path": row["path"], "sha256": row["sha256"], "text": row["text"],
            "locator": f"PDF page {row['pdf_page']}" if row.get("pdf_page") else
                       f"lines {row['start_line']}-{row['end_line']}", "href": link(paper, row)})
    for paper in papers.values():
        for field, rows in paper["card"]["fields"].items():
            for number, row in enumerate(rows):
                anchor = row["evidence"][0]
                documents.append({"key": f"card-{paper['id']}-{field}-{number}",
                    "paper_id": paper["id"], "title": paper["title"], "topic_id": paper.get("topic_id"),
                    "paper_ids": paper["paper_ids"], "kind": "card", "path": anchor["path"],
                    "sha256": anchor["sha256"], "text": field + ": " + row["text"] + "\n" + anchor["quote"],
                    "locator": anchor["locator"], "href": link(paper, anchor)})
        for asset in (paper.get("figure_manifest") or {}).get("assets", []):
            for number, occurrence in enumerate(asset["occurrences"]):
                label = occurrence.get("caption") or "Original PDF asset; caption not verified"
                documents.append({"key": f"asset-{paper['id']}-{asset['sha256']}-{number}",
                    "paper_id": paper["id"], "title": paper["title"], "topic_id": paper.get("topic_id"),
                    "paper_ids": paper["paper_ids"], "kind": "figure", "path": asset["path"],
                    "sha256": asset["sha256"], "text": label,
                    "locator": f"PDF page {occurrence['pdf_page']}",
                    "href": link(paper, {**paper["source"], "pdf_page": occurrence["pdf_page"]})})
    return {"schema_version": "1.0", "scope": library["scope"], "documents": documents,
            "topics": sorted({p["topic_id"] for p in papers.values() if p.get("topic_id")}),
            "paperMappings": sorted({value for p in papers.values() for value in p["paper_ids"]}),
            "network_requests": False, "scientific_verdict": False}


def markup(data: dict) -> str:
    # A JSON string cannot terminate its data script or create HTML elements.
    encoded = json.dumps(data, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    encoded = encoded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return ('<section aria-labelledby="reading-search-title"><h2 id="reading-search-title">Search sources, notes and figures</h2>'
        '<form id="literature-search"><label>Question or keywords <input id="reading-query" maxlength="500" type="search"></label> '
        '<label>Topic <select id="reading-topic"><option value="">All topics</option></select></label> '
        '<label>Paper <select id="reading-paper"><option value="">All six papers</option></select></label> '
        '<label>Material <select id="reading-kind"><option value="">All materials</option>'
        '<option value="metadata">Discovery metadata only</option><option value="fulltext">Original text and notes</option><option value="card">Reading cards and experiment settings</option>'
        '<option value="figure">Original figure captions</option></select></label> <button type="submit">Search</button></form>'
        '<p id="reading-status" role="status"></p><ol id="reading-results"></ol>'
        '<noscript>Enable JavaScript to search this snapshot. Source links below remain available.</noscript></section>'
        '<script type="application/json" id="literature-search-data">' + encoded + '</script>'
        '<script>' + SCRIPT + '</script>')


def planning_markup(itinerary: dict, comparison: dict) -> str:
    """Readable views of recorded planning outputs; never a new scientific call."""
    esc = lambda value: html.escape(str(value), quote=True)
    parts = ['<section><h2>Reading route and experiment evidence</h2>',
        '<p><a href="itinerary.json">Download the complete reading route</a> · '
        '<a href="comparison.json">Download the complete experiment evidence packet</a></p>']
    if itinerary.get("question"):
        parts += ["<h3>Reading question</h3><p>" + esc(itinerary["question"]) + "</p>", "<ol>"]
        for step in itinerary.get("steps", [])[:60]:
            parts += ["<li><details><summary>" + esc(step.get("title", step.get("paper_id", ""))) +
                " · " + esc(step.get("phase", "reading")) + "</summary>"]
            for key in ("purpose", "question", "reason", "status"):
                if step.get(key):
                    parts.append("<p>" + esc(step[key]) + "</p>")
            for question in step.get("questions", []):
                parts.append("<p>" + esc(question) + "</p>")
            answer = step.get("recorded_answer")
            if answer:
                parts.append("<p>Recorded answer: " + esc(answer.get("answer", "")) + " · " + esc(answer.get("outcome", "")) + "</p>")
            parts.append("</details></li>")
        parts.append("</ol>")
    else:
        parts.append("<p>A reading question is needed before creating a reading route.</p>")
    axes = comparison.get("experiment_design_axes", [])
    if axes:
        parts.append("<h3>Experiment planning checks</h3><ul>")
        for axis in axes:
            parts.append("<li><strong>" + esc(axis.get("field", "")) + "</strong>: " +
                esc(axis.get("status", "source comparison required")) + " " + esc(axis.get("required_resolution", "")) + "</li>")
        parts.append("</ul>")
    parts.append("<p>Located evidence and proposals require scientific review. This view approves no gate or experiment.</p></section>")
    return "\n".join(parts)
