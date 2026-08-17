from __future__ import annotations

import unittest

from scripts.network_safety import (
    NetworkSafetyError,
    PublicHTTPSRedirectHandler,
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


if __name__ == "__main__":
    unittest.main()
