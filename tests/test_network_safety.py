from __future__ import annotations

import unittest

from scripts.network_safety import (
    NetworkSafetyError,
    PublicHTTPSRedirectHandler,
    fetch_json,
    require_public_https_url,
)


class NetworkSafetyTests(unittest.TestCase):
    @staticmethod
    def resolver(host: str, port: int, type: int):  # noqa: A002 - socket API fixture
        address = "10.0.0.5" if host == "private.example" else "93.184.216.34"
        return [(2, 1, 6, "", (address, port))]

    def test_public_https_is_accepted(self) -> None:
        self.assertEqual(
            require_public_https_url("https://public.example/data", resolver=self.resolver),
            "https://public.example/data",
        )

    def test_private_and_credentialed_targets_are_rejected(self) -> None:
        with self.assertRaises(NetworkSafetyError):
            require_public_https_url("https://private.example/data", resolver=self.resolver)
        with self.assertRaises(NetworkSafetyError):
            require_public_https_url(
                "https://user:pass@public.example/data", resolver=self.resolver
            )

    def test_private_redirect_is_rejected_before_following(self) -> None:
        handler = PublicHTTPSRedirectHandler(self.resolver)
        with self.assertRaises(NetworkSafetyError):
            handler.redirect_request(
                None,
                None,
                302,
                "Found",
                {},
                "https://private.example/internal",
            )

    def test_json_post_body_is_encoded_without_credentials(self) -> None:
        class Response:
            headers = {"Content-Length": "12"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def geturl(self):
                return "https://public.example/search"

            def read(self, _limit):
                return b'{"ok": true}'

        captured = {}

        def opener(request, timeout):
            captured["method"] = request.get_method()
            captured["data"] = request.data
            captured["content_type"] = request.get_header("Content-type")
            captured["timeout"] = timeout
            return Response()

        value = fetch_json(
            "https://public.example/search",
            method="POST",
            json_body={"q": "bearing"},
            opener=opener,
            resolver=self.resolver,
        )
        self.assertEqual(value, {"ok": True})
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["data"], b'{"q": "bearing"}')
        self.assertEqual(captured["content_type"], "application/json")


if __name__ == "__main__":
    unittest.main()
