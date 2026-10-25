"""Offline synthetic provider fixtures. No network, paid calls or actual study."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import economic_data as economic
from scripts.research_artifacts import read, sha, write


class EconomicDataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        environment = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1", "FRED_API_KEY": "a" * 32})
        environment.start(); self.addCleanup(environment.stop)
        self.spec = {"schema_version": "1.0", "id": "fixture", "provider": "fred", "scope": "metadata_only",
            "as_of": "2020-12-31", "vintage_mode": "snapshot_as_of", "start": "2019-01-01", "end": "2020-12-31",
            "max_pages": 3, "page_size": 1, "series": [{"id": "SYNTHETIC", "units": "Percent", "frequency": "Annual", "seasonal_adjustment": "Not Seasonally Adjusted"}]}
        self.save()
        self.urls = []

    def save(self):
        write(self.project/economic.request_path(self.spec["id"]), self.spec)

    def rights(self, *, confirmed=True):
        self.spec["scope"] = "observations"
        fields = ("provider", "start", "end", "as_of", "vintage_mode", "series") if self.spec["provider"] == "fred" else ("provider", "start", "end", "as_of", "vintage_mode", "countries", "indicators")
        host = "https://fred.stlouisfed.org/series/SYNTHETIC" if self.spec["provider"] == "fred" else "https://data.worldbank.org/indicator/SYNTHETIC"
        self.manifest = {"schema_version": "1.0", "dataset_id": "synthetic-econ", "title": "Synthetic fixture only", "provider": self.spec["provider"],
            "source_url": host, "version": "fixture", "accessed_at": "2020-12-31",
            "license": {"name": "Synthetic permission", "url": host, "research_use_allowed": True, "redistribution_allowed": False, "confirmed_by_human": confirmed},
            "download": {"url": host, "sha256": "pending", "expected_bytes": None},
            "provenance": {"collection_method": "Synthetic permission only", "transformations": [], "economic_scope": {key: self.spec[key] for key in fields}},
            "unit_of_analysis": "series-year", "split_strategy": "none", "known_limitations": ["Synthetic fixture is not real permission."]}
        path = self.project/"data/manifests/synthetic-econ.json"; write(path, self.manifest)
        self.spec["dataset_manifest"] = {"path": "data/manifests/synthetic-econ.json", "sha256": sha(path)}
        write(self.project/"state/data-authorizations.json", {"schema_version": "1.0", "manifests": {
            "data/manifests/synthetic-econ.json": {"sha256": sha(path), "cloud_use_confirmed": True, "actor": "Synthetic fixture owner"}}})
        self.save()

    def test_model_authored_licence_flag_cannot_replace_protected_owner_authorization(self):
        self.rights()
        auth = self.project/"state/data-authorizations.json"
        original = read(auth)
        auth.unlink()
        with self.assertRaisesRegex(ValueError, "protected owner"):
            economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.fred)
        original["manifests"]["data/manifests/synthetic-econ.json"]["sha256"] = "0"*64
        write(auth, original)
        with self.assertRaisesRegex(ValueError, "protected owner"):
            economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.fred)

    def fred(self, url, **kwargs):
        self.urls.append(url)
        parsed = urllib.parse.urlsplit(url); parameters = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parameters["api_key"], ["a" * 32])
        self.assertEqual(parameters["realtime_start"], [self.spec["as_of"]])
        self.assertEqual(parameters["realtime_end"], [self.spec["as_of"]])
        if parsed.path.endswith("/series"):
            payload = {"realtime_start": self.spec["as_of"], "realtime_end": self.spec["as_of"], "seriess": [self.spec["series"][0]]}
        else:
            index = int(parameters["offset"][0])
            payload = {"realtime_start": self.spec["as_of"], "realtime_end": self.spec["as_of"], "count": 2, "offset": index, "limit": 1,
                "observations": ([{"date": ["2019-01-01", "2020-01-01"][index], "value": ["1.25", "."][index], "realtime_start": self.spec["as_of"], "realtime_end": self.spec["as_of"]}] if index < 2 else [])}
        return json.dumps(payload).encode(), url, 200, "application/json"

    def worldbank_spec(self):
        self.spec.pop("series")
        self.spec.update(provider="worldbank", vintage_mode="retrieval_snapshot", as_of=datetime.now(timezone.utc).date().isoformat(),
            countries=["USA"], indicators=[{"id": "SYNTHETIC", "unit": ""}])
        self.save()

    def worldbank(self, url, **kwargs):
        self.urls.append(url)
        parsed = urllib.parse.urlsplit(url); parameters = urllib.parse.parse_qs(parsed.query)
        if "/country/" not in parsed.path:
            payload = [{"page": 1, "pages": 1, "total": 1}, [{"id": "SYNTHETIC", "unit": "", "sourceNote": "Synthetic metadata"}]]
        else:
            page = int(parameters["page"][0])
            payload = [{"page": page, "pages": 2, "per_page": "1", "total": 2},
                [{"indicator": {"id": "SYNTHETIC"}, "countryiso3code": "USA", "date": ["2019", "2020"][page-1], "value": [10, None][page-1]}]]
        return json.dumps(payload).encode(), url, 200, "application/json"

    def test_metadata_only_does_not_acquire_observations_or_assert_licence(self):
        result = economic.execute(self.project, "fixture", fetcher=self.fred)["report"]
        self.assertEqual(len(self.urls), 1)
        self.assertIsNone(result["rights"])
        self.assertEqual(result["scope"], "metadata_only")
        self.assertEqual(result["observation_count"], 0)
        self.assertFalse(result["scientific_validity_verified"])
        self.assertFalse(result["gate_approved"])
        self.assertEqual(economic.validate_saved_report(self.project, "fixture"), [])

    def test_metadata_discovery_can_leave_variable_units_unknown_until_returned(self):
        self.spec["series"] = [{"id": "SYNTHETIC"}]; self.save()
        def metadata(url, **kwargs):
            value = {"realtime_start": self.spec["as_of"], "realtime_end": self.spec["as_of"],
                "seriess": [{"id": "SYNTHETIC", "units": "Percent", "frequency": "Annual", "seasonal_adjustment": "Not Seasonally Adjusted"}]}
            return json.dumps(value).encode(), url, 200, "application/json"
        result = economic.execute(self.project, "fixture", fetcher=metadata)["report"]
        meta = next(output for output in result["outputs"] if output["path"].endswith("metadata.json"))
        self.assertEqual(json.loads((self.project/meta["path"]).read_text())[0]["units"], "Percent")
        self.rights()
        with self.assertRaisesRegex(ValueError, "FRED series"):
            economic.execute(self.project, "fixture", allow_observations=True, fetcher=metadata)

    def test_exact_fred_snapshot_pages_missing_values_and_cache_without_secret(self):
        self.rights()
        first = economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.fred)
        self.assertEqual(first["report"]["observation_count"], 2)
        self.assertEqual(first["report"]["missing_observations"], 1)
        self.assertTrue(first["report"]["pagination_complete"])
        self.assertEqual(len(self.urls), 3)
        second = economic.execute(self.project, "fixture", allow_observations=True, fetcher=lambda *a, **k: self.fail("cache should avoid new requests"))
        self.assertTrue(second["reused"])
        for path in self.project.rglob("*"):
            if path.is_file():
                self.assertNotIn(("a" * 32).encode(), path.read_bytes())
        csv_path = next(item["path"] for item in first["report"]["outputs"] if item["path"].endswith("observations.csv"))
        self.assertTrue(csv_path.startswith("data/raw/"))

    def test_observations_need_explicit_authorization_and_actual_licence(self):
        self.rights()
        with self.assertRaisesRegex(ValueError, "allow_observations"):
            economic.execute(self.project, "fixture", fetcher=self.fred)
        self.assertEqual(self.urls, [])
        self.rights(confirmed=False)
        with self.assertRaisesRegex(ValueError, "human-confirmed"):
            economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.fred)

    def test_manifest_source_scope_and_current_hash_are_bound(self):
        self.rights()
        target = self.project/self.spec["dataset_manifest"]["path"]
        self.manifest["provenance"]["economic_scope"]["as_of"] = "2019-12-31"
        write(target, self.manifest)
        with self.assertRaisesRegex(ValueError, "stale"):
            economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.fred)
        self.spec["dataset_manifest"]["sha256"] = sha(target); self.save()
        with self.assertRaisesRegex(ValueError, "protected owner"):
            economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.fred)
        # Even a synthetic renewed permission cannot relabel the actual query.
        auth_path = self.project/"state/data-authorizations.json"
        auth = read(auth_path)
        auth["manifests"][self.spec["dataset_manifest"]["path"]]["sha256"] = sha(target)
        write(auth_path, auth)
        with self.assertRaisesRegex(ValueError, "exact economic"):
            economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.fred)

    def test_provider_errors_and_key_echo_are_sanitized_and_not_saved(self):
        def failure(url, **kwargs):
            raise RuntimeError("provider error " + url)
        with self.assertRaises(ValueError) as caught:
            economic.execute(self.project, "fixture", fetcher=failure)
        self.assertNotIn("a" * 32, str(caught.exception))
        def echo(url, **kwargs):
            return json.dumps({"api_key": "a" * 32}).encode(), url, 200, "application/json"
        with self.assertRaisesRegex(ValueError, "unsafe data"):
            economic.execute(self.project, "fixture", fetcher=echo)
        self.assertFalse((self.project/economic.PREFIX).exists())

    def test_wrong_origin_and_wrong_units_are_rejected(self):
        def wrong_origin(url, **kwargs):
            return b"{}", "https://other.example/data", 200, "application/json"
        with self.assertRaisesRegex(ValueError, "unsafe data"):
            economic.execute(self.project, "fixture", fetcher=wrong_origin)
        def wrong_units(url, **kwargs):
            raw, final, status, content_type = self.fred(url, **kwargs)
            value = json.loads(raw); value["seriess"][0]["units"] = "Dollars"
            return json.dumps(value).encode(), final, status, content_type
        with self.assertRaisesRegex(ValueError, "dictionary"):
            economic.execute(self.project, "fixture", fetcher=wrong_units)

    def test_wrong_vintage_nonfinite_values_duplicates_and_truncated_pages_fail(self):
        self.rights()
        for defect in ("vintage", "nonfinite", "duplicate", "total"):
            def faulty(url, **kwargs):
                raw, final, status, content_type = self.fred(url, **kwargs)
                value = json.loads(raw)
                if "observations" in value:
                    if defect == "vintage":
                        value["realtime_start"] = "2021-01-01"
                    elif defect == "nonfinite":
                        value["observations"][0]["value"] = "NaN"
                    elif defect == "duplicate":
                        value["observations"][0]["date"] = "2019-01-01"
                    else:
                        value["count"] = 4
                return json.dumps(value).encode(), final, status, content_type
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                economic.execute(self.project, "fixture", allow_observations=True, fetcher=faulty)
        self.assertFalse((self.project/economic.PREFIX).exists())

    def test_page_cap_stops_without_inventing_complete_retrieval(self):
        self.rights(); self.spec["max_pages"] = 1; self.save()
        with self.assertRaisesRegex(ValueError, "pagination cap"):
            economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.fred)

    def test_saved_receipt_or_raw_tampering_cannot_reuse_or_rewrite_snapshot(self):
        result = economic.execute(self.project, "fixture", fetcher=self.fred)
        raw = self.project/result["report"]["outputs"][0]["path"]
        raw.write_text("{}", encoding="utf-8")
        self.assertTrue(economic.validate_saved_report(self.project, "fixture"))
        with self.assertRaisesRegex(ValueError, "snapshot is stale"):
            economic.execute(self.project, "fixture", fetcher=lambda *a, **k: self.fail("no retry of altered immutable snapshot"))

    def test_changed_request_invalidates_prior_receipt(self):
        economic.execute(self.project, "fixture", fetcher=self.fred)
        self.spec["series"][0]["frequency"] = "Monthly"; self.save()
        self.assertTrue(economic.validate_saved_report(self.project, "fixture"))

    def test_worldbank_is_current_snapshot_and_reconciles_all_pages(self):
        self.worldbank_spec(); self.rights()
        result = economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.worldbank)["report"]
        self.assertEqual(result["observation_count"], 2)
        self.assertEqual(len(self.urls), 3)
        self.assertFalse(result["historical_availability_verified"])
        self.assertEqual(economic.validate_saved_report(self.project, "fixture"), [])

    def test_worldbank_cannot_claim_a_historical_vintage_or_partial_year(self):
        self.worldbank_spec(); self.spec["as_of"] = "2020-12-31"; self.save()
        with self.assertRaisesRegex(ValueError, "historical vintages"):
            economic.execute(self.project, "fixture", fetcher=self.worldbank)
        self.spec["as_of"] = datetime.now(timezone.utc).date().isoformat(); self.spec["start"] = "2019-06-01"; self.save()
        with self.assertRaisesRegex(ValueError, "complete calendar-year"):
            economic.execute(self.project, "fixture", fetcher=self.worldbank)

    def test_previous_worldbank_snapshot_remains_valid_and_reuses_without_retrieval(self):
        self.worldbank_spec(); self.rights()
        economic.execute(self.project, "fixture", allow_observations=True, fetcher=self.worldbank)
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        with patch.object(economic, "datetime", wraps=datetime) as clock:
            clock.now.return_value = tomorrow
            self.assertEqual(economic.validate_saved_report(self.project, "fixture"), [])
            cached = economic.execute(self.project, "fixture", allow_observations=True,
                fetcher=lambda *a, **k: self.fail("do not fetch current data into yesterday's snapshot"))
            self.assertTrue(cached["reused"])

    def test_worldbank_wrong_country_or_changed_total_is_rejected(self):
        self.worldbank_spec(); self.rights()
        for defect in ("country", "total"):
            def faulty(url, **kwargs):
                raw, final, status, content_type = self.worldbank(url, **kwargs)
                value = json.loads(raw)
                if "/country/" in url:
                    if defect == "country":
                        value[1][0]["countryiso3code"] = "CAN"
                    else:
                        value[0]["total"] = 10
                return json.dumps(value).encode(), final, status, content_type
            with self.subTest(defect=defect), self.assertRaisesRegex(ValueError, "scope|pagination"):
                economic.execute(self.project, "fixture", allow_observations=True, fetcher=faulty)

    def test_keys_in_specs_future_dates_and_local_execution_are_forbidden(self):
        self.spec["api_key"] = "a" * 32; self.save()
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            economic.execute(self.project, "fixture", fetcher=self.fred)
        del self.spec["api_key"]; self.spec["as_of"] = "2999-12-31"; self.save()
        with self.assertRaisesRegex(ValueError, "as_of"):
            economic.execute(self.project, "fixture", fetcher=self.fred)
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "cloud executor"):
                economic.execute(self.project, "fixture", fetcher=self.fred)


if __name__ == "__main__":
    unittest.main()
