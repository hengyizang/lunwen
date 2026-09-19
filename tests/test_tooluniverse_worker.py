from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import tooluniverse_worker


class ToolUniverseWorkerTests(unittest.TestCase):
    def test_worker_loads_only_named_tool_and_uses_dictionary_api(self) -> None:
        calls: list[tuple[str, object]] = []

        class FakeUniverse:
            def load_tools(self, **kwargs):
                calls.append(("load", kwargs))

            def run(self, request):
                calls.append(("run", request))
                return {"ok": True}

        fake_module = types.SimpleNamespace(ToolUniverse=FakeUniverse)
        request = {
            "name": "UniProt_get_entry_by_accession",
            "arguments": {"accession": "P12345"},
        }
        with patch.dict(sys.modules, {"tooluniverse": fake_module}):
            result = tooluniverse_worker.execute(request)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            calls,
            [
                ("load", {"include_tools": ["UniProt_get_entry_by_accession"]}),
                ("run", request),
            ],
        )

    def test_request_rejects_extra_execution_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(
                json.dumps(
                    {"name": "list_tools", "arguments": {}, "python": "arbitrary"}
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                tooluniverse_worker.read_request(path)


if __name__ == "__main__":
    unittest.main()
