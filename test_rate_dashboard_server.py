from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rate_dashboard_server import create_app


class RateDashboardServerTests(unittest.TestCase):
    def test_status_and_health_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(Path(temp_dir) / "snapshot.json", start_scheduler=False)
            client = app.test_client()

            status_response = client.get("/api/status")
            self.assertEqual(status_response.status_code, 200)
            status_payload = status_response.get_json()
            assert status_payload is not None
            self.assertIn("current_period", status_payload)
            self.assertIn("today_schedule", status_payload)
            self.assertIn("snapshot", status_payload)
            self.assertIn("source", status_payload)

            page_response = client.get("/")
            self.assertEqual(page_response.status_code, 200)
            self.assertIn(b"PEC Rate Dashboard", page_response.data)

            health_response = client.get("/healthz")
            self.assertEqual(health_response.status_code, 200)
            health_payload = health_response.get_json()
            assert health_payload is not None
            self.assertTrue(health_payload["ok"])
            self.assertIn("saved_at", health_payload)


if __name__ == "__main__":
    unittest.main()
