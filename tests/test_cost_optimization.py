from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import api_orchestrator as api, citation_audit, cloud_checkpoint, cloud_research_steps
from scripts import context_efficiency, cost_audit, evidence_context, model_runtime, paper_reader
from scripts.ai_providers import ModelResult


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def configuration(provider):
    anthropic = provider.endswith("anthropic")
    return {"configured": True, "model": "claude-test" if anthropic else "gpt-test",
            "protocol": "anthropic_messages" if anthropic else "openai_responses",
            "endpoint": "https://fixture.example/messages" if anthropic else "https://fixture.example/responses"}


def response(provider, prompt, **kwargs):
    config = configuration(provider)
    return ModelResult(provider, kwargs.get("model") or config["model"], "Fixture answer", {
        "input_tokens": 100, "output_tokens": 20}, "fixture-request", config["model"],
        config["protocol"], config["endpoint"], "fixture", completion_status="completed")


class LosslessContextTests(unittest.TestCase):
    def test_json_compaction_preserves_numeric_literals_strings_and_negative_evidence(self):
        source = '{\n  "estimate": 1.2345678901234567890123456789,\n  "zero": -0.000,\n  "huge": 123456789012345678901234567890,\n  "quote": "a  b\\n c",\n  "negative": "The null result contradicts the proposed mechanism."\n}\n'
        compact, representation = context_efficiency.lossless_text("evidence/result.json", source)
        self.assertLess(len(compact), len(source))
        self.assertEqual(representation, "json-whitespace-compacted")
        for token in ("1.2345678901234567890123456789", "-0.000", "123456789012345678901234567890", '"a  b\\n c"'):
            self.assertIn(token, compact)
        self.assertEqual(json.loads(compact), json.loads(source))
        prose = "Quote  with  spaces.\n\nNecessary uncertainty remains."
        self.assertEqual(context_efficiency.lossless_text("paper/main.tex", prose), (prose, None))

    def test_invalid_json_and_jsonl_record_boundaries_are_not_silently_repaired(self):
        invalid = '{ "unclosed": '
        self.assertEqual(context_efficiency.lossless_text("bad.json", invalid), (invalid, None))
        source = '{ "x": "one  two" }\n{ "x": -0.00 }\n'
        compact, _ = context_efficiency.lossless_text("events.jsonl", source)
        self.assertEqual(compact, '{"x":"one  two"}\n{"x":-0.00}\n')
        unicode_record = '{ "quote": "before\u2028after" }\n'
        preserved, _ = context_efficiency.lossless_text("events.jsonl", unicode_record)
        self.assertEqual(json.loads(preserved), json.loads(unicode_record))

    def test_default_snapshot_excludes_history_but_keeps_all_scientific_constraints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "projects/demo"
            write(project / "state/run.json", {"active_paper": "P01"})
            write(project / "state/runs/old/critic.stdout.txt", "OLD_PREFERRED_VERDICT" * 10000)
            write(project / "state/model-usage.jsonl", "BILLING_TRACE_ONLY")
            for name in ("model-route-decisions.jsonl", "dynamic-routing-acceptances.json", "task-routing-profile.json"):
                write(project / "state" / name, "OPERATIONAL_ROUTING_ONLY")
            write(project / "intake/constraints.json", {"cloud_only": True, "compute_ceiling": 0})
            write(project / "state/model-spend-control.json", {"authorized_ceiling_cny": 300})
            write(project / "evidence/contrary.md", "REGISTERED_NEGATIVE_RESULT")
            write(project / "papers/P01/manuscript/main.tex", "Current manuscript")
            write(project / "papers/P02/paper-contract.json", {"claim": "independent"})
            with patch.object(api, "ROOT", root):
                text = api.project_snapshot("demo", stage="writing-and-review", exclude_reviews=True)
            for required in ("REGISTERED_NEGATIVE_RESULT", "Current manuscript", "authorized_ceiling_cny", "compute_ceiling", "independent"):
                self.assertIn(required, text)
            self.assertNotIn("OLD_PREFERRED_VERDICT", text)
            self.assertNotIn("BILLING_TRACE_ONLY", text)
            self.assertNotIn("OPERATIONAL_ROUTING_ONLY", text)

    def test_snapshot_overflow_stops_instead_of_dropping_counterevidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "projects/demo/evidence/negative.md", "negative observation " * 100)
            with patch.object(api, "ROOT", root), patch.object(api, "MAX_SNAPSHOT_FILE_BYTES", 100):
                with self.assertRaisesRegex(ValueError, "source ranges"):
                    api.project_snapshot("demo", stage="topic-intelligence")
            with patch.object(api, "ROOT", root), patch.object(api, "MAX_SNAPSHOT_TOTAL_BYTES", 100):
                with self.assertRaisesRegex(ValueError, "never silently omit"):
                    api.project_snapshot("demo", stage="topic-intelligence")

    def test_duplicate_snippets_keep_both_stances_and_full_counterevidence(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            text = "INVARIANT_NEGATIVE_EVIDENCE\n"
            write(project / "evidence/source.md", text)
            digest = hashlib.sha256(text.encode()).hexdigest()
            items = [{"path": "evidence/source.md", "reason": "Inspect reported effect", "stance": "supports"},
                     {"path": "evidence/source.md", "reason": "Inspect contradictory finding", "stance": "contradicts"}]
            write(project / evidence_context.PLAN, {"schema_version": "1.0", "stages": {"topic-intelligence": {
                "question": "Does the mechanism survive contrary evidence?", "items": items}}})
            write(project / "program/research-notebook.json", {"questions": [{"evidence": [{
                "id": "counter", "stance": "contradicts", "source": {"path": "evidence/source.md", "sha256": digest}}]}]})
            packet = evidence_context.build(project, "topic-intelligence")
            self.assertEqual(packet["context"].count("INVARIANT_NEGATIVE_EVIDENCE"), 1)
            self.assertIn('"stance":"supports"', packet["context"])
            self.assertIn('"stance":"contradicts"', packet["context"])
            self.assertEqual(packet["duplicate_snippets_avoided"], 1)
            self.assertEqual(len(packet["bindings"]), 2)
            items[1]["end_line"] = 1
            write(project / "evidence/source.md", text + "More relevant negative evidence.\n")
            with self.assertRaises(ValueError):
                evidence_context.build(project, "topic-intelligence")

    def test_explicit_context_cannot_reintroduce_an_old_critic_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write(project / "state/runs/old/critic.stdout.txt", "Preferred verdict")
            with self.assertRaisesRegex(ValueError, "private, a prior review"):
                evidence_context.safe_text(project, "state/runs/old/critic.stdout.txt", lambda s: s)

    def test_stage_scoping_preserves_the_applicable_scientific_requirements(self):
        topic = api.stage_writing_instructions("topic-intelligence")
        design = api.stage_writing_instructions("experiment-design")
        writing = api.stage_writing_instructions("writing-and-review")
        for required in ("human-confirmed G0 weights", "closest works", "citation chaining", "rejection"):
            self.assertIn(required, topic)
        for required in ("strong", "negative controls", "stopping rules", "power", "preregistration", "clean-room"):
            self.assertIn(required, design)
        for required in ("every registered result locatable", "unfavorable", "AI-use disclosure", "strongest supported contribution", "post-hoc"):
            self.assertIn(required, writing)
        self.assertNotIn("At G5 write", topic)
        self.assertNotIn("At G1 also create", writing)

    def test_identical_output_does_not_rewrite_or_replace_existing_ancestry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "projects/demo/program/topic.md"
            write(target, "Unchanged supported claim")
            before = target.stat().st_mtime_ns
            bundle = {"stage": "topic-intelligence", "artifacts": [{"path": "program/topic.md", "content": target.read_text()}]}
            with patch.object(api, "ROOT", root):
                self.assertEqual(api.apply_bundle("demo", bundle, "topic-intelligence"), [])
            self.assertEqual(target.stat().st_mtime_ns, before)


class CostRuntimeTests(unittest.TestCase):
    def invoke(self, project, role="persistent-writer", stage="topic-intelligence"):
        return model_runtime.call(project, run_id="fixture", stage=stage, role=role,
                                  provider="uuapi-openai", prompt="Exact supported facts", max_output_tokens=100)

    def test_repeat_writer_reuses_response_but_new_scope_and_changed_response_do_not(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
                patch.object(model_runtime.ai_providers, "configuration", side_effect=configuration), \
                patch.object(model_runtime.ai_providers, "call", side_effect=response) as transport:
            project = Path(directory)
            first = self.invoke(project)
            self.assertTrue(self.invoke(project).cache_hit)
            self.assertEqual(transport.call_count, 1)
            self.assertFalse(self.invoke(project, role="persistent-remediator").cache_hit)
            self.assertFalse(self.invoke(project, stage="paper-architecture").cache_hit)
            path = project / ".cache/model-responses" / (first.cache_key + ".json")
            cached = json.loads(path.read_text())
            cached["text"] = "Corrupt replacement"
            write(path, cached)
            self.assertFalse(self.invoke(project).cache_hit)
            self.assertEqual(transport.call_count, 4)

    def test_reviews_and_health_never_replay_a_cached_assessment(self):
        for role in ("independent-critic-initial", "independent-critic-final", "independent-critique", "endpoint-health"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
                    patch.object(model_runtime.ai_providers, "configuration", side_effect=configuration), \
                    patch.object(model_runtime.ai_providers, "call", side_effect=response) as transport:
                self.assertFalse(self.invoke(Path(directory), role=role).cache_hit)
                self.assertFalse(self.invoke(Path(directory), role=role).cache_hit)
                self.assertEqual(transport.call_count, 2)

    def test_a_missing_later_route_stops_before_any_paid_role(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_REQUIRE_MODEL_AUTH": "1",
             "DR_OS_MODEL_PRICING_JSON": json.dumps({"claude-test": {"input_per_million": 2, "output_per_million": 10}})}, clear=True):
            root = Path(directory)
            write(root / "config/stages.json", {"stages": {"topic-intelligence": {"gate": "G1", "contract": "Topic", "author_task": "Compare evidence"}}})
            write(root / "projects/demo/state/run.json", {"stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work"})
            with patch.object(api, "ROOT", root), patch.object(api, "prepare_discovery_evidence", return_value=(json.dumps({
                    "literature": {"receipts": [{"fixture": True}], "pending_searches": 0}}), None)), \
                    patch.object(model_runtime.ai_providers, "configuration", side_effect=configuration), \
                    patch.object(model_runtime.ai_providers, "call") as transport:
                with self.assertRaises(model_runtime.ModelBudgetError):
                    api.run_cycle("demo", "topic-intelligence", "uuapi-anthropic", "uuapi-openai", "uuapi-anthropic", "", "", automatic_data=False)
                transport.assert_not_called()
            report = json.loads((root / "projects/demo/state/research-steps.json").read_text())
            self.assertIsNot(report.get("paid_model_cycle"), True)

    def test_ambiguous_transport_is_visible_and_never_reported_as_known_free(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
                patch.object(model_runtime.ai_providers, "configuration", side_effect=configuration), \
                patch.object(model_runtime.ai_providers, "call", side_effect=TimeoutError("lost response")) as transport:
            with self.assertRaises(TimeoutError):
                self.invoke(Path(directory))
            transport.assert_called_once()
            diagnostics = model_runtime.usage_summary(Path(directory))["cost_diagnostics"]
            self.assertEqual(diagnostics["uncertain_billing_entries"], 1)
            self.assertFalse(diagnostics["savings_or_scientific_equivalence_proven"])

    def test_audit_flags_repeat_candidates_without_removing_fresh_reviews(self):
        writer = {"role": "persistent-writer", "stage": "G1", "provider": "openai", "model": "fixture", "cache_key": "same", "cost_cny": 0.1}
        critic = {**writer, "role": "independent-critic-final"}
        report = cost_audit.summarize([writer, writer, critic, critic, {**writer, "cache_hit": True}])
        self.assertEqual(len(report["duplicate_paid_request_candidates"]), 1)
        self.assertEqual(report["fresh_review_or_health_attempts"], 2)
        self.assertEqual(report["cache_hits"], 1)
        self.assertFalse(report["duplicate_candidates_prove_waste"])


class MetadataCacheTests(unittest.TestCase):
    def bibliography(self, root, title="A Reliable Structural Model"):
        bib = root / "papers/P01/manuscript/references.bib"
        write(bib, '@article{study,\n title = {' + title + '},\n year = {2025},\n doi = {10.1234/example}\n}\n')
        return bib

    def record(self):
        return {"title": ["A Reliable Structural Model"], "issued": {"date-parts": [[2025]]}, "type": "journal-article"}

    def test_metadata_reuse_never_reuses_a_bibliography_pass_or_offline_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bib = self.bibliography(root)
            cache = root / "state/citation-metadata"
            fetch = Mock(return_value={"message": self.record()})
            self.assertEqual(citation_audit.audit(bib, cache_directory=cache, fetcher=fetch)["status"], "pass")
            self.bibliography(root, "An unrelated fabricated title")
            self.assertEqual(citation_audit.audit(bib, cache_directory=cache, fetcher=fetch)["status"], "fail")
            self.assertEqual(fetch.call_count, 1)
            self.bibliography(root)
            self.assertEqual(citation_audit.audit(bib, cache_directory=cache, fetcher=fetch, offline=True)["status"], "fail")
            self.assertEqual(fetch.call_count, 1)

    def test_expired_corrupt_future_and_force_refresh_metadata_are_refetched(self):
        for mode in ("expired", "corrupt", "future", "refresh"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                bib = self.bibliography(root)
                cache = root / "state/citation-metadata"
                fetch = Mock(return_value={"message": self.record()})
                citation_audit.audit(bib, cache_directory=cache, fetcher=fetch)
                path = next(cache.glob("*.json"))
                value = json.loads(path.read_text())
                if mode == "expired": value["retrieved_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
                if mode == "future": value["retrieved_at"] = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
                if mode == "corrupt": value["record"]["title"] = ["Modified without a matching hash"]
                write(path, value)
                citation_audit.audit(bib, cache_directory=cache, fetcher=fetch, refresh_metadata=mode == "refresh")
                self.assertEqual(fetch.call_count, 2)

    def test_controlled_citation_audit_reuses_only_metadata_and_protects_its_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.bibliography(root)
            write(root / "program/cloud-operations.json", {"operations": [{"stage": "writing-and-review", "action": "citation_audit", "paper_id": "P01"}]})
            with patch.object(citation_audit, "crossref_record", return_value=self.record()) as fetch:
                first = cloud_research_steps.after_write(root, "writing-and-review")
                second = cloud_research_steps.after_write(root, "writing-and-review")
            self.assertFalse(first["operation_errors"])
            self.assertFalse(second["operation_errors"])
            self.assertEqual(fetch.call_count, 1)
            report = json.loads((root / "papers/P01/reviews/citation-audit.json").read_text())
            self.assertEqual(report["status"], "pass")
            with patch.object(api, "ROOT", root.parent):
                from scripts.artifact_ownership import executor_owned
                self.assertTrue(executor_owned(root, "papers/P01/reviews/citation-audit.json"))

    def test_native_reader_cache_checks_pdf_output_scope_and_implementation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf, output = root / "source.pdf", root / "literature/readers/source.md"
            pdf.write_bytes(b"Synthetic receipt-validation input, not a real PDF")
            write(output, "Extracted original page")
            mapping = output.with_suffix(".source-map.json")
            digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            write(mapping, {"source_sha256": digest(pdf), "reader_sha256": digest(output), "source_blocks": [{"pdf_page": 1}]})
            receipt = {"page_count": 1, "selected_pages": [1], "translation_provider": None,
                       "reader_implementation_sha256": digest(Path(paper_reader.__file__)),
                       "pdf_sha256": digest(pdf), "reader_sha256": digest(output),
                       "source_map": {"path": mapping.relative_to(root).as_posix(), "sha256": digest(mapping)}}
            write(output.with_suffix(".reader.json"), receipt)
            self.assertTrue(paper_reader.reusable_reader(root, pdf, output))
            self.assertFalse(paper_reader.reusable_reader(root, pdf, output, pages=[1, 1]))
            pdf.write_bytes(b"Changed source")
            self.assertFalse(paper_reader.reusable_reader(root, pdf, output))

    def test_metadata_cache_is_archived_without_relaxing_authority_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "state/citation-metadata/fixture.json", {"record": "public metadata"})
            rows = cloud_checkpoint.inventory(root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["storage"], "artifact")


class HealthBudgetBoundaryTests(unittest.TestCase):
    def test_live_probe_without_project_or_authority_cannot_reach_transport(self):
        from scripts import model_health
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
                patch.object(model_runtime.ai_providers, "configuration", side_effect=configuration), \
                patch.object(model_runtime.ai_providers, "call") as transport:
            with self.assertRaises(ValueError):
                api.health_report(["uuapi-openai"], live=True)
            with self.assertRaises(RuntimeError):
                api.health_report(["uuapi-openai"], live=True, root=Path(directory))
            report = model_health.probe(Path(directory), "uuapi-openai", "gpt-test", execute=True)
            self.assertFalse(report["paid_call"])
            self.assertEqual(report["status"], "failed")
            self.assertNotIn("DR_OS_REQUIRE_MODEL_AUTH", os.environ)
            transport.assert_not_called()

    def test_zero_budget_probe_and_free_configuration_check_remain_unbilled(self):
        from scripts import model_spend
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "DR_OS_MODEL_PRICING_JSON": json.dumps({"gpt-test": {"input_per_million": 2, "output_per_million": 10}})}, clear=True), \
                patch.object(model_runtime.ai_providers, "configuration", side_effect=configuration), \
                patch.object(model_runtime.ai_providers, "call") as transport:
            root = Path(directory)
            model_spend.write(root, model_spend.initial())
            report, failed = api.health_report(["uuapi-openai"], live=True, root=root)
            self.assertTrue(failed)
            self.assertEqual(report["providers"][0]["live_probe"]["status"], "fail")
            dry, failed = api.health_report(["uuapi-openai"], live=False)
            self.assertFalse(failed)
            self.assertFalse(dry["live_probe_is_billable"])
            self.assertFalse(model_runtime.ledger_entries(root))
            transport.assert_not_called()

    def test_authorized_live_probe_is_fresh_and_settles_the_shared_ledger(self):
        from scripts import model_spend
        def ok_response(*args, **kwargs):
            result = response(*args, **kwargs)
            result.text = "OK"
            return result
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "DR_OS_MODEL_PRICING_JSON": json.dumps({"gpt-test": {"input_per_million": 2, "output_per_million": 10}})}, clear=True), \
                patch.object(model_runtime.ai_providers, "configuration", side_effect=configuration), \
                patch.object(model_runtime.ai_providers, "call", side_effect=ok_response) as transport:
            root = Path(directory)
            model_spend.write(root, model_spend.initial())
            model_spend.grant(root, new_ceiling_cny=300, actor="Fixture owner", run_id="fixture")
            report, failed = api.health_report(["uuapi-openai"], live=True, root=root)
            self.assertFalse(failed)
            self.assertEqual(report["providers"][0]["live_probe"]["status"], "pass")
            self.assertEqual(transport.call_count, 1)
            control = model_spend.read(root)
            self.assertGreater(control["spent_cny"], 0)
            self.assertFalse(control["reservations"])
            self.assertEqual(model_runtime.ledger_entries(root)[0]["role"], "endpoint-health")


class RetrievalAndSearchReuseTests(unittest.TestCase):
    def test_lexical_retrieval_keeps_source_hashes_and_never_excludes_evidence(self):
        from scripts import evidence_retrieval
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "evidence/positive.md", "Accuracy improved on the reported benchmark.\n")
            write(root / "evidence/negative.md", "Robustness analysis contradicts the proposed mechanism.\n")
            sources = [{"path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
                       for name in ("evidence/positive.md", "evidence/negative.md")]
            spec = {"schema_version": "1.0", "query": "robustness mechanism", "sources": sources, "limit": 1}
            result = evidence_retrieval.retrieve(root, spec)
            self.assertEqual(result["results"][0]["path"], "evidence/negative.md")
            self.assertEqual(len(result["searched_sources"]), 2)
            self.assertFalse(result["automatic_source_exclusion"])
            self.assertFalse(result["scientific_completeness_verified"])
            write(root / "evidence/negative.md", "Changed contrary evidence")
            with self.assertRaisesRegex(ValueError, "source changed"):
                evidence_retrieval.retrieve(root, spec)

    def test_oversized_match_is_a_locator_not_a_fabricated_truncated_quote(self):
        from scripts import evidence_retrieval
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "evidence/long.md"
            write(source, "robustness " * 1000)
            result = evidence_retrieval.retrieve(root, {"schema_version": "1.0", "query": "robustness", "sources": [{
                "path": "evidence/long.md", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]})
            self.assertIsNone(result["results"][0]["quote"])
            self.assertTrue(result["results"][0]["quote_omitted_due_to_size"])
            self.assertEqual(result["results"][0]["start_line"], 1)

    def test_duplicate_search_is_one_request_but_changed_limit_is_not_reused(self):
        from scripts import literature_evidence
        original = literature_evidence.execute_search
        payload = json.dumps({"message": {"items": [{"DOI": "10.1234/fixture", "title": ["Robustness fixture"]}]}}).encode()
        fetcher = Mock(side_effect=lambda url, **kwargs: (payload, url, 200, "application/json"))
        def execute(*args, **kwargs):
            return original(*args, **kwargs, fetcher=fetcher)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"provider": "crossref", "query": "robustness", "query_family": "direct", "limit": 1}
            write(root / "program/literature-search-plan.json", {"searches": [item, item]})
            with patch.object(literature_evidence, "execute_search", side_effect=execute):
                first = cloud_research_steps.literature_context(root, "unused")
                self.assertEqual(first["new_search_calls"], 1)
                self.assertEqual(len(first["receipts"]), 1)
                write(root / "program/literature-search-plan.json", {"searches": [{**item, "limit": 2}]})
                second = cloud_research_steps.literature_context(root, "unused")
                self.assertEqual(second["new_search_calls"], 1)
            self.assertEqual(fetcher.call_count, 2)

    def test_requested_search_scope_is_counted_before_the_bounded_preview(self):
        from scripts import literature_evidence
        original = literature_evidence.execute_search
        payload = json.dumps({"message": {"items": [{"DOI": f"10.1234/fixture{i}", "title": [f"Robustness fixture {i}"]} for i in range(50)]}}).encode()
        def execute(*args, **kwargs):
            return original(*args, **kwargs, fetcher=lambda url, **kw: (payload, url, 200, "application/json"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "program/literature-search-plan.json", {"searches": [{
                "provider": "crossref", "query": "robustness", "query_family": "direct", "limit": 50}]})
            with patch.object(literature_evidence, "execute_search", side_effect=execute):
                result = cloud_research_steps.literature_context(root, "unused")
            self.assertEqual(result["work_count"], 50)
            self.assertEqual(len(result["works"]), 50)
            self.assertEqual(result["works_omitted"], 0)


if __name__ == "__main__":
    unittest.main()
