"""Offline payload, identity, billing and media contracts for native gateways."""
from __future__ import annotations

import base64
import io
import hashlib
import http.client
import json
import os
import unittest
import urllib.error
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import ai_providers as providers


class ProductionProviderTests(unittest.TestCase):
    def setUp(self):
        # This suite isolates payload/HTTP behavior; real durable guard and
        # unleased-POST rejection are exercised by test_relay_guard.
        guard=patch("scripts.relay_guard.authorize_transport",return_value=None)
        guard.start();self.addCleanup(guard.stop)

    def test_direct_production_transport_rejects_noncloud_generation_before_network(self):
        with patch.dict(os.environ,{},clear=True), patch.object(providers.urllib.request,"build_opener") as network:
            with self.assertRaisesRegex(providers.ProviderError,"cloud runner"):
                providers._production_request("https://codekey.ai/v1/chat/completions",{}, {},30)
            network.assert_not_called()

    def env(self):
        return {"GITHUB_ACTIONS":"true", **{spec["key_setting"]: f"fixture-only-{name}"
                for name, spec in providers.PRODUCTION_PROVIDERS.items() if name != "codekey-gemini-chat"}}

    def response(self, family="openai", model="gpt-6.1-sol", protocol=None):
        if family == "google" and protocol != "openai_chat_completions":
            return {"modelVersion": model, "responseId": "gemini-fixture",
                    "candidates": [{"finishReason": "STOP", "content": {"parts": [
                        {"text": "private thought", "thought": True}, {"text": "final text"}]}}],
                    "usageMetadata": {"promptTokenCount": 100, "cachedContentTokenCount": 30,
                                      "candidatesTokenCount": 10, "thoughtsTokenCount": 20,
                                      "totalTokenCount": 130}}
        if family == "deepseek" or protocol == "openai_chat_completions":
            return {"model": model, "id": "ds-fixture", "choices": [{"finish_reason": "stop",
                    "message": {"content": "final text", "reasoning_content": "private thought"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 30,
                              "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 60,
                              "completion_tokens_details": {"reasoning_tokens": 20}}}
        if family == "anthropic":
            return {"model": model, "id": "claude-fixture", "stop_reason": "end_turn",
                    "content": [{"type": "thinking", "thinking": "private thought"},
                                {"type": "text", "text": "final text"}],
                    "usage": {"input_tokens": 100, "output_tokens": 30,
                              "cache_read_input_tokens": 20,
                              "cache_creation_input_tokens": 10}}
        return {"model": model, "id": "openai-fixture", "status": "completed",
                "output_text": "final text", "usage": {"input_tokens": 100, "output_tokens": 30,
                    "input_tokens_details": {"cached_tokens": 20},
                    "output_tokens_details": {"reasoning_tokens": 10}}}

    def invoke(self, route, response=None, **kwargs):
        spec = providers.PRODUCTION_PROVIDERS[route]
        response = response or self.response(spec["family"], kwargs.get("model", spec["model"]), spec["protocol"])
        with patch.dict(os.environ, self.env(), clear=True), patch.object(
                providers, "_production_request", return_value=response) as transport:
            result = providers.call(route, "prompt fixture", system="system fixture", **kwargs)
        return result, transport

    def attachment(self, mime="application/pdf", content=b"%PDF-1.4\nfixture"):
        return {"mime_type": mime, "data_base64": base64.b64encode(content).decode(),
                "sha256": hashlib.sha256(content).hexdigest(), "filename": "fixture.pdf"}

    def test_production_configuration_is_offline_exact_and_secret_free(self):
        with patch.object(providers, "_production_request") as transport:
            for route, spec in providers.PRODUCTION_PROVIDERS.items():
                config = providers.configuration(route, self.env())
                self.assertTrue(config["configured"])
                self.assertEqual(config["family"], spec["family"])
                self.assertEqual(config["model"], spec["model"])
                self.assertTrue(config["strict_model_id"])
                self.assertEqual(config["billing_identity"],
                                 {"plan": "production", "group": route, "mode": "standard"})
                self.assertNotIn(self.env()[spec["key_setting"]], json.dumps(config))
                self.assertFalse(providers.configuration(route, {})["configured"])
            transport.assert_not_called()

    def test_families_never_infer_independence_from_endpoint(self):
        self.assertEqual({providers.provider_family(route) for route in providers.PRODUCTION_PROVIDERS},
                         {"openai", "anthropic", "deepseek", "google", "moonshot"})
        self.assertEqual(providers.provider_family("cheapai-gpt-pro"),
                         providers.provider_family("cheapai-gpt-discount"))

    def test_openai_reasoning_store_and_tools_are_explicit(self):
        result, transport = self.invoke("cheapai-gpt-pro", model="gpt-6-astra", reasoning_effort="high")
        endpoint, headers, payload, timeout = transport.call_args.args
        self.assertEqual(endpoint, "https://cheapai.info/v1/responses")
        self.assertEqual(headers["Authorization"], "Bearer fixture-only-cheapai-gpt-pro")
        self.assertEqual(payload["reasoning"], {"effort": "high"})
        self.assertEqual(payload["tools"], [])
        self.assertEqual(payload["service_tier"], "default")
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["input"][0]["role"], "developer")
        self.assertEqual(result.requested_effort, "high")
        self.assertEqual(result.reported_model, "gpt-6-astra")
        self.assertEqual(result.completion_status, "completed")

    def test_luna_uses_dedicated_discount_key_and_medium(self):
        result, transport = self.invoke("cheapai-gpt-discount")
        self.assertEqual(result.model, "gpt-5.6-luna")
        self.assertEqual(result.requested_effort, "medium")
        self.assertEqual(transport.call_args.args[2]["reasoning"], {"effort": "medium"})
        self.assertIn("fixture-only-cheapai-gpt-discount", transport.call_args.args[1]["Authorization"])

    def test_claude_adaptive_high_read_only_native_payload(self):
        result, transport = self.invoke("codekey-kiro-enterprise", model="claude-opus-5-5")
        endpoint, headers, payload, timeout = transport.call_args.args
        self.assertEqual(endpoint, "https://codekey.ai/v1/messages")
        self.assertIn("x-api-key", headers)
        self.assertNotIn("Authorization", headers)
        self.assertEqual(payload["thinking"], {"type": "adaptive"})
        self.assertEqual(payload["output_config"], {"effort": "high"})
        self.assertEqual(payload["tools"], [])
        self.assertNotIn("private thought", result.text)
        self.assertEqual(result.usage["cache_creation_input_tokens"], 10)

    def test_deepseek_thinking_cache_and_reasoning_are_counted_once(self):
        result, transport = self.invoke("codekey-deepseek")
        endpoint, headers, payload, timeout = transport.call_args.args
        self.assertEqual(endpoint, "https://codekey.ai/v1/chat/completions")
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(result.usage["input_tokens"], 100)
        self.assertEqual(result.usage["input_tokens_details"]["cached_tokens"], 40)
        self.assertEqual(result.usage["output_tokens"], 30)
        self.assertEqual(result.usage["output_tokens_details"]["reasoning_tokens"], 20)
        self.assertEqual(providers.provider_family(result.provider), "deepseek")
        self.assertNotIn("private thought", result.text)

    def test_google_native_auth_and_candidate_plus_thoughts_accounting(self):
        result, transport = self.invoke("codekey-gemini")
        endpoint, headers, payload, timeout = transport.call_args.args
        self.assertEqual(endpoint, "https://codekey.ai/v1beta/models/gemini-4-argon:generateContent")
        self.assertEqual(headers, {"x-goog-api-key": "fixture-only-codekey-gemini"})
        self.assertNotIn("key=", endpoint)
        self.assertEqual(payload["generationConfig"]["thinkingConfig"], {"thinkingLevel": "HIGH"})
        self.assertEqual(result.usage["output_tokens"], 30)
        self.assertEqual(result.usage["output_tokens_details"]["reasoning_tokens"], 20)
        self.assertEqual(result.usage["input_tokens_details"]["cached_tokens"], 30)
        self.assertEqual(result.text, "final text")

    def test_bad_cache_receipts_fail_without_generation_retry(self):
        for field, value in (("prompt_cache_hit_tokens", 101), ("prompt_cache_miss_tokens", 1)):
            response = self.response("deepseek", "deepseek-v4.1-flash")
            response["usage"][field] = value
            with self.subTest(field=field), patch.dict(os.environ, self.env(), clear=True), patch.object(
                    providers, "_production_request", return_value=response) as transport:
                with self.assertRaises(providers.ProviderError):
                    providers.call("codekey-deepseek", "fixture")
                transport.assert_called_once()

    def test_google_bad_total_or_cache_receipt_fails(self):
        for field, value in (("cachedContentTokenCount", 101), ("totalTokenCount", 100)):
            response = self.response("google", "gemini-4-argon")
            response["usageMetadata"][field] = value
            with patch.dict(os.environ, self.env(), clear=True), patch.object(
                    providers, "_production_request", return_value=response):
                with self.assertRaises(providers.ProviderError):
                    providers.call("codekey-gemini", "fixture")

    def test_unknown_usage_and_unexpected_tool_results_fail_closed(self):
        for usage in (None, {"prompt_tokens": True, "completion_tokens": 10},
                      {"prompt_tokens": 10, "completion_tokens": float("nan")}):
            response = self.response("deepseek", "deepseek-v4.1-flash")
            response["usage"] = usage
            with patch.dict(os.environ, self.env(), clear=True), patch.object(
                    providers, "_production_request", return_value=response):
                with self.assertRaises(providers.ProviderError):
                    providers.call("codekey-deepseek", "fixture")
        response = self.response("deepseek", "deepseek-v4.1-flash")
        response["choices"][0]["message"]["tool_calls"] = [{"id": "not-authorized"}]
        with patch.dict(os.environ, self.env(), clear=True), patch.object(
                providers, "_production_request", return_value=response):
            with self.assertRaises(providers.ProviderError):
                providers.call("codekey-deepseek", "fixture")

    def test_model_allowlists_stop_cross_family_and_unapproved_route_changes(self):
        with patch.dict(os.environ, self.env(), clear=True), patch.object(providers, "_production_request") as transport:
            for route, model in (("cheapai-gpt-pro", "deepseek-v4.1-flash"),
                                 ("cheapai-gpt-discount", "gpt-6-luna"),
                                 ("codekey-deepseek", "gpt-6.1-sol"),
                                 ("codekey-gemini", "gemini-4-argon-low"),
                                 ("codekey-gemini", "gemini-4-argon-medium")):
                with self.subTest(route=route), self.assertRaises(providers.ProviderError):
                    providers.call(route, "fixture", model=model)
            transport.assert_not_called()

    def test_google_reported_base_identity_is_not_the_requested_high_route(self):
        response = self.response("google", "gemini-4-argon")
        with patch.dict(os.environ, self.env(), clear=True), patch.object(
                providers, "_production_request", return_value=response) as transport:
            with self.assertRaises(providers.ProviderError):
                providers.call("codekey-gemini", "fixture", model="gemini-4-argon-high", reasoning_effort="high")
        transport.assert_called_once()

    def test_missing_and_mismatched_identity_cannot_be_disabled(self):
        for route, spec in providers.PRODUCTION_PROVIDERS.items():
            for reported in (None, "unverified-alias"):
                response = self.response(spec["family"], spec["model"], spec["protocol"])
                response["modelVersion" if spec["protocol"] == "gemini_generate_content" else "model"] = reported
                with self.subTest(route=route, reported=reported), patch.dict(os.environ,
                        {**self.env(), "UUAPI_STRICT_MODEL_ID": "false"}, clear=True), patch.object(
                        providers, "_production_request", return_value=response) as transport:
                    with self.assertRaises(providers.ProviderError):
                        providers.call(route, "fixture")
                    transport.assert_called_once()

    def test_incomplete_or_unknown_termination_never_becomes_an_artifact(self):
        examples = [("cheapai-gpt-pro", "status", "incomplete"),
                    ("codekey-kiro-enterprise", "stop_reason", "max_tokens")]
        for route, field, value in examples:
            spec = providers.PRODUCTION_PROVIDERS[route]
            response = self.response(spec["family"], spec["model"], spec["protocol"])
            response[field] = value
            with patch.dict(os.environ, self.env(), clear=True), patch.object(
                    providers, "_production_request", return_value=response):
                with self.assertRaises(providers.ProviderError):
                    providers.call(route, "fixture")

    def test_pdf_and_image_are_native_inputs_with_hashes(self):
        attachments = [self.attachment(), self.attachment("image/png", b"\x89PNG\r\n\x1a\nfixture")]
        result, transport = self.invoke("cheapai-gpt-pro", attachments=attachments)
        content = transport.call_args.args[2]["input"][-1]["content"]
        self.assertEqual([part["type"] for part in content], ["input_text", "input_file", "input_image"])
        self.assertTrue(content[1]["file_data"].startswith("data:application/pdf;base64,"))
        self.assertEqual(result.attachment_sha256, tuple(item["sha256"] for item in attachments))
        result, transport = self.invoke("codekey-gemini", attachments=attachments)
        parts = transport.call_args.args[2]["contents"][0]["parts"]
        self.assertEqual(parts[1]["inlineData"]["mimeType"], "application/pdf")
        self.assertEqual(parts[2]["inlineData"]["data"], attachments[1]["data_base64"])

    def test_utf8_text_attachment_is_decoded_for_openai(self):
        item = self.attachment("text/plain", "evidence α".encode())
        result, transport = self.invoke("cheapai-gpt-pro", attachments=[item])
        self.assertEqual(transport.call_args.args[2]["input"][-1]["content"][-1],
                         {"type": "input_text", "text": "evidence α"})
        self.assertEqual(providers.validate_attachments([item])[0]["decoded"], "evidence α".encode())

    def test_media_rejection_precedes_any_network_or_generation(self):
        wrong_hash = {**self.attachment(), "sha256": "0" * 64}
        wrong_signature = self.attachment("application/pdf", b"not a PDF")
        url_input = {"file_url": "https://private.example/file.pdf"}
        bad_base64 = {**self.attachment(), "data_base64": "not base64?"}
        for attachment in (wrong_hash, wrong_signature, url_input, bad_base64):
            with patch.dict(os.environ, self.env(), clear=True), patch.object(providers, "_production_request") as transport:
                with self.assertRaises(providers.ProviderError):
                    providers.call("cheapai-gpt-pro", "fixture", attachments=[attachment])
                transport.assert_not_called()
        for route in ("codekey-deepseek", "codekey-kiro-enterprise"):
            with patch.dict(os.environ, self.env(), clear=True), patch.object(providers, "_production_request") as transport:
                with self.assertRaises(providers.ProviderError):
                    providers.call(route, "fixture", attachments=[self.attachment()])
                transport.assert_not_called()

    def test_http_failure_never_retries_falls_back_or_leaks_error_body(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            "https://cheapai.info/v1/responses", 502, "gateway secret body", {}, None)
        with patch.dict(os.environ, self.env(), clear=True), patch.object(
                providers.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(providers.ProviderError) as error:
                providers.call("cheapai-gpt-pro", "fixture")
            self.assertIn("502", str(error.exception))
            self.assertNotIn("secret body", str(error.exception))
            opener.open.assert_called_once()
            request = opener.open.call_args.args[0]
            headers = {key.lower(): value for key, value in request.header_items()}
            self.assertEqual(headers["user-agent"], "lunwen-production-research/1.0")
            self.assertEqual(headers["accept"], "application/json")
            self.assertNotIn("Python", headers["user-agent"])
            self.assertNotIn("fixture-only", headers["user-agent"])
            self.assertNotIn("fixture-only", request.full_url)

    def test_scoped_responses_stream_uses_only_complete_terminal_object_and_retains_wire_hash(self):
        full = {"object": "response", "id": "stream-fixture", "model": "gpt-6-astra", "status": "completed",
                "output": [{"type": "reasoning", "summary": [{"text": "PRIVATE_THOUGHT"}]},
                           {"type": "message", "status": "completed", "content": [{"type": "output_text", "text": "final terminal answer"}]}],
                "usage": {"input_tokens": 100, "output_tokens": 20}}
        event = {"type": "response.completed", "sequence_number": 2, "response": full}
        early={"object":"response","id":full["id"],"model":full["model"],"status":"in_progress","output":[],"usage":None}
        created={"type":"response.created","sequence_number":0,"response":early}
        progress={"type":"response.in_progress","sequence_number":1,"response":early}
        wire = ('data: '+json.dumps(created)+'\r\n\r\ndata: '+json.dumps(progress)+'\r\n\r\n'
                + ': heartbeat\r\n\r\ndata: {"type":"response.output_text.delta","delta":"DELTA_MUST_NOT_BECOME_ANSWER"}\r\n\r\n'
                + 'event: response.completed\r\ndata: ' + json.dumps(event) + '\r\n\r\ndata: [DONE]\r\n\r\n').encode()
        opener = Mock(); opener.open.return_value = nullcontext(SimpleNamespace(status=200,
            headers={"Content-Type": "text/event-stream; charset=utf-8"}, read1=io.BytesIO(wire).read1))
        with patch.dict(os.environ, self.env(), clear=True), patch("scripts.model_routing.g1_response_streaming_active", return_value=True), \
             patch.object(providers.urllib.request, "build_opener", return_value=opener):
            result = providers.call("codekey-codex-pro", "complete source fixture", model="gpt-6-astra", stream=True,
                                    reasoning_effort="high", max_output_tokens=12000)
        self.assertEqual(result.text, "final terminal answer")
        metadata = result.response_metadata
        self.assertEqual(metadata["http_evidence"]["raw_http_body_sha256"], hashlib.sha256(wire).hexdigest())
        self.assertEqual(metadata["http_evidence"]["sse_terminal_event"], "response.completed")
        self.assertEqual(metadata["canonical_json_sha256"], hashlib.sha256(json.dumps(full, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest())
        self.assertNotIn("PRIVATE_THOUGHT", json.dumps(metadata))
        self.assertNotIn("DELTA_MUST_NOT", json.dumps(metadata))
        request = opener.open.call_args.args[0]; payload = json.loads(request.data)
        self.assertEqual((payload["stream"], payload["reasoning"], payload["max_output_tokens"]), (True, {"effort": "high"}, 12000))
        self.assertEqual(dict((k.lower(), v) for k,v in request.header_items())["accept"], "text/event-stream")
        opener.open.assert_called_once()

    def test_stream_deltas_done_eof_failure_and_mismatched_terminal_never_succeed(self):
        response = {"object": "response", "id": "stream-fixture", "model": "gpt-6-astra", "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": "answer"}]}],
                    "usage": {"input_tokens": 1, "output_tokens": 2}}
        def frame(kind="response.completed", **overrides):
            return ('event: '+kind+'\ndata: '+json.dumps({"type":kind,"sequence_number":1,"response":{**response,**overrides}})+'\n\n').encode()
        cases = [b'data: [DONE]\n\n', b'data: {"type":"response.output_text.delta","delta":"PRIVATE_THOUGHT"}\n\ndata: [DONE]\n\n',
                 frame()[:-2], frame("response.failed", status="failed"), frame("response.incomplete", status="incomplete"),
                 frame(model="wrong-model"), frame(status="incomplete"), frame()+frame(),
                 frame(usage=None), frame(usage={"input_tokens": 1}), frame(output=[]),
                 b'data: {broken JSON}\n\n', b'event: response.failed\ndata: {"type":"response.completed"}\n\n',
                 b'data: {"type":"error","code":"server_error","message":"PRIVATE_THOUGHT"}\n\n',
                 b'data: '+json.dumps({"type":"response.created","response":response}).encode()+b'\n\ndata: {"type":"response.completed","sequence_number":1}\n\n']
        for kind,key,value in (("response.created","model","different-model"),("response.created","id","different-id"),
                               ("response.in_progress","model","different-model"),("response.in_progress","id","different-id")):
            early={**response,"status":"in_progress","output":[],"usage":None,key:value}
            cases.append(('data: '+json.dumps({"type":kind,"sequence_number":0,"response":early})+'\n\n').encode()+frame())
        cases.append(frame()+b'event: response.failed\ndata: [DONE]\n\n')
        for wire in cases:
            with self.subTest(wire=wire[:45]):
                opener = Mock(); opener.open.return_value = nullcontext(SimpleNamespace(status=200,
                    headers={"Content-Type":"text/event-stream"}, read1=io.BytesIO(wire).read1))
                with patch.dict(os.environ,self.env(),clear=True),patch("scripts.model_routing.g1_response_streaming_active",return_value=True), \
                     patch.object(providers.urllib.request,"build_opener",return_value=opener):
                    with self.assertRaises(providers.ProviderError) as caught:
                        providers.call("codekey-codex-pro","fixture",model="gpt-6-astra",stream=True)
                evidence=caught.exception.response_evidence
                self.assertEqual(evidence["http_evidence"]["raw_http_body_sha256"],hashlib.sha256(wire).hexdigest())
                self.assertNotIn("PRIVATE_THOUGHT",json.dumps(evidence))
                if b'"type":"error"' in wire:
                    self.assertEqual(evidence["diagnostics"]["error_code"],"server_error")
                    self.assertIsNotNone(evidence["canonical_json_sha256"])
                    self.assertEqual(evidence["response"],{"type":"error","code":"server_error"})
                opener.open.assert_called_once()
        wire=json.dumps(response).encode();opener=Mock()
        opener.open.return_value=nullcontext(SimpleNamespace(status=200,headers={"Content-Type":"application/json"},read1=io.BytesIO(wire).read1))
        with patch.dict(os.environ,self.env(),clear=True),patch("scripts.model_routing.g1_response_streaming_active",return_value=True), \
             patch.object(providers.urllib.request,"build_opener",return_value=opener):
            with self.assertRaisesRegex(providers.ProviderError,"wrong content type") as caught:
                providers.call("codekey-codex-pro","fixture",model="gpt-6-astra",stream=True)
        self.assertEqual(caught.exception.response_evidence["http_evidence"]["raw_http_body_sha256"],hashlib.sha256(wire).hexdigest())
        opener.open.assert_called_once()
        with patch.dict(os.environ,self.env(),clear=True),patch.object(providers.urllib.request,"build_opener") as opener:
            with self.assertRaisesRegex(providers.ProviderError,"explicit Astra G1"):
                providers.call("codekey-codex-pro","fixture",model="gpt-6-astra",stream=True)
            opener.assert_not_called()

    def test_stream_read_failure_and_oversize_preserve_only_captured_prefix(self):
        prefix=b'data: {"type":"response.reasoning_text.delta","delta":"PRIVATE_THOUGHT"}\n\n'
        response={"object":"response","id":"stream","model":"gpt-6-astra","status":"completed","output":[],"usage":{"input_tokens":1,"output_tokens":2}}
        terminal=('data: '+json.dumps({"type":"response.completed","sequence_number":0,"response":response})+'\n\n').encode()
        cases=[(Mock(side_effect=[prefix,TimeoutError("PRIVATE_READ_ERROR fixture-only-codekey-codex-pro")]),prefix,None,"TimeoutError"),
               (io.BytesIO(b":"+b"x"*(4*1024*1024+8)).read1,b":"+b"x"*(4*1024*1024),None,None),
               (Mock(side_effect=[terminal,TimeoutError("PRIVATE_READ_ERROR after terminal")]),terminal,"gpt-6-astra","TimeoutError")]
        for source,expected,model,error_type in cases:
            opener=Mock();opener.open.return_value=nullcontext(SimpleNamespace(status=200,headers={"Content-Type":"text/event-stream"},read1=source))
            with patch.dict(os.environ,self.env(),clear=True),patch("scripts.model_routing.g1_response_streaming_active",return_value=True), \
                 patch.object(providers.urllib.request,"build_opener",return_value=opener):
                with self.assertRaises(providers.ProviderError) as caught:
                    providers.call("codekey-codex-pro","fixture",model="gpt-6-astra",stream=True)
            evidence=caught.exception.response_evidence;http=evidence["http_evidence"]
            self.assertFalse(http["http_body_capture_complete"])
            self.assertIsNone(http["raw_http_body_sha256"])
            self.assertEqual(http["captured_http_body_prefix_sha256"],hashlib.sha256(expected).hexdigest())
            self.assertEqual(http.get("response_error_type"),error_type)
            self.assertNotIn("PRIVATE_THOUGHT",json.dumps(evidence))
            self.assertNotIn("PRIVATE_READ_ERROR",json.dumps(evidence))
            self.assertNotIn("fixture-only-codekey-codex-pro",json.dumps(evidence))
            self.assertEqual(evidence["diagnostics"].get("model"),model)
            opener.open.assert_called_once()
        source=Mock(return_value=prefix);opener=Mock()
        opener.open.return_value=nullcontext(SimpleNamespace(status=200,headers={"Content-Type":"text/event-stream"},read1=source))
        with patch.dict(os.environ,self.env(),clear=True),patch("scripts.model_routing.g1_response_streaming_active",return_value=True), \
             patch.object(providers.urllib.request,"build_opener",return_value=opener), \
             patch.object(providers.time,"monotonic",side_effect=[0,0,31]):
            with self.assertRaises(providers.ProviderError):
                providers.call("codekey-codex-pro","fixture",model="gpt-6-astra",stream=True,timeout=30)
        source.assert_called_once()
        opener.open.assert_called_once()

    def test_real_http_stream_rejects_premature_eof_and_invalid_authoritative_start(self):
        full={"object":"response","id":"framing-fixture","model":"gpt-6-astra","status":"completed",
              "output":[{"type":"message","status":"completed","content":[{"type":"output_text","text":"answer"}]}],
              "usage":{"input_tokens":1,"output_tokens":2}}
        terminal=('data: '+json.dumps({"type":"response.completed","sequence_number":1,"response":full})+'\n\n').encode()
        cases=[("complete",b"",0,True),("truncated-content-length",b"",97,False)]
        for kind in ("response.created","response.in_progress"):
            for overrides in ({"status":"failed"},{"object":"wrong"},{"model":None},{"id":"bad id"},{"output":None}):
                early={**full,"status":"in_progress","output":[],"usage":None,**overrides}
                frame=('data: '+json.dumps({"type":kind,"sequence_number":0,"response":early})+'\n\n').encode()
                cases.append((kind+str(overrides),frame,0,False))
        for status in ("queued","in_progress"):
            early={**full,"status":status,"output":[],"usage":None}
            frame=('data: '+json.dumps({"type":"response.created","sequence_number":0,"response":early})+'\n\n').encode()
            cases.append((status+"-empty-valid-start",frame,0,True))
        for name,prefix,missing,accepted in cases:
            with self.subTest(name=name):
                wire=prefix+terminal
                raw=(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: "+str(len(wire)+missing).encode()+b"\r\n\r\n"+wire)
                response=http.client.HTTPResponse(SimpleNamespace(makefile=lambda *args,**kwargs:io.BytesIO(raw)))
                response.begin()
                opener=Mock();opener.open.return_value=response
                with patch.dict(os.environ,self.env(),clear=True),patch("scripts.model_routing.g1_response_streaming_active",return_value=True), \
                     patch.object(providers.urllib.request,"build_opener",return_value=opener):
                    if accepted:
                        self.assertEqual(providers.call("codekey-codex-pro","fixture",model="gpt-6-astra",stream=True).text,"answer")
                    else:
                        with self.assertRaises(providers.ProviderError) as caught:
                            providers.call("codekey-codex-pro","fixture",model="gpt-6-astra",stream=True)
                        capture=caught.exception.response_evidence["http_evidence"]
                        self.assertEqual(capture["http_body_capture_complete"],not missing)
                        if missing:
                            self.assertEqual(capture["response_error_type"],"IncompleteRead")
                            self.assertIsNone(capture["raw_http_body_sha256"])
                            self.assertEqual(capture["captured_http_body_prefix_sha256"],hashlib.sha256(wire).hexdigest())
                            self.assertEqual(response.length,97)
                opener.open.assert_called_once()

    def test_empty_thinking_response_retains_redacted_wire_provenance_without_returning_success(self):
        env = self.env(); secret = env["DR_OS_CODEKEY_KIRO_ENTERPRISE_KEY"]
        response = {"id": "response-fixture", "model": "claude-opus-5-5", "stop_reason": "max_tokens",
            "content": [{"type": "thinking", "thinking": "PRIVATE_THOUGHT " + secret, "signature": "PRIVATE_SIGNATURE"}],
            "usage": {"input_tokens": 100, "output_tokens": 4000, "debug": "PRIVATE_USAGE_DEBUG"}, "authorization": "Bearer " + secret}
        body = json.dumps(response, indent=4).encode()
        opener = Mock(); opener.open.return_value = nullcontext(SimpleNamespace(status=200, read=lambda limit: body[:limit]))
        with patch.dict(os.environ, env, clear=True), patch.object(providers.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(providers.ProviderError, "contained no text") as caught:
                providers.call("codekey-kiro-enterprise", "synthetic request", model="claude-opus-5-5")
        evidence = caught.exception.response_evidence
        self.assertEqual(evidence["http_evidence"]["raw_http_body_sha256"], hashlib.sha256(body).hexdigest())
        self.assertNotEqual(evidence["canonical_json_sha256"], evidence["http_evidence"]["raw_http_body_sha256"])
        self.assertEqual(evidence["diagnostics"]["content_block_types"], ["thinking"])
        self.assertEqual(evidence["diagnostics"]["stop_reason"], "max_tokens")
        self.assertEqual(evidence["diagnostics"]["usage"]["output_tokens"], 4000)
        self.assertNotIn("PRIVATE_USAGE_DEBUG", json.dumps(evidence["diagnostics"]))
        for private in (secret, "PRIVATE_THOUGHT", "PRIVATE_SIGNATURE"):
            self.assertNotIn(private, json.dumps(evidence))
            self.assertNotIn(private, str(caught.exception))
        opener.open.assert_called_once()

    def test_failed_mocked_json_never_claims_wire_bytes_and_preserves_rejected_identity(self):
        for model, status in (("wrong-model", "completed"), ("gpt-6.1-sol", "incomplete")):
            response = {"model": model, "id": "fixture", "status": status, "output_text": "partial text",
                        "usage": {"input_tokens": 2, "output_tokens": 3}}
            with patch.dict(os.environ, self.env(), clear=True), patch.object(providers, "_production_request", return_value=response):
                with self.assertRaises(providers.ProviderError) as caught:
                    providers.call("cheapai-gpt-pro", "synthetic request")
            evidence = caught.exception.response_evidence
            self.assertIsNone(evidence["http_evidence"]["raw_http_body_sha256"])
            self.assertTrue(evidence["canonical_json_hash_available"])
            self.assertEqual(evidence["diagnostics"]["model"], model)

    def test_non_json_http_error_retains_exact_read_hash_without_echoing_credentials(self):
        env = self.env(); secret = env["DR_OS_CODEKEY_KIRO_ENTERPRISE_KEY"]
        body = ("unparsed vendor error " + secret).encode()
        opener = Mock(); opener.open.side_effect = urllib.error.HTTPError(
            "https://codekey.ai/v1/messages", 502, "gateway error", {}, io.BytesIO(body))
        with patch.dict(os.environ, env, clear=True), patch.object(providers.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(providers.ProviderError) as caught:
                providers.call("codekey-kiro-enterprise", "synthetic request")
        evidence = caught.exception.response_evidence
        self.assertEqual(evidence["http_evidence"]["raw_http_body_sha256"], hashlib.sha256(body).hexdigest())
        self.assertIsNone(evidence["canonical_json_sha256"])
        self.assertNotIn(secret, json.dumps(evidence))
        self.assertNotIn("unparsed vendor", str(caught.exception))
        opener.open.assert_called_once()

    def test_error_body_capture_redacts_json_thoughts_and_never_stores_opaque_or_truncated_text(self):
        for body in (b'{"content":[{"type":"thinking","thinking":"PRIVATE_HTTP_THOUGHT"}],"error":"backend failure"}',
                     b'PRIVATE_HTTP_THOUGHT invalid-json'):
            evidence = providers._response_evidence(None, body=body, http_status=500)
            self.assertNotIn("PRIVATE_HTTP_THOUGHT", json.dumps(evidence))
            self.assertEqual(evidence["http_evidence"]["raw_http_body_sha256"], hashlib.sha256(body).hexdigest())
        prefix = b'PRIVATE_HTTP_THOUGHT truncated'
        evidence = providers._response_evidence(None, body=prefix, http_status=200, complete=False)
        self.assertIsNone(evidence["http_evidence"]["raw_http_body_sha256"])
        self.assertEqual(evidence["http_evidence"]["captured_http_body_prefix_sha256"], hashlib.sha256(prefix).hexdigest())
        self.assertNotIn("PRIVATE_HTTP_THOUGHT", json.dumps(evidence))

    def test_reported_model_exception_attribute_cannot_echo_selected_key(self):
        env = self.env(); secret = env["DR_OS_CHEAPAI_GPT_PRO_KEY"]
        with patch.dict(os.environ, env, clear=True), patch.object(providers, "_production_request", return_value={"model":secret}):
            with self.assertRaises(providers.ProviderError) as caught:
                providers.call("cheapai-gpt-pro", "synthetic request")
        self.assertIsNone(caught.exception.reported_model)
        self.assertNotIn(secret, json.dumps(caught.exception.response_evidence))

    def test_read_body_hash_survives_non_decode_json_parser_errors(self):
        body = b'{"value":' + b'9' * 5000 + b'}'
        opener = Mock(); opener.open.return_value = nullcontext(SimpleNamespace(status=200, read=lambda limit: body[:limit]))
        with patch.dict(os.environ, self.env(), clear=True), patch.object(providers.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(providers.ProviderError) as caught:
                providers.call("codekey-kiro-enterprise", "synthetic request")
        self.assertEqual(caught.exception.response_evidence["http_evidence"]["raw_http_body_sha256"], hashlib.sha256(body).hexdigest())
        self.assertIsNone(caught.exception.response_evidence["canonical_json_sha256"])

    def test_protocol_success_with_truncated_caller_json_keeps_only_safe_response_metadata(self):
        response = self.response("anthropic", "claude-opus-5-5")
        response["content"][1]["text"] = '{"anchor_labels":[{"rationale":"'
        body = json.dumps(response, indent=4).encode()
        opener = Mock(); opener.open.return_value = nullcontext(SimpleNamespace(status=200, read=lambda limit: body[:limit]))
        with patch.dict(os.environ, self.env(), clear=True), patch.object(providers.urllib.request, "build_opener", return_value=opener):
            result = providers.call("codekey-kiro-enterprise", "synthetic request", model="claude-opus-5-5")
        with self.assertRaises(json.JSONDecodeError):
            json.loads(result.text)
        metadata = result.response_metadata
        self.assertEqual(metadata["diagnostics"]["stop_reason"], "end_turn")
        self.assertEqual(metadata["diagnostics"]["content_block_types"], ["thinking", "text"])
        self.assertEqual(metadata["http_evidence"]["raw_http_body_sha256"], hashlib.sha256(body).hexdigest())
        self.assertTrue(metadata["metadata_only"])
        self.assertFalse(metadata["original_response_body_retained"])
        self.assertNotIn("response", metadata)
        self.assertNotIn("private thought", json.dumps(metadata))

    def test_redirect_handler_refuses_credential_forwarding_and_post_replay(self):
        handler = providers._NoGenerationRedirect()
        for target in ("https://other.example/steal", "https://cheapai.info/another"):
            with self.assertRaises(providers.ProviderError):
                handler.redirect_request(None, None, 307, "redirect", {}, target)

    def test_production_transport_rejects_other_hosts_and_credential_urls(self):
        with patch.object(providers.urllib.request, "build_opener") as opener:
            for endpoint in ("http://cheapai.info/v1/responses", "https://other.example/v1/responses",
                             "https://cheapai.info@other.example/v1/responses",
                             "https://codekey.ai/v1/messages?key=secret"):
                with self.assertRaises(providers.ProviderError):
                    providers._production_request(endpoint, {}, {}, 10)
            opener.assert_not_called()

    def test_legacy_none_arguments_preserve_existing_call_signature(self):
        expected = providers.ModelResult("openai", "fixture", "OK", {})
        with patch.object(providers, "call_openai", return_value=expected) as legacy:
            self.assertIs(providers.call("openai", "fixture", reasoning_effort=None, attachments=None), expected)
            legacy.assert_called_once_with("fixture")
        with self.assertRaises(providers.ProviderError):
            providers.call("uuapi-openai", "fixture", reasoning_effort="high")

