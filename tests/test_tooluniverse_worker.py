from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from scripts import tooluniverse_worker as worker


class ToolUniversePublicTests(unittest.TestCase):
    def test_only_fixed_tool_bounded_accessions_and_compact_output_are_allowed(self):
        for accession in ("P12345", "Q9Y261", "A0A023GPI8"):
            worker.validate_request({"name": worker.TOOL_NAME, "arguments": {"accession": accession}})
        for arguments in ({"accession": "../../secret"}, {"accession": "https://example.com"},
            {"accession": "P12345", "compact": False}, {"accession": "P12345", "compact": 1},
            {"accession": "P12345", "api_key": "secret"}, {"accession": ["P12345"]}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                worker.validate_request({"name": worker.TOOL_NAME, "arguments": arguments})
        with self.assertRaisesRegex(ValueError, "metered cost adapter"):
            worker.validate_request({"name": "arbitrary_agent", "arguments": {}})

    def test_sdk_source_drift_fails_before_import_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "uniprot_tool.py"
            source.write_text("changed implementation")
            distribution = types.SimpleNamespace(version=worker.SDK_VERSION, locate_file=lambda _: source)
            with patch.object(worker.metadata, "distribution", return_value=distribution):
                with self.assertRaisesRegex(ValueError, "reviewed source"):
                    worker.execute({"name": worker.TOOL_NAME, "arguments": {"accession": "P12345"}}, [])

    def test_sdk_errors_preserve_http_attempt_and_fail_main(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tooluniverse/uniprot_tool.py"
            source.parent.mkdir()
            source.write_bytes(b"reviewed source fixture")
            config = root / "tooluniverse/data/uniprot_tools.json"
            config.parent.mkdir()
            config.write_text(json.dumps([{"name": worker.TOOL_NAME, "type": "UniProtRESTTool", "fields": {"endpoint": worker.ENDPOINT}}]))
            request = root / "request.json"
            request.write_text(json.dumps({"name": worker.TOOL_NAME, "arguments": {"accession": "P12345"}}))
            http_get = Mock(return_value=types.SimpleNamespace(status_code=503))
            module = types.SimpleNamespace(__file__=str(source), requests=types.SimpleNamespace(get=http_get))
            class Tool:
                __module__ = "tooluniverse.uniprot_tool"
                def __init__(self, config):
                    self.tool_config = config
                    self.endpoint, self.extract_path = config["fields"]["endpoint"], None
                def run(self, arguments):
                    module.requests.get(self.endpoint.format(**arguments), timeout=15)
                    return {"status": "error", "error": "service unavailable"}
            module.UniProtRESTTool = Tool
            distribution = types.SimpleNamespace(version=worker.SDK_VERSION, locate_file=lambda path: root / path)
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(worker.metadata, "distribution", return_value=distribution), \
                patch.object(worker, "SOURCE_SHA256", hashlib.sha256(source.read_bytes()).hexdigest()), \
                patch.object(worker, "CONFIG_SHA256", hashlib.sha256(config.read_bytes()).hexdigest()), \
                patch.dict("sys.modules", {"tooluniverse.uniprot_tool": module}), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(worker.main([str(request)]), 1)
            http_get.assert_called_once_with("https://rest.uniprot.org/uniprotkb/P12345.json", timeout=15, allow_redirects=False)
            self.assertEqual(json.loads(stdout.getvalue())["http_attempts"][0]["http_status"], 503)
            self.assertIn("retrieval failed", stderr.getvalue())
