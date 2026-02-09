import unittest
from types import SimpleNamespace
from unittest.mock import patch

import base

class FakeDownstreamResponse:
    def __init__(self, status_code=200, content=b'{"message":"ok"}', headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers if headers is not None else {}

class BaseTests(unittest.TestCase):
    def setUp(self):
        base.token_counts.clear()
        base.req_counts.clear()
        base.rules = {
            "hittero": {"capacity": 2, "refill_rate": 2},
            "default": {"capacity": 1, "refill_rate": 1},
        }
        base.args = SimpleNamespace(alg=base.AlgorithmType.BUCKET_TOKEN)
        self.client = base.app.test_client()

    def test_health_endpoint(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Ratelimiter is healthy", response.get_data(as_text=True))

    def test_invalid_path_returns_404(self):
        response = self.client.get("/api/not-real", headers={"X-User-Id": "hittero"})

        self.assertEqual(response.status_code, 404)
        self.assertIn("invalid_request", response.get_data(as_text=True))

    @patch("base.requests.request")
    def test_bucket_token_allows_and_sets_headers(self, mock_request):
        mock_request.return_value = FakeDownstreamResponse(
            status_code=200,
            content=b'{"message":"Ping 1 successful!"}',
            headers={},
        )

        response = self.client.get("/api/ping1", headers={"X-User-Id": "hittero"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-RateLimit-Limit"), "2")
        self.assertEqual(response.headers.get("X-RateLimit-Remaining"), "1")

    @patch("base.requests.request")
    def test_bucket_token_blocks_when_capacity_exhausted(self, mock_request):
        mock_request.return_value = FakeDownstreamResponse(status_code=200, headers={})

        first = self.client.get("/api/ping1", headers={"X-User-Id": "hittero"})
        second = self.client.get("/api/ping1", headers={"X-User-Id": "hittero"})
        third = self.client.get("/api/ping1", headers={"X-User-Id": "hittero"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.headers.get("X-RateLimit-Limit"), "2")
        self.assertEqual(third.headers.get("X-RateLimit-Remaining"), "0")
        self.assertIsNotNone(third.headers.get("Retry-After"))

    def test_bucket_token_refills_after_time_passes(self):
        base.args = SimpleNamespace(alg=base.AlgorithmType.BUCKET_TOKEN)

        with patch("base.proxy_request", return_value=base.Response("ok", status=200)):
            with patch("base.time.monotonic", side_effect=[100.0, 100.0]):
                allowed = base.bucket_token("hittero", "ping1")
            with patch("base.time.monotonic", side_effect=[131.0]):
                allowed_after_refill = base.bucket_token("hittero", "ping1")

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed_after_refill.status_code, 200)

    def test_sliding_window_blocks_at_capacity(self):
        base.args = SimpleNamespace(alg=base.AlgorithmType.SLIDING_WINDOW)

        with patch("base.proxy_request", return_value=base.Response("ok", status=200)):
            with patch("base.time.monotonic", side_effect=[100.0, 101.0, 102.0]):
                first = base.sliding_window("hittero", "ping1")
                second = base.sliding_window("hittero", "ping1")
                third = base.sliding_window("hittero", "ping1")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.headers.get("X-RateLimit-Limit"), "2")
        self.assertEqual(third.headers.get("X-RateLimit-Remaining"), "0")

    def test_sliding_window_expires_old_requests(self):
        base.args = SimpleNamespace(alg=base.AlgorithmType.SLIDING_WINDOW)

        with patch("base.proxy_request", return_value=base.Response("ok", status=200)):
            with patch("base.time.monotonic", side_effect=[100.0, 101.0, 162.0]):
                first = base.sliding_window("hittero", "ping1")
                second = base.sliding_window("hittero", "ping1")
                third = base.sliding_window("hittero", "ping1")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 200)

if __name__ == "__main__":
    unittest.main()
